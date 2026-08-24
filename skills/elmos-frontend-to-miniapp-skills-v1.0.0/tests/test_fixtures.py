from __future__ import annotations

import json
import unittest

import yaml

from _support import ROOT


class FixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.index = yaml.safe_load((ROOT / "fixtures" / "index.yaml").read_text(encoding="utf-8"))

    def test_fixture_index_is_one_to_one(self) -> None:
        mappings = self.index["fixtures"]
        self.assertEqual(len(mappings), 14)
        schemas = list(mappings.keys())
        fixtures = list(mappings.values())
        self.assertEqual(len(schemas), len(set(schemas)))
        self.assertEqual(len(fixtures), len(set(fixtures)))

    def test_fixture_json_is_parseable(self) -> None:
        for fixture in self.index["fixtures"].values():
            with self.subTest(fixture=fixture):
                path = ROOT / "fixtures" / fixture
                self.assertTrue(path.is_file())
                self.assertIsInstance(json.loads(path.read_text(encoding="utf-8")), dict)


if __name__ == "__main__":
    unittest.main()
