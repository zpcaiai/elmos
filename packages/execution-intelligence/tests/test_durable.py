"""Durable execution properties, asserted rather than described."""
import json

import pytest
from conftest import PROJECT_PATH

from elmos_execution_intelligence.durable import (
    Conflict,
    DurableStore,
    LogicalClock,
    Orchestrator,
    TaskOutcome,
    recovery_aware_eta,
    replay_is_gapless,
)

PROJECT = json.loads(PROJECT_PATH.read_text(encoding="utf-8"))


def _dag(n=4, chain=True):
    tasks = []
    for index in range(n):
        tasks.append({
            "id": f"t{index}",
            "name": f"task {index}",
            "depends_on": [f"t{index - 1}"] if chain and index else [],
            "category": "verification",
            "complexity": "medium",
            "system": {
                "optimistic_minutes": 5, "most_likely_minutes": 10, "pessimistic_minutes": 20,
                "worker_units": 1,
                "token_profile": {"input": 1000, "cached_input": 2000, "cache_write": 100,
                                  "output": 300, "reasoning_output": 100},
            },
            "human": {"hours_by_role": {"qa": 1}},
        })
    return {"schema_version": "1.0.0", "dag_id": "test-dag", "tasks": tasks}


@pytest.fixture()
def store():
    s = DurableStore(":memory:", clock=LogicalClock(start=1000.0, step=1.0))
    yield s
    s.close()


@pytest.fixture()
def run(store):
    return store.create_run(PROJECT, _dag())


def always_succeed(task, attempt):
    return TaskOutcome(status="succeeded",
                       tokens={"input": 1000, "cached_input": 2000, "output": 300},
                       execution_ms=600_000, git_commit=f"commit-{task['task_id']}",
                       artifacts=[(f"{task['task_id']}.txt", b"payload")], model="test-model")


# ------------------------------------------------------------------ 08 orchestration --

def test_a_clean_run_completes_every_task(store, run):
    result = Orchestrator(store, run).run_to_completion(always_succeed)
    assert result["state"] == "succeeded"
    assert all(task["state"] == "succeeded" for task in result["tasks"])


def test_dependencies_are_respected(store, run):
    order = []

    def executor(task, attempt):
        order.append(task["task_id"])
        return always_succeed(task, attempt)

    Orchestrator(store, run).run_to_completion(executor)
    assert order == ["t0", "t1", "t2", "t3"]


def test_a_task_wider_than_capacity_is_never_scheduled(store):
    dag = _dag(1, chain=False)
    dag["tasks"][0]["system"]["worker_units"] = 99
    run_id = store.create_run(PROJECT, dag)
    orchestrator = Orchestrator(store, run_id, capacity=4.0)
    assert orchestrator.ready_tasks() == []
    assert orchestrator.step(always_succeed) is None


# ------------------------------------------------------------------ retry policy -----

def test_transient_failures_retry_with_growing_backoff(store):
    run_id = store.create_run(PROJECT, _dag(1, chain=False))
    attempts = []

    def flaky(task, attempt):
        attempts.append(attempt)
        if attempt < 3:
            return TaskOutcome(status="failed", failure_class="transient", execution_ms=1000)
        return always_succeed(task, attempt)

    orchestrator = Orchestrator(store, run_id)
    backoffs = []
    while True:
        result = orchestrator.step(flaky)
        if result is None:
            break
        if result["status"] == "retry_scheduled":
            backoffs.append(result["backoff_seconds"])
    assert attempts == [1, 2, 3]
    assert backoffs == sorted(backoffs) and len(backoffs) == 2
    assert backoffs[1] > backoffs[0]


def test_permanent_failures_do_not_retry(store):
    run_id = store.create_run(PROJECT, _dag(1, chain=False))
    calls = []

    def broken(task, attempt):
        calls.append(attempt)
        return TaskOutcome(status="failed", failure_class="permanent")

    result = Orchestrator(store, run_id).run_to_completion(broken)
    assert calls == [1]
    assert result["state"] == "failed"


def test_business_conflict_does_not_retry_either(store):
    run_id = store.create_run(PROJECT, _dag(1, chain=False))
    calls = []

    def conflicted(task, attempt):
        calls.append(attempt)
        return TaskOutcome(status="failed", failure_class="business_conflict")

    Orchestrator(store, run_id).run_to_completion(conflicted)
    assert calls == [1]


def test_a_failed_task_blocks_its_dependents(store, run):
    def fail_second(task, attempt):
        if task["task_id"] == "t1":
            return TaskOutcome(status="failed", failure_class="permanent")
        return always_succeed(task, attempt)

    result = Orchestrator(store, run).run_to_completion(fail_second)
    states = {task["task_id"]: task["state"] for task in result["tasks"]}
    assert states["t0"] == "succeeded"
    assert states["t1"] == "failed"
    assert states["t2"] != "succeeded" and states["t3"] != "succeeded"


# ------------------------------------------------------------------ 09 recovery ------

def test_a_killed_worker_leaves_the_run_recoverable(store, run):
    class WorkerKilled(BaseException):
        pass

    def dies_on_second(task, attempt):
        if task["task_id"] == "t1":
            raise WorkerKilled()
        return always_succeed(task, attempt)

    orchestrator = Orchestrator(store, run, heartbeat_timeout_seconds=5.0)
    orchestrator.step(dies_on_second)          # t0 succeeds
    with pytest.raises(WorkerKilled):
        orchestrator.step(dies_on_second)      # t1's worker vanishes

    assert store.open_attempts(run), "the interrupted attempt must stay open for the sweeper"

    store.clock.advance(120)
    recovery = Orchestrator(store, run, heartbeat_timeout_seconds=5.0).resume()
    assert recovery["completed_tasks"] == ["t0"]
    assert "t1" in recovery["lost_attempts"]

    result = Orchestrator(store, run, heartbeat_timeout_seconds=5.0).run_to_completion(always_succeed)
    assert result["state"] == "succeeded"


def test_resume_on_a_fresh_orchestrator_does_not_redo_completed_work(store, run):
    executed = []

    def counting(task, attempt):
        executed.append(task["task_id"])
        return always_succeed(task, attempt)

    Orchestrator(store, run).step(counting)
    Orchestrator(store, run).step(counting)
    assert executed == ["t0", "t1"]

    # A brand new orchestrator object, as if the process had restarted.
    Orchestrator(store, run).run_to_completion(counting)
    assert executed == ["t0", "t1", "t2", "t3"]


def test_lost_attempts_are_classified_lost_not_failed(store, run):
    orchestrator = Orchestrator(store, run, heartbeat_timeout_seconds=5.0)
    store.start_attempt(run, "t0", "worker-x")
    store.clock.advance(60)
    lost = orchestrator.store.sweep_lost_attempts(run, 5.0)
    assert len(lost) == 1
    row = store.connection.execute(
        "SELECT outcome, failure_class FROM task_attempt WHERE run_id = ?", (run,)).fetchone()
    assert row["outcome"] == "lost"
    assert row["failure_class"] == "lost_worker"


def test_reconciliation_adopts_an_existing_commit_instead_of_retrying(store, run):
    store.record_checkpoint(run, "t0", "git", git_commit="abc123")
    checks = Orchestrator(store, run).reconcile_before_retry("t0", expected_commit="abc123")
    assert checks["original_commit"] == "present"
    assert checks["decision"] == "adopt_existing_result"


def test_reconciliation_says_retry_when_nothing_landed(store, run):
    checks = Orchestrator(store, run).reconcile_before_retry("t0", expected_commit="never-made")
    assert checks["decision"] == "retry"


def test_checkpoints_are_recorded_for_every_completed_task(store, run):
    Orchestrator(store, run).run_to_completion(always_succeed)
    checkpointed = {c["task_id"] for c in store.checkpoints(run)}
    assert checkpointed == {"t0", "t1", "t2", "t3"}


# ------------------------------------------------------------------ 10 idempotency ---

def test_replaying_a_key_returns_the_original_response_without_re_executing(store):
    status, _ = store.begin_idempotent("payment", "key-1", {"amount": 10})
    assert status == "claimed"
    store.complete_idempotent("payment", "key-1", {"receipt": "r1"})

    status, response = store.begin_idempotent("payment", "key-1", {"amount": 10})
    assert status == "replayed"
    assert response == {"receipt": "r1"}


def test_an_in_flight_key_is_not_executed_concurrently(store):
    store.begin_idempotent("payment", "key-2", {"amount": 1})
    status, _ = store.begin_idempotent("payment", "key-2", {"amount": 1})
    assert status == "in_flight"


def test_reusing_a_key_with_a_different_body_is_a_conflict(store):
    store.begin_idempotent("payment", "key-3", {"amount": 1})
    with pytest.raises(Conflict):
        store.begin_idempotent("payment", "key-3", {"amount": 999})


def test_a_failed_effect_releases_its_key_for_a_later_retry(store):
    store.begin_idempotent("payment", "key-4", {"amount": 1})
    store.fail_idempotent("payment", "key-4")
    status, _ = store.begin_idempotent("payment", "key-4", {"amount": 1})
    assert status == "claimed"


def test_republishing_identical_bytes_is_deduplicated(store, run):
    first = store.publish_artifact(run, "report.md", b"same bytes")
    second = store.publish_artifact(run, "report.md", b"same bytes")
    assert second["deduplicated"] is True
    assert second["version"] == first["version"]
    assert len(store.artifacts(run)) == 1


def test_different_bytes_take_a_new_version_and_never_overwrite(store, run):
    first = store.publish_artifact(run, "report.md", b"v1")
    second = store.publish_artifact(run, "report.md", b"v2")
    assert second["version"] == first["version"] + 1
    assert {a["version"] for a in store.artifacts(run)} == {1, 2}


def test_outbox_rows_are_written_with_the_state_change(store, run):
    Orchestrator(store, run).run_to_completion(always_succeed)
    pending = store.unpublished_outbox()
    assert {row["payload"]["task_id"] for row in pending} == {"t0", "t1", "t2", "t3"}
    store.mark_published(pending[0]["outbox_id"])
    assert len(store.unpublished_outbox()) == len(pending) - 1


# ------------------------------------------------------------------ 11 event stream --

def test_event_sequence_is_monotonic_and_gapless(store, run):
    Orchestrator(store, run).run_to_completion(always_succeed)
    events = store.events_since(run, 0, limit=10_000)
    assert len(events) > 4
    assert replay_is_gapless(events, 0)


def test_reconnect_replays_exactly_what_was_missed(store, run):
    Orchestrator(store, run).run_to_completion(always_succeed)
    everything = store.events_since(run, 0, limit=10_000)
    cut = len(everything) // 2
    last_seen = everything[cut - 1]["seq"]

    replayed = store.events_since(run, last_seen, limit=10_000)
    assert replay_is_gapless(replayed, last_seen)
    assert [event["seq"] for event in replayed] == [event["seq"] for event in everything[cut:]]
    assert not any(event["seq"] <= last_seen for event in replayed)


def test_polling_and_sse_return_the_same_rows(store, run):
    Orchestrator(store, run).run_to_completion(always_succeed)
    polled = store.events_since(run, 3, limit=10)
    frames = store.sse_frames(run, last_event_id=3, limit=10)
    ids = [int(line.split(": ", 1)[1]) for line in frames.splitlines() if line.startswith("id: ")]
    assert ids == [event["seq"] for event in polled]


def test_sse_frames_carry_the_seq_as_the_event_id(store, run):
    store.append_event(run, "task.started", "t0", {"attempt": 1})
    frames = store.sse_frames(run, last_event_id=0)
    assert frames.startswith("id: 1\n")
    assert "event: run.created" in frames


def test_events_are_never_rewritten(store, run):
    before = store.events_since(run, 0, limit=10_000)
    Orchestrator(store, run).step(always_succeed)
    after = store.events_since(run, 0, limit=10_000)
    assert after[:len(before)] == before


# ------------------------------------------------------------------ 12 recovery ETA --

def test_eta_uses_observed_durations_to_correct_the_remainder(store, run):
    orchestrator = Orchestrator(store, run)

    def slow(task, attempt):
        # estimate says 10 minutes; reality is 20
        return TaskOutcome(status="succeeded", execution_ms=20 * 60_000,
                           tokens={"input": 10}, model="m")

    orchestrator.step(slow)
    eta = recovery_aware_eta(store, run, capacity=1.0)
    assert eta["observed_runtime_multiplier"] == pytest.approx(2.0)
    assert eta["basis"] == "forecast_plus_telemetry"
    assert eta["completed_fraction"] == pytest.approx(0.25)
    # 3 tasks x 10 minutes x 2.0 = 60 minutes = 1 hour at capacity 1
    assert eta["wall_clock_hours"]["p50"] == pytest.approx(1.0)


def test_eta_never_folds_in_human_waits(store, run):
    eta = recovery_aware_eta(store, run)
    joined = " ".join(eta["excludes"]).lower()
    assert "approval" in joined and "acceptance" in joined


def test_eta_without_telemetry_falls_back_to_the_forecast(store, run):
    eta = recovery_aware_eta(store, run)
    assert eta["basis"] == "forecast_only"
    assert eta["observed_runtime_multiplier"] == 1.0


def test_completed_run_has_no_remaining_work(store, run):
    Orchestrator(store, run).run_to_completion(always_succeed)
    eta = recovery_aware_eta(store, run)
    assert eta["remaining_tasks"] == 0
    assert eta["wall_clock_hours"]["p50"] == 0.0
    assert eta["completed_fraction"] == 1.0


# ------------------------------------------------------------ telemetry -> calibrate --

def test_executed_telemetry_exports_in_calibrate_shape(store, run):
    Orchestrator(store, run).run_to_completion(always_succeed)
    rows = store.calibration_rows(run)
    assert len(rows) == 4
    for row in rows:
        assert set(row) >= {"task_type", "complexity", "model", "estimated_minutes",
                            "actual_minutes", "estimated_total_tokens", "actual_total_tokens"}
        assert row["actual_total_tokens"] > 0
        assert row["actual_minutes"] > 0


def test_calibrate_consumes_the_exported_rows(store, run):
    from elmos_execution_intelligence.calibration import calibrate

    Orchestrator(store, run).run_to_completion(always_succeed)
    result = calibrate(store.calibration_rows(run))
    assert result["valid_samples"] == 4
    assert result["global"]["runtime_multiplier"]["p50"] > 0


def test_an_unlockable_store_path_gives_a_diagnosable_error(tmp_path):
    from elmos_execution_intelligence.durable import StoreUnavailable

    # A directory can never be a SQLite database file.
    bad = tmp_path / "not-a-db"
    bad.mkdir()
    with pytest.raises(StoreUnavailable, match="file locking"):
        DurableStore(str(bad))
