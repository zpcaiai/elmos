#!/usr/bin/env python3
"""Generate a deterministic digest manifest for all strict-suite control inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _common import load_json, sha256_file


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("suite", nargs="?", default="test-suites/batch1-37-strict")
    parser.add_argument("--schema-root", default=str(REPOSITORY_ROOT / "schemas/test-suite"))
    args = parser.parse_args()
    root = Path(args.suite).resolve()
    schema_root = Path(args.schema_root).resolve()
    catalog_path = root / "cases/catalog.json"
    catalog = load_json(catalog_path)
    control_paths = {
        "catalog": catalog_path,
        "coverage_matrix": root / "coverage-matrix.json",
        "strict_profile": root / "strict-profile.json",
        "suite": root / "suite.json",
    }
    schema_digests = {
        path.name: f"sha256:{sha256_file(path)}" for path in sorted(schema_root.glob("*.json"))
    }
    document = {
        "manifest_version": 2,
        "suite_id": "batch1-37-strict",
        "case_count": len(catalog.get("cases", [])),
        "case_ids": [case["id"] for case in catalog.get("cases", [])],
        "control_digests": {
            name: f"sha256:{sha256_file(path)}" for name, path in control_paths.items()
        },
        "schema_digests": schema_digests,
    }
    output = root / "cases/manifest.json"
    output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"WROTE {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
