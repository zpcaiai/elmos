"""Native C-ABI bridge for high-performance Blast Radius and Graph Impact analysis."""

from __future__ import annotations

import ctypes
import json
import logging
import os
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_LIB = None
_LIB_TRIED = False


def _get_native_lib() -> ctypes.CDLL | None:
    global _LIB, _LIB_TRIED
    if _LIB_TRIED:
        return _LIB
    _LIB_TRIED = True

    repo_root = Path(__file__).resolve().parents[4]
    candidates = [
        repo_root / "native" / "rust-core" / "target" / "release" / "libelmos_native.dylib",
        repo_root / "native" / "rust-core" / "target" / "release" / "libelmos_native.so",
    ]

    for candidate in candidates:
        if candidate.is_file():
            try:
                lib = ctypes.CDLL(str(candidate))
                lib.elmos_blast_radius.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint32]
                lib.elmos_blast_radius.restype = ctypes.c_void_p
                lib.elmos_free_string.argtypes = [ctypes.c_void_p]
                lib.elmos_free_string.restype = None
                _LIB = lib
                return _LIB
            except Exception as ex:
                logger.debug("Failed to load native library from %s: %s", candidate, ex)

    return None


def fast_blast_radius(
    changed: Iterable[str],
    edges: Sequence[Mapping[str, Any]],
    max_nodes: int = 10_000,
) -> list[str] | None:
    """Compute blast radius via Rust native graph solver. Returns None if native lib unavailable."""
    lib = _get_native_lib()
    if lib is None:
        return None

    changed_list = [c for c in changed if isinstance(c, str)]
    edge_list = []
    for e in edges:
        s = e.get("source")
        t = e.get("target")
        if isinstance(s, str) and isinstance(t, str):
            edge_list.append({"source": s, "target": t})

    try:
        changed_json = json.dumps(changed_list).encode("utf-8")
        edges_json = json.dumps(edge_list).encode("utf-8")

        ptr = lib.elmos_blast_radius(changed_json, edges_json, max_nodes)
        if not ptr:
            return None

        try:
            raw = ctypes.string_at(ptr).decode("utf-8")
        finally:
            lib.elmos_free_string(ptr)

        data = json.loads(raw)
        if data.get("status") == "OK" and isinstance(data.get("affected_nodes"), list):
            return data["affected_nodes"]
    except Exception as ex:
        logger.debug("Native blast radius computation failed: %s", ex)

    return None
