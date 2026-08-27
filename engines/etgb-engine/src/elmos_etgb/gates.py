"""Fail-closed release gate evaluation."""

from __future__ import annotations

import datetime as dt
import json
import operator
from pathlib import Path
from typing import Any, Mapping

import yaml

from .corpus import verify_lock


OPERATORS = {"==": operator.eq, "!=": operator.ne, ">=": operator.ge, "<=": operator.le, ">": operator.gt, "<": operator.lt}
NON_WAIVABLE_GATES = {"G-P0-PASS", "G-P0-SSER", "G-DATA", "G-SEC", "G-TX", "G-AUTHORITY", "G-EVIDENCE-INTEGRITY"}


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


def evaluate_gate(*, score: dict[str, Any], validation: dict[str, Any], coverage: dict[str, Any], profile: str, external_attested: bool = False, independent_verifier: str | None = None, external_attestation: Mapping[str, Any] | None = None, attestation_verification: Mapping[str, Any] | None = None) -> dict[str, Any]:
    metrics = score.get("metrics", {})
    by_priority = score.get("by_priority", {})
    p1_applicable = float(by_priority.get("P1", {}).get("total_weight", 0.0)) > 0
    p2_applicable = float(by_priority.get("P2", {}).get("total_weight", 0.0)) > 0
    attestation_valid = bool(attestation_verification and attestation_verification.get("valid") is True)
    checks = [
        {"id": "G-P0-PASS", "passed": _threshold(metrics.get("p0_critical_oracle_pass_rate", metrics.get("critical_oracle_pass_rate")), "==", 1.0), "value": metrics.get("p0_critical_oracle_pass_rate", metrics.get("critical_oracle_pass_rate")), "threshold": 1.0},
        {"id": "G-P0-SSER", "passed": _threshold(metrics.get("p0_silent_semantic_error_rate", metrics.get("silent_semantic_error_rate")), "==", 0.0), "value": metrics.get("p0_silent_semantic_error_rate", metrics.get("silent_semantic_error_rate")), "threshold": 0.0},
        {"id": "G-DATA", "passed": _threshold(metrics.get("data_corruption_count"), "==", 0), "value": metrics.get("data_corruption_count"), "threshold": 0},
        {"id": "G-SEC", "passed": _threshold(metrics.get("security_regression_count"), "==", 0), "value": metrics.get("security_regression_count"), "threshold": 0},
        {"id": "G-TX", "passed": _threshold(metrics.get("p0_transaction_mismatch_count", metrics.get("transaction_mismatch_count")), "==", 0), "value": metrics.get("p0_transaction_mismatch_count", metrics.get("transaction_mismatch_count")), "threshold": 0},
        {"id": "G-AUTHORITY", "passed": _threshold(metrics.get("authority_violation_count"), "==", 0), "value": metrics.get("authority_violation_count"), "threshold": 0},
        {"id": "G-EVIDENCE-INTEGRITY", "passed": _threshold(metrics.get("evidence_integrity_failure_count"), "==", 0), "value": metrics.get("evidence_integrity_failure_count"), "threshold": 0},
        {"id": "G-INTEGRITY-DRIFT", "passed": profile not in {"release", "golden"} or _threshold(metrics.get("integrity_drift_count"), "==", 0), "value": metrics.get("integrity_drift_count"), "threshold": 0},
        {"id": "G-UNSUPPORTED", "passed": _threshold(metrics.get("unsupported_undisclosed_count"), "==", 0), "value": metrics.get("unsupported_undisclosed_count"), "threshold": 0},
        {"id": "G-RECOVERY", "passed": _threshold(metrics.get("recovery_failure_count"), "==", 0), "value": metrics.get("recovery_failure_count"), "threshold": 0},
        {"id": "G-BUDGET", "passed": profile not in {"release", "golden"} or _threshold(metrics.get("budget_overrun_count"), "==", 0), "value": metrics.get("budget_overrun_count"), "threshold": 0},
        {"id": "G-SUPPLY-CHAIN", "passed": profile not in {"release", "golden"} or _threshold(metrics.get("supply_chain_failure_count"), "==", 0), "value": metrics.get("supply_chain_failure_count"), "threshold": 0},
        {"id": "G-PERFORMANCE", "passed": profile not in {"release", "golden"} or _threshold(metrics.get("performance_regression_count"), "==", 0), "value": metrics.get("performance_regression_count"), "threshold": 0},
        {"id": "G-FLAKE", "passed": _threshold(metrics.get("p0_flaky_case_count", metrics.get("flaky_case_count")), "==", 0), "value": metrics.get("p0_flaky_case_count", metrics.get("flaky_case_count")), "threshold": 0},
        {"id": "G-SEEDS", "passed": _threshold(metrics.get("insufficient_seed_case_count"), "==", 0), "value": metrics.get("insufficient_seed_case_count"), "threshold": 0},
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
    if profile in {"release", "golden"} and not attestation_valid:
        blockers.append("verified independent external attestation bound to this gate input is required for release/golden promotion")
        if attestation_verification and attestation_verification.get("errors"):
            blockers.extend(f"attestation: {error}" for error in attestation_verification["errors"])
    if profile in {"release", "golden"} and not independent_verifier:
        blockers.append("independent verifier identity is required")
    if profile in {"release", "golden"} and not external_attestation and not any("candidate" in blocker for blocker in blockers):
        blockers.append("frozen candidate digest is required for release/golden evaluation")
    if profile in {"release", "golden"} and attestation_valid and attestation_verification.get("verifier_id") != independent_verifier:
        blockers.append("attestation verifier identity does not match the supplied verifier")
    if any(gate_id in {"G-P0-PASS", "G-P0-SSER", "G-DATA", "G-SEC", "G-TX"} for gate_id in failed_checks):
        decision = "REJECT"
    elif blockers:
        decision = "BLOCKED"
    else:
        decision = "PROMOTE" if attestation_valid and independent_verifier else "READY_FOR_EXTERNAL_GATE"
    return {"schema_version": "1.0", "profile": profile, "decision": decision, "certification_status": "NOT_CERTIFIED" if decision != "PROMOTE" else "EXTERNAL_ATTESTED_NOT_A_PRODUCTION_RELEASE", "checks": checks, "blockers": blockers, "external_attested": attestation_valid, "independent_verifier": independent_verifier, "attestation": dict(external_attestation) if external_attestation else None, "attestation_verification": dict(attestation_verification) if attestation_verification else None}


def _active_waivers(waivers: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    now = dt.datetime.now(dt.timezone.utc)
    active: dict[str, dict[str, Any]] = {}
    for waiver in waivers or []:
        try:
            expires = dt.datetime.fromisoformat(str(waiver["expires_at"]).replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if expires <= now or not waiver.get("approved_by"):
            continue
        for gate_id in waiver.get("gate_ids", []):
            active[str(gate_id)] = waiver
    return active


def evaluate_gates(metrics: dict[str, Any], gate_config: dict[str, Any], *, waivers: list[dict[str, Any]] | None = None, run_complete: bool = True) -> dict[str, Any]:
    """Evaluate an arbitrary v1.1 gate config with explicit waiver policy."""

    active = _active_waivers(waivers); rows: list[dict[str, Any]] = []; blocked = not run_complete; rejected = False; waived = False
    for gate in gate_config.get("gates", []):
        gate_id, metric, op, threshold = gate.get("id"), gate.get("metric"), gate.get("operator"), gate.get("threshold")
        actual = metrics.get(metric)
        if op not in OPERATORS or actual is None:
            rows.append({**gate, "state": "BLOCKED", "actual": actual, "reason": "unsupported operator or metric unavailable"}); blocked = True; continue
        if OPERATORS[op](actual, threshold):
            rows.append({**gate, "state": "PASS", "actual": actual}); continue
        waiver = active.get(str(gate_id))
        if waiver and gate_id not in NON_WAIVABLE_GATES:
            rows.append({**gate, "state": "WAIVED", "actual": actual, "waiver": waiver}); waived = True
        else:
            rows.append({**gate, "state": "FAIL", "actual": actual}); rejected = True
    decision = "REJECT" if rejected else "BLOCKED" if blocked else "PROMOTE_WITH_WAIVER" if waived else "PROMOTE"
    return {"schema_version": "1.1", "decision": decision, "run_complete": run_complete, "gate_results": rows, "summary": {"passed": sum(row["state"] == "PASS" for row in rows), "failed": sum(row["state"] == "FAIL" for row in rows), "blocked": sum(row["state"] == "BLOCKED" for row in rows), "waived": sum(row["state"] == "WAIVED" for row in rows)}}


def evaluate_gate_files(score_path: Path, gate_path: Path, *, waivers_path: Path | None = None, run_complete: bool | None = None) -> dict[str, Any]:
    score = json.loads(score_path.read_text(encoding="utf-8")); gate_config = yaml.safe_load(gate_path.read_text(encoding="utf-8")); waivers = None
    if waivers_path:
        payload = yaml.safe_load(waivers_path.read_text(encoding="utf-8")); waivers = payload.get("waivers", payload if isinstance(payload, list) else [])
    complete = not bool(score.get("partial_run")) if run_complete is None else run_complete
    return evaluate_gates(score.get("metrics", score), gate_config, waivers=waivers, run_complete=complete)
