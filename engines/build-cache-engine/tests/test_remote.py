"""REMOTE-001..003: outage safety, offline sync and trust-namespace isolation."""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import TENANT, digest
from elmos_build_cache.cas import ContentAddressableStore
from elmos_build_cache.clock import ManualClock
from elmos_build_cache.db import SqliteMetadataStore
from elmos_build_cache.enums import TrustNamespace
from elmos_build_cache.errors import DigestMismatch, RemoteUnavailable
from elmos_build_cache.remote import (
    FilesystemRemoteBackend,
    RemoteCache,
    ReplicaSet,
    TransferBudget,
    mirror_local_to_remote,
)

KEY = digest("7")


@pytest.fixture
def backend(tmp_path: Path) -> FilesystemRemoteBackend:
    return FilesystemRemoteBackend(tmp_path / "remote")


@pytest.fixture
def remote(
    backend: FilesystemRemoteBackend,
    cas: ContentAddressableStore,
    store: SqliteMetadataStore,
    clock: ManualClock,
) -> RemoteCache:
    return RemoteCache(
        backend,
        cas,
        store,
        TENANT,
        TrustNamespace.BRANCH,
        clock=clock,
        multipart_threshold=64,
        chunk_size=64,
    )


def seed(remote: RemoteCache, store: SqliteMetadataStore, cas: ContentAddressableStore) -> tuple[str, str]:
    blob = cas.put_bytes(b"generated output" * 20)
    manifest = cas.put_bytes(b'{"kind":"elmos.action-result/v1"}')
    with store.transaction():
        for item in (blob, manifest):
            store.register_artifact(TENANT, item, cas.info(item).size, "application/octet-stream", "blob")
    return blob, manifest


def test_remote_001_outage_leaves_nothing_discoverable(
    remote: RemoteCache, backend: FilesystemRemoteBackend, store: SqliteMetadataStore, cas: ContentAddressableStore
) -> None:
    """REMOTE-001: a failed upload never produces a resolvable entry."""
    blob, manifest = seed(remote, store, cas)
    backend.fail = True
    with pytest.raises(RemoteUnavailable), store.transaction():
        remote.publish_action(KEY, manifest, [blob], "TEST_VERIFIED", "worker-1", manifest)
    backend.fail = False
    assert remote.fetch_action(KEY) is None


def test_remote_001_local_execution_survives_an_outage(
    remote: RemoteCache, backend: FilesystemRemoteBackend, store: SqliteMetadataStore, cas: ContentAddressableStore
) -> None:
    blob, manifest = seed(remote, store, cas)
    backend.fail = True
    outcome = mirror_local_to_remote(remote, [blob, manifest])
    assert outcome["pushed"] == []
    assert sorted(outcome["queued"]) == sorted([blob, manifest])
    assert cas.get_bytes(blob)  # local cache untouched

    backend.fail = False
    drained = remote.drain()
    assert drained["flushed"] == 2 and drained["remaining"] == 0


def test_remote_002_offline_then_synchronise_is_idempotent(
    remote: RemoteCache, store: SqliteMetadataStore, cas: ContentAddressableStore
) -> None:
    """REMOTE-002: syncing twice does not overwrite or duplicate anything."""
    blob, manifest = seed(remote, store, cas)
    entry = {
        "action_key": KEY,
        "result_manifest_digest": manifest,
        "blobs": [blob],
        "validation_level": "TEST_VERIFIED",
        "producer_identity": "offline-worker",
        "provenance_digest": manifest,
    }
    with store.transaction():
        first = remote.synchronize([blob, manifest], [entry])
    with store.transaction():
        second = remote.synchronize([blob, manifest], [entry])

    assert first["status"] == "OK" and first["conflicts"] == []
    assert second["status"] == "OK" and second["conflicts"] == []
    assert second["uploaded"] == []  # everything was already durable
    assert remote.fetch_action(KEY) is not None


def test_remote_002_divergent_entry_is_a_conflict_not_an_overwrite(
    remote: RemoteCache, store: SqliteMetadataStore, cas: ContentAddressableStore
) -> None:
    blob, manifest = seed(remote, store, cas)
    other = cas.put_bytes(b"a different result manifest")
    with store.transaction():
        store.register_artifact(TENANT, other, cas.info(other).size, "application/json", "blob")
        remote.publish_action(KEY, manifest, [blob], "TEST_VERIFIED", "worker-1", manifest)
        outcome = remote.synchronize(
            [],
            [
                {
                    "action_key": KEY,
                    "result_manifest_digest": other,
                    "blobs": [],
                    "validation_level": "TEST_VERIFIED",
                    "producer_identity": "worker-2",
                    "provenance_digest": other,
                }
            ],
        )
    assert outcome["conflicts"] == [KEY]
    fetched = remote.fetch_action(KEY)
    assert fetched is not None and fetched["result_manifest_digest"] == manifest


def test_remote_003_fork_result_cannot_satisfy_official(
    backend: FilesystemRemoteBackend,
    cas: ContentAddressableStore,
    store: SqliteMetadataStore,
    clock: ManualClock,
) -> None:
    """REMOTE-003: trust namespaces are separate key spaces, not labels."""
    fork = RemoteCache(backend, cas, store, TENANT, TrustNamespace.FORK, clock=clock)
    official = RemoteCache(backend, cas, store, TENANT, TrustNamespace.OFFICIAL, clock=clock)
    blob, manifest = seed(fork, store, cas)
    with store.transaction():
        fork.publish_action(KEY, manifest, [blob], "TEST_VERIFIED", "fork-worker", manifest)

    assert fork.fetch_action(KEY) is not None
    assert official.fetch_action(KEY) is None


def test_end_to_end_digest_verification_rejects_tampering(
    remote: RemoteCache,
    backend: FilesystemRemoteBackend,
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    tmp_path: Path,
    clock: ManualClock,
) -> None:
    blob, manifest = seed(remote, store, cas)
    with store.transaction():
        remote.publish_action(KEY, manifest, [blob], "TEST_VERIFIED", "worker-1", manifest)
    backend.delete(remote.blob_key(blob))
    backend.put_if_absent(remote.blob_key(blob), b"tampered payload")

    clean = ContentAddressableStore(tmp_path / "clean")
    consumer = RemoteCache(backend, clean, store, TENANT, TrustNamespace.BRANCH, clock=clock)
    with pytest.raises(DigestMismatch):
        consumer.download_blob(blob)
    assert not clean.contains(blob)


def test_multipart_upload_publishes_parts_before_the_object(
    remote: RemoteCache, backend: FilesystemRemoteBackend, store: SqliteMetadataStore, cas: ContentAddressableStore
) -> None:
    payload = b"y" * 500
    blob = cas.put_bytes(payload)
    with store.transaction():
        store.register_artifact(TENANT, blob, len(payload), "application/octet-stream", "blob")
        remote.upload_blob(blob)
    keys = list(backend.list_prefix("blobs"))
    assert any(key.endswith(".multipart.json") for key in keys)
    assert sum(1 for key in keys if ".part" in key) == 8


def test_read_through_restores_into_an_empty_cache(
    remote: RemoteCache,
    backend: FilesystemRemoteBackend,
    store: SqliteMetadataStore,
    cas: ContentAddressableStore,
    tmp_path: Path,
    clock: ManualClock,
) -> None:
    blob, manifest = seed(remote, store, cas)
    with store.transaction():
        remote.publish_action(KEY, manifest, [blob], "TEST_VERIFIED", "worker-1", manifest)

    clean = ContentAddressableStore(tmp_path / "clean")
    consumer = RemoteCache(backend, clean, store, TENANT, TrustNamespace.BRANCH, clock=clock)
    with store.transaction():
        entry = consumer.restore_action(KEY)
    assert entry is not None
    assert clean.get_bytes(blob) == cas.get_bytes(blob)


def test_miss_lease_deduplicates_remote_execution(remote: RemoteCache, clock: ManualClock) -> None:
    assert remote.acquire_miss_lease(KEY, seconds=60) is True
    assert remote.acquire_miss_lease(KEY, seconds=60) is False
    clock.advance(120)
    assert remote.acquire_miss_lease(KEY, seconds=60) is True


def test_write_behind_queue_is_bounded(remote: RemoteCache) -> None:
    remote._queue_limit = 3
    for index in range(6):
        remote.enqueue("blob", f"key-{index}", b"payload")
    assert remote.pending == 3
    assert remote.stats.dropped == 3


def test_retry_budget_stops_a_transfer_storm(
    remote: RemoteCache, backend: FilesystemRemoteBackend, store: SqliteMetadataStore, cas: ContentAddressableStore
) -> None:
    remote.retry_budget = 2
    blob, _ = seed(remote, store, cas)
    remote.enqueue_blob(blob)
    backend.fail = True
    for _ in range(3):
        remote.drain()
    assert remote.pending == 0
    assert remote.stats.dropped >= 1


def test_scrub_and_repair_fix_a_bad_remote_object(
    remote: RemoteCache, backend: FilesystemRemoteBackend, store: SqliteMetadataStore, cas: ContentAddressableStore
) -> None:
    blob, manifest = seed(remote, store, cas)
    with store.transaction():
        remote.upload_blob(blob)
    backend.delete(remote.blob_key(blob))
    backend.put_if_absent(remote.blob_key(blob), b"corrupt")

    assert remote.scrub([blob])["corrupt"] == [blob]
    assert remote.repair(blob) is True
    assert remote.scrub([blob])["healthy"] == [blob]


def test_transfer_budget_is_enforced(
    backend: FilesystemRemoteBackend, cas: ContentAddressableStore, store: SqliteMetadataStore, clock: ManualClock
) -> None:
    remote = RemoteCache(
        backend, cas, store, TENANT, clock=clock, budget=TransferBudget(max_upload_bytes=10)
    )
    blob = cas.put_bytes(b"z" * 100)
    with store.transaction():
        store.register_artifact(TENANT, blob, 100, "application/octet-stream", "blob")
    with pytest.raises(RemoteUnavailable, match="budget"), store.transaction():
        remote.upload_blob(blob)


def test_replica_set_reads_the_nearest_and_writes_all(tmp_path: Path) -> None:
    primary = FilesystemRemoteBackend(tmp_path / "primary")
    regional = FilesystemRemoteBackend(tmp_path / "eu")
    replicas = ReplicaSet(primary, {"eu": regional})
    replicas.write("blobs/x", b"payload")
    assert replicas.read("blobs/x", preferred="eu") == b"payload"
    primary.fail = True
    assert replicas.read("blobs/x", preferred="eu") == b"payload"


def test_health_reports_reachability(remote: RemoteCache, backend: FilesystemRemoteBackend) -> None:
    assert remote.health()["reachable"] is True
    backend.fail = True
    assert remote.health()["reachable"] is False
