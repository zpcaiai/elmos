from pathlib import Path

import pytest

from etgb.state import JsonRunStateStore, RunState, StateConflict


def _create(store: JsonRunStateStore) -> dict:
    return store.create(
        run_id="run-1",
        owner_id="worker-1",
        tenant_id="tenant-1",
        candidate_digest="sha256:" + "a" * 64,
        plan_digest="sha256:" + "b" * 64,
        lease_seconds=600,
    )


def test_state_machine_checkpoint_pause_resume_and_fencing(tmp_path: Path) -> None:
    store = JsonRunStateStore(tmp_path)
    record = _create(store)
    record = store.transition(
        run_id="run-1", expected_state=RunState.PLANNED, target_state=RunState.PREPARING,
        owner_id="worker-1", fencing_token=1, expected_revision=record["revision"], reason="start"
    )
    record = store.record_checkpoint(
        run_id="run-1", checkpoint_digest="sha256:" + "c" * 64,
        owner_id="worker-1", fencing_token=1, expected_revision=record["revision"], phase="prepare"
    )
    assert record["checkpoint_digest"].endswith("c" * 64)
    record = store.transition(
        run_id="run-1", expected_state=RunState.PREPARING, target_state=RunState.PAUSING,
        owner_id="worker-1", fencing_token=1, expected_revision=record["revision"], reason="pause"
    )
    record = store.transition(
        run_id="run-1", expected_state=RunState.PAUSING, target_state=RunState.PAUSED,
        owner_id="worker-1", fencing_token=1, expected_revision=record["revision"], reason="paused"
    )
    record = store.transition(
        run_id="run-1", expected_state=RunState.PAUSED, target_state=RunState.RESUMING,
        owner_id="worker-1", fencing_token=1, expected_revision=record["revision"], reason="resume"
    )
    record = store.transition(
        run_id="run-1", expected_state=RunState.RESUMING, target_state=RunState.PREPARING,
        owner_id="worker-1", fencing_token=1, expected_revision=record["revision"], reason="resume phase"
    )
    assert record["resume_state"] is None
    with pytest.raises(StateConflict, match="stale fencing token"):
        store.heartbeat(run_id="run-1", owner_id="worker-1", fencing_token=0)


def test_illegal_transition_is_rejected(tmp_path: Path) -> None:
    store = JsonRunStateStore(tmp_path)
    record = _create(store)
    with pytest.raises(StateConflict, match="illegal transition"):
        store.transition(
            run_id="run-1", expected_state=RunState.PLANNED, target_state=RunState.COMPLETED,
            owner_id="worker-1", fencing_token=1, expected_revision=record["revision"], reason="skip"
        )
