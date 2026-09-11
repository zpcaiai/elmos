from datetime import datetime, timezone
import uuid
from typing import List, Optional, Dict, Any

from elmos_mature_platform.types import (
    TelemetryMetricType,
    TelemetryAnomalySeverity,
    TelemetryDataPoint,
    TelemetryAnomalyAlert,
    ObservabilityExportReport
)

class GlobalObservabilityTelemetryEngine:
    """Engine for processing and observing global telemetry data."""

    def __init__(self):
        # In-memory storage for data points and alerts
        self._data_points: List[TelemetryDataPoint] = []
        self._alerts: Dict[str, TelemetryAnomalyAlert] = {}
        # baselines mapping: tuple(metric_name, region) -> baseline_value
        self._baselines: Dict[tuple[str, str], float] = {}

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def ingest_datapoint(self, point: TelemetryDataPoint) -> str:
        """Store data point, auto-set timestamp if empty."""
        if not point.timestamp:
            point.timestamp = self._now_iso()
        self._data_points.append(point)
        return point.point_id

    def ingest_batch(self, points: List[TelemetryDataPoint]) -> int:
        """Batch ingest, return count ingested."""
        for point in points:
            self.ingest_datapoint(point)
        return len(points)

    def set_metric_baseline(self, metric_name: str, baseline_value: float, region: str = "global") -> None:
        """Store baseline value."""
        self._baselines[(metric_name, region)] = baseline_value

    def detect_anomalies(self, metric_name: str, threshold_deviation_pct: float = 20.0) -> List[TelemetryAnomalyAlert]:
        """
        Compare recent data points to baseline. If deviation exceeds threshold, create alert with severity 
        (CRITICAL for >100%, MAJOR for >50%, MINOR for >20%).
        """
        new_alerts = []
        for point in self._data_points:
            if point.metric_name != metric_name:
                continue

            baseline_val = self._baselines.get((metric_name, point.region))
            if baseline_val is None:
                continue

            if baseline_val == 0.0:
                if point.value != 0.0:
                    deviation = float('inf')
                else:
                    deviation = 0.0
            else:
                deviation = abs(point.value - baseline_val) / baseline_val * 100.0

            if deviation > threshold_deviation_pct:
                if deviation > 100.0:
                    severity = TelemetryAnomalySeverity.CRITICAL
                elif deviation > 50.0:
                    severity = TelemetryAnomalySeverity.MAJOR
                else:
                    severity = TelemetryAnomalySeverity.MINOR

                alert_id = str(uuid.uuid4())
                alert = TelemetryAnomalyAlert(
                    alert_id=alert_id,
                    metric_name=metric_name,
                    observed_value=point.value,
                    baseline_value=baseline_val,
                    deviation_pct=deviation,
                    severity=severity,
                    detected_at=self._now_iso(),
                    region=point.region,
                    service=point.service,
                    acknowledged=False,
                    resolution_notes=""
                )
                self._alerts[alert_id] = alert
                new_alerts.append(alert)

        return new_alerts

    def acknowledge_alert(self, alert_id: str, notes: str) -> TelemetryAnomalyAlert:
        """Mark alert acknowledged."""
        if alert_id not in self._alerts:
            raise ValueError(f"Alert ID {alert_id} not found.")
        
        alert = self._alerts[alert_id]
        alert.acknowledged = True
        alert.resolution_notes = notes
        return alert

    def query_metric_aggregate(self, metric_name: str, region: Optional[str] = None, service: Optional[str] = None) -> Dict[str, Any]:
        """Calculate count, min, max, avg, sum for matching points."""
        matching_points = [
            p for p in self._data_points 
            if p.metric_name == metric_name 
            and (region is None or p.region == region)
            and (service is None or p.service == service)
        ]
        
        count = len(matching_points)
        if count == 0:
            return {
                "count": 0,
                "min": 0.0,
                "max": 0.0,
                "avg": 0.0,
                "sum": 0.0
            }
            
        values = [p.value for p in matching_points]
        total_sum = sum(values)
        return {
            "count": count,
            "min": min(values),
            "max": max(values),
            "avg": total_sum / count,
            "sum": total_sum
        }

    def detect_cost_anomalies(self, service: str, expected_cost_per_hour: float, surge_multiplier: float = 1.5) -> List[TelemetryAnomalyAlert]:
        """Check points with tag cost_per_hour or metric_name matching cost."""
        new_alerts = []
        threshold_val = expected_cost_per_hour * surge_multiplier
        
        for point in self._data_points:
            if point.service != service:
                continue
                
            is_cost = False
            if "cost" in point.metric_name.lower():
                is_cost = True
            elif point.tags.get("cost_per_hour") is not None:
                is_cost = True
                
            if not is_cost:
                continue
                
            val_to_check = point.value
            if "cost_per_hour" in point.tags:
                try:
                    val_to_check = float(point.tags["cost_per_hour"])
                except ValueError:
                    pass

            if val_to_check > threshold_val:
                deviation = (val_to_check - expected_cost_per_hour) / expected_cost_per_hour * 100.0 if expected_cost_per_hour else float('inf')
                
                alert_id = str(uuid.uuid4())
                alert = TelemetryAnomalyAlert(
                    alert_id=alert_id,
                    metric_name=point.metric_name,
                    observed_value=val_to_check,
                    baseline_value=expected_cost_per_hour,
                    deviation_pct=deviation,
                    severity=TelemetryAnomalySeverity.CRITICAL if deviation > 100 else TelemetryAnomalySeverity.MAJOR,
                    detected_at=self._now_iso(),
                    region=point.region,
                    service=point.service,
                    acknowledged=False
                )
                self._alerts[alert_id] = alert
                new_alerts.append(alert)

        return new_alerts

    def export_evidence_report(self, time_window_hours: int = 24) -> ObservabilityExportReport:
        """Generate structured report."""
        services = set()
        regions = {}
        for point in self._data_points:
            if point.service:
                services.add(point.service)
            if point.region:
                regions[point.region] = regions.get(point.region, 0) + 1
                
        return ObservabilityExportReport(
            report_id=str(uuid.uuid4()),
            generated_at=self._now_iso(),
            time_window_hours=time_window_hours,
            total_datapoints=len(self._data_points),
            anomalies_detected=len(self._alerts),
            services_monitored=list(services),
            regional_breakdown=regions
        )

    def get_telemetry_summary(self) -> Dict[str, Any]:
        """Total points, total alerts, unacknowledged count, monitored services count."""
        services = set(p.service for p in self._data_points if p.service)
        unack = sum(1 for a in self._alerts.values() if not a.acknowledged)
        return {
            "total_points": len(self._data_points),
            "total_alerts": len(self._alerts),
            "unacknowledged_alerts": unack,
            "monitored_services": len(services)
        }

    def purge_old_datapoints(self, before_timestamp: str) -> int:
        """Delete data points older than timestamp, return count purged."""
        old_count = len(self._data_points)
        self._data_points = [p for p in self._data_points if p.timestamp >= before_timestamp]
        return old_count - len(self._data_points)
