"""Byte-bound immutable evidence services.

The service calculates artifact digests from the exact supplied bytes, stores
the bytes and envelope atomically, and re-verifies both on every certification
read.  Claimed digests are never accepted without reading their content.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Protocol

from .canonical import canonical_json_bytes, digest_bytes, verify_digest
from .contracts import ArtifactRef, EvidenceProducer, EvidenceRecord, SecurityContext, utc_now
from .errors import IntegrityError, ValidationError


class EvidenceBackend(Protocol):
    def append_evidence(
        self,
        context: SecurityContext,
        record: EvidenceRecord,
        content: bytes,
        *,
        idempotency_key: str | None = None,
    ) -> EvidenceRecord: ...

    def get_evidence(self, context: SecurityContext, evidence_id: str) -> tuple[EvidenceRecord, bytes]: ...

    def evidence_revoked(self, context: SecurityContext, evidence_id: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class EvidenceBundle:
    tenant_id: str
    project_id: str
    evidence_ids: tuple[str, ...]
    root_sha256: str
    sealed_at: datetime


class EvidenceService:
    """High-level evidence API over an append-only durable backend."""

    def __init__(self, backend: EvidenceBackend) -> None:
        self._backend = backend

    def record_bytes(
        self,
        context: SecurityContext,
        *,
        subject_revision: str,
        kind: str,
        evidence_class: str,
        scope: str,
        content: bytes,
        media_type: str,
        producer: EvidenceProducer,
        evidence_id: str | None = None,
        artifact_id: str | None = None,
        created_at: datetime | None = None,
        expires_at: datetime | None = None,
        lineage: Iterable[str] = (),
        assumptions: Iterable[str] = (),
        idempotency_key: str | None = None,
    ) -> EvidenceRecord:
        if not isinstance(content, bytes):
            raise ValidationError("evidence content must be immutable bytes", code="CONTENT_NOT_BYTES")
        evidence_id = evidence_id or f"ev-{uuid.uuid4()}"
        artifact_id = artifact_id or f"artifact-{uuid.uuid4()}"
        artifact = ArtifactRef(
            artifact_id=artifact_id,
            sha256=digest_bytes(content, domain="evidence-content"),
            media_type=media_type,
            byte_length=len(content),
            domain="evidence-content",
        )
        record = EvidenceRecord(
            evidence_id=evidence_id,
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            actor_id=context.actor_id,
            subject_revision=subject_revision,
            kind=kind,
            evidence_class=evidence_class,
            scope=scope,
            content=artifact,
            producer=producer,
            created_at=created_at or utc_now(),
            expires_at=expires_at,
            lineage=tuple(lineage),
            assumptions=tuple(assumptions),
        )
        return self._backend.append_evidence(context, record, content, idempotency_key=idempotency_key)

    def verify(self, context: SecurityContext, evidence_id: str, *, now: datetime | None = None) -> EvidenceRecord:
        return self.read_verified(context, evidence_id, now=now)[0]

    def read_verified(
        self,
        context: SecurityContext,
        evidence_id: str,
        *,
        now: datetime | None = None,
    ) -> tuple[EvidenceRecord, bytes]:
        """Return a record and its exact bytes after every integrity check."""

        record, content = self._backend.get_evidence(context, evidence_id)
        self.verify_record_bytes(record, content)
        current = now or utc_now()
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValidationError("verification time must be timezone-aware")
        if self._backend.evidence_revoked(context, evidence_id):
            raise IntegrityError("evidence is revoked", code="EVIDENCE_REVOKED", details={"evidence_id": evidence_id})
        if record.expires_at is not None and current >= record.expires_at:
            raise IntegrityError("evidence is expired", code="EVIDENCE_EXPIRED", details={"evidence_id": evidence_id})
        return record, content

    @staticmethod
    def verify_record_bytes(record: EvidenceRecord, content: bytes) -> None:
        if len(content) != record.content.byte_length:
            raise IntegrityError(
                "evidence byte length mismatch",
                code="EVIDENCE_LENGTH_MISMATCH",
                details={"evidence_id": record.evidence_id},
            )
        verify_digest(content, record.content.sha256, domain=record.content.domain)

    def fresh_records(
        self,
        context: SecurityContext,
        evidence_ids: Iterable[str],
        *,
        now: datetime | None = None,
    ) -> tuple[EvidenceRecord, ...]:
        ids = tuple(evidence_ids)
        if not ids or len(ids) != len(set(ids)):
            raise ValidationError("evidence bundle must contain unique evidence ids")
        return tuple(self.verify(context, evidence_id, now=now) for evidence_id in ids)

    def seal(
        self,
        context: SecurityContext,
        evidence_ids: Iterable[str],
        *,
        now: datetime | None = None,
    ) -> EvidenceBundle:
        sealed_at = now or utc_now()
        records = self.fresh_records(context, evidence_ids, now=sealed_at)
        leaves = [
            bytes.fromhex(
                digest_bytes(canonical_json_bytes(record), domain="evidence-record").removeprefix("sha256:")
            )
            for record in sorted(records, key=lambda item: item.evidence_id)
        ]
        if not leaves:
            raise ValidationError("cannot seal an empty evidence bundle")
        while len(leaves) > 1:
            if len(leaves) % 2:
                leaves.append(leaves[-1])
            leaves = [
                bytes.fromhex(digest_bytes(leaves[index] + leaves[index + 1], domain="evidence-merkle-node").removeprefix("sha256:"))
                for index in range(0, len(leaves), 2)
            ]
        root = digest_bytes(leaves[0], domain="evidence-merkle-root")
        return EvidenceBundle(
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            evidence_ids=tuple(sorted(record.evidence_id for record in records)),
            root_sha256=root,
            sealed_at=sealed_at,
        )
