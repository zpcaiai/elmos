import time
from typing import Dict, List, Optional
import uuid
from datetime import datetime, timezone
from elmos_mature_platform.types import (
    ScalingDirection, ScalingTrigger, ScalingPolicy, ScalingDecision,
    AutoscalingCapacityPlan, FairSchedulingQuota
)

class AutoscalingCapacityEngine:
    def __init__(self):
        self.policies: Dict[str, ScalingPolicy] = {}  # service_name -> policy
        self.quotas: Dict[str, Dict[str, FairSchedulingQuota]] = {}  # tenant_id -> service_name -> quota
        self.scaling_history: Dict[str, List[ScalingDecision]] = {}  # service_name -> decisions
        self.last_scaling_time: Dict[str, float] = {}  # service_name -> timestamp

    def register_policy(self, policy: ScalingPolicy) -> None:
        self.policies[policy.service_name] = policy
        if policy.service_name not in self.scaling_history:
            self.scaling_history[policy.service_name] = []
        if policy.service_name not in self.last_scaling_time:
            self.last_scaling_time[policy.service_name] = 0.0

    def evaluate_scaling(self, service_name: str, current_instances: int, metric_values: Dict[str, float]) -> ScalingDecision:
        policy = self.policies.get(service_name)
        if not policy:
            raise ValueError(f"No scaling policy registered for {service_name}")
            
        trigger = policy.trigger
        metric_key = trigger.value
        
        if metric_key not in metric_values:
            raise ValueError(f"Metric {metric_key} not provided in metric_values")
            
        current_val = metric_values[metric_key]
        decision_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        
        direction = ScalingDirection.NO_CHANGE
        target_instances = current_instances
        
        if current_val > policy.threshold_value:
            direction = ScalingDirection.SCALE_UP
            target_instances = min(current_instances + policy.scale_up_increment, policy.max_instances)
        elif current_val < policy.threshold_value * 0.5: # Simple scale down logic
            direction = ScalingDirection.SCALE_DOWN
            target_instances = max(current_instances - policy.scale_down_increment, policy.min_instances)

        if target_instances == current_instances:
            direction = ScalingDirection.NO_CHANGE

        return ScalingDecision(
            decision_id=decision_id,
            service_name=service_name,
            direction=direction,
            current_instances=current_instances,
            target_instances=target_instances,
            trigger=trigger,
            trigger_value=current_val,
            policy_id=policy.policy_id,
            timestamp=timestamp
        )

    def apply_scaling_decision(self, decision: ScalingDecision) -> Dict:
        if decision.service_name not in self.policies:
            decision.blocked = True
            decision.block_reason = "No policy registered"
            return {"status": "blocked", "decision": decision}

        if decision.direction == ScalingDirection.NO_CHANGE:
            return {"status": "no_change", "decision": decision}

        if self.check_cooldown(decision.service_name):
            decision.blocked = True
            decision.block_reason = "In cooldown period"
            decision.target_instances = decision.current_instances
            decision.direction = ScalingDirection.NO_CHANGE
            self.scaling_history[decision.service_name].append(decision)
            return {"status": "blocked", "decision": decision}

        policy = self.policies[decision.service_name]
        if decision.target_instances < policy.min_instances or decision.target_instances > policy.max_instances:
            decision.blocked = True
            decision.block_reason = "Bounds violated"
            decision.target_instances = max(policy.min_instances, min(decision.target_instances, policy.max_instances))
            
            if decision.target_instances == decision.current_instances:
                decision.direction = ScalingDirection.NO_CHANGE
                self.scaling_history[decision.service_name].append(decision)
                return {"status": "blocked", "decision": decision}

        self.last_scaling_time[decision.service_name] = time.time()
        self.scaling_history[decision.service_name].append(decision)
        return {"status": "applied", "decision": decision}

    def check_cooldown(self, service_name: str) -> bool:
        if service_name not in self.policies or service_name not in self.last_scaling_time:
            return False
            
        policy = self.policies[service_name]
        elapsed = time.time() - self.last_scaling_time[service_name]
        return elapsed < policy.cooldown_seconds

    def create_capacity_plan(self, service_name: str, current: int, peak_load: float, cost_per_instance: float) -> AutoscalingCapacityPlan:
        # Simple formula: instances needed = peak_load, + headroom
        base_needed = int(peak_load)
        if base_needed < 1:
            base_needed = 1
            
        headroom_pct = 20.0
        recommended = int(base_needed * (1 + headroom_pct / 100.0))
        
        # apply bounds if policy exists
        if service_name in self.policies:
            policy = self.policies[service_name]
            recommended = max(policy.min_instances, min(recommended, policy.max_instances))
            
        return AutoscalingCapacityPlan(
            plan_id=str(uuid.uuid4()),
            service_name=service_name,
            current_capacity=current,
            projected_peak_load=peak_load,
            recommended_capacity=recommended,
            headroom_pct=headroom_pct,
            estimated_monthly_cost=recommended * cost_per_instance
        )

    def set_fair_quota(self, quota: FairSchedulingQuota) -> None:
        if quota.tenant_id not in self.quotas:
            self.quotas[quota.tenant_id] = {}
        self.quotas[quota.tenant_id][quota.service_name] = quota

    def check_fair_scheduling(self, tenant_id: str, service_name: str, requested: int) -> Dict:
        if tenant_id not in self.quotas or service_name not in self.quotas[tenant_id]:
            raise PermissionError(f"No quota defined for tenant {tenant_id} on {service_name}")
            
        quota = self.quotas[tenant_id][service_name]
        total_requested = quota.current_usage + requested
        
        if total_requested <= quota.guaranteed_instances:
            quota.current_usage = total_requested
            return {"status": "allowed", "granted": requested, "reason": "Within guaranteed instances"}
            
        if total_requested <= quota.max_burst_instances:
            quota.current_usage = total_requested
            return {"status": "allowed", "granted": requested, "reason": "Within burst limit"}
            
        allowed = max(0, quota.max_burst_instances - quota.current_usage)
        quota.current_usage += allowed
        return {
            "status": "blocked", 
            "granted": allowed, 
            "reason": f"Requested {requested} exceeds max burst {quota.max_burst_instances}"
        }

    def protect_downstream_saturation(self, service_name: str, downstream_capacity: int, current_instances: int) -> ScalingDecision:
        decision_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        
        target_instances = current_instances
        direction = ScalingDirection.NO_CHANGE
        
        # If current_instances exceeds downstream_capacity, we must scale down or cap it
        if current_instances > downstream_capacity:
            target_instances = downstream_capacity
            direction = ScalingDirection.SCALE_DOWN
            
        decision = ScalingDecision(
            decision_id=decision_id,
            service_name=service_name,
            direction=direction,
            current_instances=current_instances,
            target_instances=target_instances,
            trigger=ScalingTrigger.MANUAL,
            trigger_value=float(downstream_capacity),
            policy_id="downstream_protection",
            timestamp=timestamp
        )
        
        if direction == ScalingDirection.SCALE_DOWN:
            if service_name not in self.scaling_history:
                self.scaling_history[service_name] = []
            self.scaling_history[service_name].append(decision)
            
        return decision

    def get_scaling_history(self, service_name: str) -> List[ScalingDecision]:
        return self.scaling_history.get(service_name, [])

    def get_capacity_report(self) -> Dict:
        return {
            "services": list(self.policies.keys()),
            "policies_count": len(self.policies),
            "total_scaling_events": sum(len(h) for h in self.scaling_history.values()),
            "capacity_utilization": {
                svc: len(h) for svc, h in self.scaling_history.items()
            }
        }
