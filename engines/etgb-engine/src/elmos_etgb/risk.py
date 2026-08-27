"""Deterministic risk-based selection with mandatory safety coverage."""

from __future__ import annotations

import random
from collections import Counter
from typing import Any, Iterable

from .canonical import digest_json


PRIORITY_SCORE = {"P0": 100.0, "P1": 45.0, "P2": 15.0}
LEVEL_SCORE = {"L0": 5.0, "L1": 10.0, "L2": 20.0, "L3": 35.0, "L4": 50.0}


def case_risk_score(case: dict[str, Any], *, affected_lines: set[str], historical_failures: Counter[str], model_uncertainty: dict[str, float] | None = None, coverage_gaps: set[str] | None = None) -> tuple[float, list[str]]:
    uncertainty = model_uncertainty or {}
    gaps = coverage_gaps or set()
    capability = str(case.get("coverage", {}).get("capability_id", ""))
    score = PRIORITY_SCORE.get(str(case.get("priority", "P2")), 10.0) + LEVEL_SCORE.get(str(case.get("level", "L0")), 0.0)
    reasons = [f"priority:{case.get('priority')}", f"level:{case.get('level')}"]
    if case.get("business_line") in affected_lines:
        score += 80.0; reasons.append("changed-business-line")
    failures = historical_failures.get(capability, 0) + historical_failures.get(str(case.get("id", "")), 0)
    if failures:
        score += min(80.0, 15.0 * failures); reasons.append(f"historical-failures:{failures}")
    confidence = float(uncertainty.get(capability, uncertainty.get(str(case.get("id", "")), 0.0)))
    if confidence > 0:
        score += 60.0 * min(1.0, confidence); reasons.append(f"model-uncertainty:{confidence:.3f}")
    if capability in gaps:
        score += 70.0; reasons.append("coverage-gap")
    if "security" in str(case.get("family", "")) or "security" in case.get("tags", []):
        score += 20.0; reasons.append("security-sensitive")
    if "transaction" in str(case.get("family", "")) or "concurrency" in case.get("tags", []):
        score += 15.0; reasons.append("stateful-high-risk")
    return score, reasons


def select_risk_plan(cases: Iterable[dict[str, Any]], *, affected_lines: set[str], historical_results: Iterable[dict[str, Any]] = (), model_uncertainty: dict[str, float] | None = None, coverage_gaps: set[str] | None = None, max_cases: int | None = None, control_fraction: float = 0.05, seed: int = 17) -> dict[str, Any]:
    rows = list(cases)
    failures: Counter[str] = Counter()
    for result in historical_results:
        if result.get("status") == "passed":
            continue
        failures[str(result.get("case_id", ""))] += 1
        capability = result.get("capability_id") or result.get("coverage", {}).get("capability_id")
        if capability:
            failures[str(capability)] += 1
    ranked: list[dict[str, Any]] = []
    mandatory: set[str] = set()
    for case in rows:
        score, reasons = case_risk_score(case, affected_lines=affected_lines, historical_failures=failures, model_uncertainty=model_uncertainty, coverage_gaps=coverage_gaps)
        if "smoke" in case.get("profiles", []):
            mandatory.add(str(case["id"])); reasons.append("mandatory-smoke")
        if case.get("priority") == "P0" and case.get("business_line") in affected_lines and "pr" in case.get("profiles", []):
            mandatory.add(str(case["id"])); reasons.append("mandatory-affected-p0")
        ranked.append({"case": case, "score": score, "reasons": reasons})
    ranked.sort(key=lambda item: (-item["score"], str(item["case"]["id"])))
    selected = [item for item in ranked if str(item["case"]["id"]) in mandatory]
    selected_ids = {str(item["case"]["id"]) for item in selected}
    remaining = [item for item in ranked if str(item["case"]["id"]) not in selected_ids]
    if max_cases is None:
        selected.extend(remaining)
    else:
        capacity = max(0, max_cases - len(selected))
        risk_slots = max(0, capacity - (max(1, int(capacity * control_fraction)) if capacity else 0))
        selected.extend(remaining[:risk_slots])
        selected_ids = {str(item["case"]["id"]) for item in selected}
        controls = [item for item in rows if str(item["id"]) not in selected_ids and item.get("business_line") not in affected_lines]
        rng = random.Random(seed); rng.shuffle(controls)
        for case in sorted(controls[:max(0, max_cases - len(selected))], key=lambda item: str(item["id"])):
            selected.append({"case": case, "score": 0.0, "reasons": ["random-unaffected-control"]})
    selections = [{"case_id": item["case"]["id"], "business_line": item["case"].get("business_line"), "risk_score": round(item["score"], 3), "reasons": item["reasons"]} for item in selected]
    material = {"seed": seed, "affected_lines": sorted(affected_lines), "selections": selections}
    return {"schema_version": "1.1", "selection_policy": "risk-impact-history-uncertainty-control-v1", "seed": seed, "affected_business_lines": sorted(affected_lines), "case_ids": [row["case_id"] for row in selections], "selections": selections, "plan_digest": digest_json(material)}
