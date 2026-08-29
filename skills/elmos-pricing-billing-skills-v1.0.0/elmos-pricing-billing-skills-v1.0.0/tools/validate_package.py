#!/usr/bin/env python3
"""Validate Elmos pricing/billing Agent Skills package structure and traceability."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except Exception:
    yaml = None

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
REQUIRED_SECTIONS = [
    "## Objective",
    "## Trigger boundaries",
    "## Inputs",
    "## Outputs",
    "## Workflow",
    "## Hard invariants",
    "## Required tests",
    "## Evidence contract",
    "## Definition of Done",
    "## Stop and escalate",
    "## Completion report",
]


class Validation:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.checks = 0

    def require(self, condition: bool, message: str) -> None:
        self.checks += 1
        if not condition:
            self.errors.append(message)

    def warn(self, condition: bool, message: str) -> None:
        self.checks += 1
        if not condition:
            self.warnings.append(message)


def parse_frontmatter(path: Path, validation: Validation) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.search(text)
    validation.require(match is not None, f"Missing YAML frontmatter: {path}")
    if match is None:
        return {}, text
    raw = match.group(1)
    if yaml is not None:
        try:
            data = yaml.safe_load(raw) or {}
        except Exception as exc:
            validation.errors.append(f"Invalid YAML frontmatter {path}: {exc}")
            data = {}
    else:
        data = {}
        for line in raw.splitlines():
            if line.startswith(" ") or ":" not in line:
                continue
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip().strip('"')
        validation.warnings.append("PyYAML not installed; used reduced frontmatter parser")
    return data, text[match.end():]


def validate_skill(path: Path, validation: Validation) -> dict[str, Any]:
    data, body = parse_frontmatter(path, validation)
    name = data.get("name")
    description = data.get("description")
    validation.require(isinstance(name, str), f"name must be string: {path}")
    if isinstance(name, str):
        validation.require(bool(NAME_RE.fullmatch(name)), f"Invalid skill name: {name}")
        validation.require(len(name) <= 64, f"Skill name exceeds 64 chars: {name}")
        validation.require(name == path.parent.name, f"Skill name must match directory: {name} != {path.parent.name}")
    validation.require(isinstance(description, str) and 1 <= len(description) <= 1024, f"Invalid description length: {path}")
    validation.require(len(body.splitlines()) <= 500, f"SKILL.md exceeds 500 lines: {path}")
    for section in REQUIRED_SECTIONS:
        validation.require(section in body, f"Missing section {section}: {path}")

    for rel in re.findall(r"\]\(([^)]+)\)", body):
        if rel.startswith(("http://", "https://", "#")):
            continue
        validation.require((path.parent / rel).exists(), f"Broken relative reference {rel} in {path}")
    return data


def check_dag(nodes: dict[str, list[str]], validation: Validation, label: str) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str, trail: list[str]) -> None:
        if node in visited:
            return
        if node in visiting:
            validation.errors.append(f"Cycle in {label}: {' -> '.join(trail + [node])}")
            return
        visiting.add(node)
        for dep in nodes.get(node, []):
            validation.require(dep in nodes, f"Unknown {label} dependency {dep} referenced by {node}")
            if dep in nodes:
                visit(dep, trail + [node])
        visiting.remove(node)
        visited.add(node)

    for node in nodes:
        visit(node, [])


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_checksums(root: Path, validation: Validation) -> None:
    checksum_path = root / "CHECKSUMS.sha256"
    validation.require(checksum_path.exists(), "Missing CHECKSUMS.sha256")
    if not checksum_path.exists():
        return
    for lineno, line in enumerate(checksum_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            expected, rel = line.split("  ", 1)
        except ValueError:
            validation.errors.append(f"Malformed checksum line {lineno}")
            continue
        target = root / rel
        validation.require(target.exists() and target.is_file(), f"Checksum target missing: {rel}")
        if target.exists() and target.is_file():
            validation.require(sha256_file(target) == expected, f"Checksum mismatch: {rel}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    v = Validation()

    v.require(root.is_dir(), f"Package root not found: {root}")
    if not root.is_dir():
        return 1

    # Safe-path and symlink checks.
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        v.require(".." not in rel.parts and not rel.is_absolute(), f"Unsafe path: {rel}")
        v.require(not path.is_symlink(), f"Symlink not allowed in distributable package: {rel}")

    package_manifest_path = root / "PACKAGE_MANIFEST.json"
    skills_manifest_path = root / "manifests" / "skills.manifest.json"
    batches_manifest_path = root / "manifests" / "batches.manifest.json"
    v.require(package_manifest_path.exists(), "Missing PACKAGE_MANIFEST.json")
    v.require(skills_manifest_path.exists(), "Missing skills.manifest.json")
    v.require(batches_manifest_path.exists(), "Missing batches.manifest.json")

    if not all(p.exists() for p in (package_manifest_path, skills_manifest_path, batches_manifest_path)):
        print("Validation failed before manifest checks", file=sys.stderr)
        return 1

    package_manifest = json.loads(package_manifest_path.read_text(encoding="utf-8"))
    skills_manifest = json.loads(skills_manifest_path.read_text(encoding="utf-8"))
    batches_manifest = json.loads(batches_manifest_path.read_text(encoding="utf-8"))

    skill_dirs = sorted((root / "skills").glob("*/SKILL.md"))
    v.require(len(skill_dirs) == package_manifest.get("counts", {}).get("skills"), "Skill count differs from package manifest")
    v.require(len(skill_dirs) == len(skills_manifest.get("skills", [])), "Skill count differs from skills manifest")

    parsed_skills: dict[str, dict[str, Any]] = {}
    for skill_file in skill_dirs:
        data = validate_skill(skill_file, v)
        if isinstance(data.get("name"), str):
            v.require(data["name"] not in parsed_skills, f"Duplicate skill name: {data['name']}")
            parsed_skills[data["name"]] = data

    manifest_skills = {s["name"]: s for s in skills_manifest.get("skills", [])}
    v.require(set(parsed_skills) == set(manifest_skills), "Skill directories and manifest names differ")
    skill_dag = {name: list(item.get("depends_on", [])) for name, item in manifest_skills.items()}
    check_dag(skill_dag, v, "skill")

    batches = batches_manifest.get("batches", [])
    v.require(len(batches) == package_manifest.get("counts", {}).get("batches"), "Batch count differs from package manifest")
    batch_ids = [b["id"] for b in batches]
    expected_batch_ids = [f"B{i:02d}" for i in range(len(batches))]
    v.require(batch_ids == expected_batch_ids, "Batch IDs must be contiguous and ordered")
    batch_dag = {b["id"]: list(b.get("depends_on", [])) for b in batches}
    check_dag(batch_dag, v, "batch")
    for b in batches:
        v.require(b.get("skill") in manifest_skills, f"Batch {b.get('id')} references unknown skill")

    trace_path = root / "manifests" / "requirements.traceability.csv"
    v.require(trace_path.exists(), "Missing requirements.traceability.csv")
    trace_rows: list[dict[str, str]] = []
    if trace_path.exists():
        with trace_path.open(encoding="utf-8", newline="") as fh:
            trace_rows = list(csv.DictReader(fh))
        req_ids = [r["requirement_id"] for r in trace_rows]
        v.require(len(req_ids) == package_manifest.get("counts", {}).get("requirements"), "Requirement count differs from package manifest")
        v.require(len(req_ids) == len(set(req_ids)), "Duplicate requirement IDs")
        manifest_req_ids = {req for s in manifest_skills.values() for req in s.get("requirement_ids", [])}
        v.require(set(req_ids) == manifest_req_ids, "Traceability and skill manifest requirement IDs differ")
        for row in trace_rows:
            v.require(row["skill"] in manifest_skills, f"Requirement references unknown skill: {row}")
            v.require(row["priority"] in {"P0", "P1", "P2"}, f"Invalid priority: {row}")
            v.require(row["status"] in {"MISSING", "IMPLEMENTED", "PARTIAL", "STUB", "NOT VERIFIED"}, f"Invalid initial status: {row}")

    # Parse all JSON and YAML files.
    for path in root.rglob("*.json"):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            v.errors.append(f"Invalid JSON {path.relative_to(root)}: {exc}")
    if yaml is not None:
        for pattern in ("*.yaml", "*.yml"):
            for path in root.rglob(pattern):
                try:
                    yaml.safe_load(path.read_text(encoding="utf-8"))
                except Exception as exc:
                    v.errors.append(f"Invalid YAML {path.relative_to(root)}: {exc}")
    else:
        v.warnings.append("PyYAML not installed; standalone YAML files were not parsed")

    for script in [root / "install.sh", root / "validate.sh", root / "uninstall.sh"] + list((root / "tools").glob("*.py")):
        v.require(script.exists(), f"Missing script: {script.relative_to(root)}")
        if script.exists() and os.name != "nt":
            v.require(os.access(script, os.X_OK), f"Script is not executable: {script.relative_to(root)}")

    validate_checksums(root, v)

    print(f"Package: {package_manifest.get('name')} {package_manifest.get('version')}")
    print(f"Checks executed: {v.checks}")
    print(f"Skills: {len(skill_dirs)}; batches: {len(batches)}; requirements: {len(trace_rows)}")
    if v.warnings:
        print("Warnings:")
        for item in v.warnings:
            print(f"  - {item}")
    if v.errors:
        print("Errors:", file=sys.stderr)
        for item in v.errors:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("VALIDATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
