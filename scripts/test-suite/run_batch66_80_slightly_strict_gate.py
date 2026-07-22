#!/usr/bin/env python3
"""Run the conservative repository gate for the Batch 66-80 450-case suite."""

from __future__ import annotations

import argparse
import importlib.util
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SUITE = ROOT / "test-suites" / "batch66-80-slightly-strict"
VALIDATOR_PATH = Path(__file__).with_name("validate_batch66_80_slightly_strict.py")


def load_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("batch66_80_rich_validator", VALIDATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load validator: {VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rate(counter: Counter[str]) -> float:
    total = sum(counter.values())
    return counter["passed"] / total if total else 0.0


def evaluate(suite: Path) -> tuple[dict[str, Any], int]:
    validator = load_validator()
    validation_errors, metrics = validator.validate_suite(suite)
    catalog = load_json(suite / "cases" / "catalog.json").get("cases", [])
    results = {
        path.stem: load_json(path) for path in sorted((suite / "results").glob("*.json"))
    }
    overall: Counter[str] = Counter()
    by_priority: dict[str, Counter[str]] = {
        priority: Counter() for priority in ("P0", "P1", "P2")
    }
    zero_tolerance_nonpass: list[str] = []
    for case in catalog:
        status = results.get(case.get("case_id"), {}).get("status", "not-run")
        overall[status] += 1
        priority = case.get("priority")
        if priority in by_priority:
            by_priority[priority][status] += 1
        if case.get("zero_tolerance") is True and status != "passed":
            zero_tolerance_nonpass.append(case.get("case_id", "unknown"))

    priority_rates = {priority: rate(counts) for priority, counts in by_priority.items()}
    flaky_rate = overall["flaky"] / len(catalog) if catalog else 1.0
    blockers = [f"validation: {error}" for error in validation_errors]
    if len(catalog) != 450 or len(results) != 450:
        blockers.append(f"exact result completeness unmet: {len(results)}/450")
    for status in ("not-run", "failed", "blocked", "skipped", "flaky"):
        if overall[status]:
            blockers.append(f"required cases are {status}: {overall[status]}")
    if zero_tolerance_nonpass:
        blockers.append(f"zero-tolerance cases are not passed: {len(zero_tolerance_nonpass)}")
    if priority_rates["P0"] < 1.0:
        blockers.append(f"P0 pass rate {priority_rates['P0']:.4f} is below 1.0000")
    if priority_rates["P1"] < 0.98:
        blockers.append(f"P1 pass rate {priority_rates['P1']:.4f} is below 0.9800")
    if priority_rates["P2"] < 0.95:
        blockers.append(f"P2 pass rate {priority_rates['P2']:.4f} is below 0.9500")
    if flaky_rate > 0.01:
        blockers.append(f"flaky rate {flaky_rate:.4f} exceeds 0.0100")
    if overall["waived"]:
        blockers.append(
            f"repository external gate does not resolve waived cases: {overall['waived']}"
        )

    all_not_run = len(catalog) == 450 and overall["not-run"] == 450
    if all_not_run:
        source_gate_status = "NOT_RUN"
    elif blockers:
        source_gate_status = "BLOCKED"
    elif overall["waived"]:
        source_gate_status = "CONDITIONAL"
    else:
        source_gate_status = "PASS"
    decision = "READY_FOR_EXTERNAL_GATE" if source_gate_status == "PASS" else "BLOCKED"
    report = {
        "schema_version": "1.0",
        "suite_id": "batch66-80-slightly-strict",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "source_gate_status": source_gate_status,
        "decision": decision,
        "maximum_success_decision": "READY_FOR_EXTERNAL_GATE",
        "certified": False,
        "updates_batch1_37_certification": False,
        "approves_production_or_provider_operation": False,
        "metrics": {
            **metrics,
            "status_counts": dict(sorted(overall.items())),
            "priority_pass_rates": priority_rates,
            "flaky_rate": flaky_rate,
            "zero_tolerance_nonpass": len(zero_tolerance_nonpass),
        },
        "blockers": blockers[:250],
    }
    return report, 0 if decision == "READY_FOR_EXTERNAL_GATE" else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("suite", nargs="?", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report, exit_code = evaluate(args.suite.resolve())
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.report:
        destination = args.report.resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
