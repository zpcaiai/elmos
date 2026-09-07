"""multi-agent-worktree-coordinator: waves, leases and real conflict pairs.

The legacy handler assigns agents by list position -
``contracts[index % len(contracts)]`` - so an agent gets a task because of where
it sat in an array, with nothing matching its declared role or path scope to the
work. Its ``agent_runs`` and ``artifact_handoffs`` are hardcoded empty and its
``merge_plan`` is a constant.
"""

from __future__ import annotations

import pytest

from elmos_repository_autonomy import kernel_bridge
from elmos_repository_autonomy.dispatcher import AutonomyRuntime, DispatchContext
from elmos_repository_autonomy.models import Status


@pytest.fixture()
def runtime():
    return AutonomyRuntime()


@pytest.fixture()
def context(runtime):
    return DispatchContext(tenant_id="t", store=runtime.store,
                           tool_runtime=runtime.tool_runtime)


def _task(task_id, glob, mode="write", role="impl"):
    return {"taskId": task_id, "role": role,
            "claims": [{"pathGlob": glob, "mode": mode}]}


def _payload(**over):
    payload = {
        "task_dag": {"tasks": [_task("a", "src/a"), _task("b", "src/b")]},
        "agent_contracts": [
            {"agentId": "ag-1", "roles": ["impl"],
             "pathScopes": [{"pathGlob": "src/a", "mode": "write"}]},
            {"agentId": "ag-2", "roles": ["impl"],
             "pathScopes": [{"pathGlob": "src/b", "mode": "write"}]},
        ],
        "workspace_topology": {
            "leaseTtlSeconds": 900,
            "agents": [{"agentId": "ag-1", "roles": ["impl"]},
                       {"agentId": "ag-2", "roles": ["impl"]}],
        },
    }
    payload.update(over)
    return payload


def test_disjoint_tasks_share_one_wave(runtime, context):
    """The question a coordinator exists to answer: what may run at once."""

    result = runtime.execute("multi-agent-worktree-coordinator", _payload(),
                             context=context)

    assert "ENGINE:kernel" in result.reasons
    plan = result.output["agent_assignments"]["wavePlan"]
    assert plan["waveCount"] == 1
    assert plan["waves"][0]["taskIds"] == ["a", "b"]
    assert result.output["conflict_report"] == []


def test_an_overlapping_write_set_blocks_and_names_both_globs(runtime, context):
    """Legacy reports the pair too - but the kernel path must not downgrade it.

    The core returns the conflicts as data and SUCCEEDED for the planning, so
    without ``blocked_when`` a plan whose tasks would write over each other came
    back LOCAL_ENGINEERING_VALIDATED: the cross-engine downgrade again, on the
    surface deciding whether two agents may run at once.
    """

    result = runtime.execute("multi-agent-worktree-coordinator", _payload(
        task_dag={"tasks": [_task("a", "src/shared"), _task("b", "src/shared")]},
    ), context=context)

    assert result.status == Status.BLOCKED
    assert "AGENT_CONFLICT" in result.reasons
    conflict = result.output["conflict_report"][0]
    assert conflict["leftTask"] == "a"
    assert conflict["rightTask"] == "b"
    assert conflict["leftGlob"] == "src/shared"


def test_a_task_without_a_role_keeps_the_legacy_coordinator(runtime, context):
    """Synthesising a role makes the core's role match succeed by construction.

    That match is what decides which agent may write where, so a bridge-invented
    role would hand the decision back to list position - the defect being
    replaced - while looking like it had been checked.
    """

    outcome = kernel_bridge.serve("multi-agent-worktree-coordinator", _payload(
        task_dag={"tasks": [{"taskId": "a",
                             "claims": [{"pathGlob": "src/a", "mode": "write"}]}]},
    ), context)

    assert outcome.served is False
    assert outcome.reasons == ("KERNEL_INPUT_UNMAPPED:EMPTY_REQUEST",)


def test_v2_owned_paths_become_write_claims(runtime, context):
    """v2 defines owned_paths as the write set, so this restates it rather than adding.

    ``read_only`` flips the mode, because v2 says that too.
    """

    spec = kernel_bridge.BRIDGES["multi-agent-worktree-coordinator"]
    request = spec.request_for(_payload(task_dag={"tasks": [
        {"taskId": "a", "role": "impl", "owned_paths": ["src/a"]},
        {"taskId": "b", "role": "review", "owned_paths": ["src/b"], "read_only": True},
    ]}), context)

    modes = {task["taskId"]: task["claims"][0]["mode"] for task in request["task_dag"]["tasks"]}
    assert modes == {"a": "write", "b": "read"}


def test_the_coordinator_leases_through_the_live_store(runtime, context):
    """A coordinator with a private in-memory lease store hands out worktrees it
    does not own - the same reason the lease kernel takes injected ports."""

    spec = kernel_bridge.BRIDGES["multi-agent-worktree-coordinator"]
    request = spec.request_for(_payload(), context)

    from elmos_repository_autonomy.kernel_store_adapter import DurableStoreLeaseStore

    assert isinstance(request["ports"]["lease_store"], DurableStoreLeaseStore)
    assert request["ports"]["clock"] is not None


def test_a_dispatch_without_a_store_stays_with_legacy(runtime):
    """No store, no lease, no honest answer about who owns a worktree."""

    outcome = kernel_bridge.serve(
        "multi-agent-worktree-coordinator", _payload(), DispatchContext(store=None))

    assert outcome.served is False


def test_the_assignment_results_own_status_is_not_overwritten(runtime, context):
    """A one-line adapter bug that destroyed a correct value.

    The kernel registry reads the handler's top-level ``status`` key to set the
    ``SkillResult``'s status and strips it from the outputs, so
    ``outputs["status"]`` is always ``None`` by the time an adapter sees it.
    Folding that into ``agent_assignments`` did not merely add a null field - it
    overwrote the assignment result's *own* ``status``, which is a real value
    computed from whether every wave member was dispatched.
    """

    result = runtime.execute("multi-agent-worktree-coordinator", _payload(),
                             context=context)

    assert result.output["agent_assignments"]["status"] == "SUCCEEDED"
    assert result.status == Status.LOCAL_ENGINEERING_VALIDATED
