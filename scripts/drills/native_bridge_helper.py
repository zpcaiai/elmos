"""Unified Native Bridge Helper for Architecture Drills.

Provides direct access to all C-ABI functions exported by libelmos_native.dylib,
along with pure Python fallback implementations for benchmarking and resilience drills.
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LIB_PATH = REPO_ROOT / "native" / "rust-core" / "target" / "release" / "libelmos_native.dylib"

_LIB: Optional[ctypes.CDLL] = None
_LIB_LOADED = False

def get_lib() -> Optional[ctypes.CDLL]:
    global _LIB, _LIB_LOADED
    if _LIB_LOADED:
        return _LIB
    if LIB_PATH.exists():
        try:
            lib = ctypes.CDLL(str(LIB_PATH))
            # Memory Management
            lib.elmos_free_string.argtypes = [ctypes.c_void_p]
            lib.elmos_free_string.restype = None

            # SQL Split
            lib.elmos_sql_split.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
            lib.elmos_sql_split.restype = ctypes.c_void_p

            # Data Reconciler
            lib.elmos_reconcile_rows.argtypes = [ctypes.c_char_p]
            lib.elmos_reconcile_rows.restype = ctypes.c_void_p

            # Dependency Solver
            lib.elmos_solve_dependencies.argtypes = [ctypes.c_char_p]
            lib.elmos_solve_dependencies.restype = ctypes.c_void_p

            # Mainframe: EBCDIC
            lib.elmos_ebcdic_to_ascii.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t]
            lib.elmos_ebcdic_to_ascii.restype = ctypes.c_void_p

            # Mainframe: COMP-3
            lib.elmos_comp3_decode.argtypes = [ctypes.c_char_p, ctypes.c_uint32]
            lib.elmos_comp3_decode.restype = ctypes.c_void_p

            lib.elmos_comp3_encode.argtypes = [ctypes.c_char_p, ctypes.c_uint32, ctypes.c_size_t]
            lib.elmos_comp3_encode.restype = ctypes.c_void_p

            # AI Vector: Cosine
            lib.elmos_vector_cosine.argtypes = [
                ctypes.POINTER(ctypes.c_float),
                ctypes.POINTER(ctypes.c_float),
                ctypes.c_size_t,
            ]
            lib.elmos_vector_cosine.restype = ctypes.c_float

            # AI Vector: Top-K
            lib.elmos_vector_topk.argtypes = [
                ctypes.POINTER(ctypes.c_float),
                ctypes.c_size_t,
                ctypes.c_char_p,
                ctypes.c_size_t,
            ]
            lib.elmos_vector_topk.restype = ctypes.c_void_p

            # AI Vector: Token Count
            lib.elmos_token_count_estimate.argtypes = [ctypes.c_char_p]
            lib.elmos_token_count_estimate.restype = ctypes.c_int32

            # AI Vector: Sliding Window Pack
            lib.elmos_token_window_pack.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_size_t]
            lib.elmos_token_window_pack.restype = ctypes.c_void_p

            # Industrial: Swap Bytes
            lib.elmos_industrial_swap_bytes.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
            lib.elmos_industrial_swap_bytes.restype = ctypes.c_void_p

            # Industrial: Decode Registers
            lib.elmos_industrial_decode_registers.argtypes = [ctypes.c_char_p, ctypes.c_uint16, ctypes.c_char_p]
            lib.elmos_industrial_decode_registers.restype = ctypes.c_void_p

            # Blast Radius: (changed_json, edges_json, max_nodes)
            lib.elmos_blast_radius.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint32]
            lib.elmos_blast_radius.restype = ctypes.c_void_p

            # Attestation Core: (payload_bytes, payload_len, secret_key)
            lib.elmos_attestation_sign.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t, ctypes.c_char_p]
            lib.elmos_attestation_sign.restype = ctypes.c_void_p

            # Attestation Core: Merkle Root
            lib.elmos_merkle_root.argtypes = [ctypes.c_char_p]
            lib.elmos_merkle_root.restype = ctypes.c_void_p

            _LIB = lib
        except Exception as e:
            print(f"Warning: Failed to load native library at {LIB_PATH}: {e}", file=sys.stderr)
            _LIB = None
    _LIB_LOADED = True
    return _LIB

# ----------------------------------------------------------------------
# 1. SQL Splitter
# ----------------------------------------------------------------------
def native_sql_split(sql: str, dialect: Optional[str] = None) -> List[Dict[str, Any]]:
    lib = get_lib()
    if not lib:
        return python_sql_split(sql, dialect)
    
    sql_b = sql.encode("utf-8")
    dia_b = dialect.encode("utf-8") if dialect else None
    ptr = lib.elmos_sql_split(sql_b, dia_b)
    if not ptr:
        return []
    try:
        raw = ctypes.cast(ptr, ctypes.c_char_p).value.decode("utf-8")
        return json.loads(raw)
    finally:
        lib.elmos_free_string(ptr)

def python_sql_split(sql: str, dialect: Optional[str] = None) -> List[Dict[str, Any]]:
    statements = []
    current = []
    in_single = False
    in_double = False
    for char in sql:
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == ';' and not in_single and not in_double:
            stmt = "".join(current).strip()
            if stmt:
                statements.append({"text": stmt, "start_line": 1})
            current = []
            continue
        current.append(char)
    last = "".join(current).strip()
    if last:
        statements.append({"text": last, "start_line": 1})
    return statements

# ----------------------------------------------------------------------
# 2. Mainframe EBCDIC & COMP-3
# ----------------------------------------------------------------------
def native_ebcdic_to_ascii(data: bytes) -> str:
    lib = get_lib()
    if not lib:
        return python_ebcdic_to_ascii(data)
    
    c_arr = (ctypes.c_uint8 * len(data)).from_buffer_copy(data)
    ptr = lib.elmos_ebcdic_to_ascii(c_arr, len(data))
    if not ptr:
        return ""
    try:
        return ctypes.cast(ptr, ctypes.c_char_p).value.decode("utf-8", errors="replace")
    finally:
        lib.elmos_free_string(ptr)

def python_ebcdic_to_ascii(data: bytes) -> str:
    try:
        return data.decode("cp037", errors="replace")
    except Exception:
        return data.decode("latin1", errors="replace")

def native_comp3_decode(hex_str: str, scale: int = 0) -> str:
    lib = get_lib()
    if not lib:
        return python_comp3_decode(hex_str, scale)
    
    clean_hex = hex_str.strip()
    if len(clean_hex) % 2 != 0:
        clean_hex = "0" + clean_hex

    ptr = lib.elmos_comp3_decode(clean_hex.encode("utf-8"), scale)
    if not ptr:
        return "0"
    try:
        data = json.loads(ctypes.cast(ptr, ctypes.c_char_p).value.decode("utf-8"))
        return str(data.get("value", "0"))
    finally:
        lib.elmos_free_string(ptr)

def python_comp3_decode(hex_str: str, scale: int = 0) -> str:
    clean_hex = hex_str.strip()
    if len(clean_hex) % 2 != 0:
        clean_hex = "0" + clean_hex
    try:
        raw = bytes.fromhex(clean_hex)
    except Exception:
        return "0"
    if not raw:
        return "0"
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

def native_comp3_encode(num_str: str, scale: int = 0, total_bytes: int = 4) -> str:
    lib = get_lib()
    if not lib:
        return python_comp3_encode(num_str, scale, total_bytes)
    
    ptr = lib.elmos_comp3_encode(num_str.encode("utf-8"), scale, total_bytes)
    if not ptr:
        return ""
    try:
        data = json.loads(ctypes.cast(ptr, ctypes.c_char_p).value.decode("utf-8"))
        return data.get("hex", "")
    finally:
        lib.elmos_free_string(ptr)

def python_comp3_encode(num_str: str, scale: int = 0, total_bytes: int = 4) -> str:
    clean = num_str.replace("-", "").replace(".", "")
    is_neg = num_str.startswith("-")
    sign = "D" if is_neg else "C"
    needed_digits = total_bytes * 2 - 1
    padded = clean.zfill(needed_digits) + sign
    if len(padded) % 2 != 0:
        padded = "0" + padded
    return padded

# ----------------------------------------------------------------------
# 3. AI Vector Operations
# ----------------------------------------------------------------------
def native_cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    lib = get_lib()
    if not lib or len(vec_a) != len(vec_b) or len(vec_a) == 0:
        return python_cosine_similarity(vec_a, vec_b)
    
    n = len(vec_a)
    arr_a = (ctypes.c_float * n)(*vec_a)
    arr_b = (ctypes.c_float * n)(*vec_b)
    return float(lib.elmos_vector_cosine(arr_a, arr_b, n))

def python_cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    if not vec_a or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(x * y for x, y in zip(vec_a, vec_b))
    norm_a = sum(x * x for x in vec_a) ** 0.5
    norm_b = sum(y * y for y in vec_b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)

def native_top_k_cosine(query: List[float], candidates: List[Dict[str, Any]], k: int = 5) -> List[Dict[str, Any]]:
    lib = get_lib()
    if not lib:
        return python_top_k_cosine(query, candidates, k)
    
    dim = len(query)
    if dim == 0 or not candidates:
        return []
    
    # Format candidates as VectorItem { id, embedding, metadata }
    formatted = []
    for cand in candidates:
        formatted.append({
            "id": cand.get("id", ""),
            "embedding": cand.get("vector") or cand.get("embedding") or [],
            "metadata": cand.get("metadata"),
        })
    
    q_arr = (ctypes.c_float * dim)(*query)
    c_json = json.dumps(formatted).encode("utf-8")
    
    ptr = lib.elmos_vector_topk(q_arr, dim, c_json, k)
    if not ptr:
        return []
    try:
        raw = ctypes.cast(ptr, ctypes.c_char_p).value.decode("utf-8")
        return json.loads(raw)
    finally:
        lib.elmos_free_string(ptr)

def python_top_k_cosine(query: List[float], candidates: List[Dict[str, Any]], k: int = 5) -> List[Dict[str, Any]]:
    scored = []
    for cand in candidates:
        vec = cand.get("vector") or cand.get("embedding") or []
        score = python_cosine_similarity(query, vec)
        scored.append({
            "id": cand.get("id", ""),
            "score": score,
            "metadata": cand.get("metadata"),
        })
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:k]

# ----------------------------------------------------------------------
# 4. Industrial Endianness & Modbus
# ----------------------------------------------------------------------
def native_swap_bytes(hex_str: str, mode: str) -> Dict[str, Any]:
    lib = get_lib()
    if not lib:
        return python_swap_bytes(hex_str, mode)
    
    ptr = lib.elmos_industrial_swap_bytes(hex_str.encode("utf-8"), mode.encode("utf-8"))
    if not ptr:
        return {}
    try:
        raw = ctypes.cast(ptr, ctypes.c_char_p).value.decode("utf-8")
        return json.loads(raw)
    finally:
        lib.elmos_free_string(ptr)

def python_swap_bytes(hex_str: str, mode: str) -> Dict[str, Any]:
    import struct
    try:
        b = bytes.fromhex(hex_str)
        if len(b) != 4:
            return {"error": "must be 4 bytes"}
    except Exception as e:
        return {"error": str(e)}
    
    b0, b1, b2, b3 = b[0], b[1], b[2], b[3]
    m = mode.upper()
    if m in ("ABCD", "BIG"):
        swapped = bytes([b0, b1, b2, b3])
    elif m in ("DCBA", "LITTLE"):
        swapped = bytes([b3, b2, b1, b0])
    elif m in ("BADC", "MID_BIG", "BYTE_SWAP"):
        swapped = bytes([b1, b0, b3, b2])
    elif m in ("CDAB", "MID_LITTLE", "WORD_SWAP"):
        swapped = bytes([b2, b3, b0, b1])
    else:
        swapped = b
    
    f32_val = struct.unpack(">f", swapped)[0]
    i32_val = struct.unpack(">i", swapped)[0]
    return {
        "hex": swapped.hex().upper(),
        "float32": f32_val,
        "int32": i32_val,
        "mode": mode,
    }

# ----------------------------------------------------------------------
# 5. Blast Radius Traversal
# ----------------------------------------------------------------------
def native_blast_radius(graph: Any, entry_nodes: List[str], max_nodes: int = 500) -> Dict[str, Any]:
    lib = get_lib()
    if not lib:
        return python_blast_radius(graph, entry_nodes, max_nodes)
    
    # Convert graph to List[{"source": ..., "target": ...}]
    edge_list = []
    if isinstance(graph, dict):
        for src, targets in graph.items():
            for tgt in targets:
                edge_list.append({"source": str(src), "target": str(tgt)})
    elif isinstance(graph, list):
        edge_list = graph

    changed_json = json.dumps(entry_nodes).encode("utf-8")
    edges_json = json.dumps(edge_list).encode("utf-8")
    ptr = lib.elmos_blast_radius(changed_json, edges_json, max_nodes)
    if not ptr:
        return {"affected_nodes": [], "node_count": 0, "truncated": False, "risk_level": "LOW"}
    try:
        raw = ctypes.cast(ptr, ctypes.c_char_p).value.decode("utf-8")
        return json.loads(raw)
    finally:
        lib.elmos_free_string(ptr)

def python_blast_radius(graph: Dict[str, List[str]], entry_nodes: List[str], max_nodes: int = 500) -> Dict[str, Any]:
    from collections import deque
    visited = set()
    queue = deque(entry_nodes)
    for n in entry_nodes:
        visited.add(n)
    while queue and len(visited) < max_nodes:
        curr = queue.popleft()
        for neighbor in graph.get(curr, []):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
    count = len(visited)
    risk = "LOW" if count < 5 else "MEDIUM" if count < 20 else "HIGH" if count < 50 else "CRITICAL"
    return {
        "affected_nodes": list(visited),
        "node_count": count,
        "truncated": len(visited) >= max_nodes,
        "risk_level": risk,
    }

# ----------------------------------------------------------------------
# 6. Attestation Core
# ----------------------------------------------------------------------
def native_attestation_sign(key: str, data: str) -> Dict[str, Any]:
    lib = get_lib()
    if not lib:
        import hmac, hashlib
        sig = hmac.new(key.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).hexdigest()
        return {"signature": sig, "algorithm": "HMAC-SHA256"}
    
    data_b = data.encode("utf-8")
    c_arr = (ctypes.c_uint8 * len(data_b))(*data_b)
    ptr = lib.elmos_attestation_sign(c_arr, len(data_b), key.encode("utf-8"))
    if not ptr:
        return {}
    try:
        raw = ctypes.cast(ptr, ctypes.c_char_p).value.decode("utf-8")
        return json.loads(raw)
    finally:
        lib.elmos_free_string(ptr)

def native_merkle_root(leaf_hashes: List[str]) -> str:
    lib = get_lib()
    if not lib:
        import hashlib
        if not leaf_hashes:
            return hashlib.sha256(b"").hexdigest()
        curr = list(leaf_hashes)
        while len(curr) > 1:
            nxt = []
            for i in range(0, len(curr), 2):
                h1 = curr[i]
                h2 = curr[i+1] if i + 1 < len(curr) else h1
                combined = hashlib.sha256(f"{h1}{h2}".encode("utf-8")).hexdigest()
                nxt.append(combined)
            curr = nxt
        return curr[0]
    
    csv_bytes = ",".join(leaf_hashes).encode("utf-8")
    ptr = lib.elmos_merkle_root(csv_bytes)
    if not ptr:
        return ""
    try:
        return ctypes.cast(ptr, ctypes.c_char_p).value.decode("utf-8")
    finally:
        lib.elmos_free_string(ptr)
