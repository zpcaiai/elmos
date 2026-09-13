"""Comprehensive test suite for ResourceMeteringEngine (Batch 44 - Skill 1457)."""

import unittest
from datetime import datetime, timezone

from elmos_mature_platform.resource_metering_engine import ResourceMeteringEngine
from elmos_mature_platform.types import (
    MeteredResourceType,
    ResourceMeterEvent,
    TenantUsageRollup,
)


class TestResourceMeteringComprehensive(unittest.TestCase):
    """Rigorous unit testing for ResourceMeteringEngine."""

    def setUp(self) -> None:
        self.engine = ResourceMeteringEngine()

    def test_record_meter_event_success(self) -> None:
        evt = ResourceMeterEvent(
            event_id="meter-ev-1",
            tenant_id="tenant-corp-a",
            project_id="proj-modernize",
            resource_type=MeteredResourceType.RUNNER_COMPUTE_SECONDS,
            units=120.5,
            metadata={"runner_id": "runner-linux-01"},
        )
        eid = self.engine.record_meter_event(evt)
        self.assertEqual(eid, "meter-ev-1")

        usage = self.engine.get_tenant_usage("tenant-corp-a")
        self.assertEqual(usage.tenant_id, "tenant-corp-a")
        self.assertEqual(
            usage.total_units_by_type[MeteredResourceType.RUNNER_COMPUTE_SECONDS.value],
            120.5,
        )
        self.assertEqual(usage.total_events_count, 1)

    def test_record_meter_event_auto_generates_id_and_date(self) -> None:
        evt = ResourceMeterEvent(
            event_id="",
            tenant_id="tenant-b",
            project_id="proj-b",
            resource_type=MeteredResourceType.MODEL_INPUT_TOKENS,
            units=5000.0,
        )
        eid = self.engine.record_meter_event(evt)
        self.assertTrue(eid.startswith("meter-"))
        self.assertTrue(len(evt.recorded_at) > 0)

    def test_record_meter_event_validation_errors(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.record_meter_event(
                ResourceMeterEvent("1", "", "p", MeteredResourceType.STORAGE_GB_HOURS, 10.0)
            )
        with self.assertRaises(ValueError):
            self.engine.record_meter_event(
                ResourceMeterEvent("2", "t", "p", MeteredResourceType.STORAGE_GB_HOURS, -5.0)
            )

    def test_get_tenant_usage_filtered(self) -> None:
        t_id = "tenant-filter"
        self.engine.record_meter_event(
            ResourceMeterEvent("1", t_id, "p", MeteredResourceType.MODEL_INPUT_TOKENS, 1000.0)
        )
        self.engine.record_meter_event(
            ResourceMeterEvent("2", t_id, "p", MeteredResourceType.MODEL_OUTPUT_TOKENS, 200.0)
        )

        filtered = self.engine.get_tenant_usage(t_id, resource_type=MeteredResourceType.MODEL_OUTPUT_TOKENS)
        self.assertIn(MeteredResourceType.MODEL_OUTPUT_TOKENS.value, filtered.total_units_by_type)
        self.assertNotIn(MeteredResourceType.MODEL_INPUT_TOKENS.value, filtered.total_units_by_type)
        self.assertEqual(filtered.total_units_by_type[MeteredResourceType.MODEL_OUTPUT_TOKENS.value], 200.0)

    def test_get_tenant_usage_unregistered_tenant(self) -> None:
        usage = self.engine.get_tenant_usage("unknown-tenant")
        self.assertEqual(usage.total_events_count, 0)
        self.assertEqual(len(usage.total_units_by_type), 0)

    def test_check_quota(self) -> None:
        t_id = "tenant-quota"
        self.engine.record_meter_event(
            ResourceMeterEvent("1", t_id, "p", MeteredResourceType.NETWORK_EGRESS_BYTES, 5000.0)
        )

        # Within limit
        self.assertTrue(self.engine.check_quota(t_id, MeteredResourceType.NETWORK_EGRESS_BYTES, 10000.0))
        # Exact limit
        self.assertTrue(self.engine.check_quota(t_id, MeteredResourceType.NETWORK_EGRESS_BYTES, 5000.0))
        # Exceeded limit
        self.assertFalse(self.engine.check_quota(t_id, MeteredResourceType.NETWORK_EGRESS_BYTES, 4000.0))

        # Check unused resource type (0 <= 100 -> True)
        self.assertTrue(self.engine.check_quota(t_id, MeteredResourceType.STORAGE_GB_HOURS, 100.0))

    def test_check_quota_negative_limit_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.check_quota("t", MeteredResourceType.STORAGE_GB_HOURS, -1.0)

    def test_get_total_metered_units(self) -> None:
        self.engine.record_meter_event(
            ResourceMeterEvent("1", "t1", "p", MeteredResourceType.RUNNER_COMPUTE_SECONDS, 100.0)
        )
        self.engine.record_meter_event(
            ResourceMeterEvent("2", "t2", "p", MeteredResourceType.RUNNER_COMPUTE_SECONDS, 250.0)
        )
        self.engine.record_meter_event(
            ResourceMeterEvent("3", "t1", "p", MeteredResourceType.STORAGE_GB_HOURS, 50.0)
        )

        compute_total = self.engine.get_total_metered_units(MeteredResourceType.RUNNER_COMPUTE_SECONDS)
        storage_total = self.engine.get_total_metered_units(MeteredResourceType.STORAGE_GB_HOURS)
        egress_total = self.engine.get_total_metered_units(MeteredResourceType.NETWORK_EGRESS_BYTES)

        self.assertEqual(compute_total, 350.0)
        self.assertEqual(storage_total, 50.0)
        self.assertEqual(egress_total, 0.0)

    def test_get_metering_report(self) -> None:
        rep_empty = self.engine.get_metering_report()
        self.assertEqual(rep_empty["total_metering_events"], 0)
        self.assertEqual(rep_empty["total_tenants_metered"], 0)

        self.engine.record_meter_event(
            ResourceMeterEvent("1", "t1", "p", MeteredResourceType.MODEL_INPUT_TOKENS, 1500.0)
        )

        rep = self.engine.get_metering_report()
        self.assertEqual(rep["total_metering_events"], 1)
        self.assertEqual(rep["total_tenants_metered"], 1)
        self.assertEqual(
            rep["units_by_resource_type"][MeteredResourceType.MODEL_INPUT_TOKENS.value],
            1500.0,
        )


if __name__ == "__main__":
    unittest.main()
