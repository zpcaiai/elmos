import base64
import unittest
from datetime import UTC, datetime

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from elmos_openhands.errors import ContractViolation
from elmos_openhands.evidence import EvidenceTrustStore, ed25519_trust_key
from elmos_openhands.models import canonical_json, digest_of
from elmos_openhands.security_review import IndependentSecurityReviewIntake, SecurityReviewRequest


class SecurityReviewIntakeTests(unittest.TestCase):
    def setUp(self):
        self.private_key = Ed25519PrivateKey.generate()
        self.trust_store = EvidenceTrustStore(
            (
                ed25519_trust_key(
                    self.private_key.public_key().public_bytes_raw(),
                    key_id="security-reviewer-key",
                    actor_id="independent-security-reviewer",
                    role="security_reviewer",
                ),
            )
        )
        self.intake = IndependentSecurityReviewIntake(self.trust_store)
        self.scope = "sha256:" + "a" * 64
        self.artifact = "sha256:" + "b" * 64
        self.now = datetime(2026, 8, 28, 8, 0, tzinfo=UTC)

    def _report(self, **updates):
        report = {
            "schema_version": "1.0",
            "review_id": "review-20260828",
            "scope_digest": self.scope,
            "artifact_digest": self.artifact,
            "reviewer_id": "independent-security-reviewer",
            "executor_id": "elmos-local-executor",
            "authorization_ref": "security-review-authorization",
            "decision": "PASS",
            "critical_findings": 0,
            "high_findings": 0,
            "findings_digest": digest_of([]),
            "completed_at": "2026-08-28T07:55:00Z",
            "expires_at": "2026-09-28T07:55:00Z",
        }
        report.update(updates)
        signature = self.private_key.sign(canonical_json(report).encode("utf-8"))
        report["signature"] = {
            "algorithm": "Ed25519",
            "key_id": "security-reviewer-key",
            "signature": base64.b64encode(signature).decode("ascii"),
        }
        return report

    def test_request_is_durable_but_not_run(self):
        request = SecurityReviewRequest(
            self.scope, self.artifact, "elmos-local-executor", "auth", "2026-08-28T08:00:00Z"
        )
        self.assertEqual(request.status, "NOT_RUN")
        self.assertEqual(request.as_dict()["certification"], "NOT_CERTIFIED")

    def test_distinct_signed_review_is_ready_for_external_gate_only(self):
        acceptance = self.intake.accept(
            self._report(),
            expected_scope_digest=self.scope,
            expected_artifact_digest=self.artifact,
            executor_id="elmos-local-executor",
            now=self.now,
        )
        self.assertEqual(acceptance.status, "READY_FOR_EXTERNAL_GATE")
        self.assertEqual(acceptance.as_dict()["certification"], "NOT_CERTIFIED")

    def test_self_review_and_tampering_fail_closed(self):
        with self.assertRaises(ContractViolation):
            self.intake.accept(
                self._report(reviewer_id="elmos-local-executor"),
                expected_scope_digest=self.scope,
                expected_artifact_digest=self.artifact,
                executor_id="elmos-local-executor",
                now=self.now,
            )
        tampered = self._report()
        tampered["high_findings"] = 1
        with self.assertRaises(ContractViolation):
            self.intake.accept(
                tampered,
                expected_scope_digest=self.scope,
                expected_artifact_digest=self.artifact,
                executor_id="elmos-local-executor",
                now=self.now,
            )


if __name__ == "__main__":
    unittest.main()
