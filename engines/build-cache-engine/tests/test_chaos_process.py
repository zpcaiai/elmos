"""CHAOS-001/002 with real operating-system faults.

These tests do not simulate. Each scenario runs in its own interpreter and
sends itself an uncatchable ``SIGKILL`` at a named kill point, so no ``finally``
block, ``atexit`` handler or buffered write ever completes -- and the exhaustion
tests run on a real 1 MiB tmpfs, so ``ENOSPC`` comes from the kernel.

The parent process then inspects only what reached the disk, exactly as a
restarted worker would, and asserts the two invariants that matter: recovery
converges, and nothing partial is ever visible.
"""

from __future__ import annotations

import os
import signal
import sqlite3
import sys
from pathlib import Path

import pytest

from elmos_build_cache.cas import ContentAddressableStore
from elmos_build_cache.chaos import (
    ExhaustionUnavailable,
    KillPoint,
    bounded_filesystem,
    check_no_partial_publication,
    check_recovery_converges,
    exhaust_inodes,
    fill_filesystem,
    release_ballast,
    run_until_kill,
    temporary_mount_point,
)
from elmos_build_cache.clock import SystemClock
from elmos_build_cache.db import SqliteMetadataStore
from elmos_build_cache.enums import StagedFileStatus
from elmos_build_cache.publish import TreePublisher
from elmos_build_cache.staging import Workspace

SRC = str(Path(__file__).resolve().parents[1] / "src")
TENANT = "tenant-chaos"
PROJECT = "project-chaos"
RUN = "run-chaos-1"

SCENARIO = '''
import sys
sys.path.insert(0, {src!r})

from pathlib import Path

from elmos_build_cache.cas import ContentAddressableStore
from elmos_build_cache.chaos import FaultInjector, FaultKind, FaultSpec, KillMode, KillPoint
from elmos_build_cache.db import SqliteMetadataStore
from elmos_build_cache.enums import FileClass, ValidationLevel
from elmos_build_cache.manifests import EvidenceBundle
from elmos_build_cache.publish import TreePublisher
from elmos_build_cache.staging import Workspace

base = Path({base!r})
cas = ContentAddressableStore(base / "cache")
store = SqliteMetadataStore.open(base / "cache" / "index.sqlite")
with store.transaction():
    store.ensure_project({tenant!r}, {project!r})
    snapshot = store.record_snapshot(
        {tenant!r}, {project!r}, "sha256:" + "1" * 64, "sha256:" + "2" * 64, "policy/1"
    )
    try:
        store.get_run({run!r})
    except Exception:
        store.create_run({run!r}, {tenant!r}, {project!r}, snapshot, "1.0.0")

workspace = Workspace(base / "workspaces", {tenant!r}, {project!r}, {run!r}, store, cas)
publisher = TreePublisher(workspace.publish_root, cas, store, {tenant!r}, {run!r})

injector = FaultInjector(
    (FaultSpec(KillPoint.{point}, FaultKind.PROCESS_KILL),),
    mode=KillMode.SIGKILL,
    marker_path=str(base / "kill-marker.json"),
)


def payload():
    yield b"class Generated {{ // first chunk\\n"
    injector.maybe_fail(KillPoint.DURING_WRITE)
    yield b"  // second chunk never arrives on a kill\\n}}\\n"


injector.maybe_fail(KillPoint.BEFORE_RESERVATION)
with store.transaction():
    record = workspace.reserve(
        "gen", 1, "src/Generated.cs", 0, file_class=FileClass.PUBLISH_CANDIDATE
    )
injector.maybe_fail(KillPoint.AFTER_RESERVATION, staged_file_id=record.staged_file_id)

with store.transaction():
    record = workspace.write_and_seal(record, payload(), 0)
injector.maybe_fail(KillPoint.AFTER_SEAL, digest=record.digest)

injector.maybe_fail(KillPoint.BEFORE_CAS_PUT)
with store.transaction():
    record = workspace.promote(record)
injector.maybe_fail(KillPoint.AFTER_CAS_PUT, artifact=record.artifact_digest)

with store.transaction():
    tree = publisher.build_tree_manifest(
        workspace.publishable(), validation_level=ValidationLevel.TEST_VERIFIED
    )
    evidence = EvidenceBundle(
        tree.root_digest,
        ValidationLevel.TEST_VERIFIED,
        ({{"kind": "test", "passed": 1}},),
        "worker-1",
        ("independent-ci",),
    )
    evidence.store(cas)
    candidate = publisher.materialize(tree)
injector.maybe_fail(KillPoint.BEFORE_TREE_SWITCH, tree=tree.root_digest)

with store.transaction():
    publisher.publish(candidate, evidence)
injector.maybe_fail(KillPoint.AFTER_TREE_SWITCH, tree=tree.root_digest)

print("SCENARIO_COMPLETED")
'''


WRITE_KILL_POINTS = [
    KillPoint.BEFORE_RESERVATION,
    KillPoint.AFTER_RESERVATION,
    KillPoint.DURING_WRITE,
    KillPoint.AFTER_SEAL,
    KillPoint.BEFORE_CAS_PUT,
    KillPoint.AFTER_CAS_PUT,
    KillPoint.BEFORE_TREE_SWITCH,
    KillPoint.AFTER_TREE_SWITCH,
]


def run_scenario(base: Path, point: KillPoint):
    source = SCENARIO.format(
        src=SRC, base=str(base), tenant=TENANT, project=PROJECT, run=RUN, point=point.name
    )
    return run_until_kill(
        source,
        base / "scripts",
        marker=base / "kill-marker.json",
        env={"PYTHONPATH": SRC, "PYTHONDONTWRITEBYTECODE": "1"},
    )


def reopen(base: Path):
    store = SqliteMetadataStore.open(base / "cache" / "index.sqlite", SystemClock())
    cas = ContentAddressableStore(base / "cache")
    workspace = Workspace(base / "workspaces", TENANT, PROJECT, RUN, store, cas)
    publisher = TreePublisher(workspace.publish_root, cas, store, TENANT, RUN)
    return store, cas, workspace, publisher


@pytest.mark.parametrize("point", WRITE_KILL_POINTS, ids=[p.name for p in WRITE_KILL_POINTS])
def test_chaos_001_real_sigkill_at_every_boundary(tmp_path: Path, point: KillPoint) -> None:
    """CHAOS-001: a real SIGKILL at each boundary leaves recoverable state."""
    base = tmp_path / "workdir"
    result = run_scenario(base, point)

    assert result.sigkilled, result.to_dict()
    assert result.killed_by_signal == int(signal.SIGKILL)
    assert "SCENARIO_COMPLETED" not in result.stdout
    assert result.fired is not None
    assert result.fired["kill_point"] == point.value
    assert result.fired["mode"] == "SIGKILL"

    store, cas, workspace, publisher = reopen(base)
    try:
        # The invariant that must hold before anything is repaired.
        assert check_no_partial_publication(publisher).held

        with store.transaction():
            first = workspace.recover()
        assert first["failed"] == []

        def recover() -> dict[str, object]:
            with store.transaction():
                return workspace.recover()

        assert check_recovery_converges(recover).held
        assert check_no_partial_publication(publisher).held

        # Whatever survived is in a terminal or reusable state -- never WRITING.
        statuses = {record.status for record in store.list_staged_files(RUN)}
        assert StagedFileStatus.WRITING not in statuses
        assert StagedFileStatus.RESERVED not in statuses
        assert list(workspace.pending_root.rglob("*.elmos-tmp-*")) == []
    finally:
        store.close()


def test_chaos_001_kill_during_write_leaves_no_sealed_file(tmp_path: Path) -> None:
    """A kill mid-stream must not produce a sealed, truncated file."""
    base = tmp_path / "workdir"
    assert run_scenario(base, KillPoint.DURING_WRITE).sigkilled

    store, cas, workspace, publisher = reopen(base)
    try:
        assert not (workspace.sealed_root / "src" / "Generated.cs").exists()
        with store.transaction():
            summary = workspace.recover()
        assert summary["failed"] == []
        assert publisher.current_tree_digest() is None
    finally:
        store.close()


def test_chaos_001_kill_before_pointer_switch_publishes_nothing(tmp_path: Path) -> None:
    """The candidate tree is complete on disk, but nothing is visible."""
    base = tmp_path / "workdir"
    assert run_scenario(base, KillPoint.BEFORE_TREE_SWITCH).sigkilled

    store, cas, workspace, publisher = reopen(base)
    try:
        assert publisher.current_tree_digest() is None
        assert len(publisher.list_trees()) == 1  # materialised, not published
        assert check_no_partial_publication(publisher).held
    finally:
        store.close()


def test_chaos_001_kill_after_pointer_switch_exposes_a_complete_tree(tmp_path: Path) -> None:
    """Once the pointer flipped, the tree is complete and readable."""
    base = tmp_path / "workdir"
    assert run_scenario(base, KillPoint.AFTER_TREE_SWITCH).sigkilled

    store, cas, workspace, publisher = reopen(base)
    try:
        digest = publisher.current_tree_digest()
        assert digest is not None
        assert check_no_partial_publication(publisher).held
        body = publisher.read_published("src/Generated.cs")
        assert body.startswith(b"class Generated {")
        assert body.endswith(b"}\n")  # the file is whole, not truncated
    finally:
        store.close()


def test_sealed_file_survives_a_kill_and_promotes_on_recovery(tmp_path: Path) -> None:
    """AFTER_SEAL: the bytes are durable; recovery finishes the promotion."""
    base = tmp_path / "workdir"
    assert run_scenario(base, KillPoint.AFTER_SEAL).sigkilled

    store, cas, workspace, publisher = reopen(base)
    try:
        staged = store.list_staged_files(RUN)
        assert [record.status for record in staged] == [StagedFileStatus.SEALED]
        with store.transaction():
            summary = workspace.recover()
        assert summary["promoted"] == ["src/Generated.cs"]
        promoted = store.list_staged_files(RUN)[0]
        assert promoted.status is StagedFileStatus.CAS_PROMOTED
        assert cas.verify(promoted.artifact_digest or "")
    finally:
        store.close()


# --------------------------------------------------------------------------
# CHAOS-002: real space and inode exhaustion
# --------------------------------------------------------------------------
@pytest.fixture
def bounded(tmp_path: Path):
    mount = temporary_mount_point()
    try:
        with bounded_filesystem(mount, size_bytes=1 << 20, inodes=96) as root:
            yield root
    except ExhaustionUnavailable as exc:  # pragma: no cover - platform dependent
        pytest.skip(f"real filesystem exhaustion unavailable: {exc}")


def test_chaos_002_real_enospc_is_a_controlled_failure(bounded: Path) -> None:
    """CHAOS-002: a genuinely full filesystem fails cleanly and recovers."""
    store = SqliteMetadataStore.open(bounded / "cache" / "index.sqlite")
    try:
        cas = ContentAddressableStore(bounded / "cache")
        with store.transaction():
            store.ensure_project(TENANT, PROJECT)
            snapshot = store.record_snapshot(
                TENANT, PROJECT, "sha256:" + "1" * 64, "sha256:" + "2" * 64, "policy/1"
            )
            store.create_run(RUN, TENANT, PROJECT, snapshot, "1.0.0")
        workspace = Workspace(bounded / "workspaces", TENANT, PROJECT, RUN, store, cas)

        with store.transaction():
            reserved = workspace.reserve("gen", 1, "src/Small.cs", 0)
            sealed = workspace.write_and_seal(reserved, b"class Small {}", 0)
            workspace.promote(sealed)

        surviving = store.list_staged_files(RUN)[0]
        assert surviving.artifact_digest is not None
        assert cas.verify(surviving.artifact_digest)

        written = fill_filesystem(bounded)
        assert written > 0
        assert os.statvfs(bounded).f_bavail == 0  # genuinely full

        # The kernel, not a mock, refuses the next write.
        with pytest.raises((OSError, sqlite3.OperationalError)) as error:
            with store.transaction():
                doomed = workspace.reserve("gen", 1, "src/Big.cs", 0)
                workspace.write_and_seal(doomed, b"x" * 400_000, 0)
        detail = str(error.value).lower()
        assert "no space" in detail or "disk" in detail or "full" in detail, detail

        assert not (workspace.sealed_root / "src" / "Big.cs").exists()

        release_ballast(bounded)
        with store.transaction():
            summary = workspace.recover()
        assert summary["failed"] == []
        # The work that completed before exhaustion is intact and still verifies.
        assert cas.verify(surviving.artifact_digest)
        assert (workspace.sealed_root / "src" / "Small.cs").read_bytes() == b"class Small {}"
    finally:
        store.close()


def test_chaos_002_real_inode_exhaustion_is_bounded(bounded: Path) -> None:
    """Inode exhaustion is a distinct failure from running out of bytes."""
    created = exhaust_inodes(bounded, limit=500)
    assert 0 < created < 500  # the 96-inode limit bit before the loop bound

    with pytest.raises(OSError) as error:
        (bounded / "one-more").touch()
    assert error.value.errno in (28, 122)  # ENOSPC / EDQUOT

    for index in range(created):
        (bounded / f".inode-{index}").unlink(missing_ok=True)
    (bounded / "recovered").touch()  # capacity is usable again


def test_bounded_filesystem_is_really_bounded(bounded: Path) -> None:
    stats = os.statvfs(bounded)
    assert stats.f_blocks * stats.f_frsize <= 2 << 20
    assert stats.f_files <= 128


def test_scenario_runs_to_completion_without_a_fault(tmp_path: Path) -> None:
    """Control: the same scenario with no armed fault publishes normally."""
    base = tmp_path / "workdir"
    source = SCENARIO.format(
        src=SRC,
        base=str(base),
        tenant=TENANT,
        project=PROJECT,
        run=RUN,
        point=KillPoint.AFTER_METADATA_COMMIT.name,  # never reached by the script
    )
    result = run_until_kill(source, base / "scripts", env={"PYTHONPATH": SRC})

    assert result.returncode == 0, result.stderr[-2000:]
    assert "SCENARIO_COMPLETED" in result.stdout

    store, cas, workspace, publisher = reopen(base)
    try:
        assert publisher.current_tree_digest() is not None
        assert publisher.read_published("src/Generated.cs").endswith(b"}\n")
        assert check_no_partial_publication(publisher).held
    finally:
        store.close()


def test_python_executable_is_the_one_running_the_tests() -> None:
    assert Path(sys.executable).exists()
