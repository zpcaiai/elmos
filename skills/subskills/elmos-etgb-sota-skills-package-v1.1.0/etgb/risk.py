from __future__ import annotations

import hashlib
import json
import random
from collections import Counter, defaultdict
from typing import Any, Iterable


PRIORITY_SCORE = {"P0": 100.0, "P1": 45.0, "P2": 15.0}
LEVEL_SCORE = {"L0": 5.0, "L1": 10.0, "L2": 20.0, "L3": 35.0, "L4": 50.0}


def case_risk_score(
    case: dict[str, Any],
    *,
    affected_lines: set[str],
    historical_failures: Counter[str],
    model_uncertainty: dict[str, float] | None = None,
    coverage_gaps: set[str] | None = None,
) -> tuple[float, list[str]]:
    model_uncertainty = model_uncertainty or {}
    coverage_gaps = coverage_gaps or set()
    capability = case.get("coverage", {}).get("capability_id", "")
    score = PRIORITY_SCORE.get(case.get("priority", "P2"), 10.0) + LEVEL_SCORE.get(case.get("level", "L0"), 0.0)
    reasons = [f"priority:{case.get('priority')}", f"level:{case.get('level')}"]
    if case.get("business_line") in affected_lines:
        score += 80.0
        reasons.append("changed-business-line")
    failure_count = historical_failures.get(capability, 0) + historical_failures.get(case.get("id", ""), 0)
    if failure_count:
        score += min(80.0, 15.0 * failure_count)
        reasons.append(f"historical-failures:{failure_count}")
    uncertainty = float(model_uncertainty.get(capability, model_uncertainty.get(case.get("id", ""), 0.0)))
    if uncertainty > 0:
        score += 60.0 * min(1.0, uncertainty)
        reasons.append(f"model-uncertainty:{uncertainty:.3f}")
    if capability in coverage_gaps:
        score += 70.0
        reasons.append("coverage-gap")
    if "security" in case.get("family", "") or "security" in case.get("tags", []):
        score += 20.0
        reasons.append("security-sensitive")
    if "transaction" in case.get("family", "") or "concurrency" in case.get("tags", []):
        score += 15.0
        reasons.append("stateful-high-risk")
    return score, reasons


def select_risk_plan(
    cases: Iterable[dict[str, Any]],
    *,
    affected_lines: set[str],
    historical_results: Iterable[dict[str, Any]] = (),
    model_uncertainty: dict[str, float] | None = None,
    coverage_gaps: set[str] | None = None,
    max_cases: int | None = None,
    control_fraction: float = 0.05,
    seed: int = 17,
) -> dict[str, Any]:
    rows = list(cases)
    historical_failures: Counter[str] = Counter()
    for result in historical_results:
        if result.get("status") == "passed":
            continue
        historical_failures[result.get("case_id", "")] += 1
        capability = result.get("capability_id") or result.get("coverage", {}).get("capability_id")
        if capability:
            historical_failures[capability] += 1

    scored: list[dict[str, Any]] = []
    mandatory: set[str] = set()
    for case in rows:
        score, reasons = case_risk_score(
            case,
            affected_lines=affected_lines,
            historical_failures=historical_failures,
            model_uncertainty=model_uncertainty,
            coverage_gaps=coverage_gaps,
        )
        if "smoke" in case.get("profiles", []):
            mandatory.add(case["id"])
            reasons.append("mandatory-smoke")
        if case.get("priority") == "P0" and case.get("business_line") in affected_lines and "pr" in case.get("profiles", []):
            mandatory.add(case["id"])
            reasons.append("mandatory-affected-p0")
        scored.append({"case": case, "score": score, "reasons": reasons})

    scored.sort(key=lambda item: (-item["score"], item["case"]["id"]))
    selected: list[dict[str, Any]] = [item for item in scored if item["case"]["id"] in mandatory]
    selected_ids = {item["case"]["id"] for item in selected}
    remaining_capacity = None if max_cases is None else max(0, max_cases - len(selected))
    ranked_remaining = [item for item in scored if item["case"]["id"] not in selected_ids]
    if remaining_capacity is None:
        selected.extend(ranked_remaining)
    else:
        risk_slots = max(0, remaining_capacity - max(1, int(remaining_capacity * control_fraction))) if remaining_capacity else 0
        selected.extend(ranked_remaining[:risk_slots])
        selected_ids = {item["case"]["id"] for item in selected}
        control_pool = [item for item in rows if item["id"] not in selected_ids and item.get("business_line") not in affected_lines]
        rng = random.Random(seed)
        rng.shuffle(control_pool)
        control_slots = max(0, max_cases - len(selected))
        for case in sorted(control_pool[:control_slots], key=lambda x: x["id"]):
            selected.append({"case": case, "score": 0.0, "reasons": ["random-unaffected-control"]})

    selections = [
        {
            "case_id": item["case"]["id"],
            "business_line": item["case"]["business_line"],
            "risk_score": round(item["score"], 3),
            "reasons": item["reasons"],
        }
        for item in selected
    ]
    material = {
        "seed": seed,
        "affected_lines": sorted(affected_lines),
        "selections": selections,
    }
    plan_digest = "sha256:" + hashlib.sha256(
        json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": "1.1",
        "selection_policy": "risk-impact-history-uncertainty-control-v1",
        "seed": seed,
        "affected_business_lines": sorted(affected_lines),
        "case_ids": [row["case_id"] for row in selections],
        "selections": selections,
        "plan_digest": plan_digest,
    }
