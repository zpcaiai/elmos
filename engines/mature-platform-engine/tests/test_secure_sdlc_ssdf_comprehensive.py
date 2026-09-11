import unittest
from elmos_mature_platform.secure_sdlc_ssdf_engine import SecureSdlcSsdfEngine
from elmos_mature_platform.types import (
    SdlcStage,
    SsdfPracticeGroup,
    SsdfPracticeTask,
    SsdfTaskStatus,
)


class TestSecureSdlcSsdfComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = SecureSdlcSsdfEngine(seed_defaults=True)

    def test_default_seeded_practices(self):
        report = self.engine.get_overall_ssdf_report()
        self.assertGreaterEqual(report["total_registered_tasks"], 5)

        stages = self.engine.get_stage_requirements(SdlcStage.REQUIREMENTS)
        self.assertTrue(any(t.practice_code == "PO.1.1" for t in stages))

    def test_register_custom_practice_task(self):
        task = SsdfPracticeTask(
            task_id="ssdf-custom-pw-2",
            group=SsdfPracticeGroup.PRODUCE_SECURED_SOFTWARE,
            practice_code="PW.2.1",
            title="Protect software integrity with cryptographic signatures",
            applicable_sdlc_stages=[SdlcStage.RELEASE_DEPLOYMENT],
            mandatory=True,
        )
        tid = self.engine.register_practice_task(task)
        self.assertEqual(tid, "ssdf-custom-pw-2")
        stages = self.engine.get_stage_requirements(SdlcStage.RELEASE_DEPLOYMENT)
        self.assertTrue(any(t.practice_code == "PW.2.1" for t in stages))

    def test_update_task_status_and_evidence(self):
        updated = self.engine.update_task_status(
            "ssdf-po-1-1",
            status=SsdfTaskStatus.SATISFIED,
            evidence_ref="evidence://sha256/doc-sec-req-123",
            auditor="sec-lead-alice",
        )
        self.assertEqual(updated.status, SsdfTaskStatus.SATISFIED)
        self.assertIn("evidence://sha256/doc-sec-req-123", updated.evidence_artifacts)
        self.assertEqual(updated.auditor, "sec-lead-alice")

    def test_record_deficiency_and_audit_failure(self):
        defective = self.engine.record_deficiency(
            "ssdf-ps-1-1", deficiency="No branch protection enforced on main repo"
        )
        self.assertEqual(defective.status, SsdfTaskStatus.AUDIT_FAILED)
        self.assertIn("No branch protection enforced on main repo", defective.deficiencies)

        crits = self.engine.get_critical_deficiencies()
        self.assertTrue(any(c["task_id"] == "ssdf-ps-1-1" for c in crits))

    def test_create_audit_and_evaluate_compliance_pass(self):
        # Satisfy all default practices
        for tid in ["ssdf-po-1-1", "ssdf-ps-1-1", "ssdf-pw-1-1", "ssdf-pw-5-1", "ssdf-rv-1-1"]:
            self.engine.update_task_status(tid, SsdfTaskStatus.SATISFIED, evidence_ref=f"ev-{tid}")

        audit = self.engine.create_audit("core-gateway", "v2.4.0")
        evaluated = self.engine.evaluate_audit_compliance(audit.audit_id)

        self.assertEqual(evaluated.compliance_score, 100.0)
        self.assertTrue(evaluated.is_certified)
        self.assertEqual(len(evaluated.blocking_findings), 0)

    def test_evaluate_compliance_mandatory_failure(self):
        self.engine.record_deficiency("ssdf-pw-5-1", "Code review bypass observed")
        audit = self.engine.create_audit("payment-service", "v1.0.0")
        evaluated = self.engine.evaluate_audit_compliance(audit.audit_id)

        self.assertFalse(evaluated.is_certified)
        self.assertTrue(len(evaluated.blocking_findings) > 0)
        self.assertTrue(any("PW.5.1" in f for f in evaluated.blocking_findings))

    def test_get_group_compliance_breakdown(self):
        # Mark PO satisfied
        self.engine.update_task_status("ssdf-po-1-1", SsdfTaskStatus.SATISFIED)
        audit = self.engine.create_audit("auth-service", "v3.0.0")
        breakdown = self.engine.get_group_compliance_breakdown(audit.audit_id)

        po_stats = breakdown.get(SsdfPracticeGroup.PREPARE_ORGANIZATION.value)
        self.assertIsNotNone(po_stats)
        self.assertEqual(po_stats["satisfied"], 1)
        self.assertEqual(po_stats["compliance_rate"], 100.0)

    def test_export_ssdf_attestation_and_report(self):
        for tid in ["ssdf-po-1-1", "ssdf-ps-1-1", "ssdf-pw-1-1", "ssdf-pw-5-1", "ssdf-rv-1-1"]:
            self.engine.update_task_status(tid, SsdfTaskStatus.SATISFIED, evidence_ref=f"attest-{tid}")

        audit = self.engine.create_audit("analytics-pipeline", "v1.5.0")
        attestation = self.engine.export_ssdf_attestation(audit.audit_id)

        self.assertEqual(attestation["standard"], "NIST SP 800-218 (SSDF v1.1)")
        self.assertEqual(attestation["repository"], "analytics-pipeline")
        self.assertTrue(attestation["certified"])
        self.assertEqual(len(attestation["task_attestations"]), 5)


if __name__ == "__main__":
    unittest.main()
