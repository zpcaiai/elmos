"""CHECK-001..003: resume equivalence, compatibility rejection, at-most-once."""

from __future__ import annotations

import dataclasses

import pytest

from conftest import claim_node, digest
from elmos_build_cache.cas import ContentAddressableStore
from elmos_build_cache.checkpoint import (
    CheckpointPolicy,
    CheckpointService,
    CompatibilityProfile,
    remaining_partitions,
)
from elmos_build_cache.clock import ManualClock
from elmos_build_cache.db import SqliteMetadataStore
from elmos_build_cache.enums import CheckpointStatus, FileClass, StagedFileStatus
from elmos_build_cache.errors import ContractViolation, StaleLease
from elmos_build_cache.journal import RunCoordinator
from elmos_build_cache.staging import Workspace, stage_all

PROFILE = CompatibilityProfile(
    stage_id="target-code-generation",
    stage_version="1.0.0",
    stage_contract_digest=digest("c"),
    rule_pack_digest=digest("5"),
    toolchain_digest=digest("4"),
    source_snapshot=digest("1"),
    action_key=digest("7"),
    pipeline_version="1.0.0",
)


def run_first_half(
    workspace: Workspace,
    store: SqliteMetadataStore,
    coordinator: RunCoordinator,
    checkpoints: CheckpointService,
    run: str,
):
    _, lease = claim_node(store, coordinator, run, "gen")
    with store.transaction():
        stage_all(
            workspace,
            "gen",
            1,
            lease.epoch,
            [("src/A.cs", b"class A {}"), ("src/B.cs", b"class B {}")],
            file_class=FileClass.PUBLISH_CANDIDATE,
        )
        record, manifest = checkpoints.commit(
            lease,
            PROFILE,
            completed_partitions=["A.f1", "A.f2"],
            resume_cursor={"next_symbol": "B.f1"},
        )
    return lease, record, manifest


def test_check_001_resume_recovers_completed_work(
    workspace: Workspace,
    store: SqliteMetadataStore,
    coordinator: RunCoordinator,
    checkpoints: CheckpointService,
    cas: ContentAddressableStore,
    run: str,
) -> None:
    """CHECK-001: resume reproduces the same sealed artifacts, no rework."""
    _, record, manifest = run_first_half(workspace, store, coordinator, checkpoints, run)
    decision = checkpoints.evaluate(run, "gen", PROFILE)

    assert decision.resumable
    assert decision.completed_partitions == ("A.f1", "A.f2")
    assert decision.resume_cursor == {"next_symbol": "B.f1"}
    assert remaining_partitions(["A.f1", "A.f2", "B.f1", "B.f2"], decision) == ("B.f1", "B.f2")
    # Every referenced artifact is present and verifies to the same digest.
    assert manifest.artifacts
    for artifact in manifest.artifacts:
        assert cas.verify(artifact)


@pytest.mark.parametrize(
    "field", ["toolchain_digest", "rule_pack_digest", "source_snapshot", "action_key", "stage_version"]
)
def test_check_002_incompatible_checkpoint_is_rejected_with_a_reason(
    workspace: Workspace,
    store: SqliteMetadataStore,
    coordinator: RunCoordinator,
    checkpoints: CheckpointService,
    run: str,
    field: str,
) -> None:
    """CHECK-002: a relevant change makes the checkpoint unusable, explicitly."""
    run_first_half(workspace, store, coordinator, checkpoints, run)
    replacement = "9.9.9" if field == "stage_version" else digest("9")
    changed = dataclasses.replace(PROFILE, **{field: replacement})
    decision = checkpoints.evaluate(run, "gen", changed)
    assert not decision.resumable
    assert any(field in reason for reason in decision.reasons)


def test_check_003_side_effect_is_not_duplicated_on_retry(
    workspace: Workspace,
    store: SqliteMetadataStore,
    coordinator: RunCoordinator,
    checkpoints: CheckpointService,
    run: str,
) -> None:
    """CHECK-003: a committed effect is visible to the retry as already done."""
    lease, _, _ = run_first_half(workspace, store, coordinator, checkpoints, run)
    with store.transaction():
        already, reference = checkpoints.guard_side_effect(lease, "publish-1", "publish", digest("a"))
        assert already is False and reference is None
        checkpoints.complete_side_effect("publish-1", "external-ref-123")

    with store.transaction():
        already, reference = checkpoints.guard_side_effect(lease, "publish-1", "publish", digest("a"))
    assert already is True
    assert reference == "external-ref-123"


def test_side_effect_key_reuse_with_a_different_payload_is_a_conflict(
    workspace: Workspace,
    store: SqliteMetadataStore,
    coordinator: RunCoordinator,
    checkpoints: CheckpointService,
    run: str,
) -> None:
    from elmos_build_cache.errors import IdempotencyConflict

    lease, _, _ = run_first_half(workspace, store, coordinator, checkpoints, run)
    with store.transaction():
        checkpoints.guard_side_effect(lease, "publish-1", "publish", digest("a"))
    with pytest.raises(IdempotencyConflict), store.transaction():
        checkpoints.guard_side_effect(lease, "publish-1", "publish", digest("b"))


def test_unsealed_files_cannot_enter_a_checkpoint(
    workspace: Workspace,
    store: SqliteMetadataStore,
    coordinator: RunCoordinator,
    checkpoints: CheckpointService,
    run: str,
) -> None:
    _, lease = claim_node(store, coordinator, run, "gen")
    with store.transaction():
        workspace.reserve("gen", 1, "src/Partial.cs", lease.epoch)
    with pytest.raises(ContractViolation, match="unsealed"), store.transaction():
        checkpoints.commit(lease, PROFILE)


def test_checkpoint_flushes_sealed_files_to_cas(
    workspace: Workspace,
    store: SqliteMetadataStore,
    coordinator: RunCoordinator,
    checkpoints: CheckpointService,
    run: str,
) -> None:
    _, lease = claim_node(store, coordinator, run, "gen")
    with store.transaction():
        record = workspace.reserve("gen", 1, "src/A.cs", lease.epoch)
        workspace.write_and_seal(record, b"class A {}", lease.epoch)
        checkpoints.commit(lease, PROFILE)
    statuses = {item.status for item in store.list_staged_files(run)}
    assert statuses == {StagedFileStatus.CAS_PROMOTED}


def test_stale_worker_cannot_commit_a_checkpoint(
    workspace: Workspace,
    store: SqliteMetadataStore,
    coordinator: RunCoordinator,
    checkpoints: CheckpointService,
    clock: ManualClock,
    run: str,
) -> None:
    _, lease = claim_node(store, coordinator, run, "gen")
    clock.advance(120)
    with store.transaction():
        coordinator.recover_expired()
    with pytest.raises(StaleLease), store.transaction():
        checkpoints.commit(lease, PROFILE)


def test_corrupt_artifact_invalidates_the_checkpoint(
    workspace: Workspace,
    store: SqliteMetadataStore,
    coordinator: RunCoordinator,
    checkpoints: CheckpointService,
    cas: ContentAddressableStore,
    run: str,
) -> None:
    _, record, manifest = run_first_half(workspace, store, coordinator, checkpoints, run)
    cas.path_for(manifest.artifacts[0]).write_bytes(b"corrupt")

    decision = checkpoints.evaluate(run, "gen", PROFILE)
    assert not decision.resumable
    assert any("corrupt" in reason for reason in decision.reasons)
    assert store.list_checkpoints(run, "gen")[0].status is CheckpointStatus.QUARANTINED


def test_newest_checkpoint_supersedes_the_previous_one(
    workspace: Workspace,
    store: SqliteMetadataStore,
    coordinator: RunCoordinator,
    checkpoints: CheckpointService,
    run: str,
) -> None:
    lease, first, _ = run_first_half(workspace, store, coordinator, checkpoints, run)
    with store.transaction():
        second, _ = checkpoints.commit(lease, PROFILE, completed_partitions=["A.f1", "A.f2", "B.f1"])
    records = {record.checkpoint_id: record.status for record in store.list_checkpoints(run, "gen")}
    assert records[first.checkpoint_id] is CheckpointStatus.SUPERSEDED
    assert records[second.checkpoint_id] is CheckpointStatus.ACTIVE
    assert checkpoints.evaluate(run, "gen", PROFILE).completed_partitions == ("A.f1", "A.f2", "B.f1")


def test_chain_length_is_bounded(
    workspace: Workspace,
    store: SqliteMetadataStore,
    coordinator: RunCoordinator,
    checkpoints: CheckpointService,
    run: str,
) -> None:
    from elmos_build_cache.errors import ConflictError

    checkpoints.policy = CheckpointPolicy(max_chain_length=2)
    lease, _, _ = run_first_half(workspace, store, coordinator, checkpoints, run)
    with store.transaction():
        checkpoints.commit(lease, PROFILE)
    with pytest.raises(ConflictError, match="maximum length"), store.transaction():
        checkpoints.commit(lease, PROFILE)


def test_policy_skips_checkpointing_cheap_work(clock: ManualClock) -> None:
    policy = CheckpointPolicy(stage_boundary=False, min_recompute_cost_ms=5000, interval_seconds=30)
    should, reason = policy.should_checkpoint(clock.now(), False, estimated_recompute_ms=10)
    assert not should and "cheaper" in reason
    should, reason = policy.should_checkpoint(clock.now(), False, estimated_recompute_ms=60_000)
    assert should
