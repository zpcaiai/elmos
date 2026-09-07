"""Native ctypes bridge for API contract differ."""

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
                lib.elmos_contract_diff.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
                lib.elmos_contract_diff.restype = ctypes.c_void_p

                lib.elmos_free_string.argtypes = [ctypes.c_void_p]
                lib.elmos_free_string.restype = None

                _NATIVE_LIB = lib
                return lib
            except Exception:
                pass
    return None


def diff_specs_native(source_spec: Dict[str, Any], target_spec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    lib = _load_native_library()
    if lib is None:
        return None

    src_json = json.dumps(source_spec).encode("utf-8")
    tgt_json = json.dumps(target_spec).encode("utf-8")

    raw_ptr = lib.elmos_contract_diff(src_json, tgt_json)
    if not raw_ptr:
        return None

    try:
        json_bytes = ctypes.string_at(raw_ptr)
        return json.loads(json_bytes.decode("utf-8"))
    finally:
        lib.elmos_free_string(raw_ptr)
