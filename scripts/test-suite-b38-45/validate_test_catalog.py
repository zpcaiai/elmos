#!/usr/bin/env python3
"""Validate the exact 400-case Batch 38-45 strict catalog."""

from __future__ import annotations

import argparse
from pathlib import Path

from _common import collect_errors, load_json, validate_case


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def validate_catalog(path: Path, skill_root: Path) -> list[str]:
    try:
        document = load_json(path)
    except Exception as exc:  # noqa: BLE001
        return [f"cannot read catalog: {exc}"]
    if not isinstance(document, dict):
        return ["catalog must be an object"]
    cases = document.get("cases")
    if not isinstance(cases, list):
        return ["catalog.cases must be an array"]
    errors: list[str] = []
    if document.get("suite_id") != "batch38-45-strict":
        errors.append("catalog suite_id mismatch")
    if document.get("case_count") != 400 or len(cases) != 400:
        errors.append(f"catalog must contain exactly 400 cases, found {len(cases)}")
    case_ids = [case.get("case_id") for case in cases if isinstance(case, dict)]
    if len(case_ids) != len(set(case_ids)):
        errors.append("duplicate case ids")
    if case_ids != sorted(case_ids):
        errors.append("case ids must remain in deterministic sorted order")

    owned: dict[str, list[str]] = {}
    for index, case in enumerate(cases):
        case_id = case.get("case_id", f"index-{index}") if isinstance(case, dict) else f"index-{index}"
        errors.extend(collect_errors(str(case_id), validate_case(case)))
        if isinstance(case, dict) and isinstance(case.get("skill_name"), str):
            owned.setdefault(case["skill_name"], []).append(str(case_id))
    if len(owned) != 30:
        errors.append(f"catalog must be owned by exactly 30 Skills, found {len(owned)}")
    codes = {case.get("skill_code") for case in cases if isinstance(case, dict)}
    if codes != {f"U{index:03d}" for index in range(1, 31)}:
        errors.append("Skill codes must be exactly U001 through U030")
    for skill_name, ids in owned.items():
        skill_file = skill_root / skill_name / "SKILL.md"
        if not skill_file.is_file():
            errors.append(f"owner Skill does not exist: {skill_name}")
            continue
        text = skill_file.read_text(encoding="utf-8")
        for case_id in ids:
            if f"`{case_id}`" not in text:
                errors.append(f"{skill_name}: mandatory case set omits {case_id}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("catalog", nargs="?", default="test-suites/batch38-45-strict/cases/catalog.json")
    parser.add_argument("--skill-root", default=str(REPOSITORY_ROOT / ".agents/skills"))
    args = parser.parse_args()
    errors = validate_catalog(Path(args.catalog), Path(args.skill_root))
    if errors:
        print("FAIL")
        print("\n".join(errors))
        return 1
    print("PASS: exact 400 cases, 30 Skill owners, strict fields and mandatory ownership")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
