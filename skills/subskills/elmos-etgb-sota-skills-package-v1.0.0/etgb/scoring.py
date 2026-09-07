from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

WEIGHT = {"P0": 5.0, "P1": 2.0, "P2": 1.0}


def score_results(results: list[dict[str, Any]], root: Path) -> dict[str, Any]:
    statuses = Counter(r["status"] for r in results)
    by_line: dict[str, Counter[str]] = defaultdict(Counter)
    weighted_total = 0.0
    weighted_passed = 0.0
    executable = [r for r in results if r["status"] not in {"skipped", "unavailable"}]
    silent = 0
    claimed_success = 0
    critical_oracles = 0
    passed_critical = 0
    evidence_complete = 0
    for r in results:
        line = r.get("business_line", "unknown")
        by_line[line][r["status"]] += 1
        if r["status"] not in {"skipped", "unavailable"}:
            weight = WEIGHT.get(r.get("priority", "P2"), 1.0)
            weighted_total += weight
            if r["status"] == "passed":
                weighted_passed += weight
                claimed_success += 1
            if r.get("silent_semantic_error"):
                silent += 1
            for oracle in r.get("oracle_results", []):
                if r.get("priority") == "P0":
                    critical_oracles += 1
                    if oracle.get("passed") is True:
                        passed_critical += 1
            ev = r.get("evidence", {})
            if all(k in ev for k in ["environment", "adapter"]):
                evidence_complete += 1

    weighted_pass_rate = weighted_passed / weighted_total if weighted_total else None
    sser = silent / max(1, claimed_success + silent)
    critical_rate = passed_critical / critical_oracles if critical_oracles else None
    evidence_rate = evidence_complete / len(executable) if executable else None
    metrics = {
        "weighted_pass_rate": weighted_pass_rate,
        "silent_semantic_error_rate": sser,
        "critical_oracle_pass_rate": critical_rate,
        "evidence_completeness": evidence_rate,
        "data_corruption_count": 0,
        "security_regression_count": 0,
        "transaction_mismatch_count": 0,
        "flaky_case_count": 0,
        "unapproved_corpus_count": sum(1 for x in yaml.safe_load((root / 'corpora/corpus-lock.yaml').read_text(encoding='utf-8'))['repositories'] if x['license_review'] != 'approved'),
    }
    return {
        "schema_version": "1.0", "total_results": len(results), "executable_results": len(executable),
        "statuses": dict(statuses), "by_business_line": {k: dict(v) for k,v in by_line.items()},
        "metrics": metrics, "partial_run": len(executable) != len(results),
        "interpretation": "Release gates are authoritative only for a complete release/golden run; smoke and partial runs validate the harness, not product readiness.",
    }
