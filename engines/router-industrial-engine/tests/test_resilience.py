"""Tests for resilience, circuit breaker, retry budget, and exactly-once commit."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from elmos_router_industrial.domain.contracts import InferenceResponse, UsageReport
from elmos_router_industrial.resilience.resilience import (
    CircuitBreaker,
    CircuitState,
    CommitCoordinator,
    ReplayEngine,
    RetryManager,
    StreamEpochCoordinator,
)


class TestResilience(unittest.TestCase):
    def test_circuit_breaker_lifecycle(self) -> None:
        cb = CircuitBreaker(scopeKey="test_scope", failureThreshold=3, cooldownSeconds=2.0, halfOpenSuccessThreshold=2)
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertTrue(cb.allow_request())

        # 3 failures -> trips OPEN
        cb.record_failure(now=100.0)
        cb.record_failure(now=101.0)
        cb.record_failure(now=102.0)
        self.assertEqual(cb.state, CircuitState.OPEN)
        self.assertFalse(cb.allow_request(now=103.0))

        # Cooldown expires -> transitions to HALF_OPEN
        self.assertTrue(cb.allow_request(now=104.5))
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)

        # 2 successes in HALF_OPEN -> closes breaker
        cb.record_success()
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)
        cb.record_success()
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertTrue(cb.allow_request(now=105.0))

    def test_retry_manager_deadline_exhaustion(self) -> None:
        rm = RetryManager(base_delay_seconds=1.0, max_delay_seconds=5.0)
        now = datetime.now(timezone.utc)

        # Deadline has plenty of time
        long_deadline = now + timedelta(seconds=20)
        delay = rm.compute_backoff(attempt=1, deadline=long_deadline, now=now)
        self.assertIsNotNone(delay)
        self.assertTrue(0.5 <= delay <= 2.0)

        # Deadline is very short; delay will exceed deadline -> returns None
        tight_deadline = now + timedelta(milliseconds=100)
        delay_tight = rm.compute_backoff(attempt=1, deadline=tight_deadline, now=now)
        self.assertIsNone(delay_tight)

    def test_stream_epoch_coordinator(self) -> None:
        sec = StreamEpochCoordinator()
        exec_id = "exec_123"

        epoch1 = sec.start_stream(exec_id)
        self.assertEqual(epoch1, 1)

        sec.append_chunk(exec_id, epoch1, "Hello ")
        sec.append_chunk(exec_id, epoch1, "world")
        self.assertEqual(sec.get_accumulated_text(exec_id), "Hello world")

        # Restart stream creates epoch 2
        epoch2 = sec.start_stream(exec_id)
        self.assertEqual(epoch2, 2)

        # Appending with stale epoch 1 must raise error
        with self.assertRaises(ValueError):
            sec.append_chunk(exec_id, epoch1, "stale token")

    def test_commit_coordinator_exactly_once(self) -> None:
        coord = CommitCoordinator()
        resp1 = InferenceResponse(
            id="resp_01",
            model="gpt-4o",
            content="Final answer",
            usage=UsageReport(10, 5, 15),
        )

        # First commit succeeds
        c1 = coord.commit(
            task_id="t_01",
            step_id="s_01",
            attempt_id="att_01",
            idempotency_key="idem_abc",
            response=resp1,
        )
        self.assertEqual(c1.attemptId, "att_01")
        self.assertEqual(c1.response.content, "Final answer")

        # Duplicate commit with same idempotency key returns exact same commit record
        c2 = coord.commit(
            task_id="t_01",
            step_id="s_01",
            attempt_id="att_02",
            idempotency_key="idem_abc",
            response=resp1,
        )
        self.assertEqual(c2.attemptId, "att_01")
        self.assertEqual(c2.resultHash, c1.resultHash)

        # Replay engine validation
        replay = ReplayEngine(coord)
        self.assertTrue(replay.verify_replay("t_01", "s_01", c1.resultHash))
        self.assertFalse(replay.verify_replay("t_01", "s_01", "invalid_hash"))


if __name__ == "__main__":
    unittest.main()
