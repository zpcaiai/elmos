"""Provider-neutral inference route planning with no prompt or result cache."""

from __future__ import annotations

import math
import time
import uuid
from collections.abc import Callable
from threading import RLock
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .authorizations import AuthorizationVerifier, require_authorization
from .canonical import canonical_digest, canonical_value, require_identifier, validate_digest
from .domain import TenantScope
from .kernel import ExecutionKernel
from .store import FoundryStore


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


class ModelServingGateway:
    """Select from caller-supplied verified candidates; never invoke a model."""

    def __init__(
        self,
        kernel: ExecutionKernel | None = None,
        *,
        route_verifier: AuthorizationVerifier | None = None,
        store: FoundryStore | None = None,
        clock: Callable[[], float] = time.time,
        health_ttl_seconds: float = 60.0,
    ) -> None:
        self.kernel = kernel or ExecutionKernel()
        self._route_verifier = route_verifier
        if (
            isinstance(health_ttl_seconds, bool)
            or not math.isfinite(health_ttl_seconds)
            or not 0 < health_ttl_seconds <= 300
        ):
            raise ValueError("health TTL must be in (0, 300] seconds")
        self.store = store
        self._clock = clock
        self._health_ttl = health_ttl_seconds
        self._epoch = uuid.uuid4().hex
        self._health: dict[tuple[str, str, str], Mapping[str, Any]] = {}
        self._lock = RLock()

    def route_inference(
        self,
        request_digest: str,
        candidates: Sequence[Mapping[str, Any]],
        *,
        max_cost_usd: float,
        max_latency_ms: float,
        verification_receipt_digest: str,
        tenant_scope: TenantScope | None = None,
    ) -> Mapping[str, Any]:
        scope = tenant_scope or self.kernel.current_tenant
        self.kernel.require_context(scope, "foundry.serving.route")
        validate_digest(request_digest, "request_digest")
        validate_digest(verification_receipt_digest, "verification_receipt_digest")
        if (
            not math.isfinite(max_cost_usd)
            or max_cost_usd < 0
            or not math.isfinite(max_latency_ms)
            or max_latency_ms <= 0
        ):
            raise ValueError("route cost and latency limits must be finite and bounded")
        if not candidates or len(candidates) > 64:
            raise ValueError("routing requires 1..64 exact candidates")
        normalized = canonical_value(candidates)
        if not isinstance(normalized, list):
            raise ValueError("route candidates must canonicalize to an array")
        authorization = require_authorization(
            self._route_verifier,
            authorization_type="model-route-verification",
            receipt_digest=verification_receipt_digest,
            request={
                "request_digest": request_digest,
                "candidates": normalized,
                "max_cost_usd": max_cost_usd,
                "max_latency_ms": max_latency_ms,
            },
            scope=scope,
        )
        accepted: list[dict[str, Any]] = []
        for raw in normalized:
            if not isinstance(raw, dict):
                raise ValueError("each route candidate must be an object")
            exact = {
                "candidate_id",
                "provider_instance_id",
                "model_version",
                "artifact_digest",
                "quality_score",
                "estimated_cost_usd",
                "estimated_latency_ms",
                "availability_status",
            }
            if set(raw) != exact:
                raise ValueError("route candidate shape is not exact")
            candidate_id = require_identifier(raw["candidate_id"], "candidate_id")
            validate_digest(raw["artifact_digest"], "candidate.artifact_digest")
            quality = _finite_number(raw["quality_score"], "candidate.quality_score")
            cost = _finite_number(raw["estimated_cost_usd"], "candidate.estimated_cost_usd")
            latency = _finite_number(raw["estimated_latency_ms"], "candidate.estimated_latency_ms")
            if not 0 <= quality <= 1:
                raise ValueError("candidate metrics are outside bounds")
            if cost < 0 or latency <= 0:
                raise ValueError("candidate cost and latency must be positive")
            with self._lock:
                if self.store is None:
                    health = self._health.get((scope.tenant_id, scope.project_id, candidate_id), {})
                else:
                    record = self.store.get_asset(scope, "health", candidate_id)
                    health = {} if record is None else record.payload
                now = self._clock()
                current = (
                    math.isfinite(now)
                    and health.get("epoch") == self._epoch
                    and health.get("observed_at", float("inf"))
                    <= now
                    < health.get("expires_at", float("-inf"))
                )
                local_health = health.get("status", "UNKNOWN") if current else "UNKNOWN"
            if (
                raw["availability_status"] == "VERIFIED_CURRENT"
                and local_health == "AVAILABLE"
                and cost <= max_cost_usd
                and latency <= max_latency_ms
            ):
                accepted.append(dict(raw))
        if not accepted:
            return MappingProxyType(
                {
                    "status": "BLOCKED",
                    "reason": "no verified candidate satisfies the route contract",
                    "request_digest": request_digest,
                    "provider_execution_status": "NOT_RUN",
                    "external_evidence_status": "NOT_RUN",
                    "certification_status": "NOT_CERTIFIED",
                }
            )
        selected = sorted(
            accepted,
            key=lambda item: (
                -float(item["quality_score"]),
                float(item["estimated_cost_usd"]),
                float(item["estimated_latency_ms"]),
                str(item["candidate_id"]),
            ),
        )[0]
        plan = {
            "status": "READY_FOR_EXTERNAL_GATE",
            "selected_candidate": selected,
            "request_digest": request_digest,
            "verification_receipt_digest": verification_receipt_digest,
            "verification_request_digest": authorization.request_digest,
            "tenant_id": scope.tenant_id,
            "project_id": scope.project_id,
            "prompt_stored": False,
            "provider_execution_status": "NOT_RUN",
            "external_evidence_status": "NOT_RUN",
            "certification_status": "NOT_CERTIFIED",
        }
        return MappingProxyType({**plan, "route_plan_digest": canonical_digest(plan)})

    def record_health(
        self,
        candidate_id: str,
        status: str,
        tenant_scope: TenantScope | None = None,
    ) -> None:
        scope = tenant_scope or self.kernel.current_tenant
        self.kernel.require_context(scope, "foundry.serving.health")
        require_identifier(candidate_id, "candidate_id")
        if status not in {"AVAILABLE", "DEGRADED", "UNAVAILABLE", "UNKNOWN"}:
            raise ValueError("candidate health status is invalid")
        with self._lock:
            now = self._clock()
            if not math.isfinite(now):
                raise ValueError("health observation requires a finite clock")
            payload = {
                "tenant_id": scope.tenant_id,
                "project_id": scope.project_id,
                "candidate_id": candidate_id,
                "status": status,
                "observed_at": now,
                "expires_at": now + self._health_ttl,
                "epoch": self._epoch,
            }
            if self.store is not None:
                identity = canonical_digest(
                    {
                        "tenant_id": scope.tenant_id,
                        "project_id": scope.project_id,
                        "candidate_id": candidate_id,
                    }
                )
                record = self.store.get_asset(scope, "health", candidate_id)
                if record is None:
                    record = self.store.create_assets(
                        scope,
                        (
                            (
                                "health",
                                candidate_id,
                                "",
                                identity,
                                payload,
                            ),
                        ),
                    )[0]
                if canonical_digest(payload) != record.payload_digest:
                    self.store.update_asset(
                        scope,
                        "health",
                        candidate_id,
                        record.revision,
                        payload,
                        event_type="model.health.observed",
                        event_payload={"status": status, "expires_at": now + self._health_ttl},
                    )
            else:
                self._health[(scope.tenant_id, scope.project_id, candidate_id)] = payload

    def record_failure(self, model_name: str, tenant_scope: TenantScope | None = None) -> None:
        self.record_health(model_name, "UNAVAILABLE", tenant_scope)

    def record_success(self, model_name: str, tenant_scope: TenantScope | None = None) -> None:
        self.record_health(model_name, "AVAILABLE", tenant_scope)


__all__ = ["ModelServingGateway"]
