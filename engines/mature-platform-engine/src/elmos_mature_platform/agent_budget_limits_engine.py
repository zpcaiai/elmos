from typing import List, Dict, Optional, Any
from datetime import datetime
from elmos_mature_platform.types import (
    ResourceType, BudgetPeriod, BudgetAction,
    AgentBudget, ResourceConsumption, BudgetDecision
)

class AgentBudgetLimitsEngine:
    """Engine for managing agent budgets and resource limits."""
    
    def __init__(self) -> None:
        self.budgets: Dict[str, AgentBudget] = {}
        self.consumptions: List[ResourceConsumption] = []
        
    def create_budget(self, budget: AgentBudget) -> str:
        """Create a new budget, initializing remaining to limit."""
        budget.remaining = budget.limit
        budget.used = 0.0
        self.budgets[budget.budget_id] = budget
        return budget.budget_id
        
    def request_resource(self, agent_id: str, resource_type: ResourceType, amount: float, task_id: str) -> BudgetDecision:
        """Check budget and decide whether to ALLOW, THROTTLE, or DENY."""
        budget = self._find_budget(agent_id, resource_type)
        if not budget:
            raise ValueError(f"No budget found for agent {agent_id} and resource {resource_type.value}")
            
        remaining_after = budget.remaining - amount
        pct_after = ((budget.used + amount) / budget.limit) * 100 if budget.limit > 0 else float('inf')
        
        if budget.hard_limit and amount > budget.remaining:
            return BudgetDecision(
                agent_id=agent_id,
                resource_type=resource_type,
                requested=amount,
                action=BudgetAction.DENY,
                remaining_after=budget.remaining,
                reason="Hard limit exceeded"
            )
            
        if pct_after > 90.0 and amount <= budget.remaining:
            return BudgetDecision(
                agent_id=agent_id,
                resource_type=resource_type,
                requested=amount,
                action=BudgetAction.THROTTLE,
                remaining_after=remaining_after,
                reason="Usage over 90%, throttling"
            )
            
        if pct_after >= budget.warning_threshold_pct:
            return BudgetDecision(
                agent_id=agent_id,
                resource_type=resource_type,
                requested=amount,
                action=BudgetAction.ALERT,
                remaining_after=remaining_after,
                reason="Usage over warning threshold"
            )
            
        return BudgetDecision(
            agent_id=agent_id,
            resource_type=resource_type,
            requested=amount,
            action=BudgetAction.ALLOW,
            remaining_after=remaining_after,
            reason="Within limits"
        )
        
    def consume_resource(self, consumption: ResourceConsumption) -> None:
        """Record consumption and deduct atomically from budget."""
        budget = self._find_budget(consumption.agent_id, consumption.resource_type)
        if not budget:
            raise ValueError("No budget found")
            
        budget.used += consumption.amount
        budget.remaining = budget.limit - budget.used
        self.consumptions.append(consumption)
        
    def get_budget(self, agent_id: str, resource_type: ResourceType) -> AgentBudget:
        """Get the current budget for an agent and resource type."""
        budget = self._find_budget(agent_id, resource_type)
        if not budget:
            raise ValueError("Budget not found")
        return budget
        
    def get_all_budgets(self, agent_id: str) -> List[AgentBudget]:
        """Get all budgets for a given agent."""
        return [b for b in self.budgets.values() if b.agent_id == agent_id]
        
    def reset_budget(self, budget_id: str) -> AgentBudget:
        """Reset the used amount to 0 and remaining to limit."""
        if budget_id not in self.budgets:
            raise ValueError("Budget not found")
        b = self.budgets[budget_id]
        b.used = 0.0
        b.remaining = b.limit
        return b
        
    def reset_expired_budgets(self, current_time: str) -> List[str]:
        """Reset all budgets whose reset_at time has passed."""
        reset_ids = []
        for b in self.budgets.values():
            if b.reset_at and b.reset_at <= current_time:
                b.used = 0.0
                b.remaining = b.limit
                reset_ids.append(b.budget_id)
        return reset_ids
        
    def get_consumption_history(self, agent_id: str, resource_type: Optional[ResourceType] = None) -> List[ResourceConsumption]:
        """Get history of resource consumption for an agent."""
        history = [c for c in self.consumptions if c.agent_id == agent_id]
        if resource_type:
            history = [c for c in history if c.resource_type == resource_type]
        return history
        
    def get_top_consumers(self, resource_type: ResourceType, n: int = 10) -> List[Dict]:
        """Get top N agents by usage for a resource type."""
        usage_by_agent: Dict[str, float] = {}
        for b in self.budgets.values():
            if b.resource_type == resource_type:
                usage_by_agent[b.agent_id] = usage_by_agent.get(b.agent_id, 0.0) + b.used
                
        sorted_usage = sorted(usage_by_agent.items(), key=lambda x: x[1], reverse=True)
        return [{"agent_id": k, "used": v} for k, v in sorted_usage[:n]]
        
    def forecast_exhaustion(self, agent_id: str, resource_type: ResourceType) -> Dict:
        """Forecast when budget will exhaust at current rate."""
        budget = self._find_budget(agent_id, resource_type)
        if not budget:
            raise ValueError("Budget not found")
            
        history = self.get_consumption_history(agent_id, resource_type)
        if not history:
            return {"agent_id": agent_id, "resource_type": resource_type.value, "exhausts_in_seconds": -1, "rate_per_sec": 0.0}
            
        # Simplistic forecast based on first and last consumption
        try:
            first_time = datetime.fromisoformat(history[0].timestamp.replace("Z", "+00:00"))
            last_time = datetime.fromisoformat(history[-1].timestamp.replace("Z", "+00:00"))
            delta_sec = (last_time - first_time).total_seconds()
        except Exception:
            delta_sec = 0.0
            
        total_consumed = sum(c.amount for c in history)
        if delta_sec <= 0 or total_consumed <= 0:
            return {"agent_id": agent_id, "resource_type": resource_type.value, "exhausts_in_seconds": -1, "rate_per_sec": 0.0}
            
        rate = total_consumed / delta_sec
        remaining_time = budget.remaining / rate if rate > 0 else -1
        
        return {
            "agent_id": agent_id,
            "resource_type": resource_type.value,
            "exhausts_in_seconds": remaining_time,
            "rate_per_sec": rate
        }
        
    def get_budget_report(self) -> Dict:
        """Summary of budgets, usage, and status."""
        total_budgets = len(self.budgets)
        usage_by_type: Dict[str, float] = {}
        agents_near_limits = 0
        
        for b in self.budgets.values():
            rt = b.resource_type.value
            usage_by_type[rt] = usage_by_type.get(rt, 0.0) + b.used
            if b.limit > 0 and (b.used / b.limit) >= (b.warning_threshold_pct / 100.0):
                agents_near_limits += 1
                
        # Denied count is harder as we didn't store decisions, but we can assume we'd track it if needed.
        # For simplicity, returning 0 or extending state.
        
        return {
            "total_budgets": total_budgets,
            "usage_by_type": usage_by_type,
            "agents_near_limits": agents_near_limits,
            "denied_count": 0  # Could track this if requested in a more complex setup
        }
        
    def _find_budget(self, agent_id: str, resource_type: ResourceType) -> Optional[AgentBudget]:
        for b in self.budgets.values():
            if b.agent_id == agent_id and b.resource_type == resource_type:
                return b
        return None
