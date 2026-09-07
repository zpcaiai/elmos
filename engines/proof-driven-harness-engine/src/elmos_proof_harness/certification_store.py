"""PostgreSQL 17 repository for durable completion certification.

This bridge intentionally uses a separate certifier DSN.  The ordinary HTTP
application role has no write privilege on certification relations, while the
certifier role can append assessments, externally verified receipts,
decisions, revocations, and their audit events.  Every transaction still uses
the authenticated tenant/project/actor session context and forced RLS.

The database stores the exact canonical local payload bytes and verifies their
domain-separated SHA-256.  Deferred constraints validate the complete child
gate/evidence set at commit.  Python re-validates the same payload and typed
certificate on every read, so a database row is never trusted as a status
boolean alone.
"""

from __future__ import annotations

import hmac
import json
import os
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, Mapping

from .canonical import canonical_json, canonical_json_bytes, digest_object, require_sha256_digest, verify_digest
from .certification import CertificationService, ExternalSignatureReceipt
from .contracts import CertificationStatus, CompletionCertificate, GateDecision, GateResult, SecurityContext, utc_now
from .errors import CertificationError, ConflictError, IntegrityError, NotFoundError, StoreError, ValidationError
from .postgres import PostgresStore
from .storage import (
    MAX_INLINE_CERTIFICATION_BYTES,
    POSTGRES_MIGRATION_SOURCE_DIGEST,
    POSTGRES_SCHEMA_VERSION,
    StorageReadiness,
    StorageStatus,
)


_CERTIFICATION_TABLES = (
    "certification_assessments",
    "certification_gate_results",
    "certification_evidence_links",
    "certification_external_receipts",
    "certification_external_decisions",
    "certification_signature_revocations",
    "certification_events",
)
_CERTIFICATION_TRIGGER_NAMES = frozenset(
    {
        "runtime_certification_assessment_complete",
        "runtime_certification_external_decision_complete",
        "runtime_certification_assessments_immutable",
        "runtime_certification_gate_results_immutable",
        "runtime_certification_evidence_links_immutable",
        "runtime_certification_external_receipts_immutable",
        "runtime_certification_external_decisions_immutable",
        "runtime_certification_signature_revocations_immutable",
        "runtime_certification_events_immutable",
    }
)


def _as_json(value: object) -> str:
    return canonical_json(value)


def _decode_json(value: object) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return json.loads(bytes(value))
    return value


def _parse_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise IntegrityError("stored certification timestamp is naive")
        return value.astimezone(UTC)
    if not isinstance(value, str):
        raise IntegrityError("stored certification timestamp is invalid")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise IntegrityError("stored certification timestamp is naive")
    return parsed.astimezone(UTC)


def _gate_from_json(value: Mapping[str, object]) -> GateResult:
    return GateResult(
        gate=str(value["gate"]),
        decision=GateDecision(str(value["decision"])),
        evidence_ids=tuple(str(item) for item in value.get("evidence_ids", ())),
        reasons=tuple(str(item) for item in value.get("reasons", ())),
    )


def _certificate_from_json(value: Mapping[str, object]) -> CompletionCertificate:
    gate_values = value.get("gate_results")
    if not isinstance(gate_values, list):
        raise IntegrityError("stored certificate gate results are invalid")
    return CompletionCertificate(
        certificate_id=str(value["certificate_id"]),
        tenant_id=str(value["tenant_id"]),
        project_id=str(value["project_id"]),
        goal_id=str(value["goal_id"]),
        run_id=None if value.get("run_id") is None else str(value["run_id"]),
        revision_set_id=str(value["revision_set_id"]),
        revision_set_digest=str(value["revision_set_digest"]),
        revision_set_revisions={str(key): str(item) for key, item in dict(value["revision_set_revisions"]).items()},
        proof_graph_digest=str(value["proof_graph_digest"]),
        certified_envelope=dict(value["certified_envelope"]),
        gate_results=tuple(_gate_from_json(dict(item)) for item in gate_values),
        status_counts={str(key): int(item) for key, item in dict(value["status_counts"]).items()},
        evidence_ids=tuple(str(item) for item in value["evidence_ids"]),
        evidence_root=str(value["evidence_root"]),
        signer_identity=None if value.get("signer_identity") is None else str(value["signer_identity"]),
        signer_key_id=None if value.get("signer_key_id") is None else str(value["signer_key_id"]),
        signer_independent=bool(value["signer_independent"]),
        issued_at=_parse_datetime(value["issued_at"]),
        status=CertificationStatus(str(value["status"])),
        payload_digest=str(value["payload_digest"]),
        production_assessment=bool(value.get("production_assessment", False)),
        signature_receipt_id=(
            None if value.get("signature_receipt_id") is None else str(value["signature_receipt_id"])
        ),
        signature_receipt_sha256=(
            None
            if value.get("signature_receipt_sha256") is None
            else str(value["signature_receipt_sha256"])
        ),
        unresolved_risks=tuple(str(item) for item in value.get("unresolved_risks", ())),
    )


class PostgresCertificationRepository:
    """Append-only certification repository using an independent PG role."""

    def __init__(
        self,
        dsn: str,
        *,
        health_context: SecurityContext | None = None,
    ) -> None:
        self._store = PostgresStore(dsn, health_context=health_context)
        self._health_context = health_context or SecurityContext(
            tenant_id="__proof_harness_certifier_health__",
            project_id="__proof_harness_certifier_health__",
            actor_id="__proof_harness_certifier__",
        )

    @classmethod
    def from_environment(
        cls,
        *,
        variable: str = "ELMOS_CERTIFIER_POSTGRES_DSN",
        environment: Mapping[str, str] | None = None,
    ) -> "PostgresCertificationRepository":
        values = os.environ if environment is None else environment
        dsn = values.get(variable, "")
        if not dsn.strip():
            raise StoreError(
                f"{variable} is required for durable external certification",
                code=StorageStatus.NOT_CONFIGURED.value,
            )
        return cls(dsn)

    def close(self) -> None:
        self._store.close()

    def readiness(self) -> StorageReadiness:
        """Fail closed on role, migration ledger, RLS, trigger, and grants drift."""

        try:
            with self._store.transaction(self._health_context) as cursor:
                role = cursor.execute(
                    "SELECT current_user AS role_name,r.rolsuper,r.rolbypassrls,"
                    "current_setting('server_version_num') AS server_version_num,"
                    "current_setting('server_version') AS server_version "
                    "FROM pg_roles r WHERE r.rolname=current_user"
                ).fetchone()
                migration = cursor.execute(
                    "SELECT m.version,l.content_sha256 FROM schema_migrations m "
                    "LEFT JOIN migration_digest_ledger l USING (version,migration_name) "
                    "WHERE m.version=? AND m.migration_name=?",
                    (POSTGRES_SCHEMA_VERSION, "V001__proof_harness_core.sql"),
                ).fetchone()
                rls = cursor.execute(
                    "SELECT COUNT(*) AS count FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname='proof_harness_runtime' AND c.relname = ANY(?) "
                    "AND c.relrowsecurity AND c.relforcerowsecurity",
                    (list(_CERTIFICATION_TABLES),),
                ).fetchone()
                triggers = cursor.execute(
                    "SELECT t.tgname FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
                    "JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname='proof_harness_runtime' AND NOT t.tgisinternal "
                    "AND t.tgname = ANY(?)",
                    (list(_CERTIFICATION_TRIGGER_NAMES),),
                ).fetchall()
                ownership = cursor.execute(
                    "SELECT COUNT(*) AS count FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname='proof_harness_runtime' AND c.relname = ANY(?) "
                    "AND pg_get_userbyid(c.relowner)=current_user",
                    (list(_CERTIFICATION_TABLES),),
                ).fetchone()
                privileges = cursor.execute(
                    "SELECT "
                    "bool_and(has_table_privilege(current_user,'proof_harness_runtime.'||name,'SELECT')) AS can_select,"
                    "bool_and(has_table_privilege(current_user,'proof_harness_runtime.'||name,'INSERT')) AS can_insert,"
                    "bool_or(has_table_privilege(current_user,'proof_harness_runtime.'||name,'UPDATE,DELETE,TRUNCATE')) AS can_mutate "
                    "FROM unnest(?::text[]) AS name",
                    (list(_CERTIFICATION_TABLES),),
                ).fetchone()
                runtime_privileges = cursor.execute(
                    "SELECT "
                    "bool_and(has_table_privilege(current_user,'proof_harness_runtime.'||name,'SELECT')) AS can_select,"
                    "bool_or(has_table_privilege(current_user,'proof_harness_runtime.'||name,'INSERT,UPDATE,DELETE,TRUNCATE')) AS can_write "
                    "FROM unnest(ARRAY['runs','evidence','evidence_revocations']::text[]) AS name"
                ).fetchone()
        except Exception as exc:
            code = getattr(exc, "code", "CERTIFIER_READINESS_FAILED")
            return StorageReadiness(
                status=StorageStatus.NOT_READY,
                reason=f"certifier PostgreSQL readiness failed ({code})",
                backend="postgresql-certifier",
            )
        if role is None or bool(role["rolsuper"]) or bool(role["rolbypassrls"]):
            reason = "certifier role must be NOSUPERUSER and NOBYPASSRLS"
        elif not (170000 <= int(role["server_version_num"]) < 180000):
            reason = "certifier repository requires PostgreSQL 17.x"
        elif migration is None or not hmac.compare_digest(
            str(migration["content_sha256"] or ""), POSTGRES_MIGRATION_SOURCE_DIGEST
        ):
            reason = "certifier migration digest ledger is missing or drifted"
        elif rls is None or int(rls["count"]) != len(_CERTIFICATION_TABLES):
            reason = "forced RLS is incomplete on certification relations"
        elif {str(row["tgname"]) for row in triggers} != _CERTIFICATION_TRIGGER_NAMES:
            reason = "certification constraints or immutable triggers are incomplete"
        elif ownership is None or int(ownership["count"]) != 0:
            reason = "certifier role must not own certification relations"
        elif (
            privileges is None
            or not bool(privileges["can_select"])
            or not bool(privileges["can_insert"])
            or bool(privileges["can_mutate"])
        ):
            reason = "certifier grants are not exact append-only privileges"
        elif (
            runtime_privileges is None
            or not bool(runtime_privileges["can_select"])
            or bool(runtime_privileges["can_write"])
        ):
            reason = "certifier runtime grants exceed read-only evidence/run access"
        else:
            return StorageReadiness(
                status=StorageStatus.READY,
                reason="durable certification schema, role, RLS, constraints and grants are ready",
                backend="postgresql-certifier",
                schema_version=POSTGRES_SCHEMA_VERSION,
                server_version=str(role["server_version"]),
            )
        return StorageReadiness(
            status=StorageStatus.NOT_READY,
            reason=reason,
            backend="postgresql-certifier",
            schema_version=POSTGRES_SCHEMA_VERSION,
            server_version=None if role is None else str(role["server_version"]),
        )

    @staticmethod
    def _validate_local_payload(certificate: CompletionCertificate, payload_bytes: bytes) -> None:
        if certificate.run_id is None:
            raise CertificationError("durable assessment lacks a run binding", code="CERTIFICATION_RUN_REQUIRED")
        if len(payload_bytes) > MAX_INLINE_CERTIFICATION_BYTES:
            raise ValidationError("certification payload exceeds the inline byte limit")
        expected = CertificationService._local_payload(
            tenant_id=certificate.tenant_id,
            project_id=certificate.project_id,
            goal_id=certificate.goal_id,
            run_id=certificate.run_id,
            revision_set_id=certificate.revision_set_id,
            revision_set_digest=certificate.revision_set_digest,
            revision_set_revisions=certificate.revision_set_revisions,
            proof_graph_digest=certificate.proof_graph_digest,
            certified_envelope=certificate.certified_envelope,
            gate_results=certificate.gate_results,
            status_counts=certificate.status_counts,
            evidence_ids=certificate.evidence_ids,
            evidence_root=certificate.evidence_root,
            status=certificate.status,
            independent_verifier_identity=certificate.signer_identity or "",
            issued_at=certificate.issued_at,
            unresolved_risks=certificate.unresolved_risks,
            production_assessment=certificate.production_assessment,
        )
        if canonical_json_bytes(expected) != payload_bytes:
            raise IntegrityError("local certification payload bytes do not match the typed assessment")
        verify_digest(payload_bytes, certificate.payload_digest, domain="local-certification-assessment")

    def save_local(
        self,
        context: SecurityContext,
        certificate: CompletionCertificate,
        *,
        payload_bytes: bytes,
        revision_set_bytes: bytes,
        proof_graph_bytes: bytes,
    ) -> CompletionCertificate:
        self._validate_local_payload(certificate, payload_bytes)
        if max(len(revision_set_bytes), len(proof_graph_bytes)) > MAX_INLINE_CERTIFICATION_BYTES:
            raise ValidationError("revision or proof-graph payload exceeds the inline byte limit")
        verify_digest(
            revision_set_bytes,
            certificate.revision_set_digest,
            domain="certification-revision-set",
        )
        verify_digest(
            proof_graph_bytes,
            certificate.proof_graph_digest,
            domain="proof-obligation-graph-state",
        )
        if (certificate.tenant_id, certificate.project_id) != (context.tenant_id, context.project_id):
            raise CertificationError("assessment scope does not match authenticated context")
        if certificate.status not in {
            CertificationStatus.BLOCKED,
            CertificationStatus.FAILED_ASSURANCE,
            CertificationStatus.READY_FOR_EXTERNAL_GATE,
        }:
            raise CertificationError("only a local assessment may be persisted")
        certificate_json = canonical_json(certificate)
        with self._store.transaction(context) as cursor:
            run = cursor.execute(
                "SELECT revision_set_id FROM runs WHERE tenant_id=? AND project_id=? AND run_id=?",
                (context.tenant_id, context.project_id, certificate.run_id),
            ).fetchone()
            if run is None:
                raise NotFoundError("certification run was not found")
            if str(run["revision_set_id"]) != certificate.revision_set_id:
                raise ConflictError("run revision set does not match the certification assessment")
            existing = cursor.execute(
                "SELECT certificate_json,payload_bytes FROM certification_assessments "
                "WHERE tenant_id=? AND project_id=? AND assessment_digest=?",
                (context.tenant_id, context.project_id, certificate.payload_digest),
            ).fetchone()
            if existing is not None:
                loaded = _certificate_from_json(dict(_decode_json(existing["certificate_json"])))
                if loaded != certificate or bytes(existing["payload_bytes"]) != payload_bytes:
                    raise ConflictError("certification assessment digest replay has different content")
                return loaded
            cursor.execute(
                "INSERT INTO certification_assessments("
                "tenant_id,project_id,assessment_digest,certificate_id,run_id,actor_id,goal_id,"
                "revision_set_id,revision_set_digest,revision_set_json,revision_set_bytes,"
                "proof_graph_digest,proof_graph_bytes,evidence_root,"
                "production_assessment,local_status,reviewer_identity,reviewer_independent,"
                "certified_envelope_json,status_counts_json,unresolved_risks_json,payload_json,payload_bytes,"
                "certificate_json,issued_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    context.tenant_id,
                    context.project_id,
                    certificate.payload_digest,
                    certificate.certificate_id,
                    certificate.run_id,
                    context.actor_id,
                    certificate.goal_id,
                    certificate.revision_set_id,
                    certificate.revision_set_digest,
                    _as_json(certificate.revision_set_revisions),
                    revision_set_bytes,
                    certificate.proof_graph_digest,
                    proof_graph_bytes,
                    certificate.evidence_root,
                    certificate.production_assessment,
                    certificate.status.value,
                    certificate.signer_identity,
                    certificate.signer_independent,
                    _as_json(certificate.certified_envelope),
                    _as_json(certificate.status_counts),
                    _as_json(certificate.unresolved_risks),
                    payload_bytes.decode("utf-8"),
                    payload_bytes,
                    certificate_json,
                    certificate.issued_at,
                ),
            )
            for ordinal, gate in enumerate(certificate.gate_results):
                cursor.execute(
                    "INSERT INTO certification_gate_results(tenant_id,project_id,assessment_digest,ordinal,"
                    "gate_name,decision,evidence_ids_json,reasons_json,result_digest) VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        context.tenant_id,
                        context.project_id,
                        certificate.payload_digest,
                        ordinal,
                        gate.gate,
                        gate.decision.value,
                        _as_json(gate.evidence_ids),
                        _as_json(gate.reasons),
                        digest_object(gate, domain="certification-gate-result"),
                    ),
                )
            for ordinal, evidence_id in enumerate(certificate.evidence_ids):
                evidence = cursor.execute(
                    "SELECT content_sha256,expires_at FROM evidence WHERE tenant_id=? AND project_id=? AND evidence_id=? "
                    "AND NOT EXISTS (SELECT 1 FROM evidence_revocations r WHERE r.tenant_id=evidence.tenant_id "
                    "AND r.project_id=evidence.project_id AND r.evidence_id=evidence.evidence_id)",
                    (context.tenant_id, context.project_id, evidence_id),
                ).fetchone()
                if evidence is None:
                    raise IntegrityError("assessment evidence is missing or revoked")
                if evidence["expires_at"] is not None and _parse_datetime(evidence["expires_at"]) <= utc_now():
                    raise IntegrityError("assessment evidence is expired")
                cursor.execute(
                    "INSERT INTO certification_evidence_links(tenant_id,project_id,assessment_digest,ordinal,"
                    "evidence_id,content_sha256) VALUES (?,?,?,?,?,?)",
                    (
                        context.tenant_id,
                        context.project_id,
                        certificate.payload_digest,
                        ordinal,
                        evidence_id,
                        str(evidence["content_sha256"]),
                    ),
                )
            self._insert_event(
                cursor,
                context,
                event_type="LOCAL_ASSESSMENT_RECORDED",
                subject_id=certificate.payload_digest,
                detail={"status": certificate.status.value, "certificate_id": certificate.certificate_id},
                occurred_at=certificate.issued_at,
            )
        return certificate

    def load_local(self, context: SecurityContext, payload_digest: str) -> CompletionCertificate | None:
        require_sha256_digest(payload_digest, field="payload_digest")
        with self._store.transaction(context) as cursor:
            row = cursor.execute(
                "SELECT certificate_json,payload_bytes FROM certification_assessments "
                "WHERE tenant_id=? AND project_id=? AND assessment_digest=?",
                (context.tenant_id, context.project_id, payload_digest),
            ).fetchone()
            if row is None:
                return None
            gates = cursor.execute(
                "SELECT gate_name,decision,evidence_ids_json,reasons_json FROM certification_gate_results "
                "WHERE tenant_id=? AND project_id=? AND assessment_digest=? ORDER BY ordinal",
                (context.tenant_id, context.project_id, payload_digest),
            ).fetchall()
            links = cursor.execute(
                "SELECT l.evidence_id,l.content_sha256,e.content_sha256 AS actual_sha256,e.content_bytes,e.expires_at,"
                "EXISTS(SELECT 1 FROM evidence_revocations r WHERE r.tenant_id=l.tenant_id "
                "AND r.project_id=l.project_id AND r.evidence_id=l.evidence_id) AS revoked "
                "FROM certification_evidence_links l JOIN evidence e USING(tenant_id,project_id,evidence_id) "
                "WHERE l.tenant_id=? AND l.project_id=? AND l.assessment_digest=? ORDER BY l.ordinal",
                (context.tenant_id, context.project_id, payload_digest),
            ).fetchall()
        certificate = _certificate_from_json(dict(_decode_json(row["certificate_json"])))
        payload_bytes = bytes(row["payload_bytes"])
        self._validate_local_payload(certificate, payload_bytes)
        loaded_gates = tuple(
            GateResult(
                gate=str(item["gate_name"]),
                decision=GateDecision(str(item["decision"])),
                evidence_ids=tuple(str(value) for value in _decode_json(item["evidence_ids_json"])),
                reasons=tuple(str(value) for value in _decode_json(item["reasons_json"])),
            )
            for item in gates
        )
        if loaded_gates != certificate.gate_results:
            raise IntegrityError("stored gate rows do not match the signed local payload")
        if tuple(str(item["evidence_id"]) for item in links) != certificate.evidence_ids:
            raise IntegrityError("stored evidence links do not match the signed local payload")
        for item in links:
            if (
                bool(item["revoked"])
                or str(item["content_sha256"]) != str(item["actual_sha256"])
                or (item["expires_at"] is not None and _parse_datetime(item["expires_at"]) <= utc_now())
            ):
                raise IntegrityError("durable assessment evidence is revoked, expired, or altered")
            verify_digest(
                bytes(item["content_bytes"]),
                str(item["actual_sha256"]),
                domain="evidence-content",
            )
        return certificate

    def save_external(
        self,
        context: SecurityContext,
        local: CompletionCertificate,
        receipt: ExternalSignatureReceipt,
        certificate: CompletionCertificate,
        *,
        signed_payload_bytes: bytes,
        trust_anchor_sha256: str,
    ) -> CompletionCertificate:
        require_sha256_digest(trust_anchor_sha256, field="trust_anchor_sha256")
        if len(signed_payload_bytes) > MAX_INLINE_CERTIFICATION_BYTES:
            raise ValidationError("signed certification payload exceeds the inline byte limit")
        if certificate.status not in {CertificationStatus.EXTERNALLY_VERIFIED, CertificationStatus.CERTIFIED}:
            raise CertificationError("external repository requires an external status")
        if replace(
            certificate,
            signer_identity=local.signer_identity,
            signer_key_id=local.signer_key_id,
            signer_independent=local.signer_independent,
            issued_at=local.issued_at,
            status=local.status,
            signature_receipt_id=local.signature_receipt_id,
            signature_receipt_sha256=local.signature_receipt_sha256,
        ) != local:
            raise IntegrityError("external certificate changed unsigned local assessment fields")
        expected_signed = receipt.signed_payload(certificate_id=local.certificate_id)
        if expected_signed != signed_payload_bytes:
            raise IntegrityError("stored signed payload differs from receipt claims")
        receipt_json_bytes = canonical_json_bytes(receipt)
        receipt_digest = digest_object(receipt, domain="external-signature-receipt")
        if not hmac.compare_digest(receipt_digest, certificate.signature_receipt_sha256 or ""):
            raise IntegrityError("external certificate receipt digest is invalid")
        external_certificate_bytes = canonical_json_bytes(certificate)
        external_certificate_json = external_certificate_bytes.decode("utf-8")
        external_certificate_digest = digest_object(certificate, domain="external-completion-certificate")
        with self._store.transaction(context) as cursor:
            assessment = cursor.execute(
                "SELECT certificate_json,local_status,production_assessment,reviewer_identity FROM certification_assessments "
                "WHERE tenant_id=? AND project_id=? AND assessment_digest=?",
                (context.tenant_id, context.project_id, local.payload_digest),
            ).fetchone()
            if assessment is None:
                raise CertificationError("durable local assessment is missing", code="LOCAL_ASSESSMENT_UNTRUSTED")
            if _certificate_from_json(dict(_decode_json(assessment["certificate_json"]))) != local:
                raise IntegrityError("durable local assessment differs from external input")
            evidence = cursor.execute(
                "SELECT content_bytes,content_sha256 FROM evidence WHERE tenant_id=? AND project_id=? AND evidence_id=? "
                "AND NOT EXISTS (SELECT 1 FROM evidence_revocations r WHERE r.tenant_id=evidence.tenant_id "
                "AND r.project_id=evidence.project_id AND r.evidence_id=evidence.evidence_id)",
                (context.tenant_id, context.project_id, receipt.verification_evidence_id),
            ).fetchone()
            if evidence is None or bytes(evidence["content_bytes"]) != receipt_json_bytes:
                raise IntegrityError("external receipt evidence bytes are missing, revoked, or mismatched")
            cursor.execute(
                "INSERT INTO certification_external_receipts(tenant_id,project_id,assessment_digest,receipt_id,"
                "verification_evidence_id,payload_digest,certificate_id,provider_id,signer_identity,key_id,algorithm,"
                "signature_bytes,signed_payload_bytes,receipt_json_bytes,receipt_sha256,trust_anchor_sha256,"
                "attested_status,independent,certification_authority,cryptographically_verified,issued_at,expires_at,verified_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
                (
                    context.tenant_id,
                    context.project_id,
                    local.payload_digest,
                    receipt.receipt_id,
                    receipt.verification_evidence_id,
                    receipt.payload_sha256,
                    local.certificate_id,
                    receipt.provider_id,
                    receipt.signer_identity,
                    receipt.key_id,
                    receipt.algorithm,
                    receipt.signature_bytes(),
                    signed_payload_bytes,
                    receipt_json_bytes,
                    receipt_digest,
                    trust_anchor_sha256,
                    receipt.attested_status.value,
                    receipt.independent,
                    receipt.certification_authority,
                    True,
                    receipt.issued_at,
                    receipt.expires_at,
                    certificate.issued_at,
                ),
            )
            cursor.execute(
                "INSERT INTO certification_external_decisions(tenant_id,project_id,assessment_digest,decision_id,"
                "receipt_id,status,external_certificate_digest,external_certificate_json,external_certificate_bytes,decided_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
                (
                    context.tenant_id,
                    context.project_id,
                    local.payload_digest,
                    f"{local.certificate_id}:{certificate.status.value}",
                    receipt.receipt_id,
                    certificate.status.value,
                    external_certificate_digest,
                    external_certificate_json,
                    external_certificate_bytes,
                    certificate.issued_at,
                ),
            )
            stored = cursor.execute(
                "SELECT external_certificate_json FROM certification_external_decisions "
                "WHERE tenant_id=? AND project_id=? AND assessment_digest=? AND status=?",
                (context.tenant_id, context.project_id, local.payload_digest, certificate.status.value),
            ).fetchone()
            if stored is None or _certificate_from_json(dict(_decode_json(stored["external_certificate_json"]))) != certificate:
                raise ConflictError("external certification replay differs from the durable decision")
            self._insert_event(
                cursor,
                context,
                event_type="EXTERNAL_DECISION_RECORDED",
                subject_id=receipt.receipt_id,
                detail={"status": certificate.status.value, "assessment_digest": local.payload_digest},
                occurred_at=certificate.issued_at,
            )
        return certificate

    def load_effective(
        self,
        context: SecurityContext,
        payload_digest: str,
        *,
        now: datetime | None = None,
    ) -> CompletionCertificate | None:
        require_sha256_digest(payload_digest, field="payload_digest")
        current = now or utc_now()
        with self._store.transaction(context) as cursor:
            row = cursor.execute(
                "SELECT external_certificate_json,effective_status FROM effective_certification_decisions "
                "WHERE tenant_id=? AND project_id=? AND assessment_digest=? "
                "ORDER BY CASE status WHEN 'CERTIFIED' THEN 2 ELSE 1 END DESC,decided_at DESC LIMIT 1",
                (context.tenant_id, context.project_id, payload_digest),
            ).fetchone()
        if row is None:
            return self.load_local(context, payload_digest)
        certificate = _certificate_from_json(dict(_decode_json(row["external_certificate_json"])))
        status = CertificationStatus(str(row["effective_status"]))
        # The view uses database clock time.  An explicit historical/future
        # caller time can only make the result more conservative here.
        if current < certificate.issued_at:
            status = CertificationStatus.EXPIRED
        return certificate if certificate.status is status else replace(certificate, status=status)

    def revoke_external(
        self,
        context: SecurityContext,
        receipt_id: str,
        *,
        reason: str,
        revocation_id: str | None = None,
        now: datetime | None = None,
    ) -> str:
        if not receipt_id or not reason.strip():
            raise ValidationError("receipt id and revocation reason are required")
        identifier = revocation_id or f"cert-revocation-{uuid.uuid4()}"
        occurred_at = now or utc_now()
        with self._store.transaction(context) as cursor:
            receipt = cursor.execute(
                "SELECT assessment_digest FROM certification_external_receipts "
                "WHERE tenant_id=? AND project_id=? AND receipt_id=?",
                (context.tenant_id, context.project_id, receipt_id),
            ).fetchone()
            if receipt is None:
                raise NotFoundError("external signature receipt was not found")
            cursor.execute(
                "INSERT INTO certification_signature_revocations(tenant_id,project_id,revocation_id,receipt_id,"
                "assessment_digest,actor_id,reason,revoked_at) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
                (
                    context.tenant_id,
                    context.project_id,
                    identifier,
                    receipt_id,
                    str(receipt["assessment_digest"]),
                    context.actor_id,
                    reason,
                    occurred_at,
                ),
            )
            stored = cursor.execute(
                "SELECT revocation_id,reason FROM certification_signature_revocations "
                "WHERE tenant_id=? AND project_id=? AND receipt_id=?",
                (context.tenant_id, context.project_id, receipt_id),
            ).fetchone()
            if stored is None:
                raise IntegrityError("external signature revocation was not persisted")
            if str(stored["revocation_id"]) != identifier or str(stored["reason"]) != reason:
                raise ConflictError("external signature receipt was already revoked differently")
            self._insert_event(
                cursor,
                context,
                event_type="EXTERNAL_SIGNATURE_REVOKED",
                subject_id=receipt_id,
                detail={"reason": reason, "revocation_id": identifier},
                occurred_at=occurred_at,
            )
        return identifier

    @staticmethod
    def _insert_event(
        cursor: Any,
        context: SecurityContext,
        *,
        event_type: str,
        subject_id: str,
        detail: Mapping[str, object],
        occurred_at: datetime,
    ) -> None:
        detail_digest = digest_object(detail, domain="certification-event-detail")
        cursor.execute(
            "INSERT INTO certification_events(tenant_id,project_id,event_id,actor_id,event_type,subject_id,"
            "detail_json,detail_sha256,occurred_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                context.tenant_id,
                context.project_id,
                f"cert-event-{uuid.uuid4()}",
                context.actor_id,
                event_type,
                subject_id,
                _as_json(detail),
                detail_digest,
                occurred_at,
            ),
        )
