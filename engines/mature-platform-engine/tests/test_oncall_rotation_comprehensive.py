import unittest
from datetime import datetime, timedelta
import uuid

from elmos_mature_platform.types import (
    OncallEngineer,
    OncallShift,
    OncallSchedule,
    OncallOverride,
    OncallShiftType
)
from elmos_mature_platform.oncall_rotation_engine import OncallRotationEngine

class TestOncallRotationComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = OncallRotationEngine()
        self.eng1 = OncallEngineer(engineer_id="eng1", name="Alice", timezone="UTC+0", region="EMEA", max_consecutive_shifts=3)
        self.eng2 = OncallEngineer(engineer_id="eng2", name="Bob", timezone="UTC+8", region="APAC", max_consecutive_shifts=3)
        self.eng3 = OncallEngineer(engineer_id="eng3", name="Charlie", timezone="UTC-8", region="AMER", max_consecutive_shifts=3)
        self.engine.register_engineer(self.eng1)
        self.engine.register_engineer(self.eng2)
        self.engine.register_engineer(self.eng3)
        
        self.schedule = OncallSchedule(schedule_id="sch1", service_name="auth-service", rotation_period_hours=8, regions=["EMEA", "APAC", "AMER"])
        self.engine.create_schedule(self.schedule)

    def test_register_engineer(self):
        self.assertIn("eng1", self.engine.engineers)
        
    def test_create_schedule(self):
        self.assertIn("sch1", self.engine.schedules)
        self.assertTrue(self.engine.schedules["sch1"].created_at)

    def test_generate_shifts_basic(self):
        shifts = self.engine.generate_shifts("sch1", 1) # 1 day = 3 shifts of 8 hours
        self.assertEqual(len(shifts), 3)

    def test_generate_shifts_engineer_order(self):
        shifts = self.engine.generate_shifts("sch1", 1)
        # Engineers ordered by timezone string sort: eng1 (+0), eng2 (+8), eng3 (-8)
        self.assertEqual(shifts[0].engineer_id, "eng1")
        self.assertEqual(shifts[1].engineer_id, "eng2")
        self.assertEqual(shifts[2].engineer_id, "eng3")

    def test_generate_shifts_fatigue(self):
        # With max_consecutive_shifts=3, if we only have 1 engineer, they should get fatigued and a gap should appear
        engine = OncallRotationEngine()
        eng = OncallEngineer(engineer_id="solo", name="Solo", timezone="UTC+0", region="EMEA", max_consecutive_shifts=3)
        engine.register_engineer(eng)
        engine.create_schedule(OncallSchedule(schedule_id="s1", service_name="s", rotation_period_hours=8))
        shifts = engine.generate_shifts("s1", 2) # 6 shifts expected, but max is 3
        # Should generate 3 shifts, then 1 gap (eng resets), then 2 shifts
        self.assertEqual(len(shifts), 5)
        self.assertEqual(engine.get_engineer_stats("solo")["current_consecutive"], 2)

    def test_generate_shifts_schedule_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.generate_shifts("unknown", 1)

    def test_generate_shifts_no_engineers(self):
        empty_engine = OncallRotationEngine()
        empty_engine.create_schedule(OncallSchedule(schedule_id="s", service_name="s", rotation_period_hours=8))
        with self.assertRaises(ValueError):
            empty_engine.generate_shifts("s", 1)

    def test_get_current_oncall(self):
        shifts = self.engine.generate_shifts("sch1", 1)
        now = shifts[0].starts_at
        current = self.engine.get_current_oncall("auth-service", now)
        self.assertIsNotNone(current)
        self.assertEqual(current.shift_id, shifts[0].shift_id)

    def test_get_current_oncall_not_found(self):
        self.engine.generate_shifts("sch1", 1)
        # Check a year from now
        future = (datetime.utcnow() + timedelta(days=365)).isoformat()
        current = self.engine.get_current_oncall("auth-service", future)
        self.assertIsNone(current)

    def test_acknowledge_shift(self):
        shifts = self.engine.generate_shifts("sch1", 1)
        shift_id = shifts[0].shift_id
        shift = self.engine.acknowledge_shift(shift_id)
        self.assertTrue(shift.acknowledged)

    def test_acknowledge_shift_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.acknowledge_shift("unknown")

    def test_handoff(self):
        shifts = self.engine.generate_shifts("sch1", 1)
        shift_id = shifts[0].shift_id
        shift = self.engine.handoff(shift_id, "All good")
        self.assertEqual(shift.handoff_notes, "All good")

    def test_handoff_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.handoff("unknown", "notes")

    def test_create_override(self):
        shifts = self.engine.generate_shifts("sch1", 1)
        shift = shifts[0]
        # eng3 is on call, swap with eng1
        override = OncallOverride(
            override_id="ov1",
            original_engineer_id="eng3",
            replacement_engineer_id="eng1",
            service_name="auth-service",
            starts_at=shift.starts_at,
            ends_at=shift.ends_at,
            reason="Sick leave"
        )
        self.engine.create_override(override)
        current = self.engine.get_current_oncall("auth-service", shift.starts_at)
        self.assertEqual(current.engineer_id, "eng1")

    def test_create_override_replacement_unavailable(self):
        self.engine.engineers["eng1"].available = False
        override = OncallOverride(
            override_id="ov1",
            original_engineer_id="eng3",
            replacement_engineer_id="eng1",
            service_name="auth-service",
            starts_at="2023-01-01T00:00:00",
            ends_at="2023-01-01T08:00:00"
        )
        with self.assertRaises(PermissionError):
            self.engine.create_override(override)

    def test_create_override_auto_id(self):
        override = OncallOverride(
            override_id="",
            original_engineer_id="eng3",
            replacement_engineer_id="eng1",
            service_name="auth-service",
            starts_at="2023-01-01T00:00:00",
            ends_at="2023-01-01T08:00:00"
        )
        ov_id = self.engine.create_override(override)
        self.assertTrue(len(ov_id) > 0)

    def test_record_incident(self):
        shifts = self.engine.generate_shifts("sch1", 1)
        shift_id = shifts[0].shift_id
        shift = self.engine.record_incident(shift_id)
        self.assertEqual(shift.incidents_handled, 1)

    def test_record_incident_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.record_incident("unknown")

    def test_get_engineer_stats(self):
        shifts = self.engine.generate_shifts("sch1", 1)
        self.engine.record_incident(shifts[0].shift_id)
        stats = self.engine.get_engineer_stats(shifts[0].engineer_id)
        self.assertEqual(stats["total_shifts"], 1)
        self.assertEqual(stats["incidents_handled"], 1)

    def test_get_engineer_stats_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.get_engineer_stats("unknown")

    def test_get_fatigue_report(self):
        # Max is 3. Make eng1 do 2 shifts -> approaching.
        self.engine.engineers["eng1"].current_consecutive = 2
        report = self.engine.get_fatigue_report()
        self.assertEqual(len(report), 1)
        self.assertEqual(report[0]["status"], "APPROACHING")

    def test_get_fatigue_report_exceeded(self):
        self.engine.engineers["eng2"].current_consecutive = 3
        report = self.engine.get_fatigue_report()
        self.assertEqual(len(report), 1)
        self.assertEqual(report[0]["status"], "EXCEEDED")

    def test_get_coverage_gaps(self):
        # Create a gap manually
        engine = OncallRotationEngine()
        eng = OncallEngineer(engineer_id="solo", name="Solo", timezone="UTC", region="EMEA", max_consecutive_shifts=1)
        engine.register_engineer(eng)
        engine.create_schedule(OncallSchedule(schedule_id="s1", service_name="s", rotation_period_hours=8))
        engine.generate_shifts("s1", 1) # Needs 3 shifts. Solo does 1, gap, Solo does 1.
        gaps = engine.get_coverage_gaps("s1")
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["duration_hours"], 8.0)

    def test_get_coverage_gaps_none(self):
        self.engine.generate_shifts("sch1", 1)
        gaps = self.engine.get_coverage_gaps("sch1")
        self.assertEqual(len(gaps), 0)

    def test_get_coverage_gaps_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.get_coverage_gaps("unknown")

    def test_get_schedule_report(self):
        self.engine.generate_shifts("sch1", 1)
        report = self.engine.get_schedule_report("sch1")
        self.assertEqual(report["total_shifts"], 3)
        self.assertEqual(report["coverage_gaps_count"], 0)

    def test_get_schedule_report_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.get_schedule_report("unknown")

    def test_schedule_shifts_appending(self):
        self.engine.generate_shifts("sch1", 1)
        self.engine.generate_shifts("sch1", 1)
        self.assertEqual(len(self.engine.schedules["sch1"].shifts), 6)

    def test_engineer_availability_toggle(self):
        self.engine.engineers["eng1"].available = False
        shifts = self.engine.generate_shifts("sch1", 1)
        eng_ids = [s.engineer_id for s in shifts]
        self.assertNotIn("eng1", eng_ids)

    def test_multiple_schedules(self):
        self.engine.create_schedule(OncallSchedule(schedule_id="sch2", service_name="db-service", rotation_period_hours=12))
        self.engine.generate_shifts("sch1", 1)
        self.engine.generate_shifts("sch2", 1)
        report1 = self.engine.get_schedule_report("sch1")
        report2 = self.engine.get_schedule_report("sch2")
        self.assertEqual(report1["total_shifts"], 3)
        self.assertEqual(report2["total_shifts"], 2)

    def test_reset_consecutive_on_gap(self):
        engine = OncallRotationEngine()
        eng = OncallEngineer(engineer_id="solo", name="Solo", timezone="UTC", region="EMEA", max_consecutive_shifts=1)
        engine.register_engineer(eng)
        engine.create_schedule(OncallSchedule(schedule_id="s1", service_name="s", rotation_period_hours=8))
        engine.generate_shifts("s1", 1)
        stats = engine.get_engineer_stats("solo")
        self.assertFalse(stats["available"])
        self.assertEqual(stats["current_consecutive"], 1)

    def test_handoff_override(self):
        shifts = self.engine.generate_shifts("sch1", 1)
        override = OncallOverride(
            override_id="ov2",
            original_engineer_id=shifts[0].engineer_id,
            replacement_engineer_id="eng1",
            service_name="auth-service",
            starts_at=shifts[0].starts_at,
            ends_at=shifts[0].ends_at
        )
        self.engine.create_override(override)
        self.engine.handoff(shifts[0].shift_id, "Replaced notes")
        curr = self.engine.get_current_oncall("auth-service", shifts[0].starts_at)
        self.assertEqual(curr.handoff_notes, "Replaced notes")

if __name__ == '__main__':
    unittest.main()
