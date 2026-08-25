#!/usr/bin/env python3
"""Validate the Elmos multimodal intake Skills package."""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SKILLS = 50
REQUIRED_ROOT_FILES = [
    "README.md", "START_HERE.md", "AGENTS.md", "CLAUDE.md",
    "package.yaml", "manifest.json", "BUILD_INFO.json",
    "docs/MASTER_REQUIREMENTS.md", "docs/REFERENCE_ARCHITECTURE.md",
    "docs/IMPLEMENTATION_ROADMAP.md", "docs/DATA_MODEL.md",
    "docs/API_AND_EVENTS.md", "docs/SECURITY_THREAT_MODEL.md",
    "docs/TEST_STRATEGY.md", "docs/COMPATIBILITY.md",
    "docs/ARCHITECTURE_DECISIONS.md", "docs/SKILL_CATALOG.md",
]
PLACEHOLDERS = re.compile(
    r"\b(TODO|TBD|FIXME|XXX|PLACEHOLDER|NOT IMPLEMENTED)\b",
    re.IGNORECASE,
)


class ValidationError(RuntimeError):
    pass


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValidationError(f"{path}: missing YAML frontmatter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValidationError(f"{path}: unterminated YAML frontmatter")
    block = text[4:end]
    data: dict[str, str] = {}
    for line in block.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise ValidationError(f"{path}: invalid frontmatter line: {line!r}")
        key, value = line.split(":", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        data[key.strip()] = value
    return data


def load_yaml(path: Path) -> Any:
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise ValidationError(
            "PyYAML is required for full validation: python -m pip install PyYAML jsonschema"
        ) from exc
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def validate_json_schemas() -> None:
    try:
        import jsonschema  # type: ignore
    except ImportError as exc:
        raise ValidationError(
            "jsonschema is required for full validation: python -m pip install PyYAML jsonschema"
        ) from exc

    schemas = sorted((ROOT / "schemas").glob("*.schema.json"))
    if len(schemas) != 9:
        raise ValidationError(f"Expected 9 JSON schemas, found {len(schemas)}")
    for path in schemas:
        obj = json.loads(path.read_text(encoding="utf-8"))
        validator = jsonschema.validators.validator_for(obj)
        validator.check_schema(obj)


def validate_skills() -> list[str]:
    canonical = ROOT / "skills"
    dirs = sorted(p for p in canonical.iterdir() if p.is_dir())
    if len(dirs) != EXPECTED_SKILLS:
        raise ValidationError(f"Expected {EXPECTED_SKILLS} Skills, found {len(dirs)}")

    names: list[str] = []
    ordinals: list[int] = []
    deps: dict[str, list[str]] = {}

    for directory in dirs:
        skill_md = directory / "SKILL.md"
        contract_path = directory / "references" / "contract.yaml"
        if not skill_md.is_file():
            raise ValidationError(f"{directory}: missing SKILL.md")
        if not contract_path.is_file():
            raise ValidationError(f"{directory}: missing references/contract.yaml")

        fm = parse_frontmatter(skill_md)
        if fm.get("name") != directory.name:
            raise ValidationError(
                f"{skill_md}: frontmatter name {fm.get('name')!r} != directory {directory.name!r}"
            )
        if not fm.get("description"):
            raise ValidationError(f"{skill_md}: empty description")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", directory.name):
            raise ValidationError(f"{directory}: invalid skill name")
        names.append(directory.name)

        contract = load_yaml(contract_path)
        if contract.get("name") != directory.name:
            raise ValidationError(f"{contract_path}: name mismatch")
        ordinal = int(contract.get("ordinal"))
        ordinals.append(ordinal)
        deps[directory.name] = list(contract.get("dependencies") or [])

        text = skill_md.read_text(encoding="utf-8")
        if PLACEHOLDERS.search(text):
            raise ValidationError(f"{skill_md}: placeholder marker found")
        if "- [ ]" not in text:
            raise ValidationError(f"{skill_md}: no deliverable/acceptance checklist")

    if sorted(ordinals) != list(range(1, EXPECTED_SKILLS + 1)):
        raise ValidationError(f"Skill ordinals are not exactly 1..{EXPECTED_SKILLS}: {sorted(ordinals)}")
    if len(set(names)) != EXPECTED_SKILLS:
        raise ValidationError("Duplicate skill names")

    known = set(names)
    for skill_name, dependencies in deps.items():
        unknown = sorted(set(dependencies) - known)
        if unknown:
            raise ValidationError(f"{skill_name}: unknown dependencies {unknown}")

    return names


def validate_yaml_files() -> None:
    yaml_files = sorted(
        list((ROOT / "policies").glob("*.yaml"))
        + list((ROOT / "evals").glob("*.yaml"))
        + list((ROOT / "skills").glob("*/references/*.yaml"))
        + [ROOT / "package.yaml"]
    )
    if len(list((ROOT / "policies").glob("*.yaml"))) != 5:
        raise ValidationError("Expected 5 policy YAML files")
    for path in yaml_files:
        obj = load_yaml(path)
        if obj is None:
            raise ValidationError(f"{path}: empty YAML")


def validate_trigger_eval(names: list[str]) -> None:
    path = ROOT / "evals" / "skill-trigger-prompts.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 100:
        raise ValidationError(f"Expected 100 trigger rows, found {len(rows)}")
    counts = {name: 0 for name in names}
    for row in rows:
        expected = row.get("expected_skill", "")
        if expected not in counts:
            raise ValidationError(f"Unknown expected_skill in eval: {expected}")
        if row.get("should_trigger", "").lower() != "true":
            raise ValidationError(f"Trigger dataset contains non-positive row: {row.get('id')}")
        counts[expected] += 1
    bad = {k: v for k, v in counts.items() if v != 2}
    if bad:
        raise ValidationError(f"Every skill must have exactly two trigger rows: {bad}")


def tree_hash(path: Path) -> str:
    digest = hashlib.sha256()
    for file_path in sorted(p for p in path.rglob("*") if p.is_file()):
        rel = file_path.relative_to(path).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def validate_mirrors(names: list[str]) -> None:
    canonical = ROOT / "skills"
    for rel in [Path(".agents/skills"), Path(".claude/skills")]:
        mirror = ROOT / rel
        dirs = sorted(p.name for p in mirror.iterdir() if p.is_dir()) if mirror.is_dir() else []
        if dirs != sorted(names):
            raise ValidationError(f"{rel}: mirror directory names do not match canonical Skills")
        for name in names:
            if tree_hash(canonical / name) != tree_hash(mirror / name):
                raise ValidationError(f"{rel / name}: content differs from canonical")


def validate_required_files() -> None:
    for rel in REQUIRED_ROOT_FILES:
        path = ROOT / rel
        if not path.is_file() or path.stat().st_size == 0:
            raise ValidationError(f"Missing/empty required file: {rel}")


def main() -> int:
    try:
        validate_required_files()
        names = validate_skills()
        validate_yaml_files()
        validate_json_schemas()
        validate_trigger_eval(names)
        validate_mirrors(names)
    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    print("PASS")
    print(f"  root: {ROOT}")
    print(f"  canonical skills: {len(names)}")
    print("  JSON schemas: 9")
    print("  policy YAML files: 5")
    print("  trigger evaluation rows: 100")
    print("  Codex and Claude Code mirrors: byte-equivalent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
