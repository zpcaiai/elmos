"""Comprehensive unit tests for ShadowDiffEngine.

Validates the 13-dimension shadow differential comparison, response normalization,
database state reconciliation, transaction rollback verification, and latency regression checks.
"""

from __future__ import annotations

import unittest

from elmos_legacy_web_modernization.shadow_diff_engine import (
    DatabaseDifferential,
    HttpExchange,
    ShadowDiffEngine,
    ShadowDiffResult,
    TableSnapshot,
)


class ShadowDiffEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = ShadowDiffEngine(latency_tolerance_ratio=2.0)

    def test_dimensions_constant(self) -> None:
        expected = (
            "route",
            "protocol",
            "view",
            "binding",
            "validation",
            "navigation",
            "session",
            "security",
            "transaction",
            "database",
            "externalEffects",
            "concurrency",
            "performance",
        )
        self.assertEqual(self.engine.DIMENSIONS, expected)

    def test_table_snapshot_from_rows_deterministic_checksums(self) -> None:
        rows = [
            {"id": 2, "name": "Bob", "amount": 100.5},
            {"id": 1, "name": "Alice", "amount": 50.0},
        ]
        snapshot = TableSnapshot.from_rows("orders", rows)
        self.assertEqual(snapshot.table_name, "orders")
        self.assertEqual(len(snapshot.rows), 2)
        self.assertEqual(len(snapshot.row_checksums), 2)
        # Checksums must be sorted alphabetically
        self.assertEqual(snapshot.row_checksums, tuple(sorted(snapshot.row_checksums)))

    def test_normalize_headers_strips_ignored_and_lowercases(self) -> None:
        headers = {
            "Content-Type": "application/json; charset=UTF-8 ",
            "Date": "Wed, 21 Oct 2025 07:28:00 GMT",
            "Server": "Apache/2.4.41",
            "X-Trace-Id": "trace-12345",
            "X-Custom-Header": "value123",
        }
        normalized = self.engine.normalize_headers(headers)
        self.assertIn("content-type", normalized)
        self.assertEqual(normalized["content-type"], "application/json; charset=UTF-8")
        self.assertIn("x-custom-header", normalized)
        self.assertEqual(normalized["x-custom-header"], "value123")
        self.assertNotIn("date", normalized)
        self.assertNotIn("server", normalized)
        self.assertNotIn("x-trace-id", normalized)

    def test_normalize_body_json_masks_volatile_fields(self) -> None:
        raw_json = '{"id": 101, "timestamp": "2026-09-12T01:00:00Z", "orderUuid": "abc-123", "amount": 99.9}'
        normalized = self.engine.normalize_body(raw_json)
        self.assertIsInstance(normalized, dict)
        self.assertEqual(normalized["id"], 101)
        self.assertEqual(normalized["amount"], 99.9)
        self.assertEqual(normalized["timestamp"], "<VOLATILE_NORMALIZED>")
        self.assertEqual(normalized["orderUuid"], "<VOLATILE_NORMALIZED>")

    def test_normalize_body_html_or_text_collapses_whitespace(self) -> None:
        raw_html = "  <html> \n\t <body>\n <h1> Welcome </h1> </body></html>  "
        normalized = self.engine.normalize_body(raw_html)
        self.assertEqual(normalized, "<html> <body> <h1> Welcome </h1> </body></html>")

    def test_normalize_body_empty(self) -> None:
        self.assertEqual(self.engine.normalize_body("   "), "")

    def test_identical_exchanges_pass(self) -> None:
        legacy = HttpExchange(
            method="GET",
            path="/api/orders/42",
            status_code=200,
            headers={"Content-Type": "application/json"},
            body='{"id": 42, "status": "CONFIRMED"}',
            latency_ms=10.0,
        )
        target = HttpExchange(
            method="GET",
            path="/api/orders/42",
            status_code=200,
            headers={"Content-Type": "application/json"},
            body='{"id": 42, "status": "CONFIRMED"}',
            latency_ms=12.0,
        )
        result = self.engine.compare_exchanges(legacy, target)
        self.assertTrue(result.equivalent)
        self.assertEqual(result.verdict, "PASS")
        self.assertFalse(result.critical_regression)
        self.assertEqual(len(result.mismatches), 0)
        for score in result.dimension_scores.values():
            self.assertEqual(score, 1.0)

    def test_route_mismatch_fails_route_dimension(self) -> None:
        legacy = HttpExchange(
            method="GET",
            path="/api/orders",
            status_code=200,
            headers={},
            body="OK",
        )
        target = HttpExchange(
            method="POST",
            path="/api/orders",
            status_code=200,
            headers={},
            body="OK",
        )
        result = self.engine.compare_exchanges(legacy, target)
        self.assertFalse(result.equivalent)
        self.assertEqual(result.verdict, "FAIL")
        self.assertEqual(result.dimension_scores["route"], 0.0)
        self.assertTrue(result.critical_regression)
        self.assertTrue(any("Route mismatch" in m for m in result.mismatches))

    def test_status_code_mismatch_and_server_error_failure(self) -> None:
        legacy = HttpExchange(
            method="POST",
            path="/api/orders",
            status_code=400,
            headers={},
            body="Bad Request",
        )
        target = HttpExchange(
            method="POST",
            path="/api/orders",
            status_code=500,
            headers={},
            body="Internal Server Error",
        )
        result = self.engine.compare_exchanges(legacy, target)
        self.assertFalse(result.equivalent)
        self.assertEqual(result.dimension_scores["protocol"], 0.0)
        self.assertEqual(result.dimension_scores["validation"], 0.0)
        self.assertTrue(result.critical_regression)

    def test_body_mismatch_fails_view_and_binding(self) -> None:
        legacy = HttpExchange(
            method="GET",
            path="/api/profile",
            status_code=200,
            headers={},
            body='{"name": "Alice", "role": "USER"}',
        )
        target = HttpExchange(
            method="GET",
            path="/api/profile",
            status_code=200,
            headers={},
            body='{"name": "Alice", "role": "ADMIN"}',
        )
        result = self.engine.compare_exchanges(legacy, target)
        self.assertFalse(result.equivalent)
        self.assertEqual(result.dimension_scores["view"], 0.0)
        self.assertEqual(result.dimension_scores["binding"], 0.0)
        self.assertTrue(any("Response body mismatch" in m for m in result.mismatches))

    def test_content_type_mismatch_penalizes_protocol(self) -> None:
        legacy = HttpExchange(
            method="GET",
            path="/api/data",
            status_code=200,
            headers={"Content-Type": "application/json"},
            body="data",
        )
        target = HttpExchange(
            method="GET",
            path="/api/data",
            status_code=200,
            headers={"Content-Type": "text/plain"},
            body="data",
        )
        result = self.engine.compare_exchanges(legacy, target)
        self.assertFalse(result.equivalent)
        self.assertEqual(result.dimension_scores["protocol"], 0.5)

    def test_database_snapshot_parity_matching(self) -> None:
        legacy = HttpExchange(method="POST", path="/api/items", status_code=201, headers={}, body='{"id": 1}')
        target = HttpExchange(method="POST", path="/api/items", status_code=201, headers={}, body='{"id": 1}')

        db_rows = [{"id": 1, "sku": "ITEM-1", "qty": 10}]
        leg_db = TableSnapshot.from_rows("inventory", db_rows)
        tar_db = TableSnapshot.from_rows("inventory", db_rows)

        result = self.engine.compare_exchanges(legacy, target, legacy_db=leg_db, target_db=tar_db)
        self.assertTrue(result.equivalent)
        self.assertEqual(result.dimension_scores["database"], 1.0)
        self.assertEqual(len(result.database_diffs), 1)
        self.assertTrue(result.database_diffs[0].matched)

    def test_database_snapshot_mismatch_fails_database_and_tx(self) -> None:
        legacy = HttpExchange(method="POST", path="/api/items", status_code=201, headers={}, body='{"id": 1}')
        target = HttpExchange(method="POST", path="/api/items", status_code=201, headers={}, body='{"id": 1}')

        leg_db = TableSnapshot.from_rows("inventory", [{"id": 1, "qty": 10}])
        tar_db = TableSnapshot.from_rows("inventory", [{"id": 1, "qty": 9}])

        result = self.engine.compare_exchanges(legacy, target, legacy_db=leg_db, target_db=tar_db)
        self.assertFalse(result.equivalent)
        self.assertEqual(result.dimension_scores["database"], 0.0)
        self.assertEqual(result.dimension_scores["transaction"], 0.0)
        self.assertTrue(result.critical_regression)
        self.assertEqual(len(result.database_diffs), 1)
        self.assertFalse(result.database_diffs[0].matched)

    def test_transaction_rollback_leak_detection(self) -> None:
        legacy = HttpExchange(method="POST", path="/api/fault", status_code=500, headers={}, body="fail")
        target = HttpExchange(method="POST", path="/api/fault", status_code=500, headers={}, body="fail")

        leg_db = TableSnapshot.from_rows("orders", [])
        tar_db = TableSnapshot.from_rows("orders", [{"id": 999, "status": "LEAKED"}])

        result = self.engine.compare_exchanges(
            legacy,
            target,
            legacy_db=leg_db,
            target_db=tar_db,
            transaction_rolled_back=True,
        )
        self.assertFalse(result.equivalent)
        self.assertEqual(result.dimension_scores["transaction"], 0.0)
        self.assertTrue(any("rollback failure" in m for m in result.mismatches))

    def test_performance_latency_regression(self) -> None:
        legacy = HttpExchange(method="GET", path="/api/search", status_code=200, headers={}, body="res", latency_ms=50.0)
        # Latency ratio threshold is 2.0x -> 100ms. 120ms exceeds 50.0 * 2.0
        target = HttpExchange(method="GET", path="/api/search", status_code=200, headers={}, body="res", latency_ms=120.0)

        result = self.engine.compare_exchanges(legacy, target)
        self.assertFalse(result.equivalent)
        self.assertEqual(result.dimension_scores["performance"], 0.5)
        self.assertTrue(any("Performance latency regression" in m for m in result.mismatches))


if __name__ == "__main__":
    unittest.main()
