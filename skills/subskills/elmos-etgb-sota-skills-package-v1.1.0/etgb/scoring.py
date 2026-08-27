from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

from etgb.statistics import multi_seed_stability

WEIGHT = {"P0": 5.0, "P1": 2.0, "P2": 1.0}
MANDATORY_EVIDENCE = {
    "input_digest",
    "toolchain_digest",
    "skill_version",
    "commands",
    "oracle_results_digest",
    "cost",
    "wall_clock_ms",
    "artifacts_digest",
    "environment",
    "adapter",
}


def _oracle_text(oracle: dict[str, Any]) -> str:
    return " ".join(str(oracle.get(key, "")) for key in ("type", "reason", "message", "classification")).lower()


def _is_failed_oracle(oracle: dict[str, Any]) -> bool:
    return oracle.get("passed") is False or oracle.get("status") in {"failed", "error"}


def score_results(results: list[dict[str, Any]], root: Path) -> dict[str, Any]:
    statuses = Counter(r["status"] for r in results)
    by_line: dict[str, Counter[str]] = defaultdict(Counter)
    weighted_total = 0.0
    weighted_passed = 0.0
    priority_total: Counter[str] = Counter()
    priority_passed: Counter[str] = Counter()
    priority_claimed_success: Counter[str] = Counter()
    priority_silent: Counter[str] = Counter()
    priority_critical: Counter[str] = Counter()
    priority_passed_critical: Counter[str] = Counter()
    executable = [r for r in results if r["status"] not in {"skipped", "unavailable"}]
    silent = 0
    claimed_success = 0
    critical_oracles = 0
    passed_critical = 0
    evidence_complete = 0
    counts = Counter()
    total_cost = {"token_input": 0, "token_output": 0, "credit_usd": 0.0, "wall_clock_ms": 0}
    mutation_killed = 0
    mutation_total = 0
    manual_cases = 0

    for result in results:
        line = result.get("business_line", "unknown")
        by_line[line][result["status"]] += 1
        if result["status"] not in {"skipped", "unavailable"}:
            priority = result.get("priority", "P2")
            weight = WEIGHT.get(priority, 1.0)
            weighted_total += weight
            priority_total[priority] += weight
            if result["status"] == "passed":
                weighted_passed += weight
                priority_passed[priority] += weight
                claimed_success += 1
                priority_claimed_success[priority] += 1
            if result.get("silent_semantic_error"):
                silent += 1
                priority_silent[priority] += 1
            if result.get("manual_intervention_required"):
                manual_cases += 1

            for oracle in result.get("oracle_results", []):
                text = _oracle_text(oracle)
                failed = _is_failed_oracle(oracle)
                critical = bool(oracle.get("critical", result.get("priority") == "P0"))
                if critical:
                    critical_oracles += 1
                    priority_critical[priority] += 1
                    if not failed and oracle.get("passed") is True:
                        passed_critical += 1
                        priority_passed_critical[priority] += 1
                if failed:
                    if "data corruption" in text or oracle.get("data_corruption"):
                        counts["data_corruption"] += 1
                    if any(x in text for x in ["security", "authorization", "authentication", "privilege", "tenant"]):
                        counts["security_regression"] += 1
                    if any(x in text for x in ["transaction", "rollback", "savepoint", "atomicity"]):
                        counts["transaction_mismatch"] += 1
                    if any(x in text for x in ["authority", "fencing", "permission owner"]):
                        counts["authority_violation"] += 1
                    if any(x in text for x in ["evidence", "digest", "signature", "audit chain"]):
                        counts["evidence_integrity_failure"] += 1
                    if any(x in text for x in ["unsupported", "manual intervention", "silent deletion"]):
                        counts["unsupported_undisclosed"] += 1
                    if any(x in text for x in ["resume", "checkpoint", "recovery", "compensation"]):
                        counts["recovery_failure"] += 1
                    if any(x in text for x in ["budget", "quota", "cost overrun", "credit"]):
                        counts["budget_overrun"] += 1
                    if any(x in text for x in ["latency", "throughput", "memory", "performance", "resource leak"]):
                        counts["performance_regression"] += 1
                    if any(x in text for x in ["candidate digest", "plan digest", "oracle version drift", "normalization policy drift", "image digest drift"]):
                        counts["integrity_drift"] += 1
                    if any(x in text for x in ["supply chain", "sbom", "provenance", "unsigned binary"]):
                        counts["supply_chain_failure"] += 1
                if oracle.get("type") == "mutation":
                    mutation_total += int(oracle.get("total", 0))
                    mutation_killed += int(oracle.get("killed", 0))

            evidence = result.get("evidence", {})
            if MANDATORY_EVIDENCE.issubset(evidence):
                evidence_complete += 1
            if evidence.get("integrity_valid") is False:
                counts["evidence_integrity_failure"] += 1
            if evidence.get("authority_valid") is False:
                counts["authority_violation"] += 1
            if result.get("flake") or result.get("status") == "flaky":
                counts["flaky"] += 1

            cost = result.get("cost", {})
            total_cost["token_input"] += int(cost.get("token_input", 0) or 0)
            total_cost["token_output"] += int(cost.get("token_output", 0) or 0)
            total_cost["credit_usd"] += float(cost.get("credit_usd", 0.0) or 0.0)
            total_cost["wall_clock_ms"] += int(cost.get("wall_clock_ms", result.get("duration_ms", 0)) or 0)

    stability = multi_seed_stability(executable, only_probabilistic=True)
    counts["flaky"] += stability["unstable_case_count"]
    weighted_pass_rate = weighted_passed / weighted_total if weighted_total else None
    sser = silent / max(1, claimed_success)
    critical_rate = passed_critical / critical_oracles if critical_oracles else None
    evidence_rate = evidence_complete / len(executable) if executable else None
    corpus = yaml.safe_load((root / "corpora/corpus-lock.yaml").read_text(encoding="utf-8"))
    metrics = {
        "weighted_pass_rate": weighted_pass_rate,
        "p0_weighted_pass_rate": priority_passed["P0"] / priority_total["P0"] if priority_total["P0"] else None,
        "p1_weighted_pass_rate": priority_passed["P1"] / priority_total["P1"] if priority_total["P1"] else None,
        "p2_weighted_pass_rate": priority_passed["P2"] / priority_total["P2"] if priority_total["P2"] else None,
        "silent_semantic_error_rate": sser,
        "p0_silent_semantic_error_rate": priority_silent["P0"] / max(1, priority_claimed_success["P0"]),
        "critical_oracle_pass_rate": critical_rate,
        "p0_critical_oracle_pass_rate": (
            priority_passed_critical["P0"] / priority_critical["P0"] if priority_critical["P0"] else None
        ),
        "evidence_completeness": evidence_rate,
        "data_corruption_count": counts["data_corruption"],
        "security_regression_count": counts["security_regression"],
        "transaction_mismatch_count": counts["transaction_mismatch"],
        "flaky_case_count": counts["flaky"],
        "authority_violation_count": counts["authority_violation"],
        "evidence_integrity_failure_count": counts["evidence_integrity_failure"],
        "unsupported_undisclosed_count": counts["unsupported_undisclosed"],
        "recovery_failure_count": counts["recovery_failure"],
        "budget_overrun_count": counts["budget_overrun"],
        "supply_chain_failure_count": counts["supply_chain_failure"],
        "performance_regression_count": counts["performance_regression"],
        "integrity_drift_count": counts["integrity_drift"],
        "human_intervention_rate": manual_cases / len(executable) if executable else None,
        "mutation_kill_rate": mutation_killed / mutation_total if mutation_total else None,
        "unapproved_corpus_count": sum(
            1 for item in corpus["repositories"] if item["license_review"] != "approved"
        ),
        "multi_seed_unstable_case_count": stability["unstable_case_count"],
        "insufficient_seed_case_count": stability["insufficient_seed_case_count"],
    }
    total_cost["credit_usd"] = round(total_cost["credit_usd"], 8)
    return {
        "schema_version": "1.1",
        "total_results": len(results),
        "executable_results": len(executable),
        "statuses": dict(statuses),
        "by_business_line": {key: dict(value) for key, value in by_line.items()},
        "metrics": metrics,
        "cost": total_cost,
        "stability": stability,
        "partial_run": len(executable) != len(results),
        "interpretation": (
            "Release gates are authoritative only for a complete release/golden run. "
            "Counts are derived from explicit Oracle/evidence classifications; missing release metrics block certification."
        ),
    }
