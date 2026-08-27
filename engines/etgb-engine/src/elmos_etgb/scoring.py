"""Conservative, priority-denominated ETGB scoring for v1.1 gates."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .corpus import verify_lock
from .statistics import multi_seed_stability

WEIGHT = {"P0": 5.0, "P1": 2.0, "P2": 1.0}
NON_SUCCESS = frozenset({"failed", "error", "skipped", "unavailable"})


def _oracle_text(oracle: dict[str, Any]) -> str:
    return " ".join(str(oracle.get(key, "")) for key in ("type", "reason", "message", "classification", "error_type")).lower()


def _is_failed(oracle: dict[str, Any]) -> bool:
    return oracle.get("passed") is False or oracle.get("status") in {"failed", "error"}


def _evidence_complete(result: dict[str, Any]) -> bool:
    evidence = result.get("evidence", {})
    artifacts = evidence.get("artifacts", [])
    required = {"input_digest", "toolchain_digest", "skill_version", "commands", "oracle_results_digest", "wall_clock_ms", "artifacts_digest", "environment", "adapter"}
    if not required.issubset(evidence) or not evidence.get("input_digest") or not evidence.get("environment") or not evidence.get("adapter"):
        return False
    roles = {item.get("role") for item in artifacts if isinstance(item, dict)}
    return isinstance(artifacts, list) and {"case-input", "environment", "evidence-manifest"}.issubset(roles)


def score_results(results: list[dict[str, Any]], root: Path, *, expected_count: int | None = None, complete: bool | None = None, corpus_release: bool = False, trust_store: dict[str, Any] | None = None) -> dict[str, Any]:
    statuses = Counter(str(result.get("status", "error")) for result in results)
    by_line: dict[str, Counter[str]] = defaultdict(Counter)
    by_priority = {key: {"total_weight": 0.0, "passed_weight": 0.0, "weighted_pass_rate": 0.0} for key in WEIGHT}
    counts = Counter()
    silent = p0_silent = claimed = p0_claimed = 0
    critical = passed_critical = p0_critical = p0_passed_critical = 0
    evidence_complete = 0
    total_cost = {"token_input": 0, "token_output": 0, "credit_usd": 0.0, "wall_clock_ms": 0}
    executable = [result for result in results if result.get("status") not in {"skipped", "unavailable"}]
    for result in results:
        status = str(result.get("status", "error")); priority = str(result.get("priority", "P2")); by_line[str(result.get("business_line", "unknown"))][status] += 1
        if status in NON_SUCCESS: counts["failed_result"] += 1
        if priority in WEIGHT and status not in {"skipped", "unavailable"}:
            by_priority[priority]["total_weight"] += WEIGHT[priority]
            if status == "passed": by_priority[priority]["passed_weight"] += WEIGHT[priority]
        if status == "passed":
            claimed += 1; p0_claimed += priority == "P0"
        if _evidence_complete(result): evidence_complete += 1
        if result.get("silent_semantic_error") is True: silent += 1; p0_silent += priority == "P0"
        failure_text = " ".join([str(result.get("failure_class", ""))] + [_oracle_text(oracle) for oracle in result.get("oracle_results", [])]).lower()
        failed_signal = status in NON_SUCCESS or any(_is_failed(oracle) for oracle in result.get("oracle_results", []) if isinstance(oracle, dict))
        if failed_signal and any(token in failure_text for token in ("data corruption", "data_corruption")): counts["data_corruption"] += 1
        if failed_signal and any(token in failure_text for token in ("security", "authorization", "authentication", "privilege", "tenant")): counts["security_regression"] += 1
        if failed_signal and any(token in failure_text for token in ("transaction", "rollback", "savepoint", "atomicity", "side-effect")): counts["transaction_mismatch"] += 1; counts["p0_transaction_mismatch"] += priority == "P0"
        if failed_signal and any(token in failure_text for token in ("authority", "fencing", "permission owner")): counts["authority_violation"] += 1
        if failed_signal and any(token in failure_text for token in ("evidence", "digest", "signature", "audit chain")): counts["evidence_integrity_failure"] += 1
        if failed_signal and any(token in failure_text for token in ("unsupported", "manual intervention", "silent deletion")): counts["unsupported_undisclosed"] += 1
        if failed_signal and any(token in failure_text for token in ("resume", "checkpoint", "recovery", "compensation")): counts["recovery_failure"] += 1
        if failed_signal and any(token in failure_text for token in ("budget", "quota", "credit", "token limit")): counts["budget_overrun"] += 1
        if failed_signal and any(token in failure_text for token in ("latency", "throughput", "memory", "performance", "resource leak")): counts["performance_regression"] += 1
        if failed_signal and any(token in failure_text for token in ("candidate digest", "plan digest", "oracle version", "normalization", "image digest drift")): counts["integrity_drift"] += 1
        if failed_signal and any(token in failure_text for token in ("supply chain", "sbom", "provenance", "unsigned binary")): counts["supply_chain_failure"] += 1
        if result.get("flaky") is True or status == "flaky": counts["flaky"] += 1
        for oracle in result.get("oracle_results", []):
            if not isinstance(oracle, dict) or (oracle.get("critical") is not True and not (oracle.get("critical") is None and priority == "P0")): continue
            critical += 1; p0_critical += priority == "P0"
            if not _is_failed(oracle): passed_critical += 1; p0_passed_critical += priority == "P0"
        cost = result.get("cost", {})
        total_cost["token_input"] += int(cost.get("token_input", 0) or 0); total_cost["token_output"] += int(cost.get("token_output", 0) or 0); total_cost["credit_usd"] += float(cost.get("credit_usd", 0.0) or 0.0); total_cost["wall_clock_ms"] += int(cost.get("wall_clock_ms", result.get("duration_ms", 0)) or 0)
    for values in by_priority.values():
        if values["total_weight"]: values["weighted_pass_rate"] = values["passed_weight"] / values["total_weight"]
    corpus = verify_lock(root, release=corpus_release, trust_store=trust_store)
    inferred_complete = expected_count is not None and len(results) == expected_count and not any(status in {"skipped", "unavailable"} for status in statuses)
    complete_run = inferred_complete if complete is None else bool(complete)
    stability = multi_seed_stability(executable, only_probabilistic=True)
    counts["flaky"] += stability["unstable_case_count"]
    total_weight = sum(item["total_weight"] for item in by_priority.values()); passed_weight = sum(item["passed_weight"] for item in by_priority.values()); total_cost["credit_usd"] = round(total_cost["credit_usd"], 8)
    metrics = {"weighted_pass_rate": passed_weight / total_weight if total_weight else None, "p0_weighted_pass_rate": by_priority["P0"]["weighted_pass_rate"], "p1_weighted_pass_rate": by_priority["P1"]["weighted_pass_rate"], "p2_weighted_pass_rate": by_priority["P2"]["weighted_pass_rate"], "silent_semantic_error_rate": silent / claimed if claimed else 0.0, "p0_silent_semantic_error_rate": p0_silent / p0_claimed if p0_claimed else 0.0, "critical_oracle_pass_rate": passed_critical / critical if critical else None, "p0_critical_oracle_pass_rate": p0_passed_critical / p0_critical if p0_critical else None, "evidence_completeness": evidence_complete / len(executable) if executable else None, "data_corruption_count": counts["data_corruption"], "security_regression_count": counts["security_regression"], "transaction_mismatch_count": counts["transaction_mismatch"], "p0_transaction_mismatch_count": counts["p0_transaction_mismatch"], "authority_violation_count": counts["authority_violation"], "evidence_integrity_failure_count": counts["evidence_integrity_failure"], "unsupported_undisclosed_count": counts["unsupported_undisclosed"], "recovery_failure_count": counts["recovery_failure"], "budget_overrun_count": counts["budget_overrun"], "supply_chain_failure_count": counts["supply_chain_failure"], "performance_regression_count": counts["performance_regression"], "integrity_drift_count": counts["integrity_drift"], "flaky_case_count": counts["flaky"], "unapproved_corpus_count": corpus["unapproved"], "failed_result_count": counts["failed_result"], "insufficient_seed_case_count": stability["insufficient_seed_case_count"]}
    return {"schema_version": "1.1", "total_results": len(results), "expected_results": expected_count, "executable_results": len(executable), "statuses": dict(statuses), "by_business_line": {key: dict(value) for key, value in by_line.items()}, "by_priority": by_priority, "complete_run": complete_run, "partial_run": not complete_run, "metrics": metrics, "corpus": corpus, "cost": total_cost, "stability": stability, "interpretation": "Unavailable, skipped, failed and incomplete work remains non-success; local results do not certify a release."}
