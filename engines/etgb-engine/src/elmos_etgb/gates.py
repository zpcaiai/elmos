"""Fail-closed release gate evaluation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .corpus import verify_lock


def _threshold(value: float | int | None, operator: str, threshold: float | int) -> bool:
    if value is None:
        return False
    if operator == "==":
        return value == threshold
    if operator == ">=":
        return value >= threshold
    if operator == "<=":
        return value <= threshold
    raise ValueError(f"unsupported gate operator: {operator}")


def evaluate_gate(*, score: dict[str, Any], validation: dict[str, Any], coverage: dict[str, Any], profile: str, external_attested: bool = False, independent_verifier: str | None = None) -> dict[str, Any]:
    metrics = score.get("metrics", {})
    by_priority = score.get("by_priority", {})
    p1_applicable = float(by_priority.get("P1", {}).get("total_weight", 0.0)) > 0
    p2_applicable = float(by_priority.get("P2", {}).get("total_weight", 0.0)) > 0
    checks = [
        {"id": "G-P0-PASS", "passed": _threshold(metrics.get("p0_critical_oracle_pass_rate", metrics.get("critical_oracle_pass_rate")), "==", 1.0), "value": metrics.get("p0_critical_oracle_pass_rate", metrics.get("critical_oracle_pass_rate")), "threshold": 1.0},
        {"id": "G-P0-SSER", "passed": _threshold(metrics.get("p0_silent_semantic_error_rate", metrics.get("silent_semantic_error_rate")), "==", 0.0), "value": metrics.get("p0_silent_semantic_error_rate", metrics.get("silent_semantic_error_rate")), "threshold": 0.0},
        {"id": "G-DATA", "passed": _threshold(metrics.get("data_corruption_count"), "==", 0), "value": metrics.get("data_corruption_count"), "threshold": 0},
        {"id": "G-SEC", "passed": _threshold(metrics.get("security_regression_count"), "==", 0), "value": metrics.get("security_regression_count"), "threshold": 0},
        {"id": "G-TX", "passed": _threshold(metrics.get("p0_transaction_mismatch_count", metrics.get("transaction_mismatch_count")), "==", 0), "value": metrics.get("p0_transaction_mismatch_count", metrics.get("transaction_mismatch_count")), "threshold": 0},
        {"id": "G-FLAKE", "passed": _threshold(metrics.get("p0_flaky_case_count", metrics.get("flaky_case_count")), "==", 0), "value": metrics.get("p0_flaky_case_count", metrics.get("flaky_case_count")), "threshold": 0},
        {"id": "G-P1", "passed": not p1_applicable or _threshold(by_priority.get("P1", {}).get("weighted_pass_rate"), ">=", 0.985), "value": by_priority.get("P1", {}).get("weighted_pass_rate"), "threshold": 0.985, "applicable": p1_applicable},
        {"id": "G-P2", "passed": not p2_applicable or _threshold(by_priority.get("P2", {}).get("weighted_pass_rate"), ">=", 0.95), "value": by_priority.get("P2", {}).get("weighted_pass_rate"), "threshold": 0.95, "applicable": p2_applicable},
        {"id": "G-EVIDENCE", "passed": _threshold(metrics.get("evidence_completeness"), "==", 1.0), "value": metrics.get("evidence_completeness"), "threshold": 1.0},
    ]
    if profile in {"release", "golden"}:
        checks.append({"id": "G-CORPUS", "passed": _threshold(metrics.get("unapproved_corpus_count"), "==", 0), "value": metrics.get("unapproved_corpus_count"), "threshold": 0})
    blockers: list[str] = []
    if not validation.get("valid"):
        blockers.append("package validation is not valid")
    if not coverage.get("complete"):
        blockers.append("declared capability coverage is incomplete")
    if not score.get("complete_run"):
        blockers.append("run is incomplete or contains unavailable/skipped cases")
    failed_checks = [item["id"] for item in checks if not item["passed"]]
    if failed_checks:
        blockers.extend(f"failed gate: {gate_id}" for gate_id in failed_checks)
    if profile in {"release", "golden"} and not external_attested:
        blockers.append("independent external attestation is required for release/golden promotion")
    if profile in {"release", "golden"} and not independent_verifier:
        blockers.append("independent verifier identity is required")
    if any(gate_id in {"G-P0-PASS", "G-P0-SSER", "G-DATA", "G-SEC", "G-TX"} for gate_id in failed_checks):
        decision = "REJECT"
    elif blockers:
        decision = "BLOCKED"
    else:
        decision = "PROMOTE" if external_attested and independent_verifier else "READY_FOR_EXTERNAL_GATE"
    return {"schema_version": "1.0", "profile": profile, "decision": decision, "certification_status": "NOT_CERTIFIED" if decision != "PROMOTE" else "EXTERNAL_ATTESTED_NOT_A_PRODUCTION_RELEASE", "checks": checks, "blockers": blockers, "external_attested": external_attested, "independent_verifier": independent_verifier}
