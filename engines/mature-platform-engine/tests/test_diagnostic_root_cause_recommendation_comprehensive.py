"""Comprehensive unit tests for DiagnosticRootCauseRecommendationEngine (Batch 41 Skill 1404)."""

import unittest

from elmos_mature_platform.diagnostic_root_cause_recommendation_engine import (
    DiagnosticRootCauseRecommendationEngine,
)
from elmos_mature_platform.types import (
    DiagnosticSeverity,
    RemediationEffort,
    RootCauseHypothesis,
    DiagnosticReport,
)


class TestDiagnosticRootCauseRecommendationComprehensive(unittest.TestCase):
    """Test suite for failure signature analysis and root cause recommendations."""

    def setUp(self) -> None:
        self.engine = DiagnosticRootCauseRecommendationEngine()

    def test_diagnose_connectivity_failure(self) -> None:
        report = self.engine.diagnose_error(
            run_id="run-mig-101",
            error_message="psycopg2.OperationalError: Connection timed out to host db.internal:5432",
            stack_trace="Traceback ... in connect_db: socket.timeout",
        )
        self.assertEqual(report.run_id, "run-mig-101")
        self.assertIsNotNone(report.primary_root_cause)
        self.assertEqual(report.primary_root_cause.cause_name, "Database/Network Connectivity Interruption")
        self.assertEqual(report.primary_root_cause.effort, RemediationEffort.IMMEDIATE_RETRY)
        self.assertTrue(report.primary_root_cause.automated_fix_available)

    def test_diagnose_schema_missing_table(self) -> None:
        report = self.engine.diagnose_error(
            run_id="run-mig-102",
            error_message='ERROR: relation "orders_v2" does not exist',
            stack_trace="org.postgresql.util.PSQLException: ERROR: relation 'orders_v2' does not exist",
        )
        self.assertEqual(report.primary_root_cause.cause_name, "Schema Definition Missing or Drift")
        self.assertEqual(report.primary_root_cause.effort, RemediationEffort.CONFIG_UPDATE)

    def test_diagnose_unique_constraint_violation(self) -> None:
        report = self.engine.diagnose_error(
            run_id="run-mig-103",
            error_message="ORA-00001: unique constraint (APP.PK_USER_ID) violated",
        )
        self.assertEqual(report.primary_root_cause.cause_name, "Data Uniqueness Collision")
        self.assertEqual(report.primary_root_cause.effort, RemediationEffort.AUTOMATIC_PATCH)

    def test_diagnose_sql_syntax_error(self) -> None:
        report = self.engine.diagnose_error(
            run_id="run-mig-104",
            error_message="SQL syntax error at or near ROWNUM <= 100",
        )
        self.assertEqual(report.primary_root_cause.cause_name, "SQL Dialect Transpilation Incompatibility")
        self.assertEqual(report.primary_root_cause.effort, RemediationEffort.MANUAL_REFACTOR)

    def test_diagnose_oom_error(self) -> None:
        report = self.engine.diagnose_error(
            run_id="run-mig-105",
            error_message="Worker terminated: killed by oom with exit code 137",
        )
        self.assertEqual(report.primary_root_cause.cause_name, "Resource Exhaustion (OOM)")

    def test_diagnose_unknown_anomaly(self) -> None:
        report = self.engine.diagnose_error(
            run_id="run-mig-106",
            error_message="Unexpected internal hardware anomaly #0099x",
        )
        self.assertEqual(report.primary_root_cause.cause_name, "Unknown Uncategorized Anomaly")
        self.assertEqual(report.primary_root_cause.confidence_score, 0.2)

    def test_user_feedback_reinforcement(self) -> None:
        report = self.engine.diagnose_error(
            run_id="run-mig-107",
            error_message="Connection timed out",
        )
        initial_conf = report.primary_root_cause.confidence_score
        success = self.engine.add_user_feedback(report.report_id, is_accurate=True)
        self.assertTrue(success)

        # After positive feedback, re-diagnosing yields equal or higher confidence
        report2 = self.engine.diagnose_error(run_id="run-mig-108", error_message="Connection timed out")
        self.assertGreaterEqual(report2.primary_root_cause.confidence_score, initial_conf)

    def test_diagnostic_insights_summary(self) -> None:
        self.engine.diagnose_error("run-1", "Connection timed out")
        self.engine.diagnose_error("run-2", "relation 'users' does not exist")
        insights = self.engine.get_diagnostic_insights()
        self.assertEqual(insights["total_diagnosed_reports"], 2)
        self.assertEqual(insights["auto_fixable_count"], 2)


if __name__ == "__main__":
    unittest.main()
