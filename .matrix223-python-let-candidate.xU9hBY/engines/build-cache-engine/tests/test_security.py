"""SEC-001..003: tenant isolation, secret blocking and provenance forgery."""

from __future__ import annotations

import dataclasses
import tarfile
import zipfile
from pathlib import Path

import pytest

from conftest import TENANT, digest
from elmos_build_cache.cas import ContentAddressableStore
from elmos_build_cache.clock import ManualClock
from elmos_build_cache.config import SecurityConfig
from elmos_build_cache.db import SqliteMetadataStore
from elmos_build_cache.enums import CacheEntryStatus, TrustNamespace, ValidationLevel
from elmos_build_cache.errors import (
    ContractViolation,
    PermissionDenied,
    ProvenanceInvalid,
    SecretDetected,
    UnsafePath,
)
from elmos_build_cache.security import (
    AccessController,
    Ed25519ProvenanceSigner,
    EnvelopeCipher,
    Principal,
    Provenance,
    ProvenanceSigner,
    RevocationService,
    SecretScanner,
    SecurityGate,
    assert_no_symlinks,
    audit_summary,
    inspect_archive,
    redact,
    safe_extract,
)


@pytest.fixture
def signer() -> ProvenanceSigner:
    return Ed25519ProvenanceSigner.generate("elmos-provenance-1")


def provenance(clock: ManualClock, **overrides: object) -> Provenance:
    base = {
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


def test_sec_001_cross_tenant_access_is_denied_without_an_existence_signal(
    store: SqliteMetadataStore,
) -> None:
    """SEC-001: the denial is identical whether or not the object exists."""
    controller = AccessController(store)
    principal = Principal("analyst", "tenant-a")
    with pytest.raises(PermissionDenied) as present:
        controller.authorize_read(principal, "tenant-b", digest("a"))
    with pytest.raises(PermissionDenied) as absent:
        controller.authorize_read(principal, "tenant-b", digest("f"))
    assert present.value.message == absent.value.message
    assert audit_summary(controller)["denied"] == 2


def test_sec_002_secret_in_generated_output_blocks_upload_and_publish(tmp_path: Path) -> None:
    """SEC-002: shared upload and publication both fail closed."""
    tree = tmp_path / "candidate"
    (tree / "src").mkdir(parents=True)
    (tree / "src" / "Config.cs").write_text(
        'const string Key = "AKIAIOSFODNN7EXAMPLE";\n', encoding="utf-8"
    )
    gate = SecurityGate()
    with pytest.raises(SecretDetected):
        gate.check_before_remote_upload(tree)
    with pytest.raises(SecretDetected):
        gate.check_before_publish(tree)


def test_secret_scanner_ignores_placeholders() -> None:
    scanner = SecretScanner()
    assert scanner.scan_text('api_key = "your_key_here"') == []
    assert scanner.scan_text('token = "${GITHUB_TOKEN}"') == []
    assert scanner.scan_text('password = "{{ vault_password }}"') == []
    findings = scanner.scan_text('password = "s3cr3t-actual-value"')
    assert [finding.rule for finding in findings] == ["generic-password-assignment"]
    # The finding never carries the secret itself.
    assert "s3cr3t" not in str(findings[0].to_dict())


def test_sec_003_forged_provenance_is_rejected(signer: ProvenanceSigner, clock: ManualClock) -> None:
    """SEC-003: the signature covers the whole statement, so no field can move."""
    signed = signer.sign(provenance(clock))
    signer.verify(signed, clock.now())

    elevated = dataclasses.replace(
        signed,
        provenance=dataclasses.replace(
            signed.provenance, validation_level=ValidationLevel.PRODUCTION_CERTIFIED
        ),
    )
    with pytest.raises(ProvenanceInvalid):
        signer.verify(elevated, clock.now())

    swapped = dataclasses.replace(
        signed, provenance=dataclasses.replace(signed.provenance, subject_digest=digest("b"))
    )
    with pytest.raises(ProvenanceInvalid):
        signer.verify(swapped, clock.now())


def test_expired_and_unknown_key_provenance_is_rejected(
    signer: ProvenanceSigner, clock: ManualClock
) -> None:
    signed = signer.sign(provenance(clock))
    clock.advance(7200)
    with pytest.raises(ProvenanceInvalid, match="expired"):
        signer.verify(signed, clock.now())

    stranger = Ed25519ProvenanceSigner.generate("someone-elses-key")
    with pytest.raises(ProvenanceInvalid, match="unknown signing key"):
        signer.verify(stranger.sign(provenance(clock)), clock.now())


def test_untrusted_producer_cannot_claim_validation(store: SqliteMetadataStore) -> None:
    controller = AccessController(store)
    with pytest.raises(PermissionDenied):
        controller.check_promotion(
            Principal("fork-worker", TENANT, TrustNamespace.FORK),
            ValidationLevel.TEST_VERIFIED,
            "fork-worker",
        )


def test_producer_cannot_self_certify(store: SqliteMetadataStore) -> None:
    controller = AccessController(store)
    with pytest.raises(ProvenanceInvalid):
        controller.check_promotion(
            Principal("worker-1", TENANT, TrustNamespace.OFFICIAL),
            ValidationLevel.TEST_VERIFIED,
            "worker-1",
        )


def test_archive_bomb_and_traversal_are_blocked(tmp_path: Path) -> None:
    archive = tmp_path / "bomb.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as handle:
        handle.writestr("big.txt", "A" * 5_000_000)
        handle.writestr("../escape.txt", "x")
    report = inspect_archive(archive, SecurityConfig())
    assert "../escape.txt" in report.rejected
    assert any("expansion ratio" in item for item in report.rejected)
    with pytest.raises(ContractViolation):
        safe_extract(archive, tmp_path / "out", SecurityConfig())


def test_tar_symlink_member_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "links.tar"
    target = tmp_path / "payload.txt"
    target.write_text("data", encoding="utf-8")
    link = tmp_path / "link"
    link.symlink_to("/etc/passwd")
    with tarfile.open(archive, "w") as handle:
        handle.add(target, arcname="payload.txt")
        handle.add(link, arcname="link")
    assert "link" in inspect_archive(archive, SecurityConfig()).rejected


def test_safe_extract_accepts_a_well_formed_archive(tmp_path: Path) -> None:
    archive = tmp_path / "ok.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("src/App.cs", "class App {}")
    assert safe_extract(archive, tmp_path / "out", SecurityConfig()) == 1
    assert (tmp_path / "out" / "src" / "App.cs").read_text(encoding="utf-8") == "class App {}"


def test_escaping_symlink_blocks_publication(tmp_path: Path) -> None:
    tree = tmp_path / "tree"
    (tree / "src").mkdir(parents=True)
    (tree / "src" / "link").symlink_to("/etc/hostname")
    assert assert_no_symlinks(tree) == ["src/link"]
    with pytest.raises(UnsafePath):
        SecurityGate().check_before_publish(tree)


def test_executable_policy_can_be_enforced(tmp_path: Path) -> None:
    tree = tmp_path / "tree"
    tree.mkdir()
    script = tree / "run.sh"
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    script.chmod(0o755)
    gate = SecurityGate(config=SecurityConfig(allow_executable_output=False))
    with pytest.raises(ContractViolation):
        gate.check_before_publish(tree)


def test_revocation_propagates_to_dependents(
    store: SqliteMetadataStore, cas: ContentAddressableStore, clock: ManualClock
) -> None:
    from elmos_build_cache.db.records import ActionCacheRecord

    manifest = cas.put_bytes(b'{"kind":"elmos.action-result/v1"}')
    output = cas.put_bytes(b"generated")
    with store.transaction():
        for item in (manifest, output):
            store.register_artifact(TENANT, item, cas.info(item).size, "application/json", "blob")
        store.add_artifact_ref(TENANT, "action_result", manifest, output, "output")
        store.put_action_entry(
            ActionCacheRecord(
                tenant_id=TENANT,
                trust_namespace=TrustNamespace.BRANCH,
                action_key=digest("7"),
                result_manifest_digest=manifest,
                validation_level=ValidationLevel.TEST_VERIFIED,
                producer_identity="worker-1",
                provenance_digest=manifest,
                status=CacheEntryStatus.ACTIVE,
            )
        )

    service = RevocationService(store, clock)
    with store.transaction():
        effect = service.revoke_artifact(TENANT, output, "compromised generator")

    assert digest("7") in effect.action_entries
    entry = store.get_action_entry(TENANT, TrustNamespace.BRANCH, digest("7"))
    assert entry is not None and entry.status is CacheEntryStatus.REVOKED
    assert service.is_revoked(TENANT, "artifact", output)


def test_envelope_cipher_separates_tenants_and_detects_tampering() -> None:
    cipher = EnvelopeCipher({"tenant-a": b"k" * 32, "tenant-b": b"j" * 32})
    blob = cipher.encrypt("tenant-a", b"sensitive artifact")
    assert cipher.decrypt("tenant-a", blob) == b"sensitive artifact"
    # The tenant identity is authenticated data, so another tenant's key cannot
    # even be applied to this ciphertext.
    with pytest.raises(ProvenanceInvalid):
        cipher.decrypt("tenant-b", blob)
    with pytest.raises(ProvenanceInvalid):
        cipher.decrypt("tenant-a", blob[:-1] + bytes([blob[-1] ^ 0x01]))
    with pytest.raises(PermissionDenied):
        cipher.encrypt("tenant-c", b"x")


def test_telemetry_redaction_covers_nested_values() -> None:
    redacted = redact(
        {"run_id": "r1", "api_key": "secret", "nested": {"prompt": "text", "count": 3}}
    )
    assert redacted["api_key"] == "<redacted>"
    assert redacted["nested"]["prompt"] == "<redacted>"
    assert redacted["nested"]["count"] == 3
    assert redacted["run_id"] == "r1"
