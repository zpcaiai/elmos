"""CAS-001..003: convergence, interruption safety and corruption handling."""

from __future__ import annotations

import io
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from elmos_build_cache.cas import ContentAddressableStore
from elmos_build_cache.errors import CorruptObject, DigestMismatch, NotFound


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
    cas.path_for(digest).write_bytes(b"tampered")

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
    cas.path_for(digest).write_bytes(b"tampered")
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

    target.chmod(0o644)
    target.write_bytes(b"hostile in-place edit")
    assert cas.get_bytes(digest) == b"canonical bytes"


def test_materialize_link_mode_is_opt_in(tmp_path: Path, cas: ContentAddressableStore) -> None:
    digest = cas.put_bytes(b"immutable")
    linked = tmp_path / "linked.bin"
    cas.materialize(digest, linked, share="link")
    assert linked.stat().st_nlink >= 2
    assert linked.stat().st_mode & 0o222 == 0


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
    cas.path_for(bad).write_bytes(b"broken")
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


def test_blobs_are_stored_read_only(cas: ContentAddressableStore) -> None:
    digest = cas.put_bytes(b"immutable payload")
    assert os.stat(cas.path_for(digest)).st_mode & 0o222 == 0
