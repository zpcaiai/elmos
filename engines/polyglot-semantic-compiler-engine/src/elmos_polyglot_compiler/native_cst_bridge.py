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
        lib.elmos_cst_parse.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        lib.elmos_cst_parse.restype = ctypes.c_void_p
        lib.elmos_free_string.argtypes = [ctypes.c_void_p]
        lib.elmos_free_string.restype = None
        _LIB = lib
    except Exception:
        _LIB = None
    return _LIB


def native_parse_cst(source: str, lang: str = "java") -> dict[str, Any] | None:
    lib = _get_lib()
    if lib is None:
        return None
    try:
        ptr = lib.elmos_cst_parse(source.encode("utf-8"), lang.encode("utf-8"))
        if not ptr:
            return None
        raw_str = ctypes.string_at(ptr).decode("utf-8")
        lib.elmos_free_string(ptr)
        return json.loads(raw_str)
    except Exception:
        return None
