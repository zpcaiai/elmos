"""K9 durable production-control-plane primitives.

The control plane owns local orchestration state, exact metering, fencing,
idempotency, audit and outbox records.  It never performs provider, SCM,
repository, network or deployment effects directly.  Those effects are
prepared as durable requests and remain ``NOT_RUN`` until an authorized base
harness executor reconciles their outcome.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence

from ._catalog import SOURCE_CAPABILITY_CATALOG
from .canonical import digest_object, freeze_json, utc_now
from .errors import UnknownCapabilityError, ValidationError
from .registry import CAPABILITY_REGISTRY, OperationSpec, resolve_operation
from .store import LeaseGrant, ScopeBinding, SqlitePdhiStore


class OutcomeStatus(StrEnum):
    COMPLETED = "COMPLETED"
    PREPARED = "PREPARED"
    BLOCKED_RECONCILIATION = "BLOCKED_RECONCILIATION"
    NOT_RUN = "NOT_RUN"


@dataclass(frozen=True, slots=True)
class ControlPlaneOutcome:
    operation: str
    status: OutcomeStatus
    result: Mapping[str, Any]
    result_digest: str
    local_evidence_status: str = "LOCAL_EXECUTED_SELF_ATTESTED"
    external_evidence_status: str = "NOT_RUN"
    certification_status: str = "NOT_CERTIFIED"

    @classmethod
    def create(
        cls,
        operation: str,
        status: OutcomeStatus,
        result: Mapping[str, Any],
    ) -> "ControlPlaneOutcome":
        frozen = freeze_json(result)
        if not isinstance(frozen, Mapping):
            raise ValidationError("control-plane result must be an object")
        return cls(
            operation=operation,
            status=status,
            result=frozen,
            result_digest=digest_object(
                {"operation": operation, "status": status.value, "result": frozen},
                domain="k9-control-plane-outcome",
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "status": self.status.value,
            "result": dict(self.result),
            "result_digest": self.result_digest,
            "local_evidence_status": self.local_evidence_status,
            "external_evidence_status": self.external_evidence_status,
            "certification_status": self.certification_status,
        }


@dataclass(frozen=True, slots=True)
class Invocation:
    scope: ScopeBinding
    operation: str
    idempotency_key: str
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.scope, ScopeBinding):
            raise ValidationError("scope must be a trusted ScopeBinding")
        _text(self.operation, "operation")
        _text(self.idempotency_key, "idempotency_key")
        frozen = freeze_json(self.payload)
        if not isinstance(frozen, Mapping):
            raise ValidationError("payload must be an object")
        object.__setattr__(self, "payload", frozen)


@dataclass(frozen=True, slots=True)
class ProgressEstimate:
    completed_work: Decimal
    total_work: Decimal
    elapsed_seconds: Decimal
    retry_probability: Decimal = Decimal("0")
    retry_penalty_seconds: Decimal = Decimal("0")
    repository_scale_factor: Decimal = Decimal("1")

    def __post_init__(self) -> None:
        for name in (
            "completed_work",
            "total_work",
            "elapsed_seconds",
            "retry_probability",
            "retry_penalty_seconds",
            "repository_scale_factor",
        ):
            _decimal(getattr(self, name), name, minimum=Decimal("0"))
        if self.total_work <= 0 or self.completed_work > self.total_work:
            raise ValidationError("work totals are invalid", code="INVALID_PROGRESS")
        if self.retry_probability > 1:
            raise ValidationError("retry_probability must be in [0,1]")
        if self.repository_scale_factor <= 0:
            raise ValidationError("repository_scale_factor must be positive")

    def calculate(self) -> Mapping[str, str]:
        progress = self.completed_work / self.total_work
        if self.completed_work == 0:
            base_remaining = Decimal("Infinity")
        else:
            rate = self.completed_work / max(self.elapsed_seconds, Decimal("0.000001"))
            base_remaining = (self.total_work - self.completed_work) / rate
        if base_remaining.is_finite():
            adjusted = (
                base_remaining * self.repository_scale_factor
                + self.retry_probability * self.retry_penalty_seconds
            )
            eta = format(adjusted.quantize(Decimal("0.001")), "f")
        else:
            eta = "UNKNOWN"
        return MappingProxyType(
            {
                "progress_ratio": format(progress.quantize(Decimal("0.000001")), "f"),
                "eta_seconds": eta,
                "confidence": "LOW" if self.completed_work == 0 else "MODELED_NOT_CERTIFIED",
            }
        )


@dataclass(frozen=True, slots=True)
class QuotaPolicy:
    maximum_concurrent_jobs: int
    maximum_daily_cost: Decimal
    currency: str
    maximum_tokens: int
    policy_revision: str

    def __post_init__(self) -> None:
        for name in ("maximum_concurrent_jobs", "maximum_tokens"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValidationError(f"{name} must be positive")
        _decimal(self.maximum_daily_cost, "maximum_daily_cost", minimum=Decimal("0"))
        if len(self.currency) != 3 or not self.currency.isalpha() or self.currency != self.currency.upper():
            raise ValidationError("currency must be uppercase ISO-like code")
        _sha256(self.policy_revision, "policy_revision")

    def decide(
        self,
        *,
        active_jobs: int,
        current_cost: Decimal,
        current_tokens: int,
        requested_cost: Decimal,
        requested_tokens: int,
    ) -> Mapping[str, Any]:
        for name, value in (("active_jobs", active_jobs), ("current_tokens", current_tokens), ("requested_tokens", requested_tokens)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValidationError(f"{name} must be non-negative")
        _decimal(current_cost, "current_cost", minimum=Decimal("0"))
        _decimal(requested_cost, "requested_cost", minimum=Decimal("0"))
        reasons: list[str] = []
        if active_jobs >= self.maximum_concurrent_jobs:
            reasons.append("CONCURRENT_JOB_QUOTA")
        if current_cost + requested_cost > self.maximum_daily_cost:
            reasons.append("DAILY_COST_QUOTA")
        if current_tokens + requested_tokens > self.maximum_tokens:
            reasons.append("TOKEN_QUOTA")
        return MappingProxyType(
            {
                "decision": "DENY" if reasons else "ALLOW",
                "reasons": tuple(reasons),
                "policy_revision": self.policy_revision,
            }
        )


def _text(value: object, name: str, *, maximum: int = 1024) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValidationError(f"{name} is required and must be canonical text")
    if len(value) > maximum or any(ord(char) < 0x20 for char in value):
        raise ValidationError(f"{name} is invalid")
    return value


def _int(value: object, name: str, *, minimum: int = 0, maximum: int = 2**63 - 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum or value > maximum:
        raise ValidationError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return value


def _decimal(value: object, name: str, *, minimum: Decimal | None = None) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise ValidationError(f"{name} must use exact decimal input")
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValidationError(f"{name} is not a decimal") from exc
    if not parsed.is_finite() or (minimum is not None and parsed < minimum):
        raise ValidationError(f"{name} is outside the permitted range")
    return parsed


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError(f"{name} must be an object")
    frozen = freeze_json(value)
    if not isinstance(frozen, Mapping):
        raise AssertionError("frozen mapping type drift")
    return frozen


def _sha256(value: object, name: str) -> str:
    checked = _text(value, name)
    raw = checked.removeprefix("sha256:")
    if len(raw) != 64 or raw.lower() != raw:
        raise ValidationError(f"{name} must be a canonical SHA-256 digest")
    try:
        bytes.fromhex(raw)
    except ValueError as exc:
        raise ValidationError(f"{name} must be a canonical SHA-256 digest") from exc
    return "sha256:" + raw


def _lease(payload: Mapping[str, Any]) -> LeaseGrant:
    expires = payload.get("lease_expires_at")
    if not isinstance(expires, str):
        raise ValidationError("lease_expires_at is required")
    try:
        parsed = datetime.fromisoformat(expires.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError("lease_expires_at is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValidationError("lease_expires_at must be timezone-aware")
    return LeaseGrant(
        resource_id=_text(payload.get("lease_resource"), "lease_resource"),
        owner_id=_text(payload.get("lease_owner"), "lease_owner"),
        generation=_int(payload.get("lease_generation"), "lease_generation", minimum=1),
        token=_text(payload.get("lease_token"), "lease_token", maximum=4096),
        expires_at=parsed.astimezone(UTC),
    )


Handler = Callable[[ScopeBinding, str, Mapping[str, Any]], ControlPlaneOutcome]


class ProductionControlPlane:
    """Exact K9 dispatcher backed by durable state and fail-closed effects."""

    def __init__(self, store: SqlitePdhiStore, *, version: str = "1.0.0") -> None:
        if not isinstance(store, SqlitePdhiStore):
            raise ValidationError("store must implement the PDHI durable-store contract")
        self._store = store
        self._version = _text(version, "version")
        handlers: dict[str, Handler] = {}
        self._bind(handlers, _JOB_OPERATIONS, self._job)
        self._bind(handlers, _RECOVERY_OPERATIONS, self._recovery)
        self._bind(handlers, _SESSION_OPERATIONS, self._session)
        self._bind(handlers, _ISOLATION_OPERATIONS, self._isolation)
        self._bind(handlers, _LEASE_OPERATIONS, self._lease_operation)
        self._bind(handlers, _EFFECT_OPERATIONS, self._effect)
        self._bind(handlers, _OPERATOR_OPERATIONS, self._operator)
        self._bind(handlers, _METER_OPERATIONS, self._meter)
        self._bind(handlers, _ROLLUP_OPERATIONS, self._rollup)
        self._bind(handlers, _ESTIMATE_OPERATIONS, self._estimate)
        self._bind(handlers, _OBSERVABILITY_OPERATIONS, self._observability)
        self._bind(handlers, _CAPACITY_OPERATIONS, self._capacity)
        expected = set(SOURCE_CAPABILITY_CATALOG["K9"])
        if set(handlers) != expected:
            raise RuntimeError(
                f"K9 handler coverage drift: missing={sorted(expected-set(handlers))}, extra={sorted(set(handlers)-expected)}"
            )
        self._handlers: Mapping[str, Handler] = MappingProxyType(handlers)

    @staticmethod
    def _bind(target: dict[str, Handler], names: Sequence[str], handler: Handler) -> None:
        for name in names:
            if name in target:
                raise RuntimeError(f"duplicate K9 runtime binding: {name}")
            target[name] = handler

    @property
    def operations(self) -> tuple[str, ...]:
        return tuple(self._handlers)

    def invoke(self, invocation: Invocation) -> ControlPlaneOutcome:
        try:
            resolved = resolve_operation(invocation.operation, owner="K9" if invocation.operation == "steer-agent" else None)
        except Exception as exc:
            raise UnknownCapabilityError(
                "operation is not an exact K9 capability",
                code="UNKNOWN_K9_CAPABILITY",
                details={"operation": invocation.operation},
            ) from exc
        if resolved.operation.canonical_owner != "K9":
            raise UnknownCapabilityError(
                "operation is not canonically owned by K9",
                code="WRONG_KERNEL_CAPABILITY",
                details={"operation": invocation.operation, "owner": resolved.operation.canonical_owner},
            )
        handler = self._handlers.get(invocation.operation)
        if handler is None:
            raise UnknownCapabilityError("K9 capability has no runtime binding", code="UNBOUND_K9_CAPABILITY")
        reservation = self._store.reserve_idempotency(
            invocation.scope,
            operation=f"K9:{invocation.operation}",
            idempotency_key=invocation.idempotency_key,
            request=dict(invocation.payload),
        )
        if not reservation.created:
            if reservation.response is not None:
                return ControlPlaneOutcome.create(
                    invocation.operation,
                    OutcomeStatus.COMPLETED,
                    {**reservation.response, "idempotent_replay": True},
                )
            return ControlPlaneOutcome.create(
                invocation.operation,
                OutcomeStatus.BLOCKED_RECONCILIATION,
                {
                    "request_digest": reservation.request_digest,
                    "reason": "prior attempt has no durable terminal response",
                    "automatic_retry": False,
                },
            )
        outcome = handler(invocation.scope, invocation.operation, invocation.payload)
        self._store.complete_idempotency(
            invocation.scope,
            operation=f"K9:{invocation.operation}",
            idempotency_key=invocation.idempotency_key,
            request_digest=reservation.request_digest,
            response=outcome.to_dict(),
        )
        return outcome

    def _job(self, scope: ScopeBinding, operation: str, payload: Mapping[str, Any]) -> ControlPlaneOutcome:
        if operation == "durable-job":
            job = self._store.create_job(
                scope,
                job_id=_text(payload.get("job_id"), "job_id"),
                input_revision=_text(payload.get("input_revision"), "input_revision"),
                payload=_mapping(payload.get("job"), "job"),
            )
            return ControlPlaneOutcome.create(operation, OutcomeStatus.COMPLETED, job)
        job_id = _text(payload.get("job_id"), "job_id")
        job = self._store.get_job(scope, job_id)
        target_by_operation = {
            "durable-phase": _text(payload.get("target_state"), "target_state").upper(),
            "pause-job": "PAUSED",
            "resume-job": _text(payload.get("resume_state"), "resume_state").upper(),
            "cancel-job": "CANCELLED",
            "retry-phase": "RETRYING",
            "rollback-transaction": "ROLLING_BACK",
        }
        target = target_by_operation[operation]
        updated = self._store.transition_job(
            scope,
            job_id=job_id,
            expected_version=_int(payload.get("expected_version"), "expected_version", minimum=1),
            target_state=target,
            reason=_text(payload.get("reason"), "reason", maximum=8192),
        )
        return ControlPlaneOutcome.create(operation, OutcomeStatus.COMPLETED, updated)

    def _recovery(self, scope: ScopeBinding, operation: str, payload: Mapping[str, Any]) -> ControlPlaneOutcome:
        job_id = _text(payload.get("job_id"), "job_id")
        checkpoint = _sha256(payload.get("checkpoint_digest"), "checkpoint_digest")
        source_revision = _sha256(payload.get("source_revision"), "source_revision")
        effect_states = _mapping(payload.get("effect_states", {}), "effect_states")
        unresolved = tuple(sorted(key for key, value in effect_states.items() if value in {"UNKNOWN", "STARTED", "PREPARED"}))
        event_digest = self._store.record_control_event(
            scope,
            operation=f"recovery.{operation}",
            aggregate_id=job_id,
            decision="BLOCK" if unresolved else "ALLOW_PREPARE",
            detail={
                "checkpoint_digest": checkpoint,
                "source_revision": source_revision,
                "unresolved_effects": unresolved,
                "replay_status": "NOT_RUN",
            },
            topic="pdhi.recovery.requested",
        )
        status = OutcomeStatus.BLOCKED_RECONCILIATION if unresolved else OutcomeStatus.PREPARED
        return ControlPlaneOutcome.create(
            operation,
            status,
            {
                "job_id": job_id,
                "event_digest": event_digest,
                "unresolved_effects": unresolved,
                "replay_status": "NOT_RUN",
            },
        )

    def _session(self, scope: ScopeBinding, operation: str, payload: Mapping[str, Any]) -> ControlPlaneOutcome:
        command = {
            "provider-session-rotation": "ROTATE",
            "provider-stream-fresh-reset": "RESET",
            "session-fork": "REGISTER",
            "job-fork": "REGISTER",
            "fork-job": "REGISTER",
        }[operation]
        source_session = payload.get("source_session_id")
        result = self._store.mutate_provider_session(
            scope,
            job_id=_text(payload.get("target_job_id", payload.get("job_id")), "job_id"),
            session_id=_text(payload.get("target_session_id", payload.get("session_id")), "session_id"),
            provider_id=_text(payload.get("provider_id"), "provider_id"),
            command=command,
            expected_generation=_int(payload.get("expected_generation", 0), "expected_generation"),
            external_ref_digest=payload.get("external_ref_digest"),
            checkpoint_digest=payload.get("checkpoint_digest"),
        )
        if source_session is not None:
            result = {**result, "source_session_id": _text(source_session, "source_session_id")}
        return ControlPlaneOutcome.create(operation, OutcomeStatus.PREPARED, result)

    def _isolation(self, scope: ScopeBinding, operation: str, payload: Mapping[str, Any]) -> ControlPlaneOutcome:
        requested_tenant = payload.get("tenant_id", scope.tenant_id)
        requested_project = payload.get("project_id", scope.project_id)
        if requested_tenant != scope.tenant_id or requested_project != scope.project_id:
            raise ValidationError("requested resource is outside authenticated scope", code="SCOPE_MISMATCH")
        result: dict[str, Any] = {
            "tenant_id": scope.tenant_id,
            "project_id": scope.project_id,
            "authority_revision": scope.authority_revision,
            "environment_revision": scope.environment_revision,
            "decision": "ALLOW_EXACT_SCOPE_ONLY",
        }
        if operation == "workspace-ownership":
            grant = _lease(payload)
            self._store.verify_lease(scope, grant)
            result.update({"workspace_resource": grant.resource_id, "fence_generation": grant.generation})
        event_digest = self._store.record_control_event(
            scope,
            operation=f"scope.{operation}",
            aggregate_id=scope.project_id,
            decision="ALLOW",
            detail=result,
        )
        return ControlPlaneOutcome.create(operation, OutcomeStatus.COMPLETED, {**result, "event_digest": event_digest})

    def _lease_operation(self, scope: ScopeBinding, operation: str, payload: Mapping[str, Any]) -> ControlPlaneOutcome:
        if operation in {"lease-management", "lease-expiry", "fencing-token"} and payload.get("action") == "ACQUIRE":
            grant = self._store.acquire_lease(
                scope,
                resource_id=_text(payload.get("resource_id"), "resource_id"),
                owner_id=_text(payload.get("owner_id"), "owner_id"),
                ttl=timedelta(seconds=_int(payload.get("ttl_seconds"), "ttl_seconds", minimum=1, maximum=900)),
            )
            return ControlPlaneOutcome.create(
                operation,
                OutcomeStatus.COMPLETED,
                {
                    "resource_id": grant.resource_id,
                    "owner_id": grant.owner_id,
                    "generation": grant.generation,
                    "lease_token": grant.token,
                    "expires_at": grant.expires_at.isoformat().replace("+00:00", "Z"),
                },
            )
        grant = _lease(payload)
        if payload.get("action") == "REVOKE":
            self._store.revoke_lease(scope, grant)
            action = "REVOKED"
        else:
            self._store.verify_lease(scope, grant)
            action = "VERIFIED"
        return ControlPlaneOutcome.create(
            operation,
            OutcomeStatus.COMPLETED,
            {"resource_id": grant.resource_id, "generation": grant.generation, "lease_status": action},
        )

    def _effect(self, scope: ScopeBinding, operation: str, payload: Mapping[str, Any]) -> ControlPlaneOutcome:
        if operation == "side-effect-outbox" and payload.get("action") == "CLAIM":
            claims = self._store.claim_outbox(
                scope,
                worker_id=_text(payload.get("worker_id"), "worker_id"),
                limit=_int(payload.get("limit", 32), "limit", minimum=1, maximum=256),
            )
            return ControlPlaneOutcome.create(
                operation,
                OutcomeStatus.PREPARED,
                {
                    "claims": tuple(
                        {
                            "event_id": item.event_id,
                            "topic": item.topic,
                            "aggregate_id": item.aggregate_id,
                            "payload": item.payload,
                            "delivery_token": item.delivery_token,
                            "attempts": item.attempts,
                        }
                        for item in claims
                    ),
                    "delivery_status": "NOT_RUN",
                },
            )
        record = self._store.prepare_effect(
            scope,
            effect_id=_text(payload.get("effect_id"), "effect_id"),
            job_id=_text(payload.get("job_id"), "job_id"),
            operation=_text(payload.get("effect_operation"), "effect_operation"),
            idempotency_key=_text(payload.get("effect_idempotency_key"), "effect_idempotency_key"),
            request=_mapping(payload.get("request"), "request"),
            lease=_lease(payload),
        )
        return ControlPlaneOutcome.create(
            operation,
            OutcomeStatus.PREPARED,
            {
                "effect_id": record.effect_id,
                "state": record.state,
                "request_digest": record.request_digest,
                "version": record.version,
                "provider_effect_status": "NOT_RUN",
            },
        )

    def _operator(self, scope: ScopeBinding, operation: str, payload: Mapping[str, Any]) -> ControlPlaneOutcome:
        command = {
            "steer-agent": "STEER",
            "kill-agent": "KILL",
            "revive-agent": "REVIVE",
        }.get(operation, _text(payload.get("command", "STEER"), "command").upper())
        result = self._store.control_agent(
            scope,
            job_id=_text(payload.get("job_id"), "job_id"),
            agent_id=_text(payload.get("agent_id"), "agent_id"),
            command=command,
            expected_generation=_int(payload.get("expected_generation"), "expected_generation"),
            detail=_mapping(payload.get("detail", {}), "detail"),
        )
        return ControlPlaneOutcome.create(operation, OutcomeStatus.PREPARED, {**result, "agent_host_effect": "NOT_RUN"})

    def _meter(self, scope: ScopeBinding, operation: str, payload: Mapping[str, Any]) -> ControlPlaneOutcome:
        definitions = {
            "token-meter": ("tokens", "token", None),
            "model-cost-meter": ("model_cost", "money", payload.get("currency")),
            "tool-cost-meter": ("tool_cost", "money", payload.get("currency")),
            "compute-meter": ("compute", _text(payload.get("unit", "cpu-second"), "unit"), None),
            "storage-meter": ("storage", _text(payload.get("unit", "byte-second"), "unit"), None),
            "revenue-meter": ("revenue", "money", payload.get("currency")),
        }
        metric_name, unit, currency = definitions[operation]
        value = _decimal(payload.get("value"), "value", minimum=Decimal("0"))
        self._store.append_metric(
            scope,
            job_id=_text(payload.get("job_id"), "job_id"),
            metric_name=metric_name,
            value=value,
            unit=unit,
            grain=_text(payload.get("grain"), "grain"),
            definition_version=_text(payload.get("definition_version"), "definition_version"),
            currency=None if currency is None else _text(currency, "currency").upper(),
        )
        return ControlPlaneOutcome.create(
            operation,
            OutcomeStatus.COMPLETED,
            {"metric_name": metric_name, "value": format(value, "f"), "unit": unit, "currency": currency},
        )

    def _rollup(self, scope: ScopeBinding, operation: str, payload: Mapping[str, Any]) -> ControlPlaneOutcome:
        job_id = None if operation == "tenant-cost-rollup" else payload.get("job_id")
        rows = self._store.metric_rollup(
            scope,
            job_id=None if job_id is None else _text(job_id, "job_id"),
            metric_names=("model_cost", "tool_cost", "revenue"),
        )
        result: dict[str, Any] = {"rollups": rows, "scope": operation.removesuffix("-cost-rollup")}
        if operation == "margin-estimator":
            by_currency: dict[str, dict[str, Decimal]] = {}
            for row in rows:
                currency = row["currency"]
                if currency is None:
                    continue
                group = by_currency.setdefault(currency, {"cost": Decimal("0"), "revenue": Decimal("0")})
                if row["metric_name"] == "revenue":
                    group["revenue"] += Decimal(row["value"])
                else:
                    group["cost"] += Decimal(row["value"])
            result["margins"] = tuple(
                {
                    "currency": currency,
                    "revenue": format(values["revenue"], "f"),
                    "cost": format(values["cost"], "f"),
                    "margin": format(values["revenue"] - values["cost"], "f"),
                    "status": "MODELED_NOT_ACCOUNTING_CERTIFIED",
                }
                for currency, values in sorted(by_currency.items())
            )
        return ControlPlaneOutcome.create(operation, OutcomeStatus.COMPLETED, result)

    def _estimate(self, scope: ScopeBinding, operation: str, payload: Mapping[str, Any]) -> ControlPlaneOutcome:
        estimate = ProgressEstimate(
            completed_work=_decimal(payload.get("completed_work"), "completed_work", minimum=Decimal("0")),
            total_work=_decimal(payload.get("total_work"), "total_work", minimum=Decimal("0")),
            elapsed_seconds=_decimal(payload.get("elapsed_seconds"), "elapsed_seconds", minimum=Decimal("0")),
            retry_probability=_decimal(payload.get("retry_probability", "0"), "retry_probability", minimum=Decimal("0")),
            retry_penalty_seconds=_decimal(payload.get("retry_penalty_seconds", "0"), "retry_penalty_seconds", minimum=Decimal("0")),
            repository_scale_factor=_decimal(payload.get("repository_scale_factor", "1"), "repository_scale_factor", minimum=Decimal("0")),
        )
        calculated: dict[str, Any] = dict(estimate.calculate())
        calculated.update({"estimator": operation, "critical_path_digest": payload.get("critical_path_digest")})
        event_digest = self._store.record_control_event(
            scope,
            operation=f"estimate.{operation}",
            aggregate_id=_text(payload.get("job_id"), "job_id"),
            decision="OBSERVE",
            detail=calculated,
        )
        return ControlPlaneOutcome.create(operation, OutcomeStatus.COMPLETED, {**calculated, "event_digest": event_digest})

    def _observability(self, scope: ScopeBinding, operation: str, payload: Mapping[str, Any]) -> ControlPlaneOutcome:
        if operation == "health-endpoint":
            result = {"status": "UP", "component": "pdhi-control-plane", "time": utc_now()}
        elif operation == "liveness":
            result = {"status": "ALIVE", "process_check": "PASS"}
        elif operation == "readiness":
            result = dict(self._store.readiness())
            if not result.get("production_multi_replica"):
                result["production_status"] = "NOT_READY_FOR_MULTI_REPLICA"
        elif operation == "version-endpoint":
            result = {
                "version": self._version,
                "catalog_digest": digest_object(tuple(SOURCE_CAPABILITY_CATALOG["K9"]), domain="k9-catalog"),
            }
        elif operation in {"trace-correlation", "structured-events", "evidence-provenance", "artifact-lineage"}:
            correlation_id = _text(payload.get("correlation_id"), "correlation_id")
            detail = _mapping(payload.get("detail"), "detail")
            event_digest = self._store.record_control_event(
                scope,
                operation=f"observe.{operation}",
                aggregate_id=correlation_id,
                decision="OBSERVE",
                detail=detail,
                topic="pdhi.observation.recorded",
            )
            result = {"correlation_id": correlation_id, "event_digest": event_digest}
        elif operation == "audit-log":
            result = {
                "records": self._store.audit_records(
                    scope,
                    after_id=_int(payload.get("after_id", 0), "after_id"),
                    limit=_int(payload.get("limit", 100), "limit", minimum=1, maximum=1000),
                )
            }
        elif operation == "metrics-endpoint":
            result = {
                "rollups": self._store.metric_rollup(
                    scope,
                    job_id=payload.get("job_id"),
                    metric_names=tuple(payload.get("metric_names", ())),
                )
            }
        else:
            detail = _mapping(payload.get("detail", {}), "detail")
            event_digest = self._store.record_control_event(
                scope,
                operation=f"monitor.{operation}",
                aggregate_id=_text(payload.get("service_id", "pdhi"), "service_id"),
                decision="OBSERVE",
                detail={**detail, "status": "LOCAL_OBSERVATION_ONLY"},
            )
            result = {"event_digest": event_digest, "status": "LOCAL_OBSERVATION_ONLY"}
        return ControlPlaneOutcome.create(operation, OutcomeStatus.COMPLETED, result)

    def _capacity(self, scope: ScopeBinding, operation: str, payload: Mapping[str, Any]) -> ControlPlaneOutcome:
        if operation == "quota-governor":
            policy = QuotaPolicy(
                maximum_concurrent_jobs=_int(payload.get("maximum_concurrent_jobs"), "maximum_concurrent_jobs", minimum=1),
                maximum_daily_cost=_decimal(payload.get("maximum_daily_cost"), "maximum_daily_cost", minimum=Decimal("0")),
                currency=_text(payload.get("currency"), "currency").upper(),
                maximum_tokens=_int(payload.get("maximum_tokens"), "maximum_tokens", minimum=1),
                policy_revision=_sha256(payload.get("policy_revision"), "policy_revision"),
            )
            result = policy.decide(
                active_jobs=_int(payload.get("active_jobs"), "active_jobs"),
                current_cost=_decimal(payload.get("current_cost"), "current_cost", minimum=Decimal("0")),
                current_tokens=_int(payload.get("current_tokens"), "current_tokens"),
                requested_cost=_decimal(payload.get("requested_cost"), "requested_cost", minimum=Decimal("0")),
                requested_tokens=_int(payload.get("requested_tokens"), "requested_tokens"),
            )
        else:
            available = _decimal(payload.get("available_units"), "available_units", minimum=Decimal("0"))
            demanded = _decimal(payload.get("demanded_units"), "demanded_units", minimum=Decimal("0"))
            reserve = _decimal(payload.get("reserve_units", "0"), "reserve_units", minimum=Decimal("0"))
            allocatable = max(Decimal("0"), available - reserve)
            result = MappingProxyType(
                {
                    "decision": "SUFFICIENT" if allocatable >= demanded else "INSUFFICIENT",
                    "available_units": format(available, "f"),
                    "allocatable_units": format(allocatable, "f"),
                    "demanded_units": format(demanded, "f"),
                    "shortfall_units": format(max(Decimal("0"), demanded - allocatable), "f"),
                    "status": "MODELED_NOT_PROVIDER_VERIFIED",
                }
            )
        event_digest = self._store.record_control_event(
            scope,
            operation=f"capacity.{operation}",
            aggregate_id=scope.project_id,
            decision=str(result["decision"]),
            detail=result,
        )
        return ControlPlaneOutcome.create(operation, OutcomeStatus.COMPLETED, {**result, "event_digest": event_digest})


_JOB_OPERATIONS = (
    "durable-job",
    "durable-phase",
    "pause-job",
    "resume-job",
    "cancel-job",
    "retry-phase",
    "rollback-transaction",
)
_RECOVERY_OPERATIONS = (
    "durable-agent-state",
    "checkpoint-resume",
    "crash-recovery",
    "replay-safe-recovery",
    "replay-scenario",
)
_SESSION_OPERATIONS = (
    "provider-session-rotation",
    "provider-stream-fresh-reset",
    "session-fork",
    "job-fork",
    "fork-job",
)
_ISOLATION_OPERATIONS = ("tenant-isolation", "project-isolation", "workspace-ownership")
_LEASE_OPERATIONS = (
    "lease-management",
    "lease-expiry",
    "fencing-token",
    "stale-worker-rejection",
    "distributed-lock-policy",
)
_EFFECT_OPERATIONS = ("durable-tool-effect", "idempotency-key", "side-effect-outbox")
_OPERATOR_OPERATIONS = ("steer-agent", "kill-agent", "revive-agent")
_METER_OPERATIONS = (
    "token-meter",
    "model-cost-meter",
    "tool-cost-meter",
    "compute-meter",
    "storage-meter",
    "revenue-meter",
)
_ROLLUP_OPERATIONS = ("project-cost-rollup", "tenant-cost-rollup", "margin-estimator")
_ESTIMATE_OPERATIONS = (
    "progress-model",
    "phase-completion-estimator",
    "wall-clock-eta",
    "critical-path-estimator",
    "retry-risk-adjustment",
    "repository-size-adjustment",
)
_OBSERVABILITY_OPERATIONS = (
    "trace-correlation",
    "structured-events",
    "audit-log",
    "evidence-provenance",
    "artifact-lineage",
    "metrics-endpoint",
    "health-endpoint",
    "version-endpoint",
    "readiness",
    "liveness",
    "sla-monitor",
)
_CAPACITY_OPERATIONS = ("capacity-planner", "quota-governor")


@dataclass(frozen=True, slots=True)
class CapabilityBinding:
    operation: str
    handler: str
    external_effect: bool


_GROUPS = (
    (_JOB_OPERATIONS, "ProductionControlPlane._job", False),
    (_RECOVERY_OPERATIONS, "ProductionControlPlane._recovery", True),
    (_SESSION_OPERATIONS, "ProductionControlPlane._session", True),
    (_ISOLATION_OPERATIONS, "ProductionControlPlane._isolation", False),
    (_LEASE_OPERATIONS, "ProductionControlPlane._lease_operation", False),
    (_EFFECT_OPERATIONS, "ProductionControlPlane._effect", True),
    (_OPERATOR_OPERATIONS, "ProductionControlPlane._operator", True),
    (_METER_OPERATIONS, "ProductionControlPlane._meter", False),
    (_ROLLUP_OPERATIONS, "ProductionControlPlane._rollup", False),
    (_ESTIMATE_OPERATIONS, "ProductionControlPlane._estimate", False),
    (_OBSERVABILITY_OPERATIONS, "ProductionControlPlane._observability", False),
    (_CAPACITY_OPERATIONS, "ProductionControlPlane._capacity", False),
)
K9_OPERATION_BINDINGS: Mapping[str, CapabilityBinding] = MappingProxyType(
    {
        operation: CapabilityBinding(operation, handler, external)
        for operations, handler, external in _GROUPS
        for operation in operations
    }
)
K9_OPERATION_SPECS: Mapping[str, OperationSpec] = MappingProxyType(
    {name: CAPABILITY_REGISTRY[name] for name in SOURCE_CAPABILITY_CATALOG["K9"]}
)

if len(K9_OPERATION_BINDINGS) != 59 or set(K9_OPERATION_BINDINGS) != set(SOURCE_CAPABILITY_CATALOG["K9"]):
    raise RuntimeError("K9 exact operation bindings drifted")
if any(spec.canonical_owner != "K9" for spec in K9_OPERATION_SPECS.values()):
    raise RuntimeError("K9 operation registry ownership drifted")


__all__ = [
    "CapabilityBinding",
    "ControlPlaneOutcome",
    "Invocation",
    "K9_OPERATION_BINDINGS",
    "K9_OPERATION_SPECS",
    "OutcomeStatus",
    "ProductionControlPlane",
    "ProgressEstimate",
    "QuotaPolicy",
]
