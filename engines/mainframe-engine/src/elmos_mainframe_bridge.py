"""Mainframe Native Bridge (EBCDIC & COMP-3 Packed Decimal).

Loads libelmos_native.dylib to perform ultra-fast SIMD EBCDIC transcoding
and zero-allocation COMP-3 packed decimal encoding/decoding, with Python fallback.
"""

from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

_NATIVE_LIB: Optional[ctypes.CDLL] = None


def _get_native_lib() -> Optional[ctypes.CDLL]:
    global _NATIVE_LIB
    if _NATIVE_LIB is not None:
        return _NATIVE_LIB

    candidate_paths = [
        Path(__file__).resolve().parents[3] / "native" / "rust-core" / "target" / "release" / "libelmos_native.dylib",
        Path(__file__).resolve().parents[3] / "native" / "rust-core" / "target" / "release" / "libelmos_native.so",
    ]

    for p in candidate_paths:
        if p.exists():
            try:
                lib = ctypes.CDLL(str(p))
                lib.elmos_ebcdic_to_ascii.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t]
                lib.elmos_ebcdic_to_ascii.restype = ctypes.c_char_p

                lib.elmos_comp3_decode.argtypes = [ctypes.c_char_p, ctypes.c_uint32]
                lib.elmos_comp3_decode.restype = ctypes.c_char_p

                lib.elmos_comp3_encode.argtypes = [ctypes.c_char_p, ctypes.c_uint32, ctypes.c_size_t]
                lib.elmos_comp3_encode.restype = ctypes.c_char_p

                _NATIVE_LIB = lib
                return _NATIVE_LIB
            except Exception:
                pass
    return None


def ebcdic_to_ascii(ebcdic_bytes: bytes) -> str:
    """Transcodes EBCDIC bytes to ASCII string."""
    lib = _get_native_lib()
    if lib:
        buf = (ctypes.c_uint8 * len(ebcdic_bytes))(*ebcdic_bytes)
        res_ptr = lib.elmos_ebcdic_to_ascii(buf, len(ebcdic_bytes))
        if res_ptr:
            return ctypes.string_at(res_ptr).decode("utf-8", errors="replace")

    # Python fallback via cp037 codec
    return ebcdic_bytes.decode("cp037", errors="replace")


def comp3_decode(hex_str: str, scale: int = 0) -> str:
    """Decodes COMP-3 packed decimal hex representation e.g. '12345C' with scale 2 -> '123.45'."""
    lib = _get_native_lib()
    if lib:
        res_ptr = lib.elmos_comp3_decode(hex_str.encode("utf-8"), scale)
        if res_ptr:
            data = json.loads(ctypes.string_at(res_ptr).decode("utf-8"))
            if "value" in data:
                return str(data["value"])

    # Fallback
    raw = bytes.fromhex(hex_str)
    digits = []
    is_neg = False
    for i, b in enumerate(raw):
        hi = (b >> 4) & 0x0F
        lo = b & 0x0F
        if i < len(raw) - 1:
            digits.extend([str(hi), str(lo)])
        else:
            digits.append(str(hi))
            if lo in (0x0D, 0x0B):
                is_neg = True
    core = "".join(digits).lstrip("0") or "0"
    if scale > 0:
        core = core.zfill(scale + 1)
        res = f"{core[:-scale]}.{core[-scale:]}"
    else:
        res = core
    return f"-{res}" if is_neg and res != "0" else res


def comp3_encode(num_str: str, scale: int, total_bytes: usize) -> str:
    """Encodes decimal string e.g. '123.45' into COMP-3 hex string."""
    lib = _get_native_lib()
    if lib:
        res_ptr = lib.elmos_comp3_encode(num_str.encode("utf-8"), scale, total_bytes)
        if res_ptr:
            data = json.loads(ctypes.string_at(res_ptr).decode("utf-8"))
            if "hex" in data:
                return data["hex"]

    raise NotImplementedError("comp3_encode fallback requires native core")
