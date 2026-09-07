#!/usr/bin/env python3
"""Build and exercise the local Batch 35 runtime without claiming certification."""
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


PACK_KEY = "elmos-local-advanced-verification"
OWNER = "elmos-verification-engineering"


def tree_digest(path: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(p for p in path.rglob("*") if p.is_file() and "target" not in p.parts)
    for file_path in files:
        digest.update(file_path.relative_to(path).as_posix().encode())
        digest.update(b"\0")
        digest.update(file_path.read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def value_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def command_output(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, check=True)
    return (completed.stdout + completed.stderr).strip()


def java_environment(repo: Path) -> tuple[dict[str, str], dict[str, str]]:
    env = os.environ.copy()
    java_home = command_output(["/usr/libexec/java_home", "-v", "21"], repo).splitlines()[0]
    env["JAVA_HOME"] = java_home
    mvn = shutil.which("mvn") or "/opt/homebrew/bin/mvn"
    versions = {
        "java_home": java_home,
        "java_version": command_output([str(Path(java_home) / "bin/java"), "-version"], repo, env),
        "maven_version": command_output([mvn, "-version"], repo, env),
        "platform": sys.platform,
    }
    return env, {"maven_executable": mvn, **versions}


def run_tests(repo: Path, env: dict[str, str], mvn: str) -> dict[str, object]:
    command = [mvn, "-B", "-pl", "modules/advanced-verification", "-am", "test"]
    completed = subprocess.run(command, cwd=repo, env=env, text=True, capture_output=True)
    report_dir = repo / "modules/advanced-verification/target/surefire-reports"
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    suites: list[dict[str, object]] = []
    for report in sorted(report_dir.glob("TEST-*.xml")):
        root = ET.parse(report).getroot()
        item = {key: int(float(root.attrib.get(key, "0"))) for key in totals}
        item["name"] = root.attrib.get("name", report.stem)
        suites.append(item)
        for key in totals:
            totals[key] += int(item[key])
    passed = completed.returncode == 0 and totals["tests"] > 0 and totals["failures"] == 0 and totals["errors"] == 0
    result = {
        "schema_version": 1,
        "status": "passed" if passed else "failed",
        "command": " ".join(command),
        "exit_code": completed.returncode,
        "totals": totals,
        "suites": suites,
        "stdout_tail": completed.stdout.splitlines()[-20:],
        "stderr_tail": completed.stderr.splitlines()[-20:],
    }
    if not passed:
        raise RuntimeError(json.dumps(result, indent=2))
    return result


def corpus_manifest(status: str, source_digest: str, dataset: object, evidence_refs: list[str], limitations: list[str] | None = None) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": status,
        "source_digest": source_digest,
        "dataset_digest": value_digest(dataset),
        "evidence_refs": evidence_refs,
        "limitations": limitations or [],
    }


def populate_pack(repo: Path, pack: Path, source_digest: str, target_digest: str, environment_digest: str, test_result: dict[str, object]) -> None:
    scope = {
        "migration_route": "local-java-regression-rehearsal",
        "source_artifact_digest": source_digest,
        "target_artifact_digest": target_digest,
        "workload_key": "portfolio-scale-and-verification-core",
        "risk_tier": "P1",
        "environment_digest": environment_digest,
        "validation_kind": "local-module-runtime-rehearsal",
        "source_target_migration_equivalence": "NOT_RUN",
        "external_solver_or_symbolic_execution": "NOT_RUN",
        "independent_holdout": "NOT_RUN",
        "representative_production_workload": "NOT_RUN",
    }
    pack_manifest = load(pack / "pack.json")
    pack_manifest.update({"version": "0.1.0", "status": "experimental", "owner": OWNER, "maintenance_owner": OWNER})
    pack_manifest["scope"] = scope
    pack_manifest["tags"] = ["advanced-verification", "local-rehearsal", "not-certified"]
    write(pack / "pack.json", pack_manifest)

    local_evidence = "certification/local-test-result.json"
    write(pack / local_evidence, test_result)
    write(pack / "certification/local-source-manifest.json", {
        "schema_version": 1,
        "status": "captured",
        "source": "modules/portfolio-scale/src",
        "source_digest": source_digest,
        "target": "modules/advanced-verification/src",
        "target_digest": target_digest,
        "environment_digest": environment_digest,
    })

    claims = [
        {
            "claim_id": "claim.local-bounded-techniques",
            "description": "The local runtime returns explicit bounded outcomes for implemented verification techniques.",
            "criticality": "P1",
            "required_oracles": ["oracle.java-contract", "oracle.junit-regression"],
            "required_techniques": ["property", "metamorphic", "mutation", "structured-fuzz", "model", "bounded-proof"],
        },
        {
            "claim_id": "claim.local-fail-closed-governance",
            "description": "Unknown proof results, oracle conflicts, unsupported evidence, and residual P0 risk do not become pass decisions.",
            "criticality": "P1",
            "required_oracles": ["oracle.java-contract", "oracle.junit-regression"],
            "required_techniques": ["oracle-governance", "assurance-case", "counterexample-replay"],
        },
    ]
    write(pack / "validation-profile.json", {
        "schema_version": 1,
        "profile_key": f"{PACK_KEY}-profile-v1",
        "version": 1,
        "risk_tier": "P1",
        "claims": claims,
        "techniques": ["property", "metamorphic", "mutation", "structured-fuzz", "model", "bounded-finite-domain-proof", "concurrency", "numeric", "security", "query-equivalence", "oracle-governance", "counterexample-replay", "assurance-case"],
        "budgets": {"max_property_cases": 1000, "max_fuzz_cases": 1000, "max_schedules": 1000, "max_wall_time_minutes": 10},
        "stop_conditions": ["budget-exhausted", "unknown-p0-property", "oracle-conflict", "security-violation"],
        "approvals": [],
    })
    write(pack / "oracle-registry.json", {
        "schema_version": 1,
        "pack_key": PACK_KEY,
        "oracles": [
            {"oracle_id": "oracle.java-contract", "type": "contract", "owner": OWNER, "scope": [c["claim_id"] for c in claims], "independence": "partially-independent", "trust_level": "strong", "version": "1", "evidence_refs": ["certification/local-source-manifest.json"]},
            {"oracle_id": "oracle.junit-regression", "type": "test", "owner": OWNER, "scope": [c["claim_id"] for c in claims], "independence": "dependent", "trust_level": "supporting", "version": "1", "evidence_refs": [local_evidence]},
        ],
        "precedence_rules": [{"claim_type": "local-runtime", "ordered_oracles": ["oracle.java-contract", "oracle.junit-regression"]}],
        "conflicts": [],
        "approvals": [],
    })
    write(pack / "properties/sample.json", {
        "schema_version": 1,
        "property_id": "property.seeded-bounded-evaluation",
        "claim_id": "claim.local-bounded-techniques",
        "owner": OWNER,
        "generator": {"kind": "seeded-java-generator", "constraints": ["bounded-cases", "deterministic-seed"]},
        "oracle_refs": ["oracle.java-contract", "oracle.junit-regression"],
        "assertion": {"kind": "declared-property"},
        "shrinker": {"kind": "bounded-domain-shrinker"},
        "replay": {"seed": "42", "command": "mvn -pl modules/advanced-verification -am -Dtest=AdvancedVerificationTechniquesTest -Dsurefire.failIfNoSpecifiedTests=false test"},
    })
    write(pack / "metamorphic/sample.json", {
        "schema_version": 1,
        "relation_id": "relation.order-invariant-conservation",
        "claim_id": "claim.local-bounded-techniques",
        "owner": OWNER,
        "preconditions": ["finite-values"],
        "transformation": {"kind": "reverse-order"},
        "expected_relation": {"kind": "same-sum"},
        "oracle_refs": ["oracle.java-contract", "oracle.junit-regression"],
        "non_applicable": [],
    })
    write(pack / "mutation/campaign.json", {
        "schema_version": 1,
        "campaign_key": "mutation.seeded-negative-controls",
        "owner": OWNER,
        "target_scope": ["modules/advanced-verification/src/main/java"],
        "operators": [{"key": "negate-condition", "risk": "P1"}, {"key": "boundary-shift", "risk": "P1"}],
        "budgets": {"max_mutants": 10, "max_minutes": 2},
        "required_tests": ["AdvancedVerificationTechniquesTest", "VerificationGovernanceTest"],
        "equivalent_mutant_policy": "explicitly-classified-in-test-fixture",
    })
    write(pack / "fuzz/campaign.json", {
        "schema_version": 1,
        "campaign_key": "fuzz.structured-local",
        "owner": OWNER,
        "targets": ["StructuredFuzzEngine"],
        "seed_corpus": ["corpus/development/seed.json"],
        "coverage_signal": "declared-semantic-signal",
        "budgets": {"max_cases": 1000, "max_input_bytes": 4096},
        "sanitizers": [],
        "dictionary_refs": [],
    })
    write(pack / "corpus/development/seed.json", {"schema_version": 1, "seed": 42, "values": [0, 1, -1, 2147483647]})
    write(pack / "models/model.json", {
        "schema_version": 1,
        "model_key": "verification-run-lifecycle",
        "owner": OWNER,
        "states": ["created", "running", "passed", "failed", "unknown"],
        "initial_state": "created",
        "commands": [
            {"command": "start", "from": ["created"], "to": "running", "effects": ["bind-budget"]},
            {"command": "pass", "from": ["running"], "to": "passed", "effects": ["record-evidence"]},
            {"command": "fail", "from": ["running"], "to": "failed", "effects": ["record-counterexample"]},
            {"command": "exhaust", "from": ["running"], "to": "unknown", "effects": ["record-budget"]},
        ],
        "invariants": ["unknown-is-not-pass", "terminal-results-have-evidence"],
        "forbidden_transitions": [{"from": "unknown", "event": "pass-without-new-run"}],
        "timeouts": [],
    })
    write(pack / "solver/proof.json", {
        "schema_version": 1,
        "proof_id": "proof.external-smt-not-run",
        "property_id": "property.seeded-bounded-evaluation",
        "solver": {"name": "external-smt", "version": "NOT_CONFIGURED", "options": {}, "timeout_ms": 0},
        "status": "unsupported",
        "assumptions": ["Local unit tests exercise a finite bounded enumerator only; this is not a universal proof."],
        "input_digest": target_digest,
        "evidence_refs": [local_evidence],
    })

    negative_input = {"fixture": "critical-mutant-survivor", "expected": "blocked"}
    fingerprint = value_digest(negative_input)
    write(pack / "counterexamples/input.json", negative_input)
    write(pack / "counterexamples/sample.json", {
        "schema_version": 1,
        "counterexample_id": "ce.negative-control-critical-mutant",
        "technique": "mutation-negative-control",
        "claim_id": "claim.local-fail-closed-governance",
        "failure_fingerprint": fingerprint,
        "environment_digest": environment_digest,
        "artifact_digests": [target_digest],
        "input_ref": "counterexamples/input.json",
        "trace_ref": local_evidence,
        "replay": {"command": "mvn -pl modules/advanced-verification -am -Dtest=AdvancedVerificationTechniquesTest -Dsurefire.failIfNoSpecifiedTests=false test", "expected_fingerprint": fingerprint},
        "status": "reproduced",
        "owner": OWNER,
        "classification": "expected-negative-control",
    })

    capabilities = ["property-based-testing", "metamorphic-testing", "mutation-testing", "structured-fuzzing", "model-based-testing", "bounded-finite-domain-proof", "schedule-exploration", "numeric-verification", "security-properties", "data-money-invariants", "query-equivalence", "oracle-governance", "counterexample-replay", "assurance-case"]
    write(pack / "support-matrix.json", {
        "schema_version": 1,
        "pack_key": PACK_KEY,
        "capabilities": [
            {"key": key, "status": "experimental", "owner": OWNER, "evidence_refs": [local_evidence], "limitations": ["Validated only by deterministic local Java tests; no independent holdout or production workload."]}
            for key in capabilities
        ] + [{"key": "external-smt-symbolic-execution", "status": "blocked", "owner": OWNER, "evidence_refs": ["solver/proof.json"], "limitations": ["NOT_RUN: no external solver or symbolic executor is configured."]}],
    })

    development = {"kind": "local-deterministic-junit", "tests": test_result["totals"]["tests"]}
    negative = {"kind": "seeded-negative-controls", "counterexample": fingerprint}
    holdout = {"kind": "independent-holdout", "status": "NOT_RUN"}
    representative = {"kind": "representative-production-workload", "status": "NOT_RUN"}
    write(pack / "corpus/development/manifest.json", corpus_manifest("passed", source_digest, development, [local_evidence]))
    write(pack / "corpus/negative/manifest.json", corpus_manifest("passed", source_digest, negative, [local_evidence, "counterexamples/sample.json"]))
    write(pack / "corpus/holdout/manifest.json", corpus_manifest("not-run", source_digest, holdout, [], ["No independent holdout corpus was supplied."]))
    write(pack / "corpus/representative-workloads/manifest.json", corpus_manifest("not-run", source_digest, representative, [], ["No production-derived representative workload was supplied."]))

    write(pack / "assurance/assurance-case.json", {
        "schema_version": 1,
        "case_key": f"{PACK_KEY}-assurance-v1",
        "version": 1,
        "owner": OWNER,
        "top_claim": "The local Batch 35 runtime is executable and fail-closed within its declared experimental scope.",
        "claims": [
            {"claim_id": "claim.local-bounded-techniques", "statement": claims[0]["description"], "status": "partially-supported", "evidence_refs": [local_evidence], "assumptions": ["Local deterministic environment"], "limitations": ["No independent holdout or production workload"]},
            {"claim_id": "claim.local-fail-closed-governance", "statement": claims[1]["description"], "status": "partially-supported", "evidence_refs": [local_evidence, "counterexamples/sample.json"], "assumptions": [], "limitations": ["No independent reviewer approval"]},
        ],
        "evidence": [local_evidence, "certification/local-source-manifest.json", "counterexamples/sample.json"],
        "residual_risks": [
            {"risk": "External solver and symbolic execution are NOT_RUN", "owner": OWNER, "status": "open"},
            {"risk": "Independent holdout and representative production workloads are NOT_RUN", "owner": OWNER, "status": "open"},
            {"risk": "This pack does not evaluate a real source-to-target migration pair", "owner": OWNER, "status": "open"},
        ],
        "monitoring_obligations": ["Re-run on every change to modules/advanced-verification", "Reject any request to certify without independent corpora and approvals"],
        "approvals": [],
    })
    write(pack / "certification/evidence.json", {
        "schema_version": 1,
        "pack_key": PACK_KEY,
        "metrics": {"local_module_test_pass_rate": 1.0, "local_module_tests": test_result["totals"]["tests"]},
        "zero_tolerance": {},
        "evidence_refs": [local_evidence, "certification/local-source-manifest.json", "counterexamples/sample.json"],
        "notes": ["Local execution evidence only; certification thresholds were not evaluated."],
    })
    write(pack / "certification/certification.json", {
        "schema_version": 1,
        "pack_key": PACK_KEY,
        "status": "experimental",
        "owner": OWNER,
        "exact_scope": scope,
        "metrics": {"local_module_test_pass_rate": 1.0},
        "evidence_refs": [local_evidence, "certification/local-source-manifest.json"],
        "limitations": ["NOT_CERTIFIED", "Source-target migration equivalence NOT_RUN", "External SMT and symbolic execution NOT_RUN", "Independent holdout NOT_RUN", "Representative production workload NOT_RUN", "No independent approval"],
        "approved_at": None,
    })
    (pack / "certification/gap-inventory.md").write_text(
        "# Gap inventory\n\n"
        "- `NOT_RUN`: real source-to-target migration equivalence.\n"
        "- `NOT_RUN`: external SMT solver and symbolic execution.\n"
        "- `NOT_RUN`: independent holdout corpus.\n"
        "- `NOT_RUN`: representative production-derived workloads.\n"
        "- Missing: independent evidence review and named approval.\n",
        encoding="utf-8",
    )
    (pack / "README.md").write_text(
        f"# {PACK_KEY}\n\n"
        "Local executable Batch 35 rehearsal for ELMOS. The pack is `experimental` and `NOT_CERTIFIED`. "
        "Its test evidence covers only the local Java modules; all external evidence gaps remain explicit.\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()
    repo = Path(args.repo_root).resolve()
    source_path = repo / "modules/portfolio-scale/src"
    target_path = repo / "modules/advanced-verification/src"
    if not source_path.is_dir() or not target_path.is_dir():
        raise SystemExit("required local Java modules are missing")

    env, environment = java_environment(repo)
    source_digest = tree_digest(source_path)
    target_digest = tree_digest(target_path)
    environment_digest = value_digest(environment)
    test_result = run_tests(repo, env, str(environment["maven_executable"]))
    test_result["environment"] = environment
    test_result["environment_digest"] = environment_digest

    scaffold = Path(__file__).with_name("scaffold_verification_pack.py")
    subprocess.run([
        sys.executable, str(scaffold), "--pack-key", PACK_KEY,
        "--migration-route", "local-java-regression-rehearsal",
        "--workload-key", "portfolio-scale-and-verification-core",
        "--risk-tier", "P1", "--source-digest", source_digest,
        "--target-digest", target_digest, "--environment-digest", environment_digest,
        "--repo-root", str(repo), "--force",
    ], check=True)
    pack = repo / "verification-packs" / PACK_KEY
    populate_pack(repo, pack, source_digest, target_digest, environment_digest, test_result)

    gate = Path(__file__).with_name("run_verification_gate.py")
    subprocess.run([sys.executable, str(gate), str(pack)], cwd=repo, check=True)
    gate_result = load(pack / "certification/gate-result.json")
    if gate_result.get("certification_decision") != "NOT_CERTIFIED":
        raise RuntimeError("local rehearsal must remain NOT_CERTIFIED")
    print(json.dumps({
        "pack": str(pack),
        "tests": test_result["totals"],
        "structural_gate_status": gate_result["structural_gate_status"],
        "certification_decision": gate_result["certification_decision"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
