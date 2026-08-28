from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class LocalTestsPackageResolutionTests(unittest.TestCase):
    def test_repository_tests_package_wins_over_poisoned_pythonpath(self) -> None:
        with tempfile.TemporaryDirectory(prefix="poisoned-tests-package-") as directory:
            poison = Path(directory)
            external_tests = poison / "tests"
            external_tests.mkdir()
            (external_tests / "__init__.py").write_text(
                "raise RuntimeError('external tests package imported')\n",
                encoding="utf-8",
            )
            environment = os.environ.copy()
            existing = environment.get("PYTHONPATH")
            environment["PYTHONPATH"] = (
                str(poison)
                if not existing
                else os.pathsep.join((str(poison), existing))
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "from pathlib import Path; import tests; "
                        "from tests.frontend_formal_toolchains import test_runner; "
                        "expected = Path('tests/__init__.py').resolve(); "
                        "actual = Path(tests.__file__).resolve(); "
                        "assert actual == expected, (actual, expected); "
                        "assert callable(test_runner.runtime_block_measurement)"
                    ),
                ],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(
                0,
                completed.returncode,
                completed.stdout + completed.stderr,
            )


if __name__ == "__main__":
    unittest.main()
