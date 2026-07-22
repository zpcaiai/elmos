#!/usr/bin/env python3
"""Validate the exact Batch 1-37 case catalog and its Skill ownership."""

from __future__ import annotations

import argparse
from pathlib import Path

from _common import collect_errors, load_json, validate_case


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def validate_catalog(path: Path, skill_root: Path) -> list[str]:
    try:
        document = load_json(path)
    except Exception as exc:  # noqa: BLE001 - validator must report malformed input
        return [f"cannot read catalog: {exc}"]
    cases = document.get("cases") if isinstance(document, dict) else None
    if not isinstance(cases, list):
        return ["catalog.cases must be an array"]

    errors: list[str] = []
    if len(cases) != 408:
        errors.append(f"catalog must contain exactly 408 cases, found {len(cases)}")
    case_ids = [case.get("id") for case in cases if isinstance(case, dict)]
    if len(case_ids) != len(set(case_ids)):
        errors.append("duplicate case ids")

    try:
        skill_manifest = load_json(REPOSITORY_ROOT / "docs/test-suite/SOURCE_PACKAGE_MANIFEST.json")
        declared_skills = skill_manifest["skills"]
    except Exception as exc:  # noqa: BLE001
        errors.append(f"cannot read strict-suite Skill manifest: {exc}")
        declared_skills = []
    skill_names = {
        item.get("name") for item in declared_skills if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    if len(skill_names) != 52:
        errors.append(f"expected exactly 52 manifest-owned tst Skills, found {len(skill_names)}")
    for name in sorted(skill_names):
        if not (skill_root / name / "SKILL.md").is_file():
            errors.append(f"manifest-owned Skill is missing: {name}")

    owned_skills: set[str] = set()
    for index, case in enumerate(cases):
        case_id = case.get("id", f"index-{index}") if isinstance(case, dict) else f"index-{index}"
        errors.extend(collect_errors(str(case_id), validate_case(case)))
        if isinstance(case, dict):
            skill = case.get("skill")
            if isinstance(skill, str):
                owned_skills.add(skill)
                if skill not in skill_names:
                    errors.append(f"{case_id}: owner Skill does not exist: {skill}")

    orphan_skills = sorted(skill_names - owned_skills)
    if orphan_skills:
        errors.append(f"Skills without owned cases: {orphan_skills}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "catalog",
        nargs="?",
        default="test-suites/batch1-37-strict/cases/catalog.json",
    )
    parser.add_argument("--skill-root", default=str(REPOSITORY_ROOT / ".agents/skills"))
    args = parser.parse_args()
    errors = validate_catalog(Path(args.catalog), Path(args.skill_root))
    if errors:
        print("FAIL")
        print("\n".join(errors))
        return 1
    print("PASS: 408 cases, exact ownership, unique ids, and strict fields")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
