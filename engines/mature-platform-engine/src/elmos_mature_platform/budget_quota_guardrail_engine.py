from typing import Dict, List, Optional
from datetime import datetime
import uuid

from .types import (
    QuotaResourceType,
    GuardrailAction,
    QuotaDefinition,
    BudgetAllocation,
    GuardrailDecision
)

class BudgetQuotaGuardrailEngine:
    """
    Engine for managing budget and quota guardrails.
    """
    
    def __init__(self):
        # Maps tenant_id -> resource_type -> QuotaDefinition
        self.quotas: Dict[str, Dict[QuotaResourceType, QuotaDefinition]] = {}
        # Maps tenant_id -> BudgetAllocation
        self.budgets: Dict[str, BudgetAllocation] = {}
        # Track all decisions made for reporting
        self.decisions: List[GuardrailDecision] = []

    def _generate_id(self) -> str:
        return str(uuid.uuid4())

    def _get_timestamp(self) -> str:
        from datetime import timezone
        return datetime.now(timezone.utc).isoformat()

    def create_quota(self, quota: QuotaDefinition) -> str:
        """Create or update a quota for a tenant and resource type."""
        if quota.tenant_id not in self.quotas:
            self.quotas[quota.tenant_id] = {}
        self.quotas[quota.tenant_id][quota.resource_type] = quota
        return quota.quota_id

    def create_budget(self, budget: BudgetAllocation) -> str:
        """Create or update a budget for a tenant."""
        self.budgets[budget.tenant_id] = budget
        return budget.budget_id

    def check_quota(self, tenant_id: str, resource_type: QuotaResourceType, amount: float) -> GuardrailDecision:
        """Check if requested amount is allowed by quota without consuming it."""
        if tenant_id not in self.quotas or resource_type not in self.quotas[tenant_id]:
            return GuardrailDecision(
                decision_id=self._generate_id(),
                tenant_id=tenant_id,
                resource_type=resource_type,
                requested_amount=amount,
                action=GuardrailAction.DENY,
                reason="No quota defined for resource type",
                timestamp=self._get_timestamp()
            )
        
        quota = self.quotas[tenant_id][resource_type]
        projected_usage = quota.current_usage + amount
        usage_pct = (projected_usage / quota.limit) * 100.0 if quota.limit > 0 else float('inf')

        action = GuardrailAction.ALLOW
        reason = "Within quota limits"

        if usage_pct >= quota.hard_limit_pct:
            action = GuardrailAction.DENY
            reason = f"Usage exceeds hard limit of {quota.hard_limit_pct}%"
        elif usage_pct >= quota.warn_threshold_pct:
            action = GuardrailAction.WARN
            reason = f"Usage exceeds warning threshold of {quota.warn_threshold_pct}%"

        decision = GuardrailDecision(
            decision_id=self._generate_id(),
            tenant_id=tenant_id,
            resource_type=resource_type,
            requested_amount=amount,
            action=action,
            reason=reason,
            remaining_quota=max(0.0, quota.limit - quota.current_usage),
            remaining_budget=self._get_remaining_budget(tenant_id),
            timestamp=self._get_timestamp()
        )
        self.decisions.append(decision)
        return decision

    def consume_quota(self, tenant_id: str, resource_type: QuotaResourceType, amount: float) -> GuardrailDecision:
        """Consume quota if allowed."""
        decision = self.check_quota(tenant_id, resource_type, amount)
        if decision.action in (GuardrailAction.ALLOW, GuardrailAction.WARN):
            quota = self.quotas[tenant_id][resource_type]
            quota.current_usage += amount
            decision.remaining_quota = max(0.0, quota.limit - quota.current_usage)
        return decision

    def _get_remaining_budget(self, tenant_id: str) -> float:
        if tenant_id not in self.budgets:
            return 0.0
        b = self.budgets[tenant_id]
        return max(0.0, b.total_budget - b.spent - b.reserved)

    def check_budget(self, tenant_id: str, amount: float) -> GuardrailDecision:
        """Check if amount can be spent against budget without actually spending it."""
        if tenant_id not in self.budgets:
            return GuardrailDecision(
                decision_id=self._generate_id(),
                tenant_id=tenant_id,
                resource_type=QuotaResourceType.COMPUTE, # Default fallback
                requested_amount=amount,
                action=GuardrailAction.DENY,
                reason="No budget defined",
                timestamp=self._get_timestamp()
            )

        budget = self.budgets[tenant_id]
        available = budget.total_budget - budget.spent - budget.reserved
        
        if amount > available:
            action = GuardrailAction.DENY
            reason = "Insufficient available budget"
        else:
            action = GuardrailAction.ALLOW
            reason = "Within budget limits"

            # Check if this spend would cross alert threshold
            projected_spent = budget.spent + amount
            if (projected_spent / budget.total_budget * 100.0) >= budget.alert_threshold_pct:
                action = GuardrailAction.WARN
                reason = "Spend exceeds budget alert threshold"

        decision = GuardrailDecision(
            decision_id=self._generate_id(),
            tenant_id=tenant_id,
            resource_type=QuotaResourceType.COMPUTE,
            requested_amount=amount,
            action=action,
            reason=reason,
            remaining_quota=0.0,
            remaining_budget=available,
            timestamp=self._get_timestamp()
        )
        self.decisions.append(decision)
        return decision

    def spend_budget(self, tenant_id: str, amount: float) -> GuardrailDecision:
        """Spend budget directly if available."""
        decision = self.check_budget(tenant_id, amount)
        if decision.action in (GuardrailAction.ALLOW, GuardrailAction.WARN):
            budget = self.budgets[tenant_id]
            budget.spent += amount
            decision.remaining_budget = max(0.0, budget.total_budget - budget.spent - budget.reserved)
        return decision

    def reserve_budget(self, tenant_id: str, amount: float) -> GuardrailDecision:
        """Reserve budget for future spending."""
        decision = self.check_budget(tenant_id, amount)
        if decision.action in (GuardrailAction.ALLOW, GuardrailAction.WARN):
            budget = self.budgets[tenant_id]
            budget.reserved += amount
            decision.remaining_budget = max(0.0, budget.total_budget - budget.spent - budget.reserved)
        return decision

    def release_reservation(self, tenant_id: str, amount: float) -> BudgetAllocation:
        """Release a previously reserved amount of budget."""
        if tenant_id not in self.budgets:
            raise ValueError(f"No budget found for tenant {tenant_id}")
        
        budget = self.budgets[tenant_id]
        release_amount = min(budget.reserved, amount)
        budget.reserved -= release_amount
        return budget

    def get_quota_usage(self, tenant_id: str) -> Dict[str, Dict]:
        """Return a summary of all quotas and their usage for a tenant."""
        if tenant_id not in self.quotas:
            return {}
        
        result = {}
        for rt, quota in self.quotas[tenant_id].items():
            result[rt.value] = {
                "limit": quota.limit,
                "current_usage": quota.current_usage,
                "warn_threshold_pct": quota.warn_threshold_pct,
                "hard_limit_pct": quota.hard_limit_pct
            }
        return result

    def get_budget_status(self, tenant_id: str) -> Dict:
        """Return the current budget status for a tenant."""
        if tenant_id not in self.budgets:
            return {}
        
        b = self.budgets[tenant_id]
        return {
            "total_budget": b.total_budget,
            "spent": b.spent,
            "reserved": b.reserved,
            "available": b.total_budget - b.spent - b.reserved,
            "currency": b.currency
        }

    def reset_quotas(self, tenant_id: str, resource_type: Optional[QuotaResourceType] = None):
        """Reset current usage to 0 for a specific quota or all quotas of a tenant."""
        if tenant_id not in self.quotas:
            return
            
        if resource_type:
            if resource_type in self.quotas[tenant_id]:
                self.quotas[tenant_id][resource_type].current_usage = 0.0
        else:
            for rt in self.quotas[tenant_id].values():
                rt.current_usage = 0.0

    def get_guardrail_report(self) -> Dict:
        """Generate a summary report of all tenants, quotas, budgets, and decisions."""
        return {
            "total_tenants_with_quotas": len(self.quotas),
            "total_tenants_with_budgets": len(self.budgets),
            "total_decisions_made": len(self.decisions),
            "decisions_by_action": self._aggregate_decisions()
        }
        
    def _aggregate_decisions(self) -> Dict[str, int]:
        counts = {action.value: 0 for action in GuardrailAction}
        for d in self.decisions:
            counts[d.action.value] += 1
        return counts
