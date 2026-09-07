"""Dependency-free validator for the closed Batch 35 pack schemas.

The repository's generic Batch 35 pack schemas intentionally use a small,
closed subset of JSON Schema 2020-12.  Qualification runs with credentials and
user package caches removed, so the gate cannot depend on an implicit network
install.  This module validates exactly that subset and rejects unknown schema
keywords instead of silently weakening validation.
"""

from __future__ import annotations

import math
import re
from typing import Any


class SchemaError(ValueError):
    """The schema uses an invalid or unsupported construct."""


class ValidationError(ValueError):
    """The instance does not satisfy the schema."""


class _Exceptions:
    SchemaError = SchemaError
    ValidationError = ValidationError


exceptions = _Exceptions()

_ANNOTATIONS = frozenset({"$id", "$schema", "description"})
_KEYWORDS = frozenset(
    {
        "type",
        "required",
        "properties",
        "additionalProperties",
        "items",
        "minItems",
        "minLength",
        "minimum",
        "pattern",
        "enum",
        "const",
    }
)
_JSON_TYPES = frozenset(
    {"array", "boolean", "integer", "null", "number", "object", "string"}
)


def _json_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _json_equal(a, b) for a, b in zip(left, right, strict=True)
        )
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            _json_equal(left[key], right[key]) for key in left
        )
    return left == right


def _matches_type(instance: Any, expected: str) -> bool:
    if expected == "null":
        return instance is None
    if expected == "boolean":
        return isinstance(instance, bool)
    if expected == "integer":
        return isinstance(instance, int) and not isinstance(instance, bool)
    if expected == "number":
        return (
            isinstance(instance, (int, float))
            and not isinstance(instance, bool)
            and math.isfinite(instance)
        )
    if expected == "string":
        return isinstance(instance, str)
    if expected == "array":
        return isinstance(instance, list)
    if expected == "object":
        return isinstance(instance, dict)
    raise SchemaError(f"unsupported JSON type: {expected!r}")


def _schema_error(message: str, path: str) -> SchemaError:
    return SchemaError(f"{path}: {message}")


def _validation_error(message: str, path: str) -> ValidationError:
    return ValidationError(f"{path}: {message}")


def _validate(instance: Any, schema: Any, path: str) -> None:
    if isinstance(schema, bool):
        if not schema:
            raise _validation_error("boolean schema is false", path)
        return
    if not isinstance(schema, dict):
        raise _schema_error("schema must be an object or boolean", path)

    unknown = sorted(set(schema) - _ANNOTATIONS - _KEYWORDS)
    if unknown:
        raise _schema_error(
            f"unsupported schema keyword(s): {', '.join(unknown)}", path
        )

    expected_type = schema.get("type")
    if expected_type is not None:
        if isinstance(expected_type, str):
            expected_types = [expected_type]
        elif (
            isinstance(expected_type, list)
            and expected_type
            and all(isinstance(item, str) for item in expected_type)
            and len(set(expected_type)) == len(expected_type)
        ):
            expected_types = expected_type
        else:
            raise _schema_error("type must be a string or unique string array", path)
        invalid_types = sorted(set(expected_types) - _JSON_TYPES)
        if invalid_types:
            raise _schema_error(
                f"unsupported JSON type(s): {', '.join(invalid_types)}", path
            )
        if not any(_matches_type(instance, item) for item in expected_types):
            raise _validation_error(
                f"expected type {' or '.join(expected_types)}", path
            )

    if "const" in schema and not _json_equal(instance, schema["const"]):
        raise _validation_error("value does not match const", path)

    if "enum" in schema:
        options = schema["enum"]
        if not isinstance(options, list) or not options:
            raise _schema_error("enum must be a non-empty array", path)
        if not any(_json_equal(instance, option) for option in options):
            raise _validation_error("value is not in enum", path)

    if "pattern" in schema:
        pattern = schema["pattern"]
        if not isinstance(pattern, str):
            raise _schema_error("pattern must be a string", path)
        try:
            compiled = re.compile(pattern)
        except re.error as exc:
            raise _schema_error(f"invalid pattern: {exc}", path) from exc
        if isinstance(instance, str) and compiled.search(instance) is None:
            raise _validation_error("string does not match pattern", path)

    if "minLength" in schema:
        minimum_length = schema["minLength"]
        if (
            not isinstance(minimum_length, int)
            or isinstance(minimum_length, bool)
            or minimum_length < 0
        ):
            raise _schema_error("minLength must be a non-negative integer", path)
        if isinstance(instance, str) and len(instance) < minimum_length:
            raise _validation_error("string is shorter than minLength", path)

    if "minimum" in schema:
        minimum = schema["minimum"]
        if (
            not isinstance(minimum, (int, float))
            or isinstance(minimum, bool)
            or not math.isfinite(minimum)
        ):
            raise _schema_error("minimum must be a finite number", path)
        if (
            isinstance(instance, (int, float))
            and not isinstance(instance, bool)
            and instance < minimum
        ):
            raise _validation_error("number is smaller than minimum", path)

    if "minItems" in schema:
        minimum_items = schema["minItems"]
        if (
            not isinstance(minimum_items, int)
            or isinstance(minimum_items, bool)
            or minimum_items < 0
        ):
            raise _schema_error("minItems must be a non-negative integer", path)
        if isinstance(instance, list) and len(instance) < minimum_items:
            raise _validation_error("array has fewer than minItems", path)

    if "items" in schema:
        item_schema = schema["items"]
        if not isinstance(item_schema, (dict, bool)):
            raise _schema_error("items must be a schema", path)
        if isinstance(instance, list):
            for index, item in enumerate(instance):
                _validate(item, item_schema, f"{path}[{index}]")

    properties = schema.get("properties", {})
    if not isinstance(properties, dict) or not all(
        isinstance(key, str) and isinstance(value, (dict, bool))
        for key, value in properties.items()
    ):
        raise _schema_error("properties must map strings to schemas", path)

    required = schema.get("required", [])
    if (
        not isinstance(required, list)
        or not all(isinstance(item, str) for item in required)
        or len(set(required)) != len(required)
    ):
        raise _schema_error("required must be a unique string array", path)

    additional = schema.get("additionalProperties", True)
    if not isinstance(additional, (bool, dict)):
        raise _schema_error("additionalProperties must be boolean or a schema", path)

    if isinstance(instance, dict):
        missing = [key for key in required if key not in instance]
        if missing:
            raise _validation_error(
                f"required property missing: {', '.join(sorted(missing))}", path
            )
        for key, value in instance.items():
            child_path = f"{path}.{key}"
            if key in properties:
                _validate(value, properties[key], child_path)
            elif additional is False:
                raise _validation_error("additional property is forbidden", child_path)
            elif isinstance(additional, dict):
                _validate(value, additional, child_path)


def validate(instance: Any, schema: Any) -> None:
    """Validate an instance against the exact closed Batch 35 subset."""

    _validate(instance, schema, "$")

