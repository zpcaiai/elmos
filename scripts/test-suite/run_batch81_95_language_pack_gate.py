#!/usr/bin/env python3
"""Run the fail-closed Batch 81-95 supplemental qualification gate."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from validate_batch81_95_language_packs import DEFAULT_SOURCE, DEFAULT_SUITE, validate_suite


EXECUTED_STATUSES = {"PASSED", "FAILED", "QUARANTINED", "FLAKY"}


def rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for child in value for item in strings(child)]
    if isinstance(value, dict):
        return [item for child in value.values() for item in strings(child)]
    return []


def dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("suite", nargs="?", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    suite = args.suite.resolve()
    source = args.source.resolve()
    validation_errors, metrics = validate_suite(suite, source)
    blockers = [f"catalog validation: {error}" for error in validation_errors]

    try:
        descriptor = json.loads((suite / "suite.json").read_text(encoding="utf-8"))
        profile = json.loads(
            (suite / descriptor["strictness_profile"]).read_text(encoding="utf-8")
        )
        cases = json.loads((suite / descriptor["case_catalog"]).read_text(encoding="utf-8"))
        result_catalog = json.loads(
            (suite / descriptor["result_catalog"]).read_text(encoding="utf-8")
        )
        results = result_catalog["results"]
    except Exception as exc:  # noqa: BLE001
        profile = {"name": "unknown", "thresholds": {}, "zero_tolerance": []}
        cases = []
        results = []
        blockers.append(f"cannot load gate inputs: {exc}")

    counts = Counter(
        result.get("status", "INVALID") for result in results if isinstance(result, dict)
    )
    severity_totals = Counter(
        result.get("severity", "INVALID") for result in results if isinstance(result, dict)
    )
    severity_passed = Counter(
        result.get("severity", "INVALID")
        for result in results
        if isinstance(result, dict) and result.get("status") == "PASSED"
    )
    passed = counts["PASSED"]
    overall_pass_rate = rate(passed, len(results))
    critical_pass_rate = rate(severity_passed["CRITICAL"], severity_totals["CRITICAL"])
    high_pass_rate = rate(severity_passed["HIGH"], severity_totals["HIGH"])

    batch_result_ids = {
        case.get("id")
        for case in cases
        if isinstance(case, dict) and isinstance(case.get("batch"), int)
    }
    direct_result_ids = {
        case.get("id")
        for case in cases
        if isinstance(case, dict) and case.get("category") == "source-skill-direct"
    }
    result_by_id = {
        result.get("case_id"): result for result in results if isinstance(result, dict)
    }
    batch_executed = sum(
        result_by_id.get(case_id, {}).get("status") in EXECUTED_STATUSES
        for case_id in batch_result_ids
    )
    direct_executed = sum(
        result_by_id.get(case_id, {}).get("status") in EXECUTED_STATUSES
        for case_id in direct_result_ids
    )
    batch_execution_coverage = rate(batch_executed, len(batch_result_ids))
    direct_source_skill_coverage = rate(direct_executed, len(direct_result_ids))

    evidence_complete = sum(
        result.get("evidence_complete") is True for result in results if isinstance(result, dict)
    )
    critical_high_results = [
        result
        for result in results
        if isinstance(result, dict) and result.get("severity") in {"CRITICAL", "HIGH"}
    ]
    critical_high_evidence = sum(
        result.get("evidence_complete") is True for result in critical_high_results
    )
    critical_high_evidence_completeness = rate(
        critical_high_evidence, len(critical_high_results)
    )
    overall_evidence_completeness = rate(evidence_complete, len(results))
    flaky_count = sum(
        result.get("status") == "FLAKY" or result.get("flaky") is True
        for result in results
        if isinstance(result, dict)
    )
    quarantine_count = sum(
        result.get("status") == "QUARANTINED" or result.get("quarantined") is True
        for result in results
        if isinstance(result, dict)
    )
    flaky_rate = rate(flaky_count, len(results))
    quarantine_rate = rate(quarantine_count, len(results))

    threshold_values = {
        "critical_pass_rate": critical_pass_rate,
        "high_pass_rate": high_pass_rate,
        "overall_pass_rate": overall_pass_rate,
        "batch_execution_coverage": batch_execution_coverage,
        "direct_source_skill_coverage": direct_source_skill_coverage,
        "critical_high_evidence_completeness": critical_high_evidence_completeness,
        "overall_evidence_completeness": overall_evidence_completeness,
    }
    thresholds = profile.get("thresholds", {})
    if len(results) != 640:
        blockers.append(f"exact result completeness unmet: {len(results)}/640")
    for name, value in threshold_values.items():
        minimum = thresholds.get(name, 1.0)
        if value < minimum:
            blockers.append(f"{name} {value:.4f} is below {minimum:.4f}")
    for name, value in (
        ("max_flaky_rate", flaky_rate),
        ("max_quarantine_rate", quarantine_rate),
    ):
        maximum = thresholds.get(name, 0.0)
        if value > maximum:
            blockers.append(f"{name} {value:.4f} exceeds {maximum:.4f}")
    if counts["NOT_RUN"]:
        blockers.append(f"required cases remain NOT_RUN: {counts['NOT_RUN']}")
    if counts["BLOCKED"]:
        blockers.append(f"required cases remain BLOCKED: {counts['BLOCKED']}")

    zero_tolerance_findings: list[dict[str, str]] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        finding_text = "\n".join(strings(result.get("findings", []))).lower()
        for prohibited in profile.get("zero_tolerance", []):
            if str(prohibited).lower() in finding_text:
                zero_tolerance_findings.append(
                    {"case_id": str(result.get("case_id")), "finding": str(prohibited)}
                )
    if zero_tolerance_findings:
        blockers.append(
            f"zero-tolerance findings remain: {len(zero_tolerance_findings)}"
        )

    source_status = "NOT_RUN" if counts["NOT_RUN"] == len(results) and results else "PARTIAL"
    if len(results) == 640 and passed == 640:
        source_status = "COMPLETE"
    decision = "BLOCKED" if blockers else "READY_FOR_EXTERNAL_GATE"
    report = {
        "schema_version": "1.0",
        "suite_id": "batch81-95-language-packs-slightly-strict",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "source_status": source_status,
        "decision": decision,
        "maximum_success_decision": "READY_FOR_EXTERNAL_GATE",
        "certified": False,
        "approves_vendor_or_physical_operation": False,
        "updates_batch1_37_certification": False,
        "source_id_namespace": "package-local-language-pack",
        "source_evaluator_authoritative": False,
        "profile_name": profile.get("name"),
        "metrics": {
            **metrics,
            "status_counts": dict(sorted(counts.items())),
            **threshold_values,
            "flaky_rate": flaky_rate,
            "quarantine_rate": quarantine_rate,
            "zero_tolerance_findings": len(zero_tolerance_findings),
        },
        "blockers": blockers,
    }
    rendered = dump_json(report)
    if args.report:
        destination = args.report.resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if decision == "READY_FOR_EXTERNAL_GATE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
