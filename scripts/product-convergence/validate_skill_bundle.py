#!/usr/bin/env python3
"""Validate the product-convergence Skill bundle against its registry.

The previous version asserted a bare directory count (``== 32``).  That made the
check fail the moment the bundle legitimately grew to 42 Skills, while telling
nobody *which* Skill was wrong.  The registry is the source of truth, so this
validates against it:

* every Skill the registry declares must exist, parse, and carry its CONV id;
* CONV ids and Skill names must be unique and contiguous;
* extra ``conv-*`` Skills are allowed but must still be structurally valid, and
  are reported explicitly so the bundle cannot grow silently.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

#: Each required section, with the accepted heading spellings.  The bundle is
#: bilingual: the CONV-001..032 core uses English headings, the later extension
#: Skills use the Chinese equivalents.  Both carry the same obligation, so both
#: are accepted - but the section must be present in one of them.
REQUIRED_SECTIONS: tuple[tuple[str, ...], ...] = (
    ("## Workflow", "## 实施流程"),
    ("## Verification", "## 验证"),
    ("## Stop and escalate when", "## Stop / escalate", "## 停止与升级"),
    ("## Definition of done", "## 完成定义"),
)
CONV_ID_RE = re.compile(r"^#\s+(CONV-\d{3})", re.M)
NAME_RE = re.compile(r"^name:\s*(\S+)", re.M)


def check_skill(path: Path, *, require_conv_id: bool, errors: list[str]) -> tuple[str | None, str | None]:
    if not path.is_file():
        errors.append(f"missing SKILL.md: {path}")
        return None, None
    text = path.read_text(encoding="utf-8")
    name_match = NAME_RE.search(text)
    if not name_match:
        errors.append(f"{path}: frontmatter has no name")
    for spellings in REQUIRED_SECTIONS:
        if not any(spelling in text for spelling in spellings):
            errors.append(f"{path}: missing section {' / '.join(spellings)}")
    id_match = CONV_ID_RE.search(text)
    if require_conv_id and not id_match:
        errors.append(f"{path}: registered Skill has no CONV id heading")
    return (name_match.group(1) if name_match else None, id_match.group(1) if id_match else None)


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else ".").resolve()
    registry_path = root / "product-convergence" / "skill-registry.json"
    if not registry_path.is_file():
        print(f"FAIL: skill registry not found at {registry_path}")
        return 1

    registry = json.loads(registry_path.read_text(encoding="utf-8"))["skills"]
    errors: list[str] = []
    names: list[str] = []
    ids: list[str] = []

    registered_dirs: set[str] = set()
    for entry in registry:
        rel = entry["path"]
        path = root / rel
        registered_dirs.add(Path(rel).parent.name)
        name, conv_id = check_skill(path, require_conv_id=True, errors=errors)
        if name and name != entry["name"]:
            errors.append(f"{rel}: frontmatter name {name!r} != registry name {entry['name']!r}")
        if conv_id and conv_id != entry["skill_id"]:
            errors.append(f"{rel}: heading {conv_id} != registry id {entry['skill_id']}")
        if name:
            names.append(name)
        if conv_id:
            ids.append(conv_id)

    on_disk = sorted(p.parent.name for p in (root / ".agents" / "skills").glob("conv-*/SKILL.md"))
    extras = [d for d in on_disk if d not in registered_dirs]
    for directory in extras:
        name, _ = check_skill(
            root / ".agents" / "skills" / directory / "SKILL.md", require_conv_id=False, errors=errors
        )
        if name:
            names.append(name)

    if len(names) != len(set(names)):
        errors.append("duplicate Skill name in the bundle")
    if len(ids) != len(set(ids)):
        errors.append("duplicate CONV id in the bundle")
    expected_ids = {f"CONV-{n:03d}" for n in range(1, len(registry) + 1)}
    if set(ids) != expected_ids:
        errors.append(
            "registered CONV ids are not contiguous: "
            f"missing={sorted(expected_ids - set(ids))} unexpected={sorted(set(ids) - expected_ids)}"
        )

    if errors:
        print("FAIL")
        for error in errors:
            print("  " + error)
        return 1
    print(
        f"convergence skills ok: {len(registry)} registered (CONV-001..CONV-{len(registry):03d})"
        f" + {len(extras)} unregistered extension skills"
    )
    if extras:
        print("  extensions: " + ", ".join(extras))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
