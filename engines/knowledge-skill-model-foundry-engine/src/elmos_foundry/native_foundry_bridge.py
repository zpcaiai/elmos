"""Native ctypes bridge for foundry skill graph dependency resolution."""

from __future__ import annotations

import ctypes
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

_NATIVE_LIB: Optional[ctypes.CDLL] = None
_INIT_ATTEMPTED = False
_CATALOG_INITIALIZED = False


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
                lib.elmos_foundry_init_catalog.argtypes = [ctypes.c_char_p]
                lib.elmos_foundry_init_catalog.restype = ctypes.c_int32

                lib.elmos_foundry_resolve_dependencies.argtypes = [ctypes.c_char_p]
                lib.elmos_foundry_resolve_dependencies.restype = ctypes.c_void_p

                lib.elmos_free_string.argtypes = [ctypes.c_void_p]
                lib.elmos_free_string.restype = None

                _NATIVE_LIB = lib
                return lib
            except Exception:
                pass
    return None


def init_catalog_native(catalog_data: str | bytes | Path) -> int:
    global _CATALOG_INITIALIZED
    lib = _load_native_library()
    if lib is None:
        return -1

    if isinstance(catalog_data, Path):
        json_bytes = catalog_data.read_bytes()
    elif isinstance(catalog_data, str):
        json_bytes = catalog_data.encode("utf-8")
    else:
        json_bytes = catalog_data

    code = lib.elmos_foundry_init_catalog(json_bytes)
    if code > 0:
        _CATALOG_INITIALIZED = True
    return code


def resolve_dependencies_native(skill_name: str) -> Optional[List[str]]:
    lib = _load_native_library()
    if lib is None or not _CATALOG_INITIALIZED:
        return None

    raw_ptr = lib.elmos_foundry_resolve_dependencies(skill_name.encode("utf-8"))
    if not raw_ptr:
        return None

    try:
        json_bytes = ctypes.string_at(raw_ptr)
        return json.loads(json_bytes.decode("utf-8"))
    finally:
        lib.elmos_free_string(raw_ptr)
