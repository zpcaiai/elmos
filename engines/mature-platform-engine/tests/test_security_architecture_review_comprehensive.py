import unittest
from elmos_mature_platform.security_architecture_review_engine import (
    SecurityArchitectureReviewEngine,
)
from elmos_mature_platform.types import (
    SecurityArchitectureReviewRecord,
    SecurityReviewVerdict,
    SecurityThreatModel,
    StrideCategory,
    ThreatSeverity,
)


class TestSecurityArchitectureReviewComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = SecurityArchitectureReviewEngine()

    def test_initiate_review_valid_and_invalid(self):
        rev_id = self.engine.initiate_review("payment-gateway", "v2.0.0", True)
        self.assertTrue(rev_id.startswith("rev-"))
        record = self.engine.get_review(rev_id)
        self.assertIsNotNone(record)
        self.assertEqual(record.system_name, "payment-gateway")
        self.assertEqual(record.verdict, SecurityReviewVerdict.REJECTED)

        with self.assertRaises(ValueError):
            self.engine.initiate_review("", "v1.0.0")
        with self.assertRaises(ValueError):
            self.engine.initiate_review("sys", "")

    def test_add_threat_model(self):
        rev_id = self.engine.initiate_review("auth-service", "v1.0.0")
        threat = SecurityThreatModel(
            threat_id="",
            component_name="jwt-validator",
            category=StrideCategory.SPOOFING,
            severity=ThreatSeverity.HIGH,
            description="Attackers might replay stolen bearer tokens.",
        )
        added = self.engine.add_threat_model(rev_id, threat)
        self.assertTrue(added.threat_id.startswith("threat-"))
        record = self.engine.get_review(rev_id)
        self.assertEqual(len(record.threats), 1)

        with self.assertRaises(ValueError):
            self.engine.add_threat_model("nonexistent-rev", threat)

    def test_mitigate_threat(self):
        rev_id = self.engine.initiate_review("auth-service", "v1.0.0")
        threat = SecurityThreatModel(
            threat_id="threat-tamper-1",
            component_name="session-cookie",
            category=StrideCategory.TAMPERING,
            severity=ThreatSeverity.CRITICAL,
            description="Cookie tampering without HMAC sign",
        )
        self.engine.add_threat_model(rev_id, threat)
        mitigated = self.engine.mitigate_threat(rev_id, "threat-tamper-1", "Use RS256 with key rotation and HMAC verification")
        self.assertTrue(mitigated.is_mitigated)
        self.assertIn("RS256", mitigated.mitigation_control)

        with self.assertRaises(ValueError):
            self.engine.mitigate_threat(rev_id, "threat-tamper-1", "")
        with self.assertRaises(ValueError):
            self.engine.mitigate_threat(rev_id, "unknown-threat", "control")

    def test_accept_residual_risk(self):
        rev_id = self.engine.initiate_review("audit-service", "v1.0.0")
        crit_threat = SecurityThreatModel(
            threat_id="threat-crit-1",
            component_name="db-pool",
            category=StrideCategory.ELEVATION_OF_PRIVILEGE,
            severity=ThreatSeverity.CRITICAL,
            description="Root injection in db pool",
        )
        med_threat = SecurityThreatModel(
            threat_id="threat-med-1",
            component_name="logger",
            category=StrideCategory.INFORMATION_DISCLOSURE,
            severity=ThreatSeverity.MEDIUM,
            description="Verbose logging of query params",
        )
        self.engine.add_threat_model(rev_id, crit_threat)
        self.engine.add_threat_model(rev_id, med_threat)

        # Critical threats cannot accept residual risk
        with self.assertRaises(PermissionError):
            self.engine.accept_residual_risk(rev_id, "threat-crit-1", "No time to fix")

        # Medium threat risk acceptance succeeds
        accepted = self.engine.accept_residual_risk(rev_id, "threat-med-1", "Internal dev cluster only")
        self.assertTrue(accepted.residual_risk_accepted)

    def test_evaluate_verdict_without_trust_boundaries(self):
        rev_id = self.engine.initiate_review("legacy-app", "v0.9.0", trust_boundaries_defined=False)
        review = self.engine.evaluate_security_verdict(rev_id, "sec-arch-1")
        self.assertEqual(review.verdict, SecurityReviewVerdict.REJECTED)
        self.assertIn("Must define formal trust boundaries", review.action_items[0])

    def test_evaluate_verdict_approved_rejected_conditional(self):
        # 1. Approved case
        rev_ok = self.engine.initiate_review("secure-storage", "v1.0.0", True)
        res_ok = self.engine.evaluate_security_verdict(rev_ok)
        self.assertEqual(res_ok.verdict, SecurityReviewVerdict.APPROVED)

        # 2. Rejected due to unmitigated high
        rev_rej = self.engine.initiate_review("insecure-api", "v1.0.0", True)
        self.engine.add_threat_model(
            rev_rej,
            SecurityThreatModel(
                threat_id="t-high",
                component_name="api-endpoint",
                category=StrideCategory.REPUDIATION,
                severity=ThreatSeverity.HIGH,
                description="Missing audit trace",
            ),
        )
        res_rej = self.engine.evaluate_security_verdict(rev_rej)
        self.assertEqual(res_rej.verdict, SecurityReviewVerdict.REJECTED)

        # 3. Conditional approval due to unmitigated medium
        rev_cond = self.engine.initiate_review("staging-api", "v1.0.0", True)
        self.engine.add_threat_model(
            rev_cond,
            SecurityThreatModel(
                threat_id="t-med",
                component_name="internal-bus",
                category=StrideCategory.DENIAL_OF_SERVICE,
                severity=ThreatSeverity.MEDIUM,
                description="Rate limit missing on internal endpoint",
            ),
        )
        res_cond = self.engine.evaluate_security_verdict(rev_cond)
        self.assertEqual(res_cond.verdict, SecurityReviewVerdict.CONDITIONAL_APPROVAL)

    def test_get_threats_by_stride_category_and_summary(self):
        rev_id = self.engine.initiate_review("gateway", "v1.0.0", True)
        self.engine.add_threat_model(
            rev_id,
            SecurityThreatModel(
                threat_id="t1",
                component_name="c1",
                category=StrideCategory.SPOOFING,
                severity=ThreatSeverity.LOW,
                description="Spoof test",
            ),
        )
        self.engine.add_threat_model(
            rev_id,
            SecurityThreatModel(
                threat_id="t2",
                component_name="c2",
                category=StrideCategory.TAMPERING,
                severity=ThreatSeverity.LOW,
                description="Tamper test",
            ),
        )

        stride_groups = self.engine.get_threats_by_stride_category(rev_id)
        self.assertEqual(len(stride_groups[StrideCategory.SPOOFING.value]), 1)
        self.assertEqual(len(stride_groups[StrideCategory.TAMPERING.value]), 1)
        self.assertEqual(len(stride_groups[StrideCategory.REPUDIATION.value]), 0)

        summary = self.engine.get_security_architecture_summary()
        self.assertEqual(summary["total_reviews"], 1)
        self.assertEqual(summary["total_modeled_threats"], 2)


if __name__ == "__main__":
    unittest.main()
