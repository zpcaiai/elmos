#!/usr/bin/env python3
"""Ensure every repository Runtime Skill has an invocable Codex interface."""

from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "agent-skills" / "runtime"
SKILL_CREATOR = Path("/Users/stephen/.codex/skills/.system/skill-creator")
GENERATOR = SKILL_CREATOR / "scripts" / "generate_openai_yaml.py"
VALIDATOR = SKILL_CREATOR / "scripts" / "quick_validate.py"


def load_validator():
    spec = importlib.util.spec_from_file_location("elmos_runtime_skill_validator", VALIDATOR)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Cannot load official Skill validator: {VALIDATOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate_skill


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail instead of generating missing interfaces")
    parser.add_argument(
        "--root",
        type=Path,
        default=RUNTIME,
        help="Skill directory root (defaults to agent-skills/runtime)",
    )
    args = parser.parse_args()
    skill_root = args.root.resolve()
    validate_skill = load_validator()
    updated: list[str] = []
    missing: list[str] = []
    skills = sorted(path.parent for path in skill_root.glob("*/SKILL.md"))
    for skill_dir in skills:
        name = skill_dir.name
        valid, message = validate_skill(skill_dir)
        if not valid:
            raise SystemExit(f"Invalid Runtime Skill {name}: {message}")
        content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        frontmatter_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        if frontmatter_match is None:
            raise SystemExit(f"Invalid Skill frontmatter for {name}")
        frontmatter = yaml.safe_load(frontmatter_match.group(1))
        if frontmatter.get("name") != name:
            raise SystemExit(
                f"Skill directory/frontmatter mismatch: {name} != {frontmatter.get('name')}"
            )
        interface = skill_dir / "agents" / "openai.yaml"
        if interface.is_file() and f"${name}" in interface.read_text(encoding="utf-8"):
            continue
        if args.check:
            missing.append(name)
            continue
        display = name.replace("-", " ").title()
        short = "Run this ELMOS Runtime Skill with evidence controls"
        prompt = f"Use ${name} to execute this ELMOS Runtime Skill with fail-closed evidence."
        subprocess.run(
            [
                sys.executable,
                str(GENERATOR),
                str(skill_dir),
                "--interface",
                f"display_name={display}",
                "--interface",
                f"short_description={short}",
                "--interface",
                f"default_prompt={prompt}",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        updated.append(name)

    if missing:
        raise SystemExit(f"Runtime Skill interfaces are missing or stale: {missing[:10]} ({len(missing)} total)")

    invalid_interfaces = []
    for skill_dir in skills:
        interface = skill_dir / "agents" / "openai.yaml"
        if not interface.is_file() or f"${skill_dir.name}" not in interface.read_text(encoding="utf-8"):
            invalid_interfaces.append(skill_dir.name)
    if invalid_interfaces:
        raise SystemExit(f"Runtime Skill interfaces remain invalid: {invalid_interfaces[:10]}")
    print(
        {
            "skill_root": str(skill_root),
            "skills": len(skills),
            "interfaces_updated": len(updated),
            "interfaces_valid": len(skills),
        }
    )


if __name__ == "__main__":
    main()
