"""Digest-bound independent verifier receipts and a fail-closed trust store."""

from __future__ import annotations

import base64
import sqlite3
import threading
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .canonical import canonical_bytes, digest, require_nonempty, require_uuid, utc_now
from .models import ConflictError, PolicyDeniedError
from .production import ExternalEvidenceState


def _time(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(
            require_nonempty(value, field_name, 64).replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class EvidenceStatement:
    statement_id: str
    scope: str
    producer_id: str
    producer_trust_domain: str
    subject_digest: str
    environment_digest: str
    raw_evidence_digests: tuple[str, ...]
    authorization_id: str
    executor_id: str
    started_at: str
    completed_at: str
    result: str
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_uuid(self.statement_id, "statement_id")
        for name in (
            "scope",
            "producer_id",
            "producer_trust_domain",
            "subject_digest",
            "environment_digest",
            "authorization_id",
            "executor_id",
        ):
            require_nonempty(getattr(self, name), name, 512)
        if not self.raw_evidence_digests:
            raise ValueError("raw_evidence_digests cannot be empty")
        if self.result not in {"PASS", "FAIL", "BLOCKED", "UNKNOWN", "NOT_RUN"}:
            raise ValueError("invalid evidence result")
        if _time(self.completed_at, "completed_at") < _time(
            self.started_at, "started_at"
        ):
            raise ValueError("evidence completion precedes start")

    def to_dict(self) -> dict[str, Any]:
        return {
            "statement_id": self.statement_id,
            "scope": self.scope,
            "producer_id": self.producer_id,
            "producer_trust_domain": self.producer_trust_domain,
            "subject_digest": self.subject_digest,
            "environment_digest": self.environment_digest,
            "raw_evidence_digests": list(self.raw_evidence_digests),
            "authorization_id": self.authorization_id,
            "executor_id": self.executor_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class SignedVerification:
    receipt_id: str
    verifier_id: str
    verifier_trust_domain: str
    key_id: str
    statement: EvidenceStatement
    verdict: str
    issued_at: str
    expires_at: str
    signature: str
    signature_algorithm: str = "Ed25519"

    def __post_init__(self) -> None:
        require_uuid(self.receipt_id, "receipt_id")
        for name in ("verifier_id", "verifier_trust_domain", "key_id", "signature"):
            require_nonempty(getattr(self, name), name, 1024)
        if self.verdict not in {"VERIFIED", "REJECTED", "INCONCLUSIVE"}:
            raise ValueError("invalid independent verifier verdict")
        if self.signature_algorithm != "Ed25519":
            raise ValueError("unsupported signature algorithm")
        if _time(self.expires_at, "expires_at") <= _time(self.issued_at, "issued_at"):
            raise ValueError("verification receipt expiry must follow issuance")

    def unsigned_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "verifier_id": self.verifier_id,
            "verifier_trust_domain": self.verifier_trust_domain,
            "key_id": self.key_id,
            "statement": self.statement.to_dict(),
            "verdict": self.verdict,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "signature_algorithm": self.signature_algorithm,
        }

    def to_dict(self) -> dict[str, Any]:
        return self.unsigned_dict() | {
            "signature": self.signature,
            "receipt_digest": digest(self.unsigned_dict()),
        }


class SignatureBackend(Protocol):
    def sign(self, payload: bytes) -> bytes: ...
    def verify(self, public_key: bytes, signature: bytes, payload: bytes) -> None: ...


class Ed25519Backend:
    def sign_with_private_key(self, private_key: bytes, payload: bytes) -> bytes:
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PrivateKey,
            )
        except ImportError as exc:  # pragma: no cover - optional production extra
            raise RuntimeError(
                "cryptography is required; install elmos-pi-harness[identity]"
            ) from exc
        return Ed25519PrivateKey.from_private_bytes(private_key).sign(payload)

    def verify(self, public_key: bytes, signature: bytes, payload: bytes) -> None:
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PublicKey,
            )
        except ImportError as exc:  # pragma: no cover - optional production extra
            raise RuntimeError(
                "cryptography is required; install elmos-pi-harness[identity]"
            ) from exc
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, payload)


@dataclass(frozen=True)
class TrustedVerifier:
    verifier_id: str
    trust_domain: str
    key_id: str
    public_key: bytes
    not_before: str
    not_after: str
    revoked: bool = False
    allowed_scopes: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        for name in ("verifier_id", "trust_domain", "key_id"):
            require_nonempty(getattr(self, name), name, 512)
        if len(self.public_key) != 32:
            raise ValueError("Ed25519 public key must contain 32 bytes")
        if _time(self.not_after, "not_after") <= _time(self.not_before, "not_before"):
            raise ValueError("verifier key validity interval is invalid")


class IndependentVerifierSigner:
    def __init__(
        self,
        *,
        verifier_id: str,
        trust_domain: str,
        key_id: str,
        private_key: bytes,
        backend: Ed25519Backend | None = None,
    ) -> None:
        self.verifier_id = require_nonempty(verifier_id, "verifier_id", 512)
        self.trust_domain = require_nonempty(trust_domain, "trust_domain", 512)
        self.key_id = require_nonempty(key_id, "key_id", 512)
        if len(private_key) != 32:
            raise ValueError("Ed25519 private key seed must contain 32 bytes")
        self.private_key = private_key
        self.backend = backend or Ed25519Backend()

    def sign(
        self,
        statement: EvidenceStatement,
        *,
        receipt_id: str,
        verdict: str,
        issued_at: str,
        expires_at: str,
    ) -> SignedVerification:
        if statement.producer_trust_domain == self.trust_domain:
            raise PolicyDeniedError(
                "producer and independent verifier must use different trust domains"
            )
        if verdict == "VERIFIED" and statement.result != "PASS":
            raise PolicyDeniedError("only a passing executed statement can be verified")
        unsigned = SignedVerification(
            receipt_id=receipt_id,
            verifier_id=self.verifier_id,
            verifier_trust_domain=self.trust_domain,
            key_id=self.key_id,
            statement=statement,
            verdict=verdict,
            issued_at=issued_at,
            expires_at=expires_at,
            signature=base64.b64encode(b"placeholder").decode(),
        )
        signature = self.backend.sign_with_private_key(
            self.private_key, canonical_bytes(unsigned.unsigned_dict())
        )
        return SignedVerification(
            **(
                unsigned.__dict__
                | {"signature": base64.b64encode(signature).decode("ascii")}
            )
        )


class VerifierTrustStore:
    def __init__(
        self,
        verifiers: Iterable[TrustedVerifier],
        *,
        backend: Ed25519Backend | None = None,
    ) -> None:
        values = list(verifiers)
        self._keys = {(item.verifier_id, item.key_id): item for item in values}
        if len(self._keys) != len(values):
            raise ValueError("duplicate verifier/key identity")
        self.backend = backend or Ed25519Backend()

    def verify(
        self,
        receipt: SignedVerification,
        *,
        expected_subject_digest: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current_time = now or datetime.now(timezone.utc)
        trusted = self._keys.get((receipt.verifier_id, receipt.key_id))
        if trusted is None or trusted.revoked:
            raise PolicyDeniedError("verifier key is unknown or revoked")
        if trusted.trust_domain != receipt.verifier_trust_domain:
            raise PolicyDeniedError("verifier trust domain mismatch")
        if receipt.statement.producer_trust_domain == trusted.trust_domain:
            raise PolicyDeniedError("verification is not independent from the producer")
        if receipt.verdict == "VERIFIED" and receipt.statement.result != "PASS":
            raise PolicyDeniedError(
                "verified receipt does not bind a passing statement"
            )
        if (
            trusted.allowed_scopes
            and receipt.statement.scope not in trusted.allowed_scopes
        ):
            raise PolicyDeniedError("verifier is not trusted for this scope")
        if not (
            _time(trusted.not_before, "not_before")
            <= current_time
            < _time(trusted.not_after, "not_after")
        ):
            raise PolicyDeniedError("verifier key is outside its validity interval")
        if not (
            _time(receipt.issued_at, "issued_at")
            <= current_time
            < _time(receipt.expires_at, "expires_at")
        ):
            raise PolicyDeniedError("verification receipt is not currently valid")
        if receipt.statement.subject_digest != expected_subject_digest:
            raise PolicyDeniedError("verification subject digest mismatch")
        try:
            signature = base64.b64decode(receipt.signature, validate=True)
            self.backend.verify(
                trusted.public_key, signature, canonical_bytes(receipt.unsigned_dict())
            )
        except Exception as exc:
            raise PolicyDeniedError(
                "independent verification signature is invalid"
            ) from exc
        return {
            "receipt_id": receipt.receipt_id,
            "receipt_digest": digest(receipt.unsigned_dict()),
            "scope": receipt.statement.scope,
            "verdict": receipt.verdict,
            "verifier_id": receipt.verifier_id,
            "independent": True,
        }


RECEIPT_SCHEMA = """
CREATE TABLE IF NOT EXISTS independent_verification_receipt (
  receipt_id TEXT PRIMARY KEY,
  receipt_digest TEXT NOT NULL UNIQUE,
  scope TEXT NOT NULL,
  subject_digest TEXT NOT NULL,
  verifier_id TEXT NOT NULL,
  verdict TEXT NOT NULL,
  receipt_json TEXT NOT NULL,
  accepted_at TEXT NOT NULL
);
"""


class VerificationReceiptRegistry:
    def __init__(self, path: str = ":memory:") -> None:
        if path != ":memory:" and not Path(path).is_absolute():
            raise ValueError("verification registry path must be absolute")
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript(RECEIPT_SCHEMA)
        self._lock = threading.RLock()

    def accept(
        self, receipt: SignedVerification, verified: Mapping[str, Any]
    ) -> dict[str, Any]:
        if (
            verified.get("receipt_id") != receipt.receipt_id
            or verified.get("independent") is not True
        ):
            raise PolicyDeniedError("receipt has not passed independent verification")
        value = receipt.to_dict()
        receipt_digest = digest(receipt.unsigned_dict())
        with self._lock, self._connection:
            existing = self._connection.execute(
                "SELECT * FROM independent_verification_receipt WHERE receipt_id=?",
                (receipt.receipt_id,),
            ).fetchone()
            if existing:
                if existing["receipt_digest"] != receipt_digest:
                    raise ConflictError("receipt id was reused with different content")
                return dict(existing) | {"replayed": True}
            self._connection.execute(
                "INSERT INTO independent_verification_receipt(receipt_id,receipt_digest,scope,subject_digest,verifier_id,verdict,receipt_json,accepted_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    receipt.receipt_id,
                    receipt_digest,
                    receipt.statement.scope,
                    receipt.statement.subject_digest,
                    receipt.verifier_id,
                    receipt.verdict,
                    canonical_bytes(value).decode(),
                    utc_now(),
                ),
            )
            return {
                "receipt_id": receipt.receipt_id,
                "receipt_digest": receipt_digest,
                "scope": receipt.statement.scope,
                "subject_digest": receipt.statement.subject_digest,
                "verifier_id": receipt.verifier_id,
                "verdict": receipt.verdict,
                "replayed": False,
            }

    def close(self) -> None:
        self._connection.close()


def external_gate_decision(
    receipts: Iterable[Mapping[str, Any]], required_scopes: set[str]
) -> dict[str, Any]:
    values = list(receipts)
    by_scope = {
        str(item.get("scope")): item
        for item in values
        if item.get("verdict") == "VERIFIED"
    }
    missing = sorted(required_scopes - set(by_scope))
    rejected = sorted(
        str(item.get("scope"))
        for item in values
        if item.get("verdict") in {"REJECTED", "INCONCLUSIVE"}
    )
    if rejected:
        return {
            "status": "FAILED",
            "certified": False,
            "blockers": ["verifier_rejected:" + value for value in rejected],
        }
    if missing:
        return {
            "status": ExternalEvidenceState.NOT_RUN.value,
            "certified": False,
            "blockers": ["missing_independent_scope:" + value for value in missing],
        }
    return {
        "status": "READY_FOR_HUMAN_DECISION",
        "certified": False,
        "blockers": ["customer_acceptance_and_release_authority_required"],
    }
