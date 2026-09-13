"""FinOps, Resource Metering & Billing Reconciliation Engine for Elmos Mature Platform."""

from __future__ import annotations

import collections
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from elmos_mature_platform.types import (
    InvoiceLineItem,
    MarginReport,
    UsageRecord,
)


class FinOpsEconomicsEngine:
    """Tracks resource consumption, reconciles billing invoices, and enforces financial guardrails."""

    UNIT_RATES = {
        "cpu_hours": 0.048,
        "memory_gb_hours": 0.007,
        "storage_gb_months": 0.022,
        "egress_gb": 0.085,
        "token_count": 0.0000025,
    }

    def __init__(self) -> None:
        self.usage_records: List[UsageRecord] = []
        self.invoices: collections.defaultdict[str, List[InvoiceLineItem]] = collections.defaultdict(list)
        self.tenant_budgets: Dict[str, float] = {}  # tenant -> monthly budget in USD
        self.event_log: List[str] = []

    def _log(self, message: str) -> None:
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        entry = f"[{ts}][FINOPS-ENGINE] {message}"
        self.event_log.append(entry)

    def set_budget(self, tenant_id: str, budget_usd: float) -> None:
        self.tenant_budgets[tenant_id] = budget_usd
        self._log(f"Set monthly budget for tenant {tenant_id} to ${budget_usd:,.2f}")

    def record_usage(self, tenant_id: str, resource_type: str, quantity: float) -> UsageRecord:
        """Records metered resource consumption."""
        rate = self.UNIT_RATES.get(resource_type, 0.01)
        cost = quantity * rate
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        record = UsageRecord(
            tenant_id=tenant_id,
            resource_type=resource_type,
            quantity=quantity,
            unit_price=rate,
            total_cost=cost,
            recorded_at=now,
        )
        self.usage_records.append(record)
        return record

    def get_tenant_total_spend(self, tenant_id: str) -> float:
        return sum(r.total_cost for r in self.usage_records if r.tenant_id == tenant_id)

    def check_budget_guardrail(self, tenant_id: str) -> Tuple[bool, str, float]:
        """Checks if tenant spend conforms to budget guardrails."""
        budget = self.tenant_budgets.get(tenant_id, 10000.0)
        spend = self.get_tenant_total_spend(tenant_id)
        pct = (spend / budget) * 100.0 if budget > 0 else 0.0

        if spend >= budget:
            self._log(f"BUDGET EXHAUSTION: Tenant {tenant_id} spend ${spend:.2f} reached 100% of ${budget:.2f} limit")
            return False, f"HARD_LIMIT_REACHED: Spend ${spend:.2f} >= Budget ${budget:.2f}", pct
        elif spend >= 0.8 * budget:
            return True, f"SOFT_WARNING: Spend ${spend:.2f} >= 80% of budget", pct
        else:
            return True, f"OK: Spend ${spend:.2f} ({pct:.1f}%) within budget", pct

    def generate_invoice(self, tenant_id: str, period: str) -> List[InvoiceLineItem]:
        """Aggregates metered usage into an itemized customer invoice."""
        tenant_records = [r for r in self.usage_records if r.tenant_id == tenant_id]
        agg: Dict[str, float] = collections.defaultdict(float)
        for r in tenant_records:
            agg[r.resource_type] += r.quantity

        line_items: List[InvoiceLineItem] = []
        for res_type, qty in agg.items():
            rate = self.UNIT_RATES.get(res_type, 0.01)
            amount = qty * rate
            item = InvoiceLineItem(
                item_id=f"inv-{tenant_id}-{res_type}-{period}",
                tenant_id=tenant_id,
                period=period,
                resource_type=res_type,
                billed_units=qty,
                billed_amount=amount,
                metered_units=qty,
                reconciled=True,
                discrepancy=0.0,
            )
            line_items.append(item)

        self.invoices[tenant_id] = line_items
        self._log(f"Generated invoice for tenant {tenant_id} period {period}: {len(line_items)} line items, total=${sum(i.billed_amount for i in line_items):.2f}")
        return line_items

    def reconcile_billing(self, tenant_id: str) -> Tuple[bool, float, List[str]]:
        """100% reconciliation between metered telemetry events and invoiced line items."""
        items = self.invoices.get(tenant_id, [])
        if not items:
            return True, 0.0, ["No invoiced items to reconcile"]

        discrepancies: List[str] = []
        total_discrepancy = 0.0

        for item in items:
            metered_qty = sum(r.quantity for r in self.usage_records if r.tenant_id == tenant_id and r.resource_type == item.resource_type)
            diff = abs(metered_qty - item.billed_units)
            if diff > 1e-4:
                item.reconciled = False
                item.discrepancy = diff
                total_discrepancy += diff
                discrepancies.append(f"Discrepancy on {item.resource_type}: billed={item.billed_units}, metered={metered_qty}")
            else:
                item.reconciled = True
                item.discrepancy = 0.0

        is_reconciled = (total_discrepancy == 0.0)
        self._log(f"Billing reconciliation for tenant {tenant_id}: Reconciled={is_reconciled}, Discrepancies={len(discrepancies)}")
        return is_reconciled, total_discrepancy, discrepancies

    def compute_gross_margin(self, period: str, total_revenue: float, tenant_id: Optional[str] = None) -> MarginReport:
        """Computes platform gross margin and evaluates commercial profitability."""
        records = [r for r in self.usage_records if tenant_id is None or r.tenant_id == tenant_id]
        infra_costs = sum(r.total_cost for r in records)
        third_party_costs = sum(r.total_cost for r in records if r.resource_type == "token_count") * 0.4
        total_cogs = infra_costs + third_party_costs
        gross_profit = total_revenue - total_cogs
        margin_pct = (gross_profit / max(1.0, total_revenue)) * 100.0

        compliant = margin_pct >= 65.0  # Enterprise target margin >= 65%

        report = MarginReport(
            period=period,
            total_revenue=total_revenue,
            infra_costs=infra_costs,
            third_party_costs=third_party_costs,
            gross_margin_percentage=margin_pct,
            margin_threshold_compliant=compliant,
        )
        self._log(f"Margin report for {period} (tenant={tenant_id}): Revenue=${total_revenue:,.2f}, COGS=${total_cogs:,.2f}, Margin={margin_pct:.1f}%, Compliant={compliant}")
        return report
