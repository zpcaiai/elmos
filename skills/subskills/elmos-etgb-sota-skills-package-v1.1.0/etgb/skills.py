from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator


FRONT_MATTER = re.compile(r"^---\n(?P<yaml>.*?)\n---\n", re.DOTALL)


def audit_skills(root: Path) -> dict[str, Any]:
    root = Path(root)
    manifest_path = root / "skills/manifest.yaml"
    schema_path = root / "schemas/skill-manifest.schema.json"
    errors: list[str] = []
    warnings: list[str] = []
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if schema_path.exists():
        schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
        errors.extend(error.message for error in Draft202012Validator(schema).iter_errors(manifest))
    names = [item["name"] for item in manifest.get("skills", [])]
    if len(names) != len(set(names)):
        errors.append("duplicate skill names")
    known = set(names)
    for item in manifest.get("skills", []):
        path = root / item["path"]
        if not path.exists():
            errors.append(f"missing skill file: {item['path']}")
            continue
        text = path.read_text(encoding="utf-8")
        match = FRONT_MATTER.match(text)
        if not match:
            errors.append(f"missing YAML front matter: {item['path']}")
            continue
        front = yaml.safe_load(match.group("yaml"))
        if front.get("name") != item["name"]:
            errors.append(f"front matter name mismatch: {item['path']}")
        if not front.get("description"):
            errors.append(f"missing front matter description: {item['path']}")
        if len(text.splitlines()) < 20:
            warnings.append(f"skill may be too shallow: {item['path']}")
        for dependency in item.get("depends_on", []):
            if dependency not in known:
                errors.append(f"unknown dependency {dependency} in {item['name']}")
    entry = manifest.get("entry_skill")
    if entry not in known:
        errors.append(f"unknown entry_skill: {entry}")

    # Detect dependency cycles because recursive skill routing must terminate.
    graph = {item["name"]: item.get("depends_on", []) for item in manifest.get("skills", [])}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str, path: list[str]) -> None:
        if node in visiting:
            errors.append("dependency cycle: " + " -> ".join(path + [node]))
            return
        if node in visited:
            return
        visiting.add(node)
        for dep in graph.get(node, []):
            visit(dep, path + [node])
        visiting.remove(node)
        visited.add(node)

    for name in graph:
        visit(name, [])
    return {
        "valid": not errors,
        "skill_count": len(names),
        "entry_skill": entry,
        "errors": errors,
        "warnings": warnings,
    }
