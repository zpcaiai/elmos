from __future__ import annotations

import ctypes
import json
import os
import sys
from pathlib import Path
from typing import Any

_LIB: ctypes.CDLL | None = None
_TRIED_LOAD = False


def _find_library() -> Path | None:
    # 1. Environment variable override
    env_path = os.environ.get("ELMOS_NATIVE_LIB")
    if env_path and os.path.isfile(env_path):
        return Path(env_path)

    # 2. Check repo-relative location: native/rust-core/target/release
    repo_root = Path(__file__).resolve().parents[4]
    ext = "dylib" if sys.platform == "darwin" else ("dll" if sys.platform == "win32" else "so")
    candidates = [
        repo_root / "native" / "rust-core" / "target" / "release" / f"libelmos_native.{ext}",
        repo_root / "native" / "rust-core" / "target" / "debug" / f"libelmos_native.{ext}",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _get_lib() -> ctypes.CDLL | None:
    global _LIB, _TRIED_LOAD
    if _TRIED_LOAD:
        return _LIB
    _TRIED_LOAD = True
    lib_path = _find_library()
    if not lib_path:
        return None
    try:
        lib = ctypes.CDLL(str(lib_path))
        lib.elmos_sql_split.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        lib.elmos_sql_split.restype = ctypes.c_void_p
        lib.elmos_free_string.argtypes = [ctypes.c_void_p]
        lib.elmos_free_string.restype = None
        _LIB = lib
    except Exception:
        _LIB = None
    return _LIB


def native_split_statements(source: str, dialect: str | None = None) -> list[dict[str, Any]] | None:
    lib = _get_lib()
    if lib is None:
        return None
    try:
        src_bytes = source.encode("utf-8")
        dialect_bytes = dialect.encode("utf-8") if dialect else None
        ptr = lib.elmos_sql_split(src_bytes, dialect_bytes)
        if not ptr:
            return None
        raw_str = ctypes.string_at(ptr).decode("utf-8")
        lib.elmos_free_string(ptr)
        payload: object = json.loads(raw_str)
        if not isinstance(payload, list) or not all(
            isinstance(item, dict) for item in payload
        ):
            return None
        return [dict(item) for item in payload]
    except Exception:
        return None
