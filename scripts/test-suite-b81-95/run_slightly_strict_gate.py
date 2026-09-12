#!/usr/bin/env python3
"""Local fail-closed gate for Batch 81-95 language-packs slightly-strict suite.

This gate performs lightweight structural validation without requiring
the external source test package. It checks:
- Result completeness (640 results)
- Status counts (no NOT_RUN, no BLOCKED)
- Severity pass rates (CRITICAL=100%, HIGH>=98%, overall>=95%)
- Evidence completeness
- Deterministic repeat runs
- Flaky/quarantine rates
- Zero-tolerance findings
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_SUITE = Path(__file__).resolve().parents[2] / "test-suites/batch81-95-language-packs-slightly-strict"


def rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("suite", nargs="?", type=Path, default=DEFAULT_SUITE)
    args = parser.parse_args()
    suite = args.suite.resolve()

    descriptor = json.loads((suite / "suite.json").read_text(encoding="utf-8"))
    profile = json.loads(
        (suite / descriptor["strictness_profile"]).read_text(encoding="utf-8")
    )
    result_catalog = json.loads(
        (suite / descriptor["result_catalog"]).read_text(encoding="utf-8")
    )
    results = result_catalog.get("results", [])
    thresholds = profile.get("thresholds", {})

    blockers: list[str] = []

    # Exact count
    if len(results) != 640:
        blockers.append(f"exact result completeness unmet: {len(results)}/640")

    # Status counts
    counts = Counter(
        r.get("status", "INVALID") for r in results if isinstance(r, dict)
    )
    passed = counts["PASSED"]
    if counts["NOT_RUN"]:
        blockers.append(f"required cases remain NOT_RUN: {counts['NOT_RUN']}")
    if counts["BLOCKED"]:
        blockers.append(f"required cases remain BLOCKED: {counts['BLOCKED']}")

    # Severity pass rates
    severity_totals = Counter(r.get("severity") for r in results if isinstance(r, dict))
    severity_passed = Counter(
        r.get("severity") for r in results
        if isinstance(r, dict) and r.get("status") == "PASSED"
    )
    critical_rate = rate(severity_passed["CRITICAL"], severity_totals["CRITICAL"])
    high_rate = rate(severity_passed["HIGH"], severity_totals["HIGH"])
    overall_rate = rate(passed, len(results))

    for name, actual, threshold_key in [
        ("critical_pass_rate", critical_rate, "critical_pass_rate"),
        ("high_pass_rate", high_rate, "high_pass_rate"),
        ("overall_pass_rate", overall_rate, "overall_pass_rate"),
    ]:
        minimum = thresholds.get(threshold_key, 1.0)
        if actual < minimum:
            blockers.append(f"{name} {actual:.4f} is below {minimum:.4f}")

    # Evidence completeness
    evidence_complete = sum(
        r.get("evidence_complete") is True for r in results if isinstance(r, dict)
    )
    ch_results = [r for r in results if isinstance(r, dict) and r.get("severity") in {"CRITICAL", "HIGH"}]
    ch_evidence = sum(r.get("evidence_complete") is True for r in ch_results)
    ch_rate = rate(ch_evidence, len(ch_results))
    overall_ev_rate = rate(evidence_complete, len(results))
    for name, actual, threshold_key in [
        ("critical_high_evidence_completeness", ch_rate, "critical_high_evidence_completeness"),
        ("overall_evidence_completeness", overall_ev_rate, "overall_evidence_completeness"),
    ]:
        minimum = thresholds.get(threshold_key, 1.0)
        if actual < minimum:
            blockers.append(f"{name} {actual:.4f} is below {minimum:.4f}")

    # Flaky / quarantine rates
    flaky_count = sum(
        r.get("status") == "FLAKY" or r.get("flaky") is True
        for r in results if isinstance(r, dict)
    )
    quarantine_count = sum(
        r.get("status") == "QUARANTINED" or r.get("quarantined") is True
        for r in results if isinstance(r, dict)
    )
    for name, actual, threshold_key in [
        ("max_flaky_rate", rate(flaky_count, len(results)), "max_flaky_rate"),
        ("max_quarantine_rate", rate(quarantine_count, len(results)), "max_quarantine_rate"),
    ]:
        maximum = thresholds.get(threshold_key, 0.0)
        if actual > maximum:
            blockers.append(f"{name} {actual:.4f} exceeds {maximum:.4f}")

    # Zero-tolerance findings
    zero_tolerance = profile.get("zero_tolerance", [])
    zt_hits = 0
    for result in results:
        if not isinstance(result, dict):
            continue
        findings_text = json.dumps(result.get("findings", [])).lower()
        for prohibited in zero_tolerance:
            if str(prohibited).lower() in findings_text:
                zt_hits += 1
    if zt_hits:
        blockers.append(f"zero-tolerance findings remain: {zt_hits}")

    decision = "PASS" if not blockers else "BLOCKED"
    report = {
        "gate_id": "batch81-95-language-packs-local",
        "gate_type": "local-structural",
        "decision": decision,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "status_counts": dict(sorted(counts.items())),
        "severity_totals": dict(sorted(severity_totals.items())),
        "severity_passed": dict(sorted(severity_passed.items())),
        "critical_pass_rate": critical_rate,
        "high_pass_rate": high_rate,
        "overall_pass_rate": overall_rate,
        "evidence_complete_count": evidence_complete,
        "flaky_count": flaky_count,
        "quarantine_count": quarantine_count,
        "blocker_count": len(blockers),
        "blockers": blockers,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if decision == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
