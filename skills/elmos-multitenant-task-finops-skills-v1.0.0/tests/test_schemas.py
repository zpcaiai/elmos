from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]


class SchemaTests(unittest.TestCase):
    def test_all_schemas_have_valid_examples(self) -> None:
        schemas = sorted((ROOT / "schemas").glob("*.schema.json"))
        self.assertGreaterEqual(len(schemas), 13)
        for schema_path in schemas:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            example_path = ROOT / "examples" / f"{schema_path.name.removesuffix('.schema.json')}.json"
            self.assertTrue(example_path.exists(), example_path)
            example = json.loads(example_path.read_text(encoding="utf-8"))
            errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(example))
            self.assertEqual([], errors, f"{example_path}: {errors}")


if __name__ == "__main__":
    unittest.main()
