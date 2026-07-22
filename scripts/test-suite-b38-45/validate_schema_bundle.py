#!/usr/bin/env python3
"""Validate strict Schemas and all checked-in Batch 38-45 controls/results."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "schemas/test-suite-b38-45"
SUITE = ROOT / "test-suites/batch38-45-strict"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate(schema_name: str, document, label: str, errors: list[str]) -> None:
    schema = load(SCHEMAS / schema_name)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for error in sorted(validator.iter_errors(document), key=lambda item: list(item.path)):
        errors.append(f"{label}: {error.message}")


def main() -> int:
    errors: list[str] = []
    schema_files = sorted(SCHEMAS.glob("*.json"))
    if len(schema_files) != 11:
        errors.append(f"expected 11 Schemas, found {len(schema_files)}")
    for path in schema_files:
        try:
            Draft202012Validator.check_schema(load(path))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{path.name}: invalid Schema: {exc}")
    validate("suite.schema.json", load(SUITE / "suite.json"), "suite.json", errors)
    validate("strict-profile.schema.json", load(SUITE / "strict-profile.json"), "strict-profile.json", errors)
    validate("release-gate.schema.json", load(SUITE / "release-gate.json"), "release-gate.json", errors)
    coverage = load(SUITE / "coverage-matrix.json")
    validate("coverage-matrix.schema.json", coverage, "coverage-matrix.json", errors)
    catalog = load(SUITE / "cases/catalog.json")
    for case in catalog["cases"]:
        validate("case.schema.json", case, case["case_id"], errors)
    jsonl = [json.loads(line) for line in (SUITE / "cases/catalog.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    if jsonl != catalog["cases"]:
        errors.append("catalog.jsonl differs from canonical catalog.json")
    for path in sorted((SUITE / "results").glob("*.json")):
        validate("result.schema.json", load(path), str(path.relative_to(SUITE)), errors)
    if len(list((SUITE / "results").glob("*.json"))) != 400:
        errors.append("result directory must contain exactly 400 JSON files")
    validate("result.schema.json", load(ROOT / "templates/test-suite-b38-45/result.json"), "result template", errors)
    validate("release-gate.schema.json", load(ROOT / "templates/test-suite-b38-45/release-gate.json"), "release gate template", errors)
    if errors:
        print("FAIL")
        print("\n".join(errors))
        return 1
    print("PASS: 11 strict Schemas and every checked-in control/result")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
