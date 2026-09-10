#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker

def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument("root", nargs="?", default="."); args = p.parse_args()
    root = Path(args.root).resolve(); errors = []; count = 0
    for schema_path in sorted((root / "contracts/schemas").glob("*.schema.json")):
        name = schema_path.name.removesuffix(".schema.json")
        example_path = root / "contracts/examples" / f"{name}.example.json"
        if not example_path.exists(): errors.append(f"missing example for {name}"); continue
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8")); example = json.loads(example_path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            Draft202012Validator(schema, format_checker=FormatChecker()).validate(example)
            count += 1
        except Exception as exc: errors.append(f"{name}: {exc}")
    print(json.dumps({"status": "PASS" if not errors else "FAIL", "validated": count, "errors": errors}, ensure_ascii=False, indent=2))
    return 1 if errors else 0
if __name__ == "__main__": raise SystemExit(main())
