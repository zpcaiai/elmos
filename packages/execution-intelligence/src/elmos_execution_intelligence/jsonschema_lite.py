"""A dependency-free JSON Schema validator covering the subset this package uses.

Why this exists: shipping schemas that nothing ever executes is how a contract
silently rots. `jsonschema` is not available in the pinned, offline toolchain the
rest of elmos runs under, so the alternative to this module is an unverified
`schemas/` directory.

Supported keywords: $ref (local file + JSON pointer), type, enum, const,
required, properties, additionalProperties, items, minItems, maxItems,
minProperties, minLength, minimum, maximum, exclusiveMinimum, exclusiveMaximum,
allOf, anyOf, oneOf, not, propertyNames, patternProperties.

Anything outside that set raises UnsupportedKeyword rather than being silently
ignored -- a validator that quietly skips a constraint is worse than no
validator, because it reports success it did not earn.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

SUPPORTED = frozenset({
    "$schema", "$id", "$ref", "$defs", "title", "description", "examples", "default",
    "type", "enum", "const", "required", "properties", "additionalProperties",
    "items", "minItems", "maxItems", "minProperties", "maxProperties", "minLength", "maxLength",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "pattern",
    "allOf", "anyOf", "oneOf", "not", "propertyNames", "patternProperties", "format",
})

TYPE_MAP = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "null": type(None),
}


class UnsupportedKeyword(ValueError):
    """Raised when a schema uses a keyword this validator cannot enforce."""


class SchemaError(ValueError):
    """Raised when a schema file itself is malformed or unreachable."""


def _type_ok(value: Any, expected: str) -> bool:
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "string":
        return isinstance(value, str)
    if expected in TYPE_MAP:
        target = TYPE_MAP[expected]
        if target is dict or target is list:
            return isinstance(value, target)
        return isinstance(value, target)
    raise UnsupportedKeyword(f"unknown type keyword: {expected}")


class Validator:
    """Validates an instance against a schema, resolving local $ref siblings."""

    def __init__(self, schema_dir: str | Path) -> None:
        self.schema_dir = Path(schema_dir)
        self._cache: dict[str, dict[str, Any]] = {}

    def load(self, name: str) -> dict[str, Any]:
        if name not in self._cache:
            path = self.schema_dir / name
            if not path.exists():
                raise SchemaError(f"schema not found: {path}")
            try:
                self._cache[name] = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise SchemaError(f"invalid JSON in schema {path}: {exc}") from exc
        return self._cache[name]

    def _resolve(self, ref: str, current: dict[str, Any],
                 current_name: str) -> tuple[dict[str, Any], dict[str, Any], str]:
        file_part, _, pointer = ref.partition("#")
        if file_part:
            root = self.load(file_part)
            root_name = file_part
        else:
            root = current
            root_name = current_name
        node: Any = root
        for token in [t for t in pointer.split("/") if t]:
            token = token.replace("~1", "/").replace("~0", "~")
            if not isinstance(node, dict) or token not in node:
                raise SchemaError(f"cannot resolve $ref {ref}")
            node = node[token]
        if not isinstance(node, dict):
            raise SchemaError(f"$ref {ref} does not point at a schema object")
        return node, root, root_name

    def validate(self, instance: Any, schema_name: str) -> list[str]:
        schema = self.load(schema_name)
        errors: list[str] = []
        self._check(instance, schema, "$", errors, schema, schema_name)
        return errors

    def validate_inline(self, instance: Any, schema: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        self._check(instance, schema, "$", errors, schema, "<inline>")
        return errors

    def _check(
        self,
        instance: Any,
        schema: dict[str, Any],
        path: str,
        errors: list[str],
        root: dict[str, Any],
        root_name: str,
    ) -> None:
        if not isinstance(schema, dict):
            raise SchemaError(f"schema at {path} is not an object")
        unknown = set(schema) - SUPPORTED
        if unknown:
            raise UnsupportedKeyword(
                f"schema at {path} uses keywords this validator cannot enforce: {sorted(unknown)}"
            )

        if "$ref" in schema:
            target, new_root, new_name = self._resolve(schema["$ref"], root, root_name)
            self._check(instance, target, path, errors, new_root, new_name)
            return

        if "type" in schema:
            expected = schema["type"]
            candidates = expected if isinstance(expected, list) else [expected]
            if not any(_type_ok(instance, candidate) for candidate in candidates):
                errors.append(f"{path}: expected type {expected}, got {type(instance).__name__}")
                return

        if "const" in schema and instance != schema["const"]:
            errors.append(f"{path}: expected const {schema['const']!r}, got {instance!r}")
        if "enum" in schema and instance not in schema["enum"]:
            errors.append(f"{path}: {instance!r} is not one of {schema['enum']}")

        comparisons: tuple[tuple[str, Callable[[float, float], bool]], ...] = (
            ("minimum", lambda v, b: v >= b),
            ("maximum", lambda v, b: v <= b),
            ("exclusiveMinimum", lambda v, b: v > b),
            ("exclusiveMaximum", lambda v, b: v < b),
        )
        for keyword, ok in comparisons:
            if keyword in schema and isinstance(instance, int | float) and not isinstance(instance, bool):
                if not ok(instance, schema[keyword]):
                    errors.append(f"{path}: {instance} violates {keyword}={schema[keyword]}")

        if isinstance(instance, str):
            if "minLength" in schema and len(instance) < schema["minLength"]:
                errors.append(f"{path}: shorter than minLength={schema['minLength']}")
            if "maxLength" in schema and len(instance) > schema["maxLength"]:
                errors.append(f"{path}: longer than maxLength={schema['maxLength']}")
            if "pattern" in schema and not re.search(schema["pattern"], instance):
                errors.append(f"{path}: does not match pattern {schema['pattern']}")

        if isinstance(instance, list):
            if "minItems" in schema and len(instance) < schema["minItems"]:
                errors.append(f"{path}: fewer than minItems={schema['minItems']}")
            if "maxItems" in schema and len(instance) > schema["maxItems"]:
                errors.append(f"{path}: more than maxItems={schema['maxItems']}")
            if "items" in schema:
                for index, item in enumerate(instance):
                    self._check(item, schema["items"], f"{path}[{index}]", errors, root, root_name)

        if isinstance(instance, dict):
            if "minProperties" in schema and len(instance) < schema["minProperties"]:
                errors.append(f"{path}: fewer than minProperties={schema['minProperties']}")
            if "maxProperties" in schema and len(instance) > schema["maxProperties"]:
                errors.append(f"{path}: more than maxProperties={schema['maxProperties']}")
            for key in schema.get("required", []):
                if key not in instance:
                    errors.append(f"{path}: missing required property '{key}'")
            properties = schema.get("properties", {})
            for key, value in instance.items():
                if key in properties:
                    self._check(value, properties[key], f"{path}.{key}", errors, root, root_name)
            pattern_properties = schema.get("patternProperties", {})
            for pattern, subschema in pattern_properties.items():
                for key, value in instance.items():
                    if re.search(pattern, key):
                        self._check(value, subschema, f"{path}.{key}", errors, root, root_name)
            if "propertyNames" in schema:
                for key in instance:
                    self._check(key, schema["propertyNames"], f"{path}.<key {key}>", errors, root, root_name)
            additional = schema.get("additionalProperties")
            if additional is not None:
                known = set(properties)
                extra = [
                    key for key in instance
                    if key not in known
                    and not any(re.search(pattern, key) for pattern in pattern_properties)
                ]
                if additional is False:
                    for key in extra:
                        errors.append(f"{path}: additional property '{key}' is not allowed")
                elif isinstance(additional, dict):
                    for key in extra:
                        self._check(instance[key], additional, f"{path}.{key}", errors, root, root_name)

        for keyword in ("allOf", "anyOf", "oneOf"):
            if keyword not in schema:
                continue
            branches = schema[keyword]
            results = []
            for branch in branches:
                branch_errors: list[str] = []
                self._check(instance, branch, path, branch_errors, root, root_name)
                results.append(branch_errors)
            passing = sum(1 for r in results if not r)
            if keyword == "allOf" and passing != len(branches):
                for r in results:
                    errors.extend(r)
            elif keyword == "anyOf" and passing == 0:
                errors.append(f"{path}: matched none of the {len(branches)} anyOf branches")
            elif keyword == "oneOf" and passing != 1:
                errors.append(f"{path}: matched {passing} oneOf branches, expected exactly 1")

        if "not" in schema:
            negative: list[str] = []
            self._check(instance, schema["not"], path, negative, root, root_name)
            if not negative:
                errors.append(f"{path}: matched a schema it must not match")


def validate_file(instance_path: str | Path, schema_name: str, schema_dir: str | Path) -> list[str]:
    instance = json.loads(Path(instance_path).read_text(encoding="utf-8"))
    return Validator(schema_dir).validate(instance, schema_name)
