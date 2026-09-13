from typing import List, Dict, Optional
import uuid

from elmos_mature_platform.types import (
    AgentDeployment,
    AgentDeploymentMode,
    ShadowComparison,
    AgentComparisonVerdict,
    CanaryMetrics,
    CanaryPromotionDecision
)


class AgentShadowCanaryEngine:
    def __init__(self):
        self.deployments: Dict[str, AgentDeployment] = {}
        self.shadow_comparisons: Dict[str, ShadowComparison] = {}
        self.canary_metrics: Dict[str, CanaryMetrics] = {}
        self.original_prod_deployments: Dict[str, str] = {}  # canary_id -> prod_id

    def create_deployment(self, deployment: AgentDeployment) -> AgentDeployment:
        """Register agent deployment."""
        if deployment.deployment_id in self.deployments:
            raise ValueError(f"Deployment {deployment.deployment_id} already exists")
        self.deployments[deployment.deployment_id] = deployment
        return deployment

    def start_shadow(self, production_id: str, shadow_id: str) -> ShadowComparison:
        """Start shadow comparison between production and shadow agent."""
        if production_id not in self.deployments:
            raise ValueError(f"Production deployment {production_id} not found")
        if shadow_id not in self.deployments:
            raise ValueError(f"Shadow deployment {shadow_id} not found")
        
        prod_dep = self.deployments[production_id]
        shadow_dep = self.deployments[shadow_id]
        
        if prod_dep.mode != AgentDeploymentMode.PRODUCTION:
            raise ValueError("Target production deployment is not in PRODUCTION mode")
        if shadow_dep.mode != AgentDeploymentMode.SHADOW:
            raise ValueError("Target shadow deployment is not in SHADOW mode")
        if shadow_dep.traffic_pct != 0.0:
            raise ValueError("Shadow deployment must not receive real traffic")

        comp_id = str(uuid.uuid4())
        comp = ShadowComparison(
            comparison_id=comp_id,
            production_deployment_id=production_id,
            shadow_deployment_id=shadow_id,
        )
        self.shadow_comparisons[comp_id] = comp
        return comp

    def record_shadow_result(self, comparison_id: str, production_output: str, shadow_output: str, prod_latency_ms: float, shadow_latency_ms: float):
        """Record a single request's comparison."""
        if comparison_id not in self.shadow_comparisons:
            raise ValueError(f"Comparison {comparison_id} not found")
        
        comp = self.shadow_comparisons[comparison_id]
        comp.request_count += 1
        
        # very simple rolling average latency diff
        latency_diff = shadow_latency_ms - prod_latency_ms
        comp.avg_latency_diff_ms = ((comp.avg_latency_diff_ms * (comp.request_count - 1)) + latency_diff) / comp.request_count
        
        if production_output == shadow_output:
            comp.match_count += 1
        else:
            comp.divergence_count += 1
            if len(comp.divergence_examples) < 10:
                comp.divergence_examples.append(f"Prod: {production_output} | Shadow: {shadow_output}")

    def get_shadow_comparison(self, comparison_id: str) -> ShadowComparison:
        """Get current shadow comparison status."""
        if comparison_id not in self.shadow_comparisons:
            raise ValueError(f"Comparison {comparison_id} not found")
        return self.shadow_comparisons[comparison_id]

    def evaluate_shadow_verdict(self, comparison_id: str) -> AgentComparisonVerdict:
        """Evaluate overall: EQUIVALENT if match_rate > 95%, DEGRADED if < 80%, else DIVERGENT."""
        comp = self.get_shadow_comparison(comparison_id)
        if comp.request_count == 0:
            comp.verdict = AgentComparisonVerdict.UNKNOWN
            return comp.verdict
            
        match_rate = comp.match_count / comp.request_count
        
        if match_rate > 0.95:
            comp.verdict = AgentComparisonVerdict.EQUIVALENT
        elif match_rate < 0.80:
            comp.verdict = AgentComparisonVerdict.DEGRADED
        else:
            comp.verdict = AgentComparisonVerdict.DIVERGENT
            
        return comp.verdict

    def start_canary(self, deployment_id: str, traffic_pct: float):
        """Start canary with specified traffic percentage."""
        if deployment_id not in self.deployments:
            raise ValueError(f"Deployment {deployment_id} not found")
        
        dep = self.deployments[deployment_id]
        if dep.mode != AgentDeploymentMode.CANARY:
            raise ValueError("Target deployment is not in CANARY mode")
        if not (1.0 <= traffic_pct <= 50.0):
            raise ValueError("Canary traffic_pct must be between 1.0 and 50.0")
            
        # Find active production to scale down
        prod_deps = [d for d in self.deployments.values() if d.mode == AgentDeploymentMode.PRODUCTION and d.is_active and d.traffic_pct > 0]
        if not prod_deps:
            raise ValueError("No active production deployment found to route traffic from")
            
        # Simplest case: pick the first active production deployment
        prod_dep = prod_deps[0]
        if prod_dep.traffic_pct < traffic_pct:
            raise ValueError("Production deployment doesn't have enough traffic to route to canary")
            
        self.original_prod_deployments[deployment_id] = prod_dep.deployment_id
        
        prod_dep.traffic_pct -= traffic_pct
        dep.traffic_pct = traffic_pct
        
        self.canary_metrics[deployment_id] = CanaryMetrics(deployment_id=deployment_id)

    def record_canary_request(self, deployment_id: str, success: bool, latency_ms: float, cost: float):
        """Record canary request metrics."""
        if deployment_id not in self.canary_metrics:
            raise ValueError(f"Canary {deployment_id} is not active or metrics missing")
            
        metrics = self.canary_metrics[deployment_id]
        metrics.total_requests += 1
        if not success:
            metrics.error_count += 1
            
        metrics.success_rate = (metrics.total_requests - metrics.error_count) / metrics.total_requests
        
        # P50/P99 simple approximations
        # In a real system, we'd use a histogram or sorted list, but for now we'll do simple moving max logic
        # For an in-memory mock we can just store the max and average to mock them roughly or keep a list if small
        # To avoid OOM in test, we just do something trivial
        if metrics.p50_latency_ms == 0:
            metrics.p50_latency_ms = latency_ms
        else:
            metrics.p50_latency_ms = (metrics.p50_latency_ms * 0.9) + (latency_ms * 0.1)
            
        if latency_ms > metrics.p99_latency_ms:
            metrics.p99_latency_ms = latency_ms
            
        metrics.cost_per_request = ((metrics.cost_per_request * (metrics.total_requests - 1)) + cost) / metrics.total_requests

    def get_canary_metrics(self, deployment_id: str) -> CanaryMetrics:
        """Get current canary metrics."""
        if deployment_id not in self.canary_metrics:
            raise ValueError(f"Canary {deployment_id} metrics not found")
        return self.canary_metrics[deployment_id]

    def evaluate_canary_promotion(self, deployment_id: str, min_requests: int, min_success_rate: float) -> CanaryPromotionDecision:
        """Decide: promote if success_rate >= threshold and enough requests."""
        if deployment_id not in self.canary_metrics:
            raise ValueError(f"Canary {deployment_id} metrics not found")
            
        metrics = self.canary_metrics[deployment_id]
        
        if metrics.total_requests < min_requests:
            return CanaryPromotionDecision(
                deployment_id=deployment_id,
                promote=False,
                reason="Insufficient requests for evaluation",
                metrics=metrics,
                rollback_recommended=False
            )
            
        if metrics.success_rate < min_success_rate:
            return CanaryPromotionDecision(
                deployment_id=deployment_id,
                promote=False,
                reason="Success rate below minimum threshold",
                metrics=metrics,
                rollback_recommended=True
            )
            
        return CanaryPromotionDecision(
            deployment_id=deployment_id,
            promote=True,
            reason="Success rate and request count met",
            metrics=metrics,
            rollback_recommended=False
        )

    def promote_canary(self, deployment_id: str):
        """Promote canary to production (set traffic to 100%, deactivate old production)."""
        if deployment_id not in self.deployments:
            raise ValueError(f"Canary {deployment_id} not found")
        dep = self.deployments[deployment_id]
        if dep.mode != AgentDeploymentMode.CANARY:
            raise ValueError("Deployment is not a CANARY")
            
        prod_id = self.original_prod_deployments.get(deployment_id)
        if not prod_id:
            raise ValueError("Original production deployment mapping not found for canary")
            
        prod_dep = self.deployments[prod_id]
        
        # Deactivate old production, taking its traffic
        remaining_traffic = prod_dep.traffic_pct
        prod_dep.traffic_pct = 0.0
        prod_dep.is_active = False
        
        # Promote canary to production
        dep.mode = AgentDeploymentMode.PRODUCTION
        dep.traffic_pct += remaining_traffic
        # ensure it's fully promoted (though normally it might just sum to 100)
        
        # Cleanup mapping
        del self.original_prod_deployments[deployment_id]

    def rollback_canary(self, deployment_id: str):
        """Rollback canary, restore original production traffic."""
        if deployment_id not in self.deployments:
            raise ValueError(f"Canary {deployment_id} not found")
        dep = self.deployments[deployment_id]
        if dep.mode != AgentDeploymentMode.CANARY:
            raise ValueError("Deployment is not a CANARY")
            
        prod_id = self.original_prod_deployments.get(deployment_id)
        if not prod_id:
            raise ValueError("Original production deployment mapping not found for canary")
            
        prod_dep = self.deployments[prod_id]
        
        # Restore traffic
        prod_dep.traffic_pct += dep.traffic_pct
        
        # Deactivate canary
        dep.traffic_pct = 0.0
        dep.is_active = False
        
        # Cleanup mapping
        del self.original_prod_deployments[deployment_id]

    def kill_switch(self, deployment_id: str):
        """Kill switch: can deactivate any deployment instantly."""
        if deployment_id not in self.deployments:
            raise ValueError(f"Deployment {deployment_id} not found")
            
        dep = self.deployments[deployment_id]
        
        if dep.mode == AgentDeploymentMode.CANARY:
            # Safe rollback if it's an active canary
            if deployment_id in self.original_prod_deployments and dep.traffic_pct > 0:
                self.rollback_canary(deployment_id)
                return
                
        # Zero out traffic
        dep.traffic_pct = 0.0
        dep.is_active = False

    def get_deployment_history(self) -> List[AgentDeployment]:
        """All deployments"""
        return list(self.deployments.values())

    def get_active_deployments(self) -> List[AgentDeployment]:
        """Currently active deployments"""
        return [d for d in self.deployments.values() if d.is_active]
