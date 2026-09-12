"""
Tests for OperationsEvidenceReportingEngine.
"""

import unittest
import hashlib
from typing import Dict, Any

from elmos_mature_platform.types import (
    CustomerOperationsReport,
    OperationalEvidenceItem,
    EvidenceReportType,
)
from elmos_mature_platform.operations_evidence_reporting_engine import (
    OperationsEvidenceReportingEngine,
)

class TestOperationsEvidenceReportingEngine(unittest.TestCase):

    def setUp(self):
        self.engine = OperationsEvidenceReportingEngine()

    def test_create_report_success(self):
        report = CustomerOperationsReport(
            report_id="r1",
            customer_id="c1",
            report_type=EvidenceReportType.DAILY_OPS,
            time_window_start="2026-09-11T00:00:00Z",
            time_window_end="2026-09-11T23:59:59Z"
        )
        report_id = self.engine.create_report(report)
        self.assertEqual(report_id, "r1")
        self.assertEqual(len(self.engine._reports), 1)

    def test_create_report_empty_id(self):
        report = CustomerOperationsReport(
            report_id="",
            customer_id="c1",
            report_type=EvidenceReportType.DAILY_OPS,
            time_window_start="2026-09-11T00:00:00Z",
            time_window_end="2026-09-11T23:59:59Z"
        )
        with self.assertRaisesRegex(ValueError, "Report ID cannot be empty"):
            self.engine.create_report(report)

    def test_create_report_multiple(self):
        r1 = CustomerOperationsReport(report_id="r1", customer_id="c1", report_type=EvidenceReportType.DAILY_OPS, time_window_start="", time_window_end="")
        r2 = CustomerOperationsReport(report_id="r2", customer_id="c1", report_type=EvidenceReportType.DAILY_OPS, time_window_start="", time_window_end="")
        self.engine.create_report(r1)
        self.engine.create_report(r2)
        self.assertEqual(len(self.engine._reports), 2)
        self.assertEqual(self.engine._reports["r1"].report_id, "r1")

    def test_record_evidence_success(self):
        item = OperationalEvidenceItem(
            item_id="e1",
            report_id="r1",
            evidence_type="metric",
            source_system="datadog",
            payload={"cpu": 50},
        )
        item_id = self.engine.record_evidence(item)
        self.assertEqual(item_id, "e1")
        self.assertTrue(item.provenance_hash != "")

    def test_record_evidence_computes_correct_hash(self):
        payload = {"mem": 100}
        item = OperationalEvidenceItem(
            item_id="e1",
            report_id="r1",
            evidence_type="metric",
            source_system="sys",
            payload=payload,
        )
        self.engine.record_evidence(item)
        expected_hash = hashlib.sha256(f"sysmetric{str(payload)}".encode("utf-8")).hexdigest()
        self.assertEqual(item.provenance_hash, expected_hash)

    def test_record_evidence_with_existing_hash(self):
        item = OperationalEvidenceItem(
            item_id="e1",
            report_id="r1",
            evidence_type="metric",
            source_system="datadog",
            payload={"cpu": 50},
            provenance_hash="myhash"
        )
        item_id = self.engine.record_evidence(item)
        self.assertEqual(item.provenance_hash, "myhash")

    def test_record_evidence_empty_id(self):
        item = OperationalEvidenceItem(
            item_id="",
            report_id="r1",
            evidence_type="metric",
            source_system="datadog"
        )
        with self.assertRaisesRegex(ValueError, "Evidence ID cannot be empty"):
            self.engine.record_evidence(item)

    def test_link_evidence_to_report(self):
        report = CustomerOperationsReport(
            report_id="r1", customer_id="c1", report_type=EvidenceReportType.DAILY_OPS,
            time_window_start="", time_window_end=""
        )
        item = OperationalEvidenceItem(item_id="e1", report_id="r1", evidence_type="metric", source_system="sys")
        self.engine.create_report(report)
        self.engine.record_evidence(item)
        
        res_report = self.engine.link_evidence_to_report("r1", "e1")
        self.assertIn("e1", res_report.evidence_items)

    def test_link_evidence_unknown_report(self):
        item = OperationalEvidenceItem(item_id="e1", report_id="r1", evidence_type="metric", source_system="sys")
        self.engine.record_evidence(item)
        with self.assertRaisesRegex(ValueError, "Unknown report ID"):
            self.engine.link_evidence_to_report("r1", "e1")

    def test_link_evidence_unknown_evidence(self):
        report = CustomerOperationsReport(
            report_id="r1", customer_id="c1", report_type=EvidenceReportType.DAILY_OPS,
            time_window_start="", time_window_end=""
        )
        self.engine.create_report(report)
        with self.assertRaisesRegex(ValueError, "Unknown evidence ID"):
            self.engine.link_evidence_to_report("r1", "e1")

    def test_link_evidence_idempotent(self):
        report = CustomerOperationsReport(
            report_id="r1", customer_id="c1", report_type=EvidenceReportType.DAILY_OPS,
            time_window_start="", time_window_end=""
        )
        item = OperationalEvidenceItem(item_id="e1", report_id="r1", evidence_type="metric", source_system="sys")
        self.engine.create_report(report)
        self.engine.record_evidence(item)
        
        self.engine.link_evidence_to_report("r1", "e1")
        res_report = self.engine.link_evidence_to_report("r1", "e1")
        self.assertEqual(len(res_report.evidence_items), 1)

    def test_verify_evidence_integrity_success(self):
        item = OperationalEvidenceItem(item_id="e1", report_id="r1", evidence_type="metric", source_system="sys", payload={"a": 1})
        self.engine.record_evidence(item)
        self.assertTrue(self.engine.verify_evidence_integrity("e1"))
        self.assertTrue(self.engine._evidence_items["e1"].verified)

    def test_verify_evidence_integrity_tampered_payload(self):
        item = OperationalEvidenceItem(item_id="e1", report_id="r1", evidence_type="metric", source_system="sys", payload={"a": 1})
        self.engine.record_evidence(item)
        # Tamper
        self.engine._evidence_items["e1"].payload = {"a": 2}
        self.assertFalse(self.engine.verify_evidence_integrity("e1"))
        self.assertFalse(self.engine._evidence_items["e1"].verified)

    def test_verify_evidence_integrity_tampered_type(self):
        item = OperationalEvidenceItem(item_id="e1", report_id="r1", evidence_type="metric", source_system="sys", payload={"a": 1})
        self.engine.record_evidence(item)
        # Tamper
        self.engine._evidence_items["e1"].evidence_type = "log"
        self.assertFalse(self.engine.verify_evidence_integrity("e1"))
        self.assertFalse(self.engine._evidence_items["e1"].verified)

    def test_verify_evidence_integrity_tampered_source(self):
        item = OperationalEvidenceItem(item_id="e1", report_id="r1", evidence_type="metric", source_system="sys", payload={"a": 1})
        self.engine.record_evidence(item)
        # Tamper
        self.engine._evidence_items["e1"].source_system = "other"
        self.assertFalse(self.engine.verify_evidence_integrity("e1"))
        self.assertFalse(self.engine._evidence_items["e1"].verified)

    def test_verify_evidence_integrity_unknown(self):
        with self.assertRaisesRegex(ValueError, "Unknown evidence ID"):
            self.engine.verify_evidence_integrity("e1")

    def test_signoff_report_success(self):
        report = CustomerOperationsReport(
            report_id="r1", customer_id="c1", report_type=EvidenceReportType.DAILY_OPS,
            time_window_start="", time_window_end=""
        )
        item = OperationalEvidenceItem(item_id="e1", report_id="r1", evidence_type="metric", source_system="sys", payload={"a": 1})
        self.engine.create_report(report)
        self.engine.record_evidence(item)
        self.engine.link_evidence_to_report("r1", "e1")
        
        signed = self.engine.signoff_report("r1", "approver1")
        self.assertEqual(signed.signoff_by, "approver1")

    def test_signoff_report_multiple_evidence_success(self):
        report = CustomerOperationsReport(
            report_id="r1", customer_id="c1", report_type=EvidenceReportType.DAILY_OPS,
            time_window_start="", time_window_end=""
        )
        item1 = OperationalEvidenceItem(item_id="e1", report_id="r1", evidence_type="metric", source_system="sys", payload={"a": 1})
        item2 = OperationalEvidenceItem(item_id="e2", report_id="r1", evidence_type="log", source_system="sys", payload={"b": 2})
        self.engine.create_report(report)
        self.engine.record_evidence(item1)
        self.engine.record_evidence(item2)
        self.engine.link_evidence_to_report("r1", "e1")
        self.engine.link_evidence_to_report("r1", "e2")
        
        signed = self.engine.signoff_report("r1", "approver1")
        self.assertEqual(signed.signoff_by, "approver1")

    def test_signoff_report_no_evidence(self):
        report = CustomerOperationsReport(
            report_id="r1", customer_id="c1", report_type=EvidenceReportType.DAILY_OPS,
            time_window_start="", time_window_end=""
        )
        self.engine.create_report(report)
        with self.assertRaisesRegex(ValueError, "Cannot signoff report without evidence"):
            self.engine.signoff_report("r1", "approver1")

    def test_signoff_report_tampered_evidence(self):
        report = CustomerOperationsReport(
            report_id="r1", customer_id="c1", report_type=EvidenceReportType.DAILY_OPS,
            time_window_start="", time_window_end=""
        )
        item = OperationalEvidenceItem(item_id="e1", report_id="r1", evidence_type="metric", source_system="sys", payload={"a": 1})
        self.engine.create_report(report)
        self.engine.record_evidence(item)
        self.engine.link_evidence_to_report("r1", "e1")
        self.engine._evidence_items["e1"].payload = {"a": 2}
        
        with self.assertRaisesRegex(ValueError, "failed verification"):
            self.engine.signoff_report("r1", "approver1")
            
    def test_signoff_report_one_of_many_tampered(self):
        report = CustomerOperationsReport(
            report_id="r1", customer_id="c1", report_type=EvidenceReportType.DAILY_OPS,
            time_window_start="", time_window_end=""
        )
        item1 = OperationalEvidenceItem(item_id="e1", report_id="r1", evidence_type="metric", source_system="sys", payload={"a": 1})
        item2 = OperationalEvidenceItem(item_id="e2", report_id="r1", evidence_type="log", source_system="sys", payload={"b": 2})
        self.engine.create_report(report)
        self.engine.record_evidence(item1)
        self.engine.record_evidence(item2)
        self.engine.link_evidence_to_report("r1", "e1")
        self.engine.link_evidence_to_report("r1", "e2")
        self.engine._evidence_items["e2"].payload = {"b": 3}
        
        with self.assertRaisesRegex(ValueError, "failed verification"):
            self.engine.signoff_report("r1", "approver1")

    def test_signoff_unknown_report(self):
        with self.assertRaisesRegex(ValueError, "Unknown report ID"):
            self.engine.signoff_report("r1", "appr")
            
    def test_signoff_empty_approver(self):
        report = CustomerOperationsReport(
            report_id="r1", customer_id="c1", report_type=EvidenceReportType.DAILY_OPS,
            time_window_start="", time_window_end=""
        )
        item = OperationalEvidenceItem(item_id="e1", report_id="r1", evidence_type="metric", source_system="sys", payload={"a": 1})
        self.engine.create_report(report)
        self.engine.record_evidence(item)
        self.engine.link_evidence_to_report("r1", "e1")
        
        with self.assertRaisesRegex(ValueError, "Approver cannot be empty"):
            self.engine.signoff_report("r1", "")

    def test_publish_report_success(self):
        report = CustomerOperationsReport(
            report_id="r1", customer_id="c1", report_type=EvidenceReportType.DAILY_OPS,
            time_window_start="", time_window_end=""
        )
        item = OperationalEvidenceItem(item_id="e1", report_id="r1", evidence_type="metric", source_system="sys", payload={"a": 1})
        self.engine.create_report(report)
        self.engine.record_evidence(item)
        self.engine.link_evidence_to_report("r1", "e1")
        self.engine.signoff_report("r1", "approver1")
        
        pub = self.engine.publish_report("r1")
        self.assertTrue(pub.published)

    def test_publish_report_no_signoff(self):
        report = CustomerOperationsReport(
            report_id="r1", customer_id="c1", report_type=EvidenceReportType.DAILY_OPS,
            time_window_start="", time_window_end=""
        )
        self.engine.create_report(report)
        with self.assertRaisesRegex(ValueError, "Cannot publish report without signoff"):
            self.engine.publish_report("r1")

    def test_publish_unknown_report(self):
        with self.assertRaisesRegex(ValueError, "Unknown report ID"):
            self.engine.publish_report("r1")
            
    def test_publish_already_published(self):
        report = CustomerOperationsReport(
            report_id="r1", customer_id="c1", report_type=EvidenceReportType.DAILY_OPS,
            time_window_start="", time_window_end=""
        )
        item = OperationalEvidenceItem(item_id="e1", report_id="r1", evidence_type="metric", source_system="sys", payload={"a": 1})
        self.engine.create_report(report)
        self.engine.record_evidence(item)
        self.engine.link_evidence_to_report("r1", "e1")
        self.engine.signoff_report("r1", "approver1")
        self.engine.publish_report("r1")
        pub = self.engine.publish_report("r1")
        self.assertTrue(pub.published)

    def test_get_customer_reports_no_filter(self):
        report1 = CustomerOperationsReport(report_id="r1", customer_id="c1", report_type=EvidenceReportType.DAILY_OPS, time_window_start="", time_window_end="")
        report2 = CustomerOperationsReport(report_id="r2", customer_id="c1", report_type=EvidenceReportType.SLA_AUDIT, time_window_start="", time_window_end="")
        report3 = CustomerOperationsReport(report_id="r3", customer_id="c2", report_type=EvidenceReportType.DAILY_OPS, time_window_start="", time_window_end="")
        self.engine.create_report(report1)
        self.engine.create_report(report2)
        self.engine.create_report(report3)
        
        reps = self.engine.get_customer_reports("c1")
        self.assertEqual(len(reps), 2)
        ids = {r.report_id for r in reps}
        self.assertIn("r1", ids)
        self.assertIn("r2", ids)

    def test_get_customer_reports_with_filter(self):
        report1 = CustomerOperationsReport(report_id="r1", customer_id="c1", report_type=EvidenceReportType.DAILY_OPS, time_window_start="", time_window_end="")
        report2 = CustomerOperationsReport(report_id="r2", customer_id="c1", report_type=EvidenceReportType.SLA_AUDIT, time_window_start="", time_window_end="")
        self.engine.create_report(report1)
        self.engine.create_report(report2)
        
        reps = self.engine.get_customer_reports("c1", EvidenceReportType.SLA_AUDIT)
        self.assertEqual(len(reps), 1)
        self.assertEqual(reps[0].report_id, "r2")
        
    def test_get_customer_reports_empty(self):
        self.assertEqual(self.engine.get_customer_reports("unknown"), [])

    def test_get_unverified_evidence_empty(self):
        item = OperationalEvidenceItem(item_id="e1", report_id="r1", evidence_type="metric", source_system="sys")
        self.engine.record_evidence(item)
        self.assertEqual(len(self.engine.get_unverified_evidence()), 0)

    def test_get_unverified_evidence_tampered(self):
        item = OperationalEvidenceItem(item_id="e1", report_id="r1", evidence_type="metric", source_system="sys")
        self.engine.record_evidence(item)
        self.engine._evidence_items["e1"].payload = {"tampered": True}
        unverified = self.engine.get_unverified_evidence()
        self.assertEqual(len(unverified), 1)
        self.assertEqual(unverified[0].item_id, "e1")

    def test_get_unverified_evidence_explicitly_false(self):
        item = OperationalEvidenceItem(item_id="e1", report_id="r1", evidence_type="metric", source_system="sys")
        self.engine.record_evidence(item)
        self.engine._evidence_items["e1"].verified = False
        unverified = self.engine.get_unverified_evidence()
        self.assertEqual(len(unverified), 1)

    def test_get_operations_audit_summary_empty(self):
        summary = self.engine.get_operations_audit_summary()
        self.assertEqual(summary["total_reports"], 0)
        self.assertEqual(summary["published_count"], 0)
        self.assertEqual(summary["total_evidence_items"], 0)
        self.assertEqual(summary["verification_rate_pct"], 100.0)

    def test_get_operations_audit_summary_populated(self):
        report = CustomerOperationsReport(report_id="r1", customer_id="c1", report_type=EvidenceReportType.DAILY_OPS, time_window_start="", time_window_end="")
        item = OperationalEvidenceItem(item_id="e1", report_id="r1", evidence_type="metric", source_system="sys")
        self.engine.create_report(report)
        self.engine.record_evidence(item)
        self.engine.link_evidence_to_report("r1", "e1")
        self.engine.signoff_report("r1", "approver1")
        self.engine.publish_report("r1")
        
        summary = self.engine.get_operations_audit_summary()
        self.assertEqual(summary["total_reports"], 1)
        self.assertEqual(summary["published_count"], 1)
        self.assertEqual(summary["total_evidence_items"], 1)
        self.assertEqual(summary["verification_rate_pct"], 100.0)

    def test_get_operations_audit_summary_with_tampered(self):
        report = CustomerOperationsReport(report_id="r1", customer_id="c1", report_type=EvidenceReportType.DAILY_OPS, time_window_start="", time_window_end="")
        item1 = OperationalEvidenceItem(item_id="e1", report_id="r1", evidence_type="metric", source_system="sys")
        item2 = OperationalEvidenceItem(item_id="e2", report_id="r1", evidence_type="metric", source_system="sys")
        self.engine.create_report(report)
        self.engine.record_evidence(item1)
        self.engine.record_evidence(item2)
        
        self.engine._evidence_items["e2"].payload = {"tampered": True}
        
        summary = self.engine.get_operations_audit_summary()
        self.assertEqual(summary["verification_rate_pct"], 50.0)
        
    def test_get_operations_audit_summary_all_tampered(self):
        report = CustomerOperationsReport(report_id="r1", customer_id="c1", report_type=EvidenceReportType.DAILY_OPS, time_window_start="", time_window_end="")
        item1 = OperationalEvidenceItem(item_id="e1", report_id="r1", evidence_type="metric", source_system="sys")
        self.engine.create_report(report)
        self.engine.record_evidence(item1)
        
        self.engine._evidence_items["e1"].payload = {"tampered": True}
        
        summary = self.engine.get_operations_audit_summary()
        self.assertEqual(summary["verification_rate_pct"], 0.0)


if __name__ == '__main__':
    unittest.main()
