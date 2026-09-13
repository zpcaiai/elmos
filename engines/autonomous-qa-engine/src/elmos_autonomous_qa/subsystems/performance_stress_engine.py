"""Industrial Performance Stress & Soak Leak Regression Engine.

Calculates exact percentiles (P50/P90/P95/P99), verifies Little's Law throughput,
and detects memory leaks using ordinary least squares (OLS) regression over time.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import List, Optional, Tuple


@dataclass
class LatencyPercentiles:
    min_ms: float
    p50_ms: float
    p90_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    mean_ms: float
    std_dev_ms: float


@dataclass
class MemoryLeakReport:
    has_memory_leak: bool
    slope_bytes_per_sec: float
    r_squared: float
    start_bytes: float
    end_bytes: float


class PerformanceStressEngine:
    """Statistical performance metrics and memory soak testing."""

    @staticmethod
    def calculate_percentiles(latencies_ms: List[float]) -> LatencyPercentiles:
        if not latencies_ms:
            raise ValueError("latencies_ms cannot be empty")

        sorted_vals = sorted(latencies_ms)
        n = len(sorted_vals)

        def percentile(p: float) -> float:
            idx = (n - 1) * p
            low = int(math.floor(idx))
            high = int(math.ceil(idx))
            if low == high:
                return sorted_vals[low]
            weight = idx - low
            return sorted_vals[low] * (1.0 - weight) + sorted_vals[high] * weight

        mean = sum(sorted_vals) / n
        variance = sum((x - mean) ** 2 for x in sorted_vals) / n
        std_dev = math.sqrt(variance)

        return LatencyPercentiles(
            min_ms=round(sorted_vals[0], 2),
            p50_ms=round(percentile(0.50), 2),
            p90_ms=round(percentile(0.90), 2),
            p95_ms=round(percentile(0.95), 2),
            p99_ms=round(percentile(0.99), 2),
            max_ms=round(sorted_vals[-1], 2),
            mean_ms=round(mean, 2),
            std_dev_ms=round(std_dev, 2),
        )

    @staticmethod
    def verify_littles_law(
        concurrency_l: float,
        throughput_lambda: float,
        mean_latency_sec_w: float,
        tolerance: float = 0.15,
    ) -> Tuple[bool, float]:
        """Verifies L = lambda * W within proportional tolerance."""
        theoretical_l = throughput_lambda * mean_latency_sec_w
        if theoretical_l == 0.0:
            error = 0.0 if concurrency_l == 0.0 else 1.0
        else:
            error = abs(concurrency_l - theoretical_l) / theoretical_l
        return error <= tolerance, round(error, 4)

    @staticmethod
    def detect_memory_leak(
        timestamps_sec: List[float],
        memory_bytes: List[float],
        leak_threshold_bytes_sec: float = 1024.0,
    ) -> MemoryLeakReport:
        """Uses OLS linear regression to detect memory growth over time."""
        n = len(timestamps_sec)
        if n < 3 or len(memory_bytes) != n:
            raise ValueError("Must provide at least 3 synchronous time and memory samples")

        x_mean = sum(timestamps_sec) / n
        y_mean = sum(memory_bytes) / n

        numerator = sum((timestamps_sec[i] - x_mean) * (memory_bytes[i] - y_mean) for i in range(n))
        denominator = sum((timestamps_sec[i] - x_mean) ** 2 for i in range(n))

        if denominator == 0.0:
            slope = 0.0
        else:
            slope = numerator / denominator

        intercept = y_mean - slope * x_mean

        ss_tot = sum((memory_bytes[i] - y_mean) ** 2 for i in range(n))
        ss_res = sum((memory_bytes[i] - (slope * timestamps_sec[i] + intercept)) ** 2 for i in range(n))
        r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 1.0

        is_leak = (slope > leak_threshold_bytes_sec) and (r2 >= 0.75)
        return MemoryLeakReport(
            has_memory_leak=is_leak,
            slope_bytes_per_sec=round(slope, 2),
            r_squared=round(r2, 4),
            start_bytes=memory_bytes[0],
            end_bytes=memory_bytes[-1],
        )
