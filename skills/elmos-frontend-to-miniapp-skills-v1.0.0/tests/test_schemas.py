from __future__ import annotations

import json
import unittest

from jsonschema.validators import validator_for

from _support import ROOT
from validate_schemas import validate


class SchemaTests(unittest.TestCase):
    def test_schema_and_fixture_validation(self) -> None:
        result = validate(ROOT)
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["schema_count"], 14)
        self.assertEqual(result["fixture_count"], 14)

    def test_all_schemas_are_draft_2020_12_and_self_valid(self) -> None:
        for path in sorted((ROOT / "schemas").glob("*.schema.json")):
            with self.subTest(schema=path.name):
                schema = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
                validator_for(schema).check_schema(schema)


if __name__ == "__main__":
    unittest.main()
