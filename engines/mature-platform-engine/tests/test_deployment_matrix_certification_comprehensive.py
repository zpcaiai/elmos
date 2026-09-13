import unittest
from datetime import datetime

from elmos_mature_platform.types import (
    DeploymentEnvironment,
    CertificationStatus,
    DeploymentCell,
    DeploymentMatrix,
    MatrixTestResult
)
from elmos_mature_platform.deployment_matrix_certification_engine import DeploymentMatrixCertificationEngine

class TestDeploymentMatrixCertificationEngine(unittest.TestCase):
    def setUp(self):
        self.engine = DeploymentMatrixCertificationEngine()

    # ─── Matrix Creation Tests ────────────────────────────────────────────────

    def test_create_matrix_success(self):
        matrix = DeploymentMatrix(
            matrix_id="m1",
            product_name="elmos",
            version="1.0"
        )
        result = self.engine.create_matrix(matrix)
        self.assertEqual(result, "m1")

    def test_create_matrix_empty_id(self):
        matrix = DeploymentMatrix(
            matrix_id="",
            product_name="elmos",
            version="1.0"
        )
        with self.assertRaises(ValueError):
            self.engine.create_matrix(matrix)

    def test_create_matrix_duplicate(self):
        matrix1 = DeploymentMatrix(matrix_id="m1", product_name="elmos", version="1.0")
        matrix2 = DeploymentMatrix(matrix_id="m1", product_name="elmos", version="1.1")
        self.engine.create_matrix(matrix1)
        with self.assertRaises(ValueError):
            self.engine.create_matrix(matrix2)

    # ─── Cell Addition Tests ──────────────────────────────────────────────────

    def test_add_cell_success(self):
        cell = DeploymentCell(
            cell_id="c1",
            environment=DeploymentEnvironment.DEV,
            platform="kubernetes",
            region="us-east-1",
            version="1.0"
        )
        result = self.engine.add_cell(cell)
        self.assertEqual(result, "c1")

    def test_add_cell_empty_id(self):
        cell = DeploymentCell(
            cell_id="",
            environment=DeploymentEnvironment.DEV,
            platform="kubernetes",
            region="us-east-1",
            version="1.0"
        )
        with self.assertRaises(ValueError):
            self.engine.add_cell(cell)

    def test_add_cell_duplicate(self):
        cell1 = DeploymentCell(cell_id="c1", environment=DeploymentEnvironment.DEV, platform="kubernetes", region="us-east-1", version="1.0")
        cell2 = DeploymentCell(cell_id="c1", environment=DeploymentEnvironment.STAGING, platform="ecs", region="us-west-2", version="1.0")
        self.engine.add_cell(cell1)
        with self.assertRaises(ValueError):
            self.engine.add_cell(cell2)

    # ─── Record Test Result Tests ─────────────────────────────────────────────

    def test_record_test_result_pass(self):
        cell = DeploymentCell(cell_id="c1", environment=DeploymentEnvironment.DEV, platform="kubernetes", region="r1", version="1.0")
        self.engine.add_cell(cell)
        result = MatrixTestResult(result_id="r1", cell_id="c1", test_name="t1", passed=True)
        self.engine.record_test_result(result)
        self.assertEqual(cell.test_count, 1)
        self.assertEqual(cell.pass_count, 1)
        self.assertEqual(cell.fail_count, 0)
        self.assertEqual(cell.status, CertificationStatus.IN_PROGRESS)

    def test_record_test_result_fail(self):
        cell = DeploymentCell(cell_id="c1", environment=DeploymentEnvironment.DEV, platform="kubernetes", region="r1", version="1.0")
        self.engine.add_cell(cell)
        result = MatrixTestResult(result_id="r1", cell_id="c1", test_name="t1", passed=False)
        self.engine.record_test_result(result)
        self.assertEqual(cell.test_count, 1)
        self.assertEqual(cell.pass_count, 0)
        self.assertEqual(cell.fail_count, 1)
        self.assertEqual(cell.status, CertificationStatus.FAILED)

    def test_record_test_result_cell_not_found(self):
        result = MatrixTestResult(result_id="r1", cell_id="nonexistent", test_name="t1", passed=True)
        with self.assertRaises(ValueError):
            self.engine.record_test_result(result)

    def test_record_test_result_already_certified(self):
        cell = DeploymentCell(cell_id="c1", environment=DeploymentEnvironment.DEV, platform="k8s", region="r1", version="1.0", status=CertificationStatus.PASSED)
        self.engine.add_cell(cell)
        result = MatrixTestResult(result_id="r1", cell_id="c1", test_name="t1", passed=False)
        self.engine.record_test_result(result)
        self.assertEqual(cell.fail_count, 0)  # Should not update

    # ─── Certify Cell Tests ───────────────────────────────────────────────────

    def test_certify_cell_success(self):
        cell = DeploymentCell(cell_id="c1", environment=DeploymentEnvironment.DEV, platform="k8s", region="r1", version="1.0")
        self.engine.add_cell(cell)
        self.engine.record_test_result(MatrixTestResult("r1", "c1", "t1", True))
        certified = self.engine.certify_cell("c1", "admin")
        self.assertEqual(certified.status, CertificationStatus.PASSED)
        self.assertEqual(certified.certified_by, "admin")

    def test_certify_cell_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.certify_cell("missing", "admin")

    def test_certify_cell_not_tested(self):
        cell = DeploymentCell(cell_id="c1", environment=DeploymentEnvironment.DEV, platform="k8s", region="r1", version="1.0")
        self.engine.add_cell(cell)
        with self.assertRaises(ValueError):
            self.engine.certify_cell("c1", "admin")

    def test_certify_cell_with_failures(self):
        cell = DeploymentCell(cell_id="c1", environment=DeploymentEnvironment.DEV, platform="k8s", region="r1", version="1.0")
        self.engine.add_cell(cell)
        self.engine.record_test_result(MatrixTestResult("r1", "c1", "t1", True))
        self.engine.record_test_result(MatrixTestResult("r2", "c1", "t2", False))
        with self.assertRaises(ValueError):
            self.engine.certify_cell("c1", "admin")

    # ─── Waive Cell Tests ─────────────────────────────────────────────────────

    def test_waive_cell_success(self):
        cell = DeploymentCell(cell_id="c1", environment=DeploymentEnvironment.DEV, platform="k8s", region="r1", version="1.0")
        self.engine.add_cell(cell)
        waived = self.engine.waive_cell("c1", "approved by PM")
        self.assertEqual(waived.status, CertificationStatus.WAIVED)
        self.assertEqual(waived.waiver_reason, "approved by PM")

    def test_waive_cell_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.waive_cell("missing", "reason")

    def test_waive_cell_no_reason(self):
        cell = DeploymentCell(cell_id="c1", environment=DeploymentEnvironment.DEV, platform="k8s", region="r1", version="1.0")
        self.engine.add_cell(cell)
        with self.assertRaises(ValueError):
            self.engine.waive_cell("c1", "")

    # ─── Matrix Coverage Tests ────────────────────────────────────────────────

    def test_get_matrix_coverage_empty(self):
        matrix = DeploymentMatrix(matrix_id="m1", product_name="p", version="1")
        self.engine.create_matrix(matrix)
        cov = self.engine.get_matrix_coverage("m1")
        self.assertEqual(cov["overall_coverage"], 0.0)
        self.assertEqual(cov["tested_ratio"], "0/0")

    def test_get_matrix_coverage_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.get_matrix_coverage("missing")

    def test_get_matrix_coverage_mixed(self):
        m = DeploymentMatrix("m1", "p", "1", cells=["c1", "c2", "c3"])
        self.engine.create_matrix(m)
        
        c1 = DeploymentCell("c1", DeploymentEnvironment.DEV, "k8s", "r1", "1")
        c2 = DeploymentCell("c2", DeploymentEnvironment.STAGING, "ecs", "r1", "1")
        c3 = DeploymentCell("c3", DeploymentEnvironment.PRODUCTION, "vm", "r1", "1")
        
        for c in [c1, c2, c3]:
            self.engine.add_cell(c)
            
        self.engine.record_test_result(MatrixTestResult("r1", "c1", "t1", True))
        self.engine.certify_cell("c1", "admin")
        self.engine.waive_cell("c2", "reason")
        
        cov = self.engine.get_matrix_coverage("m1")
        self.assertAlmostEqual(cov["overall_coverage"], 66.666, places=2)
        self.assertEqual(cov["passed_ratio"], "2/3")
        self.assertEqual(cov["tested_ratio"], "2/3")

    # ─── Evaluate Matrix Tests ────────────────────────────────────────────────

    def test_evaluate_matrix_not_tested(self):
        m = DeploymentMatrix("m1", "p", "1", cells=["c1"])
        self.engine.create_matrix(m)
        self.engine.add_cell(DeploymentCell("c1", DeploymentEnvironment.DEV, "k8s", "r1", "1"))
        result = self.engine.evaluate_matrix("m1")
        self.assertEqual(result.overall_status, CertificationStatus.NOT_TESTED)

    def test_evaluate_matrix_passed(self):
        m = DeploymentMatrix("m1", "p", "1", cells=["c1"], required_environments=[DeploymentEnvironment.DEV], required_platforms=["k8s"])
        self.engine.create_matrix(m)
        self.engine.add_cell(DeploymentCell("c1", DeploymentEnvironment.DEV, "k8s", "r1", "1"))
        self.engine.record_test_result(MatrixTestResult("r1", "c1", "t1", True))
        self.engine.certify_cell("c1", "admin")
        
        result = self.engine.evaluate_matrix("m1")
        self.assertEqual(result.overall_status, CertificationStatus.PASSED)

    def test_evaluate_matrix_failed(self):
        m = DeploymentMatrix("m1", "p", "1", cells=["c1", "c2"])
        self.engine.create_matrix(m)
        self.engine.add_cell(DeploymentCell("c1", DeploymentEnvironment.DEV, "k8s", "r1", "1"))
        self.engine.add_cell(DeploymentCell("c2", DeploymentEnvironment.STAGING, "k8s", "r1", "1"))
        
        self.engine.record_test_result(MatrixTestResult("r1", "c1", "t1", True))
        self.engine.certify_cell("c1", "admin")
        self.engine.record_test_result(MatrixTestResult("r2", "c2", "t1", False))
        
        result = self.engine.evaluate_matrix("m1")
        self.assertEqual(result.overall_status, CertificationStatus.FAILED)

    def test_evaluate_matrix_missing_requirements(self):
        m = DeploymentMatrix("m1", "p", "1", cells=["c1"], required_environments=[DeploymentEnvironment.DEV, DeploymentEnvironment.STAGING])
        self.engine.create_matrix(m)
        self.engine.add_cell(DeploymentCell("c1", DeploymentEnvironment.DEV, "k8s", "r1", "1"))
        
        self.engine.record_test_result(MatrixTestResult("r1", "c1", "t1", True))
        self.engine.certify_cell("c1", "admin")
        
        result = self.engine.evaluate_matrix("m1")
        self.assertEqual(result.overall_status, CertificationStatus.IN_PROGRESS)

    def test_evaluate_matrix_in_progress(self):
        m = DeploymentMatrix("m1", "p", "1", cells=["c1"], required_environments=[DeploymentEnvironment.DEV])
        self.engine.create_matrix(m)
        self.engine.add_cell(DeploymentCell("c1", DeploymentEnvironment.DEV, "k8s", "r1", "1"))
        
        self.engine.record_test_result(MatrixTestResult("r1", "c1", "t1", True))
        # Cell is in progress since it's not explicitly certified yet
        result = self.engine.evaluate_matrix("m1")
        self.assertEqual(result.overall_status, CertificationStatus.IN_PROGRESS)

    def test_evaluate_matrix_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.evaluate_matrix("missing")

    # ─── Cell Querying Tests ──────────────────────────────────────────────────

    def test_get_failing_cells(self):
        m = DeploymentMatrix("m1", "p", "1", cells=["c1", "c2"])
        self.engine.create_matrix(m)
        self.engine.add_cell(DeploymentCell("c1", DeploymentEnvironment.DEV, "k8s", "r1", "1"))
        self.engine.add_cell(DeploymentCell("c2", DeploymentEnvironment.STAGING, "k8s", "r1", "1"))
        
        self.engine.record_test_result(MatrixTestResult("r1", "c1", "t1", False))
        
        failing = self.engine.get_failing_cells("m1")
        self.assertEqual(len(failing), 1)
        self.assertEqual(failing[0].cell_id, "c1")

    def test_get_failing_cells_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.get_failing_cells("missing")

    def test_get_untested_cells(self):
        m = DeploymentMatrix("m1", "p", "1", cells=["c1", "c2"])
        self.engine.create_matrix(m)
        self.engine.add_cell(DeploymentCell("c1", DeploymentEnvironment.DEV, "k8s", "r1", "1"))
        self.engine.add_cell(DeploymentCell("c2", DeploymentEnvironment.STAGING, "k8s", "r1", "1"))
        
        self.engine.record_test_result(MatrixTestResult("r1", "c1", "t1", True))
        
        untested = self.engine.get_untested_cells("m1")
        self.assertEqual(len(untested), 1)
        self.assertEqual(untested[0].cell_id, "c2")

    def test_get_untested_cells_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.get_untested_cells("missing")

    # ─── Certification Report Tests ───────────────────────────────────────────

    def test_get_certification_report(self):
        m = DeploymentMatrix("m1", "p", "1", cells=["c1"], required_environments=[DeploymentEnvironment.DEV])
        self.engine.create_matrix(m)
        self.engine.add_cell(DeploymentCell("c1", DeploymentEnvironment.DEV, "k8s", "r1", "1"))
        self.engine.record_test_result(MatrixTestResult("r1", "c1", "t1", True))
        self.engine.certify_cell("c1", "admin")
        
        report = self.engine.get_certification_report("m1")
        self.assertEqual(report["matrix_id"], "m1")
        self.assertEqual(report["overall_status"], CertificationStatus.PASSED)
        self.assertEqual(report["failing_cells"], 0)
        self.assertEqual(report["untested_cells"], 0)
        self.assertEqual(len(report["cells_detail"]), 1)

    def test_get_certification_report_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.get_certification_report("missing")

    # Additional Coverage Tests for at least 28 total tests
    def test_empty_matrix_evaluation(self):
        m = DeploymentMatrix("m1", "p", "1", cells=[])
        self.engine.create_matrix(m)
        result = self.engine.evaluate_matrix("m1")
        self.assertEqual(result.overall_status, CertificationStatus.NOT_TESTED)
        self.assertEqual(result.coverage_pct, 0.0)

    def test_cell_not_in_cells_dict_handled(self):
        # Cell listed in matrix but not added
        m = DeploymentMatrix("m1", "p", "1", cells=["missing_cell"])
        self.engine.create_matrix(m)
        report = self.engine.get_certification_report("m1")
        self.assertEqual(report["untested_cells"], 0)

if __name__ == '__main__':
    unittest.main()
