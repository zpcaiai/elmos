"""The four store-backed bridge rows, end to end against a real ``DurableStore``.

Twenty-seven of the bridged skills can be checked by comparing outputs.  These
four cannot, because for them the merge had something to lose: the legacy
handlers write into a transactional store and the kernel's equivalents are pure.
A bridge that only forwarded would look better on every assertion about depth
and be a regression on the one assertion nobody writes — that the run is still
there afterwards.  So each skill is checked three ways: the kernel answers a
complete payload and the answer carries something only the kernel can produce; a
legacy-shaped payload still works and says why it fell through; and a domain
rejection from the kernel reaches the caller instead of being quietly re-decided
by the shallower engine.

The load-bearing test in the file is
``test_the_kernel_run_is_actually_persisted_and_replays_to_the_same_state``.  It
is the one that fails if the merge ever trades persistence for depth.
"""

from __future__ import annotations

import pytest

from elmos_autonomy_kernel.errors import KernelError as KernelSideError
from elmos_autonomy_kernel.orchestrator import (
    RUN_TRANSITIONS,
    RunEvent,
    RunState,
    replay,
    transition,
    view_digest,
)
from elmos_autonomy_kernel.policy import snapshot_from_layers
from elmos_repository_autonomy import kernel_bridge
from elmos_repository_autonomy.dispatcher import AutonomyRuntime, DispatchContext
from elmos_repository_autonomy.kernel_store_adapter import (
    DurableStoreArtifactStore,
    DurableStoreEventStore,
    DurableStoreKeyValueStore,
    DurableStoreLeaseStore,
)
from elmos_repository_autonomy.models import Status
from elmos_repository_autonomy.storage import DurableStore

SHA_SNAPSHOT = "sha256:" + "a" * 64
SHA_POLICY = "sha256:" + "b" * 64


@pytest.fixture()
def store() -> DurableStore:
    return DurableStore()


@pytest.fixture()
def runtime(store: DurableStore) -> AutonomyRuntime:
    return AutonomyRuntime(store)


@pytest.fixture()
def context(store: DurableStore) -> DispatchContext:
    return DispatchContext(tenant_id="tenant-a", account_id="account-a", store=store)


def run_request() -> dict:
    """A payload carrying every fact the kernel refuses to assume."""

    return {
        "task_spec": {"taskSpecId": "ts-1", "taskSpecVersion": "1",
                      "repoSnapshotSha": SHA_SNAPSHOT},
        "workflow_definition": {
            "workflowId": "wf-1", "workflowVersion": "2.0.0",
            "steps": [
                {"stepId": "plan", "inputsDigest": "d-plan",
                 "requiredCapability": "repository-census"},
                {"stepId": "edit", "requires": ["plan"], "inputsDigest": "d-edit",
                 "sideEffecting": True, "compensation": "revert-edit", "maxAttempts": 3},
            ],
        },
        "repository_snapshot": {"snapshotSha": SHA_SNAPSHOT, "paths": ["a.py"]},
        "budget": {"limits": {"usdMicros": 1000}, "maxTurns": 20},
        "policy_snapshot": {"snapshotHash": SHA_POLICY},
    }


def authority_request() -> dict:
    """An environment that states its own ceiling, and a profile strictly under it."""

    return {
        "environment": {
            "environmentId": "env-1", "workspaceId": "ws-1",
            "policySnapshotHash": SHA_POLICY, "ttlSeconds": 3600,
            "grantedTools": ["echo", "write-file"], "pathScopes": ["src"],
            "networkScopes": [], "secretBindings": [],
        },
        "workspace": {"id": "ws-1"},
        "permission_profile": {"id": "profile-1", "tools": ["echo"], "pathScopes": ["src"]},
        "fencing_token": 4,
    }


def policy_request(layers: list | None = None) -> dict:
    """A hook evaluation that declares the snapshot it is being judged against."""

    layers = [] if layers is None else layers
    declared = snapshot_from_layers("policy-snapshot", layers).snapshot_hash
    return {
        "hook_event": {"hookPoint": "pre-write", "subject": {"path": "src/app.py"}},
        "policy_layers": layers,
        "run_context": {"policySnapshotHash": declared},
    }


# --- durable-run-orchestrator ------------------------------------------------


def test_a_complete_run_payload_is_answered_by_the_kernel(runtime, context):
    result = runtime.execute("durable-run-orchestrator", run_request(), context=context)

    assert result.error is None
    assert "ENGINE:kernel" in result.reasons
    assert "KERNEL_PERSISTED" in result.reasons
    # Only the kernel hash-chains its log; the legacy handler's events have no
    # chain field at all, so a caller cannot tell a replay from a retelling.
    chains = [event["chain"] for event in result.output["run_events"]]
    assert all(chain.startswith("sha256:") for chain in chains)
    assert len(set(chains)) == len(chains)
    assert result.output["run"]["viewDigest"].startswith("sha256:")
    assert result.output["rollback_plan"]["planDigest"].startswith("sha256:")


def test_the_run_state_comes_from_the_nineteen_state_machine(runtime, context):
    """The state the bridge produced is governed by the closed transition table.

    ``RUN_TRANSITIONS`` covers all nineteen states, and the state this run landed
    in refuses an illegal target with ``ILLEGAL_TRANSITION`` — a code the legacy
    store does not have, because it reports every state-machine violation as the
    single blanket ``ORCHESTRATOR_INCONSISTENT``.
    """

    result = runtime.execute("durable-run-orchestrator", run_request(), context=context)
    state = RunState(result.output["run"]["state"])

    assert len(RUN_TRANSITIONS) == 19
    assert state in RUN_TRANSITIONS
    with pytest.raises(KernelSideError) as excinfo:
        transition(state, RunState.SUCCEEDED)
    assert excinfo.value.code == "ILLEGAL_TRANSITION"
    assert RunState.SUCCEEDED not in RUN_TRANSITIONS[state]


def test_the_kernel_run_is_actually_persisted_and_replays_to_the_same_state(
        runtime, context, store):
    """The whole point of the two-piece bridge, in one test.

    The kernel computed the run; the store must hold it afterwards.  Not a
    summary of it — the actual hash-chained events, in the same ``events`` table
    the legacy engine writes to, such that the kernel's own ``replay`` rebuilds a
    view identical to the one the call returned.  If a future change makes the
    orchestrator row a plain delegation, this is the assertion that fails.
    """

    result = runtime.execute("durable-run-orchestrator", run_request(), context=context)
    durable = result.output["run"]["durable"]
    assert durable["persisted"] is True

    rows = store.events_since(durable["runId"], tenant_id="tenant-a")
    kernel_rows = [row for row in rows if row["event_type"].startswith("KERNEL_")]
    assert len(kernel_rows) == durable["kernelEventCount"] > 0

    rebuilt = replay([RunEvent.from_payload(row["payload"]) for row in kernel_rows])
    assert str(rebuilt.state) == result.output["run"]["state"]
    assert view_digest(rebuilt) == result.output["run"]["viewDigest"]

    # The store's own invariant still holds: its materialised row agrees with its
    # own log.  Mirroring the kernel's trajectory rather than stamping a state is
    # what keeps this true.
    assert store.replay_state(durable["runId"], tenant_id="tenant-a") == durable["state"]
    assert store.latest_checkpoint(durable["runId"],
                                   tenant_id="tenant-a")["checkpoint_id"] == \
        durable["checkpointId"]


def test_the_kernel_steps_land_in_the_steps_table(runtime, context, store):
    """The legacy handler wrote a row per step; bridging must not drop that.

    The kernel's step state is carried over rather than a hardcoded ``PENDING``,
    so what the store holds is what the kernel decided.
    """

    result = runtime.execute("durable-run-orchestrator", run_request(), context=context)
    exported = store.export_run(result.output["run"]["durable"]["runId"],
                               tenant_id="tenant-a")

    assert {row["step_id"] for row in exported["steps"]} == {"plan", "edit"}
    assert result.output["run"]["durable"]["stepCount"] == 2
    states = {row["step_id"]: row["state"] for row in exported["steps"]}
    assert states == {step["stepId"]: step["state"]
                      for step in result.output["step_runs"]}


def test_replaying_the_same_run_request_appends_nothing(runtime, context, store):
    """At-least-once delivery must not double the log.

    Each kernel event is keyed for idempotency by its own chain digest, so a
    redelivered request resolves to the same run and the same events rather than
    writing a second, equally plausible history.
    """

    first = runtime.execute("durable-run-orchestrator", run_request(), context=context)
    second = runtime.execute("durable-run-orchestrator", run_request(), context=context)

    assert first.output["run"]["durable"]["runId"] == second.output["run"]["durable"]["runId"]
    assert first.output["run"]["durable"]["eventCount"] == \
        second.output["run"]["durable"]["eventCount"]
    events = store.events_since(first.output["run"]["durable"]["runId"], tenant_id="tenant-a")
    assert len({row["event_id"] for row in events}) == len(events)


def test_a_legacy_run_payload_still_works_and_records_the_gap(runtime, context):
    """The payload the legacy handler has always taken keeps working.

    It carries no policy snapshot, so promoting it would mean inventing the hash
    the kernel checks against.  Falling through is the honest outcome, and the
    reason makes the gap countable instead of invisible.
    """

    payload = {
        "task_spec": {"hash": "sha256:task"},
        "workflow_definition": {"version": "2.0.0", "tasks": [
            {"id": "discover", "owned_paths": [], "read_only": True}]},
        "idempotency_key": "legacy-run-1",
    }
    result = runtime.execute("durable-run-orchestrator", payload, context=context)

    assert result.error is None
    assert result.status is Status.LOCAL_ENGINEERING_VALIDATED
    assert "ENGINE:legacy" in result.reasons
    assert "KERNEL_INPUT_UNMAPPED:EMPTY_REQUEST" in result.reasons
    assert result.output["run"]["state"] == "PLANNING"


def test_a_run_the_kernel_rejects_on_a_domain_rule_is_not_re_decided_by_legacy(
        runtime, context):
    """A cyclic workflow is a domain rejection, not a shape mismatch.

    The legacy DAG builder would have to be trusted to find the same cycle.  It
    is never asked: letting the shallower engine overturn a correct rejection is
    worse than having no kernel at all.
    """

    payload = run_request()
    payload["workflow_definition"]["steps"] = [
        {"stepId": "a", "requires": ["b"], "inputsDigest": "d-a"},
        {"stepId": "b", "requires": ["a"], "inputsDigest": "d-b"},
    ]
    result = runtime.execute("durable-run-orchestrator", payload, context=context)

    assert result.error is not None
    assert result.error.code == "DAG_CYCLE"
    assert result.error.details["engine"] == "kernel"


def test_a_stale_snapshot_is_a_domain_rejection_too(runtime, context):
    payload = run_request()
    payload["task_spec"]["repoSnapshotSha"] = "sha256:" + "c" * 64
    result = runtime.execute("durable-run-orchestrator", payload, context=context)

    assert result.error is not None
    assert result.error.code == "STALE_SNAPSHOT"


# --- execution-authority-kernel ----------------------------------------------


def test_the_kernel_mints_an_authority_that_is_strictly_narrower(runtime, context):
    """The ceiling is the environment's; the profile can only stay under it."""

    result = runtime.execute("execution-authority-kernel", authority_request(),
                             context=context)

    assert result.error is None
    assert "ENGINE:kernel" in result.reasons
    authority = result.output["execution_authority"]
    # camelCase and an expiry: the legacy snapshot emits neither, because it
    # never mints anything - it validates the mapping it was handed.
    assert authority["allowedTools"] == ["echo"]
    assert set(authority["allowedTools"]) < set(
        authority_request()["environment"]["grantedTools"])
    assert authority["expiresAt"] > authority["issuedAt"]
    assert authority["subject"] == "environment"


def test_a_profile_that_widens_the_ceiling_cannot_be_expressed(runtime, context):
    """Escalation is a construction failure, not a denied request."""

    payload = authority_request()
    payload["permission_profile"]["tools"] = ["echo", "shell"]
    result = runtime.execute("execution-authority-kernel", payload, context=context)

    assert result.error is not None
    assert result.error.code == "SCOPE_ESCALATION_ATTEMPT"
    assert result.error.details["engine"] == "kernel"


def test_an_environment_without_a_stated_ceiling_falls_through(runtime, context):
    """The legacy payload names no grantable set, and one is not invented.

    Defaulting ``grantedTools`` to the profile's own tools would make the
    narrowing check compare the request to itself: every escalation would mint
    cleanly.  So the call goes to the legacy engine with the gap recorded.
    """

    payload = {
        "environment": {"id": "env-1"},
        "workspace": {"id": "ws-1", "root": "/workspace"},
        "permission_profile": {"id": "profile-1", "policy_snapshot_hash": SHA_POLICY,
                               "allowed_tools": ["echo"], "network_scopes": [],
                               "secret_scopes": []},
        "fencing_token": 1,
        "tool_request": {"tool_id": "echo", "environment_id": "env-1",
                         "workspace_id": "ws-1", "fencing_token": 1},
    }
    result = runtime.execute("execution-authority-kernel", payload, context=context)

    assert result.error is None
    assert "ENGINE:legacy" in result.reasons
    assert "KERNEL_INPUT_UNMAPPED:EMPTY_REQUEST" in result.reasons
    assert result.output["authorization_decision"]["decision"] == "ALLOW"


def test_a_missing_fencing_token_is_never_substituted(context):
    """No token means no request; a plausible ``1`` would satisfy the very check.

    Asserted against ``serve`` directly because the legacy engine then rejects
    the same payload on its own terms - which is correct, and would hide the
    bridge decision under a legacy error.
    """

    payload = authority_request()
    del payload["fencing_token"]
    outcome = kernel_bridge.serve("execution-authority-kernel", payload, context)

    assert outcome.served is False
    assert outcome.reasons == ("KERNEL_INPUT_UNMAPPED:EMPTY_REQUEST",)


# --- policy-hook-kernel ------------------------------------------------------


def test_an_empty_rule_set_denies(runtime, context):
    """Fail-closed on empty is the kernel's, and it is visible in the trace."""

    result = runtime.execute("policy-hook-kernel", policy_request(), context=context)

    assert result.error is None
    assert "ENGINE:kernel" in result.reasons
    decision = result.output["policy_decision"]
    assert decision["decision"] == "DENY"
    assert decision["evaluatedRuleCount"] == 0
    assert decision["trace"][0]["ruleId"] == "fail-closed"


def test_deny_wins_over_an_allow_in_the_same_snapshot(runtime, context):
    layers = [{
        "layerId": "platform",
        "rules": [
            {"ruleId": "allow-src", "hookPoint": "pre-write", "decision": "ALLOW",
             "explanation": "source edits are allowed by default",
             "match": [{"field": "path", "op": "prefix", "value": "src/"}]},
            {"ruleId": "deny-app", "hookPoint": "pre-write", "decision": "DENY",
             "explanation": "the entry point is protected",
             "match": [{"field": "path", "op": "equals", "value": "src/app.py"}]},
        ],
    }]
    result = runtime.execute("policy-hook-kernel", policy_request(layers), context=context)

    assert result.output["policy_decision"]["decision"] == "DENY"
    assert "deny-app" in result.output["policy_decision"]["matchedRuleIds"]


def test_the_kernel_decision_is_still_written_to_the_audit_table(runtime, context, store):
    """A verdict nobody can prove was made is not an audit trail.

    The legacy handler records every decision in ``policy_decisions``; the kernel
    path keeps doing so, with the kernel's own snapshot hash and explanation.
    """

    result = runtime.execute("policy-hook-kernel", policy_request(), context=context)
    assert "KERNEL_PERSISTED" in result.reasons

    with store.transaction() as db:
        rows = db.execute(
            "SELECT event_type, decision, policy_hash FROM policy_decisions "
            "WHERE tenant_id=?", ("tenant-a",)).fetchall()
    assert [dict(row) for row in rows] == [{
        "event_type": "pre-write",
        "decision": "DENY",
        "policy_hash": result.output["policy_decision"]["policySnapshotHash"],
    }]


def test_a_decision_against_an_undeclared_snapshot_is_refused(runtime, context):
    """The declared hash is the caller's claim, and it is checked, not supplied."""

    payload = policy_request()
    payload["run_context"]["policySnapshotHash"] = "sha256:" + "9" * 64
    result = runtime.execute("policy-hook-kernel", payload, context=context)

    assert result.error is not None
    assert result.error.code == "STALE_POLICY_SNAPSHOT"
    assert result.error.details["engine"] == "kernel"


def test_a_legacy_hook_payload_still_works_and_records_the_gap(runtime, context):
    """An event ``type`` is not a hook point, and it is not renamed into one."""

    payload = {
        "hook_event": {"type": "PRE_WRITE"},
        "policy_layers": [{"id": "platform", "decision": "ALLOW"}],
        "run_context": {},
    }
    result = runtime.execute("policy-hook-kernel", payload, context=context)

    assert result.error is None
    assert "ENGINE:legacy" in result.reasons
    assert "KERNEL_INPUT_UNMAPPED:EMPTY_REQUEST" in result.reasons
    assert result.output["policy_decision"]["decision"] == "ALLOW"


# --- workspace-lease-fencing -------------------------------------------------


def lease_payload(owner: str, workspace: str = "ws-1", **policy) -> dict:
    return {
        "workspace": {"workspaceId": workspace},
        "worker_identity": owner,
        "lease_policy": {"ttlSeconds": 60, **policy},
    }


def test_the_token_is_monotonic_across_a_release(runtime, context, store):
    """Release then re-acquire must never hand a stale worker a live token again.

    This is the failure fencing exists for: the paused worker wakes up holding
    token N and must find the resource has moved past it.  The high-water mark
    lives in the durable adapter, so the guarantee survives the process.
    """

    first = runtime.execute("workspace-lease-fencing", lease_payload("worker-a"),
                            context=context)
    assert "ENGINE:kernel" in first.reasons
    held = first.output["fencing_token"]

    leases = DurableStoreLeaseStore(store, tenant_id="tenant-a")
    leases.release("ws-1", "worker-a", held)

    second = runtime.execute("workspace-lease-fencing", lease_payload("worker-b"),
                             context=context)
    assert second.output["fencing_token"] > held
    assert leases.current_token("ws-1") == second.output["fencing_token"]
    assert first.output["lease"]["digest"].startswith("sha256:")


def test_a_second_live_owner_is_refused(runtime, context):
    """``DurableStore.acquire_lease`` alone would have minted a second token."""

    runtime.execute("workspace-lease-fencing", lease_payload("worker-a"), context=context)
    result = runtime.execute("workspace-lease-fencing", lease_payload("worker-b"),
                             context=context)

    assert result.error is not None
    assert result.error.code == "LEASE_HELD_BY_OTHER"


def test_a_takeover_without_a_reason_is_never_promoted(runtime, context):
    """An unexplained takeover is indistinguishable from a split brain afterwards.

    The adapter will not supply the explanation, so no request is built at all.
    """

    runtime.execute("workspace-lease-fencing", lease_payload("worker-a"), context=context)
    outcome = kernel_bridge.serve(
        "workspace-lease-fencing",
        lease_payload("worker-b", action="takeover", previousOwner="worker-a"),
        context,
    )

    assert outcome.served is False
    assert outcome.reasons == ("KERNEL_INPUT_UNMAPPED:EMPTY_REQUEST",)


def test_an_explained_takeover_records_who_lost_the_lease(runtime, context):
    first = runtime.execute("workspace-lease-fencing", lease_payload("worker-a"),
                            context=context)
    result = runtime.execute(
        "workspace-lease-fencing",
        lease_payload("worker-b", action="takeover", reason="worker-a stalled past its ttl",
                      previousOwner="worker-a"),
        context=context,
    )

    record = result.output["takeover_event"]
    assert record["previousOwner"] == "worker-a"
    assert record["newToken"] > first.output["fencing_token"]
    assert record["reason"] == "worker-a stalled past its ttl"


def test_a_renew_without_the_token_being_renewed_is_never_promoted(runtime, context):
    runtime.execute("workspace-lease-fencing", lease_payload("worker-a"), context=context)
    outcome = kernel_bridge.serve("workspace-lease-fencing",
                                  lease_payload("worker-a", action="renew"), context)

    assert outcome.served is False
    assert outcome.reasons == ("KERNEL_INPUT_UNMAPPED:EMPTY_REQUEST",)


def test_a_stale_renew_is_a_domain_rejection(runtime, context, store):
    runtime.execute("workspace-lease-fencing", lease_payload("worker-a"), context=context)
    leases = DurableStoreLeaseStore(store, tenant_id="tenant-a")
    leases.release("ws-1", "worker-a", leases.current_token("ws-1"))
    runtime.execute("workspace-lease-fencing", lease_payload("worker-b"), context=context)

    result = runtime.execute("workspace-lease-fencing",
                             lease_payload("worker-a", action="renew", fencingToken=1),
                             context=context)

    assert result.error is not None
    assert result.error.code == "LEASE_LOST"


def test_a_legacy_lease_payload_still_works_and_records_the_gap(runtime, context):
    """The legacy handler defaults a missing TTL to sixty seconds; this does not.

    A TTL decides when a stalled worker's lease becomes takeable, which is the
    entire subject of this skill.  Substituting one would be inventing the answer
    to the question being asked.
    """

    payload = {"workspace": {"id": "ws-9"}, "worker_identity": "worker-a",
               "lease_policy": {}}
    result = runtime.execute("workspace-lease-fencing", payload, context=context)

    assert result.error is None
    assert "ENGINE:legacy" in result.reasons
    assert "KERNEL_INPUT_UNMAPPED:EMPTY_REQUEST" in result.reasons
    assert result.output["fencing_token"] == 1


# --- the store-backed ports adapter ------------------------------------------
#
# These mirror the invariants in ``test_adapter_conformance.py``.  That suite is
# parametrised over backends and is *not* extended with this one, for three
# reasons that are properties of ``DurableStore`` rather than of the adapter:
# it stamps rows with the real wall clock and takes no injectable ``Clock``, so
# the ``FixedClock`` expiry cases cannot run; its ``events`` rows are foreign
# keyed to a run whose own ``RUN_CREATED`` occupies sequence 1, so a stream does
# not start at 1; and hiding that first row to make it look like it does would
# be a lie about what is recorded.  The invariants that *do* apply are asserted
# here instead, so nothing is skipped silently.


def test_a_duplicate_delivery_returns_the_original_event(store):
    events = DurableStoreEventStore(store, tenant_id="tenant-a")
    first = events.append("run-idem", {"effect": "publish"}, idempotency_key="k-1")
    second = events.append("run-idem", {"effect": "publish"}, idempotency_key="k-1")

    assert (second.sequence, second.event_id) == (first.sequence, first.event_id)
    assert len(events.read("run-idem", from_sequence=first.sequence - 1)) == 1


def test_the_same_key_with_a_different_payload_is_a_conflict(store):
    events = DurableStoreEventStore(store, tenant_id="tenant-a")
    events.append("run-idem2", {"effect": "publish", "target": "a"}, idempotency_key="k-1")
    with pytest.raises(KernelSideError) as excinfo:
        events.append("run-idem2", {"effect": "publish", "target": "b"}, idempotency_key="k-1")
    assert excinfo.value.code == "IDEMPOTENCY_CONFLICT"


def test_an_optimistic_append_against_a_moved_stream_conflicts(store):
    events = DurableStoreEventStore(store, tenant_id="tenant-a")
    first = events.append("run-cas", {"n": 1})
    with pytest.raises(KernelSideError) as excinfo:
        events.append("run-cas", {"n": 2}, expected_sequence=first.sequence - 1)
    assert excinfo.value.code == "WRITE_CONFLICT"
    assert excinfo.value.retryable is True
    assert events.append("run-cas", {"n": 2},
                         expected_sequence=first.sequence).sequence == first.sequence + 1


def test_a_stale_fencing_token_cannot_append(store):
    events = DurableStoreEventStore(store, tenant_id="tenant-a")
    events.append("run-fence", {"n": 1}, fencing_token=7)
    with pytest.raises(KernelSideError) as excinfo:
        events.append("run-fence", {"n": 2}, fencing_token=6)
    assert excinfo.value.code == "FENCING_REJECTED"
    assert excinfo.value.retryable is False
    assert events.append("run-fence", {"n": 2}, fencing_token=7) is not None


def test_the_chain_is_durable_for_events_this_adapter_wrote(store):
    events = DurableStoreEventStore(store, tenant_id="tenant-a")
    for index in range(4):
        events.append("run-chain", {"n": index})

    stored = events.read("run-chain")
    assert events.verify_chain("run-chain") is True
    # The chain digest is the row's own event id, so a rewritten payload no
    # longer hashes to the address it is filed under.
    assert [item.event_id for item in stored if item.event_id.startswith("sha256:")] == \
        [item.hash_chain for item in stored if item.event_id.startswith("sha256:")]
    assert events.head("run-chain").sequence == stored[-1].sequence
    assert "run-chain" in events.streams()


def test_key_value_compare_and_set_and_scan(store):
    kv = DurableStoreKeyValueStore(store, tenant_id="tenant-a")
    version = kv.put("run/1/state", {"state": "EXECUTING"})
    assert kv.get("run/1/state") == ({"state": "EXECUTING"}, version)
    with pytest.raises(KernelSideError) as excinfo:
        kv.put("run/1/state", {"state": "SUCCEEDED"}, expected_version=version - 1)
    assert excinfo.value.code == "WRITE_CONFLICT"

    kv.put("tenant_a/one", {"v": 1})
    kv.put("tenantXa/two", {"v": 2})
    assert {key for key, _value, _version in kv.scan("tenant_a/")} == {"tenant_a/one"}

    kv.delete("tenant_a/one")
    assert kv.get("tenant_a/one") is None
    assert list(kv.scan("tenant_a/")) == []


def test_a_claimed_artifact_digest_is_verified_not_trusted(store):
    artifacts = DurableStoreArtifactStore(store, tenant_id="tenant-a")
    stored = artifacts.put(b"report body", media_type="text/plain")

    assert artifacts.get(stored) == b"report body"
    assert artifacts.stat(stored)["byteCount"] == 11
    assert artifacts.exists(stored) is True
    with pytest.raises(KernelSideError) as excinfo:
        artifacts.put(b"other body", media_type="text/plain", expected_digest=stored)
    assert excinfo.value.code == "DIGEST_MISMATCH"


def test_a_missing_artifact_is_missing_not_empty(store):
    artifacts = DurableStoreArtifactStore(store, tenant_id="tenant-a")
    with pytest.raises(KernelSideError) as excinfo:
        artifacts.get("sha256:" + "0" * 64)
    assert excinfo.value.code == "EVIDENCE_MISSING"


def test_the_lease_adapter_refuses_a_second_live_owner_and_stays_monotonic(store):
    leases = DurableStoreLeaseStore(store, tenant_id="tenant-a")
    first = leases.acquire("ws-adapter", "worker-a", ttl_seconds=60)
    with pytest.raises(KernelSideError) as excinfo:
        leases.acquire("ws-adapter", "worker-b", ttl_seconds=60)
    assert excinfo.value.code == "LEASE_HELD_BY_OTHER"

    leases.release("ws-adapter", "worker-a", first["fencingToken"])
    second = leases.acquire("ws-adapter", "worker-b", ttl_seconds=60)
    assert second["fencingToken"] > first["fencingToken"]
    assert leases.current_token("ws-adapter") == second["fencingToken"]

    with pytest.raises(KernelSideError) as excinfo:
        leases.renew("ws-adapter", "worker-a", first["fencingToken"], ttl_seconds=60)
    assert excinfo.value.code == "LEASE_LOST"


def test_a_token_from_one_resource_is_not_valid_for_another(store):
    leases = DurableStoreLeaseStore(store, tenant_id="tenant-a")
    held = leases.acquire("ws-one", "worker-a", ttl_seconds=60)
    leases.acquire("ws-two", "worker-b", ttl_seconds=60)
    with pytest.raises(KernelSideError) as excinfo:
        leases.renew("ws-two", "worker-a", held["fencingToken"], ttl_seconds=60)
    assert excinfo.value.code == "LEASE_LOST"


def test_the_adapters_raise_the_kernels_error_type_not_the_platforms(store):
    """The kernel catches its own type; a platform error would escape every
    ``except KernelError`` inside it and lose the code on the way out."""

    from elmos_repository_autonomy.errors import KernelError as PlatformError

    leases = DurableStoreLeaseStore(store, tenant_id="tenant-a")
    with pytest.raises(KernelSideError) as excinfo:
        leases.acquire("ws-ttl", "worker-a", ttl_seconds=0)
    assert not isinstance(excinfo.value, PlatformError)
    assert excinfo.value.code == "MALFORMED_INPUT"


def test_a_run_with_no_store_on_the_context_says_it_was_not_persisted():
    """Silence about an unwritten run is the exact defect this bridge exists to avoid.

    The dispatcher always supplies a store, so this is reached only by calling
    ``serve`` directly - which is precisely why the output has to say so rather
    than let the caller infer persistence from a successful status.
    """

    outcome = kernel_bridge.serve("durable-run-orchestrator", run_request(),
                                  DispatchContext(tenant_id="tenant-a", store=None))

    assert outcome.served is True
    assert "KERNEL_NOT_PERSISTED:NO_DURABLE_STORE_IN_CONTEXT" in outcome.reasons
    assert outcome.output["run"]["durable"] == {
        "persisted": False, "reason": "NO_DURABLE_STORE_IN_CONTEXT"}


def test_a_denied_policy_decision_does_not_report_as_validated(runtime, context):
    """The worst instance of the cross-engine status downgrade.

    The legacy handler returns BLOCKED with POLICY_DENIED on a DENY. The kernel
    returns the denial as data and SUCCEEDED for the evaluation - correct for
    the kernel, which was asked to evaluate a policy and did. Over the bridge
    that read as LOCAL_ENGINEERING_VALIDATED for a *denied action*, so a caller
    gating on the dispatch status would have proceeded with it.
    """

    result = runtime.execute("policy-hook-kernel", policy_request(), context=context)

    assert result.output["policy_decision"]["decision"] == "DENY"
    assert result.status == Status.BLOCKED
    assert "POLICY_DENIED" in result.reasons


def test_an_allowed_policy_decision_still_reports_as_validated(runtime, context):
    """Only DENY blocks - an ALLOW must not be dragged down with it."""

    layers = [{
        "layerId": "platform",
        "rules": [{"ruleId": "allow-src", "hookPoint": "pre-write", "decision": "ALLOW",
                   "explanation": "source edits are allowed",
                   "match": [{"field": "path", "op": "prefix", "value": "src/"}]}],
    }]
    result = runtime.execute("policy-hook-kernel", policy_request(layers), context=context)

    assert result.output["policy_decision"]["decision"] == "ALLOW"
    assert result.status == Status.LOCAL_ENGINEERING_VALIDATED
    assert "POLICY_DENIED" not in result.reasons
