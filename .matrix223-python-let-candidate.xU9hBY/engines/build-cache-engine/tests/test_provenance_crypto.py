"""Asymmetric provenance signing and AEAD envelope encryption.

Closes the `elmos-cache-security-provenance` gap that previously read
"HMAC-SHA256 construction, not asymmetric signing / KMS-backed AEAD".
"""

from __future__ import annotations

import dataclasses

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from conftest import digest
from elmos_build_cache.clock import ManualClock
from elmos_build_cache.config import SecurityConfig
from elmos_build_cache.enums import TrustNamespace, ValidationLevel
from elmos_build_cache.errors import ContractViolation, PermissionDenied, ProvenanceInvalid
from elmos_build_cache.security import (
    Ed25519ProvenanceSigner,
    EnvelopeCipher,
    HmacProvenanceSigner,
    Provenance,
    require_asymmetric,
    signing_payload,
)


def provenance(clock: ManualClock, **overrides: object) -> Provenance:
    base: dict[str, object] = {
        "subject_digest": digest("a"),
        "action_key": digest("7"),
        "producer_identity": "worker-1",
        "validation_level": ValidationLevel.TEST_VERIFIED,
        "trust_namespace": TrustNamespace.OFFICIAL,
        "scope": "project:demo",
        "issued_at": clock.now(),
        "expires_at": clock.now() + 3600,
        "verifier_identities": ("independent-ci",),
    }
    base.update(overrides)
    return Provenance(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# Ed25519
# --------------------------------------------------------------------------
def test_signature_verifies_and_is_ed25519(clock: ManualClock) -> None:
    signer = Ed25519ProvenanceSigner.generate("prov-1")
    signed = signer.sign(provenance(clock))
    assert signed.algorithm == "ed25519"
    assert signer.asymmetric
    signer.verify(signed, clock.now())


def test_a_verifier_holds_no_forging_material(clock: ManualClock) -> None:
    """The point of asymmetric signing: verifiers cannot mint provenance."""
    signer = Ed25519ProvenanceSigner.generate("prov-1")
    verifier = Ed25519ProvenanceSigner.verifier(signer.public_keyset())

    signed = signer.sign(provenance(clock))
    verifier.verify(signed, clock.now())
    with pytest.raises(ContractViolation, match="verify-only"):
        verifier.sign(provenance(clock))


@pytest.mark.parametrize(
    "field",
    ["validation_level", "subject_digest", "action_key", "producer_identity", "scope", "trust_namespace"],
)
def test_no_field_of_a_signed_statement_can_be_swapped(clock: ManualClock, field: str) -> None:
    signer = Ed25519ProvenanceSigner.generate("prov-1")
    signed = signer.sign(provenance(clock))
    tampered_values: dict[str, object] = {
        "validation_level": ValidationLevel.PRODUCTION_CERTIFIED,
        "subject_digest": digest("b"),
        "action_key": digest("8"),
        "producer_identity": "attacker",
        "scope": "project:other",
        "trust_namespace": TrustNamespace.EXPERIMENTAL,
    }
    forged = dataclasses.replace(
        signed, provenance=dataclasses.replace(signed.provenance, **{field: tampered_values[field]})
    )
    with pytest.raises(ProvenanceInvalid, match="does not verify"):
        signer.verify(forged, clock.now())


def test_algorithm_downgrade_is_refused(clock: ManualClock) -> None:
    """A statement signed with HMAC cannot be presented as Ed25519."""
    hmac_signer = HmacProvenanceSigner({"prov-1": b"shared"}, "prov-1")
    ed_signer = Ed25519ProvenanceSigner.generate("prov-1")
    hmac_signed = hmac_signer.sign(provenance(clock))

    with pytest.raises(ProvenanceInvalid, match="algorithm mismatch"):
        ed_signer.verify(hmac_signed, clock.now())
    relabelled = dataclasses.replace(hmac_signed, algorithm="ed25519")
    with pytest.raises(ProvenanceInvalid):
        ed_signer.verify(relabelled, clock.now())


def test_key_substitution_is_refused(clock: ManualClock) -> None:
    """The key id is inside the signed payload, so it cannot be re-pointed."""
    signer = Ed25519ProvenanceSigner.generate("prov-1")
    attacker = Ed25519ProvenanceSigner.generate("prov-2")
    combined = Ed25519ProvenanceSigner.verifier(
        {**signer.public_keyset(), **attacker.public_keyset()}
    )

    signed = signer.sign(provenance(clock))
    relabelled = dataclasses.replace(signed, key_id="prov-2")
    with pytest.raises(ProvenanceInvalid, match="does not verify"):
        combined.verify(relabelled, clock.now())


def test_rotation_keeps_old_provenance_verifiable(clock: ManualClock) -> None:
    signer = Ed25519ProvenanceSigner.generate("prov-1")
    old = signer.sign(provenance(clock))

    signer.rotate("prov-2")
    new = signer.sign(provenance(clock))

    assert signer.active_key_id == "prov-2"
    assert old.key_id == "prov-1" and new.key_id == "prov-2"
    signer.verify(old, clock.now())
    signer.verify(new, clock.now())
    assert set(signer.public_keyset()) == {"prov-1", "prov-2"}


def test_signing_payload_is_domain_separated() -> None:
    statement = {"subject_digest": digest("a")}
    assert b"elmos.provenance/v1" in signing_payload(statement, "ed25519", "k1")
    assert signing_payload(statement, "ed25519", "k1") != signing_payload(statement, "ed25519", "k2")
    assert signing_payload(statement, "ed25519", "k1") != signing_payload(statement, "hmac-sha256", "k1")


def test_time_bounds_are_enforced(clock: ManualClock) -> None:
    signer = Ed25519ProvenanceSigner.generate("prov-1")
    signed = signer.sign(provenance(clock))
    clock.advance(7200)
    with pytest.raises(ProvenanceInvalid, match="expired"):
        signer.verify(signed, clock.now())

    future = signer.sign(provenance(clock, issued_at=clock.now() + 10_000, expires_at=clock.now() + 20_000))
    with pytest.raises(ProvenanceInvalid, match="clock skew"):
        signer.verify(future, clock.now())


def test_raw_key_material_round_trips(clock: ManualClock) -> None:
    private = Ed25519PrivateKey.generate()
    raw = private.private_bytes_raw()
    signer = Ed25519ProvenanceSigner({"prov-1": raw}, "prov-1")
    signed = signer.sign(provenance(clock))

    verifier = Ed25519ProvenanceSigner.verifier({"prov-1": private.public_key().public_bytes_raw()})
    verifier.verify(signed, clock.now())


def test_active_key_must_exist() -> None:
    with pytest.raises(ContractViolation, match="active signing key"):
        Ed25519ProvenanceSigner({"a": Ed25519PrivateKey.generate()}, "b")


# --------------------------------------------------------------------------
# policy
# --------------------------------------------------------------------------
def test_policy_refuses_a_shared_secret_signer() -> None:
    hmac_signer = HmacProvenanceSigner({"k1": b"shared"}, "k1")
    assert not hmac_signer.asymmetric
    with pytest.raises(ProvenanceInvalid, match="asymmetric"):
        require_asymmetric(hmac_signer)
    # An explicit opt-out exists for offline development, and only there.
    assert require_asymmetric(
        hmac_signer, SecurityConfig(require_asymmetric_provenance=False)
    ) is hmac_signer
    assert require_asymmetric(Ed25519ProvenanceSigner.generate()).asymmetric


def test_certification_refuses_a_symmetric_signer(store, clock: ManualClock) -> None:
    from elmos_build_cache.chaos import CertificationService

    with pytest.raises(ProvenanceInvalid, match="asymmetric"):
        CertificationService(store, HmacProvenanceSigner({"k1": b"shared"}, "k1"), clock)
    service = CertificationService(store, Ed25519ProvenanceSigner.generate("prov-1"), clock)
    assert service.signer.algorithm == "ed25519"


# --------------------------------------------------------------------------
# AES-256-GCM envelope
# --------------------------------------------------------------------------
def test_envelope_round_trip_and_tenant_binding() -> None:
    cipher = EnvelopeCipher(
        {"tenant-a": EnvelopeCipher.generate_key(), "tenant-b": EnvelopeCipher.generate_key()}
    )
    blob = cipher.encrypt("tenant-a", b"sensitive artifact bytes")
    assert cipher.decrypt("tenant-a", blob) == b"sensitive artifact bytes"
    with pytest.raises(ProvenanceInvalid, match="authentication"):
        cipher.decrypt("tenant-b", blob)


def test_every_byte_of_the_envelope_is_authenticated() -> None:
    cipher = EnvelopeCipher({"t": EnvelopeCipher.generate_key()})
    blob = cipher.encrypt("t", b"payload")
    for index in (2, len(blob) // 2, len(blob) - 1):
        tampered = bytearray(blob)
        tampered[index] ^= 0x01
        with pytest.raises((ProvenanceInvalid, PermissionDenied, Exception)):
            cipher.decrypt("t", bytes(tampered))


def test_nonces_are_unique_per_encryption() -> None:
    cipher = EnvelopeCipher({"t": EnvelopeCipher.generate_key()})
    blobs = {cipher.encrypt("t", b"identical plaintext") for _ in range(32)}
    assert len(blobs) == 32  # deterministic output would leak plaintext equality


def test_key_rotation_keeps_old_ciphertexts_readable() -> None:
    cipher = EnvelopeCipher({"t": {"k1": EnvelopeCipher.generate_key()}}, {"t": "k1"})
    old = cipher.encrypt("t", b"encrypted under k1")

    cipher.rotate("t", "k2")
    new = cipher.encrypt("t", b"encrypted under k2")

    assert cipher.key_ids("t") == ("k1", "k2")
    assert cipher.decrypt("t", old) == b"encrypted under k1"
    assert cipher.decrypt("t", new) == b"encrypted under k2"


def test_unknown_tenant_and_unknown_key_are_refused() -> None:
    cipher = EnvelopeCipher({"t": EnvelopeCipher.generate_key()})
    with pytest.raises(PermissionDenied):
        cipher.encrypt("other", b"x")
    with pytest.raises(PermissionDenied):
        cipher.decrypt("other", b"x" * 64)

    blob = bytearray(cipher.encrypt("t", b"x"))
    blob[2] = ord("Z")  # rewrite the key id in the header
    with pytest.raises(PermissionDenied, match="unknown encryption key"):
        cipher.decrypt("t", bytes(blob))


def test_truncated_and_wrong_version_envelopes_are_refused() -> None:
    from elmos_build_cache.errors import ConflictError

    cipher = EnvelopeCipher({"t": EnvelopeCipher.generate_key()})
    blob = cipher.encrypt("t", b"payload")
    with pytest.raises(ConflictError, match="truncated"):
        cipher.decrypt("t", blob[:5])
    with pytest.raises(ConflictError, match="unsupported envelope version"):
        cipher.decrypt("t", bytes([9]) + blob[1:])


def test_passphrase_material_is_stretched_to_a_full_key() -> None:
    cipher = EnvelopeCipher({"t": b"short-passphrase"})
    assert cipher.decrypt("t", cipher.encrypt("t", b"payload")) == b"payload"
