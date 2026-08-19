"""JOURNAL-001 and LEASE-001: idempotent replay and epoch fencing."""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import claim_node
from elmos_build_cache.clock import ManualClock
from elmos_build_cache.db import SqliteMetadataStore
from elmos_build_cache.enums import NodeStatus, RunStatus
from elmos_build_cache.errors import ConflictError, InvalidTransition, StaleLease, VersionConflict
from elmos_build_cache.journal import RetryPolicy, RunCoordinator, RunJournal


def test_journal_001_duplicate_delivery_is_idempotent(
    store: SqliteMetadataStore, coordinator: RunCoordinator, journal: RunJournal, run: str
) -> None:
    """JOURNAL-001: replaying an event does not change materialised state."""
    claim_node(store, coordinator, run, "gen")
    events = journal.read_all()
    before = len(store.list_events(run))

    with store.transaction():
        applied = coordinator.deliver(events[-1])
    assert applied is False
    assert len(store.list_events(run)) == before


def test_journal_detects_a_payload_forgery(
    store: SqliteMetadataStore, coordinator: RunCoordinator, journal: RunJournal, run: str
) -> None:
    claim_node(store, coordinator, run, "gen")
    event = journal.read_all()[-1]
    forged = type(event)(**{**event.__dict__, "payload": {"worker": "attacker"}})
    with pytest.raises(ConflictError), store.transaction():
        coordinator.deliver(forged)


def test_journal_sequence_gap_is_detected(journal: RunJournal, tmp_path: Path) -> None:
    journal.append("A", "actor", {})
    journal.append("B", "actor", {})
    lines = journal.path.read_text(encoding="utf-8").splitlines()
    journal.path.write_text(lines[0] + "\n" + lines[1].replace('"sequence":2', '"sequence":5') + "\n")
    with pytest.raises(ConflictError, match="sequence gap"):
        journal.read_all()


def test_journal_tolerates_a_torn_final_record(journal: RunJournal) -> None:
    journal.append("A", "actor", {})
    journal.append("B", "actor", {})
    with journal.path.open("a", encoding="utf-8") as handle:
        handle.write('{"sequence":3,"event_ty')
    assert [event.event_type for event in journal.read_all()] == ["A", "B"]


def test_lease_001_stale_worker_cannot_commit(
    store: SqliteMetadataStore, coordinator: RunCoordinator, clock: ManualClock, run: str
) -> None:
    """LEASE-001: after recovery bumps the epoch, the old worker is fenced."""
    _, lease = claim_node(store, coordinator, run, "gen")
    clock.advance(120)
    with store.transaction():
        recovered = coordinator.recover_expired()

    assert recovered and recovered[0]["lease_epoch"] > recovered[0]["previous_lease_epoch"]
    with pytest.raises(StaleLease), store.transaction():
        coordinator.succeed(lease)


def test_heartbeat_extends_a_lease_and_prevents_reclaim(
    store: SqliteMetadataStore, coordinator: RunCoordinator, clock: ManualClock, run: str
) -> None:
    _, lease = claim_node(store, coordinator, run, "gen")
    for _ in range(4):
        clock.advance(10)
        with store.transaction():
            lease = coordinator.leases.heartbeat(lease)
    with store.transaction():
        assert coordinator.recover_expired() == []
    with store.transaction():
        assert coordinator.succeed(lease).status is NodeStatus.SUCCEEDED


def test_illegal_transitions_are_refused(
    store: SqliteMetadataStore, coordinator: RunCoordinator, run: str
) -> None:
    with store.transaction():
        store.upsert_node(run, "gen", "gen", "1.0.0")
        node = store.get_node(run, "gen", 1)
    with pytest.raises(InvalidTransition), store.transaction():
        store.transition_node(run, "gen", 1, NodeStatus.SUCCEEDED, node.version)


def test_optimistic_version_conflict_is_refused(
    store: SqliteMetadataStore, coordinator: RunCoordinator, run: str
) -> None:
    with store.transaction():
        store.upsert_node(run, "gen", "gen", "1.0.0")
    with pytest.raises(VersionConflict), store.transaction():
        store.transition_node(run, "gen", 1, NodeStatus.READY, 99)


def test_retry_opens_a_new_attempt_and_respects_the_budget(
    store: SqliteMetadataStore, coordinator: RunCoordinator, run: str
) -> None:
    coordinator.retry_policy = RetryPolicy(max_attempts=2)
    _, lease = claim_node(store, coordinator, run, "gen")
    with store.transaction():
        coordinator.fail(lease, "COMPILE_ERROR", retryable=True)
    with store.transaction():
        second = coordinator.retry(run, "gen", 1)
    assert second.attempt == 2
    assert store.get_node(run, "gen", 2).retries == 1

    with store.transaction():
        _, lease2 = coordinator.begin(run, "gen", 2, "worker-2")
        coordinator.fail(lease2, "COMPILE_ERROR", retryable=True)
    # The budget is exhausted, so the node is poisoned rather than looping.
    assert store.get_node(run, "gen", 2).status is NodeStatus.FAILED_FINAL


def test_pause_and_resume_are_safe_at_boundaries(
    store: SqliteMetadataStore, coordinator: RunCoordinator, run: str
) -> None:
    with store.transaction():
        store.upsert_node(run, "gen", "gen", "1.0.0")
        coordinator.start_run(run)
        coordinator.mark_ready(run, "gen", 1)
        coordinator.pause_run(run)
    assert store.get_run(run).status is RunStatus.PAUSED
    assert store.get_node(run, "gen", 1).status is NodeStatus.PAUSED
    with store.transaction():
        coordinator.resume_run(run)
    assert store.get_node(run, "gen", 1).status is NodeStatus.READY


def test_cancellation_preserves_evidence(
    store: SqliteMetadataStore, coordinator: RunCoordinator, run: str
) -> None:
    claim_node(store, coordinator, run, "gen")
    with store.transaction():
        coordinator.cancel_run(run, "operator request")
    assert store.get_run(run).status is RunStatus.CANCELED
    assert store.get_node(run, "gen", 1).status is NodeStatus.CANCELED
    # Journal and events survive so the cancellation is auditable.
    assert any(event["event_type"] == "RUN_CANCELED" for event in store.list_events(run))


def test_reconcile_replays_missing_materialised_events(
    store: SqliteMetadataStore, coordinator: RunCoordinator, journal: RunJournal, run: str
) -> None:
    claim_node(store, coordinator, run, "gen")
    with store.transaction():
        store.execute("DELETE FROM cache_events WHERE run_id=? AND sequence>1", (run,))
    with store.transaction():
        report = coordinator.reconcile()
    assert report["replayed"]
    assert report["payload_mismatches"] == []
    assert len(store.list_events(run)) == report["journal_events"]


def test_state_can_be_rebuilt_from_the_journal_alone(
    store: SqliteMetadataStore, coordinator: RunCoordinator, run: str
) -> None:
    _, lease = claim_node(store, coordinator, run, "gen")
    with store.transaction():
        coordinator.succeed(lease)
    assert coordinator.rebuild_state()["gen#1"] == "SUCCEEDED"
