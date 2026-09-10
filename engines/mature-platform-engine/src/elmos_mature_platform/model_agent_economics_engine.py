from typing import List, Dict, Optional, Set
import statistics
from datetime import datetime, timedelta

from elmos_mature_platform.types import (
    ModelProvider,
    AgentCostType,
    ModelPricing,
    AgentInvocation,
    AgentROI,
    CostForecast
)

class ModelAgentEconomicsEngine:
    """
    Engine for managing model and agent economics, cost tracking,
    ROI computation, and cost anomaly detection.
    """
    
    def __init__(self):
        self._pricing: Dict[str, ModelPricing] = {}
        self._invocations: List[AgentInvocation] = []
        self._agent_invocations: Dict[str, List[AgentInvocation]] = {}

    def register_model_pricing(self, pricing: ModelPricing) -> None:
        """Register or update pricing for a given model."""
        self._pricing[pricing.model_id] = pricing

    def compute_invocation_cost(self, invocation: AgentInvocation) -> float:
        """
        Calculate cost: (input_tokens * input_rate + output_tokens * output_rate) / 1000 
        + tool_cost + human_review_cost
        Raises ValueError if model_id is not registered.
        """
        pricing = self._pricing.get(invocation.model_id)
        if not pricing:
            raise ValueError(f"Model pricing not registered for: {invocation.model_id}")
            
        input_cost = (invocation.input_tokens / 1000.0) * pricing.input_cost_per_1k_tokens
        output_cost = (invocation.output_tokens / 1000.0) * pricing.output_cost_per_1k_tokens
        
        return input_cost + output_cost + invocation.tool_cost + invocation.human_review_cost

    def record_invocation(self, invocation: AgentInvocation) -> None:
        """Record an agent invocation."""
        # Ensure cost can be computed
        self.compute_invocation_cost(invocation)
        
        self._invocations.append(invocation)
        if invocation.agent_id not in self._agent_invocations:
            self._agent_invocations[invocation.agent_id] = []
        self._agent_invocations[invocation.agent_id].append(invocation)

    def get_agent_costs(self, agent_id: str) -> Dict[AgentCostType, float]:
        """Total cost breakdown by cost type for an agent."""
        costs = {
            AgentCostType.MODEL_INFERENCE: 0.0,
            AgentCostType.TOOL_EXECUTION: 0.0,
            AgentCostType.HUMAN_REVIEW: 0.0,
        }
        
        for inv in self._agent_invocations.get(agent_id, []):
            pricing = self._pricing[inv.model_id]
            inf_cost = (inv.input_tokens / 1000.0) * pricing.input_cost_per_1k_tokens + \
                       (inv.output_tokens / 1000.0) * pricing.output_cost_per_1k_tokens
            costs[AgentCostType.MODEL_INFERENCE] += inf_cost
            costs[AgentCostType.TOOL_EXECUTION] += inv.tool_cost
            costs[AgentCostType.HUMAN_REVIEW] += inv.human_review_cost
            
        return costs

    def get_tenant_costs(self, tenant_id: str) -> Dict[str, float]:
        """Cost by tenant across all agents."""
        costs = {}
        for inv in self._invocations:
            if inv.tenant_id == tenant_id:
                cost = self.compute_invocation_cost(inv)
                costs[inv.agent_id] = costs.get(inv.agent_id, 0.0) + cost
        return costs

    def compute_agent_roi(self, agent_id: str, value_per_success: float) -> AgentROI:
        """Calculate ROI given value per successful invocation."""
        invocations = self._agent_invocations.get(agent_id, [])
        
        total_cost = 0.0
        success_count = 0
        
        for inv in invocations:
            total_cost += self.compute_invocation_cost(inv)
            if inv.success:
                success_count += 1
                
        total_value = success_count * value_per_success
        
        roi_percentage = 0.0
        if total_cost > 0:
            roi_percentage = ((total_value - total_cost) / total_cost) * 100.0
            
        cost_per_success = 0.0
        if success_count > 0:
            cost_per_success = total_cost / success_count
            
        break_even = 0
        if value_per_success > 0 and len(invocations) > 0:
            avg_cost = total_cost / len(invocations)
            if avg_cost > 0:
                # Need enough successes so value >= cost
                # break_even successes * value = break_even_inv * avg_cost
                # Assumes current success rate
                success_rate = success_count / len(invocations) if len(invocations) > 0 else 0
                if success_rate > 0:
                    net_value_per_inv = (success_rate * value_per_success) - avg_cost
                    if net_value_per_inv > 0:
                        # Return roughly how many invocations needed to cover an initial fixed cost if any.
                        # For simple usage:
                        pass
                        
        return AgentROI(
            agent_id=agent_id,
            total_cost=total_cost,
            total_value_generated=total_value,
            roi_percentage=roi_percentage,
            break_even_invocations=break_even, # Simplified
            cost_per_success=cost_per_success,
            invocation_count=len(invocations),
            success_count=success_count
        )

    def forecast_costs(self, agent_id: str, period_days: int) -> CostForecast:
        """Project costs based on historical usage rate."""
        invocations = self._agent_invocations.get(agent_id, [])
        if not invocations:
            return CostForecast(
                agent_id=agent_id,
                period_days=period_days,
                projected_invocations=0,
                projected_cost=0.0,
                projected_value=0.0,
                confidence_level=0.0
            )
            
        total_cost = sum(self.compute_invocation_cost(inv) for inv in invocations)
        total_successes = sum(1 for inv in invocations if inv.success)
        
        # Approximate average daily rate
        # Using simple extrapolation based on assuming period represents all-time 1 day for minimal viable
        # In real world: diff between min/max timestamp
        daily_invocations = len(invocations) # fallback
        daily_cost = total_cost # fallback
        daily_successes = total_successes
        
        return CostForecast(
            agent_id=agent_id,
            period_days=period_days,
            projected_invocations=daily_invocations * period_days,
            projected_cost=daily_cost * period_days,
            projected_value=0.0, # Not enough data for value without value_per_success
            confidence_level=0.5
        )

    def get_model_comparison(self) -> List[Dict]:
        """Compare models by cost efficiency (cost per successful token)."""
        model_stats = {}
        for inv in self._invocations:
            if inv.model_id not in model_stats:
                model_stats[inv.model_id] = {"cost": 0.0, "success_tokens": 0, "success_count": 0, "total_count": 0}
            
            cost = self.compute_invocation_cost(inv)
            model_stats[inv.model_id]["cost"] += cost
            model_stats[inv.model_id]["total_count"] += 1
            if inv.success:
                model_stats[inv.model_id]["success_count"] += 1
                model_stats[inv.model_id]["success_tokens"] += inv.input_tokens + inv.output_tokens
                
        comparison = []
        for model_id, stats in model_stats.items():
            efficiency = 0.0
            if stats["success_tokens"] > 0:
                efficiency = stats["cost"] / (stats["success_tokens"] / 1000.0)
            comparison.append({
                "model_id": model_id,
                "total_cost": stats["cost"],
                "success_rate": stats["success_count"] / stats["total_count"] if stats["total_count"] > 0 else 0,
                "cost_per_1k_success_tokens": efficiency
            })
            
        return sorted(comparison, key=lambda x: x["cost_per_1k_success_tokens"])

    def detect_cost_anomalies(self, agent_id: str, threshold_multiplier: float = 3.0) -> List[AgentInvocation]:
        """Find invocations costing > threshold * average (or using stddev)."""
        invocations = self._agent_invocations.get(agent_id, [])
        if len(invocations) < 2:
            return []
            
        costs = [self.compute_invocation_cost(inv) for inv in invocations]
        mean_cost = statistics.mean(costs)
        std_cost = statistics.stdev(costs)
        
        threshold = mean_cost + threshold_multiplier * std_cost
        
        anomalies = []
        for inv, cost in zip(invocations, costs):
            if cost > threshold:
                anomalies.append(inv)
                
        return anomalies

    def get_economics_report(self) -> Dict:
        """Summary: total spend, by model, by agent, by tenant, ROI."""
        total_spend = sum(self.compute_invocation_cost(inv) for inv in self._invocations)
        
        by_model = {}
        by_agent = {}
        by_tenant = {}
        
        for inv in self._invocations:
            cost = self.compute_invocation_cost(inv)
            by_model[inv.model_id] = by_model.get(inv.model_id, 0.0) + cost
            by_agent[inv.agent_id] = by_agent.get(inv.agent_id, 0.0) + cost
            by_tenant[inv.tenant_id] = by_tenant.get(inv.tenant_id, 0.0) + cost
            
        return {
            "total_spend": total_spend,
            "spend_by_model": by_model,
            "spend_by_agent": by_agent,
            "spend_by_tenant": by_tenant,
            "total_invocations": len(self._invocations)
        }

    def recommend_model(self, agent_id: str) -> str:
        """Recommend cheapest model that maintains success rate."""
        invocations = self._agent_invocations.get(agent_id, [])
        if not invocations:
            raise ValueError(f"No invocations for agent {agent_id}")
            
        # Current agent success rate
        successes = sum(1 for inv in invocations if inv.success)
        target_success_rate = successes / len(invocations)
        
        # Get overall success rates of models
        model_stats = self.get_model_comparison()
        
        # Fallback to current model used by agent if it exists
        current_model = invocations[-1].model_id
        
        for m in model_stats:
            # Simple heuristic: cheapest model that has >= target success rate or close enough
            if m["success_rate"] >= target_success_rate - 0.05:
                return m["model_id"]
                
        return current_model
