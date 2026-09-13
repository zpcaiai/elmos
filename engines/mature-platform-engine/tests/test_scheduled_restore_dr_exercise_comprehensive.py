import unittest
from datetime import datetime, timedelta

from elmos_mature_platform.types import (
    DrExerciseType,
    DrExerciseStatus,
    DrExercise,
    DrSchedule
)
from elmos_mature_platform.scheduled_restore_dr_exercise_engine import ScheduledRestoreDrExerciseEngine

class TestScheduledRestoreDrExerciseEngine(unittest.TestCase):

    def setUp(self):
        self.engine = ScheduledRestoreDrExerciseEngine()

    def test_create_schedule(self):
        schedule = DrSchedule(schedule_id="sch1", exercise_type=DrExerciseType.FULL_RESTORE)
        sid = self.engine.create_schedule(schedule)
        self.assertEqual(sid, "sch1")
        self.assertIn("sch1", self.engine._schedules)

    def test_create_exercise(self):
        exercise = DrExercise(exercise_id="ex1", name="Ex1", exercise_type=DrExerciseType.FULL_RESTORE)
        eid = self.engine.create_exercise(exercise)
        self.assertEqual(eid, "ex1")
        self.assertIn("ex1", self.engine._exercises)

    def test_start_exercise_success(self):
        exercise = DrExercise(exercise_id="ex1", name="Ex1", exercise_type=DrExerciseType.FULL_RESTORE)
        self.engine.create_exercise(exercise)
        ex = self.engine.start_exercise("ex1")
        self.assertEqual(ex.status, DrExerciseStatus.IN_PROGRESS)
        self.assertNotEqual(ex.started_at, "")

    def test_start_exercise_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.start_exercise("nonexistent")

    def test_start_exercise_wrong_status(self):
        exercise = DrExercise(exercise_id="ex1", name="Ex1", exercise_type=DrExerciseType.FULL_RESTORE, status=DrExerciseStatus.IN_PROGRESS)
        self.engine.create_exercise(exercise)
        with self.assertRaises(ValueError):
            self.engine.start_exercise("ex1")

    def test_complete_exercise_success_pass(self):
        schedule = DrSchedule(schedule_id="sch1", exercise_type=DrExerciseType.FULL_RESTORE)
        self.engine.create_schedule(schedule)
        
        exercise = DrExercise(exercise_id="ex1", name="Ex1", exercise_type=DrExerciseType.FULL_RESTORE, status=DrExerciseStatus.IN_PROGRESS)
        self.engine.create_exercise(exercise)
        
        ex = self.engine.complete_exercise("ex1", actual_rto=50, actual_rpo=10, findings=["All good"])
        
        self.assertEqual(ex.status, DrExerciseStatus.COMPLETED)
        self.assertTrue(ex.passed)
        self.assertEqual(ex.actual_rto_minutes, 50)
        self.assertEqual(ex.actual_rpo_minutes, 10)
        self.assertEqual(self.engine._schedules["sch1"].last_executed, ex.completed_at)

    def test_complete_exercise_success_fail_metrics(self):
        exercise = DrExercise(exercise_id="ex1", name="Ex1", exercise_type=DrExerciseType.FULL_RESTORE, status=DrExerciseStatus.IN_PROGRESS, target_rto_minutes=60, target_rpo_minutes=15)
        self.engine.create_exercise(exercise)
        ex = self.engine.complete_exercise("ex1", actual_rto=70, actual_rpo=10, findings=["RTO missed"])
        self.assertFalse(ex.passed)

    def test_complete_exercise_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.complete_exercise("nonexistent", 10, 10, [])

    def test_complete_exercise_wrong_status(self):
        exercise = DrExercise(exercise_id="ex1", name="Ex1", exercise_type=DrExerciseType.FULL_RESTORE, status=DrExerciseStatus.SCHEDULED)
        self.engine.create_exercise(exercise)
        with self.assertRaises(ValueError):
            self.engine.complete_exercise("ex1", 10, 10, [])

    def test_fail_exercise_success(self):
        exercise = DrExercise(exercise_id="ex1", name="Ex1", exercise_type=DrExerciseType.FULL_RESTORE, status=DrExerciseStatus.IN_PROGRESS)
        self.engine.create_exercise(exercise)
        ex = self.engine.fail_exercise("ex1", "Environment crashed")
        self.assertEqual(ex.status, DrExerciseStatus.FAILED)
        self.assertFalse(ex.passed)
        self.assertEqual(ex.findings[-1], "Failed: Environment crashed")

    def test_fail_exercise_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.fail_exercise("nonexistent", "reason")

    def test_cancel_exercise_success(self):
        exercise = DrExercise(exercise_id="ex1", name="Ex1", exercise_type=DrExerciseType.FULL_RESTORE)
        self.engine.create_exercise(exercise)
        ex = self.engine.cancel_exercise("ex1")
        self.assertEqual(ex.status, DrExerciseStatus.CANCELLED)

    def test_cancel_exercise_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.cancel_exercise("nonexistent")

    def test_cancel_exercise_wrong_status(self):
        exercise = DrExercise(exercise_id="ex1", name="Ex1", exercise_type=DrExerciseType.FULL_RESTORE, status=DrExerciseStatus.COMPLETED)
        self.engine.create_exercise(exercise)
        with self.assertRaises(ValueError):
            self.engine.cancel_exercise("ex1")

    def test_get_overdue_exercises_empty(self):
        self.assertEqual(self.engine.get_overdue_exercises(), [])

    def test_get_overdue_exercises_some(self):
        now = datetime.utcnow()
        past = (now - timedelta(days=1)).isoformat()
        future = (now + timedelta(days=1)).isoformat()
        
        self.engine.create_schedule(DrSchedule("sch1", DrExerciseType.FULL_RESTORE, next_scheduled=past))
        self.engine.create_schedule(DrSchedule("sch2", DrExerciseType.PARTIAL_RESTORE, next_scheduled=future))
        
        overdue = self.engine.get_overdue_exercises()
        self.assertEqual(len(overdue), 1)
        self.assertEqual(overdue[0].schedule_id, "sch1")

    def test_get_exercise_history_all(self):
        self.engine.create_exercise(DrExercise("ex1", "Ex1", DrExerciseType.FULL_RESTORE))
        self.engine.create_exercise(DrExercise("ex2", "Ex2", DrExerciseType.PARTIAL_RESTORE))
        history = self.engine.get_exercise_history()
        self.assertEqual(len(history), 2)

    def test_get_exercise_history_filtered(self):
        self.engine.create_exercise(DrExercise("ex1", "Ex1", DrExerciseType.FULL_RESTORE))
        self.engine.create_exercise(DrExercise("ex2", "Ex2", DrExerciseType.PARTIAL_RESTORE))
        history = self.engine.get_exercise_history(DrExerciseType.FULL_RESTORE)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].exercise_id, "ex1")

    def test_get_rto_rpo_trends_empty(self):
        trends = self.engine.get_rto_rpo_trends()
        self.assertEqual(trends["avg_rto_minutes"], 0.0)

    def test_get_rto_rpo_trends_stable(self):
        self.engine.create_exercise(DrExercise("ex1", "Ex1", DrExerciseType.FULL_RESTORE, status=DrExerciseStatus.COMPLETED, actual_rto_minutes=50, actual_rpo_minutes=10, completed_at="2024-01-01"))
        self.engine.create_exercise(DrExercise("ex2", "Ex2", DrExerciseType.FULL_RESTORE, status=DrExerciseStatus.COMPLETED, actual_rto_minutes=50, actual_rpo_minutes=10, completed_at="2024-01-02"))
        trends = self.engine.get_rto_rpo_trends()
        self.assertEqual(trends["trend"], "stable")
        self.assertEqual(trends["avg_rto_minutes"], 50.0)

    def test_get_rto_rpo_trends_improving(self):
        self.engine.create_exercise(DrExercise("ex1", "Ex1", DrExerciseType.FULL_RESTORE, status=DrExerciseStatus.COMPLETED, actual_rto_minutes=60, completed_at="2024-01-01"))
        self.engine.create_exercise(DrExercise("ex2", "Ex2", DrExerciseType.FULL_RESTORE, status=DrExerciseStatus.COMPLETED, actual_rto_minutes=40, completed_at="2024-01-02"))
        trends = self.engine.get_rto_rpo_trends()
        self.assertEqual(trends["trend"], "improving")
        self.assertEqual(trends["avg_rto_minutes"], 50.0)

    def test_get_rto_rpo_trends_degrading(self):
        self.engine.create_exercise(DrExercise("ex1", "Ex1", DrExerciseType.FULL_RESTORE, status=DrExerciseStatus.COMPLETED, actual_rto_minutes=40, completed_at="2024-01-01"))
        self.engine.create_exercise(DrExercise("ex2", "Ex2", DrExerciseType.FULL_RESTORE, status=DrExerciseStatus.COMPLETED, actual_rto_minutes=60, completed_at="2024-01-02"))
        trends = self.engine.get_rto_rpo_trends()
        self.assertEqual(trends["trend"], "degrading")

    def test_get_compliance_status_empty(self):
        status = self.engine.get_compliance_status()
        self.assertEqual(status["on_time_percent"], 0.0)

    def test_get_compliance_status_some(self):
        now = datetime.utcnow()
        past = (now - timedelta(days=1)).isoformat()
        future = (now + timedelta(days=1)).isoformat()
        
        self.engine.create_schedule(DrSchedule("sch1", DrExerciseType.FULL_RESTORE, next_scheduled=past))
        self.engine.create_schedule(DrSchedule("sch2", DrExerciseType.PARTIAL_RESTORE, next_scheduled=future))
        
        self.engine.create_exercise(DrExercise("ex1", "Ex1", DrExerciseType.FULL_RESTORE, status=DrExerciseStatus.COMPLETED, passed=True, completed_at=future))
        
        status = self.engine.get_compliance_status()
        self.assertEqual(status["overdue_count"], 1)
        self.assertEqual(status["on_time_percent"], 50.0)
        self.assertTrue(status["schedules"]["sch1"]["is_overdue"])
        self.assertTrue(status["schedules"]["sch1"]["last_passed"])
        self.assertFalse(status["schedules"]["sch2"]["is_overdue"])
        self.assertFalse(status["schedules"]["sch2"]["last_passed"])

    def test_get_dr_report_empty(self):
        report = self.engine.get_dr_report()
        self.assertEqual(report["overall_pass_rate"], 0.0)

    def test_get_dr_report_some(self):
        self.engine.create_schedule(DrSchedule("sch1", DrExerciseType.FULL_RESTORE))
        self.engine.create_exercise(DrExercise("ex1", "Ex1", DrExerciseType.FULL_RESTORE, status=DrExerciseStatus.COMPLETED, passed=True, findings=["finding1"], actual_rto_minutes=50, actual_rpo_minutes=10))
        self.engine.create_exercise(DrExercise("ex2", "Ex2", DrExerciseType.PARTIAL_RESTORE, status=DrExerciseStatus.COMPLETED, passed=False, findings=["finding2", "finding3"], actual_rto_minutes=20, actual_rpo_minutes=5))
        
        report = self.engine.get_dr_report()
        self.assertEqual(report["overall_pass_rate"], 50.0)
        self.assertEqual(report["total_findings"], 3)
        self.assertEqual(report["by_type"][DrExerciseType.FULL_RESTORE.value]["passes"], 1)
        self.assertEqual(report["by_type"][DrExerciseType.PARTIAL_RESTORE.value]["count"], 1)
        self.assertEqual(report["by_type"][DrExerciseType.PARTIAL_RESTORE.value]["avg_rto"], 20.0)

    def test_create_multiple_schedules(self):
        self.engine.create_schedule(DrSchedule("s1", DrExerciseType.FULL_RESTORE))
        self.engine.create_schedule(DrSchedule("s2", DrExerciseType.TABLETOP))
        self.assertEqual(len(self.engine._schedules), 2)

    def test_create_multiple_exercises(self):
        self.engine.create_exercise(DrExercise("e1", "E1", DrExerciseType.FULL_RESTORE))
        self.engine.create_exercise(DrExercise("e2", "E2", DrExerciseType.TABLETOP))
        self.assertEqual(len(self.engine._exercises), 2)

    def test_start_exercise_sets_started_at(self):
        self.engine.create_exercise(DrExercise("e1", "E1", DrExerciseType.FULL_RESTORE))
        ex = self.engine.start_exercise("e1")
        self.assertTrue(len(ex.started_at) > 0)

    def test_fail_exercise_appends_finding(self):
        ex = DrExercise("e1", "E1", DrExerciseType.FULL_RESTORE, status=DrExerciseStatus.IN_PROGRESS, findings=["original"])
        self.engine.create_exercise(ex)
        failed = self.engine.fail_exercise("e1", "reason")
        self.assertEqual(len(failed.findings), 2)
        self.assertEqual(failed.findings[1], "Failed: reason")

    def test_cancel_exercise_from_in_progress(self):
        self.engine.create_exercise(DrExercise("e1", "E1", DrExerciseType.FULL_RESTORE, status=DrExerciseStatus.IN_PROGRESS))
        ex = self.engine.cancel_exercise("e1")
        self.assertEqual(ex.status, DrExerciseStatus.CANCELLED)

    def test_trend_calculation_single_exercise(self):
        self.engine.create_exercise(DrExercise("ex1", "Ex1", DrExerciseType.FULL_RESTORE, status=DrExerciseStatus.COMPLETED, actual_rto_minutes=50, actual_rpo_minutes=10, completed_at="2024-01-01"))
        trends = self.engine.get_rto_rpo_trends()
        self.assertEqual(trends["avg_rto_minutes"], 50.0)
        self.assertEqual(trends["trend"], "unknown") # Mid is 0

    def test_start_exercise_cancelled(self):
        self.engine.create_exercise(DrExercise("e1", "E1", DrExerciseType.FULL_RESTORE, status=DrExerciseStatus.CANCELLED))
        with self.assertRaises(ValueError):
            self.engine.start_exercise("e1")

    def test_complete_exercise_failed(self):
        self.engine.create_exercise(DrExercise("e1", "E1", DrExerciseType.FULL_RESTORE, status=DrExerciseStatus.FAILED))
        with self.assertRaises(ValueError):
            self.engine.complete_exercise("e1", 10, 10, [])

    def test_cancel_exercise_failed(self):
        self.engine.create_exercise(DrExercise("e1", "E1", DrExerciseType.FULL_RESTORE, status=DrExerciseStatus.FAILED))
        with self.assertRaises(ValueError):
            self.engine.cancel_exercise("e1")

    def test_complete_exercise_schedule_update_multiple(self):
        schedule1 = DrSchedule("sch1", DrExerciseType.FULL_RESTORE)
        schedule2 = DrSchedule("sch2", DrExerciseType.FULL_RESTORE)
        self.engine.create_schedule(schedule1)
        self.engine.create_schedule(schedule2)
        
        self.engine.create_exercise(DrExercise("e1", "E1", DrExerciseType.FULL_RESTORE, status=DrExerciseStatus.IN_PROGRESS))
        ex = self.engine.complete_exercise("e1", 10, 10, [])
        
        self.assertEqual(self.engine._schedules["sch1"].last_executed, ex.completed_at)
        self.assertEqual(self.engine._schedules["sch2"].last_executed, ex.completed_at)

    def test_fail_exercise_from_scheduled(self):
        self.engine.create_exercise(DrExercise("e1", "E1", DrExerciseType.FULL_RESTORE, status=DrExerciseStatus.SCHEDULED))
        ex = self.engine.fail_exercise("e1", "reason")
        self.assertEqual(ex.status, DrExerciseStatus.FAILED)

if __name__ == '__main__':
    unittest.main()
