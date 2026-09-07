import json

import pytest
from conftest import ROOT

from elmos_execution_intelligence.jsonschema_lite import (
    SchemaError,
    UnsupportedKeyword,
    Validator,
)

SCHEMAS = ROOT / "schemas"


@pytest.fixture(scope="module")
def validator():
    return Validator(SCHEMAS)


def test_every_shipped_schema_parses_and_uses_only_supported_keywords(validator):
    for path in sorted(SCHEMAS.glob("*.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        # Walking it with an empty object exercises keyword support without
        # asserting the instance is valid.
        try:
            validator.validate_inline({}, schema)
        except UnsupportedKeyword as exc:  # pragma: no cover - failure path
            pytest.fail(f"{path.name}: {exc}")


def test_validator_is_not_vacuous_missing_required(validator):
    errors = validator.validate({}, "envelope.schema.json")
    assert len(errors) == 7
    assert all("missing required property" in error for error in errors)


def test_validator_catches_wrong_type(validator):
    instance = {"mean": "not-a-number", "p50": 1, "p80": 1, "p90": 1,
                "worst_case": 1, "minimum": 1, "maximum": 1}
    errors = validator.validate(instance, "envelope.schema.json")
    assert any("expected type number" in error for error in errors)


def test_validator_catches_additional_properties(validator):
    instance = {"mean": 1, "p50": 1, "p80": 1, "p90": 1, "worst_case": 1,
                "minimum": 1, "maximum": 1, "sneaky": 1}
    errors = validator.validate(instance, "envelope.schema.json")
    assert any("additional property 'sneaky'" in error for error in errors)


def test_validator_catches_const_violation(validator):
    errors = validator.validate_inline({"artifact": "wrong"},
                                       {"type": "object", "properties": {"artifact": {"const": "token-forecast"}}})
    assert any("expected const" in error for error in errors)


def test_validator_catches_bounds_and_enum(validator):
    schema = {"type": "object", "properties": {
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "mode": {"enum": ["a", "b"]},
        "workers": {"type": "number", "exclusiveMinimum": 0},
    }}
    errors = validator.validate_inline({"confidence": 1.5, "mode": "c", "workers": 0}, schema)
    assert len(errors) == 3


def test_validator_follows_cross_file_refs(validator):
    schema = {"type": "object", "properties": {"e": {"$ref": "envelope.schema.json"}}}
    errors = validator.validate_inline({"e": {"mean": 1}}, schema)
    assert any("$.e" in error and "missing required" in error for error in errors)


def test_boolean_is_not_a_number(validator):
    errors = validator.validate_inline({"x": True}, {"type": "object", "properties": {"x": {"type": "number"}}})
    assert errors


def test_unsupported_keyword_is_refused_not_ignored(validator):
    with pytest.raises(UnsupportedKeyword):
        validator.validate_inline({"a": 1}, {"type": "object", "dependentRequired": {"a": ["b"]}})


def test_missing_schema_file_raises(validator):
    with pytest.raises(SchemaError):
        validator.validate({}, "does-not-exist.schema.json")


def test_min_items_and_min_length(validator):
    schema = {"type": "object", "properties": {
        "checks": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}}}}
    assert validator.validate_inline({"checks": []}, schema)
    assert validator.validate_inline({"checks": [""]}, schema)
    assert validator.validate_inline({"checks": ["ok"]}, schema) == []
