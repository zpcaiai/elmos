"""Shared fixtures.

Every test uses a :class:`ManualClock` so lease expiry, TTLs and grace periods
are exercised deterministically instead of by sleeping.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from elmos_build_cache.action_cache import ActionCache
from elmos_build_cache.cas import ContentAddressableStore
from elmos_build_cache.checkpoint import CheckpointService
from elmos_build_cache.clock import ManualClock
from elmos_build_cache.config import CacheConfig, WorkspaceConfig
from elmos_build_cache.db import SqliteMetadataStore
from elmos_build_cache.journal import LeaseManager, RunCoordinator, RunJournal
from elmos_build_cache.publish import TreePublisher
from elmos_build_cache.staging import Workspace

TENANT = "tenant-test"
PROJECT = "project-test"
RUN = "run-test-0001"
SNAPSHOT_ROOT = "sha256:" + "1" * 64
SNAPSHOT_MANIFEST = "sha256:" + "2" * 64


def digest(character: str) -> str:
    return "sha256:" + character * 64


@pytest.fixture
def clock() -> ManualClock:
    return ManualClock()


@pytest.fixture
def cas(tmp_path: Path) -> ContentAddressableStore:
    return ContentAddressableStore(tmp_path / "cache")


@pytest.fixture
def store(tmp_path: Path, clock: ManualClock) -> Iterator[SqliteMetadataStore]:
    metadata = SqliteMetadataStore.open(tmp_path / "cache" / "index.sqlite", clock)
    with metadata.transaction():
        metadata.ensure_project(TENANT, PROJECT)
    yield metadata
    metadata.close()


@pytest.fixture
def run(store: SqliteMetadataStore) -> str:
    with store.transaction():
        snapshot_id = store.record_snapshot(
            TENANT, PROJECT, SNAPSHOT_ROOT, SNAPSHOT_MANIFEST, "elmos.snapshot-policy/1.0.0"
        )
        store.create_run(RUN, TENANT, PROJECT, snapshot_id, "1.0.0")
    return RUN


@pytest.fixture
def workspace(
    tmp_path: Path,
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    clock: ManualClock,
    run: str,
) -> Workspace:
    return Workspace(
        tmp_path / "workspaces",
        TENANT,
        PROJECT,
        run,
        store,
        cas,
        config=WorkspaceConfig(quota_gb_per_run=1, max_files_per_run=1000),
        clock=clock,
    )


@pytest.fixture
def journal(workspace: Workspace, clock: ManualClock, run: str) -> RunJournal:
    return RunJournal(workspace.root / "control" / "journal.ndjson", run, clock)


@pytest.fixture
def coordinator(
    store: SqliteMetadataStore, journal: RunJournal, clock: ManualClock
) -> RunCoordinator:
    return RunCoordinator(store, journal, LeaseManager(store, clock, lease_seconds=30), clock=clock)


@pytest.fixture
def checkpoints(
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    workspace: Workspace,
    journal: RunJournal,
    clock: ManualClock,
) -> CheckpointService:
    return CheckpointService(store, cas, workspace, journal, clock)


@pytest.fixture
def publisher(
    workspace: Workspace,
    cas: ContentAddressableStore,
    store: SqliteMetadataStore,
    clock: ManualClock,
    run: str,
) -> TreePublisher:
    return TreePublisher(workspace.publish_root, cas, store, TENANT, run, keep_previous=2, clock=clock)


@pytest.fixture
def action_cache(
    store: SqliteMetadataStore, cas: ContentAddressableStore, clock: ManualClock
) -> ActionCache:
    return ActionCache(store, cas, clock, negative_ttl_seconds=900.0)


@pytest.fixture
def config() -> CacheConfig:
    return CacheConfig()


def claim_node(
    store: SqliteMetadataStore,
    coordinator: RunCoordinator,
    run_id: str,
    node_id: str,
    stage_id: str = "target-code-generation",
    worker: str = "worker-1",
):
    """Create, ready and claim a node; returns ``(node, lease)``."""
    with store.transaction():
        store.upsert_node(run_id, node_id, stage_id, "1.0.0")
        coordinator.mark_ready(run_id, node_id, 1)
        return coordinator.begin(run_id, node_id, 1, worker)
