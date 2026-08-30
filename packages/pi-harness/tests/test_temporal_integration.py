from __future__ import annotations

import asyncio
import os
import unittest
import uuid

from elmos_pi_harness.canonical import digest
from elmos_pi_harness.temporal import TaskWorkflowInput, replay_histories

try:
    from temporalio import activity
    from temporalio.client import Client
    from temporalio.worker import Worker
except ImportError:  # pragma: no cover - optional integration profile
    activity = None
    Client = None
    Worker = None


def uid() -> str:
    return str(uuid.uuid4())


@unittest.skipUnless(
    os.environ.get("ELMOS_PI_TEMPORAL_ADDRESS") and Client is not None,
    "real Temporal integration profile is not configured",
)
class TemporalIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_workflow_success_pause_resume_cancel_and_replay(self) -> None:
        from elmos_pi_harness.temporal_workflows import PIHarnessTaskWorkflow

        client = await Client.connect(
            os.environ["ELMOS_PI_TEMPORAL_ADDRESS"],
            namespace=os.environ.get("ELMOS_PI_TEMPORAL_NAMESPACE", "default"),
            identity="pi-harness-local-integration",
        )
        task_queue = "pi-harness-integration-" + uid()
        attempts: dict[str, int] = {}

        @activity.defn(name="pi-harness-execute-task-v1")
        async def execute(value: dict) -> dict:
            execution_id = value["execution_id"]
            attempts[execution_id] = attempts.get(execution_id, 0) + 1
            mode = value["request"]["mode"]
            if mode == "pause" and attempts[execution_id] == 1:
                for _heartbeat in range(300):
                    activity.heartbeat({"execution_id": execution_id, "mode": mode})
                    await asyncio.sleep(0.1)
            elif mode == "cancel":
                for _heartbeat in range(300):
                    activity.heartbeat({"execution_id": execution_id, "mode": mode})
                    await asyncio.sleep(0.1)
            return {
                "status": "SUCCEEDED",
                "request_digest": value["request_digest"],
                "executor_generation": value["executor_generation"],
            }

        @activity.defn(name="pi-harness-control-task-v1")
        async def control(value: dict) -> dict:
            return {
                "status": {
                    "PAUSE": "PAUSED",
                    "RESUME": "RUNNING",
                    "CANCEL": "CANCELLED",
                }[value["action"]]
            }

        def workflow_input(mode: str) -> TaskWorkflowInput:
            request = {"mode": mode}
            return TaskWorkflowInput(
                tenant_id=uid(),
                project_id=uid(),
                task_id=uid(),
                execution_id=uid(),
                environment_id=uid(),
                authority_snapshot_id=uid(),
                executor_id="temporal-integration-worker",
                executor_generation=1,
                request=request,
                request_digest=digest(request),
            )

        async with Worker(
            client,
            task_queue=task_queue,
            workflows=[PIHarnessTaskWorkflow],
            activities=[execute, control],
        ):
            success_input = workflow_input("success")
            success_id = f"pi:{success_input.tenant_id}:{success_input.task_id}"
            success = await client.execute_workflow(
                PIHarnessTaskWorkflow.run,
                success_input.to_dict(),
                id=success_id,
                task_queue=task_queue,
            )
            self.assertEqual(success["status"], "SUCCEEDED")
            success_handle = client.get_workflow_handle(success_id)
            history = await success_handle.fetch_history()
            replay = await replay_histories([history])
            self.assertEqual(replay, {"status": "PASS", "replayed": 1, "failures": []})

            pause_input = workflow_input("pause")
            pause_id = f"pi:{pause_input.tenant_id}:{pause_input.task_id}"
            pause_handle = await client.start_workflow(
                PIHarnessTaskWorkflow.run,
                pause_input.to_dict(),
                id=pause_id,
                task_queue=task_queue,
            )
            await asyncio.sleep(0.5)
            await pause_handle.signal("pause", "integration fault injection")
            for _attempt in range(300):
                state = await pause_handle.query("state")
                if state["phase"] == "PAUSED":
                    break
                await asyncio.sleep(0.1)
            self.assertEqual(state["phase"], "PAUSED")
            await pause_handle.signal("resume", 1)
            resumed = await asyncio.wait_for(pause_handle.result(), timeout=15)
            self.assertEqual(resumed["status"], "SUCCEEDED")
            self.assertGreaterEqual(attempts[pause_input.execution_id], 2)

            cancel_input = workflow_input("cancel")
            cancel_id = f"pi:{cancel_input.tenant_id}:{cancel_input.task_id}"
            cancel_handle = await client.start_workflow(
                PIHarnessTaskWorkflow.run,
                cancel_input.to_dict(),
                id=cancel_id,
                task_queue=task_queue,
            )
            await asyncio.sleep(0.5)
            await cancel_handle.signal("request_cancel", "integration cancellation")
            # Temporal throttles heartbeat RPCs relative to the workflow's
            # 30-second heartbeat timeout, so remote cancellation can take one
            # throttle interval even though the activity heartbeats frequently.
            cancelled = await asyncio.wait_for(cancel_handle.result(), timeout=40)
            self.assertEqual(cancelled["status"], "CANCELLED")


if __name__ == "__main__":
    unittest.main()
