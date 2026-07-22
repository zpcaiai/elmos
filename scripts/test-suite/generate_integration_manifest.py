#!/usr/bin/env python3
"""Generate or verify the deterministic installed strict-suite payload manifest."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

from _common import sha256_file, sha256_json


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_RELATIVE = Path("docs/test-suite/ELMOS_INTEGRATION_MANIFEST.json")


def strict_skill_directories(root: Path) -> list[Path]:
    manifest = json.loads((root / "docs/test-suite/SOURCE_PACKAGE_MANIFEST.json").read_text(encoding="utf-8"))
    return [root / ".agents/skills" / item["name"] for item in manifest["skills"]]


def unittest_count(path: Path) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
    )


def payload_files(root: Path) -> list[Path]:
    candidates: list[Path] = []
    for pattern in (
        "docs/test-suite",
        "schemas/test-suite",
        "scripts/test-suite",
        "templates/test-suite",
        "tests/test-suite",
        "test-suites/batch1-37-strict",
    ):
        for item in root.glob(pattern):
            if item.is_file():
                candidates.append(item)
            elif item.is_dir():
                candidates.extend(path for path in item.rglob("*") if path.is_file())
    for directory in strict_skill_directories(root):
        if directory.is_dir():
            candidates.extend(path for path in directory.rglob("*") if path.is_file())
    exclusions = {
        root / OUTPUT_RELATIVE,
        root / "docs/test-suite/ELMOS_VALIDATION_REPORT.md",
        root / "test-suites/batch1-37-strict/release-gate.json",
        root / "test-suites/batch1-37-strict/certification-request.json",
        root / "test-suites/batch1-37-strict/certification-request.sig",
    }
    return sorted(
        {
            path.resolve()
            for path in candidates
            if path.resolve() not in exclusions
            and "__pycache__" not in path.parts
            and path.name != ".DS_Store"
            and "evidence" not in path.relative_to(root).parts
        },
        key=lambda item: str(item.relative_to(root)),
    )


def build(root: Path) -> dict:
    files = payload_files(root)
    skill_directories = strict_skill_directories(root)
    entries = [
        {
            "path": str(path.relative_to(root)),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
        for path in files
    ]
    counts = {
        "skills": sum((directory / "SKILL.md").is_file() for directory in skill_directories),
        "skill_interfaces": sum((directory / "agents/openai.yaml").is_file() for directory in skill_directories),
        "cases": 408,
        "result_placeholders": len(list((root / "test-suites/batch1-37-strict/results").glob("*.json"))),
        "schemas": len(list((root / "schemas/test-suite").glob("*.json"))),
        "templates": len(list((root / "templates/test-suite").glob("*.json"))),
        "scripts": len([path for path in (root / "scripts/test-suite").glob("*.py")]),
        "toolkit_tests": sum(
            unittest_count(path)
            for path in sorted((root / "tests/test-suite").glob("test_*.py"))
        ),
        "files": len(entries),
    }
    document = {
        "manifest_version": 1,
        "package": "elmos-batch1-37-strict-test-suite",
        "suite_version": "2.0.0",
        "source_package": {
            "name": "batch1-37-strict-test-suite-skills",
            "version": "1.0.0",
            "supplied_path": "/Users/stephen/Downloads/batch1-37-strict-test-suite-skills/",
        },
        "counts": counts,
        "files": entries,
    }
    document["payload_digest"] = sha256_json(entries)
    return document


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(REPOSITORY_ROOT))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    output = root / OUTPUT_RELATIVE
    actual = build(root)
    if args.check:
        if not output.is_file():
            print(f"FAIL: missing {output}")
            return 1
        expected = json.loads(output.read_text(encoding="utf-8"))
        if expected != actual:
            print("FAIL: strict-suite integration manifest is stale")
            return 1
        print(
            f"PASS: integration manifest files={actual['counts']['files']} "
            f"digest={actual['payload_digest']}"
        )
        return 0
    output.write_text(json.dumps(actual, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"WROTE {output} files={actual['counts']['files']} digest={actual['payload_digest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
