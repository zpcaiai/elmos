#!/usr/bin/env python3
"""Validate the 30 Batch 38-45 test Skills and their UI metadata."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from _common import load_json


SECTIONS = (
    "## Workflow",
    "## Mandatory case set",
    "## Verification",
    "## Stop / escalate",
    "## Definition of done",
)


def validate(root: Path) -> list[str]:
    catalog_path = root / "test-suites/batch38-45-strict/cases/catalog.json"
    try:
        cases = load_json(catalog_path)["cases"]
    except Exception as exc:  # noqa: BLE001
        return [f"cannot load catalog: {exc}"]
    expected = sorted({case["skill_name"] for case in cases})
    errors: list[str] = []
    if len(expected) != 30:
        errors.append(f"expected 30 catalog Skill names, found {len(expected)}")
    for name in expected:
        folder = root / ".agents/skills" / name
        skill_file = folder / "SKILL.md"
        if not skill_file.is_file():
            errors.append(f"missing {skill_file}")
            continue
        text = skill_file.read_text(encoding="utf-8")
        match = re.search(r"^name:\s*(\S+)\s*$", text, re.MULTILINE)
        if not match or match.group(1) != name:
            errors.append(f"{name}: frontmatter name mismatch")
        description = re.search(r"^description:\s*(.+)$", text, re.MULTILINE)
        if not description or "Batch 38" not in description.group(1):
            errors.append(f"{name}: description must include Batch 38-45 trigger scope")
        for section in SECTIONS:
            if section not in text:
                errors.append(f"{name}: missing {section}")
        metadata = folder / "agents/openai.yaml"
        if not metadata.is_file():
            errors.append(f"{name}: missing agents/openai.yaml")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    errors = validate(Path(args.root).resolve())
    if errors:
        print("FAIL")
        print("\n".join(errors))
        return 1
    print("PASS: 30 exact Skills with strict workflows, owned cases and UI metadata")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
