#!/usr/bin/env python3
"""Fail-closed release gate for the Batch 1-65 supplemental test suite."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from validate_batch1_65_slightly_strict import DEFAULT_SUITE, validate_suite


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def rate(passed: int, total: int) -> float:
    return passed / total if total else 1.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("suite", nargs="?", type=Path, default=DEFAULT_SUITE)
    args = parser.parse_args()
    root = args.suite.resolve()
    validation_errors, validation_metrics = validate_suite(root)
    blockers = [f"catalog validation: {error}" for error in validation_errors]

    try:
        suite = json.loads((root / "suite.json").read_text(encoding="utf-8"))
        profile = json.loads((root / suite["strictness_profile"]).read_text(encoding="utf-8"))
        result_catalog = json.loads((root / suite["result_catalog"]).read_text(encoding="utf-8"))
        results = result_catalog["results"]
    except Exception as exc:  # noqa: BLE001
        suite = {}
        profile = {"profile_id": "unknown", "thresholds": {}}
        result_catalog = {}
        results = []
        blockers.append(f"cannot load gate inputs: {exc}")

    counts = Counter(result.get("status", "INVALID") for result in results if isinstance(result, dict))
    severity_totals = Counter(result.get("severity", "INVALID") for result in results if isinstance(result, dict))
    severity_passed = Counter(
        result.get("severity", "INVALID")
        for result in results
        if isinstance(result, dict) and result.get("status") == "PASSED"
    )
    thresholds = profile.get("thresholds", {})
    total = len(results)
    passed = counts["PASSED"]
    overall_pass_rate = rate(passed, total)
    severity_rates = {
        severity: rate(severity_passed[severity], severity_totals[severity])
        for severity in ("CRITICAL", "HIGH", "MEDIUM", "LOW")
    }

    if total != 750:
        blockers.append(f"exact result completeness unmet: {total}/750")
    if counts["NOT_RUN"]:
        blockers.append(f"required cases remain NOT_RUN: {counts['NOT_RUN']}")
    if counts["BLOCKED"]:
        blockers.append(f"required cases are BLOCKED: {counts['BLOCKED']}")
    if counts["FAILED"]:
        blockers.append(f"test failures remain: {counts['FAILED']}")
    if severity_rates["CRITICAL"] < thresholds.get("critical_pass_rate_min", 1.0):
        blockers.append(
            f"critical pass rate below threshold: {severity_passed['CRITICAL']}/{severity_totals['CRITICAL']}"
        )
    if severity_rates["HIGH"] < thresholds.get("high_pass_rate_min", 0.98):
        blockers.append(f"high pass rate below threshold: {severity_rates['HIGH']:.4f}")
    if severity_rates["MEDIUM"] < thresholds.get("medium_pass_rate_min", 0.95):
        blockers.append(f"medium pass rate below threshold: {severity_rates['MEDIUM']:.4f}")
    if severity_rates["LOW"] < thresholds.get("low_pass_rate_min", 0.90):
        blockers.append(f"low pass rate below threshold: {severity_rates['LOW']:.4f}")
    if overall_pass_rate < thresholds.get("overall_pass_rate_min", 0.95):
        blockers.append(f"overall pass rate below threshold: {overall_pass_rate:.4f}")

    by_skill: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        if isinstance(result, dict) and isinstance(result.get("test_skill_id"), str):
            by_skill[result["test_skill_id"]].append(result)
    executed_batch_skills = sum(
        bool(by_skill.get(f"T{number:03d}"))
        and all(result.get("status") != "NOT_RUN" for result in by_skill[f"T{number:03d}"])
        for number in range(1, 66)
    )
    if executed_batch_skills != 65:
        blockers.append(f"Batch test Skill execution coverage unmet: {executed_batch_skills}/65")

    high_critical = [
        result for result in results if isinstance(result, dict) and result.get("severity") in {"CRITICAL", "HIGH"}
    ]
    high_critical_complete = sum(result.get("evidence_complete") is True for result in high_critical)
    evidence_complete = sum(
        result.get("evidence_complete") is True for result in results if isinstance(result, dict)
    )
    high_critical_evidence_rate = rate(high_critical_complete, len(high_critical))
    overall_evidence_rate = rate(evidence_complete, total)
    if high_critical_evidence_rate < thresholds.get("evidence_completeness_critical_high_min", 1.0):
        blockers.append(f"Critical/High evidence completeness unmet: {high_critical_evidence_rate:.4f}")
    if overall_evidence_rate < thresholds.get("evidence_completeness_overall_min", 0.98):
        blockers.append(f"overall evidence completeness unmet: {overall_evidence_rate:.4f}")

    insufficient_repeats = sum(
        result.get("status") == "PASSED"
        and result.get("deterministic_repeat_runs", 0)
        < thresholds.get("deterministic_repeat_runs", 2)
        for result in results
        if isinstance(result, dict)
    )
    if insufficient_repeats:
        blockers.append(f"passed cases without required deterministic repeats: {insufficient_repeats}")
    flaky = sum(result.get("flaky") is True for result in results if isinstance(result, dict))
    flaky_rate = rate(flaky, total)
    if flaky_rate > thresholds.get("flaky_rate_max", 0.01):
        blockers.append(f"flaky rate above threshold: {flaky_rate:.4f}")
    quarantined = counts["QUARANTINED"]
    quarantined_rate = rate(quarantined, total)
    if quarantined_rate > thresholds.get("quarantined_rate_max", 0.005):
        blockers.append(f"quarantine rate above threshold: {quarantined_rate:.4f}")
    if any(
        result.get("status") == "QUARANTINED" and result.get("severity") in {"CRITICAL", "HIGH"}
        for result in results
        if isinstance(result, dict)
    ):
        blockers.append("Critical or High case is quarantined")

    anti_fraud_signals = sorted(
        {
            signal
            for result in results
            if isinstance(result, dict)
            for signal in result.get("anti_fraud_signals", [])
            if isinstance(signal, str)
        }
    )
    if anti_fraud_signals:
        blockers.append(f"anti-fraud or zero-tolerance signals present: {anti_fraud_signals}")
    waivers = result_catalog.get("waivers", [])
    if not isinstance(waivers, list):
        blockers.append("waivers must be a list")
    elif waivers:
        blockers.append("waiver adjudication is external and has not been evidenced")

    decision = "BLOCKED" if blockers else "READY_FOR_EXTERNAL_GATE"
    field_status = "NOT_RUN" if counts["NOT_RUN"] else "INCOMPLETE" if blockers else "READY"
    gate = {
        "gate_id": "batch1-65-slightly-strict-supplemental",
        "gate_version": 1,
        "decision": decision,
        "certification_authority": False,
        "maximum_success_decision": "READY_FOR_EXTERNAL_GATE",
        "evaluated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "field_evidence_status": field_status,
        "profile_id": profile.get("profile_id"),
        "metrics": {
            **validation_metrics,
            "status_counts": {
                key: counts[key]
                for key in ("PASSED", "FAILED", "BLOCKED", "NOT_RUN", "QUARANTINED", "INVALID")
            },
            "severity_totals": dict(severity_totals),
            "severity_passed": dict(severity_passed),
            "severity_pass_rates": severity_rates,
            "overall_pass_rate": overall_pass_rate,
            "executed_batch_test_skills": executed_batch_skills,
            "critical_high_evidence_completeness": high_critical_evidence_rate,
            "overall_evidence_completeness": overall_evidence_rate,
            "flaky_rate": flaky_rate,
            "quarantined_rate": quarantined_rate,
        },
        "anti_fraud_signals": anti_fraud_signals,
        "blocker_count": len(blockers),
        "blockers": blockers,
        "control_manifest_digest": (
            "sha256:" + sha256_file(root / "control-manifest.json")
            if (root / "control-manifest.json").is_file()
            else None
        ),
        "result_catalog_digest": (
            "sha256:" + sha256_file(root / "results/catalog.json")
            if (root / "results/catalog.json").is_file()
            else None
        ),
    }
    gate["gate_digest"] = "sha256:" + sha256_json(gate)
    (root / "release-gate.json").write_text(
        json.dumps(gate, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(gate, ensure_ascii=False, indent=2))
    return 0 if decision == "READY_FOR_EXTERNAL_GATE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
