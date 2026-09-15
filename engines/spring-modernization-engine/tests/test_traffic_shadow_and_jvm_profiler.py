from __future__ import annotations

import json
from pathlib import Path
import tempfile

from elmos_spring_modernization.spring_traffic_shadow_replay_engine import (
    ProductionTrafficLogParser,
    ShadowReplayRequest,
    SpringTrafficShadowReplayEngine,
)
from elmos_spring_modernization.spring_jvm_performance_profiler import (
    JvmRuntimeSnapshot,
    SpringJvmPerformanceProfiler,
)


def test_production_traffic_log_parser():
    # 1. Combined log format
    combined_line = '192.168.1.105 - - [15/Sep/2026:14:20:00 +0000] "GET /api/v1/orders?status=PAID&page=1 HTTP/1.1" 200 450'
    req1 = ProductionTrafficLogParser.parse_log_line(combined_line)
    assert req1 is not None
    assert req1.method == "GET"
    assert req1.path == "/api/v1/orders"
    assert req1.query_params == {"status": "PAID", "page": "1"}
    assert not req1.is_state_mutating
    assert req1.client_ip == "192.168.1.105"

    # 2. JSON access log format
    json_line = json.dumps({
        "method": "POST",
        "path": "/api/v1/checkout",
        "client_ip": "10.0.5.20",
        "body": {"orderId": "ORD-1234", "amount": 99.50},
        "headers": {"Content-Type": "application/json", "Authorization": "Bearer token123"},
    })
    req2 = ProductionTrafficLogParser.parse_log_line(json_line)
    assert req2 is not None
    assert req2.method == "POST"
    assert req2.path == "/api/v1/checkout"
    assert req2.is_state_mutating
    assert req2.body == {"orderId": "ORD-1234", "amount": 99.50}


def test_spring_traffic_shadow_replay_with_isolation():
    requests = [
        ShadowReplayRequest(
            method="GET",
            path="/api/v1/users/42",
        ),
        ShadowReplayRequest(
            method="POST",
            path="/api/v1/users",
            body={"name": "Alice", "role": "ADMIN"},
        ),
    ]

    intercepted_headers = []

    def mock_executor(env: str, req: ShadowReplayRequest):
        intercepted_headers.append((env, dict(req.headers)))
        if req.path == "/api/v1/users/42":
            return {"status": 200, "body": {"id": 42, "name": "Bob"}, "latency_ms": 10.0}
        else:
            return {"status": 201, "body": {"id": 101, "status": "CREATED"}, "latency_ms": 12.0}

    engine = SpringTrafficShadowReplayEngine(
        enforce_shadow_isolation=True,
        executor=mock_executor,
    )

    report = engine.replay_suite(requests)

    assert report.total_replayed == 2
    assert report.total_matched == 2
    assert report.consistency_rate == 100.0
    assert report.total_mutating_isolated == 1

    # Verify that POST request had shadow isolation headers attached
    post_headers = [h for env, h in intercepted_headers if "X-Elmos-Shadow-Mode" in h]
    assert len(post_headers) >= 2
    assert post_headers[0]["X-Elmos-Shadow-Mode"] == "isolated"
    assert post_headers[0]["X-Elmos-Rollback-Tx"] == "true"


def test_spring_jvm_performance_profiler():
    source_snap = JvmRuntimeSnapshot(
        runtime_name="LegacyProduction",
        java_version="1.8.0_382",
        spring_boot_version="2.7.18",
        startup_time_seconds=18.4,
        heap_peak_mb=1250.0,
        rss_peak_mb=1820.0,
        gc_pause_total_ms=450.0,
        gc_count=85,
        p50_latency_ms=12.5,
        p95_latency_ms=48.2,
        p99_latency_ms=120.0,
        throughput_rps=850.0,
    )

    target_snap = JvmRuntimeSnapshot(
        runtime_name="ModernizedProduction",
        java_version="21.0.4",
        spring_boot_version="3.5.3",
        startup_time_seconds=4.2,
        heap_peak_mb=720.0,
        rss_peak_mb=1150.0,
        gc_pause_total_ms=65.0,
        gc_count=18,
        p50_latency_ms=5.1,
        p95_latency_ms=19.4,
        p99_latency_ms=42.0,
        throughput_rps=1950.0,
    )

    report = SpringJvmPerformanceProfiler.compare(source_snap, target_snap)

    # Validate deltas
    metrics = report.comparison
    assert metrics.startup_improvement_pct > 70.0  # from 18.4s to 4.2s (>75% faster)
    assert metrics.heap_reduction_pct > 40.0       # from 1250MB to 720MB (>40% reduction)
    assert metrics.gc_pause_reduction_pct > 80.0   # from 450ms to 65ms (>85% reduction)
    assert metrics.throughput_gain_pct > 100.0     # from 850 to 1950 (>120% gain)

    # Check Markdown report
    assert "# Spring Boot 2.x vs 3.x JVM Performance Certification Report" in report.summary_markdown
    assert "✅ IMPROVED" in report.summary_markdown
    assert "✅ REDUCED" in report.summary_markdown
