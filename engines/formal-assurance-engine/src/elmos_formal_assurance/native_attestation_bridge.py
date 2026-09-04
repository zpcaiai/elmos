"""Native C-ABI bridge for high-performance SBOM Attestation and Merkle sealing."""

from __future__ import annotations

import ctypes
import json
import logging
from collections.abc import Sequence
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
                lib.elmos_attestation_sign.argtypes = [
                    ctypes.POINTER(ctypes.c_uint8),
                    ctypes.c_size_t,
                    ctypes.c_char_p,
                ]
                lib.elmos_attestation_sign.restype = ctypes.c_void_p

                lib.elmos_merkle_root.argtypes = [ctypes.c_char_p]
                lib.elmos_merkle_root.restype = ctypes.c_void_p

                lib.elmos_free_string.argtypes = [ctypes.c_void_p]
                lib.elmos_free_string.restype = None
                _LIB = lib
                return _LIB
            except Exception as ex:
                logger.debug("Failed to load native library from %s: %s", candidate, ex)

    return None


def fast_sign_attestation(payload: bytes, secret_key: str) -> dict[str, Any] | None:
    """Sign payload using Rust HMAC-SHA256 signer. Returns None on fallback."""
    lib = _get_native_lib()
    if lib is None:
        return None

    try:
        buf = (ctypes.c_uint8 * len(payload)).from_buffer_copy(payload)
        ptr = lib.elmos_attestation_sign(buf, len(payload), secret_key.encode("utf-8"))
        if not ptr:
            return None

        try:
            raw = ctypes.string_at(ptr).decode("utf-8")
        finally:
            lib.elmos_free_string(ptr)

        data = json.loads(raw)
        if data.get("status") == "OK":
            return data
    except Exception as ex:
        logger.debug("Native attestation signing failed: %s", ex)

    return None


def fast_merkle_root(digests: Sequence[str]) -> str | None:
    """Calculate Merkle root hash using Rust engine. Returns None on fallback."""
    lib = _get_native_lib()
    if lib is None:
        return None

    try:
        csv_str = ",".join(digests).encode("utf-8")
        ptr = lib.elmos_merkle_root(csv_str)
        if not ptr:
            return None

        try:
            raw = ctypes.string_at(ptr).decode("utf-8")
        finally:
            lib.elmos_free_string(ptr)

        if len(raw) == 64:
            return raw
    except Exception as ex:
        logger.debug("Native merkle root calculation failed: %s", ex)

    return None
