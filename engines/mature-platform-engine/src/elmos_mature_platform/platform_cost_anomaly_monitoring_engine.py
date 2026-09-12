"""Platform Cost Anomaly Monitoring Engine (Batch 39 - Skill 1362).

Real-time cost & consumption anomaly detection, statistical baselines,
runaway workload identification, automated circuit breaking, and SRE alerting.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Dict, List, Optional, Tuple

from elmos_mature_platform.types import (
    CostAnomalyAlert,
    CostAnomalySeverity,
    CostDataPoint,
    CostMetricType,
    CostMitigationAction,
    CostThrottlePolicy,
)


class PlatformCostAnomalyMonitoringEngine:
    """Industrial engine for platform cost anomaly detection and mitigation (B39)."""

    def __init__(self, baseline_min_samples: int = 5, default_z_threshold: float = 3.0):
        self.baseline_min_samples = baseline_min_samples
        self.default_z_threshold = default_z_threshold
        # History: tenant_id -> metric_type -> List[CostDataPoint]
        self._history: Dict[str, Dict[str, List[CostDataPoint]]] = {}
        self._policies: Dict[str, Dict[str, CostThrottlePolicy]] = {}
        self._alerts: Dict[str, CostAnomalyAlert] = {}
        self._audit_log: List[Dict[str, Any]] = []

    def set_throttle_policy(self, policy: CostThrottlePolicy) -> None:
        """Register or update a cost throttle policy for tenant and metric."""
        t_policies = self._policies.setdefault(policy.tenant_id, {})
        t_policies[policy.metric_type.value] = policy
        self._record_audit("policy_updated", policy.tenant_id, {
            "metric": policy.metric_type.value,
            "hourly_cap": policy.hourly_spend_cap_usd,
            "daily_cap": policy.daily_spend_cap_usd,
        })

    def get_throttle_policy(self, tenant_id: str, metric_type: CostMetricType) -> Optional[CostThrottlePolicy]:
        """Fetch throttle policy for a specific tenant and metric."""
        return self._policies.get(tenant_id, {}).get(metric_type.value)

    def record_cost_data_point(self, point: CostDataPoint) -> Optional[CostAnomalyAlert]:
        """Record a new cost data point, check against baseline & policies, and alert if anomalous."""
        tenant_history = self._history.setdefault(point.tenant_id, {})
        metric_history = tenant_history.setdefault(point.metric_type.value, [])

        # Check policy cap before appending
        policy = self.get_throttle_policy(point.tenant_id, point.metric_type)
        if policy:
            policy.current_hourly_spend_usd += point.amount_usd
            policy.current_daily_spend_usd += point.amount_usd
            if policy.current_hourly_spend_usd > policy.hourly_spend_cap_usd or \
               policy.current_daily_spend_usd > policy.daily_spend_cap_usd:
                policy.circuit_breaker_tripped = True
                self._record_audit("circuit_breaker_tripped", point.tenant_id, {
                    "metric": point.metric_type.value,
                    "hourly_spend": policy.current_hourly_spend_usd,
                    "daily_spend": policy.current_daily_spend_usd,
                })

        alert = None
        # Detect statistical anomaly if sufficient history
        if len(metric_history) >= self.baseline_min_samples:
            amounts = [p.amount_usd for p in metric_history]
            mean_val = sum(amounts) / len(amounts)
            variance = sum((x - mean_val) ** 2 for x in amounts) / len(amounts)
            std_val = math.sqrt(variance) if variance > 1e-9 else 0.01

            z_score = (point.amount_usd - mean_val) / std_val if std_val > 0 else 0.0

            if z_score >= 2.0 or (policy and policy.circuit_breaker_tripped):
                alert = self._create_anomaly_alert(
                    point=point,
                    mean=mean_val,
                    std=std_val,
                    z_score=z_score,
                    policy=policy,
                )

        metric_history.append(point)
        return alert

    def _create_anomaly_alert(
        self,
        point: CostDataPoint,
        mean: float,
        std: float,
        z_score: float,
        policy: Optional[CostThrottlePolicy],
    ) -> CostAnomalyAlert:
        """Create and classify a cost anomaly alert."""
        # Classify severity
        if z_score >= 5.0 or (policy and policy.circuit_breaker_tripped and z_score >= 3.0):
            severity = CostAnomalySeverity.CRITICAL
            action = CostMitigationAction.TRIP_CIRCUIT_BREAKER
        elif z_score >= 3.5:
            severity = CostAnomalySeverity.HIGH
            action = CostMitigationAction.THROTTLE_RATE_LIMIT
        elif z_score >= 2.5:
            severity = CostAnomalySeverity.MEDIUM
            action = CostMitigationAction.ALERT_ONCALL
        else:
            severity = CostAnomalySeverity.LOW
            action = CostMitigationAction.NOTIFY_ONLY

        # Determine probable root cause reason
        if point.metric_type == CostMetricType.LLM_TOKENS:
            reason = "Probable runaway recursive prompt loop or high-volume agent fan-out"
        elif point.metric_type == CostMetricType.COMPUTE_CPU_HOURS:
            reason = "Probable unconstrained infinite retry or CPU spinning loop"
        elif point.metric_type == CostMetricType.STORAGE_GB_MONTHS:
            reason = "Persistent uncollected artifact or checkpoint accumulation"
        elif point.metric_type == CostMetricType.NETWORK_EGRESS_GB:
            reason = "Anomalous network egress burst - potential exfiltration or duplicate transfer"
        else:
            reason = f"Unusual consumption spike in {point.metric_type.value}"

        alert_id = f"alert-{point.tenant_id}-{point.metric_type.value}-{int(datetime.now(timezone.utc).timestamp())}"
        alert = CostAnomalyAlert(
            alert_id=alert_id,
            tenant_id=point.tenant_id,
            metric_type=point.metric_type,
            current_amount_usd=round(point.amount_usd, 4),
            baseline_mean_usd=round(mean, 4),
            baseline_std_usd=round(std, 4),
            z_score=round(z_score, 2),
            severity=severity,
            recommended_action=action,
            triggered_at=datetime.now(timezone.utc).isoformat(),
            anomaly_reason=reason,
        )
        self._alerts[alert_id] = alert
        self._record_audit("cost_anomaly_detected", point.tenant_id, {
            "alert_id": alert_id,
            "severity": severity.value,
            "z_score": alert.z_score,
            "action": action.value,
        })
        return alert

    def resolve_alert(self, alert_id: str) -> bool:
        """Mark an active alert as resolved."""
        alert = self._alerts.get(alert_id)
        if not alert:
            return False
        alert.is_resolved = True
        alert.resolved_at = datetime.now(timezone.utc).isoformat()
        self._record_audit("alert_resolved", alert.tenant_id, {"alert_id": alert_id})
        return True

    def reset_circuit_breaker(self, tenant_id: str, metric_type: CostMetricType) -> bool:
        """Reset a tripped circuit breaker after remediation."""
        policy = self.get_throttle_policy(tenant_id, metric_type)
        if not policy:
            return False
        policy.circuit_breaker_tripped = False
        policy.current_hourly_spend_usd = 0.0
        self._record_audit("circuit_breaker_reset", tenant_id, {"metric": metric_type.value})
        return True

    def list_alerts(self, tenant_id: Optional[str] = None, unresolved_only: bool = False) -> List[CostAnomalyAlert]:
        """List recorded alerts with optional filtering."""
        alerts = list(self._alerts.values())
        if tenant_id:
            alerts = [a for a in alerts if a.tenant_id == tenant_id]
        if unresolved_only:
            alerts = [a for a in alerts if not a.is_resolved]
        return alerts

    def get_tenant_cost_summary(self, tenant_id: str) -> Dict[str, Any]:
        """Compute aggregate cost metrics and statistics for a tenant."""
        tenant_data = self._history.get(tenant_id, {})
        total_spend = 0.0
        breakdown_by_metric: Dict[str, Dict[str, Any]] = {}

        for metric_name, points in tenant_data.items():
            metric_total = sum(p.amount_usd for p in points)
            total_spend += metric_total
            amounts = [p.amount_usd for p in points]
            mean_val = (sum(amounts) / len(amounts)) if amounts else 0.0
            breakdown_by_metric[metric_name] = {
                "total_usd": round(metric_total, 4),
                "data_points_count": len(points),
                "mean_amount_usd": round(mean_val, 4),
                "max_amount_usd": round(max(amounts), 4) if amounts else 0.0,
            }

        unresolved_alerts = [a for a in self._alerts.values() if a.tenant_id == tenant_id and not a.is_resolved]

        return {
            "tenant_id": tenant_id,
            "total_spend_usd": round(total_spend, 4),
            "metric_breakdown": breakdown_by_metric,
            "active_anomalies_count": len(unresolved_alerts),
            "highest_active_severity": max([a.severity.value for a in unresolved_alerts], default="none"),
        }

    def _record_audit(self, action: str, tenant_id: str, details: Dict[str, Any]) -> None:
        self._audit_log.append({
            "action": action,
            "tenant_id": tenant_id,
            "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def get_audit_log(self) -> List[Dict[str, Any]]:
        return list(self._audit_log)
