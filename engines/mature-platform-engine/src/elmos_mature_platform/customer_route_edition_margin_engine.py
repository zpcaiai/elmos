"""Customer, Route, and Edition Margin Engine (Batch 44 - Skill 1467).

Evaluates contract revenues against full Cost of Goods Sold (COGS), measuring project,
language route, and commercial platform edition gross margins, margin health statuses, and profitability thresholds.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    CustomerRouteMarginRecord,
    EditionMarginSummary,
    MarginHealthStatus,
)


class CustomerRouteEditionMarginEngine:
    """Gross margin and unit economics profitability analyzer across migration routes and editions."""

    def __init__(self) -> None:
        self._records: Dict[str, CustomerRouteMarginRecord] = {}

    def record_project_financials(self, record: CustomerRouteMarginRecord) -> str:
        """Record contract revenue and COGS for a specific migration project."""
        if not record.customer_id or not record.project_id:
            raise ValueError("customer_id and project_id are required")
        if not record.route_key or not record.edition:
            raise ValueError("route_key and edition are required")
        if record.contract_revenue_usd < 0:
            raise ValueError("contract_revenue_usd cannot be negative")

        if not record.record_id:
            record.record_id = f"crm-{uuid.uuid4().hex[:8]}"

        if not record.recorded_at:
            record.recorded_at = datetime.now(timezone.utc).isoformat()

        self._records[record.record_id] = record
        return record.record_id

    def get_record(self, record_id: str) -> Optional[CustomerRouteMarginRecord]:
        """Retrieve project financial margin record."""
        return self._records.get(record_id)

    def calculate_gross_margin(self, record_id: str) -> Dict[str, float]:
        """Calculate total COGS, gross margin USD, and gross margin percentage for a record."""
        record = self._records.get(record_id)
        if not record:
            raise ValueError(f"Margin record not found: {record_id}")

        total_cogs = (
            record.compute_cogs_usd
            + record.model_cogs_usd
            + record.storage_cogs_usd
            + record.human_cogs_usd
            + record.license_cogs_usd
        )
        gross_margin_usd = record.contract_revenue_usd - total_cogs
        if record.contract_revenue_usd > 0:
            margin_pct = (gross_margin_usd / record.contract_revenue_usd) * 100.0
        else:
            margin_pct = 0.0 if total_cogs == 0.0 else -100.0

        return {
            "contract_revenue_usd": round(record.contract_revenue_usd, 2),
            "total_cogs_usd": round(total_cogs, 2),
            "gross_margin_usd": round(gross_margin_usd, 2),
            "gross_margin_pct": round(margin_pct, 2),
            "target_margin_pct": record.target_margin_pct,
        }

    def get_margin_health_status(self, record_id: str) -> MarginHealthStatus:
        """Determine profitability health status based on realized gross margin percentage."""
        margin_info = self.calculate_gross_margin(record_id)
        pct = margin_info["gross_margin_pct"]

        if pct >= 60.0:
            return MarginHealthStatus.HEALTHY
        elif pct >= 30.0:
            return MarginHealthStatus.WARNING
        else:
            return MarginHealthStatus.CRITICAL

    def get_margin_by_route(self, route_key: str) -> Dict[str, Any]:
        """Aggregate financial margin metrics for a specific modernization route."""
        matching = [r for r in self._records.values() if r.route_key == route_key]
        if not matching:
            return {
                "route_key": route_key,
                "project_count": 0,
                "total_revenue_usd": 0.0,
                "total_cogs_usd": 0.0,
                "gross_margin_usd": 0.0,
                "gross_margin_pct": 0.0,
            }

        rev = sum(r.contract_revenue_usd for r in matching)
        cogs = sum(
            r.compute_cogs_usd
            + r.model_cogs_usd
            + r.storage_cogs_usd
            + r.human_cogs_usd
            + r.license_cogs_usd
            for r in matching
        )
        gm_usd = rev - cogs
        gm_pct = (gm_usd / rev * 100.0) if rev > 0 else 0.0

        return {
            "route_key": route_key,
            "project_count": len(matching),
            "total_revenue_usd": round(rev, 2),
            "total_cogs_usd": round(cogs, 2),
            "gross_margin_usd": round(gm_usd, 2),
            "gross_margin_pct": round(gm_pct, 2),
        }

    def get_margin_by_edition(self, edition: str) -> EditionMarginSummary:
        """Aggregate profitability and health status for a specific deployment edition."""
        matching = [r for r in self._records.values() if r.edition == edition]
        rev = sum(r.contract_revenue_usd for r in matching)
        cogs = sum(
            r.compute_cogs_usd
            + r.model_cogs_usd
            + r.storage_cogs_usd
            + r.human_cogs_usd
            + r.license_cogs_usd
            for r in matching
        )
        gm_usd = rev - cogs
        gm_pct = (gm_usd / rev * 100.0) if rev > 0 else 0.0

        if gm_pct >= 60.0:
            health = MarginHealthStatus.HEALTHY
        elif gm_pct >= 30.0:
            health = MarginHealthStatus.WARNING
        else:
            health = MarginHealthStatus.CRITICAL

        return EditionMarginSummary(
            edition=edition,
            total_revenue_usd=round(rev, 2),
            total_cogs_usd=round(cogs, 2),
            gross_margin_usd=round(gm_usd, 2),
            gross_margin_pct=round(gm_pct, 2),
            project_count=len(matching),
            health_status=health,
        )

    def get_fleet_margin_report(self) -> Dict[str, Any]:
        """Produce macro portfolio-level margin and unit economics report."""
        total_projects = len(self._records)
        total_rev = sum(r.contract_revenue_usd for r in self._records.values())
        total_cogs = sum(
            r.compute_cogs_usd
            + r.model_cogs_usd
            + r.storage_cogs_usd
            + r.human_cogs_usd
            + r.license_cogs_usd
            for r in self._records.values()
        )
        total_gm = total_rev - total_cogs
        avg_margin_pct = (total_gm / total_rev * 100.0) if total_rev > 0 else 0.0

        health_counts: Dict[str, int] = {s.value: 0 for s in MarginHealthStatus}
        for rid in self._records:
            h = self.get_margin_health_status(rid)
            health_counts[h.value] += 1

        return {
            "total_projects": total_projects,
            "portfolio_revenue_usd": round(total_rev, 2),
            "portfolio_cogs_usd": round(total_cogs, 2),
            "portfolio_gross_margin_usd": round(total_gm, 2),
            "portfolio_margin_pct": round(avg_margin_pct, 2),
            "health_distribution": health_counts,
        }
