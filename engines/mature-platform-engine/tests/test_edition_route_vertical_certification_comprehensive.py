"""Comprehensive test suite for EditionRouteVerticalCertificationEngine (Batch 45 - Skill 1495)."""

import unittest

from elmos_mature_platform.edition_route_vertical_certification_engine import (
    EditionRouteVerticalCertificationEngine,
)
from elmos_mature_platform.types import (
    MatrixCertificationRecord,
    MatrixCertificationStatus,
    VerticalDomain,
)


class TestEditionRouteVerticalCertificationComprehensive(unittest.TestCase):
    """Rigorous unit testing for EditionRouteVerticalCertificationEngine."""

    def setUp(self) -> None:
        self.engine = EditionRouteVerticalCertificationEngine()

    def test_register_matrix_cell_success(self) -> None:
        rec = MatrixCertificationRecord(
            matrix_id="mat-101",
            edition="air-gapped",
            route_key="cobol-to-java",
            vertical=VerticalDomain.FINANCIAL_SERVICES,
        )
        mid = self.engine.register_matrix_cell(rec)
        self.assertEqual(mid, "mat-101")
        retrieved = self.engine.get_matrix_cell("mat-101")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.edition, "air-gapped")
        self.assertEqual(retrieved.status, MatrixCertificationStatus.NOT_TESTED)

    def test_register_matrix_cell_auto_generates_id(self) -> None:
        rec = MatrixCertificationRecord(
            matrix_id="",
            edition="sovereign",
            route_key="spring-boot-4",
            vertical=VerticalDomain.PUBLIC_SECTOR,
        )
        mid = self.engine.register_matrix_cell(rec)
        self.assertTrue(mid.startswith("mat-"))

    def test_register_matrix_cell_validation_errors(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.register_matrix_cell(
                MatrixCertificationRecord("m1", "", "route", VerticalDomain.RETAIL_COMMERCE)
            )
        with self.assertRaises(ValueError):
            self.engine.register_matrix_cell(
                MatrixCertificationRecord("m2", "edition", "", VerticalDomain.RETAIL_COMMERCE)
            )

    def test_record_compliance_controls_success(self) -> None:
        rec = MatrixCertificationRecord(
            "mat-ctrl", "customer-vpc", "db2-to-postgres", VerticalDomain.HEALTHCARE_LIFE_SCIENCES
        )
        self.engine.register_matrix_cell(rec)

        updated = self.engine.record_compliance_controls("mat-ctrl", passed=45, total=50)
        self.assertEqual(updated.compliance_controls_passed, 45)
        self.assertEqual(updated.compliance_controls_total, 50)

    def test_record_compliance_controls_validation_errors(self) -> None:
        rec = MatrixCertificationRecord("mat-err", "ed", "route", VerticalDomain.AEROSPACE_DEFENSE)
        self.engine.register_matrix_cell(rec)

        with self.assertRaises(ValueError):
            self.engine.record_compliance_controls("mat-err", passed=-1, total=10)
        with self.assertRaises(ValueError):
            self.engine.record_compliance_controls("mat-err", passed=15, total=10)
        with self.assertRaises(ValueError):
            self.engine.record_compliance_controls("mat-unknown", passed=5, total=10)

    def test_update_certification_status_in_qualification(self) -> None:
        rec = MatrixCertificationRecord("mat-qual", "ed", "route", VerticalDomain.TELECOMMUNICATIONS)
        self.engine.register_matrix_cell(rec)

        updated = self.engine.update_certification_status(
            "mat-qual",
            MatrixCertificationStatus.IN_QUALIFICATION,
            notes="Testing HIPAA controls",
        )
        self.assertEqual(updated.status, MatrixCertificationStatus.IN_QUALIFICATION)
        self.assertEqual(updated.notes, "Testing HIPAA controls")

    def test_certify_success(self) -> None:
        rec = MatrixCertificationRecord("mat-cert", "sovereign", "oracle-to-postgres", VerticalDomain.FINANCIAL_SERVICES)
        self.engine.register_matrix_cell(rec)
        self.engine.record_compliance_controls("mat-cert", passed=100, total=100)

        certified = self.engine.update_certification_status(
            "mat-cert",
            MatrixCertificationStatus.CERTIFIED,
            certified_by="External Independent Certifier",
            evidence_ref="ev-merkle-bundle-999",
            notes="PCI-DSS and SOC2 full compliance verified",
        )
        self.assertEqual(certified.status, MatrixCertificationStatus.CERTIFIED)
        self.assertEqual(certified.certified_by, "External Independent Certifier")
        self.assertEqual(certified.evidence_bundle_ref, "ev-merkle-bundle-999")
        self.assertTrue(len(certified.certified_at) > 0)

    def test_certify_fails_without_certified_by(self) -> None:
        rec = MatrixCertificationRecord("mat-nobp", "ed", "r", VerticalDomain.PUBLIC_SECTOR)
        self.engine.register_matrix_cell(rec)
        with self.assertRaises(ValueError):
            self.engine.update_certification_status(
                "mat-nobp", MatrixCertificationStatus.CERTIFIED, certified_by=""
            )

    def test_certify_fails_with_incomplete_controls(self) -> None:
        rec = MatrixCertificationRecord("mat-incomp", "ed", "r", VerticalDomain.FINANCIAL_SERVICES)
        self.engine.register_matrix_cell(rec)
        self.engine.record_compliance_controls("mat-incomp", passed=98, total=100)

        with self.assertRaises(ValueError):
            self.engine.update_certification_status(
                "mat-incomp", MatrixCertificationStatus.CERTIFIED, certified_by="Auditor"
            )

    def test_query_matrix(self) -> None:
        self.engine.register_matrix_cell(
            MatrixCertificationRecord("m1", "air-gap", "cobol-java", VerticalDomain.FINANCIAL_SERVICES)
        )
        self.engine.register_matrix_cell(
            MatrixCertificationRecord("m2", "air-gap", "cpp-rust", VerticalDomain.AEROSPACE_DEFENSE)
        )
        self.engine.register_matrix_cell(
            MatrixCertificationRecord("m3", "saas", "react-vue", VerticalDomain.RETAIL_COMMERCE)
        )

        by_ed = self.engine.query_matrix(edition="air-gap")
        self.assertEqual(len(by_ed), 2)

        by_vert = self.engine.query_matrix(vertical=VerticalDomain.RETAIL_COMMERCE)
        self.assertEqual(len(by_vert), 1)
        self.assertEqual(by_vert[0].matrix_id, "m3")

        by_route = self.engine.query_matrix(route_key="cpp-rust")
        self.assertEqual(len(by_route), 1)
        self.assertEqual(by_route[0].matrix_id, "m2")

    def test_get_vertical_certification_report(self) -> None:
        self.engine.register_matrix_cell(
            MatrixCertificationRecord("m1", "sovereign", "r1", VerticalDomain.FINANCIAL_SERVICES)
        )
        self.engine.record_compliance_controls("m1", 10, 10)
        self.engine.update_certification_status("m1", MatrixCertificationStatus.CERTIFIED, certified_by="Audit")

        self.engine.register_matrix_cell(
            MatrixCertificationRecord("m2", "sovereign", "r2", VerticalDomain.PUBLIC_SECTOR)
        )
        self.engine.record_compliance_controls("m2", 5, 10)

        report = self.engine.get_vertical_certification_report()
        self.assertEqual(report["total_cells"], 2)
        self.assertEqual(report["certified_cells"], 1)
        self.assertEqual(report["overall_coverage_pct"], 50.0)
        self.assertEqual(report["total_controls_passed"], 15)
        self.assertEqual(report["total_controls_total"], 20)
        self.assertEqual(report["control_compliance_pct"], 75.0)


if __name__ == "__main__":
    unittest.main()
