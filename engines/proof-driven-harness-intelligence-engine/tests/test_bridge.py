from __future__ import annotations

import unittest

from elmos_pdhi.bridge import (
    BridgeResult,
    BridgeScope,
    BridgeStatus,
    CertificationSubmission,
    EvidenceWriteRequest,
    ExternalEffectRequest,
    ProofHarnessV3Bridge,
)
from elmos_pdhi.canonical import digest_bytes, digest_object
from elmos_pdhi.errors import IntegrityError, ValidationError


DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


def scope() -> BridgeScope:
    return BridgeScope("tenant-a", "project-a", "actor-a", DIGEST_A, DIGEST_B)


class _TrustedEvidence:
    trusted = True

    def record(self, request: EvidenceWriteRequest) -> BridgeResult:
        return BridgeResult(
            BridgeStatus.RECORDED,
            request.evidence_id,
            digest_object({"id": request.evidence_id}, domain="test-receipt"),
            {"content_digest": request.content_digest},
            "LOCAL_EXECUTED_SELF_ATTESTED",
            "NOT_CERTIFIED",
        )

    def readiness(self):
        return {"status": "READY", "external_evidence": "LOCAL_EXECUTED_SELF_ATTESTED"}


class _UntrustedCertification:
    trusted = True
    independent = False

    def submit(self, request: CertificationSubmission) -> BridgeResult:
        raise AssertionError("non-independent certification port must not be called")

    def readiness(self):
        return {"status": "READY", "certification": "CERTIFIED"}


class BridgeTests(unittest.TestCase):
    def test_unconfigured_ports_are_not_run(self) -> None:
        bridge = ProofHarnessV3Bridge()
        evidence = EvidenceWriteRequest(
            scope(),
            "evidence-1",
            DIGEST_A,
            "unit-test",
            "operational",
            "application/json",
            b"{}",
            "runner-a",
            "repository-owned",
            "idem-1",
        )
        result = bridge.record_evidence(evidence)
        self.assertEqual(BridgeStatus.NOT_RUN, result.status)
        self.assertEqual("NOT_RUN", result.external_evidence_status)
        self.assertEqual("NOT_CERTIFIED", result.certification_status)

    def test_trusted_evidence_port_preserves_byte_digest(self) -> None:
        bridge = ProofHarnessV3Bridge(evidence=_TrustedEvidence())
        request = EvidenceWriteRequest(
            scope(),
            "evidence-2",
            DIGEST_A,
            "unit-test",
            "operational",
            "application/octet-stream",
            b"immutable evidence",
            "runner-a",
            "repository-owned",
            "idem-2",
        )
        result = bridge.record_evidence(request)
        self.assertEqual(BridgeStatus.RECORDED, result.status)
        self.assertEqual(request.content_digest, result.detail["content_digest"])

    def test_effect_request_rejects_digest_mismatch(self) -> None:
        with self.assertRaises(IntegrityError):
            ExternalEffectRequest(
                scope(),
                "effect-1",
                "provider-a",
                "publish",
                "idem-3",
                {"artifact": DIGEST_A},
                DIGEST_B,
                "secret-lease-token",
                1,
                "poll-provider-receipt",
            )

    def test_effect_request_accepts_domain_bound_digest(self) -> None:
        request_body = {"artifact": DIGEST_A}
        request = ExternalEffectRequest(
            scope(),
            "effect-2",
            "provider-a",
            "publish",
            "idem-4",
            request_body,
            digest_object(request_body, domain="pdhi-external-effect-request"),
            "secret-lease-token",
            1,
            "poll-provider-receipt",
        )
        self.assertEqual("effect-2", request.effect_id)

    def test_non_independent_certifier_is_not_called(self) -> None:
        payload = b'{"bundle":"one"}'
        submission = CertificationSubmission(
            scope(),
            "certificate-1",
            digest_bytes(payload, domain="pdhi-certification-bundle"),
            payload,
            "E5",
            "idem-5",
        )
        result = ProofHarnessV3Bridge(
            certification=_UntrustedCertification()
        ).submit_certification(submission)
        self.assertEqual(BridgeStatus.NOT_RUN, result.status)
        self.assertEqual("NOT_CERTIFIED", result.certification_status)

    def test_certified_result_cannot_lack_receipt(self) -> None:
        with self.assertRaises(ValidationError):
            BridgeResult(
                BridgeStatus.CERTIFIED,
                None,
                None,
                {},
                "EXTERNALLY_VERIFIED",
                "CERTIFIED",
            )


if __name__ == "__main__":
    unittest.main()
