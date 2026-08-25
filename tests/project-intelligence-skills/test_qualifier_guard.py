from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
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

    def test_bounded_handler_qualification_passes_under_guard(self) -> None:
        receipt = qualifier.build_receipt()
        self.assertEqual(receipt["qualification_status"], "PASSED")
        self.assertEqual(
            receipt["effect_guard"],
            "PYTHON_AUDIT_DENY_FILESYSTEM_PROCESS_NETWORK_DURING_DISPATCH",
        )
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


if __name__ == "__main__":
    unittest.main()
