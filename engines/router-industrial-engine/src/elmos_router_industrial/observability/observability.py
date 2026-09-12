"""OpenTelemetry-compatible tracing, health metrics, and benchmark evals.

Ensures every inference step is traceable without logging raw prompt bodies,
tracks windowed health metrics, and evaluates task-class benchmark scores.
"""

from __future__ import annotations

from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import threading
import time
from typing import Any, Iterator, Mapping

from ..domain.contracts import TaskClass
from ..registry.registry import HealthSnapshot


@dataclass
class SpanRecord:
    spanName: str
    traceId: str
    spanId: str
    startTime: float
    endTime: float = 0.0
    attributes: dict[str, Any] = field(default_factory=dict)
    status: str = "OK"  # "OK", "ERROR"
    errorClass: str | None = None

    @property
    def durationMs(self) -> float:
        return max(0.0, (self.endTime - self.startTime) * 1000.0)


class TelemetryTracer:
    """Thread-safe OpenTelemetry-compatible in-memory span recorder."""

    def __init__(self) -> None:
        self._spans: list[SpanRecord] = []
        self._lock = threading.Lock()

    @contextmanager
    def start_span(
        self,
        name: str,
        trace_id: str,
        initial_attributes: Mapping[str, Any] | None = None,
    ) -> Iterator[SpanRecord]:
        span_id = hashlib.sha256(f"{name}:{trace_id}:{time.time()}".encode()).hexdigest()[:16]
        span = SpanRecord(
            spanName=name,
            traceId=trace_id,
            spanId=span_id,
            startTime=time.time(),
            attributes=dict(initial_attributes or {}),
        )
        try:
            yield span
        except Exception as e:
            span.status = "ERROR"
            span.errorClass = type(e).__name__
            span.attributes["error.message"] = str(e)
            raise
        finally:
            span.endTime = time.time()
            with self._lock:
                self._spans.append(span)

    def get_spans(self, trace_id: str | None = None) -> list[SpanRecord]:
        with self._lock:
            if trace_id:
                return [s for s in self._spans if s.traceId == trace_id]
            return list(self._spans)

    @staticmethod
    def hash_prompt(prompt_text: str) -> str:
        """Computes secure SHA-256 hash of prompt text to avoid logging bodies."""
        return hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()


class MetricsCollector:
    """Thread-safe collector for router performance, reliability, and cost metrics."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}
        self._latencies: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def increment(self, metric: str, count: int = 1) -> None:
        with self._lock:
            self._counters[metric] = self._counters.get(metric, 0) + count

    def record_latency(self, metric: str, duration_ms: float) -> None:
        with self._lock:
            if metric not in self._latencies:
                self._latencies[metric] = []
            self._latencies[metric].append(duration_ms)

    def get_counter(self, metric: str) -> int:
        with self._lock:
            return self._counters.get(metric, 0)

    def get_percentiles(self, metric: str) -> tuple[float, float, float]:
        """Returns (p50, p95, p99) latencies."""
        with self._lock:
            vals = sorted(self._latencies.get(metric, []))
            if not vals:
                return (0.0, 0.0, 0.0)
            n = len(vals)
            p50 = vals[int(n * 0.50)]
            p95 = vals[min(n - 1, int(n * 0.95))]
            p99 = vals[min(n - 1, int(n * 0.99))]
            return (round(p50, 2), round(p95, 2), round(p99, 2))


class HealthTracker:
    """Sliding-window health tracker for deployments."""

    def __init__(self, window_size: int = 100) -> None:
        self.window_size = window_size
        self._results: dict[str, deque[bool]] = {}  # deployment_id -> deque of success booleans
        self._latencies: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def record_outcome(self, deployment_id: str, success: bool, latency_ms: float) -> None:
        with self._lock:
            if deployment_id not in self._results:
                self._results[deployment_id] = deque(maxlen=self.window_size)
                self._latencies[deployment_id] = deque(maxlen=self.window_size)
            self._results[deployment_id].append(success)
            self._latencies[deployment_id].append(latency_ms)

    def snapshot(self, deployment_id: str) -> HealthSnapshot:
        with self._lock:
            results = self._results.get(deployment_id, deque())
            latencies = sorted(self._latencies.get(deployment_id, deque()))

            if not results:
                return HealthSnapshot(deploymentId=deployment_id)

            success_rate = sum(1 for r in results if r) / len(results)
            p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))] if latencies else 500.0

            return HealthSnapshot(
                deploymentId=deployment_id,
                availability=round(success_rate, 4),
                p95LatencyMs=round(p95, 2),
                rateLimitPressure=0.0,
                timeoutRate=round(1.0 - success_rate, 4),
                successRate=round(success_rate, 4),
            )


@dataclass(frozen=True)
class BenchmarkEvalResult:
    taskClass: TaskClass
    modelAlias: str
    sampleCount: int
    successRate: float
    avgLatencyMs: float
    avgCost: float
    qualityScore: float
    passedBaseline: bool


class TaskBenchmarkHarness:
    """Evaluation harness for benchmark-based quality calibration across Elmos task classes."""

    def __init__(self, baseline_scores: Mapping[str, float] | None = None) -> None:
        self.baselines = dict(baseline_scores or {})

    def evaluate_model(
        self,
        task_class: TaskClass,
        model_alias: str,
        results: list[tuple[bool, float, float]],  # (success, latency_ms, cost)
    ) -> BenchmarkEvalResult:
        if not results:
            return BenchmarkEvalResult(
                taskClass=task_class,
                modelAlias=model_alias,
                sampleCount=0,
                successRate=0.0,
                avgLatencyMs=0.0,
                avgCost=0.0,
                qualityScore=0.0,
                passedBaseline=False,
            )

        n = len(results)
        succ_cnt = sum(1 for s, _, _ in results if s)
        success_rate = succ_cnt / n
        avg_lat = sum(l for _, l, _ in results) / n
        avg_cost = sum(c for _, _, c in results) / n
        quality_score = round(success_rate * 0.8 + min(1.0, 1000.0 / max(1.0, avg_lat)) * 0.2, 4)

        baseline = self.baselines.get(task_class.value, 0.80)
        passed = quality_score >= baseline

        return BenchmarkEvalResult(
            taskClass=task_class,
            modelAlias=model_alias,
            sampleCount=n,
            successRate=round(success_rate, 4),
            avgLatencyMs=round(avg_lat, 2),
            avgCost=round(avg_cost, 6),
            qualityScore=quality_score,
            passedBaseline=passed,
        )
