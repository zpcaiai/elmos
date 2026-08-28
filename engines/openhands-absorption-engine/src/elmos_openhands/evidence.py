"""Digest-bound signed evidence packs with independent verification."""

from __future__ import annotations

import base64
import sqlite3
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Iterable, Protocol

from .errors import ContractViolation, NotConfigured, TenantIsolationError
from .models import ArtifactRef, Identity, canonical_json, digest_of, utc_now


@dataclass(frozen=True, slots=True)
class SignatureEnvelope:
    algorithm: str
    key_id: str
    signature: str

    def __post_init__(self) -> None:
        if self.algorithm not in {"Ed25519", "KMS_ASYMMETRIC_SIGN"} or not self.key_id or not self.signature:
            raise ContractViolation("signature envelope is invalid")


class EvidenceSigner(Protocol):
    key_id: str
    actor_id: str
    algorithm: str

    def sign(self, payload: bytes) -> SignatureEnvelope: ...


class KmsEvidenceSigner:
    def __init__(self, client: Any, *, key_id: str, actor_id: str, algorithm: str = "KMS_ASYMMETRIC_SIGN") -> None:
        if not key_id or not actor_id:
            raise ContractViolation("KMS signer requires key and actor identity")
        self.client, self.key_id, self.actor_id, self.algorithm = client, key_id, actor_id, algorithm

    def sign(self, payload: bytes) -> SignatureEnvelope:
        value = self.client.sign(key_id=self.key_id, message=payload, message_type="RAW", algorithm=self.algorithm)
        signature = value.get("signature")
        if isinstance(signature, bytes):
            signature = base64.b64encode(signature).decode("ascii")
        if not signature:
            raise NotConfigured("KMS did not return a signature")
        return SignatureEnvelope("KMS_ASYMMETRIC_SIGN", self.key_id, str(signature))


class Ed25519EvidenceSigner:
    algorithm = "Ed25519"

    def __init__(self, private_key: Any, *, key_id: str, actor_id: str) -> None:
        self.private_key, self.key_id, self.actor_id = private_key, key_id, actor_id

    @classmethod
    def from_private_bytes(cls, value: bytes, *, key_id: str, actor_id: str) -> "Ed25519EvidenceSigner":
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        except ImportError as error:  # pragma: no cover - optional production dependency
            raise NotConfigured("cryptography is required for Ed25519 signing") from error
        return cls(Ed25519PrivateKey.from_private_bytes(value), key_id=key_id, actor_id=actor_id)

    def sign(self, payload: bytes) -> SignatureEnvelope:
        return SignatureEnvelope(self.algorithm, self.key_id, base64.b64encode(self.private_key.sign(payload)).decode("ascii"))


@dataclass(frozen=True, slots=True)
class TrustKey:
    key_id: str
    actor_id: str
    role: str
    algorithm: str
    verifier: Callable[[bytes, bytes], bool]
    revoked: bool = False

    def __post_init__(self) -> None:
        if self.role not in {"producer", "independent_verifier", "security_reviewer", "release_authority"}:
            raise ContractViolation("evidence trust-key role is invalid")


class EvidenceTrustStore:
    def __init__(self, keys: Iterable[TrustKey] = ()) -> None:
        self._keys = {key.key_id: key for key in keys}

    def add(self, key: TrustKey) -> None:
        existing = self._keys.get(key.key_id)
        if existing is not None and (existing.actor_id != key.actor_id or existing.algorithm != key.algorithm):
            raise ContractViolation("trust key identity cannot be replaced")
        self._keys[key.key_id] = key

    def revoke(self, key_id: str) -> None:
        key = self._keys.get(key_id)
        if key is None:
            raise KeyError(key_id)
        self._keys[key_id] = TrustKey(key.key_id, key.actor_id, key.role, key.algorithm, key.verifier, True)

    def verify(self, payload: bytes, envelope: SignatureEnvelope, *, required_role: str) -> str:
        key = self._keys.get(envelope.key_id)
        if key is None or key.revoked or key.algorithm != envelope.algorithm or key.role != required_role:
            raise ContractViolation("signature key is absent, revoked, mismatched or unauthorized")
        try:
            signature = base64.b64decode(envelope.signature, validate=True)
        except ValueError as error:
            raise ContractViolation("signature is not valid base64") from error
        if not key.verifier(payload, signature):
            raise ContractViolation("evidence signature verification failed")
        return key.actor_id


def ed25519_trust_key(public_key_bytes: bytes, *, key_id: str, actor_id: str, role: str) -> TrustKey:
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as error:  # pragma: no cover - optional production dependency
        raise NotConfigured("cryptography is required for Ed25519 verification") from error
    key = Ed25519PublicKey.from_public_bytes(public_key_bytes)

    def verify(payload: bytes, signature: bytes) -> bool:
        try:
            key.verify(signature, payload)
        except Exception:
            return False
        return True

    return TrustKey(key_id, actor_id, role, "Ed25519", verify)


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    evidence_id: str
    role: str
    status: str
    artifact: ArtifactRef
    source: str
    executor_id: str
    environment_digest: str
    replay_command: tuple[str, ...]
    collected_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if self.status not in {"PASS", "FAIL", "BLOCKED", "NOT_RUN", "INCONCLUSIVE"}:
            raise ContractViolation("evidence item status is invalid")
        if not self.evidence_id or not self.role or not self.source or not self.executor_id or not self.environment_digest.startswith("sha256:"):
            raise ContractViolation("evidence item provenance is incomplete")
        if not self.replay_command:
            raise ContractViolation("evidence item requires a replay command")

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "artifact": self.artifact.as_dict(), "replay_command": list(self.replay_command)}


@dataclass(frozen=True, slots=True)
class EvidencePack:
    pack_id: str
    identity: Identity
    manifest_digest: str
    target_digest: str
    items: tuple[EvidenceItem, ...]
    producer_id: str
    body_digest: str
    signature: SignatureEnvelope
    created_at: str
    state: str = "engineering"

    def body(self) -> dict[str, Any]:
        return {
            "pack_id": self.pack_id, "identity": _identity(self.identity), "manifest_digest": self.manifest_digest,
            "target_digest": self.target_digest, "items": [item.as_dict() for item in self.items],
            "producer_id": self.producer_id, "created_at": self.created_at,
        }

    def as_dict(self) -> dict[str, Any]:
        return {**self.body(), "body_digest": self.body_digest, "signature": asdict(self.signature), "state": self.state, "certification": "NOT_CERTIFIED"}


@dataclass(frozen=True, slots=True)
class IndependentVerification:
    verification_id: str
    pack_id: str
    pack_digest: str
    verifier_id: str
    decision: str
    findings: tuple[str, ...]
    signature: SignatureEnvelope
    verified_at: str

    def __post_init__(self) -> None:
        if self.decision not in {"VERIFIED", "REJECTED", "INCONCLUSIVE"}:
            raise ContractViolation("independent verification decision is invalid")

    def body(self) -> dict[str, Any]:
        return {"verification_id": self.verification_id, "pack_id": self.pack_id, "pack_digest": self.pack_digest, "verifier_id": self.verifier_id, "decision": self.decision, "findings": list(self.findings), "verified_at": self.verified_at}


class EvidencePackBuilder:
    def __init__(self, signer: EvidenceSigner) -> None:
        self.signer = signer

    def build(self, identity: Identity, *, manifest_digest: str, target_digest: str, items: Iterable[EvidenceItem]) -> EvidencePack:
        values = tuple(items)
        if not manifest_digest.startswith("sha256:") or not target_digest.startswith("sha256:") or not values:
            raise ContractViolation("evidence pack requires digest-bound manifest, target and items")
        if any(item.artifact.tenant_id != identity.tenant_id for item in values):
            raise TenantIsolationError("evidence item belongs to another tenant")
        created_at = utc_now()
        seed = {"identity": identity.scope(), "manifest_digest": manifest_digest, "target_digest": target_digest, "items": [item.as_dict() for item in values], "producer_id": self.signer.actor_id, "created_at": created_at}
        pack_id = "evidence_" + digest_of(seed).split(":", 1)[1]
        body = {"pack_id": pack_id, "identity": _identity(identity), "manifest_digest": manifest_digest, "target_digest": target_digest, "items": [item.as_dict() for item in values], "producer_id": self.signer.actor_id, "created_at": created_at}
        encoded = canonical_json(body).encode("utf-8")
        return EvidencePack(pack_id, identity, manifest_digest, target_digest, values, self.signer.actor_id, digest_of(body), self.signer.sign(encoded), created_at)


class IndependentEvidenceVerifier:
    def __init__(self, trust_store: EvidenceTrustStore, signer: EvidenceSigner, artifact_reader: Callable[[str, ArtifactRef], bytes]) -> None:
        self.trust_store, self.signer, self.artifact_reader = trust_store, signer, artifact_reader

    def verify(self, pack: EvidencePack, *, expected_manifest: str, expected_target: str) -> IndependentVerification:
        body = pack.body()
        encoded = canonical_json(body).encode("utf-8")
        producer_id = self.trust_store.verify(encoded, pack.signature, required_role="producer")
        findings: list[str] = []
        if producer_id != pack.producer_id:
            findings.append("PRODUCER_IDENTITY_MISMATCH")
        if self.signer.actor_id == pack.producer_id:
            findings.append("SELF_VERIFICATION_FORBIDDEN")
        if pack.body_digest != digest_of(body):
            findings.append("PACK_DIGEST_MISMATCH")
        if pack.manifest_digest != expected_manifest:
            findings.append("MANIFEST_DIGEST_MISMATCH")
        if pack.target_digest != expected_target:
            findings.append("TARGET_DIGEST_MISMATCH")
        for item in pack.items:
            try:
                value = self.artifact_reader(pack.identity.tenant_id, item.artifact)
            except Exception:
                findings.append("ARTIFACT_UNAVAILABLE:" + item.evidence_id)
                continue
            if digest_of_bytes(value) != item.artifact.digest or len(value) != item.artifact.size_bytes:
                findings.append("ARTIFACT_DIGEST_MISMATCH:" + item.evidence_id)
            if item.status != "PASS":
                findings.append("NON_PASS_EVIDENCE:" + item.evidence_id)
        decision = "VERIFIED" if not findings else "REJECTED"
        verified_at = utc_now()
        seed = {"pack_id": pack.pack_id, "pack_digest": pack.body_digest, "verifier_id": self.signer.actor_id, "decision": decision, "findings": findings, "verified_at": verified_at}
        verification_id = "verification_" + digest_of(seed).split(":", 1)[1]
        body = {"verification_id": verification_id, **seed}
        signature = self.signer.sign(canonical_json(body).encode("utf-8"))
        # Validate the verifier key now, not only when a downstream gate reads it.
        self.trust_store.verify(canonical_json(body).encode("utf-8"), signature, required_role="independent_verifier")
        return IndependentVerification(verification_id, pack.pack_id, pack.body_digest, self.signer.actor_id, decision, tuple(findings), signature, verified_at)


class EvidenceRepository:
    """Append-only SQLite evidence index; artifact bytes remain in CAS/S3."""

    def __init__(self, database: str = ":memory:") -> None:
        self._connection = sqlite3.connect(database, check_same_thread=False, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.executescript(
            """CREATE TABLE IF NOT EXISTS evidence_packs(pack_id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,task_id TEXT NOT NULL,run_id TEXT NOT NULL,node_id TEXT NOT NULL,body_digest TEXT NOT NULL,body_json TEXT NOT NULL,signature_json TEXT NOT NULL,created_at TEXT NOT NULL);
               CREATE INDEX IF NOT EXISTS evidence_packs_scope_idx ON evidence_packs(tenant_id,project_id,task_id,run_id,node_id);
               CREATE TABLE IF NOT EXISTS evidence_verifications(verification_id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,task_id TEXT NOT NULL,run_id TEXT NOT NULL,node_id TEXT NOT NULL,pack_id TEXT NOT NULL,pack_digest TEXT NOT NULL,body_json TEXT NOT NULL,signature_json TEXT NOT NULL,verified_at TEXT NOT NULL);
               CREATE INDEX IF NOT EXISTS evidence_verifications_scope_idx ON evidence_verifications(tenant_id,project_id,task_id,run_id,node_id,pack_id);"""
        )

    def close(self) -> None:
        self._connection.close()

    def put_pack(self, pack: EvidencePack) -> None:
        existing = self._connection.execute("SELECT tenant_id,project_id,task_id,run_id,node_id,body_digest FROM evidence_packs WHERE pack_id=?", (pack.pack_id,)).fetchone()
        if existing is not None:
            if tuple(existing[name] for name in ("tenant_id", "project_id", "task_id", "run_id", "node_id")) != pack.identity.scope():
                raise TenantIsolationError("evidence pack identity collision crosses project/task scope")
            if existing["body_digest"] != pack.body_digest:
                raise ContractViolation("evidence pack identity collision")
        self._connection.execute(
            "INSERT OR IGNORE INTO evidence_packs(pack_id,tenant_id,project_id,task_id,run_id,node_id,body_digest,body_json,signature_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (pack.pack_id, *pack.identity.scope(), pack.body_digest, canonical_json(pack.body()), canonical_json(asdict(pack.signature)), pack.created_at),
        )

    def put_verification(self, identity: Identity, verification: IndependentVerification) -> None:
        row = self._connection.execute("SELECT tenant_id,project_id,task_id,run_id,node_id,body_digest FROM evidence_packs WHERE pack_id=?", (verification.pack_id,)).fetchone()
        if row is None or tuple(row[name] for name in ("tenant_id", "project_id", "task_id", "run_id", "node_id")) != identity.scope() or row["body_digest"] != verification.pack_digest:
            raise TenantIsolationError("verification does not bind an evidence pack in project/task scope")
        existing = self._connection.execute("SELECT tenant_id,project_id,task_id,run_id,node_id,pack_digest,body_json,signature_json FROM evidence_verifications WHERE verification_id=?", (verification.verification_id,)).fetchone()
        body_json = canonical_json(verification.body())
        signature_json = canonical_json(asdict(verification.signature))
        if existing is not None:
            if tuple(existing[name] for name in ("tenant_id", "project_id", "task_id", "run_id", "node_id")) != identity.scope():
                raise TenantIsolationError("verification identity collision crosses project/task scope")
            if (existing["pack_digest"], existing["body_json"], existing["signature_json"]) != (verification.pack_digest, body_json, signature_json):
                raise ContractViolation("verification identity collision")
        self._connection.execute(
            "INSERT OR IGNORE INTO evidence_verifications(verification_id,tenant_id,project_id,task_id,run_id,node_id,pack_id,pack_digest,body_json,signature_json,verified_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (verification.verification_id, *identity.scope(), verification.pack_id, verification.pack_digest, body_json, signature_json, verification.verified_at),
        )


def digest_of_bytes(value: bytes) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(value).hexdigest()


def _identity(identity: Identity) -> dict[str, Any]:
    return {"tenant_id": identity.tenant_id, "project_id": identity.project_id, "task_id": identity.task_id, "run_id": identity.run_id, "node_id": identity.node_id, "agent_id": identity.agent_id}
