#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_SECTIONS = [
    "## Outcome",
    "## Use this skill when",
    "## Required inputs",
    "## Produced artifacts",
    "## Non-negotiable invariants",
    "## Execution workflow",
    "## Implementation tasks",
    "## Acceptance criteria",
    "## Evidence required",
    "## Anti-patterns",
    "## Done condition",
]


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def parse_frontmatter(text: str, path: Path) -> dict[str, str]:
    if not text.startswith("---\n"):
        fail(f"{path}: missing YAML frontmatter")
    end = text.find("\n---\n", 4)
    if end < 0:
        fail(f"{path}: unclosed YAML frontmatter")
    values: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()
    return values


def validate_dag(entries: list[dict]) -> list[str]:
    by_id = {entry["id"]: entry for entry in entries}
    if len(by_id) != len(entries):
        fail("duplicate skill IDs in manifest")
    visiting: set[str] = set()
    visited: set[str] = set()
    order: list[str] = []

    def visit(node: str) -> None:
        if node in visiting:
            fail(f"dependency cycle at {node}")
        if node in visited:
            return
        visiting.add(node)
        for dependency in by_id[node].get("dependencies", []):
            if dependency not in by_id:
                fail(f"{node}: unknown dependency {dependency}")
            visit(dependency)
        visiting.remove(node)
        visited.add(node)
        order.append(node)

    for node in by_id:
        visit(node)
    return order


def validate_checksums() -> None:
    checksum_path = ROOT / "checksums.sha256"
    if not checksum_path.exists():
        fail("checksums.sha256 is missing")
    for number, line in enumerate(
        checksum_path.read_text(encoding="utf-8").splitlines(),
        1,
    ):
        if not line.strip():
            continue
        try:
            expected, relative = line.split("  ", 1)
        except ValueError:
            fail(f"checksums.sha256 line {number} is malformed")
        path = ROOT / relative
        if not path.is_file():
            fail(f"checksum target missing: {relative}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            fail(f"checksum mismatch: {relative}")


def main() -> None:
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    entries = manifest["skills"]
    computed_order = validate_dag(entries)
    if manifest.get("topological_order") != computed_order:
        fail("manifest topological_order does not match dependency graph")

    runtime = ROOT / "agent-skills/runtime"
    directories = {path.name for path in runtime.iterdir() if path.is_dir()}
    ids = {entry["id"] for entry in entries}
    if directories != ids:
        fail(
            "skill directory mismatch: "
            f"directories-only={sorted(directories - ids)}, "
            f"manifest-only={sorted(ids - directories)}"
        )

    for entry in entries:
        path = ROOT / entry["path"]
        if not path.is_file():
            fail(f"missing skill file: {path}")
        text = path.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(text, path)
        for field in (
            "name",
            "description",
            "version",
            "package",
            "phase",
            "dependencies",
        ):
            if not frontmatter.get(field):
                fail(f"{path}: missing frontmatter field {field}")
        if frontmatter["name"] != entry["id"]:
            fail(f"{path}: name does not match manifest ID")
        for section in REQUIRED_SECTIONS:
            if section not in text:
                fail(f"{path}: missing section {section}")

    for relative in manifest.get("required_files", []):
        if not (ROOT / relative).is_file():
            fail(f"missing required file: {relative}")

    for path in ROOT.rglob("*.json"):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            fail(f"invalid JSON {path}: {exc}")

    validate_checksums()
    print(f"package structure and checksums OK: {len(entries)} skills")

    command = [
        sys.executable,
        "-m",
        "unittest",
        "discover",
        "-s",
        str(ROOT / "reference-implementation/tests"),
        "-v",
    ]
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode != 0:
        fail("reference implementation tests failed")
    print("reference implementation tests OK")


if __name__ == "__main__":
    main()
