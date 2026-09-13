from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from elmos_polyglot_route import pipeline
from elmos_polyglot_route.models import RouteError


def _transport_fixture(root: Path) -> list[dict[str, object]]:
    (root / "assembled").mkdir()
    (root / "assembled" / "assembly-manifest.json").write_text("{}")
    (root / "large.data").write_bytes(bytes(range(256)) * 16384)
    (root / pipeline.ARTIFACT_MANIFEST_NAME).write_text(json.dumps({"transport_test": True}))
    return [
        {"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size,
         "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in sorted(root.rglob("*")) if path.is_file()
    ]


def test_streaming_transport_preserves_exact_legacy_zip_bytes(tmp_path: Path, monkeypatch) -> None:
    entries = _transport_fixture(tmp_path)
    baseline = io.BytesIO()
    with zipfile.ZipFile(baseline, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for entry in sorted(entries, key=lambda item: item["path"]):
            info = zipfile.ZipInfo(str(entry["path"]), date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, (tmp_path / str(entry["path"])).read_bytes())
    # Transport-only fixture; the real semantic closure has a separate suite.
    monkeypatch.setattr(pipeline, "verify_archived_assembly_closure", lambda *args, **kwargs: {})
    monkeypatch.setattr(pipeline, "_bound_artifact_bytes", lambda *args: pytest.fail("whole source read"))
    original_read = zipfile.ZipFile.read
    def read(self, name, *args, **kwargs):
        assert name != "large.data", "large member must be streamed, never bundle.read"
        return original_read(self, name, *args, **kwargs)
    monkeypatch.setattr(zipfile.ZipFile, "read", read)
    archive, size, digest = pipeline._write_deterministic_zip(tmp_path, entries, "python")
    assert archive.read_bytes() == baseline.getvalue()
    assert size == len(baseline.getvalue())
    assert digest == hashlib.sha256(baseline.getvalue()).hexdigest()


def test_source_mutation_before_archive_cannot_publish(tmp_path: Path, monkeypatch) -> None:
    entries = _transport_fixture(tmp_path)
    (tmp_path / "large.data").write_bytes(b"changed")
    monkeypatch.setattr(pipeline, "verify_archived_assembly_closure", lambda *args, **kwargs: {})
    with pytest.raises(RouteError, match="DESCRIPTOR_MISMATCH"):
        pipeline._write_deterministic_zip(tmp_path, entries, "python")
    assert not (tmp_path / pipeline.ARTIFACT_NAME).exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_published_archive_replacement_is_rejected(tmp_path: Path, monkeypatch) -> None:
    entries = _transport_fixture(tmp_path)
    def replace_archive(*args, **kwargs):
        archive = tmp_path / pipeline.ARTIFACT_NAME
        replacement = tmp_path / "replacement"
        replacement.write_bytes(archive.read_bytes())
        replacement.replace(archive)
    monkeypatch.setattr(pipeline, "verify_archived_assembly_closure", replace_archive)
    with pytest.raises(RouteError, match="ARCHIVE_CHANGED_DURING_READ"):
        pipeline._write_deterministic_zip(tmp_path, entries, "python")
    assert not (tmp_path / pipeline.ARTIFACT_NAME).exists()
