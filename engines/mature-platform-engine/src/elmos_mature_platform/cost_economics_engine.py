import uuid
import statistics
from typing import List, Dict, Optional
from elmos_mature_platform.types import (
    CostCategory,
    CostLineItem,
    CostScenarioForecast,
    ROIAnalysis,
    UnitEconomics,
    BudgetAlert,
)

class CostEconomicsEngine:
    """Engine for FinOps and economics calculations."""
    
    def __init__(self):
        self._costs: List[CostLineItem] = []
        self._budgets: Dict[str, float] = {}

    def record_cost(self, item: CostLineItem) -> None:
        """Record a cost line item."""
        if item.quantity < 0 or item.unit_price < 0 or item.total_cost < 0:
            raise ValueError("Costs must have positive amounts")
        self._costs.append(item)

    def get_costs_by_tenant(self, tenant_id: str) -> List[CostLineItem]:
        """Filter costs by tenant."""
        return [c for c in self._costs if c.tenant_id == tenant_id]

    def get_costs_by_category(self, category: CostCategory) -> List[CostLineItem]:
        """Filter by category."""
        return [c for c in self._costs if c.category == category]

    def compute_total_cost(self, tenant_id: Optional[str] = None) -> float:
        """Sum all costs, optionally filtered by tenant."""
        if tenant_id:
            return sum(c.total_cost for c in self._costs if c.tenant_id == tenant_id)
        return sum(c.total_cost for c in self._costs)

    def compute_unit_economics(self, unit_type: str, total_revenue: float, total_units: int) -> UnitEconomics:
        """Calculate per-unit margin."""
        if total_units <= 0:
            raise ValueError("Total units must be greater than 0")
        
        total_cost = self.compute_total_cost()
        cost_per_unit = total_cost / total_units
        revenue_per_unit = total_revenue / total_units
        margin_per_unit = revenue_per_unit - cost_per_unit
        margin_pct = (margin_per_unit / revenue_per_unit * 100) if revenue_per_unit > 0 else 0.0
        breakeven_units = int(total_cost / revenue_per_unit) if revenue_per_unit > 0 else 0

        return UnitEconomics(
            unit_type=unit_type,
            cost_per_unit=cost_per_unit,
            revenue_per_unit=revenue_per_unit,
            margin_per_unit=margin_per_unit,
            margin_pct=margin_pct,
            breakeven_units=breakeven_units
        )

    def create_cost_forecast(self, scenario_name: str, base_monthly_cost: float, growth_rate: float, months: int) -> CostScenarioForecast:
        """Project costs forward based on scenario and growth rate."""
        projected = []
        current = base_monthly_cost
        for _ in range(months):
            projected.append(current)
            current *= (1 + growth_rate)

        return CostScenarioForecast(
            scenario_id=str(uuid.uuid4()),
            scenario_name=scenario_name,
            time_horizon_months=months,
            projected_monthly_costs=projected
        )

    def compute_roi(self, migration_cost: float, monthly_savings: float, risk_discount: float) -> ROIAnalysis:
        """Compute 3-year ROI with risk adjustment."""
        if monthly_savings <= 0:
            raise ValueError("Monthly savings must be positive")
        annual_savings = monthly_savings * 12
        payback_months = migration_cost / monthly_savings if monthly_savings > 0 else float('inf')
        three_year_savings = monthly_savings * 36
        three_year_roi = ((three_year_savings - migration_cost) / migration_cost * 100) if migration_cost > 0 else float('inf')
        
        risk_adjusted_savings = three_year_savings * (1 - risk_discount)
        risk_adjusted_roi = ((risk_adjusted_savings - migration_cost) / migration_cost * 100) if migration_cost > 0 else float('inf')

        return ROIAnalysis(
            analysis_id=str(uuid.uuid4()),
            migration_cost=migration_cost,
            annual_savings=annual_savings,
            payback_period_months=payback_months,
            three_year_roi_pct=three_year_roi,
            risk_adjusted_roi_pct=risk_adjusted_roi
        )

    def set_budget(self, tenant_id: str, monthly_limit: float) -> None:
        """Set monthly budget limit for tenant."""
        self._budgets[tenant_id] = monthly_limit

    def check_budget(self, tenant_id: str) -> Optional[BudgetAlert]:
        """Check current spend against budget, generate alerts at 80/90/100% thresholds."""
        if tenant_id not in self._budgets:
            return None
        
        limit = self._budgets[tenant_id]
        spend = self.compute_total_cost(tenant_id=tenant_id)
        util_pct = (spend / limit * 100) if limit > 0 else float('inf')

        threshold = None
        if util_pct >= 100:
            threshold = "100pct_exceeded"
        elif util_pct >= 90:
            threshold = "90pct_critical"
        elif util_pct >= 80:
            threshold = "80pct_warning"

        if threshold:
            return BudgetAlert(
                alert_id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                budget_limit=limit,
                current_spend=spend,
                utilization_pct=util_pct,
                threshold_breached=threshold,
                projected_overage=spend - limit if spend > limit else 0.0
            )
        return None

    def generate_showback_report(self, tenant_id: str) -> Dict:
        """Cost breakdown by category for a specific tenant."""
        costs = self.get_costs_by_tenant(tenant_id)
        breakdown = {}
        for c in costs:
            cat = c.category.value
            breakdown[cat] = breakdown.get(cat, 0.0) + c.total_cost
        return {
            "tenant_id": tenant_id,
            "total_cost": sum(breakdown.values()),
            "breakdown": breakdown
        }

    def generate_chargeback_invoice(self, tenant_id: str, period: str) -> Dict:
        """Generate an itemized invoice for a tenant."""
        costs = self.get_costs_by_tenant(tenant_id)
        return {
            "tenant_id": tenant_id,
            "period": period,
            "total_amount": sum(c.total_cost for c in costs),
            "line_items": [
                {
                    "item_id": c.item_id,
                    "description": c.description,
                    "amount": c.total_cost
                } for c in costs
            ]
        }

    def reconcile_billing(self, metered_costs: List[CostLineItem], billed_amount: float) -> Dict:
        """Compare metered vs billed, report discrepancies."""
        metered_total = sum(c.total_cost for c in metered_costs)
        discrepancy = billed_amount - metered_total
        diff_pct = (abs(discrepancy) / metered_total * 100) if metered_total > 0 else (100.0 if billed_amount > 0 else 0.0)
        
        return {
            "metered_total": metered_total,
            "billed_amount": billed_amount,
            "discrepancy": discrepancy,
            "discrepancy_pct": diff_pct,
            "flagged": diff_pct > 1.0
        }

    def get_cost_anomalies(self, tenant_id: str, std_dev_threshold: float = 2.0) -> List[Dict]:
        """Detect cost spikes over the given standard deviation threshold."""
        costs = self.get_costs_by_tenant(tenant_id)
        if not costs:
            return []
        
        daily_costs: Dict[str, float] = {}
        for c in costs:
            date = c.timestamp[:10] if c.timestamp else "unknown"
            daily_costs[date] = daily_costs.get(date, 0.0) + c.total_cost
            
        values = list(daily_costs.values())
        if len(values) < 2:
            return []
            
        mean_cost = statistics.mean(values)
        stdev = statistics.stdev(values) if len(values) > 1 else 0.0
        
        anomalies = []
        for date, amount in daily_costs.items():
            if stdev > 0 and (amount - mean_cost) / stdev > std_dev_threshold:
                anomalies.append({
                    "date": date,
                    "amount": amount,
                    "mean": mean_cost,
                    "deviation_std": (amount - mean_cost) / stdev
                })
        return anomalies

    def get_model_inference_economics(self) -> Dict:
        """Cost breakdown for model inference by provider."""
        inference_costs = self.get_costs_by_category(CostCategory.MODEL_INFERENCE)
        provider_breakdown = {}
        for c in inference_costs:
            provider = c.description.split()[0] if c.description else "Unknown"
            provider_breakdown[provider] = provider_breakdown.get(provider, 0.0) + c.total_cost
            
        return {
            "total_inference_cost": sum(provider_breakdown.values()),
            "provider_breakdown": provider_breakdown
        }
