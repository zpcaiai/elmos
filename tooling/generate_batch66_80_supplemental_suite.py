#!/usr/bin/env python3
"""Generate the deterministic Batch 66-80 supplemental qualification suite."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "elmos-codex-skills-batch66-80-complete"
DEFAULT_OUTPUT = ROOT / "test-suites" / "batch66-80-slightly-strict"
SUITE_ID = "batch66-80-slightly-strict-supplemental"

CATEGORIES = [
    ("happy_path", "HIGH", "Execute the declared successful project journey with the exact real toolchain."),
    ("boundary", "MEDIUM", "Exercise minimum, maximum, empty, and platform boundary inputs without weakening contracts."),
    ("negative_input", "HIGH", "Reject malformed, ambiguous, injected, traversing, or unsupported input before mutation."),
    ("dependency_failure", "HIGH", "Inject a controlled compiler, registry, service, device, cluster, or provider failure and preserve diagnostics and cleanup."),
    ("security_isolation", "CRITICAL", "Prove default-deny secrets, permissions, network, tenant, workspace, signing, and external-effect boundaries."),
    ("replay_idempotency", "HIGH", "Repeat the approved run and prove deterministic output or an explicit immutable version without overwriting owned files."),
    ("version_drift", "HIGH", "Change a runtime, SDK, provider, schema, action, image, or lock version and require exact compatibility re-evaluation."),
    ("evidence_tamper", "CRITICAL", "Alter a case, artifact, log, environment, approval, or evidence digest and require fail-closed rejection."),
]

REQUIRED_EVIDENCE = [
    "case-definition",
    "target-profile",
    "environment-manifest",
    "command-log",
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


def test_skill_markdown(batch_manifest: dict[str, Any]) -> str:
    batch = batch_manifest["batch"]
    skill_names = [entry["name"] for entry in batch_manifest["skills"]]
    categories = ", ".join(category for category, _, _ in CATEGORIES)
    return f"""# TST-B{batch} — {batch_manifest['title']} Supplemental Qualification

## 1. Objective

Qualify the exact Batch {batch} source Skills with executable, evidence-bound engineering tests. This supplemental design cannot certify production readiness.

## 2. Target Scope

Target all {len(skill_names)} source Skills in Batch {batch}: `{', '.join(skill_names)}`.

## 3. Strictness Profile

Run exactly eight variants: {categories}. Every `PASSED` result requires two deterministic executions, an independent verifier, explicit authorization, and immutable raw evidence.

## 4. Inputs

Use the approved requirement, exact source Skill and case digests, target profile, compatibility baseline, clean environment manifest, toolchain policy, and authorization references.

## 5. Required Fixtures

Provide isolated disposable fixtures for the declared runtime, SDK, service, device, container, cluster, cloud, signing, or CI profile. Missing protected infrastructure stays `NOT_RUN`.

## 6. Preconditions

Pin versions and source commits; preserve dirty user work; inspect repository-provided executable configuration as untrusted input; deny undeclared network, secrets, permissions, and side effects.

## 7. Test Cases

The canonical case catalog contains `TC-B{batch}-001` through `TC-B{batch}-008`; no variant may be omitted or replaced by file-presence smoke checks.

## 8. Deterministic Oracles

Compare typed outputs, exit states, artifact hashes, runtime probes, negative denials, cleanup, and evidence bindings against the exact case oracle. A lower verification state never satisfies a higher one.

## 9. Execution Procedure

Create a clean workspace, record environment/tool versions, execute the source Skill workflow and real applicable tools, retain raw outputs, replay independently, and clean all fixtures.

## 10. Failure Injection

Inject bounded malformed inputs, dependency unavailability, timeouts, version drift, and evidence tampering without writing to production systems.

## 11. Security and Tenant Isolation

Verify least privilege, secret-reference handling, path and injection defenses, workspace/tenant separation, policy denials, and no unauthorized external effect.

## 12. Replay and Idempotency

Run at least twice from the same approved inputs. Outputs must be deterministic or explicitly immutable/versioned, and user-owned regions must remain unchanged.

## 13. Evidence Contract

Bind the case, source catalog, source Skill, target profile, environment, commands, artifacts, oracle, cleanup, executor, independent verifier, timestamps, authorization, and all required evidence roles by SHA-256.

## 14. Anti-Fraud Rules

Reject fabricated logs, synthetic runtime claims, self-verification, stale digests, omitted failures, weakened assertions, missing cases, and static checks presented as external execution.

## 15. Reporting

Report `NOT_RUN`, `PASSED`, `FAILED`, `BLOCKED`, or `QUARANTINED` per exact case. Preserve limitations and the highest genuinely evidenced state.

## 16. Acceptance Criteria

All exact cases and results exist; critical cases pass 100%, high cases at least 98%, and overall at least 95%; no required case is `NOT_RUN`, blocked, failed, quarantined, stale, or self-verified.

## 17. Release Impact

At most emit `READY_FOR_EXTERNAL_GATE`. Do not update Batch 1–37 strict certification or claim compiler, SDK, database, hardware, cluster, cloud, signing, CI, or production certification.

## 18. Definition of Done

Cases are complete, replayed, independently verified, authorization- and digest-bound, and fail-closed gate output truthfully records residual limitations. Otherwise the suite remains blocked.
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output.resolve()
    canonical_complete_suite = ROOT / "elmos-codex-skills-batch66-80-slightly-strict-tests"
    if output == DEFAULT_OUTPUT.resolve() and canonical_complete_suite.is_dir():
        raise SystemExit(
            "Refusing to replace the imported canonical 450-case Batch 66-80 suite "
            "with the superseded generated 120-case design"
        )
    if output.exists():
        raise SystemExit(f"Refusing to overwrite existing suite directory: {output}")

    source_manifest = json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8"))
    if source_manifest.get("skill_count") != 195 or source_manifest.get("id_range") != [
        "PG223",
        "PG417",
    ]:
        raise SystemExit("Batch 66-80 source package is missing or invalid")

    batch_manifests: list[dict[str, Any]] = []
    source_skills: list[dict[str, Any]] = []
    for batch in range(66, 81):
        manifest = json.loads(
            (SOURCE / "manifests" / f"batch-{batch}.json").read_text(encoding="utf-8")
        )
        batch_manifests.append(manifest)
        source_skills.extend(manifest["skills"])
    if len(source_skills) != 195:
        raise SystemExit("Expected exactly 195 source Skills")

    case_catalog: dict[str, Any] = {
        "schema_version": "1.0",
        "suite_id": SUITE_ID,
        "case_count": 120,
        "cases": [],
    }
    results: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []
    batch_case_ids: dict[int, list[str]] = {}

    for manifest in batch_manifests:
        batch = manifest["batch"]
        target_ids = [entry["id"] for entry in manifest["skills"]]
        case_ids: list[str] = []
        for index, (category, severity, stimulus) in enumerate(CATEGORIES, 1):
            case_id = f"TC-B{batch}-{index:03d}"
            case_ids.append(case_id)
            roles = list(REQUIRED_EVIDENCE)
            if category == "security_isolation":
                roles.append("security-policy-result")
            if category == "evidence_tamper":
                roles.append("evidence-integrity-result")
            case = {
                "case_id": case_id,
                "test_skill_id": f"TST-B{batch}",
                "batch": batch,
                "target_skill_ids": target_ids,
                "category": category,
                "severity": severity,
                "title": f"Batch {batch} {category.replace('_', ' ')} qualification",
                "setup": "Use a clean disposable workspace and an exact approved target profile with pinned tools, dependencies, policies, and content digests.",
                "stimulus": stimulus,
                "expected": "The exact declared behavior is observed, unsafe or unsupported behavior fails closed, user-owned content is preserved, and the final verification state does not exceed the evidence.",
                "deterministic_oracle": "Compare normalized outputs, command exits, artifacts, probes, denials, cleanup, and evidence hashes across two isolated runs and an independent replay.",
                "required_evidence": roles,
                "disallowed_shortcuts": [
                    "fabricate_evidence",
                    "self_verification",
                    "static_as_runtime",
                    "weaken_gate",
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
                    "reason": "Required real or approved-equivalent execution and independent verification have not occurred.",
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

    for skill in source_skills:
        coverage_rows.append(
            {
                "skill_id": skill["id"],
                "skill_name": skill["name"],
                "batch": skill["batch"],
                "case_ids": batch_case_ids[skill["batch"]],
            }
        )

    suite = {
        "schema_version": "1.0",
        "suite_id": SUITE_ID,
        "authority": "supplemental-design-and-local-engineering-only",
        "source_package": "elmos-codex-skills-batch66-80-complete",
        "source_manifest": "manifest.json",
        "control_manifest": "control-manifest.json",
        "strictness_profile": "strictness-profile.json",
        "test_skill_root": "test-skills",
        "case_catalog": "cases/catalog.json",
        "coverage_matrix": "coverage-matrix.json",
        "result_catalog": "results/catalog.json",
        "batches": list(range(66, 81)),
        "test_skill_count": 15,
        "source_skill_count": 195,
        "case_count": 120,
        "direct_coverage_edges": 1560,
        "maximum_success_decision": "READY_FOR_EXTERNAL_GATE",
        "certification_authority": False,
        "replaces_batch1_37_strict_suite": False,
    }
    profile = {
        "schema_version": "1.0",
        "profile_id": "elmos-batch66-80-slightly-strict-v1",
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
        "source_skill_count": 195,
        "case_count": 120,
        "direct_edge_count": 1560,
        "rows": coverage_rows,
    }
    result_catalog = {
        "schema_version": "1.0",
        "suite_id": SUITE_ID,
        "case_catalog_digest": canonical_digest(case_catalog),
        "target_manifest_digest": file_digest(SOURCE / "manifest.json"),
        "result_count": 120,
        "results": results,
    }

    write_new(output / "suite.json", dump_json(suite))
    write_new(output / "strictness-profile.json", dump_json(profile))
    write_new(output / "cases" / "catalog.json", dump_json(case_catalog))
    write_new(output / "coverage-matrix.json", dump_json(coverage))
    write_new(output / "results" / "catalog.json", dump_json(result_catalog))
    for manifest in batch_manifests:
        write_new(
            output / "test-skills" / f"TST-B{manifest['batch']}.md",
            test_skill_markdown(manifest),
        )

    controlled_paths = [
        "suite.json",
        "strictness-profile.json",
        "cases/catalog.json",
        "coverage-matrix.json",
        "results/catalog.json",
        *[f"test-skills/TST-B{batch}.md" for batch in range(66, 81)],
    ]
    controls = {
        "manifest_version": 1,
        "suite_id": SUITE_ID,
        "source_package": {
            "name": SOURCE.name,
            "manifest_sha256": file_digest(SOURCE / "manifest.json"),
            "skill_count": 195,
            "id_range": ["PG223", "PG417"],
        },
        "controlled_files": {
            relative: file_digest(output / relative) for relative in controlled_paths
        },
    }
    write_new(output / "control-manifest.json", dump_json(controls))
    print(
        dump_json(
            {
                "suite": SUITE_ID,
                "test_skills": 15,
                "source_skills": 195,
                "cases": 120,
                "direct_coverage_edges": 1560,
                "results": {"NOT_RUN": 120},
            }
        ).strip()
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
