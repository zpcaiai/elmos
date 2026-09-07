"""Durable cost/ETA and content-minimized telemetry lifecycle.

The pure estimators remain useful for deterministic local composition.  This
bridge is the production boundary: it binds every estimate and trace to the
authenticated tenant/project, persists immutable snapshots, and never treats
an estimate as reconciled provider actuals without a separate verified receipt.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from .canonical import (
    canonical_digest,
    canonical_json,
    normalize_sha256,
    require_idempotency_key,
    require_resource_id,
    utc_now,
)
from .errors import ConflictError, IntegrityError, ValidationError
from .models import TenantContext
from .observability import build_multimodal_observability, estimate_processing_cost_eta
from .skill_runtime import RuntimeContext
from .store import IntakeStore


COST_SKILL = "elmos-processing-cost-and-eta-estimation"
OBSERVABILITY_SKILL = "elmos-multimodal-observability"
TELEMETRY_SKILLS = frozenset({COST_SKILL, OBSERVABILITY_SKILL})
_SUBJECT_KEYS = (
    ("task_id", "TASK"),
    ("job_id", "JOB"),
    ("session_id", "SESSION"),
    ("asset_id", "ASSET"),
)
_ACTUALS_STATES = frozenset({"NOT_RUN", "PENDING", "RECONCILED", "UNKNOWN", "BLOCKED"})
_REQUIRED_TABLES = {
    "multimodal_telemetry_subjects": {
        "tenant_id", "project_id", "subject_kind", "subject_id", "version",
        "latest_estimate_sequence", "latest_trace_sequence", "actuals_state", "updated_at",
    },
    "multimodal_cost_estimates": {
        "tenant_id", "project_id", "subject_kind", "subject_id", "estimate_sequence",
        "idempotency_key", "request_digest", "estimate_json", "estimate_digest",
        "result_state", "result_code", "calibration_version", "estimated_cost", "currency",
        "actuals_state", "provider_actuals_digest", "provider_actuals_byte_count",
        "trace_id", "actor_id", "created_at",
    },
    "multimodal_cost_line_items": {
        "tenant_id", "project_id", "subject_kind", "subject_id", "estimate_sequence",
        "stage_id", "stage", "asset_id", "provider", "file_type", "quantity", "unit",
        "unit_price", "estimated_cost", "actual_quantity", "actual_cost", "currency",
        "actual_evidence_digest", "actual_evidence_byte_count", "created_at",
    },
    "multimodal_telemetry_traces": {
        "tenant_id", "project_id", "subject_kind", "subject_id", "trace_sequence",
        "idempotency_key", "request_digest", "trace_id", "trace_json", "trace_digest",
        "result_state", "result_code", "policy_version", "missing_stage_count", "event_count",
        "actor_id", "created_at",
    },
    "multimodal_telemetry_events": {
        "tenant_id", "project_id", "subject_kind", "subject_id", "trace_sequence",
        "event_id", "trace_id", "parent_event_id", "event_type", "stage", "provider",
        "file_type", "status", "error_code", "event_json", "event_digest", "created_at",
    },
}


def _bridge_envelope(
    state: str,
    code: str,
    outputs: Mapping[str, Any],
    *,
    retryable: bool = False,
) -> dict[str, Any]:
    return {
        "state": state,
        "code": code,
        "outputs": dict(outputs),
        "metrics": {},
        "retryable": retryable,
    }


def _domain_request(ctx: RuntimeContext, payload: Mapping[str, Any]) -> dict[str, Any]:
    inputs = {
        key: value
        for key, value in payload.items()
        if key not in {"operation", "idempotency_key", "trace_id"}
    }
    return {
        "schema_version": "1.0",
        "request_id": ctx.request_id,
        "tenant_id": ctx.tenant_id,
        "project_id": ctx.project_id,
        "actor_id": ctx.actor_id,
        "trace_id": ctx.trace_id,
        "inputs": inputs,
        "policy": dict(ctx.policy),
        "capabilities": dict(ctx.capabilities),
    }


def _strict_rows(value: Any, field: str, *, maximum: int = 100_000) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValidationError("TELEMETRY_COLLECTION_INVALID", details={"field": field})
    if len(value) > maximum:
        raise ValidationError("TELEMETRY_COLLECTION_LIMIT", details={"field": field})
    rows: list[Mapping[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ValidationError("TELEMETRY_ROW_INVALID", details={"field": field})
        rows.append(item)
    return rows


def _subject(
    ctx: RuntimeContext,
    payload: Mapping[str, Any],
    *,
    collection: str,
) -> tuple[str, str]:
    rows = _strict_rows(payload.get(collection, []), collection)
    identities: set[tuple[str, str]] = set()
    for row in rows:
        found = [
            (kind, require_resource_id(str(row[key]), key))
            for key, kind in _SUBJECT_KEYS
            if row.get(key) not in {None, ""}
        ]
        # The first present key is the owning ledger subject; later keys are
        # bounded child dimensions (for example, one TASK stage may also carry
        # an ASSET id).  Different owning subjects across rows still fail
        # closed below instead of being silently aggregated.
        if found:
            identities.add(found[0])
    if len(identities) > 1:
        raise ValidationError("TELEMETRY_SUBJECT_SCOPE_MIXED")
    if identities:
        return next(iter(identities))
    # A request remains a real, immutable accounting subject when the caller
    # is estimating a plan before a task/job identifier has been allocated.
    return "REQUEST", require_resource_id(ctx.request_id, "request_id")


def _request_digest(
    skill: str,
    ctx: RuntimeContext,
    payload: Mapping[str, Any],
) -> str:
    return canonical_digest(
        {
            "schema_version": "telemetry-ledger-request-v1",
            "skill": skill,
            "tenant_id": ctx.tenant_id,
            "project_id": ctx.project_id,
            "actor_id": ctx.actor_id,
            "request_id": ctx.request_id,
            "payload": dict(payload),
            "policy": dict(ctx.policy),
            "capabilities": dict(ctx.capabilities),
        }
    )


def _decode_document(raw: Any, digest: Any, code: str) -> dict[str, Any]:
    if not isinstance(raw, str) or not isinstance(digest, str):
        raise IntegrityError(code)
    try:
        value = json.loads(raw)
    except (TypeError, ValueError) as error:
        raise IntegrityError(code) from error
    if (
        not isinstance(value, dict)
        or canonical_json(value) != raw
        or canonical_digest(value) != digest
    ):
        raise IntegrityError(code)
    return value


def _exact_decimal(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise IntegrityError("COST_LEDGER_DECIMAL_INVALID", details={"field": field}) from error
    if not result.is_finite() or result < 0:
        raise IntegrityError("COST_LEDGER_DECIMAL_INVALID", details={"field": field})
    return result


class TelemetryLifecycleBridge:
    """Persist Skills 22/23 without expanding their public side-effect surface."""

    def __init__(self, store: IntakeStore) -> None:
        if not isinstance(store, IntakeStore):
            raise ValidationError("TELEMETRY_STORE_INVALID")
        self._store = store
        self._validate_schema()

    def _validate_schema(self) -> None:
        with self._store.read_transaction() as connection:
            for table, expected in _REQUIRED_TABLES.items():
                observed = {
                    str(row[1])
                    for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
                }
                if observed != expected:
                    raise IntegrityError("TELEMETRY_LEDGER_SCHEMA_INVALID")

    @staticmethod
    def _context(ctx: RuntimeContext) -> TenantContext:
        return TenantContext(ctx.tenant_id, ctx.project_id, ctx.actor_id)

    def handle(
        self,
        skill_name: str,
        ctx: RuntimeContext,
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if skill_name not in TELEMETRY_SKILLS:
            raise ValidationError("TELEMETRY_SKILL_UNSUPPORTED")
        operation = str(payload.get("operation", "")).strip().lower().replace("-", "_")
        if skill_name == COST_SKILL and operation != "estimate":
            raise ValidationError("PROCESSING_COST_OPERATION_UNSUPPORTED")
        if skill_name == OBSERVABILITY_SKILL and operation != "observe":
            raise ValidationError("OBSERVABILITY_OPERATION_UNSUPPORTED")
        context = self._context(ctx)
        self._store.require(context, self._store.WRITE)
        if ctx.idempotency_key is None:
            raise ValidationError("IDEMPOTENCY_KEY_REQUIRED")
        idempotency_key = require_idempotency_key(ctx.idempotency_key)
        if len(idempotency_key.encode("utf-8")) < 8:
            raise ValidationError("IDEMPOTENCY_KEY_INVALID")
        if skill_name == COST_SKILL:
            return self._estimate(ctx, payload, idempotency_key)
        return self._observe(ctx, payload, idempotency_key)

    def _actuals_binding(
        self,
        ctx: RuntimeContext,
        *,
        subject_kind: str,
        subject_id: str,
        estimate_digest: str,
        domain_reconciled: bool,
    ) -> tuple[str, str | None, int | None]:
        if not domain_reconciled:
            return "PENDING", None, None
        raw = ctx.capabilities.get("verified_provider_actuals_receipt")
        if not isinstance(raw, Mapping):
            return "UNKNOWN", None, None
        digest_value = raw.get("evidence_digest")
        byte_count = raw.get("evidence_byte_count")
        try:
            digest = normalize_sha256(str(digest_value))
        except ValidationError:
            return "UNKNOWN", None, None
        valid = (
            raw.get("verified") is True
            and raw.get("tenant_id") == ctx.tenant_id
            and raw.get("project_id") == ctx.project_id
            and raw.get("subject_kind") == subject_kind
            and raw.get("subject_id") == subject_id
            and raw.get("estimate_digest") == f"sha256:{estimate_digest}"
            and isinstance(byte_count, int)
            and not isinstance(byte_count, bool)
            and 0 <= byte_count <= 1_073_741_824
        )
        return ("RECONCILED", digest, byte_count) if valid else ("UNKNOWN", None, None)

    def _estimate(
        self,
        ctx: RuntimeContext,
        payload: Mapping[str, Any],
        idempotency_key: str,
    ) -> Mapping[str, Any]:
        subject_kind, subject_id = _subject(ctx, payload, collection="stages")
        request_digest = _request_digest(COST_SKILL, ctx, payload)
        with self._store.transaction() as connection:
            prior = connection.execute(
                """SELECT * FROM multimodal_cost_estimates
                   WHERE tenant_id=? AND project_id=? AND idempotency_key=?""",
                (ctx.tenant_id, ctx.project_id, idempotency_key),
            ).fetchone()
            if prior is not None:
                if prior["request_digest"] != request_digest:
                    raise ConflictError("COST_ESTIMATE_IDEMPOTENCY_CONFLICT")
                return _decode_document(
                    prior["estimate_json"], prior["estimate_digest"],
                    "COST_ESTIMATE_LEDGER_CORRUPT",
                )

        result = estimate_processing_cost_eta(_domain_request(ctx, payload))
        if not isinstance(result, Mapping):
            raise IntegrityError("COST_ESTIMATE_RESULT_INVALID")
        state = str(result.get("state", "FAILED"))
        code = str(result.get("code", "PROCESSING_COST_ESTIMATE_FAILED"))
        outputs = result.get("outputs", {})
        if not isinstance(outputs, Mapping):
            raise IntegrityError("COST_ESTIMATE_RESULT_INVALID")
        estimate_body = dict(outputs)
        base_estimate_digest = canonical_digest(estimate_body)
        domain_reconciled = estimate_body.get("provider_actuals_reconciled") is True
        actuals_state, actuals_digest, actuals_bytes = self._actuals_binding(
            ctx,
            subject_kind=subject_kind,
            subject_id=subject_id,
            estimate_digest=base_estimate_digest,
            domain_reconciled=domain_reconciled,
        )
        if state == "SUCCEEDED" and actuals_state != "RECONCILED":
            state = "PARTIAL"
            code = (
                "PROVIDER_ACTUALS_RECONCILIATION_REQUIRED"
                if actuals_state == "UNKNOWN"
                else "PROCESSING_COST_ESTIMATE_RECORDED_ACTUALS_PENDING"
            )
        created_at = utc_now()
        with self._store.transaction() as connection:
            prior = connection.execute(
                """SELECT * FROM multimodal_cost_estimates
                   WHERE tenant_id=? AND project_id=? AND idempotency_key=?""",
                (ctx.tenant_id, ctx.project_id, idempotency_key),
            ).fetchone()
            if prior is not None:
                if prior["request_digest"] != request_digest:
                    raise ConflictError("COST_ESTIMATE_IDEMPOTENCY_CONFLICT")
                return _decode_document(
                    prior["estimate_json"], prior["estimate_digest"],
                    "COST_ESTIMATE_LEDGER_CORRUPT",
                )
            subject = connection.execute(
                """SELECT * FROM multimodal_telemetry_subjects
                   WHERE tenant_id=? AND project_id=? AND subject_kind=? AND subject_id=?""",
                (ctx.tenant_id, ctx.project_id, subject_kind, subject_id),
            ).fetchone()
            sequence = 1 if subject is None else int(subject["latest_estimate_sequence"]) + 1
            enriched = {
                **estimate_body,
                "ledger": {
                    "schema_version": "multimodal-cost-ledger-v1",
                    "subject_kind": subject_kind,
                    "subject_id": subject_id,
                    "estimate_sequence": sequence,
                    "persistence": "DURABLE",
                    "actuals_state": actuals_state,
                    "estimated_and_actual_separated": True,
                    "machine_wall_clock_only": True,
                },
            }
            envelope = _bridge_envelope(state, code, enriched)
            document = canonical_json(envelope)
            document_digest = canonical_digest(envelope)
            if subject is None:
                connection.execute(
                    """INSERT INTO multimodal_telemetry_subjects
                       (tenant_id,project_id,subject_kind,subject_id,version,
                        latest_estimate_sequence,latest_trace_sequence,actuals_state,updated_at)
                       VALUES (?,?,?,?,1,?,0,?,?)""",
                    (
                        ctx.tenant_id, ctx.project_id, subject_kind, subject_id,
                        sequence, actuals_state, created_at,
                    ),
                )
            else:
                connection.execute(
                    """UPDATE multimodal_telemetry_subjects
                       SET version=version+1,latest_estimate_sequence=?,actuals_state=?,updated_at=?
                       WHERE tenant_id=? AND project_id=? AND subject_kind=? AND subject_id=?""",
                    (
                        sequence, actuals_state, created_at, ctx.tenant_id,
                        ctx.project_id, subject_kind, subject_id,
                    ),
                )
            connection.execute(
                """INSERT INTO multimodal_cost_estimates
                   (tenant_id,project_id,subject_kind,subject_id,estimate_sequence,
                    idempotency_key,request_digest,estimate_json,estimate_digest,result_state,
                    result_code,calibration_version,estimated_cost,currency,actuals_state,
                    provider_actuals_digest,provider_actuals_byte_count,trace_id,actor_id,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    ctx.tenant_id, ctx.project_id, subject_kind, subject_id, sequence,
                    idempotency_key, request_digest, document, document_digest, state, code,
                    estimate_body.get("calibration_version"), estimate_body.get("estimated_cost"),
                    estimate_body.get("currency"), actuals_state, actuals_digest, actuals_bytes,
                    ctx.trace_id, ctx.actor_id, created_at,
                ),
            )
            raw_input_stages = _strict_rows(payload.get("stages", []), "stages", maximum=1_000)
            raw_output_stages = _strict_rows(estimate_body.get("stages", []), "stages", maximum=1_000)
            by_id = {str(item.get("stage_id")): item for item in raw_input_stages}
            for stage in raw_output_stages:
                stage_id = require_resource_id(str(stage.get("stage_id", "")), "stage_id")
                source = by_id.get(stage_id, {})
                quantity = _exact_decimal(stage.get("quantity", "0"), "quantity")
                estimated_cost = _exact_decimal(stage.get("cost", "0"), "cost")
                unit_price = Decimal("0") if quantity == 0 else estimated_cost / quantity
                connection.execute(
                    """INSERT INTO multimodal_cost_line_items
                       (tenant_id,project_id,subject_kind,subject_id,estimate_sequence,
                        stage_id,stage,asset_id,provider,file_type,quantity,unit,unit_price,
                        estimated_cost,actual_quantity,actual_cost,currency,
                        actual_evidence_digest,actual_evidence_byte_count,created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        ctx.tenant_id, ctx.project_id, subject_kind, subject_id, sequence,
                        stage_id, str(stage.get("stage", "")), source.get("asset_id"),
                        str(stage.get("provider", "")), str(stage.get("file_type", "")),
                        format(quantity, "f"), str(stage.get("unit", "")),
                        format(unit_price, "f"), format(estimated_cost, "f"), None, None,
                        str(stage.get("currency", "")), actuals_digest, actuals_bytes, created_at,
                    ),
                )
            return envelope

    def _observe(
        self,
        ctx: RuntimeContext,
        payload: Mapping[str, Any],
        idempotency_key: str,
    ) -> Mapping[str, Any]:
        subject_kind, subject_id = _subject(ctx, payload, collection="events")
        request_digest = _request_digest(OBSERVABILITY_SKILL, ctx, payload)
        with self._store.transaction() as connection:
            prior = connection.execute(
                """SELECT * FROM multimodal_telemetry_traces
                   WHERE tenant_id=? AND project_id=? AND idempotency_key=?""",
                (ctx.tenant_id, ctx.project_id, idempotency_key),
            ).fetchone()
            if prior is not None:
                if prior["request_digest"] != request_digest:
                    raise ConflictError("TELEMETRY_TRACE_IDEMPOTENCY_CONFLICT")
                return _decode_document(
                    prior["trace_json"], prior["trace_digest"],
                    "TELEMETRY_TRACE_LEDGER_CORRUPT",
                )

        result = build_multimodal_observability(_domain_request(ctx, payload))
        if not isinstance(result, Mapping):
            raise IntegrityError("TELEMETRY_TRACE_RESULT_INVALID")
        state = str(result.get("state", "FAILED"))
        code = str(result.get("code", "OBSERVABILITY_FAILED"))
        outputs = result.get("outputs", {})
        if not isinstance(outputs, Mapping):
            raise IntegrityError("TELEMETRY_TRACE_RESULT_INVALID")
        safe_events = _strict_rows(outputs.get("events", []), "events")
        missing_stages = outputs.get("missing_stages", [])
        if not isinstance(missing_stages, list):
            raise IntegrityError("TELEMETRY_TRACE_RESULT_INVALID")
        created_at = utc_now()
        with self._store.transaction() as connection:
            prior = connection.execute(
                """SELECT * FROM multimodal_telemetry_traces
                   WHERE tenant_id=? AND project_id=? AND idempotency_key=?""",
                (ctx.tenant_id, ctx.project_id, idempotency_key),
            ).fetchone()
            if prior is not None:
                if prior["request_digest"] != request_digest:
                    raise ConflictError("TELEMETRY_TRACE_IDEMPOTENCY_CONFLICT")
                return _decode_document(
                    prior["trace_json"], prior["trace_digest"],
                    "TELEMETRY_TRACE_LEDGER_CORRUPT",
                )
            subject = connection.execute(
                """SELECT * FROM multimodal_telemetry_subjects
                   WHERE tenant_id=? AND project_id=? AND subject_kind=? AND subject_id=?""",
                (ctx.tenant_id, ctx.project_id, subject_kind, subject_id),
            ).fetchone()
            sequence = 1 if subject is None else int(subject["latest_trace_sequence"]) + 1
            enriched = {
                **dict(outputs),
                "ledger": {
                    "schema_version": "multimodal-telemetry-ledger-v1",
                    "subject_kind": subject_kind,
                    "subject_id": subject_id,
                    "trace_sequence": sequence,
                    "persistence": "DURABLE",
                    "raw_content_persisted": False,
                },
            }
            envelope = _bridge_envelope(state, code, enriched)
            document = canonical_json(envelope)
            document_digest = canonical_digest(envelope)
            if subject is None:
                connection.execute(
                    """INSERT INTO multimodal_telemetry_subjects
                       (tenant_id,project_id,subject_kind,subject_id,version,
                        latest_estimate_sequence,latest_trace_sequence,actuals_state,updated_at)
                       VALUES (?,?,?,?,1,0,?,'NOT_RUN',?)""",
                    (
                        ctx.tenant_id, ctx.project_id, subject_kind, subject_id,
                        sequence, created_at,
                    ),
                )
            else:
                connection.execute(
                    """UPDATE multimodal_telemetry_subjects
                       SET version=version+1,latest_trace_sequence=?,updated_at=?
                       WHERE tenant_id=? AND project_id=? AND subject_kind=? AND subject_id=?""",
                    (
                        sequence, created_at, ctx.tenant_id, ctx.project_id,
                        subject_kind, subject_id,
                    ),
                )
            connection.execute(
                """INSERT INTO multimodal_telemetry_traces
                   (tenant_id,project_id,subject_kind,subject_id,trace_sequence,
                    idempotency_key,request_digest,trace_id,trace_json,trace_digest,
                    result_state,result_code,policy_version,missing_stage_count,event_count,
                    actor_id,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    ctx.tenant_id, ctx.project_id, subject_kind, subject_id, sequence,
                    idempotency_key, request_digest, ctx.trace_id, document, document_digest,
                    state, code, outputs.get("policy_version"), len(missing_stages),
                    len(safe_events), ctx.actor_id, created_at,
                ),
            )
            for event in safe_events:
                labels = event.get("labels", {})
                if not isinstance(labels, Mapping):
                    raise IntegrityError("TELEMETRY_TRACE_RESULT_INVALID")
                event_id = require_resource_id(str(event.get("event_id", "")), "event_id")
                event_document = canonical_json(dict(event))
                event_digest = canonical_digest(dict(event))
                connection.execute(
                    """INSERT INTO multimodal_telemetry_events
                       (tenant_id,project_id,subject_kind,subject_id,trace_sequence,
                        event_id,trace_id,parent_event_id,event_type,stage,provider,file_type,
                        status,error_code,event_json,event_digest,created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        ctx.tenant_id, ctx.project_id, subject_kind, subject_id, sequence,
                        event_id, ctx.trace_id, event.get("parent_event_id"),
                        str(event.get("event_type", "")), labels.get("stage"),
                        labels.get("provider"), labels.get("file_type"), labels.get("status"),
                        labels.get("error_code"), event_document, event_digest, created_at,
                    ),
                )
            return envelope


__all__ = [
    "COST_SKILL",
    "OBSERVABILITY_SKILL",
    "TELEMETRY_SKILLS",
    "TelemetryLifecycleBridge",
]
