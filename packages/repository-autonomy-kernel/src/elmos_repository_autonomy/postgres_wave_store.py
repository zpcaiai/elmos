"""PostgreSQL persistence for Wave 0-5 external and certification state."""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from .errors import ContractError, StaleStateError
from .models import canonical_json, digest, utc_now
from .postgres import PgConnection, PostgresSessionFactory


def _normalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, (datetime, uuid.UUID)):
        return str(value)
    return value


class PostgresWaveStore:
    """Duck-typed store consumed by external, delivery and certification engines.

    Every operation creates a transaction-local tenant context, so RLS remains
    fail-closed when the context is absent. JSON is passed as text and cast by
    PostgreSQL rather than interpolated into SQL.
    """

    def __init__(self, sessions: PostgresSessionFactory, *, account_context: str = "control-plane") -> None:
        self.sessions = sessions
        self.account_context = account_context

    @contextmanager
    def _transaction(self, tenant_id: str, account_id: str | None = None) -> Iterator[PgConnection]:
        with self.sessions.tenant_transaction(
            tenant_id=tenant_id, account_id=account_id or self.account_context
        ) as connection:
            yield connection

    @staticmethod
    def _json(value: Any) -> str:
        return canonical_json(value).decode("utf-8")

    @staticmethod
    def _one(result: Any) -> dict[str, Any] | None:
        row = result.fetchone()
        if row is None:
            return None
        if not isinstance(row, Mapping):
            raise ContractError("POSTGRES_ROW_FACTORY_INVALID", "PostgreSQL connections must return mapping rows")
        return _normalize(row)

    @staticmethod
    def _many(result: Any) -> list[dict[str, Any]]:
        rows = result.fetchall()
        if any(not isinstance(row, Mapping) for row in rows):
            raise ContractError("POSTGRES_ROW_FACTORY_INVALID", "PostgreSQL connections must return mapping rows")
        return [_normalize(row) for row in rows]

    def create_external_operation(
        self, *, tenant_id: str, account_id: str, capability: str, adapter_id: str,
        adapter_version: str, provider_instance: str, region: str, native_resource_id: str,
        action: str, side_effects: bool, idempotency_key: str, request_hash: str,
        request_metadata: Mapping[str, Any], run_id: str | None = None,
    ) -> dict[str, Any]:
        with self._transaction(tenant_id, account_id) as db:
            operation_id = str(uuid.uuid4())
            inserted = self._one(
                db.execute(
                    "insert into autonomy_external_operations("
                    "operation_id,tenant_id,account_id,run_id,capability,adapter_id,adapter_version,"
                    "provider_instance,region,native_resource_id,action,state,side_effects,idempotency_key,"
                    "request_hash,request_metadata) values ("
                    "%s::uuid,%s::uuid,%s::uuid,%s::uuid,%s,%s,%s,%s,%s,%s,%s,'DRY_RUN',%s,%s,%s,%s::jsonb) "
                    "on conflict (tenant_id,capability,adapter_id,idempotency_key) do nothing returning *",
                    (
                        operation_id, tenant_id, account_id, run_id, capability, adapter_id, adapter_version,
                        provider_instance, region, native_resource_id, action, side_effects, idempotency_key,
                        request_hash, self._json(request_metadata),
                    ),
                )
            )
            if inserted is not None:
                return inserted
            existing = self._one(
                db.execute(
                    "select * from autonomy_external_operations where tenant_id=%s::uuid and capability=%s "
                    "and adapter_id=%s and idempotency_key=%s",
                    (tenant_id, capability, adapter_id, idempotency_key),
                )
            )
            if existing is None or existing.get("request_hash") != request_hash:
                raise ContractError("IDEMPOTENCY_CONFLICT", "idempotency key was reused with a different request")
            return existing

    def get_external_operation(self, operation_id: str, *, tenant_id: str) -> dict[str, Any] | None:
        with self._transaction(tenant_id) as db:
            return self._one(
                db.execute(
                    "select * from autonomy_external_operations where operation_id=%s::uuid and tenant_id=%s::uuid",
                    (operation_id, tenant_id),
                )
            )

    def transition_external_operation(
        self, operation_id: str, *, tenant_id: str, expected_states: set[str], target: str,
        authority_hash: str | None = None, result: Any = None, error: Any = None,
        unknown_outcome: bool | None = None, compensation_token: str | None = None,
    ) -> dict[str, Any]:
        with self._transaction(tenant_id) as db:
            current = self._one(
                db.execute(
                    "select * from autonomy_external_operations where operation_id=%s::uuid and tenant_id=%s::uuid for update",
                    (operation_id, tenant_id),
                )
            )
            if current is None:
                raise ContractError("EXTERNAL_OPERATION_NOT_FOUND", "operation is not visible in the requested tenant")
            if current["state"] not in expected_states:
                raise StaleStateError(
                    "EXTERNAL_OPERATION_STATE_CONFLICT",
                    f"cannot transition external operation from {current['state']} to {target}",
                )
            return self._one(
                db.execute(
                    "update autonomy_external_operations set state=%s,authority_hash=%s,result=%s::jsonb,error=%s::jsonb,"
                    "unknown_outcome=%s,compensation_token=%s,updated_at=now() "
                    "where operation_id=%s::uuid and tenant_id=%s::uuid returning *",
                    (
                        target,
                        authority_hash if authority_hash is not None else current.get("authority_hash"),
                        self._json(result) if result is not None else self._json(current.get("result")),
                        self._json(error) if error is not None else self._json(current.get("error")),
                        unknown_outcome if unknown_outcome is not None else current.get("unknown_outcome", False),
                        compensation_token if compensation_token is not None else current.get("compensation_token"),
                        operation_id,
                        tenant_id,
                    ),
                )
            ) or {}

    def record_external_receipt(
        self, *, tenant_id: str, operation_id: str, receipt_type: str, status: str,
        producer_id: str, verifier_id: str | None, evidence_class: str,
        raw_evidence: Mapping[str, Any],
    ) -> dict[str, Any]:
        created_at = utc_now()
        body = {
            "operation_id": operation_id,
            "receipt_type": receipt_type,
            "status": status,
            "producer_id": producer_id,
            "verifier_id": verifier_id,
            "evidence_class": evidence_class,
            "raw_evidence": dict(raw_evidence),
            "created_at": created_at,
        }
        receipt_id = str(uuid.uuid4())
        with self._transaction(tenant_id) as db:
            row = self._one(
                db.execute(
                    "insert into autonomy_external_receipts("
                    "receipt_id,tenant_id,operation_id,receipt_type,status,producer_id,verifier_id,evidence_class,"
                    "raw_evidence,content_hash,created_at) values ("
                    "%s::uuid,%s::uuid,%s::uuid,%s,%s,%s,%s,%s,%s::jsonb,%s,%s::timestamptz) returning *",
                    (
                        receipt_id, tenant_id, operation_id, receipt_type, status, producer_id, verifier_id,
                        evidence_class, self._json(raw_evidence), digest(body), created_at,
                    ),
                )
            )
        return row or {}

    def list_external_receipts(self, operation_id: str, *, tenant_id: str) -> list[dict[str, Any]]:
        with self._transaction(tenant_id) as db:
            return self._many(
                db.execute(
                    "select * from autonomy_external_receipts where operation_id=%s::uuid and tenant_id=%s::uuid "
                    "order by created_at,receipt_id",
                    (operation_id, tenant_id),
                )
            )

    def enqueue_outbox(
        self, *, tenant_id: str, topic: str, ordering_key: str, event_type: str,
        payload: Mapping[str, Any], idempotency_key: str, operation_id: str | None = None,
        available_at: str | None = None,
    ) -> dict[str, Any]:
        payload_hash = digest(payload)
        with self._transaction(tenant_id) as db:
            inserted = self._one(
                db.execute(
                    "insert into autonomy_outbox_events("
                    "event_id,tenant_id,operation_id,topic,ordering_key,event_type,payload,payload_hash,state,"
                    "idempotency_key,available_at) values ("
                    "%s::uuid,%s::uuid,%s::uuid,%s,%s,%s,%s::jsonb,%s,'PENDING',%s,coalesce(%s::timestamptz,now())) "
                    "on conflict (tenant_id,topic,idempotency_key) do nothing returning *",
                    (
                        str(uuid.uuid4()), tenant_id, operation_id, topic, ordering_key, event_type,
                        self._json(payload), payload_hash, idempotency_key, available_at,
                    ),
                )
            )
            if inserted is not None:
                return inserted
            existing = self._one(
                db.execute(
                    "select * from autonomy_outbox_events where tenant_id=%s::uuid and topic=%s and idempotency_key=%s",
                    (tenant_id, topic, idempotency_key),
                )
            )
            if existing is None or existing.get("payload_hash") != payload_hash:
                raise ContractError("IDEMPOTENCY_CONFLICT", "outbox idempotency key was reused")
            return existing

    def claim_outbox(self, *, tenant_id: str, limit: int = 100) -> list[dict[str, Any]]:
        if limit < 1 or limit > 1000:
            raise ContractError("INVALID_INPUT", "outbox claim limit must be between 1 and 1000")
        with self._transaction(tenant_id) as db:
            rows = self._many(
                db.execute(
                    "select * from autonomy_outbox_events where tenant_id=%s::uuid "
                    "and state in ('PENDING','RETRY') and available_at<=now() "
                    "order by ordering_key,created_at,event_id for update skip locked limit %s",
                    (tenant_id, limit),
                )
            )
            claimed: list[dict[str, Any]] = []
            for row in rows:
                claimed.append(
                    self._one(
                        db.execute(
                            "update autonomy_outbox_events set state='PUBLISHING',attempts=attempts+1 "
                            "where event_id=%s::uuid and tenant_id=%s::uuid returning *",
                            (row["event_id"], tenant_id),
                        )
                    ) or {}
                )
            return claimed

    def complete_outbox(self, event_id: str, *, tenant_id: str, outcome: str) -> dict[str, Any]:
        if outcome not in {"PUBLISHED", "RETRY", "UNKNOWN", "DEAD_LETTER"}:
            raise ContractError("INVALID_INPUT", "unsupported outbox outcome")
        with self._transaction(tenant_id) as db:
            current = self._one(
                db.execute(
                    "select * from autonomy_outbox_events where event_id=%s::uuid and tenant_id=%s::uuid for update",
                    (event_id, tenant_id),
                )
            )
            if current is None:
                raise ContractError("EVENT_NOT_FOUND", "outbox event is not visible in the requested tenant")
            if current["state"] != "PUBLISHING":
                raise StaleStateError("EVENT_STATE_CONFLICT", "outbox event is not currently claimed")
            return self._one(
                db.execute(
                    "update autonomy_outbox_events set state=%s,published_at=case when %s='PUBLISHED' then now() else null end "
                    "where event_id=%s::uuid and tenant_id=%s::uuid returning *",
                    (outcome, outcome, event_id, tenant_id),
                )
            ) or {}

    def get_outbox_event(self, event_id: str, *, tenant_id: str) -> dict[str, Any] | None:
        with self._transaction(tenant_id) as db:
            return self._one(
                db.execute(
                    "select * from autonomy_outbox_events where event_id=%s::uuid and tenant_id=%s::uuid",
                    (event_id, tenant_id),
                )
            )

    def reconcile_outbox(self, event_id: str, *, tenant_id: str, published: bool | None) -> dict[str, Any]:
        with self._transaction(tenant_id) as db:
            current = self._one(
                db.execute(
                    "select * from autonomy_outbox_events where event_id=%s::uuid and tenant_id=%s::uuid for update",
                    (event_id, tenant_id),
                )
            )
            if current is None:
                raise ContractError("EVENT_NOT_FOUND", "outbox event is not visible in the requested tenant")
            if current["state"] != "UNKNOWN":
                raise StaleStateError("EVENT_STATE_CONFLICT", "only unknown events can be reconciled")
            state = "PUBLISHED" if published is True else "RETRY" if published is False else "UNKNOWN"
            return self._one(
                db.execute(
                    "update autonomy_outbox_events set state=%s,published_at=case when %s='PUBLISHED' then now() else null end "
                    "where event_id=%s::uuid and tenant_id=%s::uuid returning *",
                    (state, state, event_id, tenant_id),
                )
            ) or {}

    def record_outbox_receipt(
        self, *, event_id: str, tenant_id: str, status: str, producer_id: str,
        verifier_id: str | None, evidence_class: str, raw_evidence: Mapping[str, Any],
    ) -> dict[str, Any]:
        created_at = utc_now()
        body = {
            "event_id": event_id,
            "status": status,
            "producer_id": producer_id,
            "verifier_id": verifier_id,
            "evidence_class": evidence_class,
            "raw_evidence": dict(raw_evidence),
            "created_at": created_at,
        }
        with self._transaction(tenant_id) as db:
            return self._one(
                db.execute(
                    "insert into autonomy_outbox_receipts("
                    "receipt_id,tenant_id,event_id,status,producer_id,verifier_id,evidence_class,raw_evidence,"
                    "content_hash,created_at) values ("
                    "%s::uuid,%s::uuid,%s::uuid,%s,%s,%s,%s,%s::jsonb,%s,%s::timestamptz) returning *",
                    (
                        str(uuid.uuid4()), tenant_id, event_id, status, producer_id, verifier_id,
                        evidence_class, self._json(raw_evidence), digest(body), created_at,
                    ),
                )
            ) or {}

    def list_outbox_receipts(self, event_id: str, *, tenant_id: str) -> list[dict[str, Any]]:
        with self._transaction(tenant_id) as db:
            return self._many(
                db.execute(
                    "select * from autonomy_outbox_receipts where event_id=%s::uuid and tenant_id=%s::uuid "
                    "order by created_at,receipt_id",
                    (event_id, tenant_id),
                )
            )

    def begin_inbox_event(
        self, *, tenant_id: str, consumer_id: str, event_id: str, payload: Mapping[str, Any],
        ordering_key: str, side_effects: bool,
    ) -> dict[str, Any]:
        payload_hash = digest(payload)
        with self._transaction(tenant_id) as db:
            inserted = self._one(
                db.execute(
                    "insert into autonomy_inbox_events("
                    "tenant_id,consumer_id,event_id,payload_hash,ordering_key,state,attempts,side_effects) "
                    "values (%s::uuid,%s,%s::uuid,%s,%s,'PROCESSING',1,%s) "
                    "on conflict (tenant_id,consumer_id,event_id) do nothing returning *",
                    (tenant_id, consumer_id, event_id, payload_hash, ordering_key, side_effects),
                )
            )
            if inserted is not None:
                return {**inserted, "replayed": False}
            current = self._one(
                db.execute(
                    "select * from autonomy_inbox_events where tenant_id=%s::uuid and consumer_id=%s "
                    "and event_id=%s::uuid for update",
                    (tenant_id, consumer_id, event_id),
                )
            )
            if current is None or current.get("payload_hash") != payload_hash:
                raise ContractError("EVENT_ID_CONFLICT", "event ID was reused with a different payload or tenant")
            if current["state"] in {"PROCESSING", "UNKNOWN"}:
                raise StaleStateError(
                    "EVENT_RECONCILIATION_REQUIRED",
                    "event is already processing or has an unknown side-effect outcome",
                )
            if current["state"] == "PROCESSED":
                return {**current, "replayed": True}
            row = self._one(
                db.execute(
                    "update autonomy_inbox_events set state='PROCESSING',attempts=attempts+1,updated_at=now() "
                    "where tenant_id=%s::uuid and consumer_id=%s and event_id=%s::uuid returning *",
                    (tenant_id, consumer_id, event_id),
                )
            )
        return {**(row or {}), "replayed": False}

    def complete_inbox_event(
        self, *, tenant_id: str, consumer_id: str, event_id: str, state: str,
        result: Mapping[str, Any] | None = None, error: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if state not in {"PROCESSED", "RETRY", "UNKNOWN", "DEAD_LETTER"}:
            raise ContractError("INVALID_INPUT", "unsupported inbox outcome")
        with self._transaction(tenant_id) as db:
            current = self._one(
                db.execute(
                    "select * from autonomy_inbox_events where tenant_id=%s::uuid and consumer_id=%s "
                    "and event_id=%s::uuid for update",
                    (tenant_id, consumer_id, event_id),
                )
            )
            if current is None:
                raise ContractError("EVENT_NOT_FOUND", "inbox event is not visible in the requested tenant")
            if current["state"] != "PROCESSING":
                raise StaleStateError("EVENT_STATE_CONFLICT", "inbox event is not being processed")
            return self._one(
                db.execute(
                    "update autonomy_inbox_events set state=%s,result=%s::jsonb,error=%s::jsonb,updated_at=now() "
                    "where tenant_id=%s::uuid and consumer_id=%s and event_id=%s::uuid returning *",
                    (
                        state, self._json(result), self._json(error), tenant_id, consumer_id, event_id,
                    ),
                )
            ) or {}

    def reconcile_inbox_event(
        self, *, tenant_id: str, consumer_id: str, event_id: str, processed: bool | None,
        evidence: Mapping[str, Any],
    ) -> dict[str, Any]:
        with self._transaction(tenant_id) as db:
            current = self._one(
                db.execute(
                    "select * from autonomy_inbox_events where tenant_id=%s::uuid and consumer_id=%s "
                    "and event_id=%s::uuid for update",
                    (tenant_id, consumer_id, event_id),
                )
            )
            if current is None:
                raise ContractError("EVENT_NOT_FOUND", "inbox event is not visible in the requested tenant")
            if current["state"] not in {"UNKNOWN", "PROCESSING"}:
                raise StaleStateError("EVENT_STATE_CONFLICT", "inbox event is not reconcilable")
            state = "PROCESSED" if processed is True else "RETRY" if processed is False else "UNKNOWN"
            return self._one(
                db.execute(
                    "update autonomy_inbox_events set state=%s,result=%s::jsonb,updated_at=now() "
                    "where tenant_id=%s::uuid and consumer_id=%s and event_id=%s::uuid returning *",
                    (
                        state, self._json({"reconciliation_evidence": dict(evidence)}),
                        tenant_id, consumer_id, event_id,
                    ),
                )
            ) or {}

    def record_secret_lease(
        self, *, tenant_id: str, broker_id: str, secret_ref: str, scope: Mapping[str, Any],
        expires_at: str, receipt_hash: str, native_lease_id: str | None = None,
        evidence_class: str = "LOCAL_ENGINEERING_VALIDATED",
    ) -> dict[str, Any]:
        if any(key.casefold() in {"value", "secret", "token", "password"} for key in scope):
            raise ContractError("SECRET_EXPOSURE", "secret lease scope must contain references, not secret values")
        with self._transaction(tenant_id) as db:
            return self._one(
                db.execute(
                    "insert into autonomy_secret_leases("
                    "lease_id,tenant_id,broker_id,secret_ref,scope_hash,state,native_lease_id,evidence_class,"
                    "expires_at,receipt_hash) values ("
                    "%s::uuid,%s::uuid,%s,%s,%s,'ACTIVE',%s,%s,%s::timestamptz,%s) returning *",
                    (
                        str(uuid.uuid4()), tenant_id, broker_id, secret_ref, digest(scope), native_lease_id,
                        evidence_class, expires_at, receipt_hash,
                    ),
                )
            ) or {}

    def revoke_secret_lease(
        self, lease_id: str, *, tenant_id: str, state: str = "REVOKED",
        revoke_receipt_hash: str | None = None,
    ) -> dict[str, Any]:
        if state not in {"REVOKED", "REVOKE_UNKNOWN"}:
            raise ContractError("INVALID_INPUT", "unsupported secret revoke state")
        with self._transaction(tenant_id) as db:
            current = self._one(
                db.execute(
                    "select * from autonomy_secret_leases where lease_id=%s::uuid and tenant_id=%s::uuid for update",
                    (lease_id, tenant_id),
                )
            )
            if current is None:
                raise ContractError("SECRET_LEASE_NOT_FOUND", "secret lease is not visible in the requested tenant")
            if current["state"] == "REVOKED":
                return current
            return self._one(
                db.execute(
                    "update autonomy_secret_leases set state=%s,revoke_receipt_hash=%s,revoked_at=now() "
                    "where lease_id=%s::uuid and tenant_id=%s::uuid returning *",
                    (state, revoke_receipt_hash or current.get("revoke_receipt_hash"), lease_id, tenant_id),
                )
            ) or {}

    def record_certification_evidence(self, *, tenant_id: str, record: Mapping[str, Any]) -> dict[str, Any]:
        with self._transaction(tenant_id) as db:
            inserted = self._one(
                db.execute(
                    "insert into autonomy_certification_evidence("
                    "evidence_id,tenant_id,case_id,capability,level,status,evidence_class,source_kind,producer_id,"
                    "verifier_id,independent,payload,signed_document,signature,key_id,content_hash,signature_verified,"
                    "captured_at,expires_at) values ("
                    "%s::uuid,%s::uuid,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s,"
                    "%s::timestamptz,%s::timestamptz) "
                    "on conflict (evidence_id) do nothing returning *",
                    (
                        record["evidence_id"], tenant_id, record["case_id"], record["capability"], record["level"],
                        record["status"], record["evidence_class"], record["source_kind"], record["producer_id"],
                        record.get("verifier_id"), bool(record["independent"]), self._json(record.get("payload", {})),
                        self._json(record.get("signed_document", {})), record.get("signature"), record.get("key_id"),
                        record["content_hash"], bool(record["signature_verified"]), record["captured_at"], record.get("expires_at"),
                    ),
                )
            )
            if inserted is not None:
                return inserted
            existing = self._one(
                db.execute(
                    "select * from autonomy_certification_evidence where evidence_id=%s::uuid",
                    (record["evidence_id"],),
                )
            )
            if existing is None or existing.get("content_hash") != record.get("content_hash"):
                raise ContractError("EVIDENCE_ID_CONFLICT", "evidence ID was reused with different bytes or tenant")
            return existing

    def list_certification_evidence(self, *, tenant_id: str) -> list[dict[str, Any]]:
        with self._transaction(tenant_id) as db:
            return self._many(
                db.execute(
                    "select * from autonomy_certification_evidence where tenant_id=%s::uuid "
                    "order by case_id,captured_at,evidence_id",
                    (tenant_id,),
                )
            )

    def record_certification_run(
        self, *, tenant_id: str, candidate_digest: str, state: str,
        level_results: Mapping[str, Any], matrix_result: Mapping[str, Any], p05_issued: bool,
    ) -> dict[str, Any]:
        created_at = utc_now()
        body = {
            "candidate_digest": candidate_digest,
            "state": state,
            "level_results": dict(level_results),
            "matrix_result": dict(matrix_result),
            "p05_issued": p05_issued,
            "created_at": created_at,
        }
        with self._transaction(tenant_id) as db:
            return self._one(
                db.execute(
                    "insert into autonomy_certification_runs("
                    "certification_run_id,tenant_id,candidate_digest,state,level_results,matrix_result,p05_issued,"
                    "decision_hash,created_at) values ("
                    "%s::uuid,%s::uuid,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s::timestamptz) returning *",
                    (
                        str(uuid.uuid4()), tenant_id, candidate_digest, state, self._json(level_results),
                        self._json(matrix_result), p05_issued, digest(body), created_at,
                    ),
                )
            ) or {}

    def record_customer_acceptance(
        self, *, tenant_id: str, repository_binding_hash: str, route_id: str, candidate_digest: str,
        customer_actor_id: str, executor_id: str, decision: str, evidence_ids: list[str],
        signature_verified: bool,
    ) -> dict[str, Any]:
        if customer_actor_id == executor_id:
            raise ContractError("SELF_APPROVAL_DENIED", "customer acceptance must be independent from the executor")
        if decision == "ACCEPTED" and (not signature_verified or not evidence_ids):
            raise ContractError("ACCEPTANCE_EVIDENCE_MISSING", "accepted decisions require verified evidence")
        body = {
            "tenant_id": tenant_id,
            "repository_binding_hash": repository_binding_hash,
            "route_id": route_id,
            "candidate_digest": candidate_digest,
            "customer_actor_id": customer_actor_id,
            "executor_id": executor_id,
            "decision": decision,
            "evidence_ids": evidence_ids,
            "signature_verified": signature_verified,
            "created_at": utc_now(),
        }
        with self._transaction(tenant_id) as db:
            inserted = self._one(
                db.execute(
                    "insert into autonomy_customer_acceptance("
                    "acceptance_id,tenant_id,repository_binding_hash,route_id,candidate_digest,customer_actor_id,"
                    "executor_id,decision,evidence_ids,signature_verified,content_hash,created_at) values ("
                    "%s::uuid,%s::uuid,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s::timestamptz) "
                    "on conflict (tenant_id,repository_binding_hash,route_id,candidate_digest) do nothing returning *",
                    (
                        str(uuid.uuid4()), tenant_id, repository_binding_hash, route_id, candidate_digest,
                        customer_actor_id, executor_id, decision, self._json(evidence_ids), signature_verified,
                        digest(body), body["created_at"],
                    ),
                )
            )
            if inserted is not None:
                return inserted
            existing = self._one(
                db.execute(
                    "select * from autonomy_customer_acceptance where tenant_id=%s::uuid "
                    "and repository_binding_hash=%s and route_id=%s and candidate_digest=%s",
                    (tenant_id, repository_binding_hash, route_id, candidate_digest),
                )
            )
            if existing is not None:
                comparable = {
                    "customer_actor_id": customer_actor_id,
                    "executor_id": executor_id,
                    "decision": decision,
                    "evidence_ids": evidence_ids,
                    "signature_verified": signature_verified,
                }
                if any(existing.get(key) != value for key, value in comparable.items()):
                    raise ContractError("ACCEPTANCE_CONFLICT", "acceptance key was reused with a different decision")
                return existing
            raise ContractError("ACCEPTANCE_CONFLICT", "acceptance key is not visible after conflict")

    def list_customer_acceptances(
        self, *, tenant_id: str, candidate_digest: str | None = None
    ) -> list[dict[str, Any]]:
        query = "select * from autonomy_customer_acceptance where tenant_id=%s::uuid"
        parameters: tuple[Any, ...] = (tenant_id,)
        if candidate_digest is not None:
            query += " and candidate_digest=%s"
            parameters += (candidate_digest,)
        query += " order by created_at,acceptance_id"
        with self._transaction(tenant_id) as db:
            return self._many(db.execute(query, parameters))

    def metrics(self) -> dict[str, float]:
        """Small readiness-safe metrics snapshot without exposing tenant rows."""

        connection = self.sessions.connect()
        try:
            row = self._one(
                connection.execute(
                    "select count(*)::double precision as schema_migration_count from autonomy_schema_migrations"
                )
            )
            return {"schema_migration_count": float((row or {}).get("schema_migration_count", 0))}
        finally:
            connection.close()

    def close(self) -> None:
        """Connections are transaction-scoped; retained for store interface parity."""

        return
