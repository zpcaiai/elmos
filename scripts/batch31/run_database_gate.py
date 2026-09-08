#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from pack_contract import load_json
from validate_database_pack import validate_pack

METRIC_THRESHOLDS = {
    "workload_fingerprint_coverage": 0.95,
    "canonical_ir_coverage": 0.95,
    "schema_conversion_pass_rate": 1.0,
    "type_boundary_pass_rate": 1.0,
    "query_semantic_pass_rate": 1.0,
    "transaction_contract_pass_rate": 1.0,
    "data_reconciliation_pass_rate": 1.0,
    "target_provision_pass_rate": 1.0,
    "representative_workload_pass_rate": 1.0,
    "source_map_coverage": 0.95,
    "query_performance_slo_pass_rate": 1.0,
}
ZERO_FIELDS = (
    "critical_unknowns",
    "silent_database_drops",
    "critical_precision_loss",
    "critical_collation_regressions",
    "critical_transaction_regressions",
    "critical_data_differences",
    "critical_security_regressions",
    "destructive_unapproved_changes",
    "test_integrity_violations",
)
LOCAL_CORE = (
    "source_execution",
    "target_execution",
    "holdout",
    "representative_workload",
    "rollback",
    "security",
)
PASS_STATUSES = {"PASSED_LOCAL", "PASSED_EXTERNAL", "PASSED_INDEPENDENT"}
EXTERNAL_STATUSES = {"PASSED_EXTERNAL", "PASSED_INDEPENDENT"}
STATUS_RANK = {
    "blocked": -1,
    "research": 0,
    "experimental": 1,
    "limited": 2,
    "certified": 3,
}


def _has_files(path: Path) -> bool:
    return any(
        candidate.is_file()
        and not candidate.is_symlink()
        and candidate.name.lower() not in {"readme.md", ".gitkeep"}
        and candidate.stat().st_size > 0
        for candidate in path.rglob("*")
    )


def _tree_digest(path: Path) -> str:
    digest = hashlib.sha256()
    for candidate in sorted(
        item for item in path.rglob("*") if item.is_file() and not item.is_symlink()
    ):
        digest.update(candidate.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(candidate.read_bytes())
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def _production_evidence_failures(pack: Path, evidence: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    metrics = evidence.get("metrics", {})
    for field, threshold in METRIC_THRESHOLDS.items():
        value = metrics.get(field)
        if not isinstance(value, (int, float)) or value < threshold:
            failures.append(f"{field} below {threshold}")
    for field in ZERO_FIELDS:
        if evidence.get(field) != 0:
            failures.append(f"{field} must be zero")
    for corpus_name in ("holdout", "representative-workloads"):
        if not _has_files(pack / "corpus" / corpus_name):
            failures.append(f"{corpus_name} corpus empty")
    if (
        _has_files(pack / "corpus" / "holdout")
        and _has_files(pack / "corpus" / "representative-workloads")
        and _tree_digest(pack / "corpus" / "holdout")
        == _tree_digest(pack / "corpus" / "representative-workloads")
    ):
        failures.append("holdout and representative workload corpora are identical")
    return failures


def _roles_are_independent(evidence: dict[str, Any]) -> bool:
    roles = evidence.get("evidence_roles")
    if not isinstance(roles, dict):
        return False
    values = [
        roles.get("executor"),
        roles.get("independent_verifier"),
        roles.get("certification_authority"),
    ]
    return (
        all(isinstance(value, str) and value.strip() for value in values)
        and len(set(values)) == 3
    )


def _derive_status(
    pack: Path,
    manifest: dict[str, Any],
    support: dict[str, Any],
    evidence: dict[str, Any],
    certification: dict[str, Any],
) -> tuple[str, list[str]]:
    blockers = _production_evidence_failures(pack, evidence)
    states = evidence.get("evidence_status", {})
    if not isinstance(states, dict):
        return "research", blockers + ["evidence_status missing"]
    if any(states.get(field) in {"FAILED", "BLOCKED"} for field in LOCAL_CORE):
        return "blocked", blockers + ["critical local evidence failed or blocked"]

    references = evidence.get("evidence_refs", [])
    has_local_evidence = bool(references) and all(
        states.get(field) in PASS_STATUSES for field in LOCAL_CORE
    )
    derived = "experimental" if has_local_evidence else "research"

    external_core = all(states.get(field) in EXTERNAL_STATUSES for field in LOCAL_CORE)
    independently_verified = (
        states.get("independent_verification") == "PASSED_INDEPENDENT"
    )
    restrictions = certification.get("restrictions")
    if (
        not blockers
        and external_core
        and independently_verified
        and _roles_are_independent(evidence)
    ):
        if isinstance(restrictions, list) and restrictions:
            derived = "limited"

        migration_mode = manifest.get("mode") == "migration"
        lifecycle_ok = states.get("rollback") in EXTERNAL_STATUSES
        if migration_mode:
            lifecycle_ok = (
                lifecycle_ok
                and states.get("cdc") in EXTERNAL_STATUSES
                and states.get("cutover") in EXTERNAL_STATUSES
            )
        else:
            lifecycle_ok = lifecycle_ok and states.get("cdc") in EXTERNAL_STATUSES | {
                "NOT_APPLICABLE"
            }
            lifecycle_ok = lifecycle_ok and states.get(
                "cutover"
            ) in EXTERNAL_STATUSES | {"NOT_APPLICABLE"}
        capabilities = support.get("capabilities", [])
        no_noncertified_capabilities = bool(capabilities) and all(
            item.get("status") == "certified" for item in capabilities
        )
        approvals = certification.get("approved_by")
        certified = (
            lifecycle_ok
            and no_noncertified_capabilities
            and states.get("external_certification") == "PASSED_INDEPENDENT"
            and certification.get("external_certification") == "PASSED_INDEPENDENT"
            and isinstance(approvals, list)
            and len(
                {item for item in approvals if isinstance(item, str) and item.strip()}
            )
            >= 2
        )
        if certified:
            derived = "certified"
    return derived, blockers


def _write_result(pack: Path, result: dict[str, Any]) -> None:
    output = pack / "certification" / "gate-result.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pack_dir")
    parser.add_argument(
        "--require-release-ready",
        action="store_true",
        help="return non-zero unless independently evidenced limited/certified status is derived",
    )
    args = parser.parse_args()
    pack = Path(args.pack_dir).resolve()
    validation_failures = validate_pack(pack)

    try:
        manifest = load_json(pack / "pack.json")
        support = load_json(pack / "support-matrix.json")
        route = load_json(pack / "route-matrix.json")
        evidence = load_json(pack / "certification" / "evidence.json")
        certification = load_json(pack / "certification" / "certification.json")
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        validation_failures.append(str(exc))
        manifest, support, route, evidence, certification = {}, {}, {}, {}, {}

    ir_result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parent / "validate_canonical_ir.py"),
            str(pack / "canonical-ir" / "model.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if ir_result.returncode:
        validation_failures.append(
            f"canonical IR validation failed: {ir_result.stderr.strip() or ir_result.stdout.strip()}"
        )

    derived_status, blockers = _derive_status(
        pack, manifest, support, evidence, certification
    )
    claims = [manifest.get("status"), certification.get("status")]
    tuples = route.get("tuples")
    if isinstance(tuples, list) and len(tuples) == 1 and isinstance(tuples[0], dict):
        claims.append(tuples[0].get("status"))
    if len(set(claims)) != 1:
        validation_failures.append("pack, certification, and route statuses must match")
    claimed_status = manifest.get("status")
    claimed_rank = STATUS_RANK.get(str(claimed_status), 99)
    derived_rank = STATUS_RANK.get(derived_status, -1)
    if claimed_rank > derived_rank:
        validation_failures.append(
            f"claimed status {claimed_status} exceeds evidence-derived status {derived_status}"
        )

    release_eligible = (
        derived_status in {"limited", "certified"} and not validation_failures
    )
    result = {
        "schema_version": 2,
        "gate_version": "batch31-evidence-derived-v2",
        "pack_key": manifest.get("pack_key", pack.name),
        "status": "blocked" if validation_failures else derived_status,
        "claimed_status": claimed_status,
        "derived_status": derived_status,
        "release_eligible": release_eligible,
        "certification_decision": "CERTIFIED"
        if derived_status == "certified" and not validation_failures
        else "NOT_CERTIFIED",
        "failures": sorted(set(validation_failures)),
        "production_blockers": sorted(set(blockers)),
    }
    _write_result(pack, result)

    if validation_failures:
        print(
            "\n".join(
                f"GATE FAIL: {failure}" for failure in sorted(set(validation_failures))
            ),
            file=sys.stderr,
        )
        return 2
    if args.require_release_ready and not release_eligible:
        print(
            f"RELEASE BLOCKED: {pack.name} derived_status={derived_status}",
            file=sys.stderr,
        )
        return 3
    print(
        f"GATE RESULT: {pack.name} derived_status={derived_status} release_eligible={str(release_eligible).lower()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
