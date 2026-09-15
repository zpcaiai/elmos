from __future__ import annotations

import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict
import unittest

import sys

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/operations/run_spring_dual_run_differential_engine.py"
SPEC = importlib.util.spec_from_file_location("spring_dual_run_differential_engine", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
subject = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = subject
SPEC.loader.exec_module(subject)


class SpringDualRunDifferentialEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.comparator = subject.ResponseComparator(
            float_epsilon=1e-6,
            normalize_uuids=True,
            strict_null=True,
        )

    # -------------------------------------------------------------------------
    # 1. Semantic Response Comparator: Deep Structural Equality
    # -------------------------------------------------------------------------

    def test_response_comparator_identical_json(self) -> None:
        src = {
            "status": 200,
            "headers": {"Content-Type": "application/json", "X-Custom": "prod"},
            "body": {
                "orderId": 1001,
                "customer": {"name": "Alice", "active": True},
                "items": [{"id": 1, "price": 49.95}, {"id": 2, "price": 19.99}],
                "tags": ["retail", "priority"],
            },
        }
        tgt = {
            "status": 200,
            "headers": {"content-type": "application/json", "x-custom": "prod"},
            "body": {
                "orderId": 1001,
                "customer": {"name": "Alice", "active": True},
                "items": [{"id": 1, "price": 49.95}, {"id": 2, "price": 19.99}],
                "tags": ["retail", "priority"],
            },
        }
        matches, diffs = self.comparator.compare_detailed(src, tgt)
        self.assertTrue(matches, f"Expected match but got diffs: {diffs}")
        self.assertEqual(diffs, [])

    def test_response_comparator_volatile_token_and_timestamp_masking(self) -> None:
        src = {
            "status": 200,
            "headers": {
                "Date": "Tue, 15 Sep 2026 10:00:00 GMT",
                "X-Request-Id": "req-source-12345",
                "Content-Type": "application/json",
            },
            "body": {
                "orderId": 1001,
                "timestamp": "2026-09-15T10:00:00.123Z",
                "_csrf": "csrf-source-token-9988",
                "date": "2026-09-15",
                "data": "stable-payload",
            },
        }
        tgt = {
            "status": 200,
            "headers": {
                "Date": "Tue, 15 Sep 2026 10:00:05 GMT",
                "X-Request-Id": "req-target-67890",
                "Content-Type": "application/json",
            },
            "body": {
                "orderId": 1001,
                "timestamp": "2026-09-15T10:00:05.456Z",
                "_csrf": "csrf-target-token-1122",
                "date": "2026-09-15",
                "data": "stable-payload",
            },
        }
        matches, diffs = self.comparator.compare_detailed(src, tgt, ignore_timestamps=True)
        self.assertTrue(matches, f"Expected volatile tokens to be masked, diffs: {diffs}")

    def test_response_comparator_uuid_normalization(self) -> None:
        src = {
            "status": 200,
            "body": {
                "sessionId": "550e8400-e29b-41d4-a716-446655440000",
                "name": "SessionA",
            },
        }
        tgt = {
            "status": 200,
            "body": {
                "sessionId": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
                "name": "SessionA",
            },
        }
        # With UUID normalization enabled
        matches_norm, _ = self.comparator.compare_detailed(src, tgt, normalize_uuids=True)
        self.assertTrue(matches_norm)

        # With UUID normalization disabled
        matches_strict, diffs = self.comparator.compare_detailed(src, tgt, normalize_uuids=False)
        self.assertFalse(matches_strict)
        self.assertTrue(any("sessionId" in d for d in diffs))

    def test_response_comparator_float_precision_epsilon(self) -> None:
        src = {"status": 200, "body": {"balance": 1000.0000001}}
        tgt_close = {"status": 200, "body": {"balance": 1000.0000002}}
        tgt_diverged = {"status": 200, "body": {"balance": 1000.05}}

        # Within epsilon 1e-5
        matches_close, _ = self.comparator.compare_detailed(src, tgt_close, float_epsilon=1e-5)
        self.assertTrue(matches_close)

        # Outside epsilon 1e-6
        matches_div, diffs_div = self.comparator.compare_detailed(src, tgt_diverged, float_epsilon=1e-6)
        self.assertFalse(matches_div)
        self.assertTrue(any("balance" in d for d in diffs_div))

    def test_response_comparator_strict_null_and_empty_distinction(self) -> None:
        src_null = {"status": 200, "body": {"detail": None}}
        tgt_empty = {"status": 200, "body": {"detail": ""}}
        tgt_missing = {"status": 200, "body": {}}

        # null vs empty string
        m1, diffs1 = self.comparator.compare_detailed(src_null, tgt_empty, strict_null=True)
        self.assertFalse(m1)
        self.assertTrue(any("detail" in d for d in diffs1))

        # null vs missing key
        m2, diffs2 = self.comparator.compare_detailed(src_null, tgt_missing, strict_null=True)
        self.assertFalse(m2)
        self.assertTrue(any("detail" in d for d in diffs2))

    # -------------------------------------------------------------------------
    # 2. Semantic Response Comparator: Negative Tests
    # -------------------------------------------------------------------------

    def test_response_comparator_status_mismatch(self) -> None:
        src = {"status": 200, "body": {"message": "ok"}}
        tgt = {"status": 403, "body": {"message": "forbidden"}}
        matches, diffs = self.comparator.compare_detailed(src, tgt)
        self.assertFalse(matches)
        self.assertTrue(any("Status mismatch" in d for d in diffs))

    def test_response_comparator_missing_and_unexpected_keys(self) -> None:
        src = {"status": 200, "body": {"id": 10, "legacyOnly": "old"}}
        tgt = {"status": 200, "body": {"id": 10, "modernOnly": "new"}}
        matches, diffs = self.comparator.compare_detailed(src, tgt)
        self.assertFalse(matches)
        self.assertTrue(any("legacyOnly" in d for d in diffs))
        self.assertTrue(any("modernOnly" in d for d in diffs))

    def test_response_comparator_array_mismatch(self) -> None:
        src = {"status": 200, "body": {"items": [1, 2, 3]}}
        tgt_len = {"status": 200, "body": {"items": [1, 2]}}
        tgt_val = {"status": 200, "body": {"items": [1, 99, 3]}}

        m1, d1 = self.comparator.compare_detailed(src, tgt_len)
        self.assertFalse(m1)
        self.assertTrue(any("Array length mismatch" in d for d in d1))

        m2, d2 = self.comparator.compare_detailed(src, tgt_val)
        self.assertFalse(m2)
        self.assertTrue(any("[1]" in d for d in d2))

    # -------------------------------------------------------------------------
    # 3. Synthetic Workload Generator
    # -------------------------------------------------------------------------

    def test_synthetic_workload_suite(self) -> None:
        suite = subject.SyntheticWorkloadGenerator.generate_suite(count=15)
        self.assertEqual(len(suite), 15)

        methods = {r.method for r in suite}
        self.assertIn("GET", methods)
        self.assertIn("POST", methods)
        self.assertIn("PUT", methods)

        paths = [r.path for r in suite]
        self.assertTrue(any("/actuator/health" in p for p in paths))
        self.assertTrue(any("/api/v1/orders" in p for p in paths))
        self.assertTrue(any("/api/v1/security/csrf" in p for p in paths))

    # -------------------------------------------------------------------------
    # 4. Replay Engine with Custom Executor
    # -------------------------------------------------------------------------

    def test_engine_replay_and_structured_evidence(self) -> None:
        def mock_executor(role: str, req: Dict[str, Any]) -> Dict[str, Any]:
            if req.get("path") == "/api/v1/orders":
                return {
                    "status": 200,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"orders": [{"id": 1, "total": 99.9}]}),
                    "latency_ms": 12.0,
                }
            elif req.get("path") == "/api/v1/diff":
                return {
                    "status": 200,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"role": role}),
                    "latency_ms": 8.0,
                }
            return {
                "status": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"status": "UP"}),
                "latency_ms": 5.0,
            }

        requests = [
            subject.ReplayRequest(method="GET", path="/api/v1/orders"),
            subject.ReplayRequest(method="GET", path="/api/v1/diff"),
            subject.ReplayRequest(method="GET", path="/actuator/health"),
        ]

        engine = subject.DualRunDifferentialEngine(executor=mock_executor)
        evidence = engine.run_workload(requests, warmup_count=0)

        self.assertEqual(evidence["schema_version"], "1.0.0")
        self.assertTrue(evidence["provenance"]["request_corpus_sha256"].startswith("sha256:"))
        self.assertEqual(evidence["summary"]["total_requests"], 3)
        self.assertEqual(evidence["summary"]["passed"], 2)
        self.assertEqual(evidence["summary"]["differed"], 1)
        self.assertEqual(evidence["summary"]["failed"], 0)
        self.assertEqual(evidence["summary"]["overall_verdict"], "DIFFERED")
        self.assertEqual(evidence["summary"]["certification_status"], "NOT_CERTIFIED")
        self.assertEqual(evidence["summary"]["gate_eligibility"], "INELIGIBLE")

    # -------------------------------------------------------------------------
    # 5. Live Mock HTTP Server Integration Test
    # -------------------------------------------------------------------------

    def test_live_http_dual_run_execution(self) -> None:
        class MockSpringHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("X-App", "spring-service")
                self.end_headers()
                response = {"status": "UP", "path": self.path, "version": "v1"}
                self.wfile.write(json.dumps(response).encode("utf-8"))

            def log_message(self, format, *args):
                pass  # Suppress console log spam during tests

        server_s = HTTPServer(("127.0.0.1", 0), MockSpringHandler)
        server_t = HTTPServer(("127.0.0.1", 0), MockSpringHandler)

        thread_s = threading.Thread(target=server_s.serve_forever, daemon=True)
        thread_t = threading.Thread(target=server_t.serve_forever, daemon=True)
        thread_s.start()
        thread_t.start()

        port_s = server_s.server_port
        port_t = server_t.server_port

        try:
            engine = subject.DualRunDifferentialEngine(
                source_url=f"http://127.0.0.1:{port_s}",
                target_url=f"http://127.0.0.1:{port_t}",
            )
            reqs = [
                subject.ReplayRequest(method="GET", path="/actuator/health"),
                subject.ReplayRequest(method="GET", path="/api/v1/items"),
            ]
            evidence = engine.run_workload(reqs, warmup_count=1)

            self.assertEqual(evidence["summary"]["total_requests"], 2)
            self.assertEqual(evidence["summary"]["passed"], 2)
            self.assertEqual(evidence["summary"]["differed"], 0)
            self.assertEqual(evidence["summary"]["overall_verdict"], "PASSED_LOCAL")
            self.assertEqual(evidence["summary"]["certification_status"], "NOT_CERTIFIED")
            self.assertEqual(evidence["summary"]["gate_eligibility"], "READY_FOR_EXTERNAL_GATE")
            self.assertGreater(evidence["performance"]["source_latency_avg_ms"], 0.0)
            self.assertGreater(evidence["performance"]["target_latency_avg_ms"], 0.0)
        finally:
            server_s.shutdown()
            server_t.shutdown()
            server_s.server_close()
            server_t.server_close()

    # -------------------------------------------------------------------------
    # 6. CLI Execution
    # -------------------------------------------------------------------------

    def test_cli_dry_run_execution(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            exit_code = subject.main([
                "--dry-run",
                "--synthetic-count", "4",
                "--output", tmp_path,
            ])
            self.assertEqual(exit_code, 0)
            with open(tmp_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data["summary"]["total_requests"], 4)
            self.assertEqual(data["summary"]["overall_verdict"], "PASSED_LOCAL")

            # Test divergence flag exits with code 1
            exit_code_div = subject.main([
                "--dry-run",
                "--simulate-divergence",
                "--synthetic-count", "4",
                "--output", tmp_path,
            ])
            self.assertEqual(exit_code_div, 1)
            with open(tmp_path, "r", encoding="utf-8") as f:
                data_div = json.load(f)
            self.assertEqual(data_div["summary"]["overall_verdict"], "DIFFERED")
        finally:
            Path(tmp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
