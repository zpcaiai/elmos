#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reference-implementation"))

from elmos_cache_ref.parity import evaluate_metrics


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate an ELMOS cache parity observation fixture against v1.2.0 gates."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    document = json.loads(args.input.read_text(encoding="utf-8"))
    result = evaluate_metrics(document["metrics"])
    output = {
        "schema_version": "1.2.0",
        "subject": document.get("subject", {}),
        "metrics": document["metrics"],
        **result,
        "limitations": [
            "This evaluator checks supplied observations; production certification also requires the scenario runner, raw evidence, security/chaos tests, and signed fingerprints."
        ],
    }
    serialized = json.dumps(output, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    if not result["mandatory_pass"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
