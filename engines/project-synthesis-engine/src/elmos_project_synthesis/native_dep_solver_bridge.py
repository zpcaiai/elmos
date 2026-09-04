from __future__ import annotations

import ctypes
import json
import os
import sys
from pathlib import Path
from typing import Any, cast

_LIB: ctypes.CDLL | None = None
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
        lib.elmos_solve_dependencies.argtypes = [ctypes.c_char_p]
        lib.elmos_solve_dependencies.restype = ctypes.c_void_p
        lib.elmos_free_string.argtypes = [ctypes.c_void_p]
        lib.elmos_free_string.restype = None
        _LIB = lib
    except Exception:
        _LIB = None
    return _LIB


def native_solve_dependencies(
    root_dependencies: list[dict[str, str]],
    available_packages: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    lib = _get_lib()
    if lib is None:
        return None
    try:
        payload = json.dumps({
            "root_dependencies": root_dependencies,
            "available_packages": available_packages,
        }).encode("utf-8")
        ptr = lib.elmos_solve_dependencies(payload)
        if not ptr:
            return None
        raw_str = ctypes.string_at(ptr).decode("utf-8")
        lib.elmos_free_string(ptr)
        return cast(dict[str, Any], json.loads(raw_str))
    except Exception:
        return None
