#!/usr/bin/env python3
"""Parametric system-runtime, human-equivalent and token-cost estimator."""
from __future__ import annotations
import argparse, json, math, sys
from pathlib import Path
from typing import Any, Dict

def load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))

def estimate(req: Dict[str, Any], in_price: float | None, out_price: float | None, currency: str) -> Dict[str, Any]:
    dc = req.get("data_characteristics", {})
    security = req.get("security", {})
    constraints = req.get("constraints", {})
    sources = max(1, len(req.get("sources", [])))
    consumers = max(1, len(req.get("consumers", [])))
    types = max(1, len(req.get("project_types", [])))
    volume = dc.get("volume_tb") or 0
    peak = dc.get("peak_events_per_second") or 0
    complexity = (
        1.0 + 0.22 * sources + 0.12 * consumers + 0.25 * types
        + 0.25 * math.log10(1 + volume)
        + 0.18 * math.log10(1 + peak)
        + (0.35 if security.get("contains_pii") else 0)
        + (0.35 if security.get("tenant_isolation") not in {None,"unknown","shared-row"} else 0)
        + (0.25 if len(constraints.get("deployment", [])) > 1 else 0)
    )
    system_likely_hours = 1.4 * complexity
    human_likely_hours = 44 * complexity
    input_tokens = int(180_000 * complexity)
    output_tokens = int(95_000 * complexity)
    if in_price is not None and out_price is not None:
        likely_cost = input_tokens / 1_000_000 * in_price + output_tokens / 1_000_000 * out_price
        amount = {"min":round(likely_cost * .7,2),"max":round(likely_cost * 1.5,2)}
        cur = currency
    else:
        amount = {"min":0.0,"max":0.0}
        cur = "UNPRICED"
    return {
        "system_autonomous_runtime":{"min":round(system_likely_hours*.55,2),"likely":round(system_likely_hours,2),"max":round(system_likely_hours*2.0,2),"unit":"hours"},
        "human_equivalent_effort":{"min":round(human_likely_hours*.65,1),"likely":round(human_likely_hours,1),"max":round(human_likely_hours*1.7,1),"unit":"person-hours"},
        "human_in_the_loop_delay":{"min":0.0,"likely":0.0,"max":0.0,"unit":"hours"},
        "estimated_token_cost":{"input_tokens":input_tokens,"output_tokens":output_tokens,"currency":cur,"amount_range":amount},
        "assumptions":[
            "System runtime is autonomous machine wall-clock time, not person-days.",
            "Human-equivalent effort is a comparison baseline and is not added to system runtime.",
            "HITL delay is zero unless the generated plan inserts approvals or waits for external systems.",
            "Token price is unpriced unless command-line model prices are supplied.",
            "Repository size, external service provisioning, benchmark duration and test failures can materially change the range."
        ],
        "confidence":0.42,
        "as_of":"2026-08-19"
    }

def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("requirements",type=Path)
    p.add_argument("--input-price-per-million",type=float)
    p.add_argument("--output-price-per-million",type=float)
    p.add_argument("--currency",default="USD")
    p.add_argument("--output",type=Path)
    a=p.parse_args()
    result=estimate(load(a.requirements),a.input_price_per_million,a.output_price_per_million,a.currency)
    text=json.dumps(result,ensure_ascii=False,indent=2)
    if a.output: a.output.write_text(text+"\n",encoding="utf-8")
    else: print(text)
    return 0

if __name__=="__main__":
    sys.exit(main())
