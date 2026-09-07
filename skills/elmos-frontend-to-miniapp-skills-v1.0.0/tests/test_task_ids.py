from __future__ import annotations

import unittest

import yaml

from _support import ROOT


class TaskIdTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = yaml.safe_load((ROOT / "skill-manifest.yaml").read_text(encoding="utf-8"))
        cls.task_ids = [tid for skill in cls.manifest["skills"] for tid in skill["task_ids"]]

    def test_task_ids_are_unique(self) -> None:
        self.assertEqual(len(self.task_ids), len(set(self.task_ids)))

    def test_task_id_sequence_is_complete(self) -> None:
        expected = [f"MAPP-{i:03d}" for i in range(1, 41)]
        self.assertEqual(sorted(self.task_ids), expected)

    def test_first_40_tasks_document_covers_every_task(self) -> None:
        text = (ROOT / "docs" / "FIRST-40-TASKS.md").read_text(encoding="utf-8")
        for task_id in self.task_ids:
            with self.subTest(task_id=task_id):
                self.assertIn(task_id, text)


if __name__ == "__main__":
    unittest.main()
