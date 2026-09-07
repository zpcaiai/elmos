"""One suite, two adapters.

Every assertion here runs against the in-memory adapters and, when a server is
reachable, against PostgreSQL.  That is the whole design: an invariant that
holds in one process and dissolves under two connections was never an invariant.
The parametrisation is deliberately not `skipif`-hidden — when PostgreSQL is
absent the run reports which half it exercised, so "the tests passed" cannot
quietly mean "the durable half never ran".

Set ``ELMOS_KERNEL_PG_DSN`` to point at a server.  Without it the PostgreSQL
parameters are skipped with a reason naming the variable.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from elmos_autonomy_kernel.adapters.memory import (
    FixedClock,
    InMemoryArtifactStore,
    InMemoryEventStore,
    InMemoryKeyValueStore,
    InMemoryLeaseStore,
)
from elmos_autonomy_kernel.errors import KernelError

DSN = os.environ.get("ELMOS_KERNEL_PG_DSN", "")
MIGRATION_DIR = str(Path(__file__).resolve().parents[1] / "sql" / "migrations")


def _pg_backend(clock):
    psycopg = pytest.importorskip("psycopg", reason="psycopg is an optional dependency")
    from elmos_autonomy_kernel.adapters.postgres import (
        PostgresArtifactStore,
        PostgresEventStore,
        PostgresKeyValueStore,
        PostgresLeaseStore,
        apply_migrations,
    )

    connection = psycopg.connect(DSN, autocommit=False)
    apply_migrations(connection, MIGRATION_DIR)
    with connection.cursor() as cursor:
        cursor.execute(
            "TRUNCATE autonomy_kernel_event, autonomy_kernel_kv, "
            "autonomy_kernel_artifact, autonomy_kernel_lease, "
            "autonomy_kernel_lease_watermark"
        )
    connection.commit()
    return {
        "events": PostgresEventStore(connection, clock),
        "kv": PostgresKeyValueStore(connection),
        "artifacts": PostgresArtifactStore(connection),
        "leases": PostgresLeaseStore(connection, clock),
        "connection": connection,
    }


def _memory_backend(clock):
    return {
        "events": InMemoryEventStore(clock),
        "kv": InMemoryKeyValueStore(),
        "artifacts": InMemoryArtifactStore(),
        "leases": InMemoryLeaseStore(clock),
        "connection": None,
    }


@pytest.fixture(params=["memory", "postgres"])
def backend(request):
    clock = FixedClock()
    if request.param == "postgres":
        if not DSN:
            pytest.skip("set ELMOS_KERNEL_PG_DSN to run the durable half of this suite")
        made = _pg_backend(clock)
        yield {"clock": clock, "kind": "postgres", **made}
        made["connection"].close()
        return
    yield {"clock": clock, "kind": "memory", **_memory_backend(clock)}


# --- event log ---------------------------------------------------------------


def test_the_log_rebuilds_state_and_its_chain_verifies(backend):
    """I2: the event log can rebuild current state, and says so verifiably."""

    events = backend["events"]
    for index in range(5):
        events.append("run-alpha", {"kind": "STEP", "n": index})
    stored = events.read("run-alpha")
    assert [item.sequence for item in stored] == [1, 2, 3, 4, 5]
    assert [item.payload["n"] for item in stored] == [0, 1, 2, 3, 4]
    assert events.verify_chain("run-alpha") is True
    assert events.head("run-alpha").sequence == 5


def test_a_duplicate_delivery_returns_the_original_event(backend):
    """The idempotency invariant: at-least-once delivery must not act twice."""

    events = backend["events"]
    first = events.append("run-idem", {"effect": "publish"}, idempotency_key="k-1")
    second = events.append("run-idem", {"effect": "publish"}, idempotency_key="k-1")
    assert second.sequence == first.sequence
    assert second.event_id == first.event_id
    assert len(events.read("run-idem")) == 1


def test_the_same_key_with_a_different_payload_is_a_conflict(backend):
    """Reusing a key for different content is a caller bug, not a dedupe."""

    events = backend["events"]
    events.append("run-idem2", {"effect": "publish", "target": "a"}, idempotency_key="k-1")
    with pytest.raises(KernelError) as excinfo:
        events.append("run-idem2", {"effect": "publish", "target": "b"}, idempotency_key="k-1")
    assert excinfo.value.code == "IDEMPOTENCY_CONFLICT"


def test_an_optimistic_append_against_a_moved_stream_conflicts(backend):
    """Two writers, one head: the loser is told, not silently overwritten."""

    events = backend["events"]
    events.append("run-cas", {"n": 1})
    with pytest.raises(KernelError) as excinfo:
        events.append("run-cas", {"n": 2}, expected_sequence=0)
    assert excinfo.value.code == "WRITE_CONFLICT"
    assert excinfo.value.retryable is True
    assert events.append("run-cas", {"n": 2}, expected_sequence=1).sequence == 2


def test_a_stale_fencing_token_cannot_append(backend):
    """The paused-worker scenario, at the log rather than at the lease."""

    events = backend["events"]
    events.append("run-fence", {"n": 1}, fencing_token=7)
    with pytest.raises(KernelError) as excinfo:
        events.append("run-fence", {"n": 2}, fencing_token=6)
    assert excinfo.value.code == "FENCING_REJECTED"
    assert excinfo.value.retryable is False
    assert events.append("run-fence", {"n": 2}, fencing_token=7).sequence == 2


def test_streams_are_isolated_from_one_another(backend):
    events = backend["events"]
    events.append("run-x", {"n": 1})
    events.append("run-y", {"n": 1})
    assert [item.sequence for item in events.read("run-x")] == [1]
    assert set(events.streams()) >= {"run-x", "run-y"}


# --- key/value ---------------------------------------------------------------


def test_compare_and_set_rejects_a_stale_version(backend):
    kv = backend["kv"]
    version = kv.put("run/1/state", {"state": "EXECUTING"})
    assert kv.get("run/1/state") == ({"state": "EXECUTING"}, version)
    with pytest.raises(KernelError) as excinfo:
        kv.put("run/1/state", {"state": "SUCCEEDED"}, expected_version=version - 1)
    assert excinfo.value.code == "WRITE_CONFLICT"
    assert kv.put("run/1/state", {"state": "SUCCEEDED"}, expected_version=version) == version + 1


def test_a_scan_prefix_is_not_a_wildcard(backend):
    """A key with SQL wildcard characters must not widen someone's scan."""

    kv = backend["kv"]
    kv.put("tenant_a/one", {"v": 1})
    kv.put("tenantXa/two", {"v": 2})
    found = {key for key, _value, _version in kv.scan("tenant_a/")}
    assert found == {"tenant_a/one"}


# --- artifacts ---------------------------------------------------------------


def test_a_claimed_digest_is_verified_not_trusted(backend):
    artifacts = backend["artifacts"]
    stored = artifacts.put(b"report body", media_type="text/plain")
    assert artifacts.get(stored) == b"report body"
    assert artifacts.stat(stored)["byteCount"] == 11
    with pytest.raises(KernelError) as excinfo:
        artifacts.put(b"other body", media_type="text/plain",
                      expected_digest=stored)
    assert excinfo.value.code == "DIGEST_MISMATCH"


def test_a_missing_artifact_is_missing_not_empty(backend):
    """An absent blob raises; returning b"" would make absence look like content."""

    artifacts = backend["artifacts"]
    with pytest.raises(KernelError) as excinfo:
        artifacts.get("sha256:" + "0" * 64)
    assert excinfo.value.code == "EVIDENCE_MISSING"


# --- leases ------------------------------------------------------------------


def test_a_second_owner_is_refused_while_the_lease_is_live(backend):
    leases = backend["leases"]
    leases.acquire("ws-1", "worker-a", ttl_seconds=30)
    with pytest.raises(KernelError) as excinfo:
        leases.acquire("ws-1", "worker-b", ttl_seconds=30)
    assert excinfo.value.code == "LEASE_HELD_BY_OTHER"


def test_the_paused_worker_can_never_write_again(backend):
    """The scenario fencing exists for, end to end.

    Worker A holds the lease, stalls past its TTL, B takes over, and A wakes up
    believing it still owns the workspace.  A's token must be dead — both at the
    lease and at the log it would have written to.
    """

    leases, events, clock = backend["leases"], backend["events"], backend["clock"]
    a = leases.acquire("ws-fence", "worker-a", ttl_seconds=10)
    clock.advance(seconds=11)
    b = leases.acquire("ws-fence", "worker-b", ttl_seconds=10)
    assert b["fencingToken"] > a["fencingToken"]

    with pytest.raises(KernelError) as excinfo:
        leases.renew("ws-fence", "worker-a", a["fencingToken"], ttl_seconds=10)
    assert excinfo.value.code == "LEASE_LOST"

    events.append("ws-fence-log", {"by": "worker-b"}, fencing_token=b["fencingToken"])
    with pytest.raises(KernelError) as excinfo:
        events.append("ws-fence-log", {"by": "worker-a"}, fencing_token=a["fencingToken"])
    assert excinfo.value.code == "FENCING_REJECTED"


def test_tokens_never_restart_after_a_release(backend):
    """Release-then-reacquire must not hand back a token a stale worker holds."""

    leases = backend["leases"]
    first = leases.acquire("ws-cycle", "worker-a", ttl_seconds=30)
    leases.release("ws-cycle", "worker-a", first["fencingToken"])
    second = leases.acquire("ws-cycle", "worker-b", ttl_seconds=30)
    assert second["fencingToken"] > first["fencingToken"]
    assert leases.current_token("ws-cycle") == second["fencingToken"]


def test_a_token_from_one_resource_is_not_valid_for_another(backend):
    leases = backend["leases"]
    held = leases.acquire("ws-one", "worker-a", ttl_seconds=30)
    leases.acquire("ws-two", "worker-b", ttl_seconds=30)
    with pytest.raises(KernelError) as excinfo:
        leases.renew("ws-two", "worker-a", held["fencingToken"], ttl_seconds=30)
    assert excinfo.value.code == "LEASE_LOST"


def test_an_expired_lease_cannot_be_renewed(backend):
    leases, clock = backend["leases"], backend["clock"]
    held = leases.acquire("ws-expire", "worker-a", ttl_seconds=10)
    clock.advance(seconds=11)
    with pytest.raises(KernelError) as excinfo:
        leases.renew("ws-expire", "worker-a", held["fencingToken"], ttl_seconds=10)
    assert excinfo.value.code == "LEASE_LOST"
