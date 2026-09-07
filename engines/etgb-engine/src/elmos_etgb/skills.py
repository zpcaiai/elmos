"""Independent audit of the declarative v1.1 Skill registry.

The archive is reference material.  This module validates its structure and
front matter without importing, executing, or trusting any package code.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator


FRONT_MATTER = re.compile(r"^---\n(?P<yaml>.*?)\n---\n", re.DOTALL)


def audit_skills(root: Path) -> dict[str, Any]:
    root = Path(root).resolve(strict=True)
    errors: list[str] = []
    warnings: list[str] = []
    try:
        manifest = yaml.safe_load((root / "skills/manifest.yaml").read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("skill manifest must be an object")
        schema_path = root / "schemas/skill-manifest.schema.json"
        if schema_path.is_file():
            schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
            errors.extend(error.message for error in Draft202012Validator(schema).iter_errors(manifest))
        skills = manifest.get("skills", [])
        if not isinstance(skills, list):
            raise ValueError("skills must be a list")
        names = [str(item.get("name", "")) for item in skills if isinstance(item, dict)]
        if len(names) != len(set(names)):
            errors.append("duplicate skill names")
        known = set(names)
        graph: dict[str, list[str]] = {}
        for item in skills:
            if not isinstance(item, dict):
                errors.append("skill entry must be an object")
                continue
            name = str(item.get("name", ""))
            relative = str(item.get("path", ""))
            path = (root / relative).resolve()
            try:
                path.relative_to(root)
            except ValueError:
                errors.append(f"skill path escapes package root: {relative}")
                continue
            if not path.is_file():
                errors.append(f"missing skill file: {relative}")
                continue
            text = path.read_text(encoding="utf-8")
            match = FRONT_MATTER.match(text)
            if not match:
                errors.append(f"missing YAML front matter: {relative}")
                continue
            front = yaml.safe_load(match.group("yaml"))
            if not isinstance(front, dict) or front.get("name") != name:
                errors.append(f"front matter name mismatch: {relative}")
            if not isinstance(front, dict) or not front.get("description"):
                errors.append(f"missing front matter description: {relative}")
            if len(text.splitlines()) < 20:
                warnings.append(f"skill may be too shallow: {relative}")
            dependencies = [str(value) for value in item.get("depends_on", [])]
            graph[name] = dependencies
            errors.extend(f"unknown dependency {dependency} in {name}" for dependency in dependencies if dependency not in known)
        entry = manifest.get("entry_skill")
        if entry not in known:
            errors.append(f"unknown entry_skill: {entry}")
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str, path: list[str]) -> None:
            if node in visiting:
                errors.append("dependency cycle: " + " -> ".join(path + [node]))
                return
            if node in visited:
                return
            visiting.add(node)
            for dependency in graph.get(node, []):
                visit(dependency, path + [node])
            visiting.remove(node)
            visited.add(node)

        for name in graph:
            visit(name, [])
        return {"valid": not errors, "skill_count": len(names), "entry_skill": entry, "errors": errors, "warnings": warnings}
    except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
        return {"valid": False, "skill_count": 0, "entry_skill": None, "errors": [str(exc)], "warnings": warnings}
