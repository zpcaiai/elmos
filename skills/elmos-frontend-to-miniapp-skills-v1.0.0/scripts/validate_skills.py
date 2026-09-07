#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict, deque
from pathlib import Path

from common import load_manifest, package_root, parse_frontmatter


def validate(root: Path) -> dict:
    manifest = load_manifest(root)
    skills = manifest["skills"]
    errors: list[str] = []
    warnings: list[str] = []
    names = [s["name"] for s in skills]

    if len(names) != len(set(names)):
        errors.append("Duplicate skill names in manifest")

    task_owners: dict[str, str] = {}
    graph: dict[str, list[str]] = {}

    for item in skills:
        name = item["name"]
        expected_dir = root / item["path"]
        entry = root / item["entrypoint"]
        if expected_dir.name != name:
            errors.append(f"{name}: directory name mismatch: {expected_dir.name}")
        if not entry.exists():
            errors.append(f"{name}: missing {entry.relative_to(root)}")
            continue

        try:
            front, body = parse_frontmatter(entry)
        except Exception as exc:
            errors.append(str(exc))
            continue

        if front.get("name") != name:
            errors.append(f"{name}: frontmatter name mismatch: {front.get('name')}")
        description = front.get("description")
        if not isinstance(description, str) or not description.strip():
            errors.append(f"{name}: missing non-empty description")
        elif len(description) > 600:
            warnings.append(f"{name}: description exceeds 600 characters")
        if len(body.strip()) < 500:
            errors.append(f"{name}: SKILL.md body is too short")

        metadata = front.get("metadata", {})
        if metadata.get("package") != manifest["package"]["id"]:
            errors.append(f"{name}: metadata.package mismatch")
        if metadata.get("version") != manifest["package"]["version"]:
            errors.append(f"{name}: metadata.version mismatch")
        if metadata.get("task_ids") != item.get("task_ids"):
            errors.append(f"{name}: task IDs differ between frontmatter and manifest")

        for required in ["references/contract.md", "assets/output-contract.yaml", "examples/invocation.md"]:
            if not (expected_dir / required).exists():
                errors.append(f"{name}: missing supporting file {required}")

        for tid in item.get("task_ids", []):
            if tid in task_owners:
                errors.append(f"Duplicate task ID {tid}: {task_owners[tid]} and {name}")
            task_owners[tid] = name

        deps = item.get("depends_on", [])
        graph[name] = deps
        for dep in deps:
            if dep not in names:
                errors.append(f"{name}: unknown dependency {dep}")
            if dep == name:
                errors.append(f"{name}: self dependency")

    # Kahn cycle detection
    incoming = {name: 0 for name in names}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for name, deps in graph.items():
        for dep in deps:
            if dep in incoming:
                incoming[name] += 1
                outgoing[dep].append(name)
    queue = deque(sorted([n for n, count in incoming.items() if count == 0]))
    visited: list[str] = []
    while queue:
        node = queue.popleft()
        visited.append(node)
        for nxt in outgoing[node]:
            incoming[nxt] -= 1
            if incoming[nxt] == 0:
                queue.append(nxt)
    if len(visited) != len(names):
        errors.append("Skill dependency graph contains a cycle")

    expected_skill_count = manifest["package"]["skill_count"]
    expected_task_count = manifest["package"]["task_count"]
    if len(skills) != expected_skill_count:
        errors.append(f"skill_count expected {expected_skill_count}, got {len(skills)}")
    if len(task_owners) != expected_task_count:
        errors.append(f"task_count expected {expected_task_count}, got {len(task_owners)}")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "skill_count": len(skills),
        "task_count": len(task_owners),
        "topological_order": visited,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = (args.root or package_root()).resolve()
    result = validate(root)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for warning in result["warnings"]:
            print(f"WARN: {warning}")
        for error in result["errors"]:
            print(f"ERROR: {error}")
        print(f"skills={result['skill_count']} tasks={result['task_count']} ok={result['ok']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
