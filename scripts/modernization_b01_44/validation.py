#!/usr/bin/env python3
"""Draft 2020-12 validation at the trust boundary.

``jsonschema`` is used when installed; otherwise a conservative built-in
validator covers the subset the Batch schemas actually use.  The built-in path
is deliberately *stricter* than the library on unknown keywords: an unmodelled
keyword raises instead of being ignored, so a schema can never silently stop
enforcing something.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from scripts.modernization_b01_44.errors import SchemaViolation

try:  # pragma: no cover - import shape depends on environment
    from jsonschema import Draft202012Validator  # type: ignore

    _HAVE_JSONSCHEMA = True
except Exception:  # pragma: no cover
    Draft202012Validator = None  # type: ignore
    _HAVE_JSONSCHEMA = False

SUPPORTED_KEYWORDS = {
    "$schema",
    "$id",
    "title",
    "description",
    "type",
    "required",
    "properties",
    "additionalProperties",
    "enum",
    "const",
    "pattern",
    "items",
    "minItems",
    "maxItems",
    "minLength",
    "format",
}

_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int,),
    "boolean": bool,
    "null": type(None),
}


def _check_type(value: Any, expected: Any, path: str) -> None:
    names = expected if isinstance(expected, list) else [expected]
    for name in names:
        if name not in _TYPES:
            raise SchemaViolation(f"unsupported type keyword {name!r}", path=path)
        python_type = _TYPES[name]
        if name == "integer" and isinstance(value, bool):
            continue
        if name == "boolean" and not isinstance(value, bool):
            continue
        if isinstance(value, python_type):
            if name in ("object", "array", "string", "integer", "number") and isinstance(value, bool):
                continue
            return
    raise SchemaViolation(f"expected type {expected!r}", path=path, actual=type(value).__name__)


def _check_format(value: Any, fmt: str, path: str) -> None:
    if fmt != "date-time" or not isinstance(value, str):
        return
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        datetime.fromisoformat(text)
    except ValueError:
        raise SchemaViolation("value is not an RFC 3339 date-time", path=path, value=value) from None


def _validate(value: Any, schema: dict[str, Any], path: str) -> None:
    unknown = set(schema) - SUPPORTED_KEYWORDS
    if unknown:
        raise SchemaViolation(
            "schema uses keywords the built-in validator does not enforce",
            path=path,
            keywords=sorted(unknown),
        )

    if "const" in schema and value != schema["const"]:
        raise SchemaViolation("value does not match const", path=path, expected=schema["const"])
    if "enum" in schema and value not in schema["enum"]:
        raise SchemaViolation("value is not in enum", path=path, value=value)
    if "type" in schema:
        _check_type(value, schema["type"], path)
    if "pattern" in schema and isinstance(value, str):
        if re.search(schema["pattern"], value) is None:
            raise SchemaViolation("value does not match pattern", path=path, value=value)
    if "minLength" in schema and isinstance(value, str) and len(value) < schema["minLength"]:
        raise SchemaViolation("value is shorter than minLength", path=path)
    if "format" in schema:
        _check_format(value, schema["format"], path)

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                raise SchemaViolation("required property is absent", path=path, property=name)
        if schema.get("additionalProperties") is False:
            extra = sorted(set(value) - set(properties))
            if extra:
                raise SchemaViolation(
                    "object carries properties the schema does not declare",
                    path=path,
                    unknown_properties=extra,
                )
        for name, subschema in properties.items():
            if name in value:
                _validate(value[name], subschema, f"{path}.{name}")

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise SchemaViolation("array is shorter than minItems", path=path, length=len(value))
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise SchemaViolation("array is longer than maxItems", path=path, length=len(value))
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate(item, item_schema, f"{path}[{index}]")


def validate(value: Any, schema: dict[str, Any], *, label: str = "$") -> None:
    """Raise :class:`SchemaViolation` when ``value`` does not satisfy ``schema``."""

    if _HAVE_JSONSCHEMA:
        validator = Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(value), key=lambda e: list(e.absolute_path))
        if errors:
            first = errors[0]
            pointer = "/".join(str(part) for part in first.absolute_path)
            raise SchemaViolation(
                first.message,
                path=f"{label}/{pointer}" if pointer else label,
                schema_id=schema.get("$id"),
            )
        return
    _validate(value, schema, label)


def is_valid(value: Any, schema: dict[str, Any]) -> bool:
    try:
        validate(value, schema)
    except SchemaViolation:
        return False
    return True
