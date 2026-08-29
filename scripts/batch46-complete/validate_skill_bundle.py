#!/usr/bin/env python3
"""Validate the 40 Batch 46 Complete convergence Skills (Skill IDs 1497-1536).

The `b46-` prefix is shared with the Batch 46 runnable-smoke pack, so this
validator selects its own Skills by Skill ID range instead of by folder prefix.
"""
from pathlib import Path
import re
import sys

ID_RANGE = range(1497, 1537)
REQUIRED_SECTIONS = ("## 实施流程", "## 验证", "## 完成定义", "## 停止与升级")
SKILL_ID_RE = re.compile(r"^# Skill (\d+)", re.M)
NAME_RE = re.compile(r"^name:\s*(\S+)", re.M)


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    errors: list[str] = []
    names: list[str] = []
    ids: list[int] = []

    search_dirs = [
        root / ".agents/skills",
        root / "skills/batch46-product-convergence-complete-skills/.agents/skills",
    ]
    seen_paths = set()
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for path in sorted(search_dir.glob("b46-*/SKILL.md")):
            if path.resolve() in seen_paths:
                continue
            seen_paths.add(path.resolve())
            text = path.read_text(encoding="utf-8")
            id_match = SKILL_ID_RE.search(text)
            if not id_match or int(id_match.group(1)) not in ID_RANGE:
                continue  # belongs to another b46- pack
            skill_id = int(id_match.group(1))
            name_match = NAME_RE.search(text)
            if not name_match:
                errors.append(f"{path}: missing frontmatter name")
                continue
            if name_match.group(1) != path.parent.name:
                errors.append(f"{path}: name {name_match.group(1)} != folder {path.parent.name}")
            for section in REQUIRED_SECTIONS:
                if section not in text:
                    errors.append(f"{path}: missing {section}")
            names.append(name_match.group(1))
            ids.append(skill_id)

    if len(names) != 40:
        errors.append(f"expected 40 Skills in {ID_RANGE.start}-{ID_RANGE.stop - 1}, found {len(names)}")
    if len(names) != len(set(names)):
        errors.append("duplicate Skill names")
    missing = sorted(set(ID_RANGE) - set(ids))
    if missing:
        errors.append(f"missing Skill IDs: {missing}")
    duplicated = sorted({i for i in ids if ids.count(i) > 1})
    if duplicated:
        errors.append(f"duplicate Skill IDs: {duplicated}")

    if errors:
        print("FAIL")
        for error in errors:
            print(f"  {error}")
        return 1
    print("Batch 46 complete skills ok: 40")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
