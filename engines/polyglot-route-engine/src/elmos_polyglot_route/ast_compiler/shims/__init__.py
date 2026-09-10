"""Standard library mapping shims across 8 languages."""

from __future__ import annotations

from .collections_shim import get_collection_type
from .datetime_shim import now_iso
from .io_shim import log_info
from .json_shim import json_serialize
from .math_shim import math_abs
from .strings_shim import string_length, string_trim


class ShimRegistry:
    """Unified registry and query engine for standard library shims."""

    @staticmethod
    def get_collection(kind: str, target_lang: str, elem_type: str = "string", val_type: str = "string") -> str:
        return get_collection_type(kind, target_lang, elem_type, val_type)

    @staticmethod
    def get_now_iso(target_lang: str) -> str:
        return now_iso(target_lang)

    @staticmethod
    def get_log_info(target_lang: str, msg_expr: str) -> str:
        return log_info(target_lang, msg_expr)

    @staticmethod
    def get_json_serialize(target_lang: str, expr: str) -> str:
        return json_serialize(target_lang, expr)

    @staticmethod
    def get_string_length(target_lang: str, expr: str) -> str:
        return string_length(target_lang, expr)

    @staticmethod
    def get_string_trim(target_lang: str, expr: str) -> str:
        return string_trim(target_lang, expr)

    @staticmethod
    def get_math_abs(target_lang: str, expr: str) -> str:
        return math_abs(target_lang, expr)


__all__ = [
    "get_collection_type",
    "string_length",
    "string_trim",
    "math_abs",
    "json_serialize",
    "log_info",
    "now_iso",
    "ShimRegistry",
]
