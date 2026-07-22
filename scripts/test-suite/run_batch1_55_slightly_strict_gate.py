#!/usr/bin/env python3
"""Fail-closed supplemental gate for the imported Batch 1-55 test designs."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from _common import sha256_file, sha256_json
from validate_batch1_55_slightly_strict import DEFAULT_SUITE, validate_suite


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("suite", nargs="?", type=Path, default=DEFAULT_SUITE)
    args = parser.parse_args()
    root = args.suite.resolve()
    errors, metrics = validate_suite(root)
    blockers = list(errors)
    try:
        suite = json.loads((root / "suite.json").read_text(encoding="utf-8"))
        results = json.loads((root / suite["result_catalog"]).read_text(encoding="utf-8"))
        cases = results["cases"]
    except Exception as exc:  # noqa: BLE001
        suite = {}
        cases = []
        blockers.append(f"cannot load gate inputs: {exc}")

    counts = Counter(result.get("status", "invalid") for result in cases if isinstance(result, dict))
    for result in cases:
        if not isinstance(result, dict):
            continue
        if result.get("status") in {"failed", "blocked", "not-run", "waived"}:
            blockers.append(f"{result.get('case_id')} is {result.get('status')}")
    uncovered = suite.get("uncovered_repository_namespaces", [])
    for namespace in uncovered:
        blockers.append(f"source package has no exact cases for {namespace}")

    p0_total = sum(result.get("priority") == "P0" for result in cases if isinstance(result, dict))
    p0_passed = sum(
        result.get("priority") == "P0" and result.get("status") == "passed"
        for result in cases
        if isinstance(result, dict)
    )
    p1_total = sum(result.get("priority") == "P1" for result in cases if isinstance(result, dict))
    p1_passed = sum(
        result.get("priority") == "P1" and result.get("status") == "passed"
        for result in cases
        if isinstance(result, dict)
    )
    if p0_passed != p0_total:
        blockers.append(f"P0 pass requirement unmet: {p0_passed}/{p0_total}")
    if p1_passed != p1_total:
        blockers.append(f"conservative P1 pass requirement unmet: {p1_passed}/{p1_total}")

    decision = "BLOCKED" if blockers else "READY_FOR_EXTERNAL_GATE"
    field_status = "NOT_RUN" if counts.get("not-run", 0) else "INCOMPLETE" if blockers else "READY"
    gate = {
        "gate_id": "batch1-55-slightly-strict-supplemental",
        "gate_version": 1,
        "decision": decision,
        "certification_authority": False,
        "maximum_success_decision": "READY_FOR_EXTERNAL_GATE",
        "evaluated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "field_evidence_status": field_status,
        "metrics": {
            **metrics,
            "status_counts": {key: counts.get(key, 0) for key in ("passed", "failed", "blocked", "not-run", "waived", "invalid")},
            "p0": {"total": p0_total, "passed": p0_passed},
            "p1": {"total": p1_total, "passed": p1_passed},
        },
        "uncovered_repository_namespaces": uncovered,
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
    gate["gate_digest"] = sha256_json(gate)
    (root / "release-gate.json").write_text(
        json.dumps(gate, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(gate, ensure_ascii=False, indent=2))
    return 0 if decision == "READY_FOR_EXTERNAL_GATE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
