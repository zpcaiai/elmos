"""REMOTE-001..003 against a live S3 endpoint.

These run the S3 backend against a real HTTP S3 service (a moto server), not a
stubbed client: conditional creation is enforced by the service returning 412,
multipart is a genuine create/upload-part/complete cycle, and an aborted upload
is checked to leave nothing discoverable.

That closes the "S3RemoteBackend is written but never certified" gap. What it
still does not prove is AWS-specific behaviour (regional consistency, IAM,
lifecycle) -- see the handoff.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

boto3 = pytest.importorskip("boto3")
moto_server = pytest.importorskip("moto.server")

from elmos_build_cache.cas import ContentAddressableStore  # noqa: E402
from elmos_build_cache.clock import ManualClock  # noqa: E402
from elmos_build_cache.db import SqliteMetadataStore  # noqa: E402
from elmos_build_cache.enums import TrustNamespace  # noqa: E402
from elmos_build_cache.errors import DigestMismatch, RemoteUnavailable  # noqa: E402
from elmos_build_cache.remote import RemoteCache, S3RemoteBackend  # noqa: E402

BUCKET = "elmos-cache-test"
TENANT = "tenant-s3"
KEY = "sha256:" + "7" * 64


@pytest.fixture(scope="module")
def endpoint() -> Iterator[str]:
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
    os.environ.setdefault("AWS_SESSION_TOKEN", "testing")
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
    server = moto_server.ThreadedMotoServer(ip_address="127.0.0.1", port=0, verbose=False)
    server.start()
    host, port = server.get_host_and_port()
    try:
        yield f"http://{host}:{port}"
    finally:
        server.stop()


@pytest.fixture
def s3_client(endpoint: str):
    client = boto3.client("s3", endpoint_url=endpoint)
    for bucket in client.list_buckets().get("Buckets", []):
        name = bucket["Name"]
        objects = client.list_objects_v2(Bucket=name).get("Contents", [])
        for item in objects:
            client.delete_object(Bucket=name, Key=item["Key"])
        client.delete_bucket(Bucket=name)
    client.create_bucket(Bucket=BUCKET)
    return client


@pytest.fixture
def backend(s3_client) -> S3RemoteBackend:
    return S3RemoteBackend(BUCKET, prefix="elmos", client=s3_client)


@pytest.fixture
def remote(backend: S3RemoteBackend, tmp_path, clock: ManualClock) -> Iterator[RemoteCache]:
    cas = ContentAddressableStore(tmp_path / "cache")
    store = SqliteMetadataStore.open(tmp_path / "cache" / "index.sqlite", clock)
    with store.transaction():
        store.ensure_project(TENANT, "project-s3")
    yield RemoteCache(
        backend,
        cas,
        store,
        TENANT,
        TrustNamespace.BRANCH,
        clock=clock,
        multipart_threshold=6 * 1024 * 1024,
        chunk_size=5 * 1024 * 1024,
    )
    store.close()


def register(remote: RemoteCache, payload: bytes) -> str:
    blob = remote.cas.put_bytes(payload)
    with remote.store.transaction():
        remote.store.register_artifact(
            TENANT, blob, len(payload), "application/octet-stream", "blob"
        )
    return blob


# --------------------------------------------------------------------------
# the service, not a stub
# --------------------------------------------------------------------------
def test_the_endpoint_is_a_real_http_service(backend: S3RemoteBackend, endpoint: str) -> None:
    assert endpoint.startswith("http://")
    assert backend.client.meta.endpoint_url == endpoint
    backend.put_if_absent("probe", b"payload")
    assert backend.get("probe") == b"payload"
    assert list(backend.list_prefix("probe")) == ["probe"]


def test_conditional_creation_is_enforced_by_the_service(backend: S3RemoteBackend) -> None:
    """REMOTE-002: a canonical entry is never silently overwritten."""
    assert backend.put_if_absent("blobs/x", b"first writer") is True
    assert backend.put_if_absent("blobs/x", b"second writer") is False
    assert backend.get("blobs/x") == b"first writer"

    # Bypass the client-side pre-check: the service itself must refuse.
    with pytest.raises(Exception) as error:
        backend.client.put_object(
            Bucket=BUCKET, Key="elmos/blobs/x", Body=b"third writer", IfNoneMatch="*"
        )
    assert "PreconditionFailed" in str(error.value)
    assert backend.get("blobs/x") == b"first writer"


def test_concurrent_identical_writers_converge(backend: S3RemoteBackend) -> None:
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=6) as pool:
        outcomes = list(pool.map(lambda _: backend.put_if_absent("blobs/race", b"same"), range(6)))
    assert outcomes.count(True) >= 1
    assert backend.get("blobs/race") == b"same"


# --------------------------------------------------------------------------
# multipart
# --------------------------------------------------------------------------
def test_native_multipart_upload_round_trips(remote: RemoteCache, backend: S3RemoteBackend) -> None:
    payload = os.urandom(12 * 1024 * 1024)
    blob = register(remote, payload)
    with remote.store.transaction():
        assert remote.upload_blob(blob) is True

    assert backend.get(remote.blob_key(blob)) == payload
    # The upload completed, so nothing is left in flight.
    assert backend.list_multipart_uploads() == []


def test_an_aborted_multipart_upload_leaves_nothing_discoverable(
    remote: RemoteCache, backend: S3RemoteBackend
) -> None:
    """REMOTE-001: an interrupted transfer produces no readable object."""
    payload = os.urandom(12 * 1024 * 1024)
    blob = register(remote, payload)
    key = remote.blob_key(blob)

    original = backend.client.complete_multipart_upload

    def explode(**kwargs: object) -> None:
        raise RuntimeError("simulated network loss before completion")

    backend.client.complete_multipart_upload = explode  # type: ignore[method-assign]
    try:
        with pytest.raises(RemoteUnavailable), remote.store.transaction():
            remote.upload_blob(blob)
    finally:
        backend.client.complete_multipart_upload = original  # type: ignore[method-assign]

    assert backend.exists(key) is False
    assert backend.list_multipart_uploads() == []  # the abort cleaned up

    # And the retry succeeds against the same key.
    with remote.store.transaction():
        assert remote.upload_blob(blob) is True
    assert backend.get(key) == payload


def test_multipart_threshold_is_respected(remote: RemoteCache, backend: S3RemoteBackend) -> None:
    small = register(remote, b"small payload")
    with remote.store.transaction():
        remote.upload_blob(small)
    assert backend.get(remote.blob_key(small)) == b"small payload"
    assert backend.list_multipart_uploads() == []


# --------------------------------------------------------------------------
# end-to-end identity and trust
# --------------------------------------------------------------------------
def test_publish_then_restore_into_an_empty_cache(
    remote: RemoteCache, backend: S3RemoteBackend, tmp_path, clock: ManualClock
) -> None:
    blob = register(remote, b"generated output")
    manifest = register(remote, b'{"kind":"elmos.action-result/v1"}')
    with remote.store.transaction():
        assert remote.publish_action(KEY, manifest, [blob], "TEST_VERIFIED", "worker-1", manifest)

    clean = ContentAddressableStore(tmp_path / "clean")
    consumer = RemoteCache(backend, clean, remote.store, TENANT, TrustNamespace.BRANCH, clock=clock)
    with remote.store.transaction():
        entry = consumer.restore_action(KEY)
    assert entry is not None
    assert clean.get_bytes(blob) == b"generated output"


def test_tampered_object_is_rejected_end_to_end(
    remote: RemoteCache, backend: S3RemoteBackend, tmp_path, clock: ManualClock
) -> None:
    blob = register(remote, b"trustworthy bytes")
    with remote.store.transaction():
        remote.upload_blob(blob)

    backend.delete(remote.blob_key(blob))
    backend.put_if_absent(remote.blob_key(blob), b"tampered in the bucket")

    clean = ContentAddressableStore(tmp_path / "clean")
    consumer = RemoteCache(backend, clean, remote.store, TENANT, TrustNamespace.BRANCH, clock=clock)
    with pytest.raises(DigestMismatch):
        consumer.download_blob(blob)
    assert not clean.contains(blob)


def test_trust_namespaces_are_separate_key_spaces(
    backend: S3RemoteBackend, remote: RemoteCache, clock: ManualClock
) -> None:
    """REMOTE-003, over the real object store."""
    blob = register(remote, b"fork output")
    manifest = register(remote, b'{"kind":"elmos.action-result/v1"}')
    fork = RemoteCache(backend, remote.cas, remote.store, TENANT, TrustNamespace.FORK, clock=clock)
    official = RemoteCache(
        backend, remote.cas, remote.store, TENANT, TrustNamespace.OFFICIAL, clock=clock
    )
    with remote.store.transaction():
        fork.publish_action(KEY, manifest, [blob], "TEST_VERIFIED", "fork-worker", manifest)

    assert fork.fetch_action(KEY) is not None
    assert official.fetch_action(KEY) is None
    keys = list(backend.list_prefix("actions"))
    assert any("/fork/" in key for key in keys)
    assert not any("/official/" in key for key in keys)


def test_scrub_and_repair_against_the_service(remote: RemoteCache, backend: S3RemoteBackend) -> None:
    blob = register(remote, b"repairable payload")
    with remote.store.transaction():
        remote.upload_blob(blob)

    backend.delete(remote.blob_key(blob))
    backend.put_if_absent(remote.blob_key(blob), b"corrupted in place")
    assert remote.scrub([blob])["corrupt"] == [blob]

    assert remote.repair(blob) is True
    assert remote.scrub([blob])["healthy"] == [blob]


def test_prefix_isolation(s3_client, remote: RemoteCache) -> None:
    other = S3RemoteBackend(BUCKET, prefix="another-tenant", client=s3_client)
    blob = register(remote, b"scoped payload")
    with remote.store.transaction():
        remote.upload_blob(blob)
    assert other.exists(remote.blob_key(blob)) is False
    assert remote.backend.exists(remote.blob_key(blob)) is True


def test_offline_then_synchronise_is_idempotent(remote: RemoteCache) -> None:
    blob = register(remote, b"produced offline")
    manifest = register(remote, b'{"kind":"elmos.action-result/v1"}')
    entry = {
        "action_key": KEY,
        "result_manifest_digest": manifest,
        "blobs": [blob],
        "validation_level": "TEST_VERIFIED",
        "producer_identity": "offline-worker",
        "provenance_digest": manifest,
    }
    with remote.store.transaction():
        first = remote.synchronize([blob, manifest], [entry])
    with remote.store.transaction():
        second = remote.synchronize([blob, manifest], [entry])
    assert first["status"] == "OK" and first["conflicts"] == []
    assert second["uploaded"] == [] and second["conflicts"] == []
