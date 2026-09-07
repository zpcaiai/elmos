"""Python ctypes bridge to the native Rust mutation testing engine."""

from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

_NATIVE_LIB = None
_INIT_ATTEMPTED = False


def _find_library() -> Optional[str]:
    custom_path = os.environ.get("ELMOS_NATIVE_LIB")
    if custom_path and os.path.exists(custom_path):
        return custom_path

    repo_root = Path(__file__).resolve().parents[4]
    candidates = [
        repo_root / "native" / "rust-core" / "target" / "release" / "libelmos_native.dylib",
        repo_root / "native" / "rust-core" / "target" / "release" / "libelmos_native.so",
        repo_root / "native" / "rust-core" / "target" / "debug" / "libelmos_native.dylib",
        repo_root / "native" / "rust-core" / "target" / "debug" / "libelmos_native.so",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None


def get_native_lib():
    global _NATIVE_LIB, _INIT_ATTEMPTED
    if _NATIVE_LIB is not None:
        return _NATIVE_LIB
    if _INIT_ATTEMPTED:
        return None

    _INIT_ATTEMPTED = True
    lib_path = _find_library()
    if not lib_path:
        return None

    try:
        lib = ctypes.CDLL(lib_path)

        # void elmos_free_string(void*)
        lib.elmos_free_string.argtypes = [ctypes.c_void_p]
        lib.elmos_free_string.restype = None

        # void* elmos_mutation_evaluate(char* source)
        lib.elmos_mutation_evaluate.argtypes = [ctypes.c_char_p]
        lib.elmos_mutation_evaluate.restype = ctypes.c_void_p

        _NATIVE_LIB = lib
        return _NATIVE_LIB
    except Exception:
        return None


def is_native_available() -> bool:
    return get_native_lib() is not None


def native_evaluate_mutants(source_code: str) -> Optional[Dict[str, Any]]:
    lib = get_native_lib()
    if lib is None:
        return None

    source_bytes = source_code.encode("utf-8")
    res_ptr = lib.elmos_mutation_evaluate(source_bytes)
    if not res_ptr:
        return None

    try:
        res_str = ctypes.string_at(res_ptr).decode("utf-8")
        parsed = json.loads(res_str)
        if "error" in parsed:
            return None
        return parsed
    finally:
        lib.elmos_free_string(res_ptr)
