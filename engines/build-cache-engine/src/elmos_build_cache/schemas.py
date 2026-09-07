"""JSON Schema registry and validation helpers.

Schema documents are packaged with the library so validation works from a
wheel, a source checkout and a vendored copy alike. ``jsonschema`` is used when
installed; the built-in fallback validator covers the subset the shipped
schemas use (type, required, enum, pattern, minimum, minLength, items,
properties, additionalProperties) and fails closed on anything else.
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path
from typing import Any

from .errors import SchemaInvalid

SCHEMA_DIR = Path(__file__).resolve().parent / "_data" / "schemas"

SCHEMA_NAMES = {
    "action-key": "action-key.schema.json",
    "artifact-manifest": "artifact-manifest.schema.json",
    "cache-affinity-decision": "cache-affinity-decision.schema.json",
    "cache-benchmark-report": "cache-benchmark-report.schema.json",
    "cache-outcome-event": "cache-outcome-event.schema.json",
    "cache-parity-report": "cache-parity-report.schema.json",
    "cache-policy": "cache-policy.schema.json",
    "cache-slo-policy": "cache-slo-policy.schema.json",
    "cache-trace-event": "cache-trace-event.schema.json",
    "checkpoint-manifest": "checkpoint-manifest.schema.json",
    "context-checkpoint": "context-checkpoint.schema.json",
    "context-ledger-event": "context-ledger-event.schema.json",
    "environment-snapshot": "environment-snapshot.schema.json",
    "file-tree-manifest": "file-tree-manifest.schema.json",
    "local-postgres-qualification-receipt": "local-postgres-qualification-receipt.schema.json",
    "prompt-prefix-manifest": "prompt-prefix-manifest.schema.json",
    "provider-cache-profile": "provider-cache-profile.schema.json",
    "run-manifest": "run-manifest.schema.json",
    "stage-contract": "stage-contract.schema.json",
    "staged-file": "staged-file.schema.json",
}


@cache
def load_schema(name: str) -> dict[str, Any]:
    try:
        filename = SCHEMA_NAMES[name]
    except KeyError as exc:
        raise SchemaInvalid(f"unknown schema: {name}", known=sorted(SCHEMA_NAMES)) from exc
    path = SCHEMA_DIR / filename
    if not path.is_file():
        raise SchemaInvalid(f"schema file is missing: {path}")
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return document


def validate(name: str, document: Any) -> None:
    """Raise :class:`SchemaInvalid` when ``document`` violates the schema."""
    schema = load_schema(name)
    try:
        import jsonschema  # type: ignore[import-untyped]
    except ImportError:
        errors = _validate_subset(schema, document, "$")
    else:
        validator = jsonschema.Draft202012Validator(schema)
        errors = [
            f"{'/'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
            for error in validator.iter_errors(document)
        ]
    if errors:
        raise SchemaInvalid(f"{name} document is invalid", schema=name, errors=sorted(errors)[:20])


_SUPPORTED_KEYWORDS = frozenset(
    {
        "$schema",
        "$id",
        "title",
        "description",
        "type",
        "required",
        "properties",
        "additionalProperties",
        "items",
        "enum",
        "pattern",
        "minimum",
        "minLength",
        "maxLength",
        "const",
    }
)

_JSON_TYPES: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "array": (list,),
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "null": (type(None),),
}


def _type_ok(expected: str, value: Any) -> bool:
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    return isinstance(value, _JSON_TYPES[expected])


def _validate_subset(schema: dict[str, Any], value: Any, path: str) -> list[str]:
    unsupported = sorted(set(schema) - _SUPPORTED_KEYWORDS)
    if unsupported:
        return [f"{path}: fallback validator cannot evaluate keywords {unsupported}"]

    errors: list[str] = []
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: expected constant {schema['const']!r}")
    if "type" in schema:
        expected = schema["type"]
        options = expected if isinstance(expected, list) else [expected]
        if not any(_type_ok(option, value) for option in options):
            errors.append(f"{path}: expected type {expected}, got {type(value).__name__}")
            return errors
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} is not one of {schema['enum']}")
    if isinstance(value, str):
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{path}: {value!r} does not match {schema['pattern']}")
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: shorter than minLength {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path}: longer than maxLength {schema['maxLength']}")
    if isinstance(value, int | float) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: below minimum {schema['minimum']}")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: missing required property {key!r}")
        properties = schema.get("properties", {})
        for key, sub_value in value.items():
            if key in properties:
                errors.extend(_validate_subset(properties[key], sub_value, f"{path}/{key}"))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}: additional property {key!r} is not allowed")
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            errors.extend(_validate_subset(schema["items"], item, f"{path}/{index}"))
    return errors
