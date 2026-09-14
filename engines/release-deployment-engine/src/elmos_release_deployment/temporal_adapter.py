"""Optional Temporal adapter. Domain reconciliation remains independently testable.

Worker bootstrap supplies authenticated principal lookup and the shared durable
journal. Workflow inputs contain IDs only, not credentials or trusted identity.
"""
from datetime import timedelta
from temporalio import activity, workflow
from temporalio.common import RetryPolicy


@workflow.defn(name='ElmosDeployReleaseV1')
class DeployReleaseWorkflow:
    @workflow.run
    async def run(self, deployment_id: str) -> str:
        for _ in range(1000):
            state = await workflow.execute_activity('elmos.rd.reconcile.v1',deployment_id,
                start_to_close_timeout=timedelta(minutes=11),
                retry_policy=RetryPolicy(initial_interval=timedelta(seconds=2),
                                         maximum_interval=timedelta(seconds=30),maximum_attempts=3))
            if state in {'SUCCEEDED','ROLLED_BACK','REJECTED','FAILED_NO_MUTATION','FAILED_NEEDS_HUMAN'}:
                return state
            await workflow.sleep(timedelta(seconds=5))
        workflow.continue_as_new(deployment_id)


def definitions(engine, principal_lookup):
    @activity.defn(name='elmos.rd.reconcile.v1')
    async def reconcile(deployment_id: str) -> str:
        principal = principal_lookup(deployment_id)
        activity.heartbeat(deployment_id)
        # Blocking SDK/database work runs in an executor, never the async loop.
        import asyncio
        return await asyncio.to_thread(engine.tick,principal,deployment_id)

    return DeployReleaseWorkflow, reconcile
