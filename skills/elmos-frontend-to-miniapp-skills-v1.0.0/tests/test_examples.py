from __future__ import annotations

import unittest

import yaml

from _support import ROOT


class ExampleTests(unittest.TestCase):
    def test_examples_cover_vue_react_flutter_and_multi_target(self) -> None:
        examples = {
            "vue3-todo": "vue3",
            "react-commerce": "react",
            "flutter-dashboard": "flutter",
            "multi-target-all-platforms": None,
        }
        for name, expected_source in examples.items():
            with self.subTest(example=name):
                example = ROOT / "examples" / name
                self.assertTrue(example.is_dir())
                data = yaml.safe_load((example / "conversion-request.yaml").read_text(encoding="utf-8"))
                if expected_source:
                    self.assertEqual(data["source"]["framework_hint"], expected_source)

    def test_multi_target_example_lists_four_platforms(self) -> None:
        path = ROOT / "examples" / "multi-target-all-platforms" / "conversion-request.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.assertEqual(set(data["targets"]), {"wechat", "alipay", "douyin", "xiaohongshu"})


if __name__ == "__main__":
    unittest.main()
