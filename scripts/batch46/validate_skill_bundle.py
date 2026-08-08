#!/usr/bin/env python3
"""Validate the exact repository-facing Batch 46 runnable-smoke Skills."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = ROOT / ".agents" / "skills"

SKILL_NAMES = (
    "b46-runnable-smoke-factory",
    "b46-minimal-runtime-data-analyzer",
    "b46-seed-data-synthesizer",
    "b46-seed-data-provenance-policy",
    "b46-one-click-entry-emitter",
    "b46-smoke-assertion-design",
    "b46-ephemeral-data-isolation-teardown",
    "b46-runtime-lease-quota-reclaim",
    "b46-smoke-evidence-recorder",
    "b46-runnable-smoke-gate",
    "b46-b29-language-route-smoke",
    "b46-b30-framework-smoke",
    "b46-b31-database-seed-smoke",
    "b46-b32-client-smoke",
    "b46-polyglot-topology-smoke",
    "b46-console-run-button",
)

REQUIRED_HEADINGS = (
    "## Operating mode",
    "## Global constraints",
    "## Use this skill when",
    "## Risks and invariants",
    "## Workflow",
    "## Required outputs",
    "## Verification",
    "## Stop and escalate when",
)

REQUIRED_RUNTIME_FILES = (
    "scripts/batch46/scaffold_smoke_pack.py",
    "scripts/batch46/validate_smoke_pack.py",
    "scripts/batch46/run_smoke_gate.py",
    "scripts/batch46/run_smoke.py",
    "scripts/batch46/smoke_lease.py",
    "docs/batch46/IMPLEMENTATION_CONTRACT.md",
    "docs/batch46/QUALITY_GATES.md",
)


def validate() -> list[str]:
    failures: list[str] = []
    ids: set[int] = set()
    for expected_name in SKILL_NAMES:
        skill_file = SKILLS_ROOT / expected_name / "SKILL.md"
        if not skill_file.is_file():
            failures.append(f"missing Skill: {skill_file.relative_to(ROOT)}")
            continue
        text = skill_file.read_text(encoding="utf-8")
        frontmatter = re.match(r"\A---\nname:\s*([^\n]+)\ndescription:\s*([^\n]+)\n---\n", text)
        if not frontmatter:
            failures.append(f"{expected_name}: invalid exact frontmatter")
        else:
            declared_name = frontmatter.group(1).strip()
            description = frontmatter.group(2).strip()
            if declared_name != expected_name:
                failures.append(f"{expected_name}: declared name is {declared_name!r}")
            if len(declared_name) > 64:
                failures.append(f"{expected_name}: name exceeds 64 characters")
            if len(description) < 40:
                failures.append(f"{expected_name}: description is not operationally specific")
        for heading in REQUIRED_HEADINGS:
            if heading not in text:
                failures.append(f"{expected_name}: missing heading {heading}")
        skill_id = re.search(r"^## Skill (46\d{2}):", text, flags=re.MULTILINE)
        if not skill_id:
            failures.append(f"{expected_name}: missing Skill 46xx identity")
        else:
            numeric_id = int(skill_id.group(1))
            if numeric_id in ids:
                failures.append(f"{expected_name}: duplicate Skill id {numeric_id}")
            ids.add(numeric_id)
        if "NOT_RUN" not in text or "never" not in text.lower():
            failures.append(f"{expected_name}: fail-closed evidence boundary is incomplete")

    expected_ids = set(range(4601, 4617))
    if ids != expected_ids:
        failures.append(f"Skill ids differ: expected {sorted(expected_ids)}, got {sorted(ids)}")
    for relative in REQUIRED_RUNTIME_FILES:
        if not (ROOT / relative).is_file():
            failures.append(f"runtime dependency missing: {relative}")
    return failures


def main() -> int:
    failures = validate()
    if failures:
        print("BATCH46_SKILL_BUNDLE=FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("BATCH46_SKILL_BUNDLE=PASS skills=16 ids=4601-4616 runtime=BOUND")
    return 0


if __name__ == "__main__":
    sys.exit(main())
