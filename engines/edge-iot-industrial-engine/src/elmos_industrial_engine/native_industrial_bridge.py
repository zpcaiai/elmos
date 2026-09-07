"""Industrial IoT Native Bridge (Endianness and Modbus Register Decoding).

Loads libelmos_native.dylib to perform zero-allocation industrial byte swaps (ABCD, DCBA,
BADC, CDAB) and batch Modbus register decoding into scaled engineering tags.
"""

from __future__ import annotations

import ctypes
import json
import struct
from pathlib import Path
from typing import Any, Dict, List, Optional

_NATIVE_LIB: Optional[ctypes.CDLL] = None


def _get_native_lib() -> Optional[ctypes.CDLL]:
    global _NATIVE_LIB
    if _NATIVE_LIB is not None:
        return _NATIVE_LIB

    candidate_paths = [
        Path(__file__).resolve().parents[4] / "native" / "rust-core" / "target" / "release" / "libelmos_native.dylib",
        Path(__file__).resolve().parents[4] / "native" / "rust-core" / "target" / "release" / "libelmos_native.so",
    ]

    for p in candidate_paths:
        if p.exists():
            try:
                lib = ctypes.CDLL(str(p))
                lib.elmos_industrial_swap_bytes.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
                lib.elmos_industrial_swap_bytes.restype = ctypes.c_char_p

                lib.elmos_industrial_decode_registers.argtypes = [
                    ctypes.c_char_p,
                    ctypes.c_uint16,
                    ctypes.c_char_p,
                ]
                lib.elmos_industrial_decode_registers.restype = ctypes.c_char_p

                _NATIVE_LIB = lib
                return _NATIVE_LIB
            except Exception:
                pass
    return None


def swap_bytes_32(raw_hex: str, endianness: str = "ABCD") -> Dict[str, Any]:
    """Swaps 4 bytes (8 hex characters) under the specified industrial endianness."""
    lib = _get_native_lib()
    if lib:
        res_ptr = lib.elmos_industrial_swap_bytes(raw_hex.encode("utf-8"), endianness.encode("utf-8"))
        if res_ptr:
            raw = ctypes.string_at(res_ptr).decode("utf-8")
            return json.loads(raw)

    # Fallback
    b = bytes.fromhex(raw_hex)
    mode = endianness.upper()
    if mode in ("DCBA", "LITTLE"):
        swapped = bytes([b[3], b[2], b[1], b[0]])
    elif mode in ("BADC", "MID_BIG"):
        swapped = bytes([b[1], b[0], b[3], b[2]])
    elif mode in ("CDAB", "MID_LITTLE"):
        swapped = bytes([b[2], b[3], b[0], b[1]])
    else:
        swapped = b

    f_val = struct.unpack(">f", swapped)[0]
    i_val = struct.unpack(">i", swapped)[0]
    return {
        "hex": swapped.hex().upper(),
        "float32": f_val,
        "int32": i_val,
        "mode": endianness,
    }


def decode_modbus_registers(
    registers: List[int], start_addr: int, mappings: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Decodes a block of 16-bit Modbus registers into physical engineering values."""
    lib = _get_native_lib()
    if lib:
        reg_json = json.dumps(registers).encode("utf-8")
        map_json = json.dumps(mappings).encode("utf-8")
        res_ptr = lib.elmos_industrial_decode_registers(reg_json, start_addr, map_json)
        if res_ptr:
            raw = ctypes.string_at(res_ptr).decode("utf-8")
            return json.loads(raw)

    # Fallback
    results = []
    for m in mappings:
        addr = m.get("register_address", 0)
        offset = addr - start_addr
        scale = m.get("scale", 1.0)
        off = m.get("offset", 0.0)
        dt = m.get("data_type", "UINT16").upper()
        if "FLOAT" in dt and offset + 1 < len(registers):
            r0 = registers[offset]
            r1 = registers[offset + 1]
            raw_bytes = bytes([r0 >> 8, r0 & 0xFF, r1 >> 8, r1 & 0xFF])
            f_val = struct.unpack(">f", raw_bytes)[0]
            results.append({
                "tag_name": m.get("tag_name", ""),
                "raw_value": f_val,
                "engineering_value": f_val * scale + off,
                "quality": "GOOD",
            })
        elif offset < len(registers):
            val = float(registers[offset])
            results.append({
                "tag_name": m.get("tag_name", ""),
                "raw_value": val,
                "engineering_value": val * scale + off,
                "quality": "GOOD",
            })
    return results
