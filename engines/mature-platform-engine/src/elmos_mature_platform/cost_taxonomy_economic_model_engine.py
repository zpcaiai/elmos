"""Cost Taxonomy and Economic Model Engine (Batch 44 - Skill 1456).

Maintains enterprise FinOps cost taxonomy, cost center allocations, CapEx vs OpEx splits,
and migration unit economics aggregation across infrastructure and engineering domains.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    CostAllocationEntry,
    CostCenterRecord,
    CostTaxonomyType,
    EconomicModelSummary,
)


class CostTaxonomyEconomicModelEngine:
    """Enterprise FinOps economic model and cost taxonomy engine."""

    def __init__(self) -> None:
        self._cost_centers: Dict[str, CostCenterRecord] = {}
        self._entries: Dict[str, CostAllocationEntry] = {}

    def register_cost_center(self, center: CostCenterRecord) -> str:
        """Register an organizational cost center."""
        if not center.name or not center.department:
            raise ValueError("name and department are required")

        if not center.center_id:
            center.center_id = f"cc-{uuid.uuid4().hex[:8]}"

        if not center.created_at:
            center.created_at = datetime.now(timezone.utc).isoformat()

        self._cost_centers[center.center_id] = center
        return center.center_id

    def record_cost_allocation(self, entry: CostAllocationEntry) -> str:
        """Record a discrete expense allocated to a cost center."""
        if entry.amount_usd < 0:
            raise ValueError("amount_usd cannot be negative")

        center = self._cost_centers.get(entry.center_id)
        if not center:
            raise ValueError(f"Cost center not found: {entry.center_id}")

        if not center.is_active:
            raise ValueError(f"Cost center {entry.center_id} is inactive; cannot allocate expense")

        if not entry.entry_id:
            entry.entry_id = f"alloc-{uuid.uuid4().hex[:8]}"

        if not entry.timestamp:
            entry.timestamp = datetime.now(timezone.utc).isoformat()

        self._entries[entry.entry_id] = entry
        center.budget_spent_usd = round(center.budget_spent_usd + entry.amount_usd, 2)
        return entry.entry_id

    def get_cost_center(self, center_id: str) -> Optional[CostCenterRecord]:
        """Retrieve cost center record."""
        return self._cost_centers.get(center_id)

    def get_cost_by_taxonomy(self) -> Dict[str, float]:
        """Aggregate total spend broken down by taxonomy category."""
        breakdown: Dict[str, float] = {tax.value: 0.0 for tax in CostTaxonomyType}
        for entry in self._entries.values():
            cat = entry.taxonomy_type.value
            breakdown[cat] = round(breakdown.get(cat, 0.0) + entry.amount_usd, 2)
        return breakdown

    def get_cost_by_center(self, center_id: str) -> Dict[str, Any]:
        """Retrieve total and itemized spend for a specific cost center."""
        center = self._cost_centers.get(center_id)
        if not center:
            raise ValueError(f"Cost center not found: {center_id}")

        allocations = [e for e in self._entries.values() if e.center_id == center_id]
        total = sum(e.amount_usd for e in allocations)
        over_budget = total > center.budget_allocated_usd if center.budget_allocated_usd > 0 else False

        return {
            "center_id": center.center_id,
            "name": center.name,
            "department": center.department,
            "owner": center.owner,
            "budget_allocated_usd": center.budget_allocated_usd,
            "budget_spent_usd": round(total, 2),
            "remaining_budget_usd": round(center.budget_allocated_usd - total, 2),
            "is_over_budget": over_budget,
            "allocations_count": len(allocations),
        }

    def compute_economic_model(self) -> EconomicModelSummary:
        """Calculate complete macro economic model summary."""
        total_spend = sum(e.amount_usd for e in self._entries.values())
        capex_total = sum(e.amount_usd for e in self._entries.values() if e.is_capex)
        opex_total = total_spend - capex_total

        by_tax = self.get_cost_by_taxonomy()
        by_center: Dict[str, float] = {}
        over_budget: List[str] = []

        for cid, center in self._cost_centers.items():
            spent = center.budget_spent_usd
            by_center[cid] = spent
            if center.budget_allocated_usd > 0 and spent > center.budget_allocated_usd:
                over_budget.append(cid)

        return EconomicModelSummary(
            total_spend_usd=round(total_spend, 2),
            capex_total_usd=round(capex_total, 2),
            opex_total_usd=round(opex_total, 2),
            by_taxonomy=by_tax,
            by_cost_center=by_center,
            active_centers_count=sum(1 for c in self._cost_centers.values() if c.is_active),
            over_budget_centers=over_budget,
        )

    def get_taxonomy_report(self) -> Dict[str, Any]:
        """Generate high-level FinOps taxonomy governance report."""
        summary = self.compute_economic_model()
        return {
            "total_expenses_recorded": len(self._entries),
            "total_cost_centers": len(self._cost_centers),
            "economic_model": {
                "total_spend_usd": summary.total_spend_usd,
                "capex_total_usd": summary.capex_total_usd,
                "opex_total_usd": summary.opex_total_usd,
                "over_budget_centers_count": len(summary.over_budget_centers),
            },
            "by_taxonomy": summary.by_taxonomy,
        }
