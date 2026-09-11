"""Comprehensive test suite for CompatibilityTestMatrixEngine (B43 - Skill 1438)."""

from datetime import datetime, timezone
import os
from pathlib import Path
import sys
import unittest

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from elmos_mature_platform.compatibility_test_matrix_engine import (
    CompatibilityTestMatrixEngine,
)
from elmos_mature_platform.types import (
    CompatibilityCell,
    CompatibilityTestMatrixReport,
    MatrixCellStatus,
)


class TestCompatibilityTestMatrixComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = CompatibilityTestMatrixEngine(target_profile="enterprise-modernization-lts")

    def test_initialization(self):
        self.assertEqual(self.engine.target_profile, "enterprise-modernization-lts")
        self.assertEqual(len(self.engine.list_cells()), 0)
        self.assertEqual(len(self.engine.get_audit_log()), 0)

    def test_register_and_get_cell(self):
        cell = CompatibilityCell(
            cell_id="cell-01",
            language_runtime="java@21",
            framework="spring-boot@3.2.0",
            database="postgresql@16",
            cloud_profile="aws-standard",
        )
        registered = self.engine.register_cell(cell)
        self.assertEqual(registered.status, MatrixCellStatus.UNTESTED)
        self.assertTrue(len(registered.evaluated_at) > 0)

        fetched = self.engine.get_cell("cell-01")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.framework, "spring-boot@3.2.0")

    def test_get_nonexistent_cell(self):
        self.assertIsNone(self.engine.get_cell("unknown-cell"))

    def test_static_incompatibility_spring_java8(self):
        cell = CompatibilityCell(
            cell_id="cell-incomp-1",
            language_runtime="java@8",
            framework="spring-boot@3.1.0",
            database="postgresql@15",
            cloud_profile="aws-standard",
        )
        self.engine.register_cell(cell)
        self.assertEqual(cell.status, MatrixCellStatus.INCOMPATIBLE)
        self.assertTrue(any("Java 17 minimum" in bf for bf in cell.broken_features))

    def test_static_incompatibility_django_python38(self):
        cell = CompatibilityCell(
            cell_id="cell-incomp-2",
            language_runtime="python@3.8",
            framework="django@5.0.0",
            database="mysql@8.0",
            cloud_profile="gcp-standard",
        )
        self.engine.register_cell(cell)
        self.assertEqual(cell.status, MatrixCellStatus.INCOMPATIBLE)
        self.assertTrue(any("Python 3.10 minimum" in bf for bf in cell.broken_features))

    def test_static_incompatibility_airgap_cloud_db(self):
        cell = CompatibilityCell(
            cell_id="cell-incomp-3",
            language_runtime="go@1.22",
            framework="gin@1.9",
            database="aws-dynamodb",
            cloud_profile="airgap-onprem",
        )
        self.engine.register_cell(cell)
        self.assertEqual(cell.status, MatrixCellStatus.INCOMPATIBLE)
        self.assertTrue(any("cannot reach AWS DynamoDB" in bf for bf in cell.broken_features))

    def test_update_cell_test_result_success_low_latency(self):
        cell = CompatibilityCell(
            cell_id="cell-pass",
            language_runtime="java@21",
            framework="spring-boot@3.2.0",
            database="postgresql@16",
            cloud_profile="aws-standard",
        )
        self.engine.register_cell(cell)
        res = self.engine.update_cell_test_result(
            cell_id="cell-pass",
            test_run_id="run-100",
            passed=True,
            latency_p95_ms=45.2,
        )
        self.assertTrue(res)
        self.assertEqual(cell.status, MatrixCellStatus.COMPATIBLE)
        self.assertEqual(cell.test_run_id, "run-100")
        self.assertEqual(len(cell.broken_features), 0)

    def test_update_cell_test_result_success_high_latency_degraded(self):
        cell = CompatibilityCell(
            cell_id="cell-deg",
            language_runtime="java@21",
            framework="spring-boot@3.2.0",
            database="postgresql@16",
            cloud_profile="aws-standard",
        )
        self.engine.register_cell(cell)
        res = self.engine.update_cell_test_result(
            cell_id="cell-deg",
            test_run_id="run-101",
            passed=True,
            latency_p95_ms=1250.0,
        )
        self.assertTrue(res)
        self.assertEqual(cell.status, MatrixCellStatus.DEGRADED)
        self.assertTrue(any("High latency overhead" in bf for bf in cell.broken_features))

    def test_update_cell_test_result_failure(self):
        cell = CompatibilityCell(
            cell_id="cell-fail",
            language_runtime="java@17",
            framework="spring-boot@3.2.0",
            database="oracle@19c",
            cloud_profile="azure-standard",
        )
        self.engine.register_cell(cell)
        res = self.engine.update_cell_test_result(
            cell_id="cell-fail",
            test_run_id="run-102",
            passed=False,
            broken_features=["HikariCP driver connection handshake timeout"],
        )
        self.assertTrue(res)
        self.assertEqual(cell.status, MatrixCellStatus.INCOMPATIBLE)
        self.assertIn("HikariCP driver connection handshake timeout", cell.broken_features)

    def test_update_nonexistent_cell_returns_false(self):
        res = self.engine.update_cell_test_result("unknown-cell", "run-x", True)
        self.assertFalse(res)

    def test_list_cells_with_and_without_status_filter(self):
        c1 = CompatibilityCell("c1", "java@17", "spring-boot@3.2", "pg@16", "aws")
        c2 = CompatibilityCell("c2", "java@8", "spring-boot@3.2", "pg@16", "aws")
        self.engine.register_cell(c1)
        self.engine.register_cell(c2)

        self.engine.update_cell_test_result("c1", "r1", True, 20.0)

        self.assertEqual(len(self.engine.list_cells()), 2)
        self.assertEqual(len(self.engine.list_cells(status=MatrixCellStatus.COMPATIBLE)), 1)
        self.assertEqual(len(self.engine.list_cells(status=MatrixCellStatus.INCOMPATIBLE)), 1)
        self.assertEqual(len(self.engine.list_cells(status=MatrixCellStatus.UNTESTED)), 0)

    def test_evaluate_matrix_report_empty(self):
        report = self.engine.evaluate_matrix_report()
        self.assertEqual(report.total_cells, 0)
        self.assertEqual(report.compatibility_score_pct, 100.0)
        self.assertTrue(report.lts_ready)

    def test_evaluate_matrix_report_lts_ready_success(self):
        # Setup required LTS combinations and verify all compatible
        combos = [
            ("java@17", "spring-boot@3.2", "postgresql@16"),
            ("java@21", "spring-boot@3.2", "postgresql@16"),
            ("python@3.11", "fastapi@0.109", "postgresql@16"),
        ]
        for idx, (lang, fw, db) in enumerate(combos):
            cid = f"lts-{idx}"
            cell = CompatibilityCell(cid, lang, fw, db, "aws-standard")
            self.engine.register_cell(cell)
            self.engine.update_cell_test_result(cid, f"run-{idx}", True, 50.0)

        report = self.engine.evaluate_matrix_report()
        self.assertEqual(report.total_cells, 3)
        self.assertEqual(report.compatible_cells_count, 3)
        self.assertEqual(report.incompatible_cells_count, 0)
        self.assertEqual(report.compatibility_score_pct, 100.0)
        self.assertTrue(report.lts_ready)
        self.assertEqual(len(report.breaking_pairwise_combinations), 0)

    def test_evaluate_matrix_report_with_breaking_pairs_not_lts_ready(self):
        # 1 valid cell, 1 incompatible cell
        c1 = CompatibilityCell("c-ok", "java@21", "spring-boot@3.2", "postgresql@16", "aws")
        c2 = CompatibilityCell("c-bad", "java@8", "spring-boot@3.2", "postgresql@16", "aws")
        self.engine.register_cell(c1)
        self.engine.register_cell(c2)
        self.engine.update_cell_test_result("c-ok", "r-ok", True, 20.0)

        report = self.engine.evaluate_matrix_report()
        self.assertEqual(report.total_cells, 2)
        self.assertEqual(report.compatible_cells_count, 1)
        self.assertEqual(report.incompatible_cells_count, 1)
        self.assertEqual(report.compatibility_score_pct, 50.0)
        self.assertFalse(report.lts_ready)
        self.assertEqual(len(report.breaking_pairwise_combinations), 1)

    def test_evaluate_matrix_report_lts_combination_untested_or_degraded(self):
        # LTS critical combination registered but left UNTESTED -> lts_ready should be False
        c_lts = CompatibilityCell("c-lts", "java@17", "spring-boot@3.2", "postgresql@16", "aws")
        self.engine.register_cell(c_lts)
        report = self.engine.evaluate_matrix_report()
        self.assertFalse(report.lts_ready)

    def test_audit_logging(self):
        cell = CompatibilityCell("c-aud", "java@21", "spring-boot@3.2", "pg@16", "aws")
        self.engine.register_cell(cell)
        self.engine.update_cell_test_result("c-aud", "r-aud", True, 30.0)
        self.engine.evaluate_matrix_report()

        trail = self.engine.get_audit_log()
        actions = [t["action"] for t in trail]
        self.assertIn("cell_registered", actions)
        self.assertIn("cell_test_updated", actions)
        self.assertIn("matrix_evaluated", actions)


if __name__ == "__main__":
    unittest.main()
