"""AI Vector and Token Packing Native Bridge.

Loads libelmos_native.dylib for SIMD vector distance, Top-K nearest neighbor search,
and BPE token counting with sliding window compaction, with pure Python fallback.
"""

from __future__ import annotations

import ctypes
import json
import math
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
                lib.elmos_vector_cosine.argtypes = [
                    ctypes.POINTER(ctypes.c_float),
                    ctypes.POINTER(ctypes.c_float),
                    ctypes.c_size_t,
                ]
                lib.elmos_vector_cosine.restype = ctypes.c_float

                lib.elmos_vector_topk.argtypes = [
                    ctypes.POINTER(ctypes.c_float),
                    ctypes.c_size_t,
                    ctypes.c_char_p,
                    ctypes.c_size_t,
                ]
                lib.elmos_vector_topk.restype = ctypes.c_char_p

                lib.elmos_token_count_estimate.argtypes = [ctypes.c_char_p]
                lib.elmos_token_count_estimate.restype = ctypes.c_int32

                lib.elmos_token_window_pack.argtypes = [
                    ctypes.c_char_p,
                    ctypes.c_size_t,
                    ctypes.c_size_t,
                    ctypes.c_size_t,
                ]
                lib.elmos_token_window_pack.restype = ctypes.c_char_p

                _NATIVE_LIB = lib
                return _NATIVE_LIB
            except Exception:
                pass
    return None


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Computes cosine similarity between two float vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0

    lib = _get_native_lib()
    if lib:
        n = len(vec_a)
        arr_a = (ctypes.c_float * n)(*vec_a)
        arr_b = (ctypes.c_float * n)(*vec_b)
        return float(lib.elmos_vector_cosine(arr_a, arr_b, n))

    # Fallback
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return max(-1.0, min(1.0, dot / (norm_a * norm_b)))


def top_k_cosine(query: List[float], candidates: List[Dict[str, Any]], k: int = 5) -> List[Dict[str, Any]]:
    """Ranks candidates by cosine similarity and returns top-k items."""
    if not query or not candidates or k <= 0:
        return []

    lib = _get_native_lib()
    if lib:
        q_len = len(query)
        q_arr = (ctypes.c_float * q_len)(*query)
        cand_json = json.dumps(candidates).encode("utf-8")
        res_ptr = lib.elmos_vector_topk(q_arr, q_len, cand_json, k)
        if res_ptr:
            raw = ctypes.string_at(res_ptr).decode("utf-8")
            return json.loads(raw)

    # Fallback
    scored = []
    for cand in candidates:
        sim = cosine_similarity(query, cand.get("embedding", []))
        scored.append({"id": cand.get("id", ""), "score": sim, "metadata": cand.get("metadata")})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:k]


def estimate_token_count(text: str) -> int:
    """Estimates BPE token count for text."""
    if not text:
        return 0

    lib = _get_native_lib()
    if lib:
        res = lib.elmos_token_count_estimate(text.encode("utf-8"))
        if res > 0:
            return int(res)

    # Fallback
    return max(1, len(text) // 4)


def sliding_window_pack(
    text: str, max_tokens: int, header_lines: int = 2, footer_lines: int = 2
) -> Dict[str, Any]:
    """Trims middle lines of long prompt/code while preserving headers and footers."""
    lib = _get_native_lib()
    if lib:
        res_ptr = lib.elmos_token_window_pack(text.encode("utf-8"), max_tokens, header_lines, footer_lines)
        if res_ptr:
            raw = ctypes.string_at(res_ptr).decode("utf-8")
            return json.loads(raw)

    # Fallback
    cur_tokens = estimate_token_count(text)
    if cur_tokens <= max_tokens:
        return {"text": text, "tokens": cur_tokens, "truncated": False}

    lines = text.splitlines()
    if len(lines) <= header_lines + footer_lines + 2:
        return {"text": text[: max_tokens * 4], "tokens": max_tokens, "truncated": True}

    header = "\n".join(lines[:header_lines])
    footer = "\n".join(lines[-footer_lines:])
    packed = f"{header}\n// ... [TRUNCATED] ...\n{footer}"
    return {"text": packed, "tokens": estimate_token_count(packed), "truncated": True}
