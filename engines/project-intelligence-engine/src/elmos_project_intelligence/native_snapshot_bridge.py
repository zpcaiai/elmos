"""Native ctypes bridge to elmos_snapshot_scan in libelmos_native.dylib."""

from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from .canonical import canonical_digest
from .contracts import EntryKind, RepositorySnapshot, Result, SecretFingerprint, SnapshotEntry, SnapshotRequest, SnapshotResult

_NATIVE_LIB: Optional[ctypes.CDLL] = None
_INIT_ATTEMPTED = False


def _load_native_library() -> Optional[ctypes.CDLL]:
    global _NATIVE_LIB, _INIT_ATTEMPTED
    if _INIT_ATTEMPTED:
        return _NATIVE_LIB
    _INIT_ATTEMPTED = True

    repo_root = Path(__file__).resolve().parents[4]
    candidates = [
        repo_root / "native/rust-core/target/release/libelmos_native.dylib",
        repo_root / "native/rust-core/target/debug/libelmos_native.dylib",
        repo_root / "native/rust-core/target/release/libelmos_native.so",
    ]

    for path in candidates:
        if path.is_file():
            try:
                lib = ctypes.CDLL(str(path))
                # Configure signatures
                lib.elmos_snapshot_scan.argtypes = [
                    ctypes.c_char_p,
                    ctypes.c_uint64,
                    ctypes.c_uint64,
                    ctypes.c_uint64,
                    ctypes.c_bool,
                ]
                lib.elmos_snapshot_scan.restype = ctypes.c_void_p

                lib.elmos_free_string.argtypes = [ctypes.c_void_p]
                lib.elmos_free_string.restype = None

                _NATIVE_LIB = lib
                return lib
            except Exception:
                pass
    return None


def scan_repository_native(request: SnapshotRequest, *, include_text: bool = False) -> Optional[SnapshotResult]:
    lib = _load_native_library()
    if lib is None:
        return None

    root_bytes = str(Path(str(request.root)).resolve()).encode("utf-8")
    limits = request.limits

    raw_ptr = lib.elmos_snapshot_scan(
        root_bytes,
        limits.max_files,
        limits.max_total_bytes,
        limits.max_file_bytes,
        include_text,
    )
    if not raw_ptr:
        return None

    try:
        json_bytes = ctypes.string_at(raw_ptr)
        data = json.loads(json_bytes.decode("utf-8"))
    finally:
        lib.elmos_free_string(raw_ptr)

    if not data.get("ok"):
        err = data.get("error", "native scan failed")
        return Result.failure(code="SNAPSHOT_ERROR", message=err)

    entries = []
    for raw_e in data.get("entries", []):
        fps = tuple(
            SecretFingerprint(
                kind=fp["kind"],
                fingerprint=fp["fingerprint"],
                occurrences=fp["occurrences"],
            )
            for fp in raw_e.get("secret_fingerprints", [])
        )
        kind = EntryKind.FILE if raw_e["kind"] == "file" else EntryKind.SYMLINK
        size = raw_e["size_bytes"]
        mode = 0o644 if kind is EntryKind.FILE else 0o777
        mtime_ns = 0
        content_digest = raw_e["sha256"]
        meta_digest = canonical_digest({
            "kind": kind.value,
            "size": size,
            "mode": mode,
            "mtime_ns": mtime_ns,
        })
        entries.append(
            SnapshotEntry(
                path=raw_e["path"],
                kind=kind,
                size=size,
                mode=mode,
                mtime_ns=mtime_ns,
                content_digest=content_digest,
                metadata_digest=meta_digest,
                secret_fingerprints=fps if kind is EntryKind.FILE else (),
                text=raw_e.get("text"),
            )
        )

    root_label = Path(request.root).name or "root"
    snapshot = RepositorySnapshot(
        tenant_id=request.tenant_id,
        project_id=request.project_id,
        run_id=request.run_id,
        root_label=root_label,
        entries=tuple(entries),
        file_count=data.get("file_count", 0),
        symlink_count=data.get("symlink_count", 0),
        total_bytes=data.get("total_bytes", 0),
        exclusions=request.exclusions,
        snapshot_digest=data.get("snapshot_digest", "sha256:" + ("0" * 64)),
    )

    return Result.success(snapshot)
