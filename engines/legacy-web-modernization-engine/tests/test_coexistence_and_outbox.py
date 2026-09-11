"""Comprehensive tests for Coexistence Strangler Proxy and Outbox Dual-Write Auditor."""

from __future__ import annotations

import json
import unittest

from elmos_legacy_web_modernization.coexistence_strangler_proxy import (
    CoexistenceStranglerProxy,
    OutboxDualWriteAuditor,
    RouteDestination,
)


class TestCoexistenceAndOutbox(unittest.TestCase):
    """Unit tests for Strangler proxy routing and Outbox event differential auditing."""

    def setUp(self) -> None:
        self.proxy = CoexistenceStranglerProxy(
            legacy_base_url="http://legacy.app.internal:8080/app",
            modern_base_url="http://modern.app.internal:8081/modern-app",
        )
        self.auditor = OutboxDualWriteAuditor()

    # ── CoexistenceStranglerProxy Tests ──

    def test_default_fallback_to_legacy(self) -> None:
        decision = self.proxy.route_request("/api/v1/orders/123", method="GET")
        self.assertEqual(decision.destination, RouteDestination.LEGACY)
        self.assertEqual(decision.target_url, "http://legacy.app.internal:8080/app/api/v1/orders/123")
        self.assertEqual(decision.matched_rule, "default-legacy-fallback")
        self.assertTrue(decision.audit_trace_id)

    def test_migrated_route_exact_and_prefix(self) -> None:
        self.proxy.register_migrated_route("/api/v1/users")
        self.proxy.register_migrated_route("/api/v1/catalog/products")

        # Exact match
        d1 = self.proxy.route_request("/api/v1/users", method="GET")
        self.assertEqual(d1.destination, RouteDestination.MODERN)
        self.assertEqual(d1.target_url, "http://modern.app.internal:8081/modern-app/api/v1/users")
        self.assertIn("path-prefix:/api/v1/users", d1.matched_rule)

        # Child path match
        d2 = self.proxy.route_request("/api/v1/users/42/profile", method="GET")
        self.assertEqual(d2.destination, RouteDestination.MODERN)
        self.assertEqual(d2.target_url, "http://modern.app.internal:8081/modern-app/api/v1/users/42/profile")

        # Unmigrated path still goes to legacy
        d3 = self.proxy.route_request("/api/v1/billing", method="POST")
        self.assertEqual(d3.destination, RouteDestination.LEGACY)

    def test_longest_prefix_match(self) -> None:
        self.proxy.register_migrated_route("/api")
        self.proxy.register_migrated_route("/api/v2/payments")

        d = self.proxy.route_request("/api/v2/payments/charge", method="POST")
        self.assertEqual(d.destination, RouteDestination.MODERN)
        self.assertEqual(d.matched_rule, "path-prefix:/api/v2/payments")

    def test_header_override_rule_takes_precedence(self) -> None:
        self.proxy.add_header_rule("x-use-modern-engine", "true")

        # Even for unmigrated route, header override directs to modern
        decision = self.proxy.route_request(
            "/legacy-only/admin/reports",
            headers={"X-Use-Modern-Engine": "true"},
        )
        self.assertEqual(decision.destination, RouteDestination.MODERN)
        self.assertEqual(decision.target_url, "http://modern.app.internal:8081/modern-app/legacy-only/admin/reports")
        self.assertEqual(decision.matched_rule, "header-match:x-use-modern-engine=true")

    def test_dual_write_shadow_routing(self) -> None:
        self.proxy.register_migrated_route("/api/v1/inventory")

        decision = self.proxy.route_request(
            "/api/v1/inventory/adjust",
            method="POST",
            headers={"X-Dual-Write-Shadow": "true"},
        )
        self.assertEqual(decision.destination, RouteDestination.DUAL_WRITE)
        self.assertEqual(decision.target_url, "http://legacy.app.internal:8080/app/api/v1/inventory/adjust")

    # ── OutboxDualWriteAuditor Tests ──

    def test_outbox_identical_events_equivalent(self) -> None:
        legacy_event = {
            "event_id": "EVT-001",
            "aggregate_type": "Order",
            "event_type": "OrderCreated",
            "topic": "orders.v1",
            "timestamp": "2026-09-01T10:00:00Z",
            "payload": {"order_id": 101, "amount": 99.50, "currency": "USD"},
        }
        modern_event = {
            "event_id": "EVT-MOD-001",
            "aggregate_type": "Order",
            "event_type": "OrderCreated",
            "topic": "orders.v1",
            "timestamp": "2026-09-01T10:00:01Z",  # Different timestamp, should be ignored
            "payload": {"order_id": 101, "amount": 99.50, "currency": "USD"},
        }
        res = self.auditor.compare_events(legacy_event, modern_event)
        self.assertTrue(res.is_equivalent)
        self.assertFalse(res.semantic_drift_detected)
        self.assertEqual(len(res.mismatched_fields), 0)
        self.assertEqual(res.payload_hash_legacy, res.payload_hash_modern)

    def test_outbox_metadata_mismatch_detected(self) -> None:
        legacy_event = {
            "event_id": "EVT-002",
            "aggregate_type": "Customer",
            "event_type": "CustomerUpdated",
            "topic": "customers.v1",
            "payload": {"id": 1},
        }
        modern_event = {
            "event_id": "EVT-MOD-002",
            "aggregate_type": "Customer",
            "event_type": "CustomerCreated",  # Mismatched event_type
            "topic": "customers.v1",
            "payload": {"id": 1},
        }
        res = self.auditor.compare_events(legacy_event, modern_event)
        self.assertFalse(res.is_equivalent)
        self.assertTrue(res.semantic_drift_detected)
        self.assertTrue(any("event_type" in m for m in res.mismatched_fields))

    def test_outbox_payload_mismatch_and_string_parsing(self) -> None:
        legacy_event = {
            "id": "100",
            "aggregate_type": "Payment",
            "payload": json.dumps({"status": "SUCCESS", "fee": 1.50}),
        }
        modern_event = {
            "id": "200",
            "aggregate_type": "Payment",
            "payload": json.dumps({"status": "SUCCESS", "fee": 2.00}),  # Divergent fee
        }
        res = self.auditor.compare_events(legacy_event, modern_event)
        self.assertFalse(res.is_equivalent)
        self.assertTrue(res.semantic_drift_detected)
        self.assertTrue(any("payload.fee" in m for m in res.mismatched_fields))
        self.assertNotEqual(res.payload_hash_legacy, res.payload_hash_modern)


if __name__ == "__main__":
    unittest.main()
