"""Tests for the deterministic, fail-closed local qualification receipt."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = ROOT / "tooling/qualify_knowledge_skill_model_foundry.py"
MODULE_NAME = "_knowledge_skill_model_foundry_qualifier_under_test"


def load_tool():
    existing = sys.modules.get(MODULE_NAME)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(MODULE_NAME, TOOL_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load Foundry qualification utility")
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


class QualificationReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tool = load_tool()

    def test_built_receipt_is_bounded_without_claiming_external_evidence(self) -> None:
        expected = self.tool.build_receipt(ROOT)
        receipt = json.loads(self.tool._canonical_bytes(expected))
        self.assertEqual(receipt["local_qualification"]["state"], "READY_FOR_EXTERNAL_GATE")
        self.assertEqual(
            receipt["local_qualification"]["evidence_status"],
            "LOCAL_EXECUTED_SELF_ATTESTED",
        )
        self.assertEqual(
            receipt["local_qualification"]["applies_to"],
            "BOUNDED_LOCAL_ENGINEERING_IMPLEMENTATION_ONLY",
        )
        self.assertEqual(
            receipt["local_qualification"]["capability_scope"],
            {
                "compiled_contracts_validated": 1_310,
                "exact_local_semantic_handlers_exercised": 26,
                "prepare_only_skills": 1_284,
            },
        )
        self.assertEqual(receipt["source_archive"]["execution"], "NEVER_EXECUTED")
        self.assertEqual(receipt["evidence_boundaries"]["independent"], "NOT_RUN")
        self.assertEqual(receipt["evidence_boundaries"]["certification"], "NOT_CERTIFIED")
        self.assertFalse(receipt["side_effects"]["performed"])
        self.assertEqual(receipt["local_qualification"]["evidence_capture"], "EXECUTED_BY_WRITE_MODE_ONLY")
        self.assertEqual(len(receipt["local_qualification"]["checks"]), 6)
        self.assertTrue(all(row["status"] == "PASS" for row in receipt["local_qualification"]["checks"]))

    def test_receipt_files_and_caches_are_excluded_from_tree_digest(self) -> None:
        files = set(self.tool.implementation_files(ROOT))
        self.assertNotIn(self.tool.ENGINE_RECEIPT_PATH, files)
        self.assertNotIn(self.tool.DOCS_RECEIPT_PATH, files)
        self.assertNotIn(self.tool.CATALOG_PATH, files)
        self.assertNotIn(self.tool.PACKAGE_REPORT_PATH, files)
        self.assertTrue(all("__pycache__" not in path.parts for path in files))
        self.assertIn(Path("AGENTS.md"), files)
        self.assertIn(Path("Makefile"), files)

    def test_implementation_drift_fails_verification(self) -> None:
        expected = self.tool.build_receipt(ROOT)
        with tempfile.TemporaryDirectory() as temporary:
            fake_root = Path(temporary)
            for relative in (self.tool.ENGINE_RECEIPT_PATH, self.tool.DOCS_RECEIPT_PATH):
                target = fake_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(self.tool._canonical_bytes(expected))
            drifted = json.loads(json.dumps(expected))
            drifted["implementation_tree"]["sha256"] = "0" * 64
            with self.assertRaisesRegex(self.tool.QualificationError, "stale or mismatched"):
                self.tool.verify_receipts(fake_root, drifted)

    def test_dual_receipt_mismatch_fails_closed(self) -> None:
        expected = self.tool.build_receipt(ROOT)
        with tempfile.TemporaryDirectory() as temporary:
            fake_root = Path(temporary)
            self.tool.write_receipts(fake_root, expected)
            docs_receipt = fake_root / self.tool.DOCS_RECEIPT_PATH
            docs_receipt.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(self.tool.QualificationError, "stale or mismatched"):
                self.tool.verify_receipts(fake_root, expected)

    def test_archive_is_hashed_as_opaque_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "payload.zip"
            payload = b"not-a-real-zip-and-never-opened-as-one"
            path.write_bytes(payload)
            digest, size = self.tool._sha256_file(path)
        self.assertEqual(digest, hashlib.sha256(payload).hexdigest())
        self.assertEqual(size, len(payload))

    def test_check_mode_fails_on_mismatched_receipt(self) -> None:
        expected = self.tool.build_receipt(ROOT)
        with (
            mock.patch.object(self.tool, "build_receipt", return_value=expected),
            mock.patch.object(
                self.tool,
                "verify_receipts",
                side_effect=self.tool.QualificationError("drift"),
            ),
        ):
            self.assertEqual(self.tool.main(["--check", "--repo-root", str(ROOT)]), 1)

    def test_check_mode_does_not_execute_local_check_commands(self) -> None:
        expected = self.tool.build_receipt(ROOT)
        with (
            mock.patch.object(self.tool, "build_receipt", return_value=expected),
            mock.patch.object(self.tool, "verify_receipts"),
            mock.patch.object(
                self.tool,
                "run_local_checks",
                side_effect=AssertionError("check mode executed evidence commands"),
            ),
        ):
            self.assertEqual(self.tool.main(["--check", "--repo-root", str(ROOT)]), 0)

    def test_local_check_failure_blocks_write(self) -> None:
        failed = mock.Mock(returncode=7, stdout="", stderr="synthetic failure")
        with mock.patch.object(self.tool.subprocess, "run", return_value=failed):
            with self.assertRaisesRegex(self.tool.QualificationError, "local check failed"):
                self.tool.run_local_checks(ROOT)


if __name__ == "__main__":
    unittest.main()
