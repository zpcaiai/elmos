"""Build/install coverage for the self-contained Foundry runtime wheel."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

from elmos_foundry.service import FoundryService
from elmos_foundry.skills import EXPECTED_COMPILED_CATALOG_SHA256


ENGINE_ROOT = Path(__file__).resolve().parents[1]


def _run(*command: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )


class WheelInstallTests(unittest.TestCase):
    def test_repository_mode_reverifies_the_pinned_source_archive(self) -> None:
        status = FoundryService().status()
        authority = status["source_authority"]
        self.assertEqual(authority["status"], "RUNTIME_ARCHIVE_REVERIFIED")
        self.assertTrue(authority["runtime_archive_reverified"])
        self.assertEqual(
            authority["compiled_catalog_sha256"], EXPECTED_COMPILED_CATALOG_SHA256
        )

    def test_wheel_is_self_contained_and_rejects_catalog_tampering(self) -> None:
        uv = shutil.which("uv")
        self.assertIsNotNone(uv, "the repository validation toolchain requires uv")
        assert uv is not None
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            distribution = root / "dist"
            environment = root / "venv"
            shutil.copytree(ENGINE_ROOT, source)
            command_env = {
                **os.environ,
                "PYTHONDONTWRITEBYTECODE": "1",
                "UV_OFFLINE": "1",
            }
            command_env.pop("PYTHONPATH", None)
            built = _run(
                uv,
                "build",
                "--offline",
                "--quiet",
                "--out-dir",
                str(distribution),
                str(source),
                env=command_env,
            )
            self.assertEqual(built.returncode, 0, built.stderr or built.stdout)
            wheels = tuple(distribution.glob("*.whl"))
            self.assertEqual(len(wheels), 1)
            wheel = wheels[0]
            with zipfile.ZipFile(wheel) as archive:
                member = "elmos_foundry/catalog/compiled-catalog.json"
                self.assertIn(member, archive.namelist())
                packaged_catalog = archive.read(member)
            self.assertEqual(
                hashlib.sha256(packaged_catalog).hexdigest(),
                EXPECTED_COMPILED_CATALOG_SHA256,
            )

            created = _run(
                uv,
                "venv",
                "--offline",
                "--quiet",
                "--python",
                sys.executable,
                str(environment),
                env=command_env,
            )
            self.assertEqual(created.returncode, 0, created.stderr or created.stdout)
            python = environment / "bin/python"
            installed = _run(
                uv,
                "pip",
                "install",
                "--offline",
                "--no-deps",
                "--python",
                str(python),
                str(wheel),
                env=command_env,
            )
            self.assertEqual(installed.returncode, 0, installed.stderr or installed.stdout)

            cli = environment / "bin/elmos-foundry"
            validated = _run(str(cli), "validate", env=command_env)
            self.assertEqual(validated.returncode, 0, validated.stderr or validated.stdout)
            result = json.loads(validated.stdout)
            authority = result["source_authority"]
            self.assertEqual(
                authority["status"], "BUILD_TIME_DIGEST_BOUND_SOURCE_AUTHORITY"
            )
            self.assertFalse(authority["runtime_archive_reverified"])
            self.assertEqual(
                authority["compiled_catalog_sha256"], EXPECTED_COMPILED_CATALOG_SHA256
            )

            installed_catalogs = tuple(
                environment.glob(
                    "lib/python*/site-packages/elmos_foundry/catalog/compiled-catalog.json"
                )
            )
            self.assertEqual(len(installed_catalogs), 1)
            installed_catalogs[0].write_bytes(packaged_catalog + b"\n")
            tampered = _run(str(cli), "validate", env=command_env)
            self.assertEqual(tampered.returncode, 2, tampered.stdout)
            blocked = json.loads(tampered.stdout)
            self.assertEqual(blocked["status"], "BLOCKED")
            self.assertIn("hard-pinned runtime identity", blocked["error"])


if __name__ == "__main__":
    unittest.main()
