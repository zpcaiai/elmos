#!/usr/bin/env python3
"""Validate the eLMOS Infrastructure Foundation Skill bundle structure."""
from __future__ import annotations
import argparse
import json
import re
import sys
from collections import defaultdict, deque
from pathlib import Path

REQUIRED_SECTIONS = [
    "## Objective",
    "## Use this skill when",
    "## Dependencies",
    "## Non-negotiable constraints",
    "## Required inputs",
    "## Required outputs",
    "## Repository discovery",
    "## Execution workflow",
    "## Implementation checklist",
    "## Required artifacts",
    "## Validation",
    "## Definition of done",
    "## Failure handling and handoff",
]

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)\b(?:api[_-]?key|secret[_-]?key|password)\s*[:=]\s*['\"][A-Za-z0-9/+_=.-]{16,}['\"]"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
]

def fail(message: str, errors: list[str]) -> None:
    errors.append(message)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=None, help="Bundle root; defaults to script parent.")
    args = parser.parse_args()
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    errors: list[str] = []

    required = [
        "README.md", "QUICKSTART.md", "skill-manifest.json", "skill-manifest.yaml",
        "docs/task-catalog.json", "docs/TASK-MATRIX.csv",
        "templates/IMPLEMENTATION-PLAN.yaml", "schemas/digest.schema.json",
        "install.sh", "uninstall.sh", "verify.sh",
    ]
    for rel in required:
        if not (root / rel).exists():
            fail(f"missing required file: {rel}", errors)

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    manifest = json.loads((root / "skill-manifest.json").read_text(encoding="utf-8"))
    catalog = json.loads((root / "docs/task-catalog.json").read_text(encoding="utf-8"))
    skills = manifest.get("skills", [])
    tasks = catalog.get("tasks", [])

    if manifest.get("skill_count") != len(skills):
        fail("manifest skill_count mismatch", errors)
    if manifest.get("task_count") != len(tasks):
        fail("manifest task_count mismatch", errors)
    if catalog.get("task_count") != len(tasks):
        fail("catalog task_count mismatch", errors)

    names = [item.get("name") for item in skills]
    if len(names) != len(set(names)):
        fail("duplicate skill name", errors)
    task_ids = [item.get("id") for item in tasks]
    if len(task_ids) != len(set(task_ids)):
        fail("duplicate task id", errors)
    bad_ids = [x for x in task_ids if not isinstance(x, str) or not re.fullmatch(r"ELMOS-[A-Z]+-\d{3}", x)]
    if bad_ids:
        fail(f"invalid task IDs: {bad_ids[:5]}", errors)

    known = set(names)
    indegree = {name: 0 for name in names}
    graph: dict[str, list[str]] = defaultdict(list)
    markdown_ids: set[str] = set()

    for entry in skills:
        name = entry["name"]
        rel = Path(entry["path"])
        path = root / rel
        if not path.is_file():
            fail(f"missing skill file: {rel}", errors)
            continue
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            fail(f"{name}: missing YAML frontmatter", errors)
        match = re.search(r"(?m)^name:\s*['\"]?([^'\"\n]+)", text[:2000])
        if not match or match.group(1).strip() != name:
            fail(f"{name}: frontmatter name mismatch", errors)
        for section in REQUIRED_SECTIONS:
            if section not in text:
                fail(f"{name}: missing section {section}", errors)
        for dep in entry.get("dependencies", []):
            if dep not in known:
                fail(f"{name}: unknown dependency {dep}", errors)
            else:
                graph[dep].append(name)
                indegree[name] += 1
        ids = re.findall(r"`(ELMOS-[A-Z]+-\d{3})`", text)
        if len(ids) != entry.get("task_count"):
            fail(f"{name}: task count in markdown {len(ids)} != manifest {entry.get('task_count')}", errors)
        for task_id in ids:
            if task_id in markdown_ids:
                fail(f"task ID appears in multiple skill files: {task_id}", errors)
            markdown_ids.add(task_id)
        if "static bundle validation" not in text.lower():
            fail(f"{name}: missing production claim boundary", errors)

    if set(task_ids) != markdown_ids:
        missing = sorted(set(task_ids) - markdown_ids)
        extra = sorted(markdown_ids - set(task_ids))
        fail(f"catalog/markdown task mismatch; missing={missing[:5]} extra={extra[:5]}", errors)

    queue = deque(sorted([name for name, count in indegree.items() if count == 0]))
    visited = []
    while queue:
        current = queue.popleft()
        visited.append(current)
        for nxt in sorted(graph[current]):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
    if len(visited) != len(names):
        fail("skill dependency graph contains a cycle", errors)
    if manifest.get("topological_order") != visited:
        fail("manifest topological_order is stale or non-canonical", errors)

    for path in root.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        if path.suffix.lower() in {".zip", ".png", ".jpg", ".jpeg", ".gif", ".pdf"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                fail(f"possible secret material: {path.relative_to(root)} ({pattern.pattern})", errors)

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"FAIL: {len(errors)} problem(s)", file=sys.stderr)
        return 1

    print(f"PASS: {len(skills)} skills")
    print(f"PASS: {len(tasks)} unique tasks")
    print("PASS: dependency graph is acyclic and topological order is canonical")
    print("PASS: required sections, manifests, and production-claim boundaries")
    print("PASS: no obvious secret material found")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
