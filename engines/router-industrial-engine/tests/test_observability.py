"""Tests for Observability, OpenTelemetry Tracing, Health, and Evals."""

from __future__ import annotations

import unittest

from elmos_router_industrial.domain.contracts import TaskClass
from elmos_router_industrial.observability.observability import (
    HealthTracker,
    MetricsCollector,
    TaskBenchmarkHarness,
    TelemetryTracer,
)


class TestObservability(unittest.TestCase):
    def test_telemetry_tracer_span_and_prompt_redaction(self) -> None:
        tracer = TelemetryTracer()
        trace_id = "trace_abc123"

        prompt = "SELECT * FROM users WHERE ssn = '123-45-6789';"
        prompt_hash = tracer.hash_prompt(prompt)

        with tracer.start_span("elmos.route.evaluate", trace_id, {"promptHash": prompt_hash}) as span:
            span.attributes["tenantId"] = "tenant_test"

        spans = tracer.get_spans(trace_id)
        self.assertEqual(len(spans), 1)
        record = spans[0]
        self.assertEqual(record.spanName, "elmos.route.evaluate")
        self.assertEqual(record.status, "OK")
        self.assertIn("promptHash", record.attributes)
        # Ensure raw prompt string is not present
        self.assertNotIn("123-45-6789", str(record.attributes))

    def test_metrics_collector_percentiles(self) -> None:
        metrics = MetricsCollector()
        for lat in [100.0, 200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0, 900.0, 1000.0]:
            metrics.record_latency("provider.latency", lat)

        p50, p95, p99 = metrics.get_percentiles("provider.latency")
        self.assertEqual(p50, 600.0)
        self.assertEqual(p95, 1000.0)
        self.assertEqual(p99, 1000.0)

    def test_health_tracker_window(self) -> None:
        tracker = HealthTracker(window_size=10)
        dep_id = "dep_test"

        # 9 successes, 1 failure
        for _ in range(9):
            tracker.record_outcome(dep_id, True, 200.0)
        tracker.record_outcome(dep_id, False, 1500.0)

        snapshot = tracker.snapshot(dep_id)
        self.assertAlmostEqual(snapshot.availability, 0.9)
        self.assertAlmostEqual(snapshot.successRate, 0.9)
        self.assertAlmostEqual(snapshot.timeoutRate, 0.1)

    def test_task_benchmark_harness(self) -> None:
        harness = TaskBenchmarkHarness(baseline_scores={"CODE_GENERATION": 0.85})

        # Results: 10 samples, 9 success, 200ms latency, $0.01 cost
        results = [(True, 200.0, 0.01) for _ in range(9)] + [(False, 500.0, 0.01)]
        res = harness.evaluate_model(TaskClass.CODE_GENERATION, "gpt-4o", results)

        self.assertEqual(res.sampleCount, 10)
        self.assertEqual(res.successRate, 0.90)
        self.assertTrue(res.passedBaseline)


if __name__ == "__main__":
    unittest.main()
