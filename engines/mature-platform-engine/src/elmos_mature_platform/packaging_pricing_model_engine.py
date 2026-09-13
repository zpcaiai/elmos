"""Packaging and Pricing Model Engine."""

from typing import Dict, List, Optional
from datetime import datetime, timezone

from .types import (
    PricingModel,
    PackageTier,
    PricingPlan,
    PricingSubscription,
    PricingSimulation
)

class PackagingPricingModelEngine:
    """Engine for managing packaging tiers, pricing models, and billing simulations."""

    def __init__(self):
        self._plans: Dict[str, PricingPlan] = {}
        self._subscriptions: Dict[str, PricingSubscription] = {}
        self._revenue_records: List[Dict] = []

    def create_plan(self, plan: PricingPlan) -> str:
        """Create a new pricing plan."""
        if plan.tier == PackageTier.FREE:
            if plan.base_price_monthly > 0 or plan.per_seat_price > 0:
                raise ValueError("FREE tier must have 0 base price and 0 per-seat price")
        self._plans[plan.plan_id] = plan
        return plan.plan_id

    def create_subscription(self, sub: PricingSubscription) -> str:
        """Create a new subscription."""
        if sub.plan_id not in self._plans:
            raise ValueError(f"Plan not found: {sub.plan_id}")
        
        plan = self._plans[sub.plan_id]
        if plan.max_seats > 0 and sub.seats > plan.max_seats:
            raise ValueError(f"Cannot exceed max seats ({plan.max_seats}) for this plan")

        if not sub.started_at:
            sub.started_at = datetime.now(timezone.utc).isoformat()
        if not sub.billing_cycle_start:
            sub.billing_cycle_start = sub.started_at

        # Calculate initial monthly total
        self._subscriptions[sub.subscription_id] = sub
        sub.monthly_total = self.calculate_monthly_cost(sub.subscription_id)
        return sub.subscription_id

    def calculate_monthly_cost(self, subscription_id: str) -> float:
        """Calculate the monthly cost for a subscription."""
        if subscription_id not in self._subscriptions:
            raise ValueError(f"Subscription not found: {subscription_id}")
            
        sub = self._subscriptions[subscription_id]
        plan = self._plans[sub.plan_id]

        cost = plan.base_price_monthly + (sub.seats * plan.per_seat_price)
        overage = max(0, sub.usage_units - plan.included_units)
        cost += overage * plan.overage_price_per_unit

        if sub.discount_pct > 0:
            cost = cost * (1 - sub.discount_pct / 100.0)

        return cost

    def record_usage(self, subscription_id: str, units: int) -> None:
        """Record usage for a subscription."""
        if subscription_id not in self._subscriptions:
            raise ValueError(f"Subscription not found: {subscription_id}")
        
        sub = self._subscriptions[subscription_id]
        sub.usage_units += units
        sub.monthly_total = self.calculate_monthly_cost(subscription_id)

    def simulate_pricing(self, plan_id: str, seats: int, usage: int, discount_pct: float = 0.0) -> PricingSimulation:
        """Simulate the cost of a plan based on seats and usage."""
        if plan_id not in self._plans:
            raise ValueError(f"Plan not found: {plan_id}")
            
        plan = self._plans[plan_id]
        if plan.max_seats > 0 and seats > plan.max_seats:
            raise ValueError(f"Cannot exceed max seats ({plan.max_seats}) for this plan")

        base_cost = plan.base_price_monthly + (seats * plan.per_seat_price)
        overage = max(0, usage - plan.included_units)
        overage_cost = overage * plan.overage_price_per_unit
        
        total_monthly = base_cost + overage_cost
        
        if discount_pct > 0:
            total_monthly = total_monthly * (1 - discount_pct / 100.0)

        annual_cost = total_monthly * 12
        cost_per_seat = total_monthly / seats if seats > 0 else total_monthly

        return PricingSimulation(
            simulation_id=f"sim_{int(datetime.now().timestamp())}",
            plan_id=plan_id,
            seats=seats,
            projected_usage=usage,
            monthly_cost=total_monthly,
            annual_cost=annual_cost,
            cost_per_seat=cost_per_seat
        )

    def upgrade_plan(self, subscription_id: str, new_plan_id: str) -> PricingSubscription:
        """Upgrade to a higher tier plan."""
        if subscription_id not in self._subscriptions:
            raise ValueError("Subscription not found")
        if new_plan_id not in self._plans:
            raise ValueError("New plan not found")

        sub = self._subscriptions[subscription_id]
        current_plan = self._plans[sub.plan_id]
        new_plan = self._plans[new_plan_id]

        tier_order = {
            PackageTier.FREE: 0,
            PackageTier.STARTER: 1,
            PackageTier.PROFESSIONAL: 2,
            PackageTier.ENTERPRISE: 3,
            PackageTier.CUSTOM: 4
        }
        
        if tier_order[new_plan.tier] <= tier_order[current_plan.tier]:
            raise ValueError("Can only upgrade to a higher tier")

        if new_plan.max_seats > 0 and sub.seats > new_plan.max_seats:
            raise ValueError(f"Cannot exceed max seats ({new_plan.max_seats}) for this plan")

        sub.plan_id = new_plan_id
        sub.monthly_total = self.calculate_monthly_cost(subscription_id)
        return sub

    def downgrade_plan(self, subscription_id: str, new_plan_id: str) -> PricingSubscription:
        """Downgrade to a lower tier plan (at cycle end)."""
        if subscription_id not in self._subscriptions:
            raise ValueError("Subscription not found")
        if new_plan_id not in self._plans:
            raise ValueError("New plan not found")

        sub = self._subscriptions[subscription_id]
        current_plan = self._plans[sub.plan_id]
        new_plan = self._plans[new_plan_id]

        tier_order = {
            PackageTier.FREE: 0,
            PackageTier.STARTER: 1,
            PackageTier.PROFESSIONAL: 2,
            PackageTier.ENTERPRISE: 3,
            PackageTier.CUSTOM: 4
        }
        
        if tier_order[new_plan.tier] >= tier_order[current_plan.tier]:
            raise ValueError("Can only downgrade to a lower tier")

        if new_plan.max_seats > 0 and sub.seats > new_plan.max_seats:
            raise ValueError(f"Cannot exceed max seats ({new_plan.max_seats}) for this plan")

        sub.plan_id = new_plan_id
        sub.monthly_total = self.calculate_monthly_cost(subscription_id)
        return sub

    def get_revenue_report(self) -> Dict:
        """Generate a revenue report."""
        total_mrr = 0.0
        mrr_by_tier = {tier.value: 0.0 for tier in PackageTier}
        total_customers = len(self._subscriptions)
        
        for sub in self._subscriptions.values():
            cost = self.calculate_monthly_cost(sub.subscription_id)
            total_mrr += cost
            tier = self._plans[sub.plan_id].tier
            mrr_by_tier[tier.value] += cost
            
        arr = total_mrr * 12
        avg_revenue_per_customer = total_mrr / total_customers if total_customers > 0 else 0.0
        
        return {
            "total_mrr": total_mrr,
            "total_arr": arr,
            "mrr_by_tier": mrr_by_tier,
            "avg_revenue_per_customer": avg_revenue_per_customer
        }

    def compare_plans(self, plan_ids: List[str]) -> Dict:
        """Compare features and pricing of multiple plans."""
        matrix = {}
        all_features = set()
        
        for pid in plan_ids:
            if pid in self._plans:
                plan = self._plans[pid]
                all_features.update(plan.features)
                
        for pid in plan_ids:
            if pid not in self._plans:
                continue
            plan = self._plans[pid]
            matrix[pid] = {
                "name": plan.name,
                "tier": plan.tier.value,
                "base_price": plan.base_price_monthly,
                "per_seat_price": plan.per_seat_price,
                "included_units": plan.included_units,
                "overage_price": plan.overage_price_per_unit,
                "max_seats": plan.max_seats if plan.max_seats > 0 else "unlimited",
                "feature_support": {feat: (feat in plan.features) for feat in all_features}
            }
        return matrix

    def get_plan_recommendations(self, seats: int, usage: int) -> List[Dict]:
        """Recommend plans based on seats and usage, ordered by lowest cost."""
        recommendations = []
        for plan in self._plans.values():
            if plan.max_seats > 0 and seats > plan.max_seats:
                continue
            if not plan.active:
                continue
                
            sim = self.simulate_pricing(plan.plan_id, seats, usage)
            recommendations.append({
                "plan_id": plan.plan_id,
                "name": plan.name,
                "tier": plan.tier.value,
                "monthly_cost": sim.monthly_cost,
                "features": plan.features
            })
            
        recommendations.sort(key=lambda x: x["monthly_cost"])
        return recommendations

    def apply_discount(self, subscription_id: str, discount_pct: float) -> PricingSubscription:
        """Apply a discount percentage to a subscription."""
        if subscription_id not in self._subscriptions:
            raise ValueError(f"Subscription not found: {subscription_id}")
        if discount_pct < 0 or discount_pct > 100:
            raise ValueError("Discount must be between 0 and 100")
            
        sub = self._subscriptions[subscription_id]
        sub.discount_pct = discount_pct
        sub.monthly_total = self.calculate_monthly_cost(subscription_id)
        return sub
