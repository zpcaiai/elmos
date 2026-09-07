from __future__ import annotations

import unittest

import yaml

from _support import ROOT
from validate_skills import validate


class DependencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = yaml.safe_load((ROOT / "skill-manifest.yaml").read_text(encoding="utf-8"))
        cls.by_name = {item["name"]: item for item in cls.manifest["skills"]}

    def test_dependencies_exist_and_graph_is_acyclic(self) -> None:
        result = validate(ROOT)
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(len(result["topological_order"]), len(self.by_name))

    def test_target_generators_depend_on_core_plans(self) -> None:
        expected = {
            "miniapp-component-mapping-engine",
            "miniapp-state-event-lifecycle-converter",
            "miniapp-style-layout-converter",
            "miniapp-third-party-dependency-migrator",
        }
        for name in [
            "wechat-miniapp-codegen",
            "alipay-miniapp-codegen",
            "douyin-miniapp-codegen",
            "xiaohongshu-miniapp-codegen",
        ]:
            with self.subTest(skill=name):
                self.assertTrue(expected.issubset(set(self.by_name[name]["depends_on"])))


if __name__ == "__main__":
    unittest.main()
