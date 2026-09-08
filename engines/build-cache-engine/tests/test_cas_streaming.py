"""Bounded storage paths must not expose bytes before verification."""
import io
from pathlib import Path

import pytest

from elmos_build_cache import native_cas_bridge
from elmos_build_cache.canonical import sha256_bytes
from elmos_build_cache.cas import CHUNK, ContentAddressableStore
from elmos_build_cache.errors import CorruptObject, DigestMismatch, QuotaExceeded


def test_compressed_stream_never_materializes_whole_file(tmp_path, monkeypatch):
    store = ContentAddressableStore(tmp_path / "cas", compression="zstd")
    payload = b"compressible" * (CHUNK // 2)
    monkeypatch.setattr(Path, "read_bytes", lambda _: pytest.fail("whole-file read"))
    digest = store.put_stream(io.BytesIO(payload))
    assert store.info(digest).compressed
    assert b"".join(store.open_stream(digest)) == payload
    destination = tmp_path / "restored"
    store.materialize(digest, destination)
    with destination.open("rb") as source:
        assert source.read() == payload


def test_no_corrupt_prefix_is_yielded(tmp_path):
    store = ContentAddressableStore(tmp_path / "cas")
    digest = store.put_stream(io.BytesIO(b"a" * (CHUNK + 20)))
    path = store.path_for(digest)
    path.chmod(0o600)
    with path.open("r+b") as source:
        source.seek(CHUNK + 19)
        source.write(b"b")
    with pytest.raises(CorruptObject):
        next(store.open_stream(digest))
    assert store.is_quarantined(digest)


def test_staging_disk_failure_does_not_quarantine_good_object(tmp_path, monkeypatch):
    store = ContentAddressableStore(tmp_path / "cas")
    digest = store.put_stream(io.BytesIO(b"valid"))

    class FullDisk(io.BytesIO):
        def write(self, data):
            raise OSError("disk full")

    monkeypatch.setattr("elmos_build_cache.cas.tempfile.TemporaryFile", lambda **_: FullDisk())
    with pytest.raises(OSError, match="disk full"):
        next(store.open_stream(digest))
    assert store.contains(digest)
    assert not store.is_quarantined(digest)


def test_native_file_descriptor_parity_and_fail_closed(tmp_path):
    if not native_cas_bridge.is_native_available():
        pytest.skip("native library not configured")
    payload = b"native fd\x00payload" * 10000
    source = tmp_path / "source"
    source.write_bytes(payload)
    store = ContentAddressableStore(tmp_path / "cas")
    with source.open("rb") as file:
        file.seek(13)
        digest = native_cas_bridge.native_put_file_descriptor(
            store.root, file.fileno(), len(payload), sha256_bytes(payload), "blob"
        )
        if digest is None:
            pytest.fail("new fd ABI must be loaded for native qualification")
        assert file.tell() == 13
        assert digest == sha256_bytes(payload)
        with pytest.raises(QuotaExceeded):
            native_cas_bridge.native_put_file_descriptor(store.root, file.fileno(), 1, None, "blob")
        with pytest.raises(DigestMismatch):
            native_cas_bridge.native_put_file_descriptor(
                store.root, file.fileno(), len(payload), sha256_bytes(b"wrong"), "blob"
            )
    assert b"".join(store.open_stream(digest)) == payload


def test_native_file_io_is_an_explicit_measured_choice(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.write_bytes(b"bounded python default")
    monkeypatch.setattr(native_cas_bridge, "native_put_file_descriptor", lambda *_: pytest.fail("implicit Rust switch"))
    store = ContentAddressableStore(tmp_path / "store")
    assert store.put_file(source) == sha256_bytes(b"bounded python default")


def test_native_bytes_is_independent_opt_in_without_python_prehash(tmp_path, monkeypatch):
    import elmos_build_cache.cas as cas_module
    payload = b"explicit measured bytes kernel"
    digest = sha256_bytes(payload)
    calls = []
    def native(root, data, expected, kind):
        calls.append((root, data, expected, kind))
        return digest
    monkeypatch.setattr(native_cas_bridge, "native_put_bytes", native)
    default = ContentAddressableStore(tmp_path / "default", native_file_io=True)
    assert default.put_bytes(payload) == digest
    assert calls == []
    monkeypatch.setattr(cas_module, "sha256_bytes", lambda *_: pytest.fail("duplicate Python hash"))
    selected = ContentAddressableStore(tmp_path / "native", native_bytes_io=True)
    assert selected.put_bytes(payload, expected_digest=digest) == digest
    assert calls == [(selected.root, payload, digest, "blob")]


def test_unavailable_selected_bytes_kernel_falls_back_but_errors_do_not(tmp_path, monkeypatch):
    from elmos_build_cache.errors import DigestMismatch
    store = ContentAddressableStore(tmp_path / "store", native_bytes_io=True)
    monkeypatch.setattr(native_cas_bridge, "native_put_bytes", lambda *_: None)
    assert store.put_bytes(b"fallback") == sha256_bytes(b"fallback")
    def reject(*_):
        raise DigestMismatch("native rejected bytes")
    monkeypatch.setattr(native_cas_bridge, "native_put_bytes", reject)
    with pytest.raises(DigestMismatch):
        store.put_bytes(b"must not publish")
    assert not store.contains(sha256_bytes(b"must not publish"))


def test_bytes_read_backend_is_independent_opt_in(tmp_path, monkeypatch):
    payload = b"explicit bytes read backend"
    store = ContentAddressableStore(tmp_path / "store", native_file_io=True)
    digest = store.put_bytes(payload)
    calls = []
    monkeypatch.setattr(native_cas_bridge, "is_native_available", lambda: True)
    def native(root, requested_digest, verify):
        calls.append((root, requested_digest, verify))
        return payload
    monkeypatch.setattr(native_cas_bridge, "native_get_bytes", native)
    assert store.get_bytes(digest) == payload
    assert calls == []
    selected = ContentAddressableStore(store.root, native_bytes_io=True)
    assert selected.get_bytes(digest) == payload
    assert calls == [(store.root, digest, True)]
    monkeypatch.setattr(native_cas_bridge, "native_get_bytes", lambda *args, **kwargs: None)
    assert selected.get_bytes(digest) == payload


@pytest.mark.parametrize("native_bytes_io", [False, True])
def test_bytes_backend_preserves_digest_dedup_quota_order(tmp_path, monkeypatch, native_bytes_io):
    from elmos_build_cache.errors import DigestMismatch, QuotaExceeded
    payload = b"previously published object"
    existing = ContentAddressableStore(tmp_path / "store")
    digest = existing.put_bytes(payload)
    store = ContentAddressableStore(existing.root, max_bytes=1, native_bytes_io=native_bytes_io)
    monkeypatch.setattr(native_cas_bridge, "native_put_bytes", lambda *_: pytest.fail("over-budget native publish"))
    assert store.put_bytes(payload) == digest
    with pytest.raises(DigestMismatch):
        store.put_bytes(payload, expected_digest="sha256:" + "0" * 64)
    with pytest.raises(QuotaExceeded):
        store.put_bytes(b"new over-budget object")
    assert not store.contains(sha256_bytes(b"new over-budget object"))


def test_native_file_writer_preserves_existing_compressed_winner(tmp_path):
    if not native_cas_bridge.is_native_available():
        pytest.skip("native library not configured")
    payload = b"compressible native race" * 10000
    store = ContentAddressableStore(tmp_path / "store", compression="gzip")
    digest = store.put_stream(io.BytesIO(payload))
    source = tmp_path / "source"
    source.write_bytes(payload)
    native_store = ContentAddressableStore(store.root, native_file_io=True)
    assert native_store.put_file(source) == digest
    assert store.info(digest).compressed
    assert b"".join(store.open_stream(digest)) == payload
