from __future__ import annotations

import unittest

import yaml

from _support import ROOT


class TemplateTests(unittest.TestCase):
    def test_yaml_templates_are_parseable(self) -> None:
        paths = sorted((ROOT / "templates").rglob("*.yaml")) + sorted((ROOT / "plans").rglob("*.yaml"))
        self.assertGreaterEqual(len(paths), 10)
        for path in paths:
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                self.assertIsNotNone(yaml.safe_load(path.read_text(encoding="utf-8")))

    def test_target_layout_templates_cover_all_platforms(self) -> None:
        platform_root = ROOT / "templates" / "platforms"
        expected = {"wechat", "alipay", "douyin", "xiaohongshu"}
        actual = {p.name for p in platform_root.iterdir() if p.is_dir()}
        self.assertEqual(actual, expected)
        for platform in expected:
            self.assertTrue((platform_root / platform / "PROJECT-LAYOUT.md").is_file())


if __name__ == "__main__":
    unittest.main()
