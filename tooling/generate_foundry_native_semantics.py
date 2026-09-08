#!/usr/bin/env python3
"""Generate or verify exact brokered native semantic programs.

This utility consumes only the repository-owned compiled catalog.  It does not
read or execute source-package code.  Existing provider-free handlers remain in
``local_semantics`` and are deliberately excluded from the brokered manifest.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
ENGINE_ROOT = ROOT / "engines/knowledge-skill-model-foundry-engine"
ENGINE_SOURCE = ENGINE_ROOT / "src"
CATALOG_PATH = ENGINE_ROOT / "catalog/compiled-catalog.json"
OUTPUT_PATH = ENGINE_SOURCE / "elmos_foundry/native-semantic-programs.json"

sys.path.insert(0, str(ENGINE_SOURCE))

from elmos_foundry.local_semantics import LOCAL_SEMANTIC_SKILLS  # noqa: E402
from elmos_foundry.native_semantics import build_manifest  # noqa: E402


def _read_catalog() -> dict[str, Any]:
    value = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("atomic_skills"), list):
        raise SystemExit("compiled catalog is not an object with atomic_skills")
    return value


def expected_bytes() -> bytes:
    catalog = _read_catalog()
    records = [
        row
        for row in catalog["atomic_skills"]
        if isinstance(row, dict) and row.get("name") not in LOCAL_SEMANTIC_SKILLS
    ]
    if len(records) != 1_310 - len(LOCAL_SEMANTIC_SKILLS):
        raise SystemExit("native semantic source set is incomplete")
    manifest = build_manifest(records)
    return (
        json.dumps(
            manifest,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    expected = expected_bytes()
    if args.write:
        OUTPUT_PATH.write_bytes(expected)
    if not OUTPUT_PATH.is_file() or OUTPUT_PATH.read_bytes() != expected:
        raise SystemExit("native semantic program manifest is missing or stale")
    programs = json.loads(expected)["programs"]
    print(
        json.dumps(
            {
                "status": "PASS",
                "mode": "WRITE" if args.write else "CHECK",
                "native_semantic_programs": len(programs),
                "local_semantic_handlers": len(LOCAL_SEMANTIC_SKILLS),
                "prepare_only": 0,
                "external_evidence_status": "NOT_RUN",
                "certification_status": "NOT_CERTIFIED",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
