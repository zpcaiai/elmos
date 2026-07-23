#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


def section(text: str, heading: str) -> str:
    match = re.search(
        rf"(?ms)^{re.escape(heading)}\n(.*?)(?=^## |\Z)",
        text,
    )
    return match.group(1).strip() if match else ""


def frontmatter_value(text: str, key: str) -> str:
    match = re.search(rf"^\s*{re.escape(key)}:\s*(.+?)\s*$", text, re.MULTILINE)
    if match is None:
        raise ValueError(f"missing frontmatter field: {key}")
    return match.group(1).strip().strip('"')


def bullet_identifiers(body: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"^- `([^`]+)`", body, re.MULTILINE)))


def compile_tests(body: str) -> list[dict[str, Any]]:
    tests: list[dict[str, Any]] = []
    current_type: str | None = None
    counters: dict[str, int] = {}
    mapping = {
        "Unit tests": ("unit", "P1"),
        "Integration tests": ("integration", "P0"),
        "Negative and adversarial tests": ("negative", "P0"),
    }
    for line in body.splitlines():
        heading = re.fullmatch(r"### (.+)", line)
        if heading:
            current_type = heading.group(1) if heading.group(1) in mapping else None
            continue
        if current_type is None or not line.startswith("- "):
            continue
        test_type, priority = mapping[current_type]
        counters[test_type] = counters.get(test_type, 0) + 1
        tests.append(
            {
                "id": f"{test_type}-{counters[test_type]:02d}",
                "type": test_type,
                "priority": priority,
                "required": True,
                "instruction": line[2:].strip(),
            }
        )
    return tests


def compile_contract(skill: Path) -> dict[str, Any]:
    if not skill.is_file() or skill.is_symlink():
        raise ValueError("skill must be a regular file")
    text = skill.read_text(encoding="utf-8")
    name = frontmatter_value(text, "name")
    identifier = frontmatter_value(text, "id")
    batch = int(frontmatter_value(text, "batch"))
    version = frontmatter_value(text, "version")
    inputs = bullet_identifiers(section(text, "## Inputs"))
    outputs = bullet_identifiers(section(text, "## Outputs"))

    steps = []
    for match in re.finditer(
        r"^(\d+)\.\s+\*\*(.+?):\*\*\s*(.+)$",
        section(text, "## Workflow"),
        re.MULTILINE,
    ):
        steps.append(
            {
                "id": f"step-{int(match.group(1)):02d}",
                "title": match.group(2).strip(),
                "instruction": match.group(3).strip(),
                "effect": "declared-at-runtime",
            }
        )

    rollback_candidates = []
    for heading in ("## Preconditions", "## Implementation Requirements"):
        for line in section(text, heading).splitlines():
            if line.startswith("- ") and re.search(r"rollback|compensat", line, re.IGNORECASE):
                rollback_candidates.append(line[2:].strip())
    rollback = [
        {
            "id": f"rollback-{index:02d}",
            "instruction": instruction,
            "effect": "declared-at-runtime",
        }
        for index, instruction in enumerate(dict.fromkeys(rollback_candidates), 1)
    ]
    tests = compile_tests(section(text, "## Required Tests"))
    verification_states = list(
        dict.fromkeys(
            re.findall(
                r"^\d+\. `([a-z_]+)`",
                section(text, "## Verification States"),
                re.MULTILINE,
            )
        )
    )
    if not inputs or not outputs or len(steps) < 10 or not rollback or len(tests) < 3:
        raise ValueError("skill does not compile to a complete executable contract")
    if not {"unit", "integration", "negative"}.issubset({test["type"] for test in tests}):
        raise ValueError("skill must declare unit, integration, and negative tests")
    if not verification_states:
        raise ValueError("skill verification states are missing")

    return {
        "schema_version": "elmos.executable-skill-contract.v1",
        "id": identifier,
        "name": name,
        "version": version,
        "batch": batch,
        "inputs": inputs,
        "outputs": outputs,
        "permissions": {
            "default": "deny",
            "external_effects": "authorization-required",
            "secrets": "broker-reference-only",
        },
        "steps": steps,
        "rollback": rollback,
        "tests": tests,
        "evidence": [
            {
                "type": "evidence_bundle",
                "required": True,
                "source_section": "Evidence Contract",
            }
        ],
        "verification_states": verification_states,
        "source_hash": "sha256:" + hashlib.sha256(skill.read_bytes()).hexdigest(),
        "signature": None,
    }


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and (path.is_symlink() or not path.is_file()):
        raise ValueError("output must be a regular file")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("skill")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    try:
        contract = compile_contract(Path(args.skill))
        atomic_write(Path(args.out), contract)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
