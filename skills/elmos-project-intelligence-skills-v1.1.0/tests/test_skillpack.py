from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]


class SkillPackTests(unittest.TestCase):
    def test_validator_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/validate_skillpack.py")],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_profiles_reference_real_skills(self) -> None:
        manifest = yaml.safe_load((ROOT / "skillpack.yaml").read_text(encoding="utf-8"))
        names = set()
        for directory in (ROOT / "skills").iterdir():
            if not (directory / "SKILL.md").is_file():
                continue
            fm = yaml.safe_load((directory / "SKILL.md").read_text(encoding="utf-8").split("---", 2)[1])
            names.add(fm["name"])
        self.assertEqual(len(names), manifest["skill_count"])
        for profile, requested in manifest["profiles"].items():
            with self.subTest(profile=profile):
                self.assertTrue(set(requested).issubset(names))

    def test_dry_run_installer(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/install_skillpack.py"),
                    "--repo", td,
                    "--target", "both",
                    "--profile", "reader",
                    "--dry-run",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["profile"], "reader")
            self.assertGreater(payload["skill_count"], 0)
            self.assertEqual(len(payload["operations"]), payload["skill_count"] * 2)

    def test_real_install_uses_canonical_skill_names(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/install_skillpack.py"),
                    "--repo", str(repo),
                    "--target", "both",
                    "--profile", "bootstrap",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for base in [repo / ".agents/skills", repo / ".claude/skills"]:
                installed = {p.name for p in base.iterdir() if p.is_dir()}
                self.assertIn("elmos-insight-orchestrator", installed)
                self.assertFalse(any(name[:2].isdigit() for name in installed))
                self.assertTrue((base / "elmos-insight-orchestrator/SKILL.md").is_file())
            self.assertTrue((repo / ".elmos/skillpacks/elmos-project-intelligence/batches").is_dir())

    def test_debug_profile_contains_online_debug_stack(self) -> None:
        manifest = yaml.safe_load((ROOT / "skillpack.yaml").read_text(encoding="utf-8"))
        requested = set(manifest["profiles"]["debug"])
        expected = {
            "elmos-debug-adapter-gateway",
            "elmos-debug-sandbox-orchestration",
            "elmos-online-debug-workbench",
            "elmos-debug-learning-copilot",
            "elmos-debug-record-replay",
            "elmos-distributed-debug-correlation",
        }
        self.assertTrue(expected.issubset(requested))


if __name__ == "__main__":
    unittest.main()
