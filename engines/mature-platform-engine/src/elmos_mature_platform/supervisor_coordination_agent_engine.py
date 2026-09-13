"""Supervisor Coordination Agent Engine (Batch 42 - Skill 1420).

Orchestrates multi-agent teams executing complex, multi-repository modernization tasks,
granting capability and token leases, detecting inter-agent deadlocks, and resolving contention.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    CoordinationStatus,
    SupervisorSession,
    WorkerAgentLease,
)


class SupervisorCoordinationAgentEngine:
    """Supervisor orchestrator managing agent delegation, token budgeting, and deadlock prevention."""

    def __init__(self) -> None:
        self._sessions: Dict[str, SupervisorSession] = {}
        self._deadlocks_resolved_count: int = 0

    def start_session(self, session: SupervisorSession) -> str:
        """Start a top-level supervisory coordination session."""
        if not session.goal:
            raise ValueError("Supervisory session goal is required")

        if not session.session_id:
            session.session_id = f"sup-{uuid.uuid4().hex[:8]}"

        session.status = CoordinationStatus.COORDINATING
        session.started_at = datetime.now(timezone.utc).isoformat()
        self._sessions[session.session_id] = session
        return session.session_id

    def grant_lease(self, session_id: str, lease: WorkerAgentLease) -> WorkerAgentLease:
        """Grant a capability and token lease to a worker agent."""
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        if not lease.agent_id or not lease.assigned_subtask:
            raise ValueError("agent_id and assigned_subtask are required")

        if not lease.lease_id:
            lease.lease_id = f"lease-{uuid.uuid4().hex[:8]}"

        lease.granted_at = datetime.now(timezone.utc).isoformat()
        lease.is_active = True
        session.active_leases[lease.lease_id] = lease
        return lease

    def release_lease(
        self, session_id: str, lease_id: str, subtask_completed: bool = True
    ) -> bool:
        """Release a worker lease upon subtask completion or failure."""
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        lease = session.active_leases.get(lease_id)
        if not lease:
            raise ValueError(f"Lease not found in session: {lease_id}")

        lease.is_active = False
        if subtask_completed:
            session.completed_subtasks.append(lease.assigned_subtask)

        return True

    def detect_deadlock(self, session_id: str, stalled_agent_ids: List[str]) -> bool:
        """Check whether mutual resource locks among stalled agents constitute a deadlock."""
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        active_stalled = [
            l for l in session.active_leases.values()
            if l.is_active and l.agent_id in stalled_agent_ids
        ]

        if len(active_stalled) >= 2:
            session.status = CoordinationStatus.DEADLOCKED
            return True

        return False

    def resolve_deadlock(self, session_id: str, preempted_lease_id: str) -> bool:
        """Resolve deadlock by preempting a low-priority lease and restoring coordination."""
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        lease = session.active_leases.get(preempted_lease_id)
        if not lease:
            raise ValueError(f"Lease not found: {preempted_lease_id}")

        lease.is_active = False
        session.status = CoordinationStatus.COORDINATING
        self._deadlocks_resolved_count += 1
        return True

    def complete_session(self, session_id: str) -> SupervisorSession:
        """Conclude the supervisory session once all goals are satisfied."""
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        session.status = CoordinationStatus.COMPLETED
        session.completed_at = datetime.now(timezone.utc).isoformat()
        return session

    def get_session(self, session_id: str) -> Optional[SupervisorSession]:
        """Retrieve supervisor session details."""
        return self._sessions.get(session_id)

    def get_coordination_report(self) -> Dict[str, Any]:
        """Generate platform supervision metrics."""
        total = len(self._sessions)
        completed = sum(1 for s in self._sessions.values() if s.status == CoordinationStatus.COMPLETED)
        deadlocked = sum(1 for s in self._sessions.values() if s.status == CoordinationStatus.DEADLOCKED)
        total_subtasks = sum(len(s.completed_subtasks) for s in self._sessions.values())

        return {
            "total_sessions": total,
            "completed_sessions": completed,
            "active_deadlocks": deadlocked,
            "deadlocks_resolved_total": self._deadlocks_resolved_count,
            "total_subtasks_delivered": total_subtasks,
        }
