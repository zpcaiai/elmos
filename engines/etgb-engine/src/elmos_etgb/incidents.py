"""Append-only incident-to-regression materialization."""

from __future__ import annotations

from typing import Any, Mapping

from .canonical import digest_json


def regression_from_incident(incident: Mapping[str, Any]) -> dict[str, Any]:
    required = ("incident_id", "summary", "business_line", "failure_class")
    missing = [key for key in required if not incident.get(key)]
    if missing:
        raise ValueError("incident is missing: " + ", ".join(missing))
    material = {
        "incident_id": str(incident["incident_id"]),
        "summary": str(incident["summary"]),
        "business_line": str(incident["business_line"]),
        "failure_class": str(incident["failure_class"]),
        "case_inputs": dict(incident.get("case_inputs", {})),
        "expected_invariants": list(incident.get("expected_invariants", [])),
        "source_refs": list(incident.get("source_refs", [])),
        "hidden": bool(incident.get("hidden", True)),
        "priority": str(incident.get("priority", "P0")),
    }
    regression_id = "INC-REG-" + digest_json(material)[7:23]
    return {"schema_version": "1.1", "regression_id": regression_id, "incident_id": material["incident_id"], "case": material, "planner_tags": ["incident-regression", material["failure_class"]], "source_digest": digest_json(material), "status": "MATERIALIZED_FOR_REVIEW", "publication_status": "NOT_RUN"}
