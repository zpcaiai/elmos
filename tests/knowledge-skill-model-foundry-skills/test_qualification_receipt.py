"""Tests for the deterministic, fail-closed local qualification receipt."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
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
                "exact_local_semantic_handlers_exercised": 51,
                "prepare_only_skills": 1_259,
                "exact_integration_bindings_validated": 1_310,
                "host_route_bound_skills": 1_259,
                "integration_unbound_skills": 0,
                "pipeline_host_routes_validated": 14,
            },
        )
        self.assertEqual(receipt["source_archive"]["execution"], "NEVER_EXECUTED")
        self.assertEqual(receipt["evidence_boundaries"]["independent"], "NOT_RUN")
        self.assertEqual(receipt["evidence_boundaries"]["certification"], "NOT_CERTIFIED")
        self.assertFalse(receipt["side_effects"]["performed"])
        self.assertEqual(receipt["local_qualification"]["evidence_capture"], "EXECUTED_BY_WRITE_MODE_ONLY")
        self.assertEqual(len(receipt["local_qualification"]["checks"]), 7)
        self.assertTrue(all(row["status"] == "PASS" for row in receipt["local_qualification"]["checks"]))

    def test_receipt_files_and_caches_are_excluded_from_tree_digest(self) -> None:
        files = set(self.tool.implementation_files(ROOT))
        self.assertNotIn(self.tool.ENGINE_RECEIPT_PATH, files)
        self.assertNotIn(self.tool.DOCS_RECEIPT_PATH, files)
        self.assertFalse(any(".venv" in path.parts for path in files))
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


class QualificationGitBaselineTests(unittest.TestCase):
    """Real Git history in disposable repositories; the workspace Git is read-only."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tool = load_tool()
        cls.template = cls.tool.build_receipt(ROOT)

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.handler = self.root / "handler.py"
        self.handler.write_text("value = 'baseline'\n", encoding="utf-8")
        self.git("init", "--initial-branch=main")
        self.git("add", "handler.py")
        self.git("commit", "-m", "independent baseline")
        self.baseline = self.git("rev-parse", "HEAD")

    def git(self, *arguments: str, input_text: str | None = None) -> str:
        environment = {
            key: value for key, value in os.environ.items() if not key.startswith("GIT_")
        }
        environment.update(
            {"LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
        )
        result = subprocess.run(
            [
                "git", "-C", str(self.root),
                "-c", "user.name=Foundry qualification test",
                "-c", "user.email=foundry-test@example.invalid",
                "-c", "commit.gpgSign=false",
                "-c", "tag.gpgSign=false",
                "-c", f"core.hooksPath={os.devnull}",
                *arguments,
            ],
            input=input_text, text=True, capture_output=True, check=True,
            timeout=10, env=environment,
        )
        return result.stdout.strip()

    def expected(self) -> dict:
        receipt = deepcopy(self.template)
        receipt["baseline_commit"] = self.tool._baseline_commit(self.root)
        with mock.patch.object(self.tool, "IMPLEMENTATION_ROOTS", (Path("handler.py"),)):
            receipt["implementation_tree"] = self.tool.implementation_tree(self.root)
        return receipt

    def test_content_bound_receipt_checks_before_and_after_delivery_commit(self) -> None:
        self.handler.write_text("value = 'qualified implementation'\n", encoding="utf-8")
        receipt = self.expected()
        self.tool.write_receipts(self.root, receipt)
        original = (self.root / self.tool.ENGINE_RECEIPT_PATH).read_bytes()
        self.tool.verify_receipts(self.root, self.expected())
        self.git(
            "add", "handler.py", self.tool.ENGINE_RECEIPT_PATH.as_posix(),
            self.tool.DOCS_RECEIPT_PATH.as_posix(),
        )
        self.git("commit", "-m", "deliver qualified bytes and receipts")
        self.assertNotEqual(self.baseline, self.git("rev-parse", "HEAD"))
        self.tool.verify_receipts(self.root, self.expected())
        self.assertEqual(original, (self.root / self.tool.ENGINE_RECEIPT_PATH).read_bytes())
        self.assertEqual(
            self.baseline,
            json.loads(original)["baseline_commit"],
        )

    def test_real_implementation_drift_still_fails_after_commit(self) -> None:
        receipt = self.expected()
        self.tool.write_receipts(self.root, receipt)
        self.handler.write_text("value = 'unqualified drift'\n", encoding="utf-8")
        self.git("add", "handler.py")
        self.git("commit", "-m", "unqualified implementation change")
        with self.assertRaisesRegex(self.tool.QualificationError, "stale or mismatched"):
            self.tool.verify_receipts(self.root, self.expected())
        # Substituting another valid ancestor cannot bypass the content digest.
        receipt["baseline_commit"] = self.git("rev-parse", "HEAD")
        self.tool.write_receipts(self.root, receipt)
        with self.assertRaisesRegex(self.tool.QualificationError, "stale or mismatched"):
            self.tool.verify_receipts(self.root, self.expected())

    def test_missing_malformed_and_nonexistent_baselines_fail_closed(self) -> None:
        for baseline in (None, False, 42, "HEAD", "a" * 39, "G" * 40, "0" * 40):
            with self.subTest(baseline=baseline):
                receipt = self.expected()
                receipt["baseline_commit"] = baseline
                self.tool.write_receipts(self.root, receipt)
                with self.assertRaisesRegex(self.tool.QualificationError, "baseline_commit"):
                    self.tool.verify_receipts(self.root, self.expected())

    def test_unrelated_and_future_commit_baselines_fail_closed(self) -> None:
        tree = self.git("rev-parse", "HEAD^{tree}")
        unrelated = self.git("commit-tree", tree, input_text="unrelated root\n")
        future = self.git("commit-tree", tree, "-p", self.baseline, input_text="future commit\n")
        for baseline in (unrelated, future):
            with self.subTest(baseline=baseline):
                receipt = self.expected()
                receipt["baseline_commit"] = baseline
                self.tool.write_receipts(self.root, receipt)
                with self.assertRaisesRegex(self.tool.QualificationError, "ancestor"):
                    self.tool.verify_receipts(self.root, self.expected())

    def test_local_grafts_cannot_forge_baseline_ancestry(self) -> None:
        tree = self.git("rev-parse", "HEAD^{tree}")
        unrelated = self.git("commit-tree", tree, input_text="unrelated graft target\n")
        grafts = self.root / ".git/info/grafts"
        grafts.write_text(f"{self.baseline} {unrelated}\n", encoding="ascii")
        # Ordinary Git now reports the forged relationship; qualification must
        # inspect history with grafts and replacement objects disabled.
        self.git("merge-base", "--is-ancestor", unrelated, self.baseline)
        with self.assertRaisesRegex(self.tool.QualificationError, "ancestor"):
            self.tool._verify_recorded_baseline(self.root, unrelated)

    def test_existing_tag_and_blob_ids_cannot_masquerade_as_commit_baseline(self) -> None:
        self.git("tag", "-a", "baseline-tag", "-m", "annotated tag")
        for baseline in (
            self.git("rev-parse", "refs/tags/baseline-tag"),
            self.git("rev-parse", "HEAD:handler.py"),
        ):
            with self.subTest(baseline=baseline):
                receipt = self.expected()
                receipt["baseline_commit"] = baseline
                self.tool.write_receipts(self.root, receipt)
                with self.assertRaisesRegex(self.tool.QualificationError, "existing commit"):
                    self.tool.verify_receipts(self.root, self.expected())

    def test_valid_baseline_does_not_relax_checks_catalog_or_dual_receipt_bindings(self) -> None:
        receipt = self.expected()
        self.tool.write_receipts(self.root, receipt)
        for section in ("checks", "catalog"):
            expected = self.expected()
            if section == "checks":
                expected["local_qualification"]["checks"][0]["status"] = "NOT_RUN"
            else:
                expected["generated_artifacts"]["compiled_catalog"]["sha256"] = "0" * 64
            with self.subTest(section=section), self.assertRaisesRegex(
                self.tool.QualificationError, "stale or mismatched"
            ):
                self.tool.verify_receipts(self.root, expected)
        docs = self.root / self.tool.DOCS_RECEIPT_PATH
        docs.write_bytes(docs.read_bytes() + b" ")
        with self.assertRaisesRegex(self.tool.QualificationError, "not byte-identical"):
            self.tool.verify_receipts(self.root, self.expected())

    def test_ambient_git_paths_cannot_redirect_baseline_validation(self) -> None:
        with mock.patch.dict(os.environ, {"GIT_DIR": "/does-not-exist", "GIT_WORK_TREE": "/"}):
            self.assertEqual(self.baseline, self.tool._baseline_commit(self.root))

    def test_unborn_git_repository_cannot_claim_no_git_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            empty = Path(directory)
            subprocess.run(
                ["git", "init", "--initial-branch=main", str(empty)],
                check=True, capture_output=True, timeout=10,
            )
            with self.assertRaisesRegex(self.tool.QualificationError, "committed baseline"):
                self.tool._baseline_commit(empty)

    def test_corrupt_git_indirection_cannot_downgrade_to_archive_only_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            broken = Path(directory)
            (broken / ".git").write_text(
                f"gitdir: {broken / 'nonexistent-git-directory'}\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(self.tool.QualificationError, "repository context"):
                self.tool._baseline_commit(broken)

    def test_absent_git_binary_only_allows_archive_without_git_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(self.tool.subprocess, "run", side_effect=FileNotFoundError):
                self.assertIsNone(self.tool._baseline_commit(Path(directory)))
                with self.assertRaisesRegex(self.tool.QualificationError, "could not be verified"):
                    self.tool._baseline_commit(self.root)


if __name__ == "__main__":
    unittest.main()
