from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
VALIDATOR_PATH = REPOSITORY_ROOT / "scripts/batch35/_local_jsonschema.py"
SPEC = importlib.util.spec_from_file_location(
    "batch35_local_jsonschema_for_tests", VALIDATOR_PATH
)
assert SPEC is not None and SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)


class Batch35LocalJsonSchemaTests(unittest.TestCase):
    def test_nested_closed_object_and_array_validation(self) -> None:
        schema = {
            "type": "object",
            "required": ["items"],
            "properties": {
                "items": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "required": ["name"],
                        "properties": {
                            "name": {
                                "type": "string",
                                "minLength": 2,
                                "pattern": "^[a-z]+$",
                            }
                        },
                        "additionalProperties": False,
                    },
                }
            },
            "additionalProperties": False,
        }
        validator.validate({"items": [{"name": "safe"}]}, schema)
        with self.assertRaises(validator.ValidationError):
            validator.validate({"items": [{"name": "X", "extra": True}]}, schema)

    def test_boolean_is_not_an_integer_and_const_is_type_exact(self) -> None:
        with self.assertRaises(validator.ValidationError):
            validator.validate(True, {"type": "integer"})
        with self.assertRaises(validator.ValidationError):
            validator.validate(True, {"const": 1})

    def test_unknown_keywords_and_invalid_schema_fail_closed(self) -> None:
        with self.assertRaises(validator.SchemaError):
            validator.validate("value", {"type": "string", "unknown": True})
        with self.assertRaises(validator.SchemaError):
            validator.validate([], {"type": "array", "minItems": True})

    def test_false_boolean_schema_rejects(self) -> None:
        with self.assertRaises(validator.ValidationError):
            validator.validate({}, False)


if __name__ == "__main__":
    unittest.main()
