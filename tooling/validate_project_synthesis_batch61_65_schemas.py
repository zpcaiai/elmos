#!/usr/bin/env python3
"""Validate Batch 61-65 planning Schemas/examples without granting authority."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "elmos-project-synthesis-batch61-65"
PAIRS = {
    "agent-runtime.plan.json": "agent-runtime-v1.schema.json",
    "certification.result.json": "certification-result-v1.schema.json",
    "change-request.alert-escalation.json": "change-request-v1.schema.json",
    "domain-pack.ai-agent-rag.json": "domain-pack-v1.schema.json",
    "requirement-studio.workspace.json": "requirement-studio-workspace-v1.schema.json",
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    errors: list[str] = []
    for example_name, schema_name in PAIRS.items():
        schema_path = PACKAGE / "schemas" / schema_name
        example_path = PACKAGE / "examples" / example_name
        try:
            schema = load(schema_path)
            example = load(example_path)
            Draft202012Validator.check_schema(schema)
            validator = Draft202012Validator(schema, format_checker=FormatChecker())
            for error in validator.iter_errors(example):
                errors.append(f"{example_name}: {error.message}")
            if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
                errors.append(f"{schema_name}: draft must remain 2020-12")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{example_name}/{schema_name}: {exc}")
    certification = load(PACKAGE / "examples/certification.result.json")
    if certification.get("certificate_hash") != "sha256:example":
        errors.append("certification example must retain its unmistakable placeholder hash")
    if certification.get("decision") == "certified" or not certification.get("limitations"):
        errors.append("certification example must remain limited and non-authoritative")
    if errors:
        print("FAIL")
        print("\n".join(errors))
        return 1
    print("PASS: 5 Batch 61-65 Schemas and examples; certification fixture remains planning-only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
