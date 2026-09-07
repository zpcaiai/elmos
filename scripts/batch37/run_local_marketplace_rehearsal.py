#!/usr/bin/env python3
"""Build the local Batch 37 core and emit an explicitly non-certified pack."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from _common import load, write


PACK_KEY = "elmos-local-extension-marketplace"


def digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def tree_digest(root: Path, excluded: set[str] | None = None) -> str:
    excluded = excluded or set()
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root)
        if any(part in excluded for part in relative.parts):
            continue
        digest.update(str(relative).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def command(argv: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, text=True, capture_output=True)


def locate_maven(explicit: str | None) -> str:
    candidates = [explicit, os.environ.get("MAVEN_CMD"), shutil.which("mvn"),
                  "/tmp/elmos-b36-tooling/apache-maven-3.9.11/bin/mvn"]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return str(Path(candidate).resolve())
    raise SystemExit("Maven 3.9+ is required; pass --maven-command or set MAVEN_CMD")


def totals(report_root: Path) -> dict[str, int]:
    result = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for report in sorted(report_root.glob("TEST-*.xml")):
        suite = ET.parse(report).getroot()
        for key in result:
            result[key] += int(suite.attrib.get(key, 0))
    return result


def corpus(pack: Path, relative: str, status: str, source_digest: str,
           evidence_refs: list[str], independent: bool, execution_kind: str) -> None:
    write(pack / relative / "manifest.json", {
        "schema_version": 1,
        "status": status,
        "source_digest": source_digest,
        "dataset_digest": digest_bytes((relative + status + source_digest).encode()),
        "independent": independent,
        "execution_kind": execution_kind,
        "authorization_refs": [],
        "evidence_refs": evidence_refs,
        "reason": None if status == "passed" else "No independent external execution was authorized or performed.",
    })


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--maven-command")
    parser.add_argument("--pack-key", default=PACK_KEY)
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    module = root / "modules" / "extension-marketplace"
    maven = locate_maven(args.maven_command)
    source_digest = tree_digest(root / ".agents" / "skills", {"target"})
    runtime_digest = tree_digest(module, {"target"})

    java_version = command(["java", "-version"], root)
    maven_version = command([maven, "-version"], root)
    if java_version.returncode or maven_version.returncode:
        raise SystemExit("Java or Maven inspection failed")
    environment_text = java_version.stderr + java_version.stdout + maven_version.stdout + maven_version.stderr
    environment_digest = digest_bytes(environment_text.encode())

    build_command = [maven, "-q", "-pl", "modules/extension-marketplace", "test"]
    build = command(build_command, root)
    test_totals = totals(module / "target" / "surefire-reports")
    if build.returncode or test_totals["tests"] < 1 or test_totals["failures"] or test_totals["errors"]:
        sys.stderr.write(build.stdout + build.stderr)
        raise SystemExit("local extension-marketplace tests failed")

    cli_base = ["java", "-cp", str(module / "target" / "classes"), "io.elmos.marketplace.MarketplaceCli"]
    inspect = command(cli_base + ["inspect"], root)
    evaluate = command(cli_base + ["evaluate"], root)
    if inspect.returncode or evaluate.returncode:
        raise SystemExit("local Marketplace CLI rehearsal failed")
    inspect_result, evaluate_result = json.loads(inspect.stdout), json.loads(evaluate.stdout)
    if inspect_result.get("status") != "READY" or evaluate_result.get("decision") != "ALLOW":
        raise SystemExit("local Marketplace CLI did not return the expected safe decision")

    scaffold = command([
        sys.executable, str(root / "scripts" / "batch37" / "scaffold_marketplace_pack.py"),
        "--pack-key", args.pack_key, "--product-version", "0.1.0",
        "--protocol-version", "1.0.0", "--edition", "local",
        "--risk-tier", "P1", "--environment-digest", environment_digest,
        "--publisher-id", "elmos-local", "--extension-id", "elmos.local.extension",
        "--repo-root", str(root), "--force",
    ], root)
    if scaffold.returncode:
        sys.stderr.write(scaffold.stdout + scaffold.stderr)
        return scaffold.returncode
    pack = root / "marketplace-packs" / args.pack_key

    local_refs = ["certification/local-test-result.json", "certification/local-cli-result.json",
                  "certification/source-manifest.json"]
    write(pack / "certification" / "local-test-result.json", {
        "schema_version": 1, "status": "passed", "execution_kind": "real-local-maven",
        "command": build_command, "return_code": build.returncode, "totals": test_totals,
        "environment_digest": environment_digest, "stdout": build.stdout, "stderr": build.stderr,
    })
    write(pack / "certification" / "local-cli-result.json", {
        "schema_version": 1, "status": "passed", "execution_kind": "real-local-java-cli",
        "inspect": inspect_result, "evaluate": evaluate_result,
    })
    write(pack / "certification" / "source-manifest.json", {
        "schema_version": 1, "skill_source_digest": source_digest,
        "runtime_source_digest": runtime_digest, "environment_digest": environment_digest,
        "java_version": (java_version.stderr or java_version.stdout).splitlines()[0],
        "maven_version": maven_version.stdout.splitlines()[0],
    })

    manifest = load(pack / "pack.json")
    manifest.update({"version": "0.1.0", "status": "experimental",
                     "owner": "elmos-marketplace", "maintenance_owner": "elmos-platform"})
    write(pack / "pack.json", manifest)

    package_path = pack / "releases" / "sample" / "package.tgz"
    package_path.write_bytes(b"ELMOS Batch 37 local rehearsal artifact\n")
    artifact_digest = digest_bytes(package_path.read_bytes())
    extension = load(pack / "extensions" / "sample" / "manifest.json")
    extension["product_compatibility"]["product"] = "0.1.0"
    extension["artifacts"]["package_digest"] = artifact_digest
    extension["local_runtime_class"] = "io.elmos.marketplace.MarketplaceCli"
    extension["field_validation_status"] = "NOT_RUN"
    write(pack / "extensions" / "sample" / "manifest.json", extension)
    release = load(pack / "releases" / "sample" / "release.json")
    release.update({"status": "draft", "channel": "preview", "artifact_digest": artifact_digest,
                    "published_at": "NOT_RUN", "signature_status": "NOT_RUN",
                    "external_release_status": "NOT_RUN"})
    write(pack / "releases" / "sample" / "release.json", release)
    (pack / "releases" / "sample" / "signature.sig").write_text("NOT_RUN: production signing was not performed\n")
    write(pack / "releases" / "sample" / "sbom.json", {"status": "local-test-only", "artifact_digest": artifact_digest})
    write(pack / "releases" / "sample" / "provenance.json", {"status": "local-test-only", "runtime_source_digest": runtime_digest})

    publisher_path = pack / manifest["contracts"]["publisher_profile"]
    publisher = load(publisher_path)
    publisher.update({"legal_name": "ELMOS local rehearsal", "status": "pending", "verified": False,
                      "organization_owner": "elmos-marketplace", "security_contact": "security@example.invalid",
                      "agreements": [], "signing_identities": [], "payout_status": "pending",
                      "external_identity_status": "NOT_RUN"})
    publisher["maintainers"] = [{"subject_id": "local-maintainer", "role": "owner", "mfa": True}]
    write(publisher_path, publisher)

    compatibility = load(pack / "compatibility" / "matrix.json")
    compatibility.update({"product_versions": ["0.1.0"], "external_conformance_status": "NOT_RUN"})
    compatibility["entries"] = [{"product": "0.1.0", "protocol": "1.0.0", "sdk": "1.0.0",
                                   "status": "conditional", "evidence_refs": local_refs}]
    write(pack / "compatibility" / "matrix.json", compatibility)

    support = load(pack / "support-matrix.json")
    for capability in support["capabilities"]:
        capability.update({"owner": "elmos-marketplace", "status": "experimental",
                           "evidence_refs": local_refs,
                           "conditions": ["Local Java core only; external Marketplace execution is NOT_RUN."]})
    write(pack / "support-matrix.json", support)

    evidence = load(pack / "certification" / "evidence.json")
    evidence.update({"external_evidence_status": "NOT_RUN", "measurement_scope": "local-java-core-and-cli-only",
                     "evidence_refs": local_refs})
    local_metrics = {"abi_conformance_rate", "sdk_conformance_rate", "sandbox_conformance_rate",
                     "extension_build_pass_rate", "negative_security_pass_rate", "signature_verification_rate"}
    evidence["metrics"] = {key: (1 if key in local_metrics else 0) for key in evidence["metrics"]}
    write(pack / "certification" / "evidence.json", evidence)
    certification = load(pack / "certification" / "certification.json")
    certification.update({"status": "experimental", "owner": "elmos-quality", "exact_scope": manifest["scope"],
                          "metrics": evidence["metrics"], "zero_tolerance": evidence["zero_tolerance"],
                          "evidence_refs": local_refs, "expires_at": "NOT_RUN",
                          "external_evidence_status": "NOT_RUN",
                          "limitations": ["Publisher identity and production signing: NOT_RUN",
                                          "Independent holdout and representative extensions: NOT_RUN",
                                          "Install, upgrade, rollback, revocation and billing providers: NOT_RUN",
                                          "Private and air-gapped Marketplace execution: NOT_RUN"]})
    write(pack / "certification" / "certification.json", certification)
    closure = load(pack / "certification" / "closure-certification.json")
    closure.update({"pack_key": args.pack_key, "status": "experimental", "owner": "elmos-quality",
                    "evidence_status": "NOT_RUN", "evidence_refs": local_refs,
                    "limitations": ["All external lifecycle, operations, legal, settlement and EOL evidence is NOT_RUN."]})
    write(pack / "certification" / "closure-certification.json", closure)

    external_contracts = [
        "dependencies/lock.json", "runtime/health.json", "catalog/catalog-entry.json",
        "catalog/ranking-policy.json", "publishers/lifecycle.json", "certification/recertification-policy.json",
        "migrations/extension-migration.json", "continuity/revocation-plan.json", "legal-support/policy.json",
        "private-marketplace/policy.json", "offline-mirror/policy.json", "operations/operations-policy.json",
        "commercial/settlement.json", "lifecycle/eol-policy.json",
    ]
    for relative in external_contracts:
        payload = load(pack / relative)
        payload["evidence_status"] = "NOT_RUN"
        payload["limitations"] = ["No authorized external execution was performed."]
        write(pack / relative, payload)
    catalog = load(pack / "catalog" / "catalog-entry.json")
    catalog.update({"certification_status": "experimental", "discoverable": False, "ranking_eligible": False})
    write(pack / "catalog" / "catalog-entry.json", catalog)
    migration = load(pack / "migrations" / "extension-migration.json")
    for key in ["dry_run_passed", "checkpointed", "reconciliation_passed", "rollback_tested", "mixed_version_tested"]:
        migration[key] = False
    write(pack / "migrations" / "extension-migration.json", migration)
    continuity = load(pack / "continuity" / "revocation-plan.json")
    continuity.update({"affected_tenants_known": False, "notifications_complete": False, "tested": False})
    continuity["replacement_or_exit"] = {"available": False, "config_export": False, "data_export": False}
    write(pack / "continuity" / "revocation-plan.json", continuity)
    offline = load(pack / "offline-mirror" / "policy.json")
    offline.update({"signature_verified": False, "disconnected_tested": False, "emergency_revoke_tested": False})
    write(pack / "offline-mirror" / "policy.json", offline)
    operations = load(pack / "operations" / "operations-policy.json")
    operations.update({"backup_restore_tested": False, "dr_tested": False, "state_reconciled": False})
    write(pack / "operations" / "operations-policy.json", operations)
    eol = load(pack / "lifecycle" / "eol-policy.json")
    eol.update({"deprecation_announced": False, "replacement_or_exit_available": False,
                "config_export_tested": False, "data_portability_tested": False,
                "uninstall_tested": False, "customers_unresolved": 1})
    write(pack / "lifecycle" / "eol-policy.json", eol)

    for relative in ["dependencies/evidence.txt", "runtime/evidence.txt", "catalog/evidence.txt",
                     "catalog/ranking-evidence.txt", "publishers/lifecycle-evidence.txt",
                     "certification/recertification-evidence.txt", "migrations/evidence.txt",
                     "continuity/evidence.txt", "legal/evidence.txt", "support/evidence.txt",
                     "private-marketplace/evidence.txt", "offline-mirror/evidence.txt",
                     "operations/evidence.txt", "commercial/settlement-evidence.txt", "lifecycle/evidence.txt"]:
        target = pack / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("NOT_RUN: external evidence was not authorized or executed.\n")

    corpus(pack, "corpus/development", "passed", source_digest, local_refs, False, "real-local-maven")
    corpus(pack, "corpus/negative", "passed", source_digest, ["certification/local-test-result.json"], False, "real-local-maven")
    for relative in ["corpus/holdout", "corpus/representative-extensions", "corpus/closure-holdout", "corpus/representative-lifecycle"]:
        corpus(pack, relative, "NOT_RUN", source_digest, [], False, "NOT_RUN")

    (pack / "certification" / "gap-inventory.md").write_text(
        "# Batch 37 gap inventory\n\n"
        "- Verify publisher organization, maintainers, agreements, payout identity, and production signing keys.\n"
        "- Run independent negative, holdout, representative extension, and lifecycle corpora.\n"
        "- Execute installation, upgrade, rollback, quarantine, revocation, and customer continuity in approved environments.\n"
        "- Exercise private and disconnected mirrors, emergency revocation, backup/restore, and DR.\n"
        "- Reconcile provider metering, invoices, refunds, taxes, payouts, fraud controls, support, legal, and EOL evidence.\n",
        encoding="utf-8")
    (pack / "README.md").write_text(
        "# ELMOS local extension Marketplace\n\n"
        "This experimental pack records a real local Java build, 24 policy/runtime tests, and safe CLI execution. "
        "It is not a publisher, production signing, Marketplace, private/offline, commercial, or closure certification.\n",
        encoding="utf-8")

    for validator in ["validate_marketplace_pack.py", "validate_marketplace_closure.py"]:
        result = command([sys.executable, str(root / "scripts" / "batch37" / validator), str(pack)], root)
        if result.returncode:
            sys.stderr.write(result.stdout + result.stderr)
            return result.returncode
    for gate_name in ["run_marketplace_gate.py", "run_marketplace_closure_gate.py"]:
        result = command([sys.executable, str(root / "scripts" / "batch37" / gate_name), str(pack)], root)
        sys.stdout.write(result.stdout); sys.stderr.write(result.stderr)
        if result.returncode:
            return result.returncode
    core_result = load(pack / "certification" / "gate-result.json")
    closure_result = load(pack / "certification" / "closure-gate-result.json")
    if core_result.get("certification_decision") != "NOT_CERTIFIED" or closure_result.get("closure_decision") != "NOT_CERTIFIED" or closure_result.get("closure_complete"):
        raise SystemExit("experimental local rehearsal must remain NOT_CERTIFIED and closure-incomplete")
    print(f"LOCAL BATCH37 REHEARSAL PASS: {pack} tests={test_totals['tests']} decisions=NOT_CERTIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
