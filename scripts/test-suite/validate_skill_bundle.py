#!/usr/bin/env python3
"""Validate standard Codex Skill metadata and strict-suite content."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError:  # Keep the strict-suite validator runnable with stdlib Python.
    yaml = None


FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
REQUIRED_HEADINGS = {
    "## Workflow",
    "## Verification",
    "## Stop and escalate when",
    "## Definition of done",
}


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if value.startswith('"'):
        return json.loads(value)
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1].replace("''", "'")
    if value in {"true", "false"}:
        return value == "true"
    if value in {"null", "~"}:
        return None
    return value


def load_yaml_document(text: str) -> Any:
    if yaml is not None:
        return yaml.safe_load(text)
    result: dict[str, Any] = {}
    current: dict[str, Any] | None = None
    for line_number, raw in enumerate(text.splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"(\s*)([A-Za-z_][A-Za-z0-9_-]*):(?:\s+(.*))?", raw)
        if match is None:
            raise ValueError(f"unsupported YAML syntax on line {line_number}")
        indent, key, value = match.groups()
        if not indent:
            if value is None:
                nested: dict[str, Any] = {}
                result[key] = nested
                current = nested
            else:
                result[key] = parse_scalar(value)
                current = None
        elif indent == "  " and current is not None and value is not None:
            current[key] = parse_scalar(value)
        else:
            raise ValueError(f"unsupported YAML indentation on line {line_number}")
    return result


def validate_bundle(root: Path) -> list[str]:
    errors: list[str] = []
    names: list[str] = []
    manifest_path = root / "docs/test-suite/SOURCE_PACKAGE_MANIFEST.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        declared = manifest["skills"]
    except Exception as exc:  # noqa: BLE001
        return [f"cannot load strict-suite Skill manifest: {exc}"]
    declared_names = [item.get("name") for item in declared if isinstance(item, dict)]
    if len(declared_names) != 52 or len(set(declared_names)) != 52:
        errors.append("strict-suite manifest must declare 52 unique Skills")
    files = [root / ".agents/skills" / name / "SKILL.md" for name in declared_names if isinstance(name, str)]
    for skill_file in files:
        if not skill_file.is_file():
            errors.append(f"missing authoritative strict test Skill: {skill_file}")
    for skill_file in files:
        if not skill_file.is_file():
            continue
        text = skill_file.read_text(encoding="utf-8")
        match = FRONTMATTER_RE.match(text)
        if not match:
            errors.append(f"{skill_file}: invalid YAML frontmatter envelope")
            continue
        try:
            metadata = load_yaml_document(match.group(1))
        except (ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{skill_file}: invalid YAML frontmatter: {exc}")
            continue
        if not isinstance(metadata, dict) or set(metadata) != {"name", "description"}:
            errors.append(f"{skill_file}: frontmatter must contain only name and description")
            continue
        name = metadata.get("name")
        description = metadata.get("description")
        if name != skill_file.parent.name:
            errors.append(f"{skill_file}: name must equal directory name")
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9-]{1,64}", name):
            errors.append(f"{skill_file}: invalid Skill name")
        else:
            names.append(name)
        if not isinstance(description, str) or not description.strip() or len(description) > 1024:
            errors.append(f"{skill_file}: invalid description")
        for heading in REQUIRED_HEADINGS:
            if heading not in text:
                errors.append(f"{skill_file}: missing {heading}")

        interface_path = skill_file.parent / "agents/openai.yaml"
        if not interface_path.is_file():
            errors.append(f"{skill_file.parent}: missing agents/openai.yaml")
            continue
        try:
            interface_doc = load_yaml_document(interface_path.read_text(encoding="utf-8"))
        except (ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{interface_path}: invalid YAML: {exc}")
            continue
        interface = interface_doc.get("interface", {}) if isinstance(interface_doc, dict) else {}
        short_description = interface.get("short_description")
        default_prompt = interface.get("default_prompt")
        if not isinstance(interface.get("display_name"), str) or not interface["display_name"].strip():
            errors.append(f"{interface_path}: display_name is required")
        if not isinstance(short_description, str) or not 25 <= len(short_description) <= 64:
            errors.append(f"{interface_path}: short_description must be 25-64 characters")
        if not isinstance(default_prompt, str) or f"${name}" not in default_prompt:
            errors.append(f"{interface_path}: default_prompt must mention ${name}")
    if len(names) != len(set(names)):
        errors.append("duplicate Skill names")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    errors = validate_bundle(Path(args.root))
    if errors:
        print("FAIL")
        print("\n".join(errors))
        return 1
    print("PASS: 52 manifest-owned standard Codex Skills with valid UI metadata")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
