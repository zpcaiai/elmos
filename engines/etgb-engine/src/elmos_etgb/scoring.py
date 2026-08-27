"""Conservative ETGB metrics; unavailable and incomplete work remains visible."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .corpus import verify_lock


WEIGHT = {"P0": 5.0, "P1": 2.0, "P2": 1.0}
NON_SUCCESS = frozenset({"failed", "error", "skipped", "unavailable"})


def _is_evidence_complete(result: dict[str, Any]) -> bool:
    evidence = result.get("evidence", {})
    artifacts = evidence.get("artifacts", [])
    if not evidence.get("input_digest") or not evidence.get("environment") or not evidence.get("adapter"):
        return False
    if not isinstance(artifacts, list) or not artifacts:
        return False
    roles = {item.get("role") for item in artifacts if isinstance(item, dict)}
    return "case-input" in roles and "environment" in roles and "evidence-manifest" in roles


def score_results(results: list[dict[str, Any]], root: Path, *, expected_count: int | None = None, complete: bool | None = None) -> dict[str, Any]:
    statuses = Counter(str(result.get("status", "error")) for result in results)
    by_line: dict[str, Counter[str]] = defaultdict(Counter)
    by_priority: dict[str, dict[str, float]] = {priority: {"total_weight": 0.0, "passed_weight": 0.0, "weighted_pass_rate": 0.0} for priority in WEIGHT}
    silent = 0
    p0_silent = 0
    claimed_success = 0
    p0_claimed_success = 0
    critical_oracles = 0
    passed_critical = 0
    p0_critical_oracles = 0
    p0_passed_critical = 0
    evidence_success = 0
    failed_results = 0
    data_corruption = 0
    security_regressions = 0
    transaction_mismatches = 0
    p0_transaction_mismatches = 0
    flaky = 0
    p0_flaky = 0
    seeds_by_case: dict[str, set[int]] = defaultdict(set)
    for result in results:
        status = str(result.get("status", "error"))
        line = str(result.get("business_line", "unknown"))
        priority = str(result.get("priority", "P2"))
        by_line[line][status] += 1
        if priority in WEIGHT:
            by_priority[priority]["total_weight"] += WEIGHT[priority]
            if status == "passed":
                by_priority[priority]["passed_weight"] += WEIGHT[priority]
        if status == "passed":
            claimed_success += 1
            if priority == "P0":
                p0_claimed_success += 1
            if _is_evidence_complete(result):
                evidence_success += 1
        if result.get("silent_semantic_error") is True:
            silent += 1
            if priority == "P0":
                p0_silent += 1
        if status in NON_SUCCESS:
            failed_results += 1
        if result.get("failure_class") in {"security", "security regression"}:
            security_regressions += 1
        if result.get("failure_class") in {"state/transaction mismatch", "transaction mismatch"}:
            transaction_mismatches += 1
            if priority == "P0":
                p0_transaction_mismatches += 1
        if result.get("failure_class") == "data corruption":
            data_corruption += 1
        if result.get("flaky") is True:
            flaky += 1
            if priority == "P0":
                p0_flaky += 1
        for oracle in result.get("oracle_results", []):
            if isinstance(oracle, dict) and oracle.get("critical") is True:
                critical_oracles += 1
                if priority == "P0":
                    p0_critical_oracles += 1
                if oracle.get("passed") is True:
                    passed_critical += 1
                    if priority == "P0":
                        p0_passed_critical += 1
        if result.get("case_id") is not None:
            seeds_by_case[str(result["case_id"])].add(int(result.get("seed", 0)))
    for values in by_priority.values():
        if values["total_weight"]:
            values["weighted_pass_rate"] = values["passed_weight"] / values["total_weight"]
    total_weight = sum(values["total_weight"] for values in by_priority.values())
    passed_weight = sum(values["passed_weight"] for values in by_priority.values())
    corpus = verify_lock(root, release=False)
    inferred_complete = expected_count is not None and len(results) == expected_count and not any(status in statuses for status in {"skipped", "unavailable"})
    complete_run = inferred_complete if complete is None else complete
    multi_seed_cases = sum(1 for seeds in seeds_by_case.values() if len(seeds) > 1)
    return {
        "schema_version": "1.0",
        "total_results": len(results),
        "expected_results": expected_count,
        "executable_results": len(results) - statuses.get("skipped", 0) - statuses.get("unavailable", 0),
        "statuses": dict(statuses),
        "by_business_line": {key: dict(value) for key, value in by_line.items()},
        "by_priority": by_priority,
        "complete_run": complete_run,
        "partial_run": not complete_run,
        "metrics": {
            "weighted_pass_rate": passed_weight / total_weight if total_weight else None,
            "silent_semantic_error_rate": silent / claimed_success if claimed_success else 0.0,
            "critical_oracle_pass_rate": passed_critical / critical_oracles if critical_oracles else None,
            "evidence_completeness": evidence_success / claimed_success if claimed_success else None,
            "p0_silent_semantic_error_rate": p0_silent / p0_claimed_success if p0_claimed_success else 0.0,
            "p0_critical_oracle_pass_rate": p0_passed_critical / p0_critical_oracles if p0_critical_oracles else None,
            "data_corruption_count": data_corruption,
            "security_regression_count": security_regressions,
            "transaction_mismatch_count": transaction_mismatches,
            "p0_transaction_mismatch_count": p0_transaction_mismatches,
            "flaky_case_count": flaky,
            "p0_flaky_case_count": p0_flaky,
            "unapproved_corpus_count": corpus["unapproved"],
            "failed_result_count": failed_results,
            "multi_seed_case_count": multi_seed_cases,
        },
        "corpus": corpus,
        "interpretation": "Unavailable, skipped, failed, and incomplete work remains non-success; local results are engineering evidence and do not by themselves certify a release.",
    }
