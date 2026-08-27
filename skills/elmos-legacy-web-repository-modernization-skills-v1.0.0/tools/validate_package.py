#!/usr/bin/env python3
"""Validate the Elmos modernization skills package."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:
    raise SystemExit("PyYAML is required: pip install -r requirements.txt") from exc

try:
    import jsonschema
except ImportError as exc:
    raise SystemExit("jsonschema is required: pip install -r requirements.txt") from exc


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def check_dag(skills: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    ids = {s["id"] for s in skills}
    errors: list[str] = []
    indegree = {sid: 0 for sid in ids}
    outgoing: dict[str, list[str]] = defaultdict(list)

    for skill in skills:
        sid = skill["id"]
        for dep in skill.get("requires", []):
            if dep not in ids:
                errors.append(f"{sid}: missing dependency {dep}")
                continue
            outgoing[dep].append(sid)
            indegree[sid] += 1

    queue = deque(sorted(sid for sid, degree in indegree.items() if degree == 0))
    order: list[str] = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for nxt in sorted(outgoing[node]):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)

    if len(order) != len(ids):
        cyclic = sorted(sid for sid, degree in indegree.items() if degree > 0)
        errors.append("skill dependency cycle detected: " + ", ".join(cyclic))
    return order, errors


def parse_front_matter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError("missing YAML front matter")
    try:
        _, front, _ = text.split("---", 2)
    except ValueError as exc:
        raise ValueError("invalid front matter delimiters") from exc
    data = yaml.safe_load(front)
    if not isinstance(data, dict):
        raise ValueError("front matter is not an object")
    return data


def validate_examples(root: Path, errors: list[str]) -> int:
    mapping = {
        "repository-evidence-graph.example.json": "repository-evidence-graph.schema.json",
        "legacy-web-semantic-ir.example.json": "legacy-web-semantic-ir.schema.json",
        "behavior-contract.example.json": "behavior-contract.schema.json",
        "migration-plan.example.json": "migration-plan.schema.json",
        "equivalence-report.example.json": "equivalence-report.schema.json",
        "certification-bundle.example.json": "certification-bundle.schema.json",
        "wall-clock-estimate.example.json": "wall-clock-estimate.schema.json",
        "unknown-semantics-ledger.example.json": "unknown-semantics-ledger.schema.json",
        "semantic-source-map.example.json": "semantic-source-map.schema.json",
    }
    count = 0
    for example_name, schema_name in mapping.items():
        example_path = root / "examples" / example_name
        schema_path = root / "schemas" / schema_name
        if not example_path.exists() or not schema_path.exists():
            errors.append(f"missing example/schema pair: {example_name} / {schema_name}")
            continue
        instance = load_json(example_path)
        schema = load_json(schema_path)
        validator_cls = jsonschema.validators.validator_for(schema)
        validator_cls.check_schema(schema)
        validator = validator_cls(schema)
        issues = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
        if issues:
            for issue in issues:
                loc = ".".join(str(x) for x in issue.path)
                errors.append(f"{example_name}:{loc}: {issue.message}")
        count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".", help="package root")
    parser.add_argument("--write-order", action="store_true", help="write topological skill order")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    errors: list[str] = []
    warnings: list[str] = []

    package_path = root / "package.yaml"
    if not package_path.exists():
        print("ERROR: package.yaml missing", file=sys.stderr)
        return 2
    package = load_yaml(package_path)
    if package.get("schema_version") != "elmos.skills.package/v1":
        errors.append("unexpected package schema_version")
    skills = package.get("skills")
    if not isinstance(skills, list) or not skills:
        errors.append("package.skills must be a non-empty list")
        skills = []

    ids: set[str] = set()
    for skill in skills:
        sid = skill.get("id")
        rel = skill.get("path")
        if not sid or sid in ids:
            errors.append(f"duplicate or missing skill id: {sid}")
            continue
        ids.add(sid)
        if not rel:
            errors.append(f"{sid}: missing path")
            continue
        path = root / rel
        if not path.exists():
            errors.append(f"{sid}: skill file missing: {rel}")
            continue
        try:
            front = parse_front_matter(path)
        except Exception as exc:
            errors.append(f"{sid}: {exc}")
            continue
        if front.get("id") != sid:
            errors.append(f"{sid}: front matter id mismatch: {front.get('id')}")
        if front.get("requires", []) != skill.get("requires", []):
            errors.append(f"{sid}: front matter requires differs from package.yaml")
        if front.get("produces", []) != skill.get("produces", []):
            errors.append(f"{sid}: front matter produces differs from package.yaml")

    order, dag_errors = check_dag(skills)
    errors.extend(dag_errors)

    for rel in package.get("schemas", []):
        path = root / rel
        if not path.exists():
            errors.append(f"schema missing: {rel}")
            continue
        try:
            schema = load_json(path)
            jsonschema.validators.validator_for(schema).check_schema(schema)
        except Exception as exc:
            errors.append(f"invalid schema {rel}: {exc}")

    for rel in package.get("policies", []):
        path = root / rel
        if not path.exists():
            errors.append(f"policy missing: {rel}")

    yaml_count = 0
    json_count = 0
    for path in root.rglob("*.yaml"):
        try:
            load_yaml(path)
            yaml_count += 1
        except Exception as exc:
            errors.append(f"invalid YAML {path.relative_to(root)}: {exc}")
    for path in root.rglob("*.json"):
        try:
            load_json(path)
            json_count += 1
        except Exception as exc:
            errors.append(f"invalid JSON {path.relative_to(root)}: {exc}")

    examples_validated = validate_examples(root, errors)

    entrypoint = root / package.get("entrypoint", "")
    if not entrypoint.exists():
        errors.append(f"entrypoint missing: {package.get('entrypoint')}")

    if args.write_order and not errors:
        out = root / "build" / "skill-topological-order.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(order) + "\n", encoding="utf-8")

    print(f"Package: {package.get('id')} {package.get('version')}")
    print(f"Skills: {len(skills)}")
    print(f"Schemas: {len(package.get('schemas', []))}")
    print(f"YAML files parsed: {yaml_count}")
    print(f"JSON files parsed: {json_count}")
    print(f"Examples schema-validated: {examples_validated}")
    print(f"DAG nodes ordered: {len(order)}")

    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"Validation FAILED with {len(errors)} error(s)", file=sys.stderr)
        return 1

    print("Validation PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
