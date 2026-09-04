from __future__ import annotations

import ctypes
import json
import os
import sys
from pathlib import Path
from typing import Any

_LIB = None
_TRIED_LOAD = False


def _find_library() -> Path | None:
    env_path = os.environ.get("ELMOS_NATIVE_LIB")
    if env_path and os.path.isfile(env_path):
        return Path(env_path)

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


def _get_lib():
    global _LIB, _TRIED_LOAD
    if _TRIED_LOAD:
        return _LIB
    _TRIED_LOAD = True
    lib_path = _find_library()
    if not lib_path:
        return None
    try:
        lib = ctypes.CDLL(str(lib_path))
        lib.elmos_scan_bytecode_bytes.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
        lib.elmos_scan_bytecode_bytes.restype = ctypes.c_void_p

        lib.elmos_scan_bytecode_dir.argtypes = [ctypes.c_char_p]
        lib.elmos_scan_bytecode_dir.restype = ctypes.c_void_p

        lib.elmos_shadow_diff_compare.argtypes = [ctypes.c_char_p]
        lib.elmos_shadow_diff_compare.restype = ctypes.c_void_p

        lib.elmos_free_string.argtypes = [ctypes.c_void_p]
        lib.elmos_free_string.restype = None
        _LIB = lib
    except Exception:
        _LIB = None
    return _LIB


def native_scan_bytecode_bytes(data: bytes) -> dict[str, Any] | None:
    lib = _get_lib()
    if lib is None:
        return None
    try:
        ptr = lib.elmos_scan_bytecode_bytes(data, len(data))
        if not ptr:
            return None
        raw_str = ctypes.string_at(ptr).decode("utf-8")
        lib.elmos_free_string(ptr)
        return json.loads(raw_str)
    except Exception:
        return None


def native_scan_bytecode_dir(dir_path: str) -> dict[str, Any] | None:
    lib = _get_lib()
    if lib is None:
        return None
    try:
        ptr = lib.elmos_scan_bytecode_dir(dir_path.encode("utf-8"))
        if not ptr:
            return None
        raw_str = ctypes.string_at(ptr).decode("utf-8")
        lib.elmos_free_string(ptr)
        return json.loads(raw_str)
    except Exception:
        return None


def native_shadow_diff(
    primary: dict[str, Any],
    shadow: dict[str, Any],
    ignored_headers: list[str] | None = None,
    ignored_body_fields: list[str] | None = None,
    float_tolerance: float | None = None,
) -> dict[str, Any] | None:
    lib = _get_lib()
    if lib is None:
        return None
    try:
        req = {
            "primary": primary,
            "shadow": shadow,
            "ignored_headers": ignored_headers or [],
            "ignored_body_fields": ignored_body_fields or [],
            "float_tolerance": float_tolerance,
        }
        payload = json.dumps(req).encode("utf-8")
        ptr = lib.elmos_shadow_diff_compare(payload)
        if not ptr:
            return None
        raw_str = ctypes.string_at(ptr).decode("utf-8")
        lib.elmos_free_string(ptr)
        return json.loads(raw_str)
    except Exception:
        return None
