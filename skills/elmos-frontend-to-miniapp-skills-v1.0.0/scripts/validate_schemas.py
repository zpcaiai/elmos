#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from common import package_root


def validate(root: Path) -> dict:
    errors: list[str] = []
    schemas_dir = root / "schemas"
    fixtures_dir = root / "fixtures"
    index = yaml.safe_load((fixtures_dir / "index.yaml").read_text(encoding="utf-8"))
    mapping: dict[str, str] = index["fixtures"]
    schema_files = sorted(schemas_dir.glob("*.schema.json"))

    for schema_path in schema_files:
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
        except Exception as exc:
            errors.append(f"{schema_path.name}: invalid schema: {exc}")
            continue

        fixture_name = mapping.get(schema_path.name)
        if not fixture_name:
            errors.append(f"{schema_path.name}: no fixture mapping")
            continue
        fixture_path = fixtures_dir / fixture_name
        if not fixture_path.exists():
            errors.append(f"{schema_path.name}: missing fixture {fixture_name}")
            continue
        try:
            instance = json.loads(fixture_path.read_text(encoding="utf-8"))
            validator = Draft202012Validator(schema, format_checker=FormatChecker())
            validation_errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
            for err in validation_errors:
                path = ".".join(str(x) for x in err.path) or "<root>"
                errors.append(f"{fixture_name}:{path}: {err.message}")
        except Exception as exc:
            errors.append(f"{fixture_name}: {exc}")

    for schema_name in mapping:
        if not (schemas_dir / schema_name).exists():
            errors.append(f"Fixture index references missing schema {schema_name}")

    return {
        "ok": not errors,
        "errors": errors,
        "schema_count": len(schema_files),
        "fixture_count": len(mapping),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = (args.root or package_root()).resolve()
    result = validate(root)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for error in result["errors"]:
            print(f"ERROR: {error}")
        print(f"schemas={result['schema_count']} fixtures={result['fixture_count']} ok={result['ok']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
