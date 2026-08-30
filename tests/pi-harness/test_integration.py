"""Fail-closed integration tests for the pinned PI Harness package."""

from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tooling/integrate_pi_harness.py"


def load_tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pi_harness_integrator", TOOL_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load PI Harness integrator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PIHarnessIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tool = load_tool()

    def materialize_implementation(self, destination: Path) -> None:
        for member in self.tool.REQUIRED_IMPLEMENTATION_MEMBERS:
            source = self.tool.PACKAGE_ROOT / member
            target = destination / member
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    def test_pinned_archive_and_complete_implementation(self) -> None:
        result = self.tool.validate()
        self.assertEqual(result["sha256"], self.tool.EXPECTED_ARCHIVE_SHA256)
        self.assertEqual(result["entries"], self.tool.EXPECTED_ARCHIVE_ENTRIES)
        implementation = result["implementation"]
        self.assertEqual(
            implementation["required_members"],
            len(self.tool.REQUIRED_IMPLEMENTATION_MEMBERS),
        )
        self.assertEqual(implementation["external_evidence"], "NOT_RUN")
        self.assertEqual(implementation["certification"], "NOT_CERTIFIED")

    def test_archive_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pi-archive-drift-") as raw_root:
            raw = self.tool.ARCHIVE.read_bytes()
            same_size_archive = Path(raw_root) / "same-size-tampered.zip"
            tampered = bytearray(raw)
            tampered[len(tampered) // 2] ^= 1
            same_size_archive.write_bytes(tampered)
            with self.assertRaisesRegex(SystemExit, "archive digest mismatch"):
                self.tool.validate(same_size_archive)

            wrong_size_archive = Path(raw_root) / "wrong-size-tampered.zip"
            wrong_size_archive.write_bytes(raw + b"drift")
            with self.assertRaisesRegex(SystemExit, "archive byte count mismatch"):
                self.tool.validate(wrong_size_archive)

    def test_missing_runtime_member_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pi-missing-runtime-") as raw_root:
            package_root = Path(raw_root) / "pi-harness"
            self.materialize_implementation(package_root)
            (package_root / "src/elmos_pi_harness/temporal.py").unlink()
            with self.assertRaisesRegex(
                SystemExit, "implementation is missing required members"
            ):
                self.tool.validate_implementation(package_root)

    def test_certification_status_promotion_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pi-status-drift-") as raw_root:
            package_root = Path(raw_root) / "pi-harness"
            self.materialize_implementation(package_root)
            manifest_path = package_root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["certification"] = "CERTIFIED"
            manifest["certified"] = True
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                SystemExit, "implementation manifest certification mismatch"
            ):
                self.tool.validate_implementation(package_root)


if __name__ == "__main__":
    unittest.main()
