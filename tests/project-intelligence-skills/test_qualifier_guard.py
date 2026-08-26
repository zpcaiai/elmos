from __future__ import annotations

import importlib.util
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
ENGINE_SRC = ROOT / "engines/project-intelligence-engine/src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

SPEC = importlib.util.spec_from_file_location(
    "qualify_project_intelligence_runtime_guard_test",
    ROOT / "tooling/qualify_project_intelligence_runtime.py",
)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - import diagnostic
    raise RuntimeError("cannot load Project Intelligence qualifier")
qualifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qualifier)


class QualificationEffectGuardTests(unittest.TestCase):
    def test_guard_denies_filesystem_effect_while_active(self) -> None:
        try:
            qualifier._EFFECT_GUARD_ACTIVE = True
            with self.assertRaisesRegex(
                qualifier.QualificationError,
                "denied external effect: open",
            ):
                Path(__file__).read_bytes()
        finally:
            qualifier._EFFECT_GUARD_ACTIVE = False

    def test_guard_denies_direct_process_and_thread_audit_events(self) -> None:
        try:
            qualifier._EFFECT_GUARD_ACTIVE = True
            for event in (
                "os.posix_spawn",
                "os.forkpty",
                "os.utime",
                "os.setxattr",
                "os.removexattr",
                "_thread.start_new_thread",
            ):
                with (
                    self.subTest(event=event),
                    self.assertRaisesRegex(
                        qualifier.QualificationError,
                        f"denied external effect: {event}",
                    ),
                ):
                    qualifier._deny_qualification_effects(event, ())
        finally:
            qualifier._EFFECT_GUARD_ACTIVE = False

    def test_bounded_handler_qualification_passes_under_guard(self) -> None:
        receipt = qualifier.build_receipt()
        self.assertEqual(receipt["qualification_status"], "PASSED")
        self.assertEqual(
            receipt["effect_guard"],
            "PYTHON_AUDIT_BEST_EFFORT_EFFECT_GUARD_DURING_DISPATCH",
        )
        self.assertIn("not an OS sandbox", receipt["effect_guard_limitations"])
        self.assertEqual(len(receipt["results"]), 50)
        self.assertTrue(all(item["status"] == "PASSED" for item in receipt["results"]))

    def test_failed_handler_contract_cannot_write_or_report_pass(self) -> None:
        failure = qualifier.QualificationContractError("forced qualification failure")
        with (
            patch.object(
                qualifier,
                "validate_qualification_result",
                side_effect=failure,
            ),
            patch.object(qualifier, "write_receipt") as write_receipt,
        ):
            self.assertEqual(qualifier.main(["--write"]), 1)
        write_receipt.assert_not_called()

    def test_receipt_write_is_atomic_and_world_readable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            receipt = Path(temporary) / "qualification.json"
            with patch.object(qualifier, "RECEIPT", receipt):
                qualifier.write_receipt({"schema_version": "test"})
            self.assertEqual(
                receipt.read_bytes(),
                qualifier.serialized({"schema_version": "test"}),
            )
            self.assertEqual(stat.S_IMODE(receipt.lstat().st_mode), 0o644)

    def test_check_rejects_receipt_mode_drift(self) -> None:
        expected = {"schema_version": "test"}
        with tempfile.TemporaryDirectory() as temporary:
            receipt = Path(temporary) / "qualification.json"
            receipt.write_bytes(qualifier.serialized(expected))
            receipt.chmod(0o600)
            with (
                patch.object(qualifier, "RECEIPT", receipt),
                patch.object(qualifier, "build_receipt", return_value=expected),
            ):
                self.assertEqual(qualifier.main(["--check"]), 1)


if __name__ == "__main__":
    unittest.main()
