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


def ascii_to_ebcdic(ascii_str: str) -> bytes:
    """Transcodes ASCII string to EBCDIC bytes."""
    return ascii_str.encode("cp037", errors="replace")


def comp3_decode(hex_str: str, scale: int = 0) -> str:
    """Decodes COMP-3 packed decimal hex representation e.g. '12345C' with scale 2 -> '123.45'."""
    lib = _get_native_lib()
    if lib:
        res_ptr = lib.elmos_comp3_decode(hex_str.encode("utf-8"), scale)
        if res_ptr:
            data = json.loads(ctypes.string_at(res_ptr).decode("utf-8"))
            if "value" in data:
                return str(data["value"])

    # Python fallback
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


def comp3_encode(num_str: str, scale: int, total_bytes: int) -> str:
    """Encodes decimal string e.g. '123.45' into COMP-3 hex string."""
    lib = _get_native_lib()
    if lib:
        res_ptr = lib.elmos_comp3_encode(num_str.encode("utf-8"), scale, total_bytes)
        if res_ptr:
            data = json.loads(ctypes.string_at(res_ptr).decode("utf-8"))
            if "hex" in data:
                return data["hex"]

    # Python fallback
    is_neg = False
    s = num_str.strip()
    if s.startswith("-"):
        is_neg = True
        s = s[1:]
    elif s.startswith("+"):
        s = s[1:]
    if "." in s:
        parts = s.split(".", 1)
        int_part = parts[0]
        frac_part = parts[1]
        if len(frac_part) < scale:
            frac_part = frac_part.ljust(scale, "0")
        else:
            frac_part = frac_part[:scale]
        digits = int_part + frac_part
    else:
        digits = s + ("0" * scale)
    digits = digits.lstrip("0") or "0"
    capacity = total_bytes * 2 - 1
    if len(digits) > capacity:
        raise ValueError(f"Value '{num_str}' exceeds capacity of {total_bytes} bytes ({capacity} digits)")
    padded = digits.zfill(capacity)
    sign = "D" if is_neg and digits != "0" else "C"
    return padded + sign


def parse_comp3_field(raw_bytes: bytes, offset: int, length: int, scale: int = 0) -> str:
    """Extracts and decodes a COMP-3 field from a byte buffer."""
    field_bytes = raw_bytes[offset : offset + length]
    return comp3_decode(field_bytes.hex().upper(), scale=scale)


def format_comp3_field(num_str: str, scale: int, length: int) -> bytes:
    """Formats a decimal value into COMP-3 bytes of specified byte length."""
    hex_str = comp3_encode(num_str, scale=scale, total_bytes=length)
    return bytes.fromhex(hex_str)

