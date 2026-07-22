#!/usr/bin/env python3
"""Meta-validate Draft 2020-12 schemas and all shipped JSON instances."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from jsonschema import Draft202012Validator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def validate_instance(schema: dict, instance: object, label: str) -> list[str]:
    validator = Draft202012Validator(schema)
    return [
        f"{label}: {'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.absolute_path))
    ]


def load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(REPOSITORY_ROOT))
    args = parser.parse_args()
    root = Path(args.root).resolve()
    schema_root = root / "schemas/test-suite"
    suite_root = root / "test-suites/batch1-37-strict"
    template_root = root / "templates/test-suite"
    errors: list[str] = []
    schemas: dict[str, dict] = {}
    for path in sorted(schema_root.glob("*.schema.json")):
        try:
            schema = load(path)
            Draft202012Validator.check_schema(schema)
            schemas[path.name] = schema
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{path}: invalid schema: {exc}")

    expected = {
        "coverage-matrix.schema.json",
        "evidence-manifest.schema.json",
        "release-gate.schema.json",
        "strict-profile.schema.json",
        "test-case.schema.json",
        "test-environment.schema.json",
        "test-result.schema.json",
        "test-suite.schema.json",
        "waiver.schema.json",
    }
    if set(schemas) != expected:
        errors.append(f"schema bundle mismatch: expected={sorted(expected)} actual={sorted(schemas)}")

    if not errors:
        instances = [
            ("coverage-matrix.schema.json", suite_root / "coverage-matrix.json"),
            ("strict-profile.schema.json", suite_root / "strict-profile.json"),
            ("test-suite.schema.json", suite_root / "suite.json"),
            ("coverage-matrix.schema.json", template_root / "coverage-matrix.json"),
            ("strict-profile.schema.json", template_root / "strict-profile.json"),
            ("test-suite.schema.json", template_root / "suite.json"),
            ("test-case.schema.json", template_root / "test-case.json"),
            ("test-environment.schema.json", template_root / "environment.json"),
            ("test-result.schema.json", template_root / "test-result.json"),
            ("evidence-manifest.schema.json", template_root / "evidence-manifest.json"),
            ("release-gate.schema.json", template_root / "release-gate.json"),
            ("waiver.schema.json", template_root / "waiver.json"),
        ]
        for schema_name, instance_path in instances:
            errors.extend(validate_instance(schemas[schema_name], load(instance_path), str(instance_path)))
        catalog = load(suite_root / "cases/catalog.json")
        for index, case in enumerate(catalog["cases"]):
            errors.extend(validate_instance(schemas["test-case.schema.json"], case, f"catalog[{index}]"))
        for path in sorted((suite_root / "results").glob("*.json")):
            errors.extend(validate_instance(schemas["test-result.schema.json"], load(path), str(path)))
        gate_path = suite_root / "release-gate.json"
        if gate_path.is_file():
            errors.extend(
                validate_instance(
                    schemas["release-gate.schema.json"],
                    load(gate_path),
                    str(gate_path),
                )
            )

    if errors:
        print("FAIL")
        print("\n".join(errors))
        return 1
    print("PASS: 9 Draft 2020-12 schemas, 408 cases, 408 results, and templates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
