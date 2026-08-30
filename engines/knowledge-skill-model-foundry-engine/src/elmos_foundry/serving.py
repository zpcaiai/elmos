"""Provider-neutral inference route planning with no prompt or result cache."""

from __future__ import annotations

import math
from threading import RLock
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .authorizations import AuthorizationVerifier, require_authorization
from .canonical import canonical_digest, canonical_value, validate_digest
from .domain import TenantScope
from .kernel import ExecutionKernel


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
    ) -> None:
        self.kernel = kernel or ExecutionKernel()
        self._route_verifier = route_verifier
        self._health: dict[tuple[str, str, str], str] = {}
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
            validate_digest(raw["artifact_digest"], "candidate.artifact_digest")
            quality = _finite_number(raw["quality_score"], "candidate.quality_score")
            cost = _finite_number(raw["estimated_cost_usd"], "candidate.estimated_cost_usd")
            latency = _finite_number(
                raw["estimated_latency_ms"], "candidate.estimated_latency_ms"
            )
            if not 0 <= quality <= 1:
                raise ValueError("candidate metrics are outside bounds")
            if cost < 0 or latency <= 0:
                raise ValueError("candidate cost and latency must be positive")
            with self._lock:
                local_health = self._health.get(
                    (scope.tenant_id, scope.project_id, str(raw["candidate_id"])),
                    "UNKNOWN",
                )
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
        if status not in {"AVAILABLE", "DEGRADED", "UNAVAILABLE", "UNKNOWN"}:
            raise ValueError("candidate health status is invalid")
        with self._lock:
            self._health[(scope.tenant_id, scope.project_id, candidate_id)] = status

    def record_failure(
        self, model_name: str, tenant_scope: TenantScope | None = None
    ) -> None:
        self.record_health(model_name, "UNAVAILABLE", tenant_scope)

    def record_success(
        self, model_name: str, tenant_scope: TenantScope | None = None
    ) -> None:
        self.record_health(model_name, "AVAILABLE", tenant_scope)


__all__ = ["ModelServingGateway"]
