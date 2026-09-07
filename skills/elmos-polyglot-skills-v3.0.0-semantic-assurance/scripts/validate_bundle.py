#!/usr/bin/env python3
"""Static validator for the ELMOS Polyglot Skills bundle.

This validates package structure and internal consistency only. It does not
certify that any language route or production migration has been implemented.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Iterable

EXPECTED_TECHNOLOGIES = [
    "java", "kotlin", "python", "csharp", "go", "rust", "cpp", "php",
    "typescript", "react", "objc", "swift", "flutter", "javascript",
]
EXPECTED_SKILLS = 64
EXPECTED_ROUTE_CELLS = len(EXPECTED_TECHNOLOGIES) ** 2
EXPECTED_REFERENCE_ROUTES = 18
EXPECTED_SCHEMAS = 15
REQUIRED_SECTIONS = [
    "## Objective",
    "## When to use",
    "## Preconditions",
    "## Inputs",
    "## Outputs",
    "## Guardrails",
    "## Workflow",
    "## Implementation Contract",
    "## Required Tests",
    "## Verification",
    "## Stop and Escalate",
    "## Definition of Done",
    "## Completion Report",
]
SECRET_PATTERNS = [
    re.compile(r"(?i)\b(?:api[_-]?key|secret|token|password)\b\s*[:=]\s*['\"]?[A-Za-z0-9+/=_-]{20,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
]
TEXT_EXTENSIONS = {
    ".md", ".txt", ".yaml", ".yml", ".json", ".csv", ".py", ".sh",
    ".toml", ".ini", ".cfg", ".xml", ".js", ".ts",
}


class ValidationResult:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.checks: list[str] = []

    def ok(self, message: str) -> None:
        self.checks.append(message)

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    @property
    def passed(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": "PASS" if self.passed else "FAIL",
            "checks": self.checks,
            "warnings": self.warnings,
            "errors": self.errors,
        }


def load_json(path: Path, result: ValidationResult) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        result.error(f"missing JSON file: {path}")
    except json.JSONDecodeError as exc:
        result.error(f"invalid JSON {path}: {exc}")
    return None


def parse_frontmatter(text: str) -> dict[str, Any]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}
    block = text[4:end].splitlines()
    data: dict[str, Any] = {}
    current_list: str | None = None
    for raw in block:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw.startswith("  - ") and current_list:
            value = raw[4:].strip()
            try:
                value = json.loads(value)
            except Exception:
                value = value.strip("'\"")
            data.setdefault(current_list, []).append(value)
            continue
        current_list = None
        match = re.match(r"^([A-Za-z0-9_-]+):(?:\s*(.*))?$", raw)
        if not match:
            continue
        key, value = match.group(1), (match.group(2) or "").strip()
        if value == "":
            data[key] = []
            current_list = key
        else:
            try:
                data[key] = json.loads(value)
            except Exception:
                data[key] = value.strip("'\"")
    return data


def resolve_skill_path(root: Path, skills_root: Path | None, manifest_path: str) -> Path:
    path = Path(manifest_path)
    if skills_root is not None:
        # Manifest paths are agent-skills/runtime/<name>/SKILL.md.
        parts = path.parts
        if len(parts) >= 4 and parts[0] == "agent-skills" and parts[1] == "runtime":
            return skills_root.joinpath(*parts[2:])
    local = root / path
    if local.exists():
        return local
    # Installed layout keeps support files in <repo>/elmos-polyglot and Skills in
    # <repo>/agent-skills/runtime.
    parent_candidate = root.parent / path
    return parent_candidate


def check_dependency_graph(skills: list[dict[str, Any]], result: ValidationResult) -> None:
    names = {s["name"] for s in skills}
    graph: dict[str, list[str]] = {}
    for skill in skills:
        deps = skill.get("dependencies", [])
        if not isinstance(deps, list):
            result.error(f"{skill['name']}: dependencies must be a list")
            deps = []
        missing = sorted(set(deps) - names)
        if missing:
            result.error(f"{skill['name']}: missing dependencies {missing}")
        graph[skill["name"]] = [d for d in deps if d in names]

    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(node: str) -> None:
        marker = state.get(node, 0)
        if marker == 2:
            return
        if marker == 1:
            try:
                start = stack.index(node)
                cycle = stack[start:] + [node]
            except ValueError:
                cycle = stack + [node]
            result.error("dependency cycle: " + " -> ".join(cycle))
            return
        state[node] = 1
        stack.append(node)
        for dep in graph.get(node, []):
            visit(dep)
        stack.pop()
        state[node] = 2

    for name in sorted(names):
        visit(name)
    if not any("dependency cycle" in e for e in result.errors):
        result.ok("Skill dependency graph is acyclic")


def iter_text_files(root: Path) -> Iterable[Path]:
    excluded = {"__pycache__", ".git", ".venv", "dist"}
    for path in root.rglob("*"):
        if any(part in excluded for part in path.parts):
            continue
        if path.is_file() and path.suffix.lower() in TEXT_EXTENSIONS:
            yield path


def validate_bundle(root: Path, skills_root: Path | None = None) -> ValidationResult:
    root = root.resolve()
    skills_root = skills_root.resolve() if skills_root else None
    result = ValidationResult()

    required_top = [
        "README.md", "AGENTS.md", "manifest.json", "capability-package.yaml",
        "technology-registry.yaml", "technology-registry.json",
        "route-registry.yaml", "route-registry.json", "route-matrix.csv",
        "SKILL_INDEX.md", "install.sh", "uninstall.sh", "validate.sh",
    ]
    for rel in required_top:
        if not (root / rel).exists():
            result.error(f"missing required top-level file: {rel}")
    if not result.errors:
        result.ok("Required top-level files exist")

    manifest = load_json(root / "manifest.json", result)
    if not isinstance(manifest, dict):
        return result
    package = manifest.get("package", {})
    skills = manifest.get("skills", [])
    tech_ids = manifest.get("technologies", [])

    if package.get("skill_count") != EXPECTED_SKILLS or len(skills) != EXPECTED_SKILLS:
        result.error(f"expected {EXPECTED_SKILLS} Skills, manifest declares {package.get('skill_count')} and contains {len(skills)}")
    else:
        result.ok(f"Manifest contains {EXPECTED_SKILLS} Skills")
    if package.get("technology_count") != len(EXPECTED_TECHNOLOGIES):
        result.error("package technology_count mismatch")
    if tech_ids != EXPECTED_TECHNOLOGIES:
        result.error(f"technology order/content mismatch: {tech_ids}")
    else:
        result.ok("Manifest contains the exact 14 requested technology IDs")
    if package.get("default_readiness") != "not-run":
        result.error("package default readiness must be not-run")

    ids: set[str] = set()
    names: set[str] = set()
    for skill in skills:
        sid = skill.get("id")
        name = skill.get("name")
        if sid in ids:
            result.error(f"duplicate Skill ID: {sid}")
        ids.add(sid)
        if name in names:
            result.error(f"duplicate Skill name: {name}")
        names.add(name)
        if skill.get("readiness") != "not-run":
            result.error(f"{name}: manifest readiness must be not-run")
        path = resolve_skill_path(root, skills_root, skill.get("path", ""))
        if not path.exists():
            result.error(f"{name}: missing Skill path {path}")
            continue
        text = path.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        if not fm:
            result.error(f"{name}: missing or invalid YAML frontmatter")
            continue
        if fm.get("name") != name:
            result.error(f"{name}: frontmatter name mismatch {fm.get('name')!r}")
        if fm.get("skill_id") != sid:
            result.error(f"{name}: frontmatter skill_id mismatch {fm.get('skill_id')!r}")
        if fm.get("version") != skill.get("version"):
            result.error(f"{name}: frontmatter version mismatch")
        if fm.get("readiness") != "not-run":
            result.error(f"{name}: frontmatter readiness must be not-run")
        if path.parent.name != name:
            result.error(f"{name}: directory name mismatch {path.parent.name}")
        missing_sections = [section for section in REQUIRED_SECTIONS if section not in text]
        if missing_sections:
            result.error(f"{name}: missing sections {missing_sections}")
        if len(text.splitlines()) < 100:
            result.error(f"{name}: Skill is suspiciously short ({len(text.splitlines())} lines)")
    if not any("missing Skill path" in e or "frontmatter" in e or "missing sections" in e or "suspiciously short" in e for e in result.errors):
        result.ok("All Skill paths, frontmatter, required sections, and minimum content checks pass")

    check_dependency_graph(skills, result)

    tech_registry = load_json(root / "technology-registry.json", result)
    if isinstance(tech_registry, dict):
        entries = tech_registry.get("spec", {}).get("technologies", [])
        actual = [t.get("id") for t in entries]
        if actual != EXPECTED_TECHNOLOGIES:
            result.error(f"technology registry mismatch: {actual}")
        adapters = [t.get("adapter_skill") for t in entries]
        expected_adapters = {f"elmos-adapter-{x}" if x != "objc" else "elmos-adapter-objective-c" for x in EXPECTED_TECHNOLOGIES}
        if set(adapters) != expected_adapters:
            result.error(f"adapter registry mismatch: {sorted(set(adapters) ^ expected_adapters)}")
        else:
            result.ok("Technology registry and fourteen adapters are complete")

    route_registry = load_json(root / "route-registry.json", result)
    if isinstance(route_registry, dict):
        profiles = route_registry.get("spec", {}).get("profiles", [])
        if len(profiles) != EXPECTED_REFERENCE_ROUTES:
            result.error(f"expected {EXPECTED_REFERENCE_ROUTES} route profiles, found {len(profiles)}")
        seen_route_ids: set[str] = set()
        for route in profiles:
            rid = route.get("id")
            if rid in seen_route_ids:
                result.error(f"duplicate route ID: {rid}")
            seen_route_ids.add(rid)
            if route.get("source") not in EXPECTED_TECHNOLOGIES or route.get("target") not in EXPECTED_TECHNOLOGIES:
                result.error(f"{rid}: unknown source/target")
            if route.get("readiness") != "not-run":
                result.error(f"{rid}: readiness must be not-run")
            profile_path = root / route.get("profile", "")
            if not profile_path.exists():
                result.error(f"{rid}: missing profile file {profile_path}")
            elif "readiness: not-run" not in profile_path.read_text(encoding="utf-8"):
                result.error(f"{rid}: YAML profile must default to not-run")
        if len(profiles) == EXPECTED_REFERENCE_ROUTES and not any("route" in e.lower() and ("missing" in e.lower() or "duplicate" in e.lower() or "unknown" in e.lower()) for e in result.errors):
            result.ok(f"{EXPECTED_REFERENCE_ROUTES} reference route profiles are registered")

    matrix_path = root / "route-matrix.csv"
    if matrix_path.exists():
        with matrix_path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if len(rows) != EXPECTED_ROUTE_CELLS:
            result.error(f"expected {EXPECTED_ROUTE_CELLS} route matrix rows, found {len(rows)}")
        pairs = {(row["source"], row["target"]) for row in rows}
        expected_pairs = {(s, t) for s in EXPECTED_TECHNOLOGIES for t in EXPECTED_TECHNOLOGIES}
        if pairs != expected_pairs:
            result.error("route matrix does not contain every ordered technology pair exactly once")
        if any(row.get("readiness") != "not-run" for row in rows):
            result.error("every route matrix row must default to not-run")
        if len(rows) == EXPECTED_ROUTE_CELLS and pairs == expected_pairs:
            result.ok(f"Route matrix contains all {EXPECTED_ROUTE_CELLS} cells")

    schema_files = sorted((root / "schemas").glob("*.json"))
    if len(schema_files) != EXPECTED_SCHEMAS:
        result.error(f"expected {EXPECTED_SCHEMAS} JSON schemas, found {len(schema_files)}")
    for schema_path in schema_files:
        schema = load_json(schema_path, result)
        if isinstance(schema, dict):
            if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
                result.error(f"{schema_path.name}: unsupported or missing $schema")
            if not schema.get("title"):
                result.error(f"{schema_path.name}: missing title")
    if len(schema_files) == EXPECTED_SCHEMAS and not any("schema" in e.lower() and ("invalid" in e.lower() or "missing title" in e.lower()) for e in result.errors):
        result.ok(f"All {EXPECTED_SCHEMAS} JSON schemas parse")

    secret_hits: list[str] = []
    for path in iter_text_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                secret_hits.append(str(path.relative_to(root)))
                break
    if secret_hits:
        result.error(f"possible embedded secrets/private keys in: {sorted(secret_hits)}")
    else:
        result.ok("Obvious secret and private-key scan passes")

    if not result.errors:
        result.ok("Static bundle validation completed")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--skills-root", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    result = validate_bundle(args.root, args.skills_root)
    if args.as_json:
        print(json.dumps(result.as_dict(), indent=2, ensure_ascii=False))
    else:
        for check in result.checks:
            print(f"PASS: {check}")
        for warning in result.warnings:
            print(f"WARN: {warning}")
        for error in result.errors:
            print(f"FAIL: {error}", file=sys.stderr)
        print(f"RESULT: {'PASS' if result.passed else 'FAIL'}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
