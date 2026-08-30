"""Small, dependency-free JSON Schema validator for offline gate checks.

The Batch 35 validator normally uses the ``jsonschema`` distribution.  Local
qualification deliberately removes network access, so a clean checkout must
still be able to validate its repository-owned pack.  This module implements
the JSON Schema vocabulary used by the checked-in Batch 35 schemas and keeps
the same ``validate``/``exceptions`` surface used by the external package.
It is not a general-purpose replacement for the dependency in other tools.
"""

from __future__ import annotations

from datetime import datetime
import json
import re
from typing import Any, Mapping


class SchemaError(ValueError):
    """The schema itself cannot be evaluated by this bounded validator."""


class ValidationError(ValueError):
    """The instance does not satisfy the schema."""


class _Exceptions:
    SchemaError = SchemaError
    ValidationError = ValidationError


exceptions = _Exceptions()


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    raise TypeError(f"unsupported JSON value type: {type(value).__name__}")


def _same_json(left: Any, right: Any) -> bool:
    if _json_type(left) != _json_type(right):
        return False
    return left == right


def _resolve_ref(root: Mapping[str, Any], reference: str) -> Any:
    if not isinstance(reference, str) or not reference.startswith("#/"):
        raise SchemaError(f"unsupported schema reference: {reference!r}")
    current: Any = root
    for raw_part in reference[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, Mapping) or part not in current:
            raise SchemaError(f"unresolvable schema reference: {reference!r}")
        current = current[part]
    return current


def _check_format(value: str, name: str) -> bool:
    if name == "date-time":
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return False
        return "T" in value or "t" in value
    if name == "uri":
        return bool(re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", value))
    return True


def _validate(
    value: Any,
    schema: Any,
    path: str,
    root: Mapping[str, Any],
) -> None:
    if schema is True:
        return
    if schema is False:
        raise ValidationError(f"{path} is forbidden by the schema")
    if not isinstance(schema, Mapping):
        raise SchemaError(f"{path}: schema must be an object or boolean")

    if "$ref" in schema:
        _validate(value, _resolve_ref(root, schema["$ref"]), path, root)

    if "allOf" in schema:
        for index, option in enumerate(schema["allOf"]):
            _validate(value, option, f"{path}.allOf[{index}]", root)

    if "oneOf" in schema:
        matches = 0
        for option in schema["oneOf"]:
            try:
                _validate(value, option, path, root)
            except (ValidationError, SchemaError):
                continue
            matches += 1
        if matches != 1:
            raise ValidationError(f"{path} matches {matches} oneOf branches")

    if "anyOf" in schema:
        if not any(
            _matches(value, option, path, root) for option in schema["anyOf"]
        ):
            raise ValidationError(f"{path} matches no anyOf branch")

    if "not" in schema and _matches(value, schema["not"], path, root):
        raise ValidationError(f"{path} matches a forbidden schema")

    expected = schema.get("type")
    if expected is not None:
        allowed = [expected] if isinstance(expected, str) else expected
        if not isinstance(allowed, list) or not all(
            isinstance(item, str) for item in allowed
        ):
            raise SchemaError(f"{path}.type must be a string or array of strings")
        actual = _json_type(value)
        if actual not in allowed and not (actual == "integer" and "number" in allowed):
            raise ValidationError(
                f"{path} has type {actual!r}, expected {allowed!r}"
            )

    if "enum" in schema:
        if not isinstance(schema["enum"], list) or not any(
            _same_json(value, candidate) for candidate in schema["enum"]
        ):
            raise ValidationError(f"{path} is not one of the allowed values")
    if "const" in schema and not _same_json(value, schema["const"]):
        raise ValidationError(f"{path} does not equal the required constant")

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            raise ValidationError(f"{path} is shorter than minLength")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise ValidationError(f"{path} is longer than maxLength")
        if "pattern" in schema:
            try:
                matches = re.search(schema["pattern"], value)
            except re.error as exc:
                raise SchemaError(f"{path}.pattern is invalid: {exc}") from exc
            if matches is None:
                raise ValidationError(f"{path} does not match pattern")
        if "format" in schema and not _check_format(value, schema["format"]):
            raise ValidationError(f"{path} does not match format {schema['format']!r}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise ValidationError(f"{path} is below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise ValidationError(f"{path} is above maximum")

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise ValidationError(f"{path} has too few items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise ValidationError(f"{path} has too many items")
        if schema.get("uniqueItems"):
            encoded = [json.dumps(item, sort_keys=True, separators=(",", ":")) for item in value]
            if len(encoded) != len(set(encoded)):
                raise ValidationError(f"{path} contains duplicate items")
        items = schema.get("items")
        if isinstance(items, list):
            for index, item_schema in enumerate(items):
                if index < len(value):
                    _validate(value[index], item_schema, f"{path}[{index}]", root)
        elif items is not None:
            for index, item in enumerate(value):
                _validate(item, items, f"{path}[{index}]", root)

    if isinstance(value, Mapping):
        required = schema.get("required", [])
        if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
            raise SchemaError(f"{path}.required must be an array of strings")
        missing = [item for item in required if item not in value]
        if missing:
            raise ValidationError(f"{path} is missing required properties: {missing}")

        properties = schema.get("properties", {})
        if not isinstance(properties, Mapping):
            raise SchemaError(f"{path}.properties must be an object")
        patterns = schema.get("patternProperties", {})
        if not isinstance(patterns, Mapping):
            raise SchemaError(f"{path}.patternProperties must be an object")
        for key, item in value.items():
            matched = False
            if key in properties:
                _validate(item, properties[key], f"{path}.{key}", root)
                matched = True
            for pattern, item_schema in patterns.items():
                try:
                    pattern_matches = re.search(pattern, key) is not None
                except re.error as exc:
                    raise SchemaError(f"{path}.patternProperties is invalid: {exc}") from exc
                if pattern_matches:
                    _validate(item, item_schema, f"{path}.{key}", root)
                    matched = True
            if not matched and "additionalProperties" in schema:
                additional = schema["additionalProperties"]
                if additional is False:
                    raise ValidationError(f"{path} has unexpected property {key!r}")
                if additional is not True:
                    _validate(item, additional, f"{path}.{key}", root)
        if "minProperties" in schema and len(value) < schema["minProperties"]:
            raise ValidationError(f"{path} has too few properties")
        if "maxProperties" in schema and len(value) > schema["maxProperties"]:
            raise ValidationError(f"{path} has too many properties")


def _matches(value: Any, schema: Any, path: str, root: Mapping[str, Any]) -> bool:
    try:
        _validate(value, schema, path, root)
    except (ValidationError, SchemaError):
        return False
    return True


def validate(instance: Any, schema: Mapping[str, Any]) -> None:
    """Validate one JSON instance against one repository-owned schema."""

    if not isinstance(schema, Mapping):
        raise SchemaError("root schema must be an object")
    _validate(instance, schema, "$", schema)
