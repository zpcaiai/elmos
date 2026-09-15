"""Adversarial Sabotage Blind Testing and Cryptographic Notary Verification Suite."""

from __future__ import annotations

import pytest

from elmos_proof_harness.delta_v32 import execute_v32_skill
from elmos_proof_harness.notary import (
    CryptographicNotary,
    NotarizedEvidenceEnvelope,
    SignatureVerificationError,
)


# ---- Cryptographic Notary Tests ----


def test_notary_sealing_and_verification() -> None:
    notary = CryptographicNotary(notary_id="test-notary-01")
    payload = {"suite": "integration", "passed": 120, "failed": 0}

    envelope = notary.notarize_evidence("ev-001", "test-report", payload)
    assert envelope.evidence_id == "ev-001"
    assert envelope.algorithm == "HMAC-SHA256"
    assert len(envelope.signature) > 10

    # Verification passes
    assert notary.verify_envelope(envelope, payload) is True


def test_notary_tampered_payload_rejected() -> None:
    notary = CryptographicNotary(notary_id="test-notary-01")
    original_payload = {"suite": "integration", "passed": 120, "failed": 0}
    tampered_payload = {"suite": "integration", "passed": 120, "failed": 1}  # Tampered!

    envelope = notary.notarize_evidence("ev-001", "test-report", original_payload)

    # Verification must raise SignatureVerificationError
    with pytest.raises(SignatureVerificationError, match="Payload digest mismatch"):
        notary.verify_envelope(envelope, tampered_payload)


def test_notary_tampered_signature_rejected() -> None:
    notary = CryptographicNotary(notary_id="test-notary-01")
    payload = {"commit": "abc1234"}
    envelope = notary.notarize_evidence("ev-002", "commit-proof", payload)

    # Tamper with signature
    tampered_env = NotarizedEvidenceEnvelope(
        envelope_id=envelope.envelope_id,
        evidence_id=envelope.evidence_id,
        evidence_type=envelope.evidence_type,
        payload_digest=envelope.payload_digest,
        notary_id=envelope.notary_id,
        timestamp=envelope.timestamp,
        algorithm=envelope.algorithm,
        signature=envelope.signature[:-4] + "AAAA",
    )

    with pytest.raises(SignatureVerificationError, match="Digital signature verification failed"):
        notary.verify_envelope(tampered_env, payload)


# ---- Sabotage Blind Gate Tests ----


def test_gate_sabotage_tampered_exit_code() -> None:
    """Sabotage attempt: runner exited with code 1, but someone tries to pass gate."""
    payload = {
        "audit_run_id": "audit-sabotage-01",
        "authoritative_evidence": {
            "test_evidence": {"exit_code": 1},  # Non-zero exit code!
            "build_evidence": {"exit_code": 0},
        },
        "sabotage_blind_test_passed": True,
        "external_verifier_attestations": ["ext-01"],
    }
    res = execute_v32_skill("release-evidence-exact-artifact", payload)
    assert res["status"] == "SUCCESS"
    assert res["gate_decision"] == "FAIL"  # Must fail closed!


def test_gate_sabotage_blind_test_failed() -> None:
    """Sabotage check failed: deliberate regression injection was not caught."""
    payload = {
        "audit_run_id": "audit-sabotage-02",
        "authoritative_evidence": {
            "test_evidence": {"exit_code": 0},
            "build_evidence": {"exit_code": 0},
        },
        "sabotage_blind_test_passed": False,  # Sabotage test failed!
        "external_verifier_attestations": ["ext-01"],
    }
    res = execute_v32_skill("release-evidence-exact-artifact", payload)
    assert res["status"] == "SUCCESS"
    assert res["gate_decision"] == "FAIL"


def test_gate_sabotage_missing_attestations() -> None:
    """Sabotage check: self-certification attempted without external attestations."""
    payload = {
        "audit_run_id": "audit-sabotage-03",
        "authoritative_evidence": {
            "test_evidence": {"exit_code": 0},
            "build_evidence": {"exit_code": 0},
        },
        "sabotage_blind_test_passed": True,
        "external_verifier_attestations": [],  # Missing required independent attestation!
    }
    res = execute_v32_skill("release-evidence-exact-artifact", payload)
    assert res["status"] == "SUCCESS"
    assert res["gate_decision"] == "FAIL"
