#!/usr/bin/env python3
"""Validate the repository-scoped Batch 29-45 mature-product Skill series."""

from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema
import yaml


ROOT = Path(__file__).resolve().parents[1]
BATCHES = {
    29: {"skills": 20, "first_id": 1141, "last_id": 1160, "schemas": 3},
    30: {"skills": 20, "first_id": 1161, "last_id": 1180, "schemas": 4},
    31: {"skills": 22, "first_id": 1181, "last_id": 1202, "schemas": 6},
    32: {"skills": 20, "first_id": 1203, "last_id": 1222, "schemas": 7},
    33: {"skills": 20, "first_id": 1223, "last_id": 1242, "schemas": 8},
    34: {"skills": 22, "first_id": 1243, "last_id": 1264, "schemas": 10},
    35: {"skills": 22, "first_id": 1265, "last_id": 1286, "schemas": 13, "templates": 15},
    36: {"skills": 18, "first_id": 1287, "last_id": 1304, "schemas": 12, "templates": 16},
    37: {"skills": 36, "first_id": 1305, "last_id": 1324, "schemas": 25, "templates": 27, "supplemental": 16},
    38: {"skills": 22, "first_id": 1325, "last_id": 1346, "schemas": 4},
    39: {"skills": 22, "first_id": 1347, "last_id": 1368, "schemas": 4},
    40: {"skills": 24, "first_id": 1369, "last_id": 1392, "schemas": 4},
    41: {"skills": 20, "first_id": 1393, "last_id": 1412, "schemas": 4},
    42: {"skills": 22, "first_id": 1413, "last_id": 1434, "schemas": 4},
    43: {"skills": 20, "first_id": 1435, "last_id": 1454, "schemas": 4},
    44: {"skills": 20, "first_id": 1455, "last_id": 1474, "schemas": 4},
    45: {"skills": 22, "first_id": 1475, "last_id": 1496, "schemas": 4},
}
REQUIRED_SECTIONS = (
    "## Workflow",
    "## Verification",
    "## Stop and escalate when",
    "## Definition of done",
)
SKILL_ID_PATTERN = re.compile(r"^#{1,2} Skill (\d+)(?::|\b)", re.MULTILINE)
SUPPLEMENTAL_ID_PATTERN = re.compile(r"^#{1,2} Skill B37-X(\d+)(?::|\b)", re.MULTILINE)
LOCAL_REFERENCE_PATTERN = re.compile(
    r"`(\.\./\.\./\.\./(?:docs|scripts)/[^`]+)`"
)


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def parse_frontmatter(path: Path, text: str, errors: list[str]) -> dict[str, object]:
    parts = text.split("---", 2)
    require(len(parts) == 3 and not parts[0].strip(), f"{path}: invalid front matter", errors)
    if len(parts) != 3:
        return {}
    try:
        payload = yaml.safe_load(parts[1])
    except yaml.YAMLError as exc:
        errors.append(f"{path}: invalid YAML: {exc}")
        return {}
    require(isinstance(payload, dict), f"{path}: front matter must be a mapping", errors)
    return payload if isinstance(payload, dict) else {}


def validate_skill(path: Path, seen_names: set[str], errors: list[str]) -> tuple[int | None, int | None]:
    text = path.read_text(encoding="utf-8")
    metadata = parse_frontmatter(path, text, errors)
    name = metadata.get("name")
    description = metadata.get("description")
    require(set(metadata) == {"name", "description"}, f"{path}: unexpected front-matter keys", errors)
    require(name == path.parent.name, f"{path}: name does not match directory", errors)
    require(isinstance(name, str) and name not in seen_names, f"{path}: duplicate or invalid name", errors)
    if isinstance(name, str):
        seen_names.add(name)
    require(
        isinstance(description, str) and len(description.strip()) >= 40,
        f"{path}: description is not specific enough",
        errors,
    )
    for section in REQUIRED_SECTIONS:
        require(section in text, f"{path}: missing {section}", errors)
    ids = [int(value) for value in SKILL_ID_PATTERN.findall(text)]
    supplemental_ids = [int(value) for value in SUPPLEMENTAL_ID_PATTERN.findall(text)]
    require(
        len(ids) + len(supplemental_ids) == 1,
        f"{path}: expected one numeric or B37-X Skill ID, found numeric={ids} supplemental={supplemental_ids}",
        errors,
    )
    for relative in LOCAL_REFERENCE_PATTERN.findall(text):
        resolved = (path.parent / relative).resolve()
        require(resolved.is_file(), f"{path}: missing local reference {relative}", errors)
    return (
        ids[0] if len(ids) == 1 else None,
        supplemental_ids[0] if len(supplemental_ids) == 1 else None,
    )


def validate_json(path: Path, errors: list[str]) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{path}: invalid JSON: {exc}")
        return None


def main() -> int:
    errors: list[str] = []
    seen_names: set[str] = set()
    total_skills = 0
    total_schemas = 0
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

    for batch, expected in BATCHES.items():
        skill_dirs = sorted((ROOT / ".agents" / "skills").glob(f"b{batch}-*"))
        require(
            len(skill_dirs) == expected["skills"],
            f"Batch {batch}: expected {expected['skills']} Skills, found {len(skill_dirs)}",
            errors,
        )
        parsed_ids = [validate_skill(directory / "SKILL.md", seen_names, errors) for directory in skill_dirs]
        ids = [numeric for numeric, _ in parsed_ids if numeric is not None]
        supplemental_ids = [supplemental for _, supplemental in parsed_ids if supplemental is not None]
        if batch >= 35:
            for directory in skill_dirs:
                agent_path = directory / "agents" / "openai.yaml"
                require(agent_path.is_file(), f"{directory}: agents/openai.yaml missing", errors)
                if agent_path.is_file():
                    agent = yaml.safe_load(agent_path.read_text(encoding="utf-8"))
                    prompt = agent.get("interface", {}).get("default_prompt", "") if isinstance(agent, dict) else ""
                    require(f"${directory.name}" in prompt, f"{agent_path}: default_prompt missing Skill name", errors)
        expected_ids = list(range(expected["first_id"], expected["last_id"] + 1))
        require(sorted(ids) == expected_ids, f"Batch {batch}: Skill IDs are not contiguous", errors)
        expected_supplemental = list(range(1, expected.get("supplemental", 0) + 1))
        require(
            sorted(supplemental_ids) == expected_supplemental,
            f"Batch {batch}: supplemental Skill IDs are not contiguous",
            errors,
        )

        schema_files = sorted((ROOT / "schemas" / f"batch{batch}").glob("*.json"))
        require(
            len(schema_files) == expected["schemas"],
            f"Batch {batch}: expected {expected['schemas']} Schemas, found {len(schema_files)}",
            errors,
        )
        for path in schema_files:
            schema = validate_json(path, errors)
            if isinstance(schema, dict):
                try:
                    jsonschema.validators.validator_for(schema).check_schema(schema)
                except jsonschema.exceptions.SchemaError as exc:
                    errors.append(f"{path}: invalid JSON Schema: {exc.message}")

        template_files = sorted((ROOT / "templates" / f"batch{batch}").glob("*.json"))
        require(bool(template_files), f"Batch {batch}: no JSON templates", errors)
        if "templates" in expected:
            require(
                len(template_files) == expected["templates"],
                f"Batch {batch}: expected {expected['templates']} templates, found {len(template_files)}",
                errors,
            )
        for path in template_files:
            validate_json(path, errors)

        require((ROOT / "docs" / f"batch{batch}").is_dir(), f"Batch {batch}: docs missing", errors)
        if batch <= 37:
            require((ROOT / "scripts" / f"batch{batch}").is_dir(), f"Batch {batch}: scripts missing", errors)
        else:
            require((ROOT / "scripts" / "mature_product_toolkit.py").is_file(), f"Batch {batch}: shared toolkit missing", errors)
        require((ROOT / "tests" / f"batch{batch}" / "test_toolkit.py").is_file(), f"Batch {batch}: tests missing", errors)
        if batch == 37:
            require(
                (ROOT / "tests" / "batch37" / "test_closure_toolkit.py").is_file(),
                "Batch 37: closure tests missing",
                errors,
            )
        require((ROOT / f"Makefile.batch{batch}").is_file(), f"Batch {batch}: Makefile missing", errors)
        agent_marker = f"Batch {batch}" if batch < 35 else f"$b{batch}-"
        require(agent_marker in agents, f"Batch {batch}: AGENTS.md instructions missing", errors)

        total_skills += len(skill_dirs)
        total_schemas += len(schema_files)
        print(
            f"Batch {batch}: skills={len(skill_dirs)} ids={expected['first_id']}-{expected['last_id']} "
            f"schemas={len(schema_files)} templates={len(template_files)}"
        )

    require(total_skills == 372, f"Expected 372 Skills, found {total_skills}", errors)
    require(total_schemas == 120, f"Expected 120 Schemas, found {total_schemas}", errors)

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"OK: batches=17 skills={total_skills} schemas={total_schemas}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
