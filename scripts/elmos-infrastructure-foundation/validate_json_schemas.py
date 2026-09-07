#!/usr/bin/env python3
"""Validate JSON Schemas and all mapped example fixtures without network access."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

try:
    from jsonschema import Draft202012Validator, FormatChecker
    from referencing import Registry, Resource
except ImportError:
    print("ERROR: jsonschema and referencing are required. Install requirements-dev.txt.", file=sys.stderr)
    raise SystemExit(2)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=None)
    args = parser.parse_args()
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    schema_dir = root / "schemas"
    fixture_dir = root / "tests" / "fixtures"
    errors: list[str] = []
    schemas = {}

    for path in sorted(schema_dir.glob("*.schema.json")):
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            schemas[path.name] = schema
        except Exception as exc:
            errors.append(f"{path.name}: invalid schema: {exc}")

    resources = []
    for name, schema in schemas.items():
        if "$id" in schema:
            resources.append((schema["$id"], Resource.from_contents(schema)))
    registry = Registry().with_resources(resources)

    fixture_map = json.loads((fixture_dir / "fixture-map.json").read_text(encoding="utf-8"))
    validated = 0
    for fixture_name, schema_name in sorted(fixture_map.items()):
        try:
            instance = json.loads((fixture_dir / fixture_name).read_text(encoding="utf-8"))
            schema = schemas[schema_name]
            validator = Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())
            instance_errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
            if instance_errors:
                for err in instance_errors:
                    loc = "/".join(str(x) for x in err.path)
                    errors.append(f"{fixture_name} at {loc or '<root>'}: {err.message}")
            else:
                validated += 1
        except Exception as exc:
            errors.append(f"{fixture_name}: validation setup failed: {exc}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"FAIL: {len(errors)} schema/fixture problem(s)", file=sys.stderr)
        return 1
    print(f"PASS: {len(schemas)} JSON Schemas are valid Draft 2020-12 schemas")
    print(f"PASS: {validated} mapped fixtures validate")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
