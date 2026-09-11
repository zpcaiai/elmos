"""Provider Resource Routing Engine (Batch 44 - Skill 1470).

Dynamically routes model inference, runner execution, and cloud resources across providers
balancing cost, latency, real-time load, and failover guarantees under strict FinOps policies.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    ProviderResourceProfile,
    ResourceRoutingDecision,
    RoutingStrategy,
)


class ProviderResourceRoutingEngine:
    """FinOps resource router for multi-provider models, runners, and infrastructure."""

    def __init__(self) -> None:
        self._resources: Dict[str, ProviderResourceProfile] = {}
        self._decisions: List[ResourceRoutingDecision] = []

    def register_provider_resource(self, profile: ProviderResourceProfile) -> str:
        """Register a provider compute/model resource candidate."""
        if not profile.provider_name or not profile.resource_type:
            raise ValueError("provider_name and resource_type are required")
        if profile.unit_cost_usd < 0:
            raise ValueError("unit_cost_usd cannot be negative")

        if not profile.resource_id:
            profile.resource_id = f"res-{uuid.uuid4().hex[:8]}"

        self._resources[profile.resource_id] = profile
        return profile.resource_id

    def update_availability(
        self, resource_id: str, is_available: bool, current_load_pct: Optional[float] = None
    ) -> ProviderResourceProfile:
        """Update live availability and load metrics for a provider resource."""
        res = self._resources.get(resource_id)
        if not res:
            raise ValueError(f"Resource not found: {resource_id}")

        res.is_available = is_available
        if current_load_pct is not None:
            if not (0.0 <= current_load_pct <= 100.0):
                raise ValueError("current_load_pct must be between 0.0 and 100.0")
            res.current_load_pct = current_load_pct

        return res

    def route_request(
        self,
        workload_type: str,
        required_capacity: float = 1.0,
        strategy: RoutingStrategy = RoutingStrategy.LOWEST_COST,
    ) -> ResourceRoutingDecision:
        """Select best matching provider resource based on specified routing strategy."""
        if not workload_type:
            raise ValueError("workload_type is required")

        candidates = [
            r for r in self._resources.values()
            if r.resource_type == workload_type and r.is_available and r.current_load_pct < 100.0
        ]

        if not candidates:
            raise RuntimeError(f"No available provider resources found for workload '{workload_type}'")

        if strategy == RoutingStrategy.LOWEST_COST:
            selected = min(candidates, key=lambda c: (c.unit_cost_usd, c.current_load_pct))
            reason = f"Selected for lowest unit cost (${selected.unit_cost_usd}) and acceptable load"
        elif strategy == RoutingStrategy.LOWEST_LATENCY:
            selected = min(candidates, key=lambda c: (c.average_latency_ms, c.unit_cost_usd))
            reason = f"Selected for lowest latency ({selected.average_latency_ms}ms)"
        elif strategy == RoutingStrategy.MAX_CAPACITY:
            selected = min(candidates, key=lambda c: c.current_load_pct)
            reason = f"Selected for lowest current load ({selected.current_load_pct}%)"
        else:
            # Balanced efficiency: blend cost, latency and load
            selected = min(
                candidates,
                key=lambda c: (c.unit_cost_usd * 0.5 + (c.average_latency_ms / 10.0) * 0.3 + c.current_load_pct * 0.2)
            )
            reason = "Selected via balanced cost/latency/load efficiency score"

        decision = ResourceRoutingDecision(
            decision_id=f"dec-{uuid.uuid4().hex[:8]}",
            workload_type=workload_type,
            strategy=strategy,
            selected_resource_id=selected.resource_id,
            provider_name=selected.provider_name,
            estimated_cost_usd=round(selected.unit_cost_usd * required_capacity, 4),
            estimated_latency_ms=selected.average_latency_ms,
            reason=reason,
            routed_at=datetime.now(timezone.utc).isoformat(),
        )

        self._decisions.append(decision)
        return decision

    def get_resource(self, resource_id: str) -> Optional[ProviderResourceProfile]:
        """Retrieve resource details."""
        return self._resources.get(resource_id)

    def get_routing_report(self) -> Dict[str, Any]:
        """Generate summary of resource routing decisions and fleet distribution."""
        total_res = len(self._resources)
        avail_res = sum(1 for r in self._resources.values() if r.is_available)
        by_provider: Dict[str, int] = {}
        for d in self._decisions:
            by_provider[d.provider_name] = by_provider.get(d.provider_name, 0) + 1

        return {
            "total_resources_registered": total_res,
            "available_resources": avail_res,
            "total_routing_decisions": len(self._decisions),
            "decisions_by_provider": by_provider,
        }
