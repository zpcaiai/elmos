"""Workspace Lease Fencing tests.

Named after the acceptance gates and negative tests in
``skills/workspace-lease-fencing/acceptance.yaml`` and the four invariants in its SKILL.md.  The
centrepiece is :func:`test_paused_worker_cannot_write_after_takeover`, which reproduces the
failure the whole capability exists to prevent.
"""

from __future__ import annotations

import pytest

from elmos_autonomy_kernel.adapters.memory import (
    FixedClock,
    InMemoryEventStore,
    InMemoryLeaseStore,
)
from elmos_autonomy_kernel.contracts import SkillResult, Status, digest
from elmos_autonomy_kernel.errors import KernelError
from elmos_autonomy_kernel.leasing import FencedWriter, Lease, LeaseManager, handle
from elmos_autonomy_kernel.registry import dispatch

ISSUED_AT = "2026-01-01T00:00:00.000000Z"


@pytest.fixture()
def manager(leases: InMemoryLeaseStore, clock: FixedClock,
            events: InMemoryEventStore) -> LeaseManager:
    return LeaseManager(leases, clock, events=events)


def _checkpoint(resource_id: str = "ws-1", state: dict | None = None) -> dict:
    body = {"checkpointId": "cp-1", "resourceId": resource_id, "state": state or {"step": "s1"}}
    return {**body, "digest": digest(body)}


def _handle_request(store: InMemoryLeaseStore, clock: FixedClock,
                    events: InMemoryEventStore, **overrides) -> dict:
    body = {
        "workspace": {"workspaceId": "ws-1"},
        "worker_identity": {"ownerId": "worker-a"},
        "lease_policy": {"ttlSeconds": 60, "issuedAt": ISSUED_AT, "action": "acquire"},
        "ports": {"lease_store": store, "clock": clock, "event_store": events},
    }
    body.update(overrides)
    return body


# --- the failure this capability exists to prevent ---------------------------


def test_paused_worker_cannot_write_after_takeover(manager: LeaseManager,
                                                   clock: FixedClock) -> None:
    """Worker A acquires, stalls past its TTL, B takes over, A wakes up and writes -> rejected.

    A has no way to know it lost the lease.  Only the token check at the write can stop it.
    """

    a = manager.acquire("ws-1", "worker-a", ttl_seconds=30)
    assert a.fencing_token == 1

    clock.advance(60)  # A is paused (GC, host freeze, partition) past its TTL

    b = manager.acquire("ws-1", "worker-b", ttl_seconds=30)
    assert b.fencing_token == 2

    landed: list[str] = []
    with pytest.raises(KernelError) as excinfo:
        FencedWriter(manager, a).write(lambda: landed.append("A wrote"))
    assert excinfo.value.code == "LEASE_LOST"
    assert landed == []  # the write never ran
    assert manager.current_token("ws-1") == 2


def test_stale_owner_is_rejected_even_before_its_lease_looks_expired(
        manager: LeaseManager) -> None:
    """The token, not the local expiry belief, is what rejects a superseded owner."""

    a = manager.acquire("ws-1", "worker-a", ttl_seconds=600)
    manager.takeover("ws-1", new_owner="worker-b", reason="worker-a stopped heartbeating",
                     ttl_seconds=600, previous_owner="worker-a")
    assert a.is_expired(manager._clock.now()) is False  # A still believes it holds the lease
    with pytest.raises(KernelError) as excinfo:
        manager.validate(a)
    assert excinfo.value.code == "LEASE_LOST"
    assert excinfo.value.details["currentToken"] == 2


# --- positive gates ----------------------------------------------------------


def test_gate_stale_worker_denied(manager: LeaseManager, clock: FixedClock) -> None:
    """`stale-worker-denied`."""

    a = manager.acquire("ws-1", "worker-a", ttl_seconds=30)
    clock.advance(60)
    manager.acquire("ws-1", "worker-b", ttl_seconds=30)
    with pytest.raises(KernelError):
        manager.validate(a)


def test_gate_duplicate_delivery_safe(manager: LeaseManager) -> None:
    """`duplicate-delivery-safe`: a redelivered side effect returns the original record."""

    lease = manager.acquire("ws-1", "worker-a", ttl_seconds=600)
    first = manager.record_side_effect(lease, effect_id="eff.1", idempotency_key="key-1",
                                       payload={"amount": 100})
    second = manager.record_side_effect(lease, effect_id="eff.1", idempotency_key="key-1",
                                        payload={"amount": 100})
    assert first["eventId"] == second["eventId"]
    assert first["sequence"] == second["sequence"]


def test_gate_takeover_recoverable(manager: LeaseManager) -> None:
    """`takeover-recoverable`: takeover issues a new token and leaves a stated reason."""

    manager.acquire("ws-1", "worker-a", ttl_seconds=600)
    lease, record = manager.takeover("ws-1", new_owner="worker-b",
                                     reason="worker-a stopped heartbeating", ttl_seconds=600,
                                     previous_owner="worker-a")
    assert lease.fencing_token == 2
    assert record.previous_token == 1
    assert record.reason == "worker-a stopped heartbeating"
    assert record.event_id  # written to the durable log
    assert manager.takeovers == (record,)


def test_gate_write_set_owned(manager: LeaseManager) -> None:
    """`write-set-owned`: the guarded write runs only under a live, current lease."""

    lease = manager.acquire("ws-1", "worker-a", ttl_seconds=600)
    with manager.guard(lease) as guarded:
        assert guarded is lease
    assert FencedWriter(manager, lease).write(lambda: "wrote") == "wrote"


# --- negative tests ----------------------------------------------------------


def test_negative_malformed_input_is_rejected(leases: InMemoryLeaseStore, clock: FixedClock,
                                              events: InMemoryEventStore) -> None:
    with pytest.raises(KernelError) as unknown:
        handle(_handle_request(leases, clock, events, surprise=True))
    assert unknown.value.code == "UNKNOWN_FIELD"

    body = _handle_request(leases, clock, events)
    del body["lease_policy"]
    with pytest.raises(KernelError) as missing:
        handle(body)
    assert missing.value.code == "MISSING_REQUIRED_INPUT"

    with pytest.raises(KernelError) as action:
        handle(_handle_request(leases, clock, events,
                               lease_policy={"ttlSeconds": 60, "issuedAt": ISSUED_AT,
                                             "action": "seize"}))
    assert action.value.code == "MALFORMED_INPUT"


def test_negative_ports_are_required(clock: FixedClock) -> None:
    """A lease kernel with no store would answer confidently and wrongly, so it refuses."""

    with pytest.raises(KernelError) as excinfo:
        handle({
            "workspace": {"workspaceId": "ws-1"},
            "worker_identity": {"ownerId": "worker-a"},
            "lease_policy": {"ttlSeconds": 60, "issuedAt": ISSUED_AT},
        })
    assert excinfo.value.code == "MISSING_REQUIRED_INPUT"


def test_negative_stale_snapshot_is_rejected(manager: LeaseManager) -> None:
    """A checkpoint whose content no longer hashes to its declared digest is refused."""

    checkpoint = _checkpoint()
    tampered = dict(checkpoint, state={"step": "s1", "injected": "rm -rf /"})
    with pytest.raises(KernelError) as excinfo:
        manager.plan_recovery(tampered, ())
    assert excinfo.value.code == "CHECKPOINT_CORRUPT"


def test_negative_unauthorized_tool_is_denied(manager: LeaseManager) -> None:
    """This capability's equivalent: an unauthorised *writer* is refused the write."""

    manager.acquire("ws-1", "worker-a", ttl_seconds=600)
    foreign = Lease(resource_id="ws-1", owner_id="worker-b", fencing_token=99,
                    acquired_at=manager._clock.now(),
                    expires_at=manager._clock.now().replace(year=2027), ttl_seconds=600)
    with pytest.raises(KernelError) as excinfo:
        FencedWriter(manager, foreign).write(lambda: "should not run")
    assert excinfo.value.code == "LEASE_LOST"


def test_negative_interrupted_is_not_success(manager: LeaseManager, clock: FixedClock) -> None:
    """A lease lost *during* a write is INTERRUPTED: the effect may or may not have landed."""

    lease = manager.acquire("ws-1", "worker-a", ttl_seconds=30)

    def slow_write() -> str:
        clock.advance(60)  # the write outlives the lease
        manager.acquire("ws-1", "worker-b", ttl_seconds=30)
        return "wrote"

    with pytest.raises(KernelError) as excinfo:
        FencedWriter(manager, lease).write(slow_write)
    assert excinfo.value.code == "LEASE_LOST"
    assert excinfo.value.interrupted is True
    assert excinfo.value.retryable is False
    result = SkillResult.failure("workspace-lease-fencing", excinfo.value,
                                 status=Status.INTERRUPTED)
    assert result.succeeded is False


def test_negative_partial_is_not_success() -> None:
    error = KernelError(code="PARTIAL", message="two of three effects replayed", partial=True)
    result = SkillResult.failure("workspace-lease-fencing", error, status=Status.PARTIAL)
    assert result.status is Status.PARTIAL
    assert result.succeeded is False


def test_negative_duplicate_side_effect_is_prevented(manager: LeaseManager) -> None:
    """Reusing an idempotency key for a *different* payload is a conflict, not a silent win."""

    lease = manager.acquire("ws-1", "worker-a", ttl_seconds=600)
    manager.record_side_effect(lease, effect_id="eff.1", idempotency_key="key-1",
                               payload={"amount": 100})
    with pytest.raises(KernelError) as excinfo:
        manager.record_side_effect(lease, effect_id="eff.1", idempotency_key="key-1",
                                   payload={"amount": 200})
    assert excinfo.value.code == "IDEMPOTENCY_CONFLICT"


def test_negative_stale_fencing_token_is_rejected(manager: LeaseManager,
                                                  events: InMemoryEventStore) -> None:
    """The event log rejects an append from a superseded token, independently of the manager."""

    manager.acquire("ws-1", "worker-a", ttl_seconds=600)
    manager.takeover("ws-1", new_owner="worker-b", reason="a is wedged", ttl_seconds=600,
                     previous_owner="worker-a")
    with pytest.raises(KernelError) as excinfo:
        events.append("ws-1", {"type": "late-write"}, fencing_token=1)
    assert excinfo.value.code == "FENCING_REJECTED"


def test_negative_prompt_injection_cannot_expand_authority(manager: LeaseManager) -> None:
    """A takeover needs a reason and, for a live lease, the previous owner's identity."""

    manager.acquire("ws-1", "worker-a", ttl_seconds=600)
    with pytest.raises(KernelError) as no_reason:
        manager.takeover("ws-1", new_owner="worker-b", reason="   ", ttl_seconds=600,
                         previous_owner="worker-a")
    assert no_reason.value.code == "MALFORMED_INPUT"

    with pytest.raises(KernelError) as no_owner:
        manager.takeover("ws-1", new_owner="worker-b", reason="just take it", ttl_seconds=600)
    assert no_owner.value.code == "TAKEOVER_DENIED"
    assert manager.current_token("ws-1") == 1  # nothing moved


# --- non-negotiable invariants ----------------------------------------------


def test_invariant_i1_an_old_token_never_becomes_valid_again(manager: LeaseManager,
                                                             clock: FixedClock) -> None:
    """I1: tokens are strictly monotonic per resource; a released lease does not rewind."""

    tokens = []
    for index in range(4):
        lease = manager.acquire("ws-1", f"worker-{index}", ttl_seconds=10)
        tokens.append(lease.fencing_token)
        manager.release(lease)
        clock.advance(1)
    assert tokens == [1, 2, 3, 4]
    assert tokens == sorted(set(tokens))
    with pytest.raises(KernelError) as excinfo:
        manager.assert_current("ws-1", 1)
    assert excinfo.value.code == "LEASE_LOST"


def test_invariant_i2_a_token_from_one_resource_is_not_valid_for_another(
        manager: LeaseManager, clock: FixedClock) -> None:
    """I2: tokens are per resource, so a bare integer proves nothing.

    Both workspaces hand out token 1.  Only the ``(resource, token)`` pair identifies a lease.
    """

    for _ in range(3):
        lease = manager.acquire("ws-x", "worker-a", ttl_seconds=10)
        manager.release(lease)
    on_x = manager.acquire("ws-x", "worker-a", ttl_seconds=600)
    on_y = manager.acquire("ws-y", "worker-b", ttl_seconds=600)
    assert on_x.fencing_token == 4
    assert on_y.fencing_token == 1  # the same numeric space, a different resource

    manager.assert_current("ws-x", on_x.fencing_token)
    manager.assert_current("ws-y", on_y.fencing_token)
    with pytest.raises(KernelError):
        manager.assert_current("ws-y", on_x.fencing_token)
    with pytest.raises(KernelError):
        manager.assert_current("ws-x", on_y.fencing_token)

    borrowed = Lease(resource_id="ws-y", owner_id="worker-a",
                     fencing_token=on_x.fencing_token, acquired_at=clock.now(),
                     expires_at=on_y.expires_at, ttl_seconds=600)
    with pytest.raises(KernelError) as excinfo:
        FencedWriter(manager, borrowed).write(lambda: "cross-resource write")
    assert excinfo.value.code == "LEASE_LOST"


def test_invariant_i3_expiry_is_decided_by_the_injected_clock(manager: LeaseManager,
                                                              clock: FixedClock) -> None:
    """I3: expiry is an orchestrator decision read from the clock, never from wall time."""

    lease = manager.acquire("ws-1", "worker-a", ttl_seconds=30)
    manager.validate(lease)
    clock.advance(30)
    with pytest.raises(KernelError) as excinfo:
        manager.validate(lease)
    assert excinfo.value.code == "LEASE_LOST"


def test_invariant_i4_unknown_side_effects_are_never_blindly_replayed(
        manager: LeaseManager) -> None:
    """I4: an effect of unknown status goes to reconciliation, never to replay."""

    plan = manager.plan_recovery(_checkpoint(), [
        {"effectId": "eff.applied", "status": "applied"},
        {"effectId": "eff.pending", "status": "not-applied"},
        {"effectId": "eff.unknown", "status": "unknown"},
    ])
    assert plan.replay == ("eff.pending",)
    assert plan.skip == ("eff.applied",)
    assert plan.reconcile == ("eff.unknown",)
    assert plan.to_payload()["blindReplayAllowed"] is False
    with pytest.raises(KernelError) as excinfo:
        plan.assert_replayable()
    assert excinfo.value.code == "SIDE_EFFECT_AMBIGUOUS"


def test_a_fully_known_ledger_is_replayable(manager: LeaseManager) -> None:
    plan = manager.plan_recovery(_checkpoint(), [
        {"effectId": "eff.pending", "status": "not-applied"},
    ])
    plan.assert_replayable()
    assert plan.to_payload()["blindReplayAllowed"] is True


def test_an_unknown_ledger_status_is_refused(manager: LeaseManager) -> None:
    """A status outside the vocabulary is malformed input, not a fourth quiet state."""

    with pytest.raises(KernelError) as excinfo:
        manager.plan_recovery(_checkpoint(), [{"effectId": "eff.1", "status": "probably-fine"}])
    assert excinfo.value.code == "MALFORMED_INPUT"


# --- heartbeat and lifecycle -------------------------------------------------


def test_renew_keeps_the_token_and_extends_the_window(manager: LeaseManager,
                                                      clock: FixedClock) -> None:
    lease = manager.acquire("ws-1", "worker-a", ttl_seconds=30)
    clock.advance(20)
    renewed = manager.renew(lease, ttl_seconds=30)
    assert renewed.fencing_token == lease.fencing_token
    assert renewed.expires_at > lease.expires_at


def test_renewing_a_superseded_lease_fails(manager: LeaseManager, clock: FixedClock) -> None:
    lease = manager.acquire("ws-1", "worker-a", ttl_seconds=30)
    clock.advance(60)
    manager.acquire("ws-1", "worker-b", ttl_seconds=30)
    with pytest.raises(KernelError) as excinfo:
        manager.renew(lease, ttl_seconds=30)
    assert excinfo.value.code == "LEASE_LOST"


def test_recording_a_side_effect_requires_a_live_lease(manager: LeaseManager,
                                                       clock: FixedClock) -> None:
    lease = manager.acquire("ws-1", "worker-a", ttl_seconds=30)
    clock.advance(60)
    manager.acquire("ws-1", "worker-b", ttl_seconds=30)
    with pytest.raises(KernelError) as excinfo:
        manager.record_side_effect(lease, effect_id="eff.1", idempotency_key="key-1",
                                   payload={})
    assert excinfo.value.code == "LEASE_LOST"


# --- digests and tamper detection -------------------------------------------


def test_mutating_a_lease_payload_breaks_its_digest(manager: LeaseManager) -> None:
    """The wrong answer is rejected, not just the right one accepted."""

    payload = manager.acquire("ws-1", "worker-a", ttl_seconds=600).to_payload()
    original = payload.pop("digest")
    assert digest(payload) == original
    payload["fencingToken"] = 99
    assert digest(payload) != original


# --- registry ---------------------------------------------------------------


def test_registry_round_trip(leases: InMemoryLeaseStore, clock: FixedClock,
                             events: InMemoryEventStore) -> None:
    result = dispatch("workspace-lease-fencing", _handle_request(leases, clock, events))
    assert result.status is Status.SUCCEEDED
    assert result.outputs["fencing_token"] == 1
    assert result.outputs["lease"]["ownerId"] == "worker-a"
    assert result.outputs["takeover_event"] is None
    assert result.outputs["recovery_plan"] is None


def test_registry_round_trip_with_takeover_and_recovery(
        leases: InMemoryLeaseStore, clock: FixedClock, events: InMemoryEventStore) -> None:
    leases.acquire("ws-1", "worker-a", ttl_seconds=600)
    result = dispatch("workspace-lease-fencing", _handle_request(
        leases, clock, events,
        worker_identity={"ownerId": "worker-b"},
        lease_policy={"ttlSeconds": 60, "issuedAt": ISSUED_AT, "action": "takeover",
                      "reason": "worker-a stopped heartbeating", "previousOwner": "worker-a"},
        checkpoint=_checkpoint(),
        side_effect_ledger=[{"effectId": "eff.1", "status": "unknown"}],
    ))
    assert result.status is Status.SUCCEEDED
    assert result.outputs["fencing_token"] == 2
    assert result.outputs["takeover_event"]["reason"] == "worker-a stopped heartbeating"
    assert result.outputs["recovery_plan"]["reconcile"] == ["eff.1"]
    assert result.outputs["recovery_plan"]["blindReplayAllowed"] is False


def test_registry_normalises_a_failure_into_the_envelope(leases: InMemoryLeaseStore,
                                                         clock: FixedClock,
                                                         events: InMemoryEventStore) -> None:
    result = dispatch("workspace-lease-fencing",
                      _handle_request(leases, clock, events, surprise=True))
    assert result.status is Status.FAILED
    assert result.error is not None
    assert result.error["code"] == "UNKNOWN_FIELD"
