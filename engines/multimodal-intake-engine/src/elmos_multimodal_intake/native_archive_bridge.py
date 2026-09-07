"""Native ctypes bridge for archive inspection and zip-bomb guard."""

from __future__ import annotations

import ctypes
import json
from pathlib import Path
from typing import Any, Dict, Optional

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
                lib.elmos_archive_inspect.argtypes = [
                    ctypes.c_char_p,
                    ctypes.c_uint64,
                    ctypes.c_uint64,
                ]
                lib.elmos_archive_inspect.restype = ctypes.c_void_p

                lib.elmos_free_string.argtypes = [ctypes.c_void_p]
                lib.elmos_free_string.restype = None

                _NATIVE_LIB = lib
                return lib
            except Exception:
                pass
    return None


def inspect_archive_native(
    archive_path: Path | str,
    *,
    max_entries: int = 50_000,
    max_uncompressed_bytes: int = 1024 * 1024 * 1024,
) -> Optional[Dict[str, Any]]:
    lib = _load_native_library()
    if lib is None:
        return None

    path_bytes = str(Path(archive_path).resolve()).encode("utf-8")
    raw_ptr = lib.elmos_archive_inspect(
        path_bytes,
        max_entries,
        max_uncompressed_bytes,
    )
    if not raw_ptr:
        return None

    try:
        json_bytes = ctypes.string_at(raw_ptr)
        return json.loads(json_bytes.decode("utf-8"))
    finally:
        lib.elmos_free_string(raw_ptr)
