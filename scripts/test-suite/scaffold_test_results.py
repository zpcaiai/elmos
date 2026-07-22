#!/usr/bin/env python3
"""Create fail-closed result placeholders without overwriting existing evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _common import ZERO_DIGEST, load_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("suite", nargs="?", default="test-suites/batch1-37-strict")
    args = parser.parse_args()
    root = Path(args.suite)
    catalog = load_json(root / "cases/catalog.json")
    results = root / "results"
    results.mkdir(parents=True, exist_ok=True)
    created = 0
    preserved = 0
    for case in catalog["cases"]:
        path = results / f"{case['id']}.json"
        if path.exists():
            preserved += 1
            continue
        placeholder = {
            "case_id": case["id"],
            "status": "not-run",
            "artifact_digest": ZERO_DIGEST,
            "environment_digest": ZERO_DIGEST,
            "started_at": "",
            "finished_at": "",
            "evidence": [],
        }
        path.write_text(json.dumps(placeholder, indent=2) + "\n", encoding="utf-8")
        created += 1
    print(f"WROTE {created} result placeholders; preserved {preserved} existing results")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
