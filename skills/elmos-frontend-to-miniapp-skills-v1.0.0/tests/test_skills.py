from __future__ import annotations

import unittest

from _support import ROOT
from common import parse_frontmatter
from validate_skills import validate


class SkillTests(unittest.TestCase):
    def test_package_skill_validation(self) -> None:
        result = validate(ROOT)
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["skill_count"], 22)
        self.assertEqual(result["task_count"], 40)

    def test_each_skill_is_self_contained(self) -> None:
        skill_dirs = sorted((ROOT / ".agents" / "skills").iterdir())
        self.assertEqual(len(skill_dirs), 22)
        for skill_dir in skill_dirs:
            with self.subTest(skill=skill_dir.name):
                entry = skill_dir / "SKILL.md"
                frontmatter, body = parse_frontmatter(entry)
                self.assertEqual(frontmatter["name"], skill_dir.name)
                self.assertGreater(len(frontmatter["description"]), 20)
                self.assertGreater(len(body), 500)
                self.assertTrue((skill_dir / "references" / "contract.md").is_file())
                self.assertTrue((skill_dir / "assets" / "output-contract.yaml").is_file())
                self.assertTrue((skill_dir / "examples" / "invocation.md").is_file())


if __name__ == "__main__":
    unittest.main()
