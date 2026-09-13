"""Comprehensive test suite for ProviderResourceRoutingEngine (Batch 44 - Skill 1470)."""

import unittest
from datetime import datetime, timezone

from elmos_mature_platform.provider_resource_routing_engine import ProviderResourceRoutingEngine
from elmos_mature_platform.types import (
    ProviderResourceProfile,
    ResourceRoutingDecision,
    RoutingStrategy,
)


class TestProviderResourceRoutingComprehensive(unittest.TestCase):
    """Rigorous unit testing for ProviderResourceRoutingEngine."""

    def setUp(self) -> None:
        self.engine = ProviderResourceRoutingEngine()

    def test_register_provider_resource_success(self) -> None:
        profile = ProviderResourceProfile(
            resource_id="res-gpu-a100",
            provider_name="AWS",
            resource_type="gpu-runner",
            unit_cost_usd=3.06,
            average_latency_ms=45.0,
            current_load_pct=20.0,
            region="us-east-1",
        )
        rid = self.engine.register_provider_resource(profile)
        self.assertEqual(rid, "res-gpu-a100")
        fetched = self.engine.get_resource("res-gpu-a100")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.provider_name, "AWS")
        self.assertEqual(fetched.unit_cost_usd, 3.06)

    def test_register_provider_resource_auto_generates_id(self) -> None:
        profile = ProviderResourceProfile(
            resource_id="",
            provider_name="GCP",
            resource_type="llm-inference",
            unit_cost_usd=0.002,
        )
        rid = self.engine.register_provider_resource(profile)
        self.assertTrue(rid.startswith("res-"))

    def test_register_provider_resource_validation_errors(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.register_provider_resource(
                ProviderResourceProfile("1", "", "gpu", 1.0)
            )
        with self.assertRaises(ValueError):
            self.engine.register_provider_resource(
                ProviderResourceProfile("2", "AWS", "", 1.0)
            )
        with self.assertRaises(ValueError):
            self.engine.register_provider_resource(
                ProviderResourceProfile("3", "AWS", "gpu", -5.0)
            )

    def test_update_availability_and_load(self) -> None:
        profile = ProviderResourceProfile(
            resource_id="res-upd",
            provider_name="Azure",
            resource_type="runner",
            unit_cost_usd=1.50,
            current_load_pct=30.0,
        )
        self.engine.register_provider_resource(profile)

        upd = self.engine.update_availability("res-upd", is_available=False, current_load_pct=90.0)
        self.assertFalse(upd.is_available)
        self.assertEqual(upd.current_load_pct, 90.0)

    def test_update_availability_invalid_load_raises(self) -> None:
        profile = ProviderResourceProfile("res-inv", "AWS", "gpu", 1.0)
        self.engine.register_provider_resource(profile)
        with self.assertRaises(ValueError):
            self.engine.update_availability("res-inv", is_available=True, current_load_pct=105.0)
        with self.assertRaises(ValueError):
            self.engine.update_availability("res-inv", is_available=True, current_load_pct=-5.0)

    def test_update_availability_missing_resource_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.update_availability("missing-id", is_available=True)

    def test_route_lowest_cost(self) -> None:
        # High cost, low latency
        r1 = ProviderResourceProfile("r1", "AWS", "llm-inference", unit_cost_usd=0.010, average_latency_ms=30.0)
        # Low cost, higher latency
        r2 = ProviderResourceProfile("r2", "GCP", "llm-inference", unit_cost_usd=0.002, average_latency_ms=120.0)
        self.engine.register_provider_resource(r1)
        self.engine.register_provider_resource(r2)

        dec = self.engine.route_request(
            workload_type="llm-inference",
            required_capacity=100.0,
            strategy=RoutingStrategy.LOWEST_COST,
        )
        self.assertEqual(dec.selected_resource_id, "r2")
        self.assertEqual(dec.provider_name, "GCP")
        self.assertEqual(dec.estimated_cost_usd, 0.2)

    def test_route_lowest_latency(self) -> None:
        r1 = ProviderResourceProfile("r1", "AWS", "gpu-runner", unit_cost_usd=3.0, average_latency_ms=50.0)
        r2 = ProviderResourceProfile("r2", "GCP", "gpu-runner", unit_cost_usd=1.5, average_latency_ms=250.0)
        self.engine.register_provider_resource(r1)
        self.engine.register_provider_resource(r2)

        dec = self.engine.route_request(
            workload_type="gpu-runner",
            strategy=RoutingStrategy.LOWEST_LATENCY,
        )
        self.assertEqual(dec.selected_resource_id, "r1")
        self.assertEqual(dec.estimated_latency_ms, 50.0)

    def test_route_max_capacity(self) -> None:
        # r1 is heavily loaded (80%), r2 is lightly loaded (10%)
        r1 = ProviderResourceProfile("r1", "AWS", "batch-runner", unit_cost_usd=1.0, current_load_pct=80.0)
        r2 = ProviderResourceProfile("r2", "Azure", "batch-runner", unit_cost_usd=1.0, current_load_pct=10.0)
        self.engine.register_provider_resource(r1)
        self.engine.register_provider_resource(r2)

        dec = self.engine.route_request(
            workload_type="batch-runner",
            strategy=RoutingStrategy.MAX_CAPACITY,
        )
        self.assertEqual(dec.selected_resource_id, "r2")

    def test_route_balanced_efficiency(self) -> None:
        r1 = ProviderResourceProfile("r1", "AWS", "storage", unit_cost_usd=0.05, average_latency_ms=10.0, current_load_pct=10.0)
        self.engine.register_provider_resource(r1)

        dec = self.engine.route_request(
            workload_type="storage",
            strategy=RoutingStrategy.BALANCED_EFFICIENCY,
        )
        self.assertEqual(dec.selected_resource_id, "r1")

    def test_route_no_available_resources_raises(self) -> None:
        r1 = ProviderResourceProfile("r1", "AWS", "heavy-gpu", 10.0, is_available=False)
        r2 = ProviderResourceProfile("r2", "GCP", "heavy-gpu", 10.0, current_load_pct=100.0)
        self.engine.register_provider_resource(r1)
        self.engine.register_provider_resource(r2)

        with self.assertRaises(RuntimeError) as ctx:
            self.engine.route_request("heavy-gpu")
        self.assertIn("No available provider resources found", str(ctx.exception))

    def test_route_missing_workload_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.route_request("")

    def test_get_routing_report(self) -> None:
        rep_empty = self.engine.get_routing_report()
        self.assertEqual(rep_empty["total_resources_registered"], 0)
        self.assertEqual(rep_empty["total_routing_decisions"], 0)

        r = ProviderResourceProfile("r", "AWS", "llm", 0.01)
        self.engine.register_provider_resource(r)
        self.engine.route_request("llm")

        rep = self.engine.get_routing_report()
        self.assertEqual(rep["total_resources_registered"], 1)
        self.assertEqual(rep["available_resources"], 1)
        self.assertEqual(rep["total_routing_decisions"], 1)
        self.assertEqual(rep["decisions_by_provider"]["AWS"], 1)


if __name__ == "__main__":
    unittest.main()
