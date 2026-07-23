#!/usr/bin/env python3
"""Validate the installed Product Convergence bundle against every Schema."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_ROOT = ROOT / "schemas" / "product-convergence"
EXPECTED_SCHEMA_FILES = {
    "benchmark-corpus.schema.json",
    "capability-package.schema.json",
    "capability-registry.schema.json",
    "dependency-graph.schema.json",
    "evidence-graph.schema.json",
    "handoff-package.schema.json",
    "policy-decision.schema.json",
    "project-lifecycle.schema.json",
    "readiness-gate.schema.json",
    "reference-route-plan.schema.json",
    "skill-registry.schema.json",
    "workflow-definition.schema.json",
}
INSTANCE_BY_SCHEMA = {
    "benchmark-corpus.schema.json": "benchmark-corpus.json",
    "capability-registry.schema.json": "capability-registry.json",
    "dependency-graph.schema.json": "dependency-graph.json",
    "evidence-graph.schema.json": "evidence-graph.json",
    "handoff-package.schema.json": "handoff-package.json",
    "policy-decision.schema.json": "policy-sample.json",
    "project-lifecycle.schema.json": "project-lifecycle.json",
    "readiness-gate.schema.json": "readiness-gate.json",
    "reference-route-plan.schema.json": "reference-route-plan.json",
    "skill-registry.schema.json": "skill-registry.json",
    "workflow-definition.schema.json": "workflow-definition.json",
}
EXPECTED_SKILL_IDS = [f"CONV-{number:03d}" for number in range(1, 33)]
EXPECTED_CRITERIA = {
    "unified_core",
    "private_runner",
    "reference_engine",
    "reference_route",
    "validation_lab",
    "maintainability",
    "customer_handoff",
    "unit_economics",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(bundle: Path) -> dict[str, Any]:
    schema_files = {path.name for path in SCHEMA_ROOT.glob("*.json")}
    if schema_files != EXPECTED_SCHEMA_FILES:
        raise ValueError(
            f"expected exact 12-Schema set; missing={sorted(EXPECTED_SCHEMA_FILES-schema_files)} "
            f"extra={sorted(schema_files-EXPECTED_SCHEMA_FILES)}"
        )
    for schema_name in sorted(EXPECTED_SCHEMA_FILES):
        schema = load_json(SCHEMA_ROOT / schema_name)
        Draft202012Validator.check_schema(schema)
        instance_name = INSTANCE_BY_SCHEMA.get(schema_name)
        if instance_name:
            Draft202012Validator(schema).validate(load_json(bundle / instance_name))

    registry = load_json(bundle / "skill-registry.json")
    skills = registry["skills"]
    if [skill.get("skill_id") for skill in skills] != EXPECTED_SKILL_IDS:
        raise ValueError("Skill registry IDs must be exactly CONV-001 through CONV-032")
    names: set[str] = set()
    for skill in skills:
        name = skill.get("name")
        expected_path = f".agents/skills/{name}/SKILL.md"
        if (
            not isinstance(name, str)
            or name in names
            or skill.get("path") != expected_path
            or not (ROOT / expected_path).is_file()
        ):
            raise ValueError(f"invalid installed Skill binding: {skill.get('skill_id')}")
        names.add(name)

    plan = load_json(bundle / "convergence-plan.json")
    if plan.get("p0_skills") != EXPECTED_SKILL_IDS:
        raise ValueError("convergence plan must preserve all 32 ordered P0 Skills")
    readiness = load_json(bundle / "readiness-gate.json")
    criteria = readiness.get("criteria")
    if not isinstance(criteria, dict) or set(criteria) != EXPECTED_CRITERIA:
        raise ValueError("readiness gate must preserve the exact eight criteria")
    if readiness.get("status") == "not-run" and any(criteria.values()):
        raise ValueError("not-run readiness cannot contain passed criteria")

    return {
        "status": "PASS",
        "schemas": len(EXPECTED_SCHEMA_FILES),
        "schema_bound_instances": len(INSTANCE_BY_SCHEMA),
        "skills": len(skills),
        "capabilities": len(load_json(bundle / "capability-registry.json")["capabilities"]),
        "dependency_nodes": len(load_json(bundle / "dependency-graph.json")["nodes"]),
        "evidence_nodes": len(load_json(bundle / "evidence-graph.json")["nodes"]),
        "readiness": readiness.get("status"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(args.bundle.resolve()), sort_keys=True))


if __name__ == "__main__":
    main()
