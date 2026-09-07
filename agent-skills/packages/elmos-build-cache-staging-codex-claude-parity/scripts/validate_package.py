#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PACKAGE = "elmos-build-cache-staging-codex-claude-parity"
EXPECTED_VERSION = "1.2.0"
EXPECTED_SKILLS = 42
EXPECTED_TESTS = 34
EXPECTED_ENTRY = "elmos-codex-claude-cache-parity-rollout"
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


def validate_checksums() -> int:
    checksum_path = ROOT / "checksums.sha256"
    if not checksum_path.exists():
        fail("checksums.sha256 is missing")
    count = 0
    for number, line in enumerate(checksum_path.read_text(encoding="utf-8").splitlines(), 1):
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
        count += 1
    return count


def run(command: list[str], *, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> None:
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("package_id") != EXPECTED_PACKAGE:
        fail("unexpected package_id")
    if manifest.get("package_version") != EXPECTED_VERSION:
        fail("unexpected package_version")
    if manifest.get("entry_skill") != EXPECTED_ENTRY:
        fail("unexpected entry_skill")

    entries = manifest["skills"]
    if len(entries) != EXPECTED_SKILLS:
        fail(f"expected {EXPECTED_SKILLS} skills, found {len(entries)}")
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
        for field in ("name", "description", "version", "package", "phase", "dependencies"):
            if not frontmatter.get(field):
                fail(f"{path}: missing frontmatter field {field}")
        if frontmatter["name"] != entry["id"]:
            fail(f"{path}: name does not match manifest ID")
        if frontmatter["version"] != manifest["package_version"]:
            fail(f"{path}: version does not match package_version")
        if frontmatter["package"] != manifest["package_id"]:
            fail(f"{path}: package does not match package_id")
        for section in REQUIRED_SECTIONS:
            if section not in text:
                fail(f"{path}: missing section {section}")

    for relative in manifest.get("required_files", []):
        if not (ROOT / relative).is_file():
            fail(f"missing required file: {relative}")

    json_count = 0
    for path in ROOT.rglob("*.json"):
        if "__pycache__" in path.parts:
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            fail(f"invalid JSON {path}: {exc}")
        json_count += 1

    checksum_count = validate_checksums()
    print(f"package structure OK: {len(entries)} skills, {json_count} JSON files, {checksum_count} checksums")

    python_paths = list((ROOT / "reference-implementation").rglob("*.py")) + list((ROOT / "scripts").rglob("*.py"))
    for python_path in python_paths:
        try:
            compile(python_path.read_text(encoding="utf-8"), str(python_path), "exec")
        except Exception as exc:
            fail(f"Python compilation failed for {python_path}: {exc}")
    print(f"Python compilation OK: {len(python_paths)} files")

    tests = run([
        sys.executable,
        "-m",
        "unittest",
        "discover",
        "-s",
        str(ROOT / "reference-implementation/tests"),
        "-v",
    ])
    if tests.returncode != 0:
        print(tests.stdout)
        print(tests.stderr, file=sys.stderr)
        fail("reference implementation tests failed")
    combined = tests.stdout + tests.stderr
    match = re.search(r"Ran (\d+) tests?", combined)
    if not match or int(match.group(1)) != EXPECTED_TESTS:
        fail(f"expected {EXPECTED_TESTS} tests; output was:\n{combined}")
    print(f"reference implementation tests OK: {EXPECTED_TESTS}")

    parity = run([
        sys.executable,
        str(ROOT / "scripts/run_cache_parity_benchmark.py"),
        str(ROOT / "examples/cache-parity-observations.example.json"),
    ])
    if parity.returncode != 0:
        print(parity.stdout)
        print(parity.stderr, file=sys.stderr)
        fail("example parity gate failed")
    parity_report = json.loads(parity.stdout)
    if not parity_report.get("mandatory_pass") or len(parity_report.get("checks", {})) != 15:
        fail("example parity report did not pass all 15 checks")
    print("example parity gate OK: 15 checks")

    with tempfile.TemporaryDirectory() as directory:
        destination = Path(directory) / "skills"
        install = run([
            sys.executable,
            str(ROOT / "scripts/install.py"),
            "--dest",
            str(destination),
        ])
        if install.returncode != 0:
            print(install.stdout)
            print(install.stderr, file=sys.stderr)
            fail("installer smoke test failed")
        installed = [path for path in destination.iterdir() if path.is_dir()]
        if len(installed) != EXPECTED_SKILLS:
            fail(f"installer smoke test installed {len(installed)} skills")
    print(f"installer smoke test OK: {EXPECTED_SKILLS} skills")

    pycache = list(ROOT.rglob("__pycache__"))
    if pycache:
        fail(f"package contains __pycache__ directories: {pycache}")
    print("package validation PASS")


if __name__ == "__main__":
    main()
