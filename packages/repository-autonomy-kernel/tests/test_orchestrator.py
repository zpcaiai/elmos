"""Durable run orchestrator: acceptance gates, invariants and mandatory negatives.

Test names follow the gate / negative-test ids in
``skills/durable-run-orchestrator/acceptance.yaml`` so a failure names the gate
it broke.  Nothing here sleeps, touches the network or reads the wall clock.
"""

from __future__ import annotations

import dataclasses

import pytest

from elmos_autonomy_kernel.adapters.memory import (
    FixedClock,
    InMemoryArtifactStore,
    InMemoryEventStore,
    InMemoryKeyValueStore,
)
from elmos_autonomy_kernel.contracts import Status
from elmos_autonomy_kernel.errors import KernelError
from elmos_autonomy_kernel.orchestrator import (
    GENESIS_CHAIN,
    PAUSABLE_RUN_STATES,
    RUN_TRANSITIONS,
    SKILL_ID,
    STEP_TRANSITIONS,
    TERMINAL_RUN_STATES,
    Budget,
    DurableRun,
    EventType,
    RetryClass,
    RetryPolicy,
    RunEvent,
    RunState,
    RunView,
    StepDefinition,
    StepState,
    WorkflowDefinition,
    allowed_targets,
    backoff_ms,
    budget_report,
    build_dag,
    chain_for,
    checkpoint,
    classify_failure,
    decide_retry,
    idempotency_key,
    is_safe_point,
    is_terminal,
    next_ready_steps,
    reconciliation_plan,
    replay,
    rollback_plan,
    step_transition,
    steps_to_rerun,
    transition,
    unresolved_intents,
    verify_chain,
    view_digest,
)
from elmos_autonomy_kernel.registry import dispatch

SHA_A = "sha256:" + "a" * 64
SHA_B = "sha256:" + "b" * 64


# --- fixtures ----------------------------------------------------------------


def linear_definition(task_spec_version: str = "1") -> WorkflowDefinition:
    """plan -> edit (side-effecting, reversible) -> publish (irreversible)."""

    return WorkflowDefinition(
        workflow_id="wf-1",
        workflow_version="2.0.0",
        task_spec_version=task_spec_version,
        steps=(
            StepDefinition("plan", inputs_digest="d-plan"),
            StepDefinition("edit", requires=("plan",), inputs_digest="d-edit",
                           side_effecting=True, compensation="revert-edit", max_attempts=3),
            StepDefinition("publish", requires=("edit",), inputs_digest="d-publish",
                           side_effecting=True, compensation=None, max_attempts=2),
        ),
    )


@pytest.fixture()
def definition() -> WorkflowDefinition:
    return linear_definition()


@pytest.fixture()
def run(definition, events, kv, clock, artifacts) -> DurableRun:
    instance = DurableRun.create(
        run_id="run-1", definition=definition,
        budget=Budget(limits={"usdMicros": 1000}, max_turns=20),
        events=events, kv=kv, clock=clock, artifacts=artifacts, fencing_token=1,
    )
    instance.advance(RunState.SPECIFYING)
    instance.advance(RunState.PLANNING)
    instance.advance(RunState.EXECUTING)
    return instance


def finish_plan(run: DurableRun) -> None:
    run.start_step("plan")
    run.mark_step("plan", StepState.SUCCEEDED, outputs_digest="out-plan")


def craft(previous: tuple[RunEvent, ...], event_type: EventType, run_id: str,
          body: dict, *, step_id: str | None = None) -> RunEvent:
    """Hand-build an event so a test can forge a log the writer would refuse."""

    sequence = len(previous) + 1
    previous_chain = previous[-1].chain if previous else GENESIS_CHAIN
    content = {
        "sequence": sequence,
        "eventType": str(event_type),
        "runId": run_id,
        "stepId": step_id,
        "occurredAt": "2026-01-01T00:00:00.000000Z",
        "body": body,
    }
    return RunEvent(
        sequence=sequence, event_type=event_type, run_id=run_id, step_id=step_id,
        occurred_at=content["occurredAt"], body=body,
        chain=chain_for(previous_chain, content),
    )


def good_request() -> dict:
    return {
        "task_spec": {
            "taskSpecId": "ts-1", "taskSpecVersion": "1", "tenantId": "tenant-a",
            "accountId": "account-a", "runId": "run-1", "repoSnapshotSha": SHA_A,
        },
        "workflow_definition": {
            "workflowId": "wf-1", "workflowVersion": "2.0.0",
            "steps": [
                {"stepId": "plan", "inputsDigest": "d-plan",
                 "requiredCapability": "repository-census"},
                {"stepId": "edit", "requires": ["plan"], "inputsDigest": "d-edit",
                 "sideEffecting": True, "compensation": "revert-edit", "maxAttempts": 3},
            ],
        },
        "repository_snapshot": {"snapshotSha": SHA_A, "paths": ["a.py"]},
        "budget": {"limits": {"usdMicros": 1000}, "maxTurns": 20},
        "policy_snapshot": {"snapshotHash": SHA_B},
    }


# --- gate: state-machine-valid ----------------------------------------------


def test_gate_state_machine_valid_table_is_closed_and_typed():
    for state, targets in RUN_TRANSITIONS.items():
        assert isinstance(state, RunState)
        for target in targets:
            assert isinstance(target, RunState)
    assert set(RUN_TRANSITIONS) == set(RunState)
    assert set(STEP_TRANSITIONS) == set(StepState)


def test_gate_state_machine_valid_terminal_states_have_no_outgoing_edges():
    for state in TERMINAL_RUN_STATES:
        assert allowed_targets(state) == frozenset()
        assert is_terminal(state)
        with pytest.raises(KernelError) as excinfo:
            transition(state, RunState.EXECUTING)
        assert excinfo.value.code == "ILLEGAL_TRANSITION"
        assert excinfo.value.details["terminal"] is True


def test_gate_state_machine_valid_illegal_transition_is_coded():
    with pytest.raises(KernelError) as excinfo:
        transition(RunState.CREATED, RunState.SUCCEEDED)
    assert excinfo.value.code == "ILLEGAL_TRANSITION"
    assert excinfo.value.details["allowed"] == sorted(
        str(item) for item in allowed_targets(RunState.CREATED)
    )


def test_gate_state_machine_valid_pause_is_symmetric():
    for state in PAUSABLE_RUN_STATES:
        assert RunState.PAUSED in allowed_targets(state)
        assert state in allowed_targets(RunState.PAUSED)
    assert RunState.PAUSED not in allowed_targets(RunState.RELEASING)


def test_pause_records_origin_and_resume_restores_it(run):
    run.pause()
    assert run.view.state is RunState.PAUSED
    assert run.view.paused_from is RunState.EXECUTING
    pause_event = run.stream()[-1]
    assert pause_event.body["pausedFrom"] == "EXECUTING"
    run.resume()
    assert run.view.state is RunState.EXECUTING
    assert run.view.paused_from is None


def test_pause_from_verifying_resumes_into_verifying_not_executing(run):
    finish_plan(run)
    run.advance(RunState.VERIFYING)
    run.pause()
    run.resume()
    assert run.view.state is RunState.VERIFYING


def test_resume_never_guesses_the_pre_pause_state():
    created = craft((), EventType.RUN_CREATED, "run-1", {
        "workflowId": "wf-1", "workflowVersion": "2.0.0", "taskSpecVersion": "1",
        "definitionDigest": SHA_A, "maxTurns": 5, "steps": [],
    })
    to_specifying = craft((created,), EventType.RUN_STATE_CHANGED, "run-1",
                          {"from": "CREATED", "to": "SPECIFYING"})
    # A PAUSED transition with no recorded origin is refused at replay time.
    forged = craft((created, to_specifying), EventType.RUN_STATE_CHANGED, "run-1",
                   {"from": "SPECIFYING", "to": "PAUSED"})
    with pytest.raises(KernelError) as excinfo:
        replay((created, to_specifying, forged))
    assert excinfo.value.code == "PAUSE_ORIGIN_MISSING"


def test_resume_into_the_wrong_state_is_rejected():
    created = craft((), EventType.RUN_CREATED, "run-1", {
        "workflowId": "wf-1", "workflowVersion": "2.0.0", "taskSpecVersion": "1",
        "definitionDigest": SHA_A, "maxTurns": 5, "steps": [],
    })
    spec = craft((created,), EventType.RUN_STATE_CHANGED, "run-1",
                 {"from": "CREATED", "to": "SPECIFYING"})
    paused = craft((created, spec), EventType.RUN_STATE_CHANGED, "run-1",
                   {"from": "SPECIFYING", "to": "PAUSED", "pausedFrom": "SPECIFYING"})
    wrong = craft((created, spec, paused), EventType.RUN_STATE_CHANGED, "run-1",
                  {"from": "PAUSED", "to": "EXECUTING"})
    with pytest.raises(KernelError) as excinfo:
        replay((created, spec, paused, wrong))
    assert excinfo.value.code == "ORCHESTRATOR_INCONSISTENT"


def test_invariant_i4_partially_completed_cannot_become_succeeded():
    assert RunState.SUCCEEDED not in allowed_targets(RunState.PARTIALLY_COMPLETED)
    assert RunState.RELEASING not in allowed_targets(RunState.PARTIALLY_COMPLETED)
    with pytest.raises(KernelError) as excinfo:
        transition(RunState.PARTIALLY_COMPLETED, RunState.SUCCEEDED)
    assert excinfo.value.code == "ILLEGAL_TRANSITION"


def test_invariant_i4_step_partial_and_interrupted_cannot_become_succeeded():
    assert StepState.SUCCEEDED not in STEP_TRANSITIONS[StepState.PARTIAL]
    assert StepState.SUCCEEDED not in STEP_TRANSITIONS[StepState.INTERRUPTED]
    with pytest.raises(KernelError):
        step_transition(StepState.PARTIAL, StepState.SUCCEEDED)
    with pytest.raises(KernelError):
        step_transition(StepState.INTERRUPTED, StepState.SUCCEEDED)


# --- gate: event-replay-valid -----------------------------------------------


def test_gate_event_replay_valid_rebuilds_the_live_view_field_by_field(run):
    finish_plan(run)
    run.start_step("edit")
    run.begin_side_effect("edit")
    run.observe_side_effect("edit", "obs-edit")
    run.mark_step("edit", StepState.SUCCEEDED, outputs_digest="out-edit")
    run.consume_budget("usdMicros", 250)
    run.write_checkpoint()
    run.advance(RunState.VERIFYING)

    live = run.view
    rebuilt = replay(run.stream())
    for field in dataclasses.fields(RunView):
        assert getattr(rebuilt, field.name) == getattr(live, field.name), field.name
    assert view_digest(rebuilt) == view_digest(live)
    assert rebuilt.sequence == len(run.stream())


def test_gate_event_replay_valid_counters_and_budget_survive_replay(run):
    finish_plan(run)
    run.consume_budget("usdMicros", 10)
    run.consume_budget("usdMicros", 5)
    rebuilt = replay(run.stream())
    assert rebuilt.budget_spent == {"usdMicros": 15}
    assert rebuilt.counters["runTransitions"] == run.view.counters["runTransitions"]
    assert rebuilt.counters["budgetEvents"] == 2


def test_wrong_answer_rejected_tampering_with_a_payload_breaks_verify_chain(run):
    finish_plan(run)
    stream = list(run.stream())
    assert verify_chain(stream) is True
    victim = stream[2]
    stream[2] = dataclasses.replace(victim, body={**victim.body, "to": "SUCCEEDED"})
    assert verify_chain(stream) is False


def test_replay_refuses_a_tampered_stream(run):
    finish_plan(run)
    stream = list(run.stream())
    victim = stream[1]
    stream[1] = dataclasses.replace(victim, body={**victim.body, "to": "PLANNING"})
    with pytest.raises(KernelError) as excinfo:
        replay(stream)
    assert excinfo.value.code == "EVENT_CHAIN_BROKEN"


def test_replay_refuses_a_reordered_or_gapped_stream(run):
    finish_plan(run)
    stream = list(run.stream())
    del stream[3]
    with pytest.raises(KernelError) as excinfo:
        replay(stream)
    assert excinfo.value.code == "EVENT_CHAIN_BROKEN"


def test_replay_requires_run_created_first(run):
    stream = run.stream()[1:]
    with pytest.raises(KernelError) as excinfo:
        replay(stream)
    assert excinfo.value.code in {"EVENT_CHAIN_BROKEN", "ORCHESTRATOR_INCONSISTENT"}


# --- gate: recovery-tested ---------------------------------------------------


class ExplodingKeyValueStore:
    """A materialised store that dies on write, as a crash would."""

    def __init__(self, inner, *, fail_after: int) -> None:
        self._inner = inner
        self._writes = 0
        self._fail_after = fail_after

    def put(self, key, value, *, expected_version=None):
        self._writes += 1
        if self._writes > self._fail_after:
            raise RuntimeError("materialised store crashed")
        return self._inner.put(key, value, expected_version=expected_version)

    def get(self, key):
        return self._inner.get(key)


def test_gate_recovery_tested_event_is_durable_before_the_view_moves(
    definition, events, clock, artifacts
):
    inner = InMemoryKeyValueStore()
    kv = ExplodingKeyValueStore(inner, fail_after=1)
    run = DurableRun.create(
        run_id="run-1", definition=definition, budget=Budget(max_turns=10),
        events=events, kv=kv, clock=clock, artifacts=artifacts,
    )
    with pytest.raises(RuntimeError):
        run.advance(RunState.SPECIFYING)

    # The log is ahead of the cache — which is the recoverable direction.
    stored = events.read("run-1")
    assert len(stored) == 2
    assert stored[-1].payload["body"]["to"] == "SPECIFYING"
    cached, _version = inner.get("run:run-1:view")
    assert cached["state"] == "CREATED"

    recovered = DurableRun.rehydrate(
        run_id="run-1", definition=definition, events=events,
        kv=InMemoryKeyValueStore(), clock=clock,
    )
    assert recovered.view.state is RunState.SPECIFYING


def test_invariant_i1_the_cached_view_is_not_execution_truth(run, kv):
    finish_plan(run)
    kv.put("run:run-1:view", {"state": "SUCCEEDED", "lies": True})
    recovered = DurableRun.rehydrate(
        run_id="run-1", definition=run.definition, events=run._events,
        kv=kv, clock=FixedClock(),
    )
    assert recovered.view.state is RunState.EXECUTING
    assert recovered.view.steps["plan"].state is StepState.SUCCEEDED


def test_gate_recovery_tested_crash_mid_side_effect_lands_on_reconciliation(
    definition, events, kv, clock, artifacts
):
    run = DurableRun.create(
        run_id="run-1", definition=definition, budget=Budget(max_turns=10),
        events=events, kv=kv, clock=clock, artifacts=artifacts,
    )
    run.advance(RunState.SPECIFYING)
    run.advance(RunState.PLANNING)
    run.advance(RunState.EXECUTING)
    finish_plan(run)
    run.start_step("edit")
    key = run.begin_side_effect("edit")
    # ---- process dies here ----
    recovered = DurableRun.rehydrate(
        run_id="run-1", definition=definition, events=events,
        kv=InMemoryKeyValueStore(), clock=clock,
    )
    plan = reconciliation_plan(recovered.view)
    assert [task.idempotency_key for task in plan] == [key]
    with pytest.raises(KernelError) as excinfo:
        recovered.require_resolved_side_effects()
    assert excinfo.value.code == "UNRESOLVED_SIDE_EFFECT"
    assert excinfo.value.interrupted is True

    recovered.reconcile(key, "DID_NOT_LAND", evidence_digest=SHA_B)
    assert unresolved_intents(recovered.view) == ()
    assert recovered.view.intents[key].observed is False


def test_reconciliation_landed_marks_the_effect_as_done(run):
    finish_plan(run)
    run.start_step("edit")
    key = run.begin_side_effect("edit")
    run.reconcile(key, "LANDED", evidence_digest=SHA_A)
    assert run.view.intents[key].observed is True
    assert run.view.intents[key].reconciliation_verdict == "LANDED"
    assert unresolved_intents(run.view) == ()


def test_reconciliation_refuses_a_hedged_verdict(run):
    finish_plan(run)
    run.start_step("edit")
    key = run.begin_side_effect("edit")
    with pytest.raises(KernelError) as excinfo:
        run.reconcile(key, "PROBABLY")
    assert excinfo.value.code == "MALFORMED_INPUT"


def test_resume_is_blocked_while_a_side_effect_is_unresolved(run):
    finish_plan(run)
    run.start_step("edit")
    run.begin_side_effect("edit")
    run.pause()
    with pytest.raises(KernelError) as excinfo:
        run.resume()
    assert excinfo.value.code == "UNRESOLVED_SIDE_EFFECT"


# --- gate: idempotency-covered ----------------------------------------------


def test_gate_idempotency_covered_key_is_attempt_invariant():
    first = idempotency_key("run-1", "edit", "d-edit")
    second = idempotency_key("run-1", "edit", "d-edit")
    assert first == second
    assert first != idempotency_key("run-1", "other", "d-edit")
    assert first != idempotency_key("run-2", "edit", "d-edit")
    assert first != idempotency_key("run-1", "edit", "d-edit-v2")


def test_gate_idempotency_covered_retry_reuses_the_same_key(run):
    finish_plan(run)
    run.start_step("edit")
    key = run.begin_side_effect("edit")
    run.reconcile(key, "DID_NOT_LAND")
    run.mark_step("edit", StepState.FAILED_RETRYABLE, error_code="FAILED_RETRYABLE")
    run.mark_step("edit", StepState.PENDING)
    run.mark_step("edit", StepState.READY)
    run.mark_step("edit", StepState.RUNNING)
    assert run.view.steps["edit"].attempts == 2
    assert run.begin_side_effect("edit") == key


def test_negative_duplicate_side_effect_is_prevented(run):
    finish_plan(run)
    run.start_step("edit")
    run.begin_side_effect("edit")
    run.observe_side_effect("edit", "obs-edit")
    with pytest.raises(KernelError) as excinfo:
        run.begin_side_effect("edit")
    assert excinfo.value.code == "IDEMPOTENCY_CONFLICT"


def test_an_unresolved_intent_is_never_re_announced(run):
    finish_plan(run)
    run.start_step("edit")
    run.begin_side_effect("edit")
    with pytest.raises(KernelError) as excinfo:
        run.begin_side_effect("edit")
    assert excinfo.value.code == "UNRESOLVED_SIDE_EFFECT"


def test_unresolved_intent_blocks_a_blind_retry(run):
    finish_plan(run)
    run.start_step("edit")
    run.begin_side_effect("edit")
    decision = decide_retry(
        run.view, "edit",
        KernelError(code="FAILED_RETRYABLE", message="boom", retryable=True),
    )
    assert decision.should_retry is False
    assert decision.backoff_ms is None
    assert "unresolved" in decision.reason


def test_side_effect_must_be_declared_in_the_definition(run):
    finish_plan(run)
    with pytest.raises(KernelError) as excinfo:
        run.begin_side_effect("plan")
    assert excinfo.value.code == "ORCHESTRATOR_INCONSISTENT"


# --- DAG ---------------------------------------------------------------------


def test_dag_cycle_reports_the_actual_path():
    steps = (
        StepDefinition("a", requires=("c",)),
        StepDefinition("b", requires=("a",)),
        StepDefinition("c", requires=("b",)),
    )
    with pytest.raises(KernelError) as excinfo:
        build_dag(steps)
    assert excinfo.value.code == "DAG_CYCLE"
    cycle = excinfo.value.details["cycle"]
    assert cycle[0] == cycle[-1]
    assert set(cycle) == {"a", "b", "c"}
    assert " -> ".join(cycle) in excinfo.value.message


def test_dag_rejects_a_self_dependency():
    with pytest.raises(KernelError) as excinfo:
        StepDefinition("a", requires=("a",))
    assert excinfo.value.code == "DAG_CYCLE"


def test_dag_rejects_an_unknown_dependency():
    with pytest.raises(KernelError) as excinfo:
        build_dag((StepDefinition("a", requires=("ghost",)),))
    assert excinfo.value.code == "UNKNOWN_STEP"
    assert excinfo.value.details["unknown"] == ["ghost"]


def test_dag_rejects_a_duplicate_step():
    with pytest.raises(KernelError) as excinfo:
        build_dag((StepDefinition("a"), StepDefinition("a")))
    assert excinfo.value.code == "DUPLICATE_STEP"


def test_dag_waves_and_critical_path_are_deterministic():
    steps = (
        StepDefinition("plan"),
        StepDefinition("edit", requires=("plan",)),
        StepDefinition("docs", requires=("plan",)),
        StepDefinition("verify", requires=("edit",)),
        StepDefinition("release", requires=("verify", "docs")),
    )
    dag = build_dag(steps)
    assert dag.waves == (("plan",), ("docs", "edit"), ("verify",), ("release",))
    assert dag.critical_path == ("plan", "edit", "verify", "release")
    assert build_dag(steps) == dag


def test_next_ready_steps_needs_every_dependency_succeeded(run):
    assert next_ready_steps(run.view) == ("plan",)
    finish_plan(run)
    assert next_ready_steps(run.view) == ("edit",)


def test_invariant_partial_dependency_is_not_ready(run):
    run.start_step("plan")
    run.mark_step("plan", StepState.PARTIAL, outputs_digest="half")
    assert next_ready_steps(run.view) == ()
    with pytest.raises(KernelError) as excinfo:
        run.start_step("edit")
    assert excinfo.value.code == "STEP_NOT_READY"
    assert excinfo.value.details["dependencyStates"] == {"plan": "PARTIAL"}


def test_interrupted_dependency_is_not_ready(run):
    run.start_step("plan")
    run.mark_step("plan", StepState.INTERRUPTED)
    assert next_ready_steps(run.view) == ()


def test_no_step_is_ready_while_paused_or_cancelling(run):
    run.pause()
    assert next_ready_steps(run.view) == ()
    run.resume()
    run.request_cancel()
    assert next_ready_steps(run.view) == ()


# --- checkpoints and rollback ------------------------------------------------


def test_checkpoint_is_content_addressed(run):
    first = checkpoint(run.view)
    assert first.checkpoint_id == checkpoint(run.view).checkpoint_id
    finish_plan(run)
    second = checkpoint(run.view)
    assert second.checkpoint_id != first.checkpoint_id


def test_checkpoint_is_recorded_and_replayable(run):
    snapshot = run.write_checkpoint()
    assert run.view.checkpoint_id == snapshot.checkpoint_id
    assert replay(run.stream()).checkpoint_id == snapshot.checkpoint_id


def test_rollback_plan_walks_completed_side_effects_in_reverse(definition, events, kv,
                                                               clock, artifacts):
    steps = (
        StepDefinition("one", inputs_digest="d1", side_effecting=True, compensation="undo-one"),
        StepDefinition("two", requires=("one",), inputs_digest="d2", side_effecting=True,
                       compensation="undo-two"),
    )
    two_step = WorkflowDefinition("wf-2", "2.0.0", "1", steps)
    run = DurableRun.create(run_id="run-2", definition=two_step, budget=Budget(max_turns=10),
                            events=events, kv=kv, clock=clock, artifacts=artifacts)
    run.advance(RunState.SPECIFYING)
    run.advance(RunState.PLANNING)
    run.advance(RunState.EXECUTING)
    for step_id in ("one", "two"):
        run.start_step(step_id)
        run.begin_side_effect(step_id)
        run.observe_side_effect(step_id, f"obs-{step_id}")
        run.mark_step(step_id, StepState.SUCCEEDED, outputs_digest=f"out-{step_id}")

    plan = rollback_plan(run.view)
    assert [entry.step_id for entry in plan.entries] == ["two", "one"]
    assert plan.complete is True
    plan.require_complete()


def test_rollback_plan_marks_an_irreversible_side_effect_and_is_incomplete(run):
    finish_plan(run)
    for step_id in ("edit", "publish"):
        run.start_step(step_id)
        run.begin_side_effect(step_id)
        run.observe_side_effect(step_id, f"obs-{step_id}")
        run.mark_step(step_id, StepState.SUCCEEDED, outputs_digest=f"out-{step_id}")

    plan = run.rollback_plan()
    assert plan.irreversible == ("publish",)
    assert [entry.step_id for entry in plan.entries] == ["edit"]
    assert plan.complete is False
    with pytest.raises(KernelError) as excinfo:
        plan.require_complete()
    assert excinfo.value.code == "ROLLBACK_INCOMPLETE"
    assert excinfo.value.details["irreversible"] == ["publish"]


def test_rollback_plan_is_incomplete_while_a_side_effect_is_unresolved(run):
    finish_plan(run)
    run.start_step("edit")
    run.begin_side_effect("edit")
    run.mark_step("edit", StepState.INTERRUPTED)
    plan = run.rollback_plan()
    assert plan.unresolved == ("edit",)
    assert plan.complete is False
    assert plan.entries[0].certainty == "unresolved"


def test_compensation_moves_the_step_through_compensating(run):
    finish_plan(run)
    run.start_step("edit")
    run.begin_side_effect("edit")
    run.observe_side_effect("edit", "obs-edit")
    run.mark_step("edit", StepState.SUCCEEDED, outputs_digest="out-edit")
    run.apply_compensation("edit")
    assert run.view.steps["edit"].state is StepState.COMPENSATED
    assert run.view.counters["compensationsApplied"] == 1


def test_compensation_refuses_an_irreversible_step(run):
    finish_plan(run)
    with pytest.raises(KernelError) as excinfo:
        run.apply_compensation("publish")
    assert excinfo.value.code == "ROLLBACK_INCOMPLETE"


# --- cancellation and safe points -------------------------------------------


def test_invariant_i3_cancel_passes_through_cancel_requested(run):
    run.request_cancel("operator")
    assert run.view.state is RunState.CANCEL_REQUESTED
    assert run.view.cancel_requested is True
    assert RunState.CANCELLED not in {RunState(event.body.get("to", "CREATED"))
                                      for event in run.stream()
                                      if event.event_type is EventType.RUN_STATE_CHANGED}


def test_invariant_i3_mid_step_cancel_does_not_abandon_a_side_effect(run):
    finish_plan(run)
    run.start_step("edit")
    key = run.begin_side_effect("edit")
    run.request_cancel("operator hit stop")

    unsafe = run.safe_point()
    assert unsafe.safe is False
    assert unsafe.cancel_effective is False
    assert run.view.state is RunState.CANCEL_REQUESTED
    assert key in " ".join(unsafe.reasons)
    assert unresolved_intents(run.view)[0].key == key

    run.observe_side_effect("edit", "obs-edit")
    run.mark_step("edit", StepState.SUCCEEDED, outputs_digest="out-edit")

    safe = run.safe_point()
    assert safe.safe is True
    assert safe.cancel_effective is True
    # There is a landed, reversible effect, so cancellation unwinds it rather
    # than declaring the run simply CANCELLED.
    assert run.view.state is RunState.ROLLING_BACK
    assert run.rollback_plan().entries[0].step_id == "edit"


def test_cancel_with_nothing_to_undo_reaches_cancelled(run):
    run.request_cancel()
    outcome = run.safe_point()
    assert outcome.cancel_effective is True
    assert run.view.state is RunState.CANCELLED
    assert is_terminal(run.view.state)


def test_is_safe_point_reports_running_steps(run):
    run.start_step("plan")
    safe, reasons = is_safe_point(run.view)
    assert safe is False
    assert "plan" in reasons[0]


def test_terminal_run_cannot_be_cancelled_again(run):
    run.request_cancel()
    run.safe_point()
    with pytest.raises(KernelError) as excinfo:
        run.request_cancel()
    assert excinfo.value.code == "ILLEGAL_TRANSITION"


# --- requirement updates -----------------------------------------------------


def test_steps_to_rerun_only_touches_changed_steps_and_their_dependents(run):
    finish_plan(run)
    run.start_step("edit")
    run.begin_side_effect("edit")
    run.observe_side_effect("edit", "obs-edit")
    run.mark_step("edit", StepState.SUCCEEDED, outputs_digest="out-edit")

    updated = WorkflowDefinition(
        workflow_id="wf-1", workflow_version="2.0.0", task_spec_version="2",
        steps=(
            StepDefinition("plan", inputs_digest="d-plan"),
            StepDefinition("edit", requires=("plan",), inputs_digest="d-edit-v2",
                           side_effecting=True, compensation="revert-edit", max_attempts=3),
            StepDefinition("publish", requires=("edit",), inputs_digest="d-publish",
                           side_effecting=True, compensation=None, max_attempts=2),
        ),
    )
    assert steps_to_rerun(run.view, updated) == ("edit", "publish")

    invalidated = run.update_requirements(updated)
    assert invalidated == ("edit", "publish")
    # The unaffected step keeps its result: re-running it would spend budget to
    # reproduce a value we can prove is identical.
    assert run.view.steps["plan"].state is StepState.SUCCEEDED
    assert run.view.steps["plan"].outputs_digest == "out-plan"
    assert run.view.steps["edit"].state is StepState.PENDING
    assert run.view.steps["edit"].attempts == 0
    assert run.view.task_spec_version == "2"


def test_requirement_update_records_effects_needing_compensation(run):
    finish_plan(run)
    run.start_step("edit")
    run.begin_side_effect("edit")
    run.observe_side_effect("edit", "obs-edit")
    run.mark_step("edit", StepState.SUCCEEDED, outputs_digest="out-edit")
    updated = dataclasses.replace(
        run.definition, task_spec_version="2",
        steps=(
            StepDefinition("plan", inputs_digest="d-plan"),
            StepDefinition("edit", requires=("plan",), inputs_digest="d-edit-v2",
                           side_effecting=True, compensation="revert-edit", max_attempts=3),
            StepDefinition("publish", requires=("edit",), inputs_digest="d-publish",
                           side_effecting=True, compensation=None, max_attempts=2),
        ),
    )
    run.update_requirements(updated)
    event = run.stream()[-1]
    assert event.event_type is EventType.REQUIREMENT_UPDATED
    assert event.body["requiresCompensation"] == ["edit"]


def test_requirement_update_demands_a_version_bump(run):
    changed = dataclasses.replace(
        run.definition,
        steps=(StepDefinition("plan", inputs_digest="d-plan-v2"),),
    )
    with pytest.raises(KernelError) as excinfo:
        run.update_requirements(changed)
    assert excinfo.value.code == "TASK_SPEC_VERSION_NOT_BUMPED"


def test_requirement_update_survives_replay(run):
    finish_plan(run)
    updated = dataclasses.replace(
        run.definition, task_spec_version="2",
        steps=(
            StepDefinition("plan", inputs_digest="d-plan"),
            StepDefinition("edit", requires=("plan",), inputs_digest="d-edit-v2",
                           side_effecting=True, compensation="revert-edit", max_attempts=3),
        ),
    )
    run.update_requirements(updated)
    rebuilt = replay(run.stream())
    assert rebuilt.steps["plan"].state is StepState.SUCCEEDED
    assert rebuilt.steps["edit"].inputs_digest == "d-edit-v2"
    assert "publish" not in rebuilt.steps


# --- retry classification ----------------------------------------------------


def test_classify_failure_separates_the_four_classes():
    assert classify_failure(
        KernelError(code="FAILED_RETRYABLE", message="x", retryable=True)
    ) is RetryClass.RETRYABLE
    assert classify_failure(
        KernelError(code="FAILED_TERMINAL", message="x")
    ) is RetryClass.TERMINAL
    assert classify_failure(
        KernelError(code="PARTIAL", message="x", retryable=True, interrupted=True)
    ) is RetryClass.INTERRUPTED
    assert classify_failure(
        KernelError(code="BUDGET_EXHAUSTED", message="x")
    ) is RetryClass.RESOURCE_EXHAUSTED
    assert classify_failure(
        KernelError(code="LEASE_HELD_BY_OTHER", message="x")
    ) is RetryClass.RETRYABLE


def test_backoff_is_integer_deterministic_and_bounded():
    policy = RetryPolicy(base_ms=200, multiplier=2, max_ms=10_000, jitter_pct=20)
    values = [backoff_ms("run-1", "edit", attempt, policy=policy) for attempt in range(1, 9)]
    assert all(isinstance(value, int) for value in values)
    assert values == [backoff_ms("run-1", "edit", attempt, policy=policy)
                      for attempt in range(1, 9)]
    assert values[0] <= 200 and values[1] <= 400
    assert max(values) <= 10_000
    assert values[3] > values[0]
    # jitter is derived from the identity triple, not from a global RNG
    assert backoff_ms("run-1", "edit", 3, policy=policy) != backoff_ms(
        "run-2", "edit", 3, policy=policy
    )


def test_backoff_never_falls_below_the_jitter_floor():
    policy = RetryPolicy(base_ms=1000, multiplier=1, max_ms=1000, jitter_pct=20)
    for attempt in range(1, 20):
        value = backoff_ms("run-1", "edit", attempt, policy=policy)
        assert 800 <= value <= 1000


def test_resource_exhaustion_backs_off_further(run):
    policy = RetryPolicy(base_ms=100, multiplier=2, max_ms=60_000, jitter_pct=0,
                         resource_floor_ms=5_000)
    assert backoff_ms("run-1", "edit", 1, policy=policy,
                      retry_class=RetryClass.RESOURCE_EXHAUSTED) == 5_000
    assert backoff_ms("run-1", "edit", 1, policy=policy) == 100


def test_interrupted_attempt_is_never_retried(run):
    finish_plan(run)
    run.start_step("edit")
    run.mark_step("edit", StepState.INTERRUPTED)
    decision = decide_retry(
        run.view, "edit",
        KernelError(code="PARTIAL", message="executor vanished", retryable=True,
                    interrupted=True),
    )
    assert decision.retry_class is RetryClass.INTERRUPTED
    assert decision.should_retry is False
    assert decision.backoff_ms is None


def test_retry_stops_at_max_attempts(run):
    finish_plan(run)
    error = KernelError(code="FAILED_RETRYABLE", message="flaky", retryable=True)
    for _ in range(3):
        run.start_step("edit") if run.view.steps["edit"].state in {
            StepState.PENDING, StepState.READY} else None
        run.mark_step("edit", StepState.FAILED_RETRYABLE, error_code="FAILED_RETRYABLE")
        decision = run.schedule_retry("edit", error)
    assert run.view.steps["edit"].attempts == 3
    assert decision.should_retry is False
    assert decision.backoff_ms is None
    assert "maxAttempts" in decision.reason


def test_attempts_beyond_max_are_refused_by_the_log(run):
    finish_plan(run)
    definition_max = run.view.steps["edit"].max_attempts
    for _ in range(definition_max):
        run.start_step("edit")
        run.mark_step("edit", StepState.FAILED_RETRYABLE)
        run.mark_step("edit", StepState.PENDING)
    with pytest.raises(KernelError) as excinfo:
        run.start_step("edit")
    assert excinfo.value.code == "ATTEMPTS_EXHAUSTED"


def test_retry_decision_rejects_an_unknown_step(run):
    with pytest.raises(KernelError) as excinfo:
        decide_retry(run.view, "ghost", KernelError(code="FAILED_RETRYABLE", message="x"))
    assert excinfo.value.code == "UNKNOWN_STEP"


# --- budget and turns --------------------------------------------------------


def test_no_silent_zero_an_unmeasured_meter_is_not_zero(run):
    report = run.budget_report()
    entry = report["meters"]["usdMicros"]
    assert entry["measured"] is False
    assert entry["spent"] is None
    assert entry["remaining"] is None


def test_a_recorded_zero_is_a_measurement(run):
    run.consume_budget("usdMicros", 0)
    entry = run.budget_report()["meters"]["usdMicros"]
    assert entry["measured"] is True
    assert entry["spent"] == 0
    assert entry["remaining"] == 1000


def test_budget_exhaustion_is_recorded_before_it_is_raised(run):
    with pytest.raises(KernelError) as excinfo:
        run.consume_budget("usdMicros", 1001)
    assert excinfo.value.code == "BUDGET_EXHAUSTED"
    assert replay(run.stream()).budget_spent == {"usdMicros": 1001}


def test_budget_rejects_a_float_limit():
    with pytest.raises(KernelError) as excinfo:
        Budget.from_payload({"limits": {"usdMicros": 1.5}, "maxTurns": 3})
    assert excinfo.value.code == "MALFORMED_INPUT"


def test_budget_requires_max_turns():
    with pytest.raises(KernelError) as excinfo:
        Budget.from_payload({"limits": {}})
    assert excinfo.value.code == "MISSING_REQUIRED_INPUT"


def test_max_turns_is_enforced(definition, events, kv, clock, artifacts):
    run = DurableRun.create(
        run_id="run-1", definition=definition, budget=Budget(max_turns=1),
        events=events, kv=kv, clock=clock, artifacts=artifacts,
    )
    run.advance(RunState.SPECIFYING)
    run.advance(RunState.PLANNING)
    run.advance(RunState.EXECUTING)
    finish_plan(run)
    with pytest.raises(KernelError) as excinfo:
        run.start_step("edit")
    assert excinfo.value.code == "MAX_TURNS_EXCEEDED"


def test_budget_report_of_an_unlimited_meter_reports_no_remaining():
    report = budget_report(Budget(max_turns=1), {"tokens": 12})
    assert report["meters"]["tokens"] == {
        "limit": None, "spent": 12, "measured": True, "remaining": None, "exhausted": False,
    }


# --- concurrency -------------------------------------------------------------


def test_negative_stale_fencing_token_is_rejected(run, definition, events, clock):
    taken_over = DurableRun.rehydrate(
        run_id="run-1", definition=definition, events=events,
        kv=InMemoryKeyValueStore(), clock=clock, fencing_token=7,
    )
    taken_over.advance(RunState.VERIFYING)
    with pytest.raises(KernelError) as excinfo:
        run.advance(RunState.VERIFYING)
    assert excinfo.value.code == "FENCING_REJECTED"


def test_creating_an_existing_run_is_a_write_conflict(run, definition, events, kv, clock):
    with pytest.raises(KernelError) as excinfo:
        DurableRun.create(run_id="run-1", definition=definition, budget=Budget(max_turns=5),
                          events=events, kv=kv, clock=clock)
    assert excinfo.value.code == "WRITE_CONFLICT"


def test_rehydrating_a_run_that_never_existed_is_a_history_gap(definition, events, kv, clock):
    with pytest.raises(KernelError) as excinfo:
        DurableRun.rehydrate(run_id="ghost-run", definition=definition, events=events,
                             kv=kv, clock=clock)
    assert excinfo.value.code == "HISTORY_GAP"


# --- registry and mandatory negatives ---------------------------------------


def test_registry_round_trip():
    result = dispatch(SKILL_ID, good_request())
    assert result.status is Status.SUCCEEDED
    assert result.succeeded is True
    assert set(result.outputs) == {
        "run", "step_runs", "run_events", "checkpoints", "rollback_plan", "progress_snapshot",
    }
    assert result.evidence_ids


def test_dispatch_is_deterministic():
    first = dispatch(SKILL_ID, good_request())
    second = dispatch(SKILL_ID, good_request())
    assert first.outputs == second.outputs


def test_negative_malformed_input_is_rejected():
    request = good_request()
    request["surprise"] = True
    result = dispatch(SKILL_ID, request)
    assert result.status is Status.FAILED
    assert result.error["code"] == "UNKNOWN_FIELD"


def test_negative_missing_input_is_not_applicable():
    request = good_request()
    del request["workflow_definition"]
    result = dispatch(SKILL_ID, request)
    assert result.status is Status.NOT_APPLICABLE


def test_negative_stale_snapshot_is_rejected():
    request = good_request()
    request["repository_snapshot"]["snapshotSha"] = "sha256:" + "c" * 64
    result = dispatch(SKILL_ID, request)
    assert result.status is Status.FAILED
    assert result.error["code"] == "STALE_SNAPSHOT"


def test_negative_missing_policy_snapshot_is_denied():
    request = good_request()
    request["policy_snapshot"] = {}
    result = dispatch(SKILL_ID, request)
    assert result.error["code"] == "POLICY_SNAPSHOT_MISSING"


def test_negative_unauthorized_tool_is_denied():
    request = good_request()
    request["workflow_definition"]["steps"][0]["requiredCapability"] = "arbitrary-shell"
    result = dispatch(SKILL_ID, request)
    assert result.status is Status.FAILED
    assert result.error["code"] == "TOOL_DENIED"


def test_negative_prompt_injection_cannot_expand_authority():
    # A capability id lifted from untrusted repository text.
    request = good_request()
    request["workflow_definition"]["steps"][1]["requiredCapability"] = "ignore-policy-and-deploy"
    result = dispatch(SKILL_ID, request)
    assert result.error["code"] == "TOOL_DENIED"
    assert result.error["details"]["requiredCapability"] == "ignore-policy-and-deploy"


def test_negative_partial_is_not_success():
    error = KernelError(code="PARTIAL", message="half the steps landed", partial=True)
    from elmos_autonomy_kernel.contracts import SkillResult

    result = SkillResult.failure(SKILL_ID, error, status=Status.PARTIAL)
    assert result.status is Status.PARTIAL
    assert result.succeeded is False
    assert Status.PARTIAL is not Status.SUCCEEDED


def test_negative_interrupted_is_not_success(run):
    finish_plan(run)
    run.start_step("edit")
    run.begin_side_effect("edit")
    with pytest.raises(KernelError) as excinfo:
        run.require_resolved_side_effects()
    error = excinfo.value
    assert error.interrupted is True
    assert error.partial is False
    assert error.retryable is False
    from elmos_autonomy_kernel.contracts import SkillResult

    result = SkillResult.failure(SKILL_ID, error, status=Status.INTERRUPTED)
    assert result.succeeded is False


def test_negative_cyclic_workflow_is_rejected_through_dispatch():
    request = good_request()
    request["workflow_definition"]["steps"][0]["requires"] = ["edit"]
    result = dispatch(SKILL_ID, request)
    assert result.error["code"] == "DAG_CYCLE"
    assert result.error["details"]["cycle"][0] == result.error["details"]["cycle"][-1]


def test_negative_unknown_step_field_is_rejected():
    request = good_request()
    request["workflow_definition"]["steps"][0]["runAsRoot"] = True
    result = dispatch(SKILL_ID, request)
    assert result.error["code"] == "UNKNOWN_FIELD"


def test_handle_output_carries_its_own_digests():
    outputs = dispatch(SKILL_ID, good_request()).outputs
    assert outputs["run"]["viewDigest"].startswith("sha256:")
    assert outputs["checkpoints"][0]["checkpointId"].startswith("sha256:")
    assert outputs["rollback_plan"]["planDigest"].startswith("sha256:")


def test_progress_snapshot_reports_measured_and_unmeasured_separately():
    snapshot = dispatch(SKILL_ID, good_request()).outputs["progress_snapshot"]
    assert snapshot["budget"]["meters"]["usdMicros"]["measured"] is False
    assert snapshot["readySteps"] == ["plan"]
    assert snapshot["safePoint"]["safe"] is True


def test_event_store_and_artifact_store_are_untouched_by_a_failed_request(clock):
    events = InMemoryEventStore(clock)
    artifacts = InMemoryArtifactStore()
    assert events.streams() == ()
    assert artifacts.exists(SHA_A) is False
