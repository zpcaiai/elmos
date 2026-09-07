#!/usr/bin/env python3
"""Generate the deterministic Batch 81-95 Language Pack qualification suite."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "elmos-language-packs-batch81-95-complete"
INSTALL_MANIFEST = ROOT / "docs" / "language-packs-batch81-95" / "installed-manifest.json"
DEFAULT_OUTPUT = ROOT / "test-suites" / "batch81-95-language-packs-slightly-strict"
SUITE_ID = "batch81-95-language-packs-slightly-strict-supplemental"

CATEGORIES = [
    ("happy_path", "HIGH", "Execute the declared successful language-pack journey with the exact native or approved-equivalent toolchain."),
    ("boundary", "MEDIUM", "Exercise minimum, maximum, encoding, numeric, timing, resource, and platform boundary inputs."),
    ("negative_input", "HIGH", "Reject malformed, ambiguous, injected, traversing, unsupported, or unsafe source constructs before mutation."),
    ("dependency_failure", "HIGH", "Inject a controlled vendor tool, compiler, simulator, runtime, database, device, platform, or provider failure."),
    ("security_isolation", "CRITICAL", "Prove tenant, secret, permission, macro/plugin, physical-system, production, and external-effect boundaries fail closed."),
    ("replay_idempotency", "HIGH", "Repeat the approved run and prove deterministic output, safe restart, and preservation of user-owned artifacts."),
    ("version_drift", "HIGH", "Change a dialect, vendor platform, compiler, simulator, runtime, dependency, binary, or target version and re-evaluate compatibility."),
    ("evidence_tamper", "CRITICAL", "Alter the namespace binding, case, source, artifact, environment, approval, or evidence digest and require rejection."),
]

BASE_EVIDENCE = [
    "case-definition",
    "source-namespace-binding",
    "target-profile",
    "environment-manifest",
    "native-command-log",
    "artifact-manifest",
    "oracle-result",
    "cleanup-report",
]


def dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def canonical_digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, content: str) -> None:
    if path.exists():
        raise SystemExit(f"Refusing to overwrite existing suite file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_skill_markdown(manifest: dict[str, Any]) -> str:
    batch = manifest["batch"]
    categories = ", ".join(category for category, _, _ in CATEGORIES)
    return f"""# TST-B{batch} — {manifest['title']} Supplemental Qualification

## 1. Objective

Qualify all 12 exact Batch {batch} Language Pack Skills with executable, evidence-bound engineering tests. This supplemental design cannot certify a vendor platform, physical system, production change, or migration outcome.

## 2. Target Scope

Target Batch {batch}, family `{manifest['family']}`, source namespace `package-local-language-pack`, while preserving original PG IDs and deterministic installed aliases.

## 3. Strictness Profile

Run exactly eight variants: {categories}. Every `PASSED` result requires two deterministic executions, explicit authorization, immutable evidence, and an independent verifier.

## 4. Inputs

Use the exact source/installed manifest digests, approved requirement or modernization scope, dialect/platform profile, compatibility baseline, clean environment, safety policy, and authorization references.

## 5. Required Fixtures

Provide isolated disposable fixtures for the declared native/vendor toolchain, runtime, simulator, database, device, tenant, platform, or approved equivalent. Missing protected infrastructure remains `NOT_RUN`.

## 6. Preconditions

Pin dialects, versions, encodings, numeric/timing modes, dependencies, source commits, ownership, and safety boundaries. Treat source, macros, plugins, binaries, models, metadata, and project configuration as untrusted.

## 7. Test Cases

Preserve `TC-B{batch}-001` through `TC-B{batch}-008`. Do not replace semantic, numerical, transaction, timing, failure, security, or physical-system tests with file-presence smoke checks.

## 8. Deterministic Oracles

Compare typed semantics, native tool exits, artifacts, runtime/simulation behavior, negative denials, cleanup, and evidence hashes across two isolated runs and an independent replay.

## 9. Execution Procedure

Create a clean workspace, record exact environment/tool versions, execute the approved workflow and applicable native tools, retain raw output, replay independently, and clean every fixture.

## 10. Failure Injection

Inject bounded malformed input, unsupported constructs, dependency/runtime failures, version drift, restart/cancellation, and evidence tampering without production or physical-system writes.

## 11. Security and Tenant Isolation

Verify least privilege, secret references, injection/path defenses, tenant/workspace separation, macro/plugin isolation, policy denial, and absence of unauthorized external effects.

## 12. Replay and Idempotency

Run at least twice from identical approved inputs. Outputs must be deterministic or explicitly immutable/versioned; retries and restart cannot duplicate effects or overwrite user-owned content.

## 13. Evidence Contract

Bind the case, namespace, source and installed Skills, target profile, environment, commands, artifacts, oracle, cleanup, executor, independent verifier, authorization, timestamps, and evidence roles by SHA-256.

## 14. Anti-Fraud Rules

Reject fabricated logs, source-ID relabeling, synthetic runtime claims, self-verification, stale digests, omitted failures, weakened tolerances/assertions, missing cases, and static checks presented as vendor execution.

## 15. Reporting

Report `NOT_RUN`, `PASSED`, `FAILED`, `BLOCKED`, or `QUARANTINED` per exact case. Preserve limitations and the highest genuinely evidenced state.

## 16. Acceptance Criteria

All exact cases/results exist; critical cases pass 100%, high cases at least 98%, and overall at least 95%; no required case is missing, stale, self-verified, blocked, failed, quarantined, or `NOT_RUN`.

## 17. Release Impact

At most emit `READY_FOR_EXTERNAL_GATE`. Never update Batch 1–37 certification or approve vendor deployment, physical actuation, safety, financial, clinical, scientific, production, or cutover outcomes.

## 18. Definition of Done

Cases are complete, replayed, independently verified, authorization- and digest-bound, and the gate truthfully records residual limitations. Otherwise the suite remains blocked.

Batch safety boundary: **{manifest['safety_boundary']}**
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output.resolve()
    if output == DEFAULT_OUTPUT.resolve():
        raise SystemExit(
            "The legacy 120-case generator is retired for the canonical suite; "
            "use tooling/import_batch81_95_strict_test_assets.py instead"
        )
    if output.exists():
        raise SystemExit(f"Refusing to overwrite existing suite directory: {output}")

    package_manifest = json.loads((SOURCE / "package-manifest.json").read_text(encoding="utf-8"))
    install_manifest = json.loads(INSTALL_MANIFEST.read_text(encoding="utf-8"))
    if package_manifest.get("skills") != 180 or install_manifest.get("skill_count") != 180:
        raise SystemExit("Batch 81-95 Language Pack source or install manifest is invalid")
    installed_by_key = {entry["source_key"]: entry for entry in install_manifest["skills"]}

    batch_manifests: list[dict[str, Any]] = []
    case_catalog: dict[str, Any] = {
        "schema_version": "1.0",
        "suite_id": SUITE_ID,
        "case_count": 120,
        "cases": [],
    }
    results: list[dict[str, Any]] = []
    batch_case_ids: dict[int, list[str]] = {}
    all_source_skills: list[dict[str, Any]] = []

    for batch in range(81, 96):
        manifest = json.loads((SOURCE / f"batch-{batch}-manifest.json").read_text(encoding="utf-8"))
        batch_manifests.append(manifest)
        target_skills = []
        for skill in manifest["skills"]:
            source_key = f"LP-B{batch}-{skill['id']}"
            installed = installed_by_key[source_key]
            target = {
                "source_key": source_key,
                "source_id": skill["id"],
                "source_name": skill["name"],
                "installed_name": installed["installed_name"],
            }
            target_skills.append(target)
            all_source_skills.append({**target, "batch": batch})
        case_ids: list[str] = []
        for index, (category, severity, stimulus) in enumerate(CATEGORIES, 1):
            case_id = f"TC-B{batch}-{index:03d}"
            case_ids.append(case_id)
            evidence = list(BASE_EVIDENCE)
            if category == "security_isolation":
                evidence.append("security-safety-policy-result")
            if category == "evidence_tamper":
                evidence.append("evidence-integrity-result")
            case = {
                "case_id": case_id,
                "test_skill_id": f"TST-B{batch}",
                "batch": batch,
                "target_skills": target_skills,
                "category": category,
                "severity": severity,
                "title": f"Batch {batch} {category.replace('_', ' ')} qualification",
                "setup": "Use a clean disposable workspace and exact approved dialect/platform profile with pinned native tools, dependencies, policies, ownership, and content digests.",
                "stimulus": stimulus,
                "expected": "Declared native semantics are observed, unsafe or unsupported behavior fails closed, the Batch safety boundary and user ownership are preserved, and claims do not exceed evidence.",
                "deterministic_oracle": "Compare normalized semantic outputs, native command exits, artifacts, runtime/simulation probes, denials, cleanup, and evidence hashes across two isolated runs and independent replay.",
                "required_evidence": evidence,
                "disallowed_shortcuts": [
                    "fabricate_evidence",
                    "relabel_source_id",
                    "self_verification",
                    "static_as_native_runtime",
                    "weaken_gate_or_tolerance",
                    "omit_failure",
                ],
            }
            case_catalog["cases"].append(case)
            results.append(
                {
                    "case_id": case_id,
                    "test_skill_id": f"TST-B{batch}",
                    "batch": batch,
                    "severity": severity,
                    "source_case_digest": canonical_digest(case),
                    "status": "NOT_RUN",
                    "reason": "Required native or approved-equivalent execution and independent verification have not occurred.",
                    "artifact_digest": None,
                    "environment_digest": None,
                    "target_manifest_digest": None,
                    "started_at": None,
                    "finished_at": None,
                    "execution_kind": None,
                    "replay_command": None,
                    "deterministic_repeat_runs": 0,
                    "evidence_complete": False,
                    "flaky": None,
                    "executor": None,
                    "verifier": None,
                    "authorization_refs": [],
                    "evidence": [],
                    "anti_fraud_signals": [],
                }
            )
        batch_case_ids[batch] = case_ids

    coverage_rows = [
        {
            **skill,
            "case_ids": batch_case_ids[skill["batch"]],
        }
        for skill in all_source_skills
    ]
    suite = {
        "schema_version": "1.0",
        "suite_id": SUITE_ID,
        "authority": "supplemental-design-and-local-engineering-only",
        "source_package": "elmos-language-packs-batch81-95-complete",
        "source_id_namespace": "package-local-language-pack",
        "source_id_range": ["PG223", "PG402"],
        "global_pg_collision_preserved": True,
        "install_manifest": "docs/language-packs-batch81-95/installed-manifest.json",
        "control_manifest": "control-manifest.json",
        "strictness_profile": "strictness-profile.json",
        "test_skill_root": "test-skills",
        "case_catalog": "cases/catalog.json",
        "coverage_matrix": "coverage-matrix.json",
        "result_catalog": "results/catalog.json",
        "batches": list(range(81, 96)),
        "test_skill_count": 15,
        "source_skill_count": 180,
        "case_count": 120,
        "direct_coverage_edges": 1440,
        "maximum_success_decision": "READY_FOR_EXTERNAL_GATE",
        "certification_authority": False,
        "replaces_batch1_37_strict_suite": False,
    }
    profile = {
        "schema_version": "1.0",
        "profile_id": "elmos-batch81-95-language-packs-slightly-strict-v1",
        "required_variants": [category for category, _, _ in CATEGORIES],
        "thresholds": {
            "overall_pass_rate": 0.95,
            "critical_pass_rate": 1.0,
            "high_pass_rate": 0.98,
        },
        "minimum_deterministic_repeat_runs": 2,
        "independent_verifier_required": True,
        "missing_or_not_run_fails_closed": True,
        "maximum_success_decision": "READY_FOR_EXTERNAL_GATE",
    }
    coverage = {
        "schema_version": "1.0",
        "suite_id": SUITE_ID,
        "source_skill_count": 180,
        "case_count": 120,
        "direct_edge_count": 1440,
        "rows": coverage_rows,
    }
    result_catalog = {
        "schema_version": "1.0",
        "suite_id": SUITE_ID,
        "case_catalog_digest": canonical_digest(case_catalog),
        "source_package_manifest_digest": file_digest(SOURCE / "package-manifest.json"),
        "target_manifest_digest": file_digest(INSTALL_MANIFEST),
        "result_count": 120,
        "results": results,
    }

    write_new(output / "suite.json", dump_json(suite))
    write_new(output / "strictness-profile.json", dump_json(profile))
    write_new(output / "cases" / "catalog.json", dump_json(case_catalog))
    write_new(output / "coverage-matrix.json", dump_json(coverage))
    write_new(output / "results" / "catalog.json", dump_json(result_catalog))
    for manifest in batch_manifests:
        write_new(output / "test-skills" / f"TST-B{manifest['batch']}.md", test_skill_markdown(manifest))

    controlled_paths = [
        "suite.json",
        "strictness-profile.json",
        "cases/catalog.json",
        "coverage-matrix.json",
        "results/catalog.json",
        *[f"test-skills/TST-B{batch}.md" for batch in range(81, 96)],
    ]
    controls = {
        "manifest_version": 1,
        "suite_id": SUITE_ID,
        "source_package": {
            "name": SOURCE.name,
            "package_manifest_sha256": file_digest(SOURCE / "package-manifest.json"),
            "sha256s_sha256": file_digest(SOURCE / "SHA256SUMS.txt"),
            "skill_count": 180,
            "source_id_namespace": "package-local-language-pack",
            "source_id_range": ["PG223", "PG402"],
        },
        "install_manifest_sha256": file_digest(INSTALL_MANIFEST),
        "controlled_files": {relative: file_digest(output / relative) for relative in controlled_paths},
    }
    write_new(output / "control-manifest.json", dump_json(controls))
    print(
        dump_json(
            {
                "suite": SUITE_ID,
                "test_skills": 15,
                "source_skills": 180,
                "cases": 120,
                "direct_coverage_edges": 1440,
                "results": {"NOT_RUN": 120},
            }
        ).strip()
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
