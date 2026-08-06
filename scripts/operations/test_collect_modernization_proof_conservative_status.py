import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_modernization_proof_conservative_status as subject


class ConservativeStatusTest(unittest.TestCase):
    def check(self, state="SUCCESS", *, kind="CheckRun"):
        if kind == "CheckRun":
            return {
                "__typename": kind,
                "name": "CI",
                "workflowName": "CI",
                "status": "COMPLETED" if state != "IN_PROGRESS" else state,
                "conclusion": "" if state == "IN_PROGRESS" else state,
                "detailsUrl": "https://example.test/check",
            }
        return {
            "__typename": "StatusContext",
            "context": "deploy",
            "state": state,
            "targetUrl": "https://example.test/status",
        }

    def test_ci_pass_requires_nonempty_all_success(self):
        self.assertEqual("NOT_RUN", subject.classify_check_rollup([])["status"])
        passed = subject.classify_check_rollup(
            [self.check(), self.check(kind="StatusContext")]
        )
        self.assertEqual("PASSED", passed["status"])
        self.assertTrue(passed["claimed_passed"])

    def test_ci_failure_wins_while_pending_is_still_counted(self):
        result = subject.classify_check_rollup(
            [self.check("FAILURE"), self.check("IN_PROGRESS")]
        )
        self.assertEqual("FAILED", result["status"])
        self.assertEqual(1, result["failure_count"])
        self.assertEqual(1, result["pending_count"])
        self.assertFalse(result["claimed_passed"])

    def test_unknown_or_skipped_check_cannot_be_passed(self):
        result = subject.classify_check_rollup([self.check("SKIPPED")])
        self.assertEqual("IN_PROGRESS", result["status"])
        self.assertEqual(1, result["other_non_success_count"])
        self.assertFalse(result["claimed_passed"])

    def test_v63_pass_is_local_only_and_digest_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            xml = root / "report.xml"
            xml.write_text(
                """<testsuite name="io.elmos.persistence.FlywayMigrationTest"
 tests="1" failures="0" errors="0" skipped="0">
 <system-err>Creating container for image: postgres:17.5-alpine
 Successfully applied 61 migrations to schema "public", now at version v63
 </system-err></testsuite>""",
                encoding="utf-8",
            )
            text = root / "report.txt"
            text.write_text(
                "Tests run: 1, Failures: 0, Errors: 0, Skipped: 0\n",
                encoding="utf-8",
            )
            migration = root / subject.EXPECTED_MIGRATION
            migration.write_text(
                "-- MODERNIZATION_PROOF\nselect 1;\n", encoding="utf-8"
            )
            test_source = root / "FlywayMigrationTest.java"
            test_source.write_text(
                """class FlywayMigrationTest {
// flyway_schema_history version = '63' MODERNIZATION_PROOF
// UNKNOWN_PROOF_LINE worker:latest assertThrows
}
""",
                encoding="utf-8",
            )
            result = subject.evaluate_v63_integration(
                xml_report=xml,
                text_report=text,
                migration=migration,
                test_source=test_source,
                postgres_image={
                    "tag": subject.EXPECTED_POSTGRES_TAG,
                    "immutable_reference": "postgres@sha256:" + "a" * 64,
                    "local_image_id": "sha256:" + "a" * 64,
                    "platform": "linux/arm64",
                },
            )
        self.assertEqual("PASSED", result["status"])
        self.assertEqual("LOCAL_ENGINEERING_INTEGRATION", result["scope"])
        self.assertFalse(result["production_equivalent"])
        self.assertFalse(result["promotes_external_boundary"])
        self.assertFalse(result["certifies_release"])

    def test_v63_skip_or_missing_runtime_log_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            xml = root / "report.xml"
            xml.write_text(
                """<testsuite name="io.elmos.persistence.FlywayMigrationTest"
 tests="1" failures="0" errors="0" skipped="1"/>""",
                encoding="utf-8",
            )
            text = root / "report.txt"
            text.write_text("Tests run: 1, Skipped: 1\n", encoding="utf-8")
            migration = root / subject.EXPECTED_MIGRATION
            migration.write_text("select 1;\n", encoding="utf-8")
            test_source = root / "FlywayMigrationTest.java"
            test_source.write_text("class FlywayMigrationTest {}\n", encoding="utf-8")
            result = subject.evaluate_v63_integration(
                xml_report=xml,
                text_report=text,
                migration=migration,
                test_source=test_source,
                postgres_image={
                    "tag": subject.EXPECTED_POSTGRES_TAG,
                    "immutable_reference": "postgres@sha256:" + "a" * 64,
                },
            )
        self.assertEqual("BLOCKED", result["status"])
        self.assertIn("V63_SUREFIRE_COUNTS_NOT_PASSED", result["blockers"])
        self.assertIn(
            "V63_POSTGRES_CONTAINER_EXECUTION_NOT_OBSERVED", result["blockers"]
        )

    @patch.object(subject, "evaluate_v63_integration")
    @patch.object(subject, "observe_pr")
    @patch.object(subject, "observe_worktree")
    @patch.object(subject, "evaluate_release_gate")
    def test_collector_preserves_two_boundary_layers_and_false_release_flags(
        self, gate_mock, worktree_mock, pr_mock, v63_mock
    ):
        boundaries = {
            boundary: subject.NOT_RUN for boundary in subject.EXTERNAL_BOUNDARIES
        }
        effective = dict(boundaries)
        effective["SCM_DRAFT_PULL_REQUEST"] = subject.EXECUTED_AWAITING_VERIFICATION
        gate_mock.return_value = {
            "schema_version": 1,
            "decision": "BLOCKED",
            "blockers": ["REAL_CLOUD_PROVIDER_NOT_RUN"],
            "effective_external_boundaries": effective,
            "production_ready": False,
            "certified": False,
        }
        worktree_mock.side_effect = [
            {
                "path": "/primary",
                "head_sha": "b" * 40,
                "clean": False,
                "dirty_entry_count": 4747,
                "status_sha256": "1" * 64,
            },
            {
                "path": "/source",
                "head_sha": "a" * 40,
                "clean": True,
                "dirty_entry_count": 0,
                "status_sha256": "e3b0c442" + "0" * 56,
            },
        ]
        pr_mock.return_value = {
            "remote_ci": {
                "status": "FAILED",
                "failure_count": 2,
                "pending_count": 1,
                "other_non_success_count": 0,
            }
        }
        v63_mock.return_value = {"status": "PASSED", "blockers": []}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "image.json"
            closure = root / "closure.json"
            image.write_text(
                json.dumps(
                    {
                        "source_commit": "a" * 40,
                        "external_boundaries": boundaries,
                        "source_worktree_clean_before": True,
                        "source_worktree_clean_after": True,
                    }
                ),
                encoding="utf-8",
            )
            closure.write_text("{}", encoding="utf-8")
            result = subject.collect_status(
                image_receipt_path=image,
                closure_path=closure,
                primary_worktree=root,
                source_worktree=root,
                repository="zpcaiai/elmos",
                pr_number=25,
                xml_report=root / "report.xml",
                text_report=root / "report.txt",
                migration=root / subject.EXPECTED_MIGRATION,
                test_source=root / subject.EXPECTED_TEST_SOURCE,
                postgres_image={},
            )
        self.assertEqual(
            boundaries,
            result["boundary_state_layers"]["image_build_external_boundaries"],
        )
        self.assertEqual(
            subject.EXECUTED_AWAITING_VERIFICATION,
            result["boundary_state_layers"]["release_closure_effective_boundaries"][
                "SCM_DRAFT_PULL_REQUEST"
            ],
        )
        self.assertEqual("BLOCKED", result["decision"])
        self.assertFalse(result["production_ready"])
        self.assertFalse(result["certified"])
        self.assertIn("REMOTE_CI_FAILED", result["blockers"])
        self.assertIn("REMOTE_CI_IN_PROGRESS_OR_NON_SUCCESS", result["blockers"])


if __name__ == "__main__":
    unittest.main()
