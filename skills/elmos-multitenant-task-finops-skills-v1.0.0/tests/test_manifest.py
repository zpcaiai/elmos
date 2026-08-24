from __future__ import annotations

import csv
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASK_RE = re.compile(r"ELMOS-MTF-\d{3}-T\d{2}")


class ManifestTests(unittest.TestCase):
    def test_manifest_counts_and_paths(self) -> None:
        manifest = json.loads((ROOT / "skill-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(12, manifest["total_skills"])
        self.assertEqual(144, manifest["total_tasks"])
        self.assertEqual(3, manifest["hard_requirements"]["account_active_root_task_limit"])
        for skill in manifest["skills"]:
            self.assertTrue((ROOT / skill["path"]).is_file())
            self.assertEqual(12, skill["task_count"])

    def test_stable_task_ids_are_unique(self) -> None:
        ids: list[str] = []
        for path in sorted((ROOT / ".agents" / "skills").glob("*/SKILL.md")):
            ids.extend(TASK_RE.findall(path.read_text(encoding="utf-8")))
        self.assertEqual(144, len(ids))
        self.assertEqual(144, len(set(ids)))

    def test_task_matrix_matches(self) -> None:
        with (ROOT / "docs" / "TASK-MATRIX.csv").open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(144, len(rows))
        self.assertEqual(144, len({row["task_id"] for row in rows}))


if __name__ == "__main__":
    unittest.main()
