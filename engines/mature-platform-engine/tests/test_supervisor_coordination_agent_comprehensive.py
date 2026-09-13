"""Comprehensive test suite for SupervisorCoordinationAgentEngine (Batch 42 - Skill 1420)."""

import unittest

from elmos_mature_platform.supervisor_coordination_agent_engine import (
    SupervisorCoordinationAgentEngine,
)
from elmos_mature_platform.types import (
    CoordinationStatus,
    SupervisorSession,
    WorkerAgentLease,
)


class TestSupervisorCoordinationAgentComprehensive(unittest.TestCase):
    """Rigorous tests covering multi-agent delegation, token leases, deadlock detection, and preemption."""

    def setUp(self) -> None:
        self.engine = SupervisorCoordinationAgentEngine()

    def test_start_session_success(self) -> None:
        sess = SupervisorSession(
            session_id="",
            goal="Migrate Legacy Billing System from Java 8 to Java 21",
        )
        sid = self.engine.start_session(sess)
        self.assertTrue(sid.startswith("sup-"))

        retrieved = self.engine.get_session(sid)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.status, CoordinationStatus.COORDINATING)

    def test_start_session_missing_goal(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.start_session(SupervisorSession(session_id="", goal=""))

    def test_grant_and_release_lease(self) -> None:
        sid = self.engine.start_session(
            SupervisorSession(session_id="sup-01", goal="Goal 1")
        )
        lease = WorkerAgentLease(
            lease_id="",
            agent_id="worker-agent-1",
            assigned_subtask="Transform BillingModels.java",
            allocated_tokens=40000,
        )
        granted = self.engine.grant_lease(sid, lease)
        self.assertTrue(granted.lease_id.startswith("lease-"))
        self.assertTrue(granted.is_active)

        # Release lease upon subtask completion
        released = self.engine.release_lease(sid, granted.lease_id, subtask_completed=True)
        self.assertTrue(released)
        self.assertFalse(granted.is_active)

        sess = self.engine.get_session(sid)
        self.assertIn("Transform BillingModels.java", sess.completed_subtasks)

    def test_deadlock_detection_and_resolution(self) -> None:
        sid = self.engine.start_session(
            SupervisorSession(session_id="sup-02", goal="Deadlock Test")
        )
        l1 = self.engine.grant_lease(
            sid,
            WorkerAgentLease(lease_id="l1", agent_id="agent-A", assigned_subtask="Task A"),
        )
        l2 = self.engine.grant_lease(
            sid,
            WorkerAgentLease(lease_id="l2", agent_id="agent-B", assigned_subtask="Task B"),
        )

        # Stalled agent list has only 1 -> not a deadlock
        is_deadlock = self.engine.detect_deadlock(sid, ["agent-A"])
        self.assertFalse(is_deadlock)

        # Both agents stalled -> deadlock detected
        is_deadlock2 = self.engine.detect_deadlock(sid, ["agent-A", "agent-B"])
        self.assertTrue(is_deadlock2)
        sess = self.engine.get_session(sid)
        self.assertEqual(sess.status, CoordinationStatus.DEADLOCKED)

        # Resolve deadlock by preempting lease l1
        resolved = self.engine.resolve_deadlock(sid, "l1")
        self.assertTrue(resolved)
        self.assertEqual(sess.status, CoordinationStatus.COORDINATING)
        self.assertFalse(l1.is_active)

    def test_complete_session_and_report(self) -> None:
        sid = self.engine.start_session(
            SupervisorSession(session_id="sup-03", goal="Finalize Wave")
        )
        self.engine.complete_session(sid)
        sess = self.engine.get_session(sid)
        self.assertEqual(sess.status, CoordinationStatus.COMPLETED)
        self.assertNotEqual(sess.completed_at, "")

        report = self.engine.get_coordination_report()
        self.assertEqual(report["total_sessions"], 1)
        self.assertEqual(report["completed_sessions"], 1)


if __name__ == "__main__":
    unittest.main()
