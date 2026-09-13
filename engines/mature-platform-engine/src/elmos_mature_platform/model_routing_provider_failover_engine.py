"""Model Routing and Provider Failover Engine (Batch 42 - Skill 1425).

Routes LLM inference workloads across diverse model providers (OpenAI, Anthropic, Gemini, DeepSeek, Airgap),
dynamically tracking endpoint latency, error rates, and managing circuit breakers with auto-failover.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    ModelProviderEndpoint,
    ModelProviderType,
    ModelRoutingDecision,
    ProviderCircuitState,
)


class ModelRoutingProviderFailoverEngine:
    """Intelligent multi-provider model routing, health evaluation, and failover circuit breaker."""

    def __init__(self) -> None:
        self._providers: Dict[str, ModelProviderEndpoint] = {}
        self._decisions: Dict[str, ModelRoutingDecision] = {}

    def register_provider(self, endpoint: ModelProviderEndpoint) -> str:
        """Register a model provider endpoint."""
        if not endpoint.provider_id or not endpoint.model_name:
            raise ValueError("provider_id and model_name are required")

        self._providers[endpoint.provider_id] = endpoint
        return endpoint.provider_id

    def record_call_result(
        self, provider_id: str, success: bool, latency_ms: float = 0.0
    ) -> ModelProviderEndpoint:
        """Record the outcome of a provider invocation, updating circuit breaker and latency."""
        endpoint = self._providers.get(provider_id)
        if not endpoint:
            raise ValueError(f"Provider endpoint not found: {provider_id}")

        if success:
            endpoint.consecutive_failures = 0
            if endpoint.circuit_state == ProviderCircuitState.HALF_OPEN:
                endpoint.circuit_state = ProviderCircuitState.CLOSED
            if latency_ms > 0:
                endpoint.avg_latency_ms = 0.8 * endpoint.avg_latency_ms + 0.2 * latency_ms
        else:
            endpoint.consecutive_failures += 1
            if endpoint.consecutive_failures >= 3:
                endpoint.circuit_state = ProviderCircuitState.OPEN

        return endpoint

    def reset_circuit(self, provider_id: str) -> ModelProviderEndpoint:
        """Transition an OPEN circuit breaker to HALF_OPEN to allow canary health checking."""
        endpoint = self._providers.get(provider_id)
        if not endpoint:
            raise ValueError(f"Provider endpoint not found: {provider_id}")

        endpoint.circuit_state = ProviderCircuitState.HALF_OPEN
        endpoint.consecutive_failures = 0
        return endpoint

    def route_model_call(
        self,
        task_class: str,
        preferred_type: Optional[ModelProviderType] = None,
    ) -> ModelRoutingDecision:
        """Select optimal healthy provider for task with deterministic fallback chain."""
        if not task_class:
            raise ValueError("task_class is required")

        healthy_candidates = [
            p for p in self._providers.values()
            if p.active and p.circuit_state != ProviderCircuitState.OPEN
        ]

        if not healthy_candidates:
            raise RuntimeError("All model provider endpoints are unavailable or in OPEN circuit breaker state")

        if preferred_type:
            matched_preferred = [p for p in healthy_candidates if p.provider_type == preferred_type]
            if matched_preferred:
                healthy_candidates = matched_preferred

        # Sort by priority (asc), then error rate (asc), then cost (asc)
        healthy_candidates.sort(key=lambda p: (p.priority, p.error_rate_pct, p.cost_per_1k_tokens))

        primary = healthy_candidates[0]
        fallbacks = [p.provider_id for p in healthy_candidates[1:]]

        decision = ModelRoutingDecision(
            routing_id=f"route-{uuid.uuid4().hex[:8]}",
            task_class=task_class,
            selected_provider_id=primary.provider_id,
            model_name=primary.model_name,
            fallback_chain=fallbacks,
            routed_at=datetime.now(timezone.utc).isoformat(),
        )

        self._decisions[decision.routing_id] = decision
        return decision

    def get_provider(self, provider_id: str) -> Optional[ModelProviderEndpoint]:
        """Retrieve provider endpoint details."""
        return self._providers.get(provider_id)

    def get_routing_report(self) -> Dict[str, Any]:
        """Generate platform model routing telemetry and circuit breaker status report."""
        total = len(self._providers)
        open_circuits = sum(1 for p in self._providers.values() if p.circuit_state == ProviderCircuitState.OPEN)
        by_type: Dict[str, int] = {}
        for p in self._providers.values():
            t = p.provider_type.value
            by_type[t] = by_type.get(t, 0) + 1

        avg_lat = (
            sum(p.avg_latency_ms for p in self._providers.values()) / total
            if total > 0 else 0.0
        )

        return {
            "total_providers": total,
            "open_circuits_count": open_circuits,
            "providers_by_type": by_type,
            "average_latency_ms": avg_lat,
            "total_routing_decisions": len(self._decisions),
        }
