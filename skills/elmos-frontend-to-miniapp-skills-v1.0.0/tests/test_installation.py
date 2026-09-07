from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from _support import ROOT
from manage_install import MARKER, install, status, uninstall


class InstallationTests(unittest.TestCase):
    def test_install_status_and_uninstall_both_runtimes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-miniapp-skills-test-") as tmp:
            project = Path(tmp)
            installed = install(project, "both", force=False, dry_run=False)
            self.assertTrue(installed["ok"], installed["errors"])

            for runtime_root in [project / ".agents" / "skills", project / ".claude" / "skills"]:
                skill_dirs = [p for p in runtime_root.iterdir() if p.is_dir()]
                self.assertEqual(len(skill_dirs), 22)
                for skill_dir in skill_dirs:
                    marker = json.loads((skill_dir / MARKER).read_text(encoding="utf-8"))
                    self.assertEqual(marker["package_id"], "elmos.frontend-to-miniapp.skills")

            rows = status(project, "both")["skills"]
            self.assertEqual(len(rows), 44)
            self.assertTrue(all(row["state"] == "present" and row["owned"] for row in rows))

            removed = uninstall(project, "both", dry_run=False)
            self.assertTrue(removed["ok"], removed["errors"])
            self.assertFalse(any((project / ".agents" / "skills").iterdir()))
            self.assertFalse(any((project / ".claude" / "skills").iterdir()))

    def test_dry_run_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory(prefix="elmos-miniapp-skills-dry-") as tmp:
            project = Path(tmp)
            result = install(project, "both", force=False, dry_run=True)
            self.assertTrue(result["ok"])
            self.assertFalse((project / ".agents").exists())
            self.assertFalse((project / ".claude").exists())


if __name__ == "__main__":
    unittest.main()
