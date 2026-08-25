#!/usr/bin/env python3
"""Reference architecture-pattern selector for Elmos big-data projects."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

def load(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot read {path}: {exc}") from exc

def choose(req: Dict[str, Any]) -> Dict[str, Any]:
    types = {str(x).lower() for x in req.get("project_types", [])}
    dc = req.get("data_characteristics", {})
    slo = req.get("slo", {})
    constraints = req.get("constraints", {})
    must = {str(x).lower() for x in constraints.get("must_have", [])}
    sources = req.get("sources", [])

    freshness = slo.get("freshness_ms")
    peak = dc.get("peak_events_per_second") or 0
    volume = dc.get("volume_tb") or 0
    retention = dc.get("retention_days") or 0
    variety = set(dc.get("variety", []))
    realtime = (freshness is not None and freshness <= 60_000) or peak >= 100 or any(
        x in types for x in {"realtime-analytics","realtime-user-profile","fraud-risk","iot-timeseries","observability"}
    )
    batch = (freshness is None or freshness >= 300_000) or any(
        x in types for x in {"offline-warehouse","recommendation","migration","lakehouse"}
    )
    replayable = any(s.get("change_mode") in {"cdc","stream"} for s in sources)
    historical = volume >= 0.5 or retention >= 30 or "unstructured" in variety
    multi_source = len(sources) >= 4
    strict_reconciliation = any(x in must for x in {"strict-reconciliation","regulatory-batch-baseline"})
    separate_semantics = any(x in must for x in {"separate-batch-speed-logic","lambda"})

    rationale: List[str] = []
    risks: List[str] = []
    validation: List[str] = []
    secondary: List[str] = []
    overlays: List[str] = []

    if realtime and batch:
        if separate_semantics or strict_reconciliation:
            primary = "lambda"
            rationale.append("Both realtime and historical paths are required and requirements explicitly justify separate semantics.")
            risks += ["duplicate business logic", "batch/speed inconsistency", "higher operations cost"]
            validation += ["batch-speed differential tests", "serving reconciliation"]
        else:
            primary = "unified-batch-stream"
            rationale.append("Both bounded and unbounded workloads exist without a proven need for duplicate business logic.")
            risks += ["runtime modes may still differ", "sink semantics must be validated"]
            validation += ["bounded/unbounded parity", "checkpoint and sink recovery"]
    elif realtime:
        if replayable:
            primary = "streaming-kappa"
            rationale.append("Realtime processing dominates and at least one durable replay-capable source is present.")
            validation += ["retention versus replay duration", "state recovery", "idempotent sinks"]
        else:
            primary = "unified-batch-stream"
            rationale.append("Realtime is required but replayability is not yet proven; a unified design with explicit recovery is safer than claiming Kappa.")
            risks.append("source replay gap")
            validation.append("establish durable replay source or snapshot+stream boundary")
    else:
        primary = "batch-warehouse"
        rationale.append("Historical/bounded processing dominates the declared freshness requirement.")
        validation += ["incremental/full equivalence", "batch SLA", "atomic commits"]

    if historical:
        secondary.append("lakehouse")
        rationale.append("Historical volume/retention/variety favors an open, governed lakehouse layer.")
        validation += ["table-format engine compatibility", "file layout and maintenance"]
    if multi_source or "federated-query" in must:
        secondary.append("federated-query")
        rationale.append("Multiple heterogeneous sources or an explicit federation requirement exists.")
        validation += ["connector pushdown", "source load and network cost"]
    if multi_source or "data-fabric" in must or any("governance" in x for x in types):
        overlays.append("data-fabric-overlay")
        rationale.append("Common metadata, policy, lineage, quality and discovery are needed across sources.")
    if "data-mesh" in must:
        overlays.append("data-mesh-operating-model")
        risks.append("domain ownership and platform maturity must be demonstrated")
        validation.append("data product ownership and federated governance readiness")
    if "htap" in must:
        secondary.append("htap")
        validation.append("workload isolation benchmark between OLTP and analytics")

    return {
        "selector_version":"1.0.0",
        "project_id":req.get("project_id"),
        "primary_pattern":primary,
        "secondary_patterns":list(dict.fromkeys(secondary)),
        "overlays":list(dict.fromkeys(overlays)),
        "rationale":rationale,
        "risks":risks,
        "validation":list(dict.fromkeys(validation)),
        "reconsider_when":[
            "freshness or throughput changes by more than 2x",
            "a source becomes non-replayable or retention is reduced",
            "team operations maturity or deployment policy changes",
            "representative benchmark contradicts the heuristic decision"
        ]
    }

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("requirements", type=Path)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    result = choose(load(args.requirements))
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0

if __name__ == "__main__":
    sys.exit(main())
