import unittest
from datetime import datetime, timedelta
from typing import List, Dict

from elmos_mature_platform.types import (
    ProblemRecord, ProblemStatus, ProblemPriority,
    RcaFinding, CorrectiveAction
)
from elmos_mature_platform.problem_root_cause_engine import ProblemRootCauseEngine

class TestProblemRootCauseEngineComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = ProblemRootCauseEngine()
        self.base_time = datetime(2023, 1, 1, 12, 0, 0)
        self.current_time = self.base_time
        
        def mock_time_fn():
            return self.current_time.isoformat()
            
        self.engine.set_time_fn(mock_time_fn)

    def advance_time(self, seconds=3600):
        self.current_time += timedelta(seconds=seconds)

    # 1. Test create problem
    def test_create_problem_basic(self):
        record = ProblemRecord(problem_id="p1", title="Memory Leak", description="App OOMs", priority=ProblemPriority.P1)
        p_id = self.engine.create_problem(record)
        self.assertEqual(p_id, "p1")
        self.assertEqual(self.engine.problems["p1"].status, ProblemStatus.OPEN)

    # 2. Test create problem sets time
    def test_create_problem_sets_created_at(self):
        record = ProblemRecord(problem_id="p2", title="CPU Spike", description="High CPU", priority=ProblemPriority.P2)
        self.engine.create_problem(record)
        self.assertEqual(self.engine.problems["p2"].created_at, self.base_time.isoformat())

    # 3. Test start investigation
    def test_start_investigation(self):
        self.engine.create_problem(ProblemRecord(problem_id="p1", title="T1", description="D1", priority=ProblemPriority.P3))
        prob = self.engine.start_investigation("p1")
        self.assertEqual(prob.status, ProblemStatus.INVESTIGATING)

    # 4. Test start investigation not found
    def test_start_investigation_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.start_investigation("missing")

    # 5. Test start investigation invalid state
    def test_start_investigation_invalid_state(self):
        self.engine.create_problem(ProblemRecord(problem_id="p1", title="T1", description="D1", priority=ProblemPriority.P3, status=ProblemStatus.RESOLVED))
        with self.assertRaises(ValueError):
            self.engine.start_investigation("p1")

    # 6. Test add finding
    def test_add_finding(self):
        self.engine.create_problem(ProblemRecord(problem_id="p1", title="T1", description="D1", priority=ProblemPriority.P3))
        self.engine.start_investigation("p1")
        finding = RcaFinding(finding_id="f1", problem_id="p1", category="technology", description="Null pointer")
        self.engine.add_finding(finding)
        self.assertEqual(len(self.engine.findings["p1"]), 1)

    # 7. Test add finding invalid problem
    def test_add_finding_invalid_problem(self):
        finding = RcaFinding(finding_id="f1", problem_id="p1", category="technology", description="Null pointer")
        with self.assertRaises(ValueError):
            self.engine.add_finding(finding)

    # 8. Test add finding without investigating
    def test_add_finding_without_investigating(self):
        self.engine.create_problem(ProblemRecord(problem_id="p1", title="T1", description="D1", priority=ProblemPriority.P3))
        finding = RcaFinding(finding_id="f1", problem_id="p1", category="technology", description="Null pointer")
        with self.assertRaises(ValueError):
            self.engine.add_finding(finding)

    # 9. Test identify root cause
    def test_identify_root_cause(self):
        self.engine.create_problem(ProblemRecord(problem_id="p1", title="T1", description="D1", priority=ProblemPriority.P3))
        self.engine.start_investigation("p1")
        prob = self.engine.identify_root_cause("p1", "Database timeout")
        self.assertEqual(prob.root_cause, "Database timeout")
        self.assertEqual(prob.status, ProblemStatus.ROOT_CAUSE_IDENTIFIED)

    # 10. Test identify root cause invalid state
    def test_identify_root_cause_invalid_state(self):
        self.engine.create_problem(ProblemRecord(problem_id="p1", title="T1", description="D1", priority=ProblemPriority.P3))
        with self.assertRaises(ValueError):
            self.engine.identify_root_cause("p1", "Database timeout")

    # 11. Test identify root cause not found
    def test_identify_root_cause_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.identify_root_cause("p1", "Database timeout")

    # 12. Test add corrective action
    def test_add_corrective_action(self):
        self.engine.create_problem(ProblemRecord(problem_id="p1", title="T1", description="D1", priority=ProblemPriority.P3))
        self.engine.start_investigation("p1")
        self.engine.identify_root_cause("p1", "Database timeout")
        action = CorrectiveAction(action_id="a1", problem_id="p1", description="Increase timeout", owner="dba")
        self.engine.add_corrective_action(action)
        self.assertEqual(len(self.engine.actions["p1"]), 1)
        self.assertEqual(self.engine.problems["p1"].status, ProblemStatus.FIX_IN_PROGRESS)

    # 13. Test add corrective action without root cause
    def test_add_corrective_action_without_root_cause(self):
        self.engine.create_problem(ProblemRecord(problem_id="p1", title="T1", description="D1", priority=ProblemPriority.P3))
        self.engine.start_investigation("p1")
        action = CorrectiveAction(action_id="a1", problem_id="p1", description="Increase timeout", owner="dba")
        with self.assertRaises(ValueError):
            self.engine.add_corrective_action(action)

    # 14. Test add corrective action not found
    def test_add_corrective_action_not_found(self):
        action = CorrectiveAction(action_id="a1", problem_id="p1", description="Increase timeout", owner="dba")
        with self.assertRaises(ValueError):
            self.engine.add_corrective_action(action)

    # 15. Test complete action
    def test_complete_action(self):
        self.engine.create_problem(ProblemRecord(problem_id="p1", title="T1", description="D1", priority=ProblemPriority.P3))
        self.engine.start_investigation("p1")
        self.engine.identify_root_cause("p1", "Database timeout")
        action = CorrectiveAction(action_id="a1", problem_id="p1", description="Increase timeout", owner="dba")
        self.engine.add_corrective_action(action)
        res = self.engine.complete_action("a1")
        self.assertTrue(res.completed)

    # 16. Test complete action not found
    def test_complete_action_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.complete_action("a1")

    # 17. Test verify action
    def test_verify_action(self):
        self.engine.create_problem(ProblemRecord(problem_id="p1", title="T1", description="D1", priority=ProblemPriority.P3))
        self.engine.start_investigation("p1")
        self.engine.identify_root_cause("p1", "Database timeout")
        action = CorrectiveAction(action_id="a1", problem_id="p1", description="Increase timeout", owner="dba")
        self.engine.add_corrective_action(action)
        self.engine.complete_action("a1")
        res = self.engine.verify_action("a1", 0.9)
        self.assertTrue(res.verified)
        self.assertEqual(res.effectiveness_score, 0.9)

    # 18. Test verify action clamps score
    def test_verify_action_clamps_score(self):
        self.engine.create_problem(ProblemRecord(problem_id="p1", title="T1", description="D1", priority=ProblemPriority.P3))
        self.engine.start_investigation("p1")
        self.engine.identify_root_cause("p1", "Database timeout")
        action = CorrectiveAction(action_id="a1", problem_id="p1", description="Increase timeout", owner="dba")
        self.engine.add_corrective_action(action)
        self.engine.complete_action("a1")
        res = self.engine.verify_action("a1", 1.5)
        self.assertEqual(res.effectiveness_score, 1.0)
        res2 = self.engine.verify_action("a1", -0.5)
        self.assertEqual(res2.effectiveness_score, 0.0)

    # 19. Test verify action not complete
    def test_verify_action_not_complete(self):
        self.engine.create_problem(ProblemRecord(problem_id="p1", title="T1", description="D1", priority=ProblemPriority.P3))
        self.engine.start_investigation("p1")
        self.engine.identify_root_cause("p1", "Database timeout")
        action = CorrectiveAction(action_id="a1", problem_id="p1", description="Increase timeout", owner="dba")
        self.engine.add_corrective_action(action)
        with self.assertRaises(ValueError):
            self.engine.verify_action("a1", 0.9)

    # 20. Test verify action not found
    def test_verify_action_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.verify_action("a1", 0.9)

    # 21. Test resolve problem
    def test_resolve_problem(self):
        self.engine.create_problem(ProblemRecord(problem_id="p1", title="T1", description="D1", priority=ProblemPriority.P3))
        self.engine.start_investigation("p1")
        self.engine.identify_root_cause("p1", "Database timeout")
        action = CorrectiveAction(action_id="a1", problem_id="p1", description="Increase timeout", owner="dba")
        self.engine.add_corrective_action(action)
        self.engine.complete_action("a1")
        self.advance_time()
        prob = self.engine.resolve_problem("p1", "Increased timeout config")
        self.assertEqual(prob.status, ProblemStatus.RESOLVED)
        self.assertEqual(prob.resolved_at, self.current_time.isoformat())
        self.assertEqual(prob.fix_description, "Increased timeout config")

    # 22. Test resolve problem actions not complete
    def test_resolve_problem_actions_not_complete(self):
        self.engine.create_problem(ProblemRecord(problem_id="p1", title="T1", description="D1", priority=ProblemPriority.P3))
        self.engine.start_investigation("p1")
        self.engine.identify_root_cause("p1", "Database timeout")
        action = CorrectiveAction(action_id="a1", problem_id="p1", description="Increase timeout", owner="dba")
        self.engine.add_corrective_action(action)
        with self.assertRaises(ValueError):
            self.engine.resolve_problem("p1", "Increased timeout config")

    # 23. Test resolve problem no root cause
    def test_resolve_problem_no_root_cause(self):
        self.engine.create_problem(ProblemRecord(problem_id="p1", title="T1", description="D1", priority=ProblemPriority.P3))
        self.engine.start_investigation("p1")
        with self.assertRaises(ValueError):
            self.engine.resolve_problem("p1", "Fixed")

    # 24. Test resolve problem not found
    def test_resolve_problem_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.resolve_problem("p1", "Fixed")

    # 25. Test link incident
    def test_link_incident(self):
        self.engine.create_problem(ProblemRecord(problem_id="p1", title="T1", description="D1", priority=ProblemPriority.P3))
        self.engine.link_incident("p1", "inc1")
        self.assertIn("inc1", self.engine.problems["p1"].related_incidents)
        # Idempotency
        self.engine.link_incident("p1", "inc1")
        self.assertEqual(len(self.engine.problems["p1"].related_incidents), 1)

    # 26. Test link incident not found
    def test_link_incident_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.link_incident("p1", "inc1")

    # 27. Test detect recurrence
    def test_detect_recurrence(self):
        self.engine.create_problem(ProblemRecord(problem_id="p1", title="T1", description="D1", priority=ProblemPriority.P3))
        self.engine.start_investigation("p1")
        self.engine.identify_root_cause("p1", "OOM")
        
        self.engine.create_problem(ProblemRecord(problem_id="p2", title="T2", description="D2", priority=ProblemPriority.P3))
        self.engine.start_investigation("p2")
        self.engine.identify_root_cause("p2", "OOM")
        
        self.assertTrue(self.engine.detect_recurrence("p2"))
        self.assertEqual(self.engine.problems["p2"].recurrence_count, 1)

    # 28. Test detect recurrence no recurrence
    def test_detect_recurrence_no_recurrence(self):
        self.engine.create_problem(ProblemRecord(problem_id="p1", title="T1", description="D1", priority=ProblemPriority.P3))
        self.engine.start_investigation("p1")
        self.engine.identify_root_cause("p1", "OOM")
        
        self.assertFalse(self.engine.detect_recurrence("p1"))
        self.assertEqual(self.engine.problems["p1"].recurrence_count, 0)

    # 29. Test detect recurrence no root cause
    def test_detect_recurrence_no_root_cause(self):
        self.engine.create_problem(ProblemRecord(problem_id="p1", title="T1", description="D1", priority=ProblemPriority.P3))
        self.assertFalse(self.engine.detect_recurrence("p1"))

    # 30. Test detect recurrence not found
    def test_detect_recurrence_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.detect_recurrence("p1")

    # 31. Test get problem report
    def test_get_problem_report(self):
        self.engine.create_problem(ProblemRecord(problem_id="p1", title="T1", description="D1", priority=ProblemPriority.P1))
        self.engine.start_investigation("p1")
        self.engine.identify_root_cause("p1", "OOM")
        self.engine.add_corrective_action(CorrectiveAction(action_id="a1", problem_id="p1", description="Fix OOM", owner="dev"))
        self.engine.complete_action("a1")
        self.advance_time(7200) # 2 hours
        self.engine.resolve_problem("p1", "Fixed OOM")
        
        self.engine.create_problem(ProblemRecord(problem_id="p2", title="T2", description="D2", priority=ProblemPriority.P2))
        self.engine.start_investigation("p2")
        self.engine.identify_root_cause("p2", "OOM")
        
        self.engine.create_problem(ProblemRecord(problem_id="p3", title="T3", description="D3", priority=ProblemPriority.P1))
        
        report = self.engine.get_problem_report()
        self.assertEqual(report["total_problems"], 3)
        self.assertEqual(report["by_status"]["resolved"], 1)
        self.assertEqual(report["by_status"]["root_cause_identified"], 1)
        self.assertEqual(report["by_status"]["open"], 1)
        self.assertEqual(report["by_priority"]["p1"], 2)
        self.assertEqual(report["by_priority"]["p2"], 1)
        self.assertEqual(report["avg_resolve_time_seconds"], 7200.0)
        self.assertEqual(report["top_root_causes"]["OOM"], 2)

    # 32. Test get problem report empty
    def test_get_problem_report_empty(self):
        report = self.engine.get_problem_report()
        self.assertEqual(report["total_problems"], 0)
        self.assertEqual(report["avg_resolve_time_seconds"], 0.0)

if __name__ == '__main__':
    unittest.main()
