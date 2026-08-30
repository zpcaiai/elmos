"""Deterministic Temporal workflows. This module requires the temporal extra."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError, CancelledError
from temporalio.workflow import ActivityCancellationType


@workflow.defn(name="pi-harness-task-v1", sandboxed=True)
class PIHarnessTaskWorkflow:
    def __init__(self) -> None:
        self.paused = False
        self.cancel_requested = False
        self.pause_reason: str | None = None
        self.resume_requested = False
        self.executor_generation = -1
        self.phase = "CREATED"
        self.control_sequence = 0

    @workflow.run
    async def run(self, value: dict[str, Any]) -> dict[str, Any]:
        self.executor_generation = int(value["executor_generation"])
        while True:
            await workflow.wait_condition(
                lambda: not self.paused or self.cancel_requested
            )
            if self.cancel_requested:
                await self._control(value, "CANCEL")
                self.phase = "CANCELLED"
                return {
                    "status": self.phase,
                    "request_digest": value["request_digest"],
                    "executor_generation": self.executor_generation,
                }
            self.phase = "RUNNING"
            handle = workflow.start_activity(
                "pi-harness-execute-task-v1",
                value,
                start_to_close_timeout=timedelta(hours=2),
                heartbeat_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(
                    initial_interval=timedelta(seconds=1),
                    backoff_coefficient=2.0,
                    maximum_interval=timedelta(minutes=1),
                    maximum_attempts=5,
                    non_retryable_error_types=[
                        "PolicyDeniedError",
                        "StaleGenerationError",
                        "InvalidInput",
                        "ConflictError",
                    ],
                ),
                cancellation_type=ActivityCancellationType.WAIT_CANCELLATION_COMPLETED,
            )

            def activity_completed_or_interrupted() -> bool:
                return handle.done() or self.paused or self.cancel_requested

            await workflow.wait_condition(activity_completed_or_interrupted)
            if self.cancel_requested:
                handle.cancel()
                try:
                    await handle
                except (ActivityError, CancelledError, asyncio.CancelledError):
                    pass
                await self._control(value, "CANCEL")
                self.phase = "CANCELLED"
                return {
                    "status": self.phase,
                    "request_digest": value["request_digest"],
                    "executor_generation": self.executor_generation,
                }
            if handle.done():
                result = await handle
                break
            handle.cancel()
            try:
                await handle
            except (ActivityError, CancelledError, asyncio.CancelledError):
                pass
            await self._control(value, "PAUSE")
            self.phase = "PAUSED"
            if self.resume_requested:
                self.resume_requested = False
                self.paused = False
                self.pause_reason = None
            await workflow.wait_condition(
                lambda: not self.paused or self.cancel_requested
            )
            if self.cancel_requested:
                await self._control(value, "CANCEL")
                self.phase = "CANCELLED"
                return {
                    "status": self.phase,
                    "request_digest": value["request_digest"],
                    "executor_generation": self.executor_generation,
                }
            await self._control(value, "RESUME")
        if not isinstance(result, dict):
            raise ApplicationError(
                "activity result must be an object", non_retryable=True
            )
        if int(result.get("executor_generation", -1)) != self.executor_generation:
            raise ApplicationError(
                "activity returned a stale executor generation", non_retryable=True
            )
        if result.get("request_digest") != value["request_digest"]:
            raise ApplicationError(
                "activity result digest binding failed", non_retryable=True
            )
        self.phase = str(result.get("status", "UNKNOWN"))
        return result

    async def _control(self, value: dict[str, Any], action: str) -> None:
        self.control_sequence += 1
        result = await workflow.execute_activity(
            "pi-harness-control-task-v1",
            {
                "value": value,
                "action": action,
                "control_sequence": self.control_sequence,
            },
            start_to_close_timeout=timedelta(minutes=1),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                maximum_interval=timedelta(seconds=10),
                maximum_attempts=5,
                non_retryable_error_types=[
                    "PolicyDeniedError",
                    "StaleGenerationError",
                    "InvalidInput",
                    "ConflictError",
                ],
            ),
        )
        expected = (
            "CANCELLED"
            if action == "CANCEL"
            else ("PAUSED" if action == "PAUSE" else "RUNNING")
        )
        if result.get("status") != expected:
            raise ApplicationError(
                f"durable control activity did not reach {expected}", non_retryable=True
            )

    @workflow.signal(name="pause")
    async def pause(self, reason: str) -> None:
        if self.phase == "RUNNING":
            self.paused = True
            self.pause_reason = reason
            self.phase = "PAUSE_REQUESTED"

    @workflow.signal(name="resume")
    async def resume(self, expected_executor_generation: int) -> None:
        if expected_executor_generation != self.executor_generation:
            raise ApplicationError("resume generation is stale", non_retryable=True)
        if self.paused:
            if self.phase == "PAUSE_REQUESTED":
                self.resume_requested = True
            else:
                self.paused = False
                self.pause_reason = None
                self.phase = "RUNNING"

    @workflow.signal(name="request_cancel")
    async def request_cancel(self, _reason: str) -> None:
        self.cancel_requested = True
        self.paused = False
        self.phase = "CANCEL_REQUESTED"

    @workflow.query(name="state")
    def state(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "paused": self.paused,
            "pause_reason": self.pause_reason,
            "resume_requested": self.resume_requested,
            "cancel_requested": self.cancel_requested,
            "executor_generation": self.executor_generation,
            "control_sequence": self.control_sequence,
        }
