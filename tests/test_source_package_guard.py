from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

from tooling.source_package_guard import resolve_source_package


ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "tooling" / "source_package_guard.py"


class SourcePackageGuardTest(unittest.TestCase):
    def run_guard(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(GUARD), *arguments],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_present_package_returns_success_without_claiming_validation(self) -> None:
        result = self.run_guard(
            "batch46-product-convergence-complete-skills",
            "--manifest",
            "manifest.json",
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout)

    def test_resolver_returns_relocated_skills_package(self) -> None:
        package = resolve_source_package(
            Path("elmos-project-synthesis-batch61-65"),
            Path("package-manifest.json"),
            root=ROOT,
        )
        self.assertEqual(
            ROOT / "skills" / "elmos-project-synthesis-batch61-65",
            package,
        )

    def test_absent_package_is_explicit_and_non_success(self) -> None:
        result = self.run_guard(
            "definitely-absent-source-package",
            "--manifest",
            "manifest.json",
        )
        self.assertEqual(1, result.returncode)
        self.assertIn(
            "SOURCE_PACKAGE_ABSENT=definitely-absent-source-package",
            result.stdout,
        )
        self.assertIn("skipping source-bundle integrity checks", result.stdout)

    def test_absolute_and_traversal_paths_fail_closed(self) -> None:
        for package, manifest in (
            (str(ROOT), "manifest.json"),
            ("../outside", "manifest.json"),
            ("package", "../manifest.json"),
        ):
            with self.subTest(package=package, manifest=manifest):
                result = self.run_guard(package, "--manifest", manifest)
                self.assertEqual(2, result.returncode)
                self.assertIn("SOURCE_PACKAGE_INVALID", result.stderr)
                self.assertNotIn(str(ROOT.parent), result.stderr)


if __name__ == "__main__":
    unittest.main()
