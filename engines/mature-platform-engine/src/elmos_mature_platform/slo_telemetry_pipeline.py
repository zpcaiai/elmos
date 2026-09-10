"""Real-Time SLO & Telemetry Pipeline for Elmos Mature Platform."""

from __future__ import annotations

import collections
from datetime import datetime, timezone
import math
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from elmos_mature_platform.types import (
    AlertRecord,
    HistogramSnapshot,
    MetricSample,
    SeverityLevel,
    SloDefinition,
    SloEvaluationResult,
    ZeroToleranceCategory,
)


class EnterpriseSloCollector:
    """Collects high-frequency telemetry samples, computes exact quantiles, and enforces SLO error budgets."""

    def __init__(self) -> None:
        self.samples: collections.defaultdict[str, List[MetricSample]] = collections.defaultdict(list)
        self.slos: Dict[str, SloDefinition] = {}
        self.active_alerts: Dict[str, AlertRecord] = {}
        self.alert_history: List[AlertRecord] = []
        self.zero_tolerance_counters: Dict[str, int] = {cat.value: 0 for cat in ZeroToleranceCategory}
        self.event_log: List[str] = []
        self._init_default_slos()

    def _log(self, message: str) -> None:
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        entry = f"[{ts}][SLO-PIPELINE] {message}"
        self.event_log.append(entry)

    def _init_default_slos(self) -> None:
        self.slos["api-availability"] = SloDefinition(
            slo_id="api-availability",
            name="API Availability (99.9% 2xx/3xx/4xx)",
            target_percentage=99.9,
            metric_name="http_request_success_ratio",
            threshold_value=1.0,
            window_seconds=3600,
        )
        self.slos["api-p99-latency"] = SloDefinition(
            slo_id="api-p99-latency",
            name="API P99 Latency (< 100ms)",
            target_percentage=99.0,
            metric_name="http_request_duration_ms",
            threshold_value=100.0,
            window_seconds=3600,
        )
        self.slos["replication-lag"] = SloDefinition(
            slo_id="replication-lag",
            name="Cross-Region Replication Lag (< 200ms)",
            target_percentage=99.5,
            metric_name="cross_region_replication_lag_ms",
            threshold_value=200.0,
            window_seconds=3600,
        )

    def record_sample(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        now = time.time()
        self.samples[name].append(MetricSample(name=name, value=value, timestamp=now, labels=labels or {}))

    record_metric_sample = record_sample

    def record_zero_tolerance_event(self, category: ZeroToleranceCategory, details: str) -> None:
        self.zero_tolerance_counters[category.value] += 1
        self._log(f"CRITICAL ZERO-TOLERANCE VIOLATION: {category.value} -> {details}")

    def compute_histogram(self, metric_name: str, window_seconds: Optional[int] = None) -> HistogramSnapshot:
        """Computes statistical quantiles over recorded values."""
        raw = self.samples.get(metric_name, [])
        if window_seconds:
            cutoff = time.time() - window_seconds
            vals = [s.value for s in raw if s.timestamp >= cutoff]
        else:
            vals = [s.value for s in raw]

        if not vals:
            return HistogramSnapshot(
                count=0,
                total_sum=0.0,
                p50=0.0,
                p75=0.0,
                p90=0.0,
                p95=0.0,
                p99=0.0,
                p999=0.0,
                min_val=0.0,
                max_val=0.0,
            )

        sorted_vals = sorted(vals)
        n = len(sorted_vals)

        def quantile(q: float) -> float:
            idx = int(math.ceil(q * n)) - 1
            return sorted_vals[max(0, min(idx, n - 1))]

        return HistogramSnapshot(
            count=n,
            total_sum=sum(sorted_vals),
            p50=quantile(0.50),
            p75=quantile(0.75),
            p90=quantile(0.90),
            p95=quantile(0.95),
            p99=quantile(0.99),
            p999=quantile(0.999),
            min_val=sorted_vals[0],
            max_val=sorted_vals[-1],
        )

    def evaluate_slo(self, slo_id: str) -> SloEvaluationResult:
        """Evaluates an SLO target and computes error budget burn rates."""
        slo = self.slos.get(slo_id)
        if not slo:
            raise KeyError(f"SLO {slo_id} not registered")

        cutoff_1h = time.time() - 3600
        cutoff_6h = time.time() - 21600

        samples = self.samples.get(slo.metric_name, [])
        if not samples:
            return SloEvaluationResult(
                slo_id=slo_id,
                target_percentage=slo.target_percentage,
                actual_percentage=100.0,
                is_compliant=True,
                error_budget_remaining=1.0,
                burn_rate_1h=0.0,
                burn_rate_6h=0.0,
            )

        # Count good events vs total events in 1h window
        samples_1h = [s for s in samples if s.timestamp >= cutoff_1h]
        samples_6h = [s for s in samples if s.timestamp >= cutoff_6h]

        total_1h = len(samples_1h) or 1
        if "ratio" in slo.metric_name:
            good_1h = len([s for s in samples_1h if s.value >= slo.threshold_value])
        else:
            good_1h = len([s for s in samples_1h if s.value <= slo.threshold_value])

        actual_pct = (good_1h / total_1h) * 100.0
        is_compliant = actual_pct >= slo.target_percentage

        # Allowed error rate = (100 - target_percentage) / 100
        allowed_error_fraction = max(1e-6, (100.0 - slo.target_percentage) / 100.0)
        actual_error_fraction_1h = max(0.0, 1.0 - (actual_pct / 100.0))
        burn_rate_1h = actual_error_fraction_1h / allowed_error_fraction

        # 6h burn rate
        total_6h = len(samples_6h) or 1
        if "ratio" in slo.metric_name:
            good_6h = len([s for s in samples_6h if s.value >= slo.threshold_value])
        else:
            good_6h = len([s for s in samples_6h if s.value <= slo.threshold_value])
        actual_error_fraction_6h = max(0.0, 1.0 - (good_6h / total_6h))
        burn_rate_6h = actual_error_fraction_6h / allowed_error_fraction

        error_budget_remaining = max(0.0, 1.0 - burn_rate_1h * (3600.0 / (30 * 86400.0)))

        # Trigger alerts if multi-window burn rate thresholds are exceeded (Google SRE book standard: 14.4x for 1h, 6x for 6h)
        if burn_rate_1h >= 14.4 or burn_rate_6h >= 6.0 or not is_compliant:
            self._trigger_alert(slo_id, SeverityLevel.CRITICAL if burn_rate_1h >= 14.4 else SeverityLevel.HIGH, f"SLO {slo.name} burn rate high (1h={burn_rate_1h:.2f}x, 6h={burn_rate_6h:.2f}x, actual={actual_pct:.2f}%)")

        return SloEvaluationResult(
            slo_id=slo_id,
            target_percentage=slo.target_percentage,
            actual_percentage=actual_pct,
            is_compliant=is_compliant,
            error_budget_remaining=error_budget_remaining,
            burn_rate_1h=burn_rate_1h,
            burn_rate_6h=burn_rate_6h,
        )

    def _trigger_alert(self, slo_id: str, severity: SeverityLevel, message: str) -> None:
        if slo_id in self.active_alerts:
            return
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        alert = AlertRecord(
            alert_id=f"alert-{len(self.alert_history)+1:04d}",
            slo_id=slo_id,
            severity=severity,
            message=message,
            triggered_at=now,
        )
        self.active_alerts[slo_id] = alert
        self.alert_history.append(alert)
        self._log(f"ALERT TRIGGERED [{severity.value}] for SLO {slo_id}: {message}")

    def resolve_alert(self, slo_id: str) -> None:
        if slo_id in self.active_alerts:
            alert = self.active_alerts.pop(slo_id)
            alert.resolved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            self._log(f"ALERT RESOLVED for SLO {slo_id}")

    def evaluate_performance_regression(
        self,
        baseline_p95: float,
        current_p95: float,
        baseline_p99: float,
        current_p99: float,
        baseline_cost: float,
        current_cost: float,
    ) -> Tuple[bool, Dict[str, float]]:
        """Validates latency and cost regressions against strict thresholds."""
        p95_reg = max(0.0, (current_p95 - baseline_p95) / max(1e-6, baseline_p95))
        p99_reg = max(0.0, (current_p99 - baseline_p99) / max(1e-6, baseline_p99))
        cost_reg = max(0.0, (current_cost - baseline_cost) / max(1e-6, baseline_cost))

        metrics = {
            "p95_latency_regression": p95_reg,
            "p99_latency_regression": p99_reg,
            "unit_cost_regression": cost_reg,
        }

        # Strict profile thresholds: p95 <= 0.05, p99 <= 0.10, cost <= 0.08
        valid = (p95_reg <= 0.05) and (p99_reg <= 0.10) and (cost_reg <= 0.08)
        return valid, metrics
