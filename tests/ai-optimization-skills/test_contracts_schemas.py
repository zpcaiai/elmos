from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
PACKAGE_DIR = ROOT / "skills/elmos-ai-optimization-skills-v1.0.0"


class ContractsSchemasTest(unittest.TestCase):
    def test_all_14_schemas_and_examples(self) -> None:
        index_file = PACKAGE_DIR / "contracts/examples/index.json"
        self.assertTrue(index_file.is_file())
        examples_index = json.loads(index_file.read_text())
        self.assertEqual(len(examples_index), 14)

        for item in examples_index:
            schema_file = PACKAGE_DIR / item["schema"]
            example_file = PACKAGE_DIR / item["example"]
            self.assertTrue(schema_file.is_file(), f"Schema missing: {schema_file}")
            self.assertTrue(example_file.is_file(), f"Example missing: {example_file}")

            schema = json.loads(schema_file.read_text())
            example = json.loads(example_file.read_text())

            Draft202012Validator.check_schema(schema)
            validator = Draft202012Validator(schema)
            validator.validate(example)


if __name__ == "__main__":
    unittest.main()
