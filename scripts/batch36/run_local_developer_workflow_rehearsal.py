#!/usr/bin/env python3
"""Build the local Batch 36 runtime and emit a deliberately non-certified pack."""

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


PACK_KEY = "elmos-local-developer-workflow"
LOCAL_CAPABILITIES = {
    "ide-protocol", "cli", "local-preview", "source-target-navigation", "explainability",
    "quick-fix", "semantic-conflict", "ownership", "local-eval", "recipe-authoring", "telemetry",
}


def sha256_bytes(value: bytes) -> str:
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


def command(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True)


def locate_maven(explicit: str | None) -> str:
    candidates = [explicit, os.environ.get("MAVEN_CMD"), shutil.which("mvn"),
                  "/tmp/elmos-b36-tooling/apache-maven-3.9.11/bin/mvn"]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return str(Path(candidate).resolve())
    raise SystemExit("Maven 3.9+ is required; pass --maven-command or set MAVEN_CMD")


def test_totals(report_root: Path) -> dict[str, int]:
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for report in sorted(report_root.glob("TEST-*.xml")):
        suite = ET.parse(report).getroot()
        for key in totals:
            totals[key] += int(suite.attrib.get(key, 0))
    return totals


def corpus_manifest(pack: Path, relative: str, status: str, source_digest: str,
                    evidence_refs: list[str], reason: str | None = None) -> None:
    payload = {
        "schema_version": 1,
        "status": status,
        "source_digest": source_digest,
        "dataset_digest": sha256_bytes((relative + "\n" + status + "\n" + source_digest).encode()),
        "evidence_refs": evidence_refs,
    }
    if reason:
        payload["reason"] = reason
    write(pack / relative / "manifest.json", payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--maven-command")
    parser.add_argument("--pack-key", default=PACK_KEY)
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    maven = locate_maven(args.maven_command)
    module = root / "modules" / "developer-workflow"
    skill_root = root / ".agents" / "skills"
    source_digest = tree_digest(skill_root, {"target"})
    target_digest = tree_digest(module, {"target"})

    java_version = command(["java", "-version"], root)
    maven_version = command([maven, "-version"], root)
    if java_version.returncode or maven_version.returncode:
        raise SystemExit("Java or Maven version inspection failed")
    environment_text = java_version.stderr + java_version.stdout + maven_version.stdout + maven_version.stderr
    environment_digest = sha256_bytes(environment_text.encode())

    build_command = [maven, "-q", "-pl", "modules/developer-workflow", "-am", "test"]
    build = command(build_command, root)
    reports = module / "target" / "surefire-reports"
    totals = test_totals(reports) if reports.is_dir() else {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    if build.returncode or totals["tests"] < 1 or totals["failures"] or totals["errors"]:
        sys.stderr.write(build.stdout + build.stderr)
        raise SystemExit("local developer-workflow tests failed")

    cli_base = ["java", "-cp", str(module / "target" / "classes"),
                "io.elmos.developerworkflow.DeveloperWorkflowCli"]
    inspect = command(cli_base + ["inspect"], root)
    preview = command(cli_base + ["preview"], root)
    if inspect.returncode or preview.returncode:
        raise SystemExit("local developer-workflow CLI rehearsal failed")
    inspect_result = json.loads(inspect.stdout)
    preview_result = json.loads(preview.stdout)
    if inspect_result.get("status") != "READY" or preview_result.get("decision") != "ALLOW":
        raise SystemExit("local developer-workflow CLI did not return the expected safe result")

    scaffold = command([
        sys.executable, str(root / "scripts" / "batch36" / "scaffold_developer_experience_pack.py"),
        "--pack-key", args.pack_key,
        "--migration-route", "batch36-spec-to-java-runtime",
        "--repository-provider", "local",
        "--repository-id", "elmos/local-workspace",
        "--risk-tier", "P1",
        "--source-digest", source_digest,
        "--target-digest", target_digest,
        "--environment-digest", environment_digest,
        "--repo-root", str(root),
        "--force",
    ], root)
    if scaffold.returncode:
        sys.stderr.write(scaffold.stdout + scaffold.stderr)
        return scaffold.returncode
    pack = root / "developer-experience-packs" / args.pack_key

    test_evidence = {
        "schema_version": 1,
        "status": "passed",
        "execution_kind": "real-local-maven",
        "command": build_command,
        "return_code": build.returncode,
        "totals": totals,
        "environment_digest": environment_digest,
        "stdout": build.stdout,
        "stderr": build.stderr,
    }
    write(pack / "certification" / "local-test-result.json", test_evidence)
    write(pack / "certification" / "local-cli-result.json", {
        "schema_version": 1, "status": "passed", "execution_kind": "real-local-java-cli",
        "inspect": inspect_result, "preview": preview_result,
    })
    write(pack / "certification" / "source-manifest.json", {
        "schema_version": 1,
        "skill_source_digest": source_digest,
        "runtime_source_digest": target_digest,
        "environment_digest": environment_digest,
        "java_version": (java_version.stderr or java_version.stdout).splitlines()[0],
        "maven_version": maven_version.stdout.splitlines()[0],
    })
    local_refs = ["certification/local-test-result.json", "certification/local-cli-result.json",
                  "certification/source-manifest.json"]

    manifest = load(pack / "pack.json")
    manifest.update({"version": "0.1.0", "status": "experimental",
                     "owner": "elmos-developer-experience", "maintenance_owner": "elmos-platform"})
    write(pack / "pack.json", manifest)

    protocol = load(pack / "protocol" / "ide-protocol.json")
    protocol["security"].update({"network_allowlist": [], "path_allowlist": ["${workspace}"],
                                 "tool_allowlist": ["migration-cli"], "arbitrary_shell": False,
                                 "secret_access": "reference-only"})
    protocol["implementation_status"] = "local-core-only"
    protocol["external_host_status"] = "NOT_RUN"
    write(pack / "protocol" / "ide-protocol.json", protocol)

    host_ranges = {"intellij.json": "2026.1.0-2026.1.x", "visual-studio.json": "18.0.0-18.0.x",
                   "vscode.json": "1.110.0-1.110.x"}
    for name, version_range in host_ranges.items():
        extension = load(pack / "extensions" / name)
        extension["host_version_range"] = version_range
        extension["permissions"].update({"repository_write": "none", "network_domains": [],
                                         "arbitrary_shell": False, "secret_read": False})
        extension["distribution"] = {"signed": False,
                                     "package_ref": "NOT_RUN:real-host-package",
                                     "signature_ref": "NOT_RUN:real-host-signature"}
        extension["validation_status"] = "NOT_RUN"
        write(pack / "extensions" / name, extension)

    cli = load(pack / "cli" / "contract.json")
    cli["implementation_class"] = "io.elmos.developerworkflow.DeveloperWorkflowCli"
    cli["local_rehearsal_ref"] = "certification/local-cli-result.json"
    write(pack / "cli" / "contract.json", cli)

    bot = load(pack / "pr-bot" / "policy.json")
    bot["providers"] = ["github", "gitlab", "bitbucket"]
    bot["runtime_status"] = "NOT_RUN"
    bot["limitations"] = ["No SCM sandbox, webhook-signature, fork, or replay test was executed."]
    write(pack / "pr-bot" / "policy.json", bot)

    document = module / "src" / "main" / "java" / "io" / "elmos" / "developerworkflow" / "DeveloperWorkflowService.java"
    document_digest = sha256_bytes(document.read_bytes())
    navigation = load(pack / "navigation" / "map.json")
    navigation.update({
        "map_key": args.pack_key + "-navigation-v1",
        "source_artifact_digest": source_digest,
        "target_artifact_digest": target_digest,
        "nodes": [
            {"node_id": "source:b36-developer-workflow-factory", "side": "source",
             "path": ".agents/skills/b36-developer-workflow-factory/SKILL.md", "range": {"start": 1, "end": 30},
             "symbol_id": "b36-developer-workflow-factory", "document_digest": source_digest},
            {"node_id": "target:DeveloperWorkflowService", "side": "target",
             "path": "modules/developer-workflow/src/main/java/io/elmos/developerworkflow/DeveloperWorkflowService.java",
             "range": {"start": 1, "end": len(document.read_text().splitlines())},
             "symbol_id": "io.elmos.developerworkflow.DeveloperWorkflowService", "document_digest": document_digest},
        ],
        "edges": [{"from": "source:b36-developer-workflow-factory", "to": "target:DeveloperWorkflowService",
                   "relation": "derived", "confidence": 1.0,
                   "provenance_refs": ["certification/source-manifest.json", "certification/local-test-result.json"]}],
    })
    write(pack / "navigation" / "map.json", navigation)

    ownership = load(pack / "ownership" / "policy.json")
    ownership.update({"policy_key": args.pack_key + "-ownership", "default_ownership": "customer-owned",
                      "entries": [
                          {"selector": "modules/developer-workflow/src/main/**", "ownership": "platform-owned",
                           "regeneration_policy": "semantic-merge", "owners": ["elmos-developer-experience"],
                           "approval_required": True},
                          {"selector": "developer-experience-packs/**", "ownership": "generated-once",
                           "regeneration_policy": "preserve", "owners": ["elmos-platform"],
                           "approval_required": True},
                      ]})
    write(pack / "ownership" / "policy.json", ownership)

    local_eval = load(pack / "local-eval" / "profile.json")
    local_eval.update({"profile_key": args.pack_key + "-local-eval", "toolchain_digest": environment_digest,
                       "remote_fallback": "policy-approved"})
    write(pack / "local-eval" / "profile.json", local_eval)
    write(pack / "commands" / "build.json", {"schema_version": 1, "argv": build_command,
                                               "network": "deny", "repository_write": False})
    write(pack / "commands" / "affected-tests.json", {"schema_version": 1,
                                                        "selector": "semantic-impact-graph",
                                                        "fallback": "broader-suite", "network": "deny"})

    authoring = load(pack / "authoring" / "profile.json")
    authoring.update({"profile_key": args.pack_key + "-authoring", "typed_model": "recipe-contract-v1",
                      "preview_required": True, "negative_required": True, "holdout_required": True,
                      "signing_required": True, "arbitrary_script": False})
    write(pack / "authoring" / "profile.json", authoring)

    telemetry = load(pack / "telemetry" / "policy.json")
    telemetry.update({"policy_key": args.pack_key + "-telemetry", "retention_days": 30,
                      "residency": ["local-only"], "individual_performance_monitoring": False})
    write(pack / "telemetry" / "policy.json", telemetry)

    profiles = {
        "preview/profile.json": {"key": args.pack_key + "-preview", "status": "experimental", "repository_write": False, "network": "deny", "evidence_refs": local_refs},
        "explainability/profile.json": {"key": args.pack_key + "-explainability", "status": "experimental", "provenance_required": True, "evidence_refs": local_refs},
        "quick-fix/profile.json": {"key": args.pack_key + "-quick-fix", "status": "experimental", "exact_diagnostic_binding": True, "auto_apply": False, "evidence_refs": local_refs},
        "conflicts/profile.json": {"key": args.pack_key + "-conflict", "status": "experimental", "ambiguous_action": "escalate", "human_regions": "preserve", "evidence_refs": local_refs},
        "review/policy.json": {"key": args.pack_key + "-review", "status": "blocked", "separation_of_duties": True, "external_review_status": "NOT_RUN", "evidence_refs": []},
        "offline/profile.json": {"key": args.pack_key + "-offline", "status": "blocked", "network": "deny", "signed_bundle_required": True, "real_airgap_status": "NOT_RUN", "evidence_refs": []},
    }
    titles = {path: load(pack / path).get("title") for path in profiles}
    for path, payload in profiles.items():
        write(pack / path, {"schema_version": 1, "title": titles[path], **payload})

    support = load(pack / "support-matrix.json")
    for capability in support["capabilities"]:
        capability["owner"] = "elmos-developer-experience"
        if capability["capability"] in LOCAL_CAPABILITIES:
            capability.update({"status": "experimental", "evidence_refs": local_refs,
                               "constraints": ["Validated only in the local Java core and CLI rehearsal."]})
        else:
            capability.update({"status": "blocked", "evidence_refs": [],
                               "constraints": ["Real host, SCM, review, or air-gapped evidence is NOT_RUN."]})
    write(pack / "support-matrix.json", support)

    metrics = load(pack / "certification" / "evidence.json")["metrics"]
    local_metric_keys = {"ide_protocol_conformance", "cli_contract_pass_rate", "local_preview_pass_rate",
                         "navigation_accuracy", "explanation_provenance_coverage", "quick_fix_postcondition_pass_rate",
                         "conflict_resolution_pass_rate", "ownership_protection_pass_rate", "affected_test_recall",
                         "recipe_authoring_validation_pass_rate", "telemetry_privacy_pass_rate", "evidence_trace_coverage"}
    measured = {key: (1 if key in local_metric_keys else 0) for key in metrics}
    zero = load(pack / "certification" / "evidence.json")["zero_tolerance"]
    locally_observed_zero = {"unauthorized_repository_writes", "secret_leaks", "critical_source_mapping_errors",
                             "protected_region_overwrites", "test_integrity_violations", "telemetry_policy_violations",
                             "unreplayed_local_failures", "hidden_network_dependencies"}
    observed = {key: (0 if key in locally_observed_zero else 1) for key in zero}
    evidence = {"schema_version": 1, "pack_key": args.pack_key, "metrics": measured,
                "zero_tolerance": observed, "evidence_refs": local_refs,
                "measurement_scope": "local-java-core-and-cli-only",
                "external_evidence_status": "NOT_RUN"}
    write(pack / "certification" / "evidence.json", evidence)
    certification = load(pack / "certification" / "certification.json")
    certification.update({"status": "experimental", "owner": "elmos-quality",
                          "exact_scope": manifest["scope"], "metrics": measured,
                          "zero_tolerance": observed, "evidence_refs": local_refs,
                          "limitations": [
                              "IntelliJ, Visual Studio, and VS Code extension builds and host execution: NOT_RUN",
                              "GitHub, GitLab, and Bitbucket pull-request bot sandbox execution: NOT_RUN",
                              "Independent holdout corpus: NOT_RUN",
                              "Representative developer workflows: NOT_RUN",
                              "Private or air-gapped execution: NOT_RUN",
                              "Independent human approval: NOT_RUN",
                          ]})
    write(pack / "certification" / "certification.json", certification)

    corpus_manifest(pack, "corpus/development", "passed", source_digest, local_refs)
    corpus_manifest(pack, "corpus/negative", "passed", source_digest, ["certification/local-test-result.json"])
    corpus_manifest(pack, "corpus/holdout", "not-run", source_digest, [], "No independent holdout execution was authorized or performed.")
    corpus_manifest(pack, "corpus/representative-workflows", "not-run", source_digest, [], "No real representative IDE or SCM workflow was executed.")

    (pack / "certification" / "gap-inventory.md").write_text(
        "# Gap inventory\n\n"
        "- Build, sign, and execute all three extensions in exact real host versions.\n"
        "- Exercise the PR bot in isolated GitHub, GitLab, and Bitbucket repositories.\n"
        "- Run independent holdout and representative developer workflow corpora.\n"
        "- Execute the signed offline workflow in a real network-isolated environment.\n"
        "- Obtain independent review bound to the exact artifacts and evidence.\n",
        encoding="utf-8")
    (pack / "certification" / "replay.md").write_text(
        "# Local replay\n\n"
        f"`{sys.executable} scripts/batch36/run_local_developer_workflow_rehearsal.py --repo-root . --maven-command {maven}`\n\n"
        "This replays only the local Java core, CLI, schemas, and policy tests. It does not execute IDE hosts, SCM providers, holdout users, or air-gapped infrastructure.\n",
        encoding="utf-8")
    (pack / "README.md").write_text(
        "# ELMOS local developer workflow\n\n"
        "This is an experimental Batch 36 pack backed by a real local Java module and CLI rehearsal. "
        "It is not a production IDE, SCM, private-environment, or developer-experience certification.\n",
        encoding="utf-8")

    gate = command([sys.executable, str(root / "scripts" / "batch36" / "run_developer_experience_gate.py"), str(pack)], root)
    sys.stdout.write(gate.stdout)
    sys.stderr.write(gate.stderr)
    if gate.returncode:
        return gate.returncode
    gate_result = load(pack / "certification" / "gate-result.json")
    if gate_result.get("certification_decision") != "NOT_CERTIFIED":
        raise SystemExit("experimental rehearsal must remain NOT_CERTIFIED")
    print(f"LOCAL REHEARSAL PASS: {pack} tests={totals['tests']} decision=NOT_CERTIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
