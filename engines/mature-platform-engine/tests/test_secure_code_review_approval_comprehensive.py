"""Comprehensive unit tests for SecureCodeReviewApprovalEngine (Batch 40 Skill 1373)."""

import unittest

from elmos_mature_platform.secure_code_review_approval_engine import (
    SecureCodeReviewApprovalEngine,
)
from elmos_mature_platform.types import (
    CodeReviewRiskLevel,
    ApprovalGateStatus,
    ChangeSensitivityFlag,
    SecureCodeReviewRequest,
    SecureReviewApprovalVerdict,
)


class TestSecureCodeReviewApprovalComprehensive(unittest.TestCase):
    """Test suite for change sensitivity classification, SOD checks, and quorum gating."""

    def setUp(self) -> None:
        self.engine = SecureCodeReviewApprovalEngine()
        self.sample_request = SecureCodeReviewRequest(
            request_id="cr-req-001",
            change_title="Refactor JWT token validator and KMS keys",
            author="dev-sam",
            diff_hash="a1b2c3d4e5f67890",
            sensitivity_flags=[ChangeSensitivityFlag.CRYPTO_CHANGE, ChangeSensitivityFlag.AUTH_CHANGE],
        )

    def test_submit_request_auto_risk_critical(self) -> None:
        rid = self.engine.submit_review_request(self.sample_request)
        self.assertEqual(rid, "cr-req-001")
        req = self.engine.get_request("cr-req-001")
        self.assertIsNotNone(req)
        self.assertEqual(req.risk_level, CodeReviewRiskLevel.CRITICAL)
        self.assertEqual(req.status, ApprovalGateStatus.PENDING)

    def test_submit_request_low_risk(self) -> None:
        low_req = SecureCodeReviewRequest(
            request_id="cr-req-002",
            change_title="Update frontend footer typography",
            author="dev-anna",
            diff_hash="f0e1d2c3b4a5",
            sensitivity_flags=[],
        )
        self.engine.submit_review_request(low_req)
        req = self.engine.get_request("cr-req-002")
        self.assertEqual(req.risk_level, CodeReviewRiskLevel.LOW)

    def test_author_cannot_self_approve_sod_violation(self) -> None:
        self.engine.submit_review_request(self.sample_request)
        verdict = SecureReviewApprovalVerdict(
            verdict_id="v1",
            request_id="cr-req-001",
            reviewer="dev-sam",  # Same as author
            decision=ApprovalGateStatus.APPROVED,
            rationale="Looks good to me!",
        )
        with self.assertRaises(ValueError):
            self.engine.record_verdict(verdict)

    def test_critical_risk_requires_two_approvers(self) -> None:
        self.engine.submit_review_request(self.sample_request)

        # First approver
        v1 = SecureReviewApprovalVerdict(
            verdict_id="v1",
            request_id="cr-req-001",
            reviewer="sec-lead-carol",
            decision=ApprovalGateStatus.APPROVED,
            rationale="Crypto primitives validated.",
        )
        req = self.engine.record_verdict(v1)
        # Still PENDING because CRITICAL requires 2 approvers
        self.assertEqual(req.status, ApprovalGateStatus.PENDING)
        self.assertEqual(len(req.approvers), 1)

        # Second approver
        v2 = SecureReviewApprovalVerdict(
            verdict_id="v2",
            request_id="cr-req-001",
            reviewer="arch-lead-bob",
            decision=ApprovalGateStatus.APPROVED,
            rationale="Key rotation lifecycle verified.",
        )
        req2 = self.engine.record_verdict(v2)
        # Now APPROVED
        self.assertEqual(req2.status, ApprovalGateStatus.APPROVED)
        self.assertEqual(len(req2.approvers), 2)

    def test_rejection_marks_rejected_immediately(self) -> None:
        self.engine.submit_review_request(self.sample_request)
        v = SecureReviewApprovalVerdict(
            verdict_id="v-rej",
            request_id="cr-req-001",
            reviewer="sec-auditor-eva",
            decision=ApprovalGateStatus.REJECTED,
            rationale="Hardcoded test IV detected.",
        )
        req = self.engine.record_verdict(v)
        self.assertEqual(req.status, ApprovalGateStatus.REJECTED)

    def test_add_sensitivity_flag_escalates_risk(self) -> None:
        req = SecureCodeReviewRequest(
            request_id="cr-req-003",
            change_title="Add new migration file",
            author="dev-dan",
            diff_hash="00112233",
            sensitivity_flags=[ChangeSensitivityFlag.DATA_PIPELINE],
        )
        self.engine.submit_review_request(req)
        self.assertEqual(req.risk_level, CodeReviewRiskLevel.MEDIUM)

        updated = self.engine.add_sensitivity_flag("cr-req-003", ChangeSensitivityFlag.IAM_PERMISSION)
        self.assertEqual(updated.risk_level, CodeReviewRiskLevel.CRITICAL)

    def test_governance_reporting(self) -> None:
        self.engine.submit_review_request(self.sample_request)
        report = self.engine.get_review_governance_report()
        self.assertEqual(report["total_requests"], 1)
        self.assertEqual(report["by_risk_level"]["critical"], 1)
        self.assertEqual(report["sensitivity_flag_distribution"]["crypto_change"], 1)


if __name__ == "__main__":
    unittest.main()
