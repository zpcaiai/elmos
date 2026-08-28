from __future__ import annotations

import datetime as dt
import json
import operator
from pathlib import Path
from typing import Any, Callable

import yaml


OPERATORS: dict[str, Callable[[Any, Any], bool]] = {
    "==": operator.eq,
    "!=": operator.ne,
    ">=": operator.ge,
    "<=": operator.le,
    ">": operator.gt,
    "<": operator.lt,
}

NON_WAIVABLE_GATES = {
    "G-P0-PASS",
    "G-P0-SSER",
    "G-DATA",
    "G-SEC",
    "G-TX",
    "G-AUTHORITY",
    "G-EVIDENCE-INTEGRITY",
    "G-FEATURE-COVERAGE",
    "G-UNDECLARED-FEATURE",
    "G-ADAPTER-AVAILABLE",
    "G-UNAVAILABLE-CASES",
    "G-TENANT-ISOLATION",
    "G-FINANCIAL-RECONCILIATION",
    "G-DUPLICATE-CHARGE",
    "G-HIDDEN-AUTHORITY",
    "G-STALE-EVIDENCE",
}


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
            active[gate_id] = waiver
    return active


def evaluate_gates(
    metrics: dict[str, Any],
    gate_config: dict[str, Any],
    *,
    waivers: list[dict[str, Any]] | None = None,
    run_complete: bool = True,
) -> dict[str, Any]:
    active_waivers = _active_waivers(waivers)
    results: list[dict[str, Any]] = []
    blocked = False
    rejected = False
    waived_failure = False
    for gate in gate_config.get("gates", []):
        gate_id = gate["id"]
        metric_name = gate["metric"]
        actual = metrics.get(metric_name)
        expected = gate["threshold"]
        op_text = gate["operator"]
        if op_text not in OPERATORS:
            results.append({**gate, "state": "ERROR", "actual": actual, "reason": "unsupported operator"})
            blocked = True
            continue
        if actual is None:
            results.append({**gate, "state": "BLOCKED", "actual": None, "reason": "metric unavailable"})
            blocked = True
            continue
        passed = OPERATORS[op_text](actual, expected)
        if passed:
            results.append({**gate, "state": "PASS", "actual": actual})
            continue
        waiver = active_waivers.get(gate_id)
        if waiver is not None and gate_id not in NON_WAIVABLE_GATES:
            results.append({**gate, "state": "WAIVED", "actual": actual, "waiver": waiver})
            waived_failure = True
        else:
            results.append({**gate, "state": "FAIL", "actual": actual})
            rejected = True

    if not run_complete:
        blocked = True
    if rejected:
        decision = "REJECT"
    elif blocked:
        decision = "BLOCKED"
    elif waived_failure:
        decision = "PROMOTE_WITH_WAIVER"
    else:
        decision = "PROMOTE"
    return {
        "schema_version": "1.1",
        "decision": decision,
        "run_complete": run_complete,
        "evaluated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "gate_results": results,
        "summary": {
            "passed": sum(1 for x in results if x["state"] == "PASS"),
            "failed": sum(1 for x in results if x["state"] == "FAIL"),
            "blocked": sum(1 for x in results if x["state"] in {"BLOCKED", "ERROR"}),
            "waived": sum(1 for x in results if x["state"] == "WAIVED"),
        },
    }


def evaluate_gate_files(
    score_path: Path,
    gate_path: Path,
    *,
    waivers_path: Path | None = None,
    run_complete: bool | None = None,
) -> dict[str, Any]:
    score = json.loads(Path(score_path).read_text(encoding="utf-8"))
    gates = yaml.safe_load(Path(gate_path).read_text(encoding="utf-8"))
    waivers: list[dict[str, Any]] | None = None
    if waivers_path:
        payload = yaml.safe_load(Path(waivers_path).read_text(encoding="utf-8"))
        waivers = payload.get("waivers", payload if isinstance(payload, list) else [])
    complete = not bool(score.get("partial_run")) if run_complete is None else run_complete
    return evaluate_gates(score.get("metrics", score), gates, waivers=waivers, run_complete=complete)
