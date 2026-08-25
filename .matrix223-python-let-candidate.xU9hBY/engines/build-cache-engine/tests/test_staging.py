"""STAGE-001..007: the generated-file lifecycle and its kill points."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from conftest import claim_node
from elmos_build_cache.clock import ManualClock
from elmos_build_cache.db import SqliteMetadataStore
from elmos_build_cache.enums import FileClass, StagedFileStatus
from elmos_build_cache.errors import ConflictError, QuotaExceeded, StaleLease, UnsafePath
from elmos_build_cache.journal import RunCoordinator
from elmos_build_cache.staging import Workspace, stage_all


def test_workspace_layout_matches_the_contract(workspace: Workspace) -> None:
    for relative in (
        "control",
        "source",
        "overlay",
        "scratch",
        "generated/pending",
        "generated/sealed",
        "artifacts",
        "checkpoints",
        "quarantine",
        "publish",
        "logs",
    ):
        assert (workspace.root / relative).is_dir(), relative
    assert (workspace.root / "control" / "run.json").is_file()


def test_stage_001_kill_after_reservation_reclaims_without_publishing(
    workspace: Workspace, store: SqliteMetadataStore, coordinator: RunCoordinator, run: str
) -> None:
    """STAGE-001: a reservation with no bytes is released, never published."""
    _, lease = claim_node(store, coordinator, run, "gen")
    with store.transaction():
        record = workspace.reserve("gen", 1, "src/App.cs", lease.epoch)
    assert record.status is StagedFileStatus.RESERVED

    with store.transaction():
        summary = workspace.recover()
    assert summary["released"] == ["src/App.cs"]
    assert store.get_staged_file(record.staged_file_id).status is StagedFileStatus.ABORTED
    assert not (workspace.sealed_root / "src/App.cs").exists()


def test_stage_002_kill_during_write_never_seals(
    workspace: Workspace, store: SqliteMetadataStore, coordinator: RunCoordinator, run: str
) -> None:
    """STAGE-002: a partial temp file is discarded; nothing reaches sealed."""
    _, lease = claim_node(store, coordinator, run, "gen")

    class Exploding(io.RawIOBase):
        def read(self, size: int = -1) -> bytes:  # type: ignore[override]
            raise OSError("simulated kill during write")

    with store.transaction():
        record = workspace.reserve("gen", 1, "src/App.cs", lease.epoch)
    with pytest.raises(OSError, match="simulated kill"), store.transaction():
        workspace.write_and_seal(record, Exploding(), lease.epoch)

    assert store.get_staged_file(record.staged_file_id).status is StagedFileStatus.ABORTED
    assert not (workspace.sealed_root / "src/App.cs").exists()
    assert list(workspace.pending_root.rglob("*.elmos-tmp-*")) == []


def test_stage_003_kill_after_seal_before_metadata_converges(
    workspace: Workspace, store: SqliteMetadataStore, coordinator: RunCoordinator, run: str
) -> None:
    """STAGE-003: recovery does not create a duplicate logical file."""
    _, lease = claim_node(store, coordinator, run, "gen")
    with store.transaction():
        record = workspace.reserve("gen", 1, "src/App.cs", lease.epoch)
        record = workspace.write_and_seal(record, b"class App {}", lease.epoch)

    with store.transaction():
        summary = workspace.recover()
    assert summary["promoted"] == ["src/App.cs"]
    paths = [item.logical_path for item in store.list_staged_files(run)]
    assert paths.count("src/App.cs") == 1


def test_stage_004_promotion_is_idempotent(
    workspace: Workspace, store: SqliteMetadataStore, coordinator: RunCoordinator, run: str
) -> None:
    """STAGE-004: resume after a kill between seal and CAS put converges."""
    _, lease = claim_node(store, coordinator, run, "gen")
    with store.transaction():
        record = workspace.reserve("gen", 1, "src/App.cs", lease.epoch)
        record = workspace.write_and_seal(record, b"class App {}", lease.epoch)
        first = workspace.promote(record)
        second = workspace.promote(first)
    assert first.artifact_digest == second.artifact_digest
    assert second.status is StagedFileStatus.CAS_PROMOTED
    assert workspace.cas.get_bytes(second.artifact_digest or "") == b"class App {}"


def test_stage_005_undeclared_output_is_quarantined(
    workspace: Workspace, store: SqliteMetadataStore, coordinator: RunCoordinator, run: str
) -> None:
    """STAGE-005: a file nobody reserved cannot reach the tree."""
    _, lease = claim_node(store, coordinator, run, "gen")
    with store.transaction():
        stage_all(workspace, "gen", 1, lease.epoch, [("src/App.cs", b"class App {}")])
    (workspace.sealed_root / "sneaky.txt").write_text("undeclared", encoding="utf-8")

    assert workspace.scan_undeclared() == ["sneaky.txt"]
    assert workspace.handle_undeclared("gen", 1) == ["sneaky.txt"]
    assert workspace.scan_undeclared() == []
    assert (workspace.quarantine_root / "undeclared" / "sneaky.txt").is_file()
    assert "sneaky.txt" not in [record.logical_path for record in workspace.publishable()]


@pytest.mark.parametrize(
    "logical_path",
    [
        "../escape.cs",
        "/absolute.cs",
        "src/../../outside.cs",
        "con.txt",
        "COM1.cs",
        "src/trailing.",
        "src/trailing ",
        "src/\u202egnp.cs",
        "C:/windows.cs",
        "//server/share.cs",
    ],
)
def test_stage_006_unsafe_paths_are_rejected_before_any_write(
    workspace: Workspace, store: SqliteMetadataStore, coordinator: RunCoordinator, run: str, logical_path: str
) -> None:
    """STAGE-006: traversal, reserved names and unicode spoofing never land."""
    _, lease = claim_node(store, coordinator, run, "gen")
    with pytest.raises(UnsafePath), store.transaction():
        workspace.reserve("gen", 1, logical_path, lease.epoch)
    assert store.list_staged_files(run) == []


def test_stage_006_case_collision_is_rejected(
    workspace: Workspace, store: SqliteMetadataStore, coordinator: RunCoordinator, run: str
) -> None:
    _, lease = claim_node(store, coordinator, run, "gen")
    with store.transaction():
        workspace.reserve("gen", 1, "src/App.cs", lease.epoch)
    with pytest.raises(ConflictError), store.transaction():
        workspace.reserve("gen", 1, "src/APP.cs", lease.epoch)


def test_stage_006_symlink_on_the_write_path_is_refused(
    workspace: Workspace, store: SqliteMetadataStore, coordinator: RunCoordinator, run: str, tmp_path: Path
) -> None:
    _, lease = claim_node(store, coordinator, run, "gen")
    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace.sealed_root / "linked").symlink_to(outside, target_is_directory=True)
    with pytest.raises(UnsafePath), store.transaction():
        record = workspace.reserve("gen", 1, "linked/escaped.cs", lease.epoch)
        workspace.write_and_seal(record, b"payload", lease.epoch)
    assert not (outside / "escaped.cs").exists()


def test_stage_007_stale_worker_cannot_seal(
    workspace: Workspace, store: SqliteMetadataStore, coordinator: RunCoordinator, run: str
) -> None:
    """STAGE-007: recovery bumped the epoch; the old worker is fenced out."""
    _, lease = claim_node(store, coordinator, run, "gen")
    with store.transaction():
        record = workspace.reserve("gen", 1, "src/App.cs", lease.epoch)
    with store.transaction():
        node = store.get_node(run, "gen", 1)
        store.claim_node(run, "gen", 1, "lease-recovery", 30, node.version)

    with pytest.raises(StaleLease), store.transaction():
        workspace.write_and_seal(record, b"class App {}", lease.epoch)
    assert not (workspace.sealed_root / "src/App.cs").exists()


def test_duplicate_reservation_is_rejected_by_default(
    workspace: Workspace, store: SqliteMetadataStore, coordinator: RunCoordinator, run: str
) -> None:
    _, lease = claim_node(store, coordinator, run, "gen")
    with store.transaction():
        workspace.reserve("gen", 1, "src/App.cs", lease.epoch)
    with pytest.raises(ConflictError), store.transaction():
        workspace.reserve("gen", 1, "src/App.cs", lease.epoch)


def test_replace_policy_reopens_the_producer_own_aborted_path(
    workspace: Workspace, store: SqliteMetadataStore, coordinator: RunCoordinator, run: str
) -> None:
    """A retry of a failed write re-uses the one row for that logical path."""
    _, lease = claim_node(store, coordinator, run, "gen")

    class Exploding(io.RawIOBase):
        def read(self, size: int = -1) -> bytes:  # type: ignore[override]
            raise OSError("simulated kill during write")

    with store.transaction():
        first = workspace.reserve("gen", 1, "src/App.cs", lease.epoch)
    with pytest.raises(OSError), store.transaction():
        workspace.write_and_seal(first, Exploding(), lease.epoch)
    assert store.get_staged_file(first.staged_file_id).status is StagedFileStatus.ABORTED

    with store.transaction():
        retried = workspace.reserve("gen", 1, "src/App.cs", lease.epoch, overwrite_policy="replace")
        sealed = workspace.write_and_seal(retried, b"class App {}", lease.epoch)
    assert retried.staged_file_id == first.staged_file_id
    assert sealed.status is StagedFileStatus.SEALED
    assert len(store.list_staged_files(run)) == 1


def test_a_second_node_cannot_claim_a_live_path(
    workspace: Workspace, store: SqliteMetadataStore, coordinator: RunCoordinator, run: str
) -> None:
    _, first_lease = claim_node(store, coordinator, run, "gen-a")
    _, second_lease = claim_node(store, coordinator, run, "gen-b")
    with store.transaction():
        workspace.reserve("gen-a", 1, "src/App.cs", first_lease.epoch)
    with pytest.raises(ConflictError), store.transaction():
        workspace.reserve("gen-b", 1, "src/App.cs", second_lease.epoch)


def test_sealed_file_cannot_be_overwritten(
    workspace: Workspace, store: SqliteMetadataStore, coordinator: RunCoordinator, run: str
) -> None:
    _, lease = claim_node(store, coordinator, run, "gen")
    with store.transaction():
        record = workspace.reserve("gen", 1, "src/App.cs", lease.epoch)
        workspace.write_and_seal(record, b"class App {}", lease.epoch)
    with pytest.raises(ConflictError), store.transaction():
        workspace.reserve("gen", 1, "src/App.cs", lease.epoch, overwrite_policy="replace")


def test_per_file_quota_is_enforced(
    tmp_path: Path,
    store: SqliteMetadataStore,
    coordinator: RunCoordinator,
    run: str,
    clock: ManualClock,
    cas,
) -> None:
    from elmos_build_cache.config import WorkspaceConfig

    small = Workspace(
        tmp_path / "ws-small",
        "tenant-test",
        "project-test",
        run,
        store,
        cas,
        config=WorkspaceConfig(max_single_file_mb=0, quota_gb_per_run=1),
        clock=clock,
    )
    _, lease = claim_node(store, coordinator, run, "gen")
    with pytest.raises(QuotaExceeded), store.transaction():
        record = small.reserve("gen", 1, "big.bin", lease.epoch)
        small.write_and_seal(record, b"x" * 1024, lease.epoch)


def test_declared_digest_mismatch_aborts_the_staged_file(
    workspace: Workspace, store: SqliteMetadataStore, coordinator: RunCoordinator, run: str
) -> None:
    _, lease = claim_node(store, coordinator, run, "gen")
    with pytest.raises(ConflictError), store.transaction():
        record = workspace.reserve("gen", 1, "src/App.cs", lease.epoch)
        workspace.write_and_seal(record, b"payload", lease.epoch, expected_digest="sha256:" + "0" * 64)
    assert not (workspace.sealed_root / "src/App.cs").exists()


def test_protected_digests_cover_every_live_staged_file(
    workspace: Workspace, store: SqliteMetadataStore, coordinator: RunCoordinator, run: str
) -> None:
    _, lease = claim_node(store, coordinator, run, "gen")
    with store.transaction():
        records = stage_all(
            workspace,
            "gen",
            1,
            lease.epoch,
            [("a.cs", b"a"), ("b.cs", b"b")],
            file_class=FileClass.PUBLISH_CANDIDATE,
        )
    assert workspace.protected_digests() == {record.artifact_digest for record in records}


def test_recovery_converges_to_a_fixed_point(
    workspace: Workspace, store: SqliteMetadataStore, coordinator: RunCoordinator, run: str
) -> None:
    _, lease = claim_node(store, coordinator, run, "gen")
    with store.transaction():
        stage_all(workspace, "gen", 1, lease.epoch, [("a.cs", b"a")])
        workspace.reserve("gen", 1, "b.cs", lease.epoch)

    with store.transaction():
        first = workspace.recover()
    with store.transaction():
        second = workspace.recover()
    assert first["released"] == ["b.cs"]
    assert second["released"] == []
    assert second["failed"] == []
