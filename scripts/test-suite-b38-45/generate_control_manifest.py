#!/usr/bin/env python3
"""Generate or verify immutable Batch 38-45 suite control digests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _common import load_json, sha256_file


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def build(root: Path, schema_root: Path) -> dict[str, object]:
    suite = load_json(root / "suite.json")
    catalog = load_json(root / suite["case_catalog"])
    control_paths = {
        "catalog": root / suite["case_catalog"],
        "coverage_matrix": root / suite["coverage_matrix"],
        "strict_profile": root / suite["profile"],
        "release_gate": root / suite["release_gate"],
        "suite": root / "suite.json",
    }
    return {
        "manifest_version": 2,
        "suite_id": "batch38-45-strict",
        "case_count": 400,
        "case_ids": [case["case_id"] for case in catalog["cases"]],
        "control_digests": {name: sha256_file(path) for name, path in control_paths.items()},
        "schema_digests": {path.name: sha256_file(path) for path in sorted(schema_root.glob("*.json"))},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", default="test-suites/batch38-45-strict")
    parser.add_argument("--schema-root", default=str(REPOSITORY_ROOT / "schemas/test-suite-b38-45"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(args.suite).resolve()
    expected = build(root, Path(args.schema_root).resolve())
    output = root / "cases/manifest.json"
    if args.check:
        if not output.is_file() or load_json(output) != expected:
            print("FAIL: Batch 38-45 control manifest is missing or stale")
            return 1
        print("PASS: Batch 38-45 control manifest binds controls and Schemas")
        return 0
    output.write_text(json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
