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
        lib.elmos_scan_project_graph.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
        lib.elmos_scan_project_graph.restype = ctypes.c_void_p
        lib.elmos_free_string.argtypes = [ctypes.c_void_p]
        lib.elmos_free_string.restype = None
        _LIB = lib
    except Exception:
        _LIB = None
    return _LIB


def native_scan_project_graph(root_path: str, max_files: int = 100000) -> dict[str, Any] | None:
    lib = _get_lib()
    if lib is None:
        return None
    try:
        ptr = lib.elmos_scan_project_graph(root_path.encode("utf-8"), max_files)
        if not ptr:
            return None
        raw_str = ctypes.string_at(ptr).decode("utf-8")
        lib.elmos_free_string(ptr)
        parsed = json.loads(raw_str)
        if isinstance(parsed, dict) and "Ok" in parsed:
            return parsed["Ok"]
        return parsed
    except Exception:
        return None
