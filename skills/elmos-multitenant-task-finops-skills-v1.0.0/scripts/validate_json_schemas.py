#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    errors: list[str] = []
    examples = sorted((ROOT / "examples").glob("*.json"))
    if not examples:
        errors.append("no JSON examples found")

    for example_path in examples:
        schema_path = ROOT / "schemas" / f"{example_path.stem}.schema.json"
        if not schema_path.exists():
            errors.append(f"missing schema for {example_path.name}")
            continue
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            instance = json.loads(example_path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            validator = Draft202012Validator(schema, format_checker=FormatChecker())
            for err in sorted(validator.iter_errors(instance), key=lambda e: list(e.path)):
                location = "/".join(str(p) for p in err.path) or "<root>"
                errors.append(f"{example_path.name}:{location}: {err.message}")
        except Exception as exc:  # validation tool must report every file
            errors.append(f"{example_path.name}: {exc}")

    if errors:
        print("JSON Schema validation FAILED", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"JSON Schema validation PASS — {len(examples)} examples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
