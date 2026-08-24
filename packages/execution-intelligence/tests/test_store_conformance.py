"""One contract, two backends.

Every assertion here is written against the store *interface*, not against
SQLite. The PostgreSQL parameter runs the same assertions against the production
schema in ``sql/001_execution_intelligence.sql`` -- including its enums and its
``append_run_event`` function -- so "the contract is portable" is a test result
rather than a claim.

The PostgreSQL case is skipped unless ELMOS_EI_PG_DSN names a reachable server
and a DB-API driver is importable. A skip is reported as a skip; it never counts
as a pass.
"""
import json
import os

import pytest
from conftest import PROJECT_PATH

from elmos_execution_intelligence.durable import (
    Conflict,
    DurableStore,
    LogicalClock,
    Orchestrator,
    TaskOutcome,
    replay_is_gapless,
)

PROJECT = json.loads(PROJECT_PATH.read_text(encoding="utf-8"))
PG_DSN = os.environ.get("ELMOS_EI_PG_DSN")


def _dag(n=3):
    return {
        "schema_version": "1.0.0",
        "dag_id": "conformance",
        "tasks": [
            {
                "id": f"t{i}",
                "name": f"task {i}",
                "depends_on": [f"t{i - 1}"] if i else [],
                "category": "verification",
                "complexity": "medium",
                "system": {
                    "optimistic_minutes": 5, "most_likely_minutes": 10, "pessimistic_minutes": 20,
                    "worker_units": 1,
                    "token_profile": {"input": 1000, "cached_input": 2000, "cache_write": 100,
                                      "output": 300, "reasoning_output": 100},
                },
                "human": {"hours_by_role": {"qa": 1}},
            }
            for i in range(n)
        ],
    }


def _sqlite_store():
    return DurableStore(":memory:", clock=LogicalClock(start=1000.0, step=1.0))


def _postgres_store():
    if not PG_DSN:
        pytest.skip("ELMOS_EI_PG_DSN is not set; PostgreSQL conformance not exercised")
    try:
        import pg8000.dbapi as driver
    except ImportError:  # pragma: no cover - environment dependent
        pytest.skip("no DB-API driver available for PostgreSQL")

    from urllib.parse import urlparse

    from elmos_execution_intelligence.postgres import PostgresStore

    parsed = urlparse(PG_DSN)

    def connect():
        return driver.connect(
            user=parsed.username or "postgres",
            password=parsed.password,
            host=parsed.hostname or "localhost",
            port=parsed.port or 5432,
            database=(parsed.path or "/postgres").lstrip("/"),
            unix_sock=os.environ.get("ELMOS_EI_PG_UNIX_SOCK"),
        )

    # Each test gets its own tenant so runs never collide across cases.
    import uuid as _uuid

    return PostgresStore(connect, clock=LogicalClock(start=1000.0, step=1.0),
                         tenant_id=f"conformance-{_uuid.uuid4().hex[:8]}")


BACKENDS = {"sqlite": _sqlite_store, "postgres": _postgres_store}


@pytest.fixture(params=sorted(BACKENDS))
def store(request):
    made = BACKENDS[request.param]()
    yield made
    made.close()


def always_succeed(task, attempt):
    return TaskOutcome(status="succeeded",
                       tokens={"input": 1000, "cached_input": 2000, "output": 300},
                       execution_ms=600_000, git_commit=f"commit-{task['task_id']}",
                       artifacts=[(f"{task['task_id']}.txt", b"payload")], model="test-model")


def test_a_run_executes_to_completion(store):
    run_id = store.create_run(PROJECT, _dag())
    result = Orchestrator(store, run_id, capacity=2.0).run_to_completion(always_succeed)
    assert result["state"] == "succeeded"
    assert all(task["state"] == "succeeded" for task in store.tasks(run_id))


def test_event_sequence_is_monotonic_and_gapless(store):
    run_id = store.create_run(PROJECT, _dag())
    Orchestrator(store, run_id, capacity=2.0).run_to_completion(always_succeed)
    events = store.events_since(run_id, 0, limit=10_000)
    assert len(events) > 3
    assert replay_is_gapless(events, 0)
    assert store.get_run(run_id)["last_event_seq"] == events[-1]["seq"]


def test_reconnect_replays_only_what_was_missed(store):
    run_id = store.create_run(PROJECT, _dag())
    orchestrator = Orchestrator(store, run_id, capacity=2.0)
    orchestrator.step(always_succeed)
    seen = store.events_since(run_id, 0, limit=10_000)
    last_seen = seen[-1]["seq"]
    orchestrator.run_to_completion(always_succeed)

    replayed = store.events_since(run_id, last_seen, limit=10_000)
    assert replay_is_gapless(replayed, last_seen)
    assert all(event["seq"] > last_seen for event in replayed)
    assert len(seen) + len(replayed) == len(store.events_since(run_id, 0, limit=10_000))


def test_idempotency_replay_and_conflict(store):
    status, _ = store.begin_idempotent("payment", "k", {"amount": 1})
    assert status == "claimed"
    store.complete_idempotent("payment", "k", {"receipt": "r"})

    status, response = store.begin_idempotent("payment", "k", {"amount": 1})
    assert status == "replayed"
    assert response == {"receipt": "r"}

    with pytest.raises(Conflict):
        store.begin_idempotent("payment", "k", {"amount": 2})


def test_a_released_key_can_be_reclaimed(store):
    store.begin_idempotent("payment", "k2", {"amount": 1})
    store.fail_idempotent("payment", "k2")
    status, _ = store.begin_idempotent("payment", "k2", {"amount": 1})
    assert status == "claimed"


def test_artifacts_are_content_addressed(store):
    run_id = store.create_run(PROJECT, _dag(1))
    first = store.publish_artifact(run_id, "report.md", b"same")
    again = store.publish_artifact(run_id, "report.md", b"same")
    different = store.publish_artifact(run_id, "report.md", b"other")

    assert again["deduplicated"] is True
    assert again["version"] == first["version"]
    assert different["version"] == first["version"] + 1
    assert store.has_artifact(run_id, "report.md", first["sha256"]) is True
    assert len(store.artifacts(run_id)) == 2


def test_checkpoints_and_commit_lookup(store):
    run_id = store.create_run(PROJECT, _dag(1))
    store.record_checkpoint(run_id, "t0", "git", git_commit="abc123")
    assert store.has_commit(run_id, "abc123") is True
    assert store.has_commit(run_id, "nope") is False
    assert store.checkpoints(run_id, "t0")[0]["git_commit"] == "abc123"


def test_a_lost_worker_is_swept_as_lost_not_failed(store):
    run_id = store.create_run(PROJECT, _dag(1))
    store.start_attempt(run_id, "t0", "worker-x")
    store.clock.advance(120)
    lost = store.sweep_lost_attempts(run_id, 5.0)
    assert [item["task_id"] for item in lost] == ["t0"]
    assert store.tasks(run_id)[0]["state"] == "ready"


def test_outbox_rows_accompany_state_changes(store):
    run_id = store.create_run(PROJECT, _dag(2))
    Orchestrator(store, run_id, capacity=2.0).run_to_completion(always_succeed)
    pending = store.unpublished_outbox()
    assert {row["payload"]["task_id"] for row in pending} == {"t0", "t1"}
    store.mark_published(pending[0]["outbox_id"])
    assert len(store.unpublished_outbox()) == len(pending) - 1


def test_telemetry_exports_in_calibrate_shape(store):
    run_id = store.create_run(PROJECT, _dag(2))
    Orchestrator(store, run_id, capacity=2.0).run_to_completion(always_succeed)
    rows = store.calibration_rows(run_id)
    assert len(rows) == 2
    for row in rows:
        assert row["actual_total_tokens"] > 0
        assert row["estimated_total_tokens"] > 0


def test_sse_frames_use_the_sequence_as_the_event_id(store):
    run_id = store.create_run(PROJECT, _dag(1))
    frames = store.sse_frames(run_id, last_event_id=0)
    assert frames.startswith("id: 1\n")
    assert "event: run.created" in frames
