from __future__ import annotations

import unittest

import yaml

from _support import ROOT


class DocumentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = yaml.safe_load((ROOT / "skill-manifest.yaml").read_text(encoding="utf-8"))

    def test_required_docs_exist_and_are_nontrivial(self) -> None:
        for rel in self.manifest["required_docs"]:
            with self.subTest(document=rel):
                path = ROOT / rel
                self.assertTrue(path.is_file())
                self.assertGreater(len(path.read_text(encoding="utf-8")), 400)

    def test_architecture_names_four_target_adapters(self) -> None:
        text = (ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8").lower()
        for platform in ["wechat", "alipay", "douyin", "xiaohongshu"]:
            self.assertIn(platform, text)

    def test_acceptance_gates_prohibit_silent_drop(self) -> None:
        text = (ROOT / "docs" / "ACCEPTANCE-GATES.md").read_text(encoding="utf-8")
        self.assertIn("无说明删除", text)
        self.assertIn("100%", text)


if __name__ == "__main__":
    unittest.main()
