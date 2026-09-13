import os
from pathlib import Path
import sys
import unittest

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from elmos_mature_platform.types import (
    VexAssessmentResult,
    VexJustification,
    VexStatement,
    VexStatus,
)
from elmos_mature_platform.vex_applicability_engine import VexApplicabilityEngine


class TestVexApplicabilityComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = VexApplicabilityEngine()

    def test_record_statement(self):
        stmt = VexStatement(
            vex_id="vex-1",
            cve_id="CVE-2024-1234",
            product_id="pkg:npm/express@4.18.2",
            status=VexStatus.UNDER_INVESTIGATION,
        )
        vid = self.engine.record_statement(stmt)
        self.assertEqual(vid, "vex-1")
        retrieved = self.engine.get_statement("vex-1")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.cve_id, "CVE-2024-1234")

    def test_record_statement_missing_fields(self):
        s1 = VexStatement(vex_id="s1", cve_id="", product_id="prod")
        with self.assertRaises(ValueError):
            self.engine.record_statement(s1)

        s2 = VexStatement(vex_id="s2", cve_id="CVE-1", product_id="")
        with self.assertRaises(ValueError):
            self.engine.record_statement(s2)

    def test_update_status_not_affected_requires_justification(self):
        stmt = VexStatement(
            vex_id="v-up",
            cve_id="CVE-2024-9999",
            product_id="my-app:1.0",
            status=VexStatus.UNDER_INVESTIGATION,
        )
        self.engine.record_statement(stmt)

        # Updating to NOT_AFFECTED without justification raises ValueError
        with self.assertRaises(ValueError):
            self.engine.update_status("v-up", VexStatus.NOT_AFFECTED, justification=None)

        # Updating with justification succeeds
        updated = self.engine.update_status(
            "v-up",
            VexStatus.NOT_AFFECTED,
            justification=VexJustification.VULNERABLE_CODE_NOT_IN_EXECUTE_PATH,
            impact="Code path disabled in production build",
        )
        self.assertEqual(updated.status, VexStatus.NOT_AFFECTED.value)
        self.assertEqual(updated.justification, VexJustification.VULNERABLE_CODE_NOT_IN_EXECUTE_PATH)

    def test_is_vulnerability_actionable(self):
        # 1. Unregistered CVE -> Fail closed (actionable = True)
        self.assertTrue(self.engine.is_vulnerability_actionable("CVE-UNKNOWN", "prod-1"))

        # 2. Registered NOT_AFFECTED -> actionable = False
        s_suppressed = VexStatement(
            vex_id="s-supp",
            cve_id="CVE-SUPP",
            product_id="prod-1",
            status=VexStatus.NOT_AFFECTED.value,
            justification=VexJustification.COMPONENT_NOT_PRESENT,
        )
        self.engine.record_statement(s_suppressed)
        self.assertFalse(self.engine.is_vulnerability_actionable("CVE-SUPP", "prod-1"))

        # 3. Registered FIXED -> actionable = False
        s_fixed = VexStatement(
            vex_id="s-fix",
            cve_id="CVE-FIX",
            product_id="prod-1",
            status=VexStatus.FIXED.value,
        )
        self.engine.record_statement(s_fixed)
        self.assertFalse(self.engine.is_vulnerability_actionable("CVE-FIX", "prod-1"))

        # 4. Registered AFFECTED -> actionable = True
        s_aff = VexStatement(
            vex_id="s-aff",
            cve_id="CVE-AFF",
            product_id="prod-1",
            status=VexStatus.AFFECTED.value,
        )
        self.engine.record_statement(s_aff)
        self.assertTrue(self.engine.is_vulnerability_actionable("CVE-AFF", "prod-1"))

    def test_assess_product_cves(self):
        s1 = VexStatement(
            vex_id="v1",
            cve_id="CVE-1",
            product_id="app-1",
            status=VexStatus.NOT_AFFECTED.value,
            justification=VexJustification.INLINE_MITIGATIONS_EXIST,
        )
        s2 = VexStatement(
            vex_id="v2",
            cve_id="CVE-2",
            product_id="app-1",
            status=VexStatus.AFFECTED.value,
        )
        self.engine.record_statement(s1)
        self.engine.record_statement(s2)

        cve_findings = [
            {"cve_id": "CVE-1"},
            {"cve_id": "CVE-2"},
            {"cve_id": "CVE-3"},  # Unmapped, fails closed
        ]

        result = self.engine.assess_product_cves("app-1", cve_findings)
        self.assertEqual(result.total_cves, 3)
        self.assertEqual(result.suppressed_cves, 1)
        self.assertEqual(result.actionable_cves, 2)

    def test_export_openvex_document(self):
        stmt = VexStatement(
            vex_id="vex-open",
            cve_id="CVE-2024-5555",
            product_id="prod-alpha",
            status=VexStatus.NOT_AFFECTED.value,
            justification=VexJustification.VULNERABLE_CODE_CANNOT_BE_CONTROLLED_BY_ADVERSARY,
            impact_statement="Protected by upstream rate limiter",
        )
        self.engine.record_statement(stmt)

        doc = self.engine.export_openvex_document("prod-alpha")
        self.assertIn("@context", doc)
        self.assertEqual(doc["author"], "Elmos Mature Platform VEX Authority")
        self.assertEqual(len(doc["statements"]), 1)
        self.assertEqual(doc["statements"][0]["vulnerability"]["name"], "CVE-2024-5555")

    def test_get_vex_summary(self):
        s1 = VexStatement(vex_id="s1", cve_id="CVE-A", product_id="p", status=VexStatus.NOT_AFFECTED.value)
        s2 = VexStatement(vex_id="s2", cve_id="CVE-B", product_id="p", status=VexStatus.AFFECTED.value)
        s3 = VexStatement(vex_id="s3", cve_id="CVE-C", product_id="p", status=VexStatus.UNDER_INVESTIGATION.value)
        self.engine.record_statement(s1)
        self.engine.record_statement(s2)
        self.engine.record_statement(s3)

        summary = self.engine.get_vex_summary()
        self.assertEqual(summary["total_statements"], 3)
        self.assertEqual(summary["not_affected_count"], 1)
        self.assertEqual(summary["affected_count"], 1)
        self.assertEqual(summary["under_investigation_count"], 1)
        self.assertAlmostEqual(summary["suppression_ratio"], 1/3, places=3)


if __name__ == "__main__":
    unittest.main()
