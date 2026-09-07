"""CAS-001..003: convergence, interruption safety and corruption handling."""

from __future__ import annotations

import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from elmos_build_cache.cas import BLOB_MODE, ContentAddressableStore
from elmos_build_cache.errors import CorruptObject, DigestMismatch, NotFound


def corrupt_stored_blob(path: Path, payload: bytes) -> None:
    """Simulate on-disk corruption of a stored blob.

    A committed blob is ``BLOB_MODE`` (``0o444``), so a plain ``write_bytes``
    is ``PermissionError`` for every user except root -- which is exactly the
    hardening ``test_every_store_path_leaves_the_blob_read_only`` asserts.
    Corruption arrives from outside the process (bit rot, a bad restore, a
    hostile write), so the simulation unlocks the file, rewrites it, and puts
    the mode back: the code under test then meets a genuinely read-only
    corrupt object, and quarantine/repair have to move it as an unprivileged
    user would.
    """
    path.chmod(0o600)
    path.write_bytes(payload)
    path.chmod(BLOB_MODE)


def test_cas_001_concurrent_identical_writers_converge(cas: ContentAddressableStore) -> None:
    """CAS-001: create-if-absent means both writers win, with one object."""
    payload = b"identical bytes" * 100
    with ThreadPoolExecutor(max_workers=8) as pool:
        digests = list(pool.map(lambda _: cas.put_bytes(payload), range(8)))
    assert len(set(digests)) == 1
    assert len(list(cas.iter_digests())) == 1
    assert cas.get_bytes(digests[0]) == payload


def test_cas_002_interrupted_write_leaves_no_visible_object(cas: ContentAddressableStore) -> None:
    """CAS-002: a kill during streaming leaves no canonical object behind."""

    class Exploding(io.RawIOBase):
        def __init__(self) -> None:
            self.sent = 0

        def read(self, size: int = -1) -> bytes:  # type: ignore[override]
            if self.sent >= 1:
                raise OSError("simulated process kill during write")
            self.sent += 1
            return b"partial"

    with pytest.raises(OSError, match="simulated process kill"):
        cas.put_stream(Exploding())
    assert list(cas.iter_digests()) == []
    incoming = list((cas.objects_root / ".incoming").glob("*")) if (cas.objects_root / ".incoming").exists() else []
    assert incoming == []


def test_cas_003_corruption_is_rejected_and_quarantined(cas: ContentAddressableStore) -> None:
    """CAS-003: a corrupt object refuses to serve and is moved aside."""
    digest = cas.put_bytes(b"trustworthy payload")
    corrupt_stored_blob(cas.path_for(digest), b"tampered")

    with pytest.raises(CorruptObject):
        cas.get_bytes(digest)
    assert cas.is_quarantined(digest)
    assert not cas.contains(digest)
    with pytest.raises(CorruptObject):
        cas.info(digest)


def test_cas_003_repair_from_verified_replica(tmp_path: Path, cas: ContentAddressableStore) -> None:
    replica = ContentAddressableStore(tmp_path / "replica")
    digest = cas.put_bytes(b"trustworthy payload")
    replica.put_bytes(b"trustworthy payload")
    corrupt_stored_blob(cas.path_for(digest), b"tampered")
    with pytest.raises(CorruptObject):
        cas.get_bytes(digest)

    assert cas.repair_from(digest, replica) is True
    assert cas.get_bytes(digest) == b"trustworthy payload"
    assert not cas.is_quarantined(digest)


def test_declared_digest_mismatch_is_rejected(cas: ContentAddressableStore) -> None:
    with pytest.raises(DigestMismatch):
        cas.put_bytes(b"actual", expected_digest="sha256:" + "0" * 64)
    assert list(cas.iter_digests()) == []


def test_materialize_shares_safely(tmp_path: Path, cas: ContentAddressableStore) -> None:
    """``auto`` must never hand out an inode shared with the canonical object."""
    digest = cas.put_bytes(b"canonical bytes")
    target = tmp_path / "out" / "file.txt"
    cas.materialize(digest, target)

    assert target.stat().st_mode & 0o777 == 0o644, "a materialised copy is writable by its owner"
    target.write_bytes(b"hostile in-place edit")
    assert cas.get_bytes(digest) == b"canonical bytes"


def test_materialize_link_mode_is_opt_in(tmp_path: Path, cas: ContentAddressableStore) -> None:
    digest = cas.put_bytes(b"immutable")
    linked = tmp_path / "linked.bin"
    cas.materialize(digest, linked, share="link")
    assert linked.stat().st_nlink >= 2
    # share="link" hands out the canonical inode, so it keeps the canonical mode.
    assert linked.stat().st_mode & 0o777 == BLOB_MODE


def test_compression_roundtrip_and_accounting(tmp_path: Path) -> None:
    store = ContentAddressableStore(tmp_path / "cache", compression="zstd")
    payload = b"x" * 200_000
    digest = store.put_bytes(payload)
    assert store.info(digest).compression == "gzip"
    assert store.info(digest).stored_size < len(payload)
    assert store.get_bytes(digest) == payload
    accounting = store.accounting()
    assert accounting["logical_bytes"] == len(payload)
    assert accounting["stored_bytes"] < accounting["logical_bytes"]


def test_scrub_reports_healthy_and_corrupt(cas: ContentAddressableStore) -> None:
    good = cas.put_bytes(b"good")
    bad = cas.put_bytes(b"bad")
    corrupt_stored_blob(cas.path_for(bad), b"broken")
    outcome = cas.scrub()
    assert good in outcome["healthy"]
    assert bad in outcome["corrupt"]


def test_missing_object_raises_not_found(cas: ContentAddressableStore) -> None:
    with pytest.raises(NotFound):
        cas.info("sha256:" + "e" * 64)


def test_restore_estimate_supports_recompute_bypass(cas: ContentAddressableStore) -> None:
    digest = cas.put_bytes(b"y" * 1_000_000)
    estimate = cas.estimate_restore(digest)
    assert estimate.size == 1_000_000
    assert estimate.cheaper_than(estimate.estimated_restore_ms + 1)
    assert not estimate.cheaper_than(estimate.estimated_restore_ms - 1)


def test_every_store_path_leaves_the_blob_read_only(tmp_path: Path, cas: ContentAddressableStore) -> None:
    """``BLOB_MODE`` is the immutability contract, so assert it on every writer.

    "An update is a new digest" only holds if a committed object cannot be
    rewritten under its own name, and the thing that enforces that on disk is
    the ``0o444`` mode ``_link_commit`` stamps on the staged file before it is
    linked into place. Every entry point that lands bytes in the store reaches
    that same commit, and this test walks all of them -- so deleting or
    loosening ``BLOB_MODE`` fails here rather than silently.

    A mode assertion, not a write attempt: ``os.stat`` reports the same bits to
    root as to anyone else, so this is meaningful under uid 0 too -- where a
    ``pytest.raises(PermissionError)`` probe would simply not fire.
    """
    assert BLOB_MODE == 0o444, "the CAS blob contract is read-only for every user"

    compressible = b"compressible payload " * 1_000
    compressed = ContentAddressableStore(tmp_path / "compressed", compression="zstd")
    from_file = tmp_path / "input.bin"
    from_file.write_bytes(b"put_file payload")

    replica = ContentAddressableStore(tmp_path / "replica")
    repaired_payload = b"payload that gets repaired"
    repaired = cas.put_bytes(repaired_payload)
    replica.put_bytes(repaired_payload)
    corrupt_stored_blob(cas.path_for(repaired), b"tampered")
    assert cas.verify(repaired) is False
    assert cas.repair_from(repaired, replica) is True

    stored = {
        # put_bytes -> _commit -> _link_commit
        "put_bytes": (cas, cas.put_bytes(b"put_bytes payload")),
        # put_document -> put_bytes
        "put_document": (cas, cas.put_document({"kind": "manifest", "n": 1})),
        # put_stream under the compression floor -> _link_commit on the staged file
        "put_stream/linked": (cas, cas.put_stream(io.BytesIO(b"put_stream payload"))),
        # put_file -> put_stream
        "put_file": (cas, cas.put_file(from_file)),
        # a large object in a store with compression on -> _maybe_compress -> _commit
        "put_bytes/compressed": (compressed, compressed.put_bytes(compressible)),
        "put_stream/compressed": (compressed, compressed.put_stream(io.BytesIO(compressible + b"!"))),
        # repair_from unlinks the quarantined object and commits fresh bytes
        "repair_from": (cas, repaired),
    }
    # Pin the branch each key claims to take, so a change in the compression
    # floor cannot quietly reroute these through the uncompressed commit.
    assert compressed.info(stored["put_bytes/compressed"][1]).compression == "gzip"
    assert compressed.info(stored["put_stream/compressed"][1]).compression == "gzip"
    assert cas.info(stored["put_stream/linked"][1]).compression == "none"

    for path_name, (store, digest) in stored.items():
        blob = store.path_for(digest)
        assert blob.exists(), path_name
        assert blob.stat().st_mode & 0o777 == BLOB_MODE, f"{path_name} stored {oct(blob.stat().st_mode)}"

    # The mirror image: a *materialised* copy is the caller's to edit, so it
    # carries the requested mode and never inherits the canonical one.
    working_copy = cas.materialize(stored["put_bytes"][1], tmp_path / "out" / "working.bin")
    assert working_copy.stat().st_mode & 0o777 == 0o644
    executable = cas.materialize(stored["put_bytes"][1], tmp_path / "out" / "tool", mode=0o755)
    assert executable.stat().st_mode & 0o777 == 0o755
