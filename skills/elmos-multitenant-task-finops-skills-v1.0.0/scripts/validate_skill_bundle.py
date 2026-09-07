#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_SKILL_SECTIONS = [
    "## Purpose",
    "## Use this skill when",
    "## Hard invariants",
    "## Required inputs",
    "## Procedure",
    "## Stable implementation tasks",
    "## Primary outputs",
    "## Acceptance criteria",
    "## Required tests",
    "## Evidence contract",
    "## Production-claim boundary",
]


def load_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        raise ValueError("missing YAML frontmatter")
    _, raw, body = text.split("---", 2)
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError("frontmatter must be a mapping")
    return data, body


def validate_dag(skills: list[dict[str, Any]]) -> list[str]:
    internal = {s["name"] for s in skills}
    graph = {s["name"]: [d for d in s.get("depends_on", []) if d in internal] for s in skills}
    indegree = {name: 0 for name in internal}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for child, deps in graph.items():
        for dep in deps:
            indegree[child] += 1
            outgoing[dep].append(child)
    queue = deque(sorted(name for name, degree in indegree.items() if degree == 0))
    visited = []
    while queue:
        current = queue.popleft()
        visited.append(current)
        for child in outgoing[current]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    return [] if len(visited) == len(internal) else ["internal Skill dependency graph contains a cycle"]


def main() -> int:
    errors: list[str] = []
    expected_paths = [
        "README.md", "README.en.md", "AGENTS.md", "CLAUDE.md", "VERSION",
        "skill-manifest.json", "skill-manifest.yaml", "install.sh", "uninstall.sh", "verify.sh",
        "api/openapi.yaml", "events/asyncapi.yaml", "docs/TASK-MATRIX.csv",
        "docs/TRACEABILITY.csv", "docs/task-catalog.json",
        "sql/V100__multitenant_task_finops.sql", "sql/V101__rls_policies.sql",
        "sql/V102__views_and_rollups.sql",
    ]
    for rel in expected_paths:
        if not (ROOT / rel).is_file():
            errors.append(f"missing required file: {rel}")

    try:
        manifest = json.loads((ROOT / "skill-manifest.json").read_text(encoding="utf-8"))
        yaml_manifest = yaml.safe_load((ROOT / "skill-manifest.yaml").read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"manifest parse FAILED: {exc}", file=sys.stderr)
        return 1

    if manifest.get("package") != yaml_manifest.get("package") or manifest.get("version") != yaml_manifest.get("version"):
        errors.append("JSON and YAML manifests disagree")
    skills = manifest.get("skills", [])
    if len(skills) != 12 or manifest.get("total_skills") != 12:
        errors.append("manifest must contain exactly 12 Skills")
    if manifest.get("hard_requirements", {}).get("account_active_root_task_limit") != 3:
        errors.append("hard account task limit must be 3")
    errors += validate_dag(skills)

    skill_ids: set[str] = set()
    skill_names: set[str] = set()
    task_ids_from_skills: set[str] = set()
    task_re = re.compile(r"`(ELMOS-MTF-\d{3}-T\d{2})`")

    for skill in skills:
        sid, name = skill.get("id"), skill.get("name")
        if sid in skill_ids or name in skill_names:
            errors.append(f"duplicate Skill id/name: {sid}/{name}")
        skill_ids.add(sid)
        skill_names.add(name)
        path = ROOT / skill.get("path", "")
        if not path.is_file():
            errors.append(f"missing Skill path: {skill.get('path')}")
            continue
        text = path.read_text(encoding="utf-8")
        try:
            fm, body = load_frontmatter(text)
        except Exception as exc:
            errors.append(f"{path}: {exc}")
            continue
        for key in ("name", "id", "version", "description", "layer", "risk", "depends_on"):
            if key not in fm:
                errors.append(f"{path}: missing frontmatter key {key}")
        if fm.get("name") != name or fm.get("id") != sid:
            errors.append(f"{path}: frontmatter does not match manifest")
        for section in REQUIRED_SKILL_SECTIONS:
            if section not in body:
                errors.append(f"{path}: missing section {section}")
        task_ids = set(task_re.findall(body))
        if len(task_ids) != skill.get("task_count", 0):
            errors.append(f"{path}: expected {skill.get('task_count')} stable tasks, found {len(task_ids)}")
        overlap = task_ids_from_skills & task_ids
        if overlap:
            errors.append(f"duplicate task IDs across Skills: {sorted(overlap)}")
        task_ids_from_skills |= task_ids

    try:
        with (ROOT / "docs" / "TASK-MATRIX.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        matrix_ids = [row["task_id"] for row in rows]
        if len(matrix_ids) != 144 or manifest.get("total_tasks") != 144:
            errors.append(f"expected 144 task rows; found {len(matrix_ids)}")
        if len(set(matrix_ids)) != len(matrix_ids):
            errors.append("TASK-MATRIX contains duplicate task IDs")
        if set(matrix_ids) != task_ids_from_skills:
            errors.append("TASK-MATRIX task IDs differ from Skill task IDs")
    except Exception as exc:
        errors.append(f"TASK-MATRIX parse error: {exc}")

    forbidden_patterns = {
        "obvious private key": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        "obvious AWS access key": r"AKIA[0-9A-Z]{16}",
        "obvious GitHub token": r"gh[pousr]_[A-Za-z0-9_]{30,}",
        "unfinished marker": r"\b(?:TODO|TBD|FIXME)\b",
    }
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix in {".zip", ".gz"}:
            continue
        if path.resolve() == Path(__file__).resolve():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for label, pattern in forbidden_patterns.items():
            if re.search(pattern, text):
                errors.append(f"{path.relative_to(ROOT)}: {label}")

    if errors:
        print("Skill bundle validation FAILED", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Skill bundle validation PASS — 12 Skills / 144 stable tasks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
