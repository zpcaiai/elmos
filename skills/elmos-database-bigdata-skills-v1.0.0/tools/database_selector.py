#!/usr/bin/env python3
"""Conservative role-based database and data-technology selector for Elmos.

The static capability catalog is only a seed. Production selection must still be
backed by project-specific version checks, representative benchmarks, recovery
tests, security validation, capacity estimates, and an Architecture Decision
Record (ADR).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "catalog" / "database-capabilities.json"

ROLE_FILTERS = {
    "system-of-record": {"database", "distributed-sql", "document-database", "time-series-relational"},
    "cache": {"key-value"},
    "search": {"search-engine"},
    "vector-search": {"vector-database", "vector-extension", "search-engine"},
    "graph-serving": {"graph-database"},
    "time-series": {"time-series", "time-series-relational", "wide-column", "olap-database"},
    "event-backbone": {"event-streaming"},
    "stream-processing": {"processing-engine"},
    "batch-processing": {"processing-engine"},
    "lakehouse": {"table-format"},
    "federated-query": {"query-engine"},
    "real-time-analytics": {"olap-database"},
    "local-analytics": {"embedded-olap"},
}

ROLE_WEIGHTS = {
    "system-of-record": {
        "transactions": .22, "read_latency": .13, "write_throughput": .13,
        "horizontal_scale": .10, "cost_efficiency": .12,
        "operational_simplicity": .15, "ecosystem": .08, "model_fit": .07,
    },
    "cache": {"read_latency": .35, "write_throughput": .25, "horizontal_scale": .15,
              "operational_simplicity": .15, "cost_efficiency": .10},
    "search": {"full_text": .40, "read_latency": .18, "horizontal_scale": .16,
               "write_throughput": .10, "operational_simplicity": .08, "cost_efficiency": .08},
    "vector-search": {"vector": .40, "read_latency": .18, "horizontal_scale": .15,
                      "write_throughput": .10, "operational_simplicity": .10, "cost_efficiency": .07},
    "graph-serving": {"graph": .48, "read_latency": .18, "transactions": .10,
                      "horizontal_scale": .08, "operational_simplicity": .08, "cost_efficiency": .08},
    "time-series": {"time_series": .35, "write_throughput": .20, "read_latency": .13,
                    "horizontal_scale": .12, "analytical_scan": .08,
                    "operational_simplicity": .06, "cost_efficiency": .06},
    "event-backbone": {"real_time_ingest": .28, "write_throughput": .24, "horizontal_scale": .18,
                       "transactions": .10, "operational_simplicity": .10, "cost_efficiency": .10},
    "stream-processing": {"real_time_ingest": .25, "write_throughput": .18, "horizontal_scale": .17,
                          "time_series": .10, "lakehouse": .10,
                          "operational_simplicity": .10, "cost_efficiency": .10},
    "batch-processing": {"analytical_scan": .30, "horizontal_scale": .20, "lakehouse": .15,
                         "write_throughput": .10, "operational_simplicity": .10,
                         "cost_efficiency": .10, "ecosystem": .05},
    "lakehouse": {"lakehouse": .38, "analytical_scan": .20, "federation": .12,
                  "write_throughput": .08, "transactions": .07,
                  "operational_simplicity": .07, "cost_efficiency": .08},
    "federated-query": {"federation": .42, "analytical_scan": .22, "horizontal_scale": .12,
                        "operational_simplicity": .12, "cost_efficiency": .12},
    "real-time-analytics": {"analytical_scan": .22, "real_time_ingest": .20, "read_latency": .20,
                            "horizontal_scale": .12, "lakehouse": .08,
                            "operational_simplicity": .08, "cost_efficiency": .10},
    "local-analytics": {"analytical_scan": .40, "read_latency": .20,
                        "operational_simplicity": .25, "cost_efficiency": .15},
}


def load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot read JSON {path}: {exc}") from exc


def infer_roles(req: Dict[str, Any]) -> List[str]:
    """Infer independently selectable persistence and processing roles."""
    roles: List[str] = []
    types = {str(x).lower() for x in req.get("project_types", [])}
    dc = req.get("data_characteristics", {})
    slo = req.get("slo", {})
    variety = {str(x).lower() for x in dc.get("variety", [])}
    sources = req.get("sources", [])
    consumers = req.get("consumers", [])
    constraints = req.get("constraints", {})
    must = {str(x).lower() for x in constraints.get("must_have", [])}

    transactional = any(x in types for x in {"oltp", "application", "realtime-user-profile", "fraud-risk"})
    explicit_system_of_record = "system-of-record" in must
    if transactional or explicit_system_of_record:
        roles.append("system-of-record")

    if "vector" in variety or any("vector" in x or "rag" in x or "knowledge" in x for x in types):
        roles.append("vector-search")
    if "graph" in variety or any("graph" in x or "fraud" in x for x in types):
        roles.append("graph-serving")
    if "time-series" in variety or any(x in types for x in {"iot", "iot-timeseries", "observability"}):
        roles.append("time-series")
    if any("search" in str(c.get("query_pattern", "")).lower() for c in consumers):
        roles.append("search")

    peak_eps = dc.get("peak_events_per_second") or 0
    freshness = slo.get("freshness_ms")
    realtime = (freshness is not None and freshness <= 60_000) or peak_eps >= 100 or any(
        x in types for x in {"realtime-analytics", "realtime-user-profile", "fraud-risk", "iot-timeseries", "observability"}
    )
    if realtime or any(s.get("change_mode") in {"cdc", "stream"} for s in sources):
        roles += ["event-backbone", "stream-processing", "real-time-analytics"]

    volume = dc.get("volume_tb") or 0
    retention = dc.get("retention_days") or 0
    historical = volume >= 0.5 or retention >= 30 or any(
        x in types for x in {"offline-warehouse", "lakehouse", "recommendation", "vector-knowledge"}
    )
    if historical:
        roles += ["lakehouse", "batch-processing", "federated-query"]

    if slo.get("p95_read_ms") is not None and slo["p95_read_ms"] <= 10:
        roles.append("cache")
    if "federated-query" in must or len({s.get("kind") for s in sources}) >= 4:
        roles.append("federated-query")
    if not roles:
        roles = ["system-of-record", "local-analytics"]

    return list(dict.fromkeys(roles))


def deployment_compatible(technology: Dict[str, Any], req: Dict[str, Any]) -> bool:
    requested = set(req.get("constraints", {}).get("deployment", [])) - {"unknown"}
    if not requested:
        return True
    available = set(technology.get("deployments", []))
    return bool(requested & available)


def hard_rejection(technology: Dict[str, Any], role: str, req: Dict[str, Any]) -> List[str]:
    """Return hard-constraint failures. Soft preferences never enter this function."""
    reasons: List[str] = []
    forbidden = {str(x).lower() for x in req.get("constraints", {}).get("forbidden", [])}
    if technology["id"].lower() in forbidden or technology["name"].lower() in forbidden:
        reasons.append("explicitly forbidden")
    if not deployment_compatible(technology, req):
        reasons.append("deployment model incompatible")

    flags = technology.get("hard_flags", {})
    consistency = req.get("consistency", {})
    if role == "system-of-record":
        if consistency.get("model") == "strong" and not flags.get("strong_consistency", False):
            reasons.append("strong consistency required")
        if consistency.get("transactions") in {"single-database", "cross-aggregate"} and not flags.get("multi_row_transactions", False):
            reasons.append("multi-row transactions required")

    must = {str(x).lower() for x in req.get("constraints", {}).get("must_have", [])}
    if "open-source" in must and not technology.get("open_source", False):
        reasons.append("open-source is mandatory")
    if "on-prem" in must and "on-prem" not in technology.get("deployments", []):
        reasons.append("on-prem is mandatory")
    return reasons


def model_fit(technology: Dict[str, Any], req: Dict[str, Any], role: str) -> float:
    variety = set(req.get("data_characteristics", {}).get("variety", []))
    models = set(technology.get("data_models", []))
    score_value = 2.5
    mapping = {
        "vector-search": {"vector"},
        "graph-serving": {"property-graph", "graph"},
        "time-series": {"time-series"},
        "real-time-analytics": {"columnar-olap", "olap"},
        "lakehouse": {"columnar-table", "table-format"},
        "system-of-record": {"relational", "document"},
    }
    wanted = mapping.get(role, set())
    if wanted & models:
        score_value = 5.0
    elif variety & models:
        score_value = 4.0
    return score_value


def score(technology: Dict[str, Any], role: str, req: Dict[str, Any]) -> Tuple[float, Dict[str, float], List[str]]:
    raw = technology.get("heuristic_scores_0_to_5", {})
    weights = ROLE_WEIGHTS[role]
    components: Dict[str, float] = {}
    notes: List[str] = []
    total = 0.0
    for metric, weight in weights.items():
        if metric == "operational_simplicity":
            value = 5.0 - float(raw.get("operational_complexity", 3))
        elif metric == "ecosystem":
            value = 3.0  # must be replaced by versioned project evidence when material
        elif metric == "model_fit":
            value = model_fit(technology, req, role)
        else:
            value = float(raw.get(metric, 0))
        components[metric] = round(value, 3)
        total += weight * value

    constraints = req.get("constraints", {})
    operations_maturity = constraints.get("operations_maturity", "unknown")
    complexity = float(raw.get("operational_complexity", 3))
    if operations_maturity == "low" and complexity > 2:
        penalty = min(0.8, 0.2 * (complexity - 2))
        total -= penalty
        notes.append(f"low operations maturity complexity penalty: -{penalty:.2f}")
    elif operations_maturity == "medium" and complexity > 4:
        total -= 0.15
        notes.append("medium operations maturity complexity penalty: -0.15")

    if constraints.get("preferred_open_source") is True and technology.get("open_source", False):
        total += 0.05
        notes.append("open-source preference bonus: +0.05")
    if technology.get("adapter_status") == "catalog-only":
        total -= 0.15
        notes.append("unverified adapter penalty: -0.15")

    return round(max(0.0, min(5.0, total)), 4), components, notes


def role_constraints(role: str, req: Dict[str, Any]) -> List[str]:
    constraints = [str(x) for x in req.get("constraints", {}).get("must_have", [])]
    if role == "system-of-record":
        consistency = req.get("consistency", {})
        if consistency.get("model"):
            constraints.append(f"consistency={consistency['model']}")
        if consistency.get("transactions"):
            constraints.append(f"transactions={consistency['transactions']}")
    return list(dict.fromkeys(constraints))


def select(req: Dict[str, Any], registry: Dict[str, Any], top_n: int) -> Dict[str, Any]:
    roles = infer_roles(req)
    technologies = registry.get("technologies", [])
    role_results: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []

    for role in roles:
        kinds = ROLE_FILTERS[role]
        candidates = [t for t in technologies if t.get("technology_kind") in kinds]
        ranked: List[Dict[str, Any]] = []
        for technology in candidates:
            reasons = hard_rejection(technology, role, req)
            if reasons:
                rejected.append({
                    "role": role,
                    "technology": technology["id"],
                    "reason": "; ".join(reasons),
                    "constraint": reasons[0] if reasons else None,
                })
                continue
            score_value, components, notes = score(technology, role, req)
            ranked.append({
                "technology": technology["id"],
                "name": technology["name"],
                "score_0_to_5": score_value,
                "components_0_to_5": components,
                "adjustments": notes,
                "adapter_status": technology.get("adapter_status"),
                "best_for": technology.get("best_for", []),
                "avoid_for": technology.get("avoid_for", []),
                "official_evidence": technology.get("official_docs"),
            })
        ranked.sort(key=lambda item: (-item["score_0_to_5"], item["technology"]))
        top = ranked[:top_n]
        selected = [top[0]["technology"]] if top else []
        alternatives = [item["technology"] for item in top[1:]]
        rationale = []
        if top:
            rationale.append(
                f"{top[0]['technology']} has the highest seed score ({top[0]['score_0_to_5']}/5) after hard constraints and declared adjustments."
            )
            rationale.append("Selection is provisional until representative benchmark, TCO, recovery and security evidence pass.")
        else:
            rationale.append("No candidate survived the declared hard constraints; requirements must not be silently relaxed.")
        role_results.append({
            "role": role,
            "selected": selected,
            "alternatives": alternatives,
            "rationale": rationale,
            "constraints": role_constraints(role, req),
            "top_candidates": top,
            "candidate_count": len(ranked),
        })

    confidence = 0.55
    if role_results and all(item["candidate_count"] >= 2 for item in role_results):
        confidence += 0.10
    if any(not item["selected"] for item in role_results):
        confidence -= 0.25
    if req.get("assumptions"):
        confidence -= min(0.20, 0.02 * len(req["assumptions"]))

    project_id = str(req.get("project_id") or "unknown-project")
    registry_version = str(registry.get("registry_version") or "unknown")
    generated_at = str(registry.get("generated_at") or "unknown")
    return {
        "decision_id": f"database-decision:{project_id}:1.0.0",
        "selector_version": "1.0.0",
        "project_id": project_id,
        "roles": role_results,
        "rejected": rejected,
        "confidence": round(max(0.10, min(0.85, confidence)), 2),
        "evidence": [
            {
                "kind": "capability-registry",
                "reference": f"catalog/database-capabilities.json#{registry_version}",
                "as_of": generated_at,
            },
            {
                "kind": "project-requirement",
                "reference": f"project_id:{project_id}",
                "as_of": generated_at,
            },
        ],
        "sensitivity": {
            "status": "not-run-by-reference-selector",
            "required_next": "Run representative benchmark and weight perturbation before production certification.",
        },
        "assumptions": [str(item.get("statement")) for item in req.get("assumptions", []) if item.get("statement")],
        "warnings": [
            "Scores are heuristic seeds, not production benchmarks.",
            "A selected portfolio still needs a complexity penalty review, representative benchmark, cost model and ADR.",
            "A technology appearing in the catalog does not prove an executable provider integration.",
            "Derived stores require one authoritative source, idempotent synchronization, deletion propagation and rebuild procedures.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("requirements", type=Path)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    req = load_json(args.requirements)
    registry = load_json(args.registry)
    result = select(req, registry, max(1, args.top_n))
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
