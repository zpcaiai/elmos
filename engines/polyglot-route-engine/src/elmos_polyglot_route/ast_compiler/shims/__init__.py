"""Standard library mapping shims across 11 enterprise languages."""

from __future__ import annotations

from .collections_shim import (
    COLLECTIONS_MAP,
    get_collection_type,
    list_add,
    list_size,
    list_contains,
    list_clear,
    map_get,
    map_put,
    map_contains_key,
    map_remove,
    set_add,
    set_contains,
)
from .datetime_shim import (
    now_iso,
    epoch_millis,
    sleep_millis,
)
from .io_shim import (
    log_info,
    log_error,
    file_read_text,
    file_write_text,
    file_exists,
    path_combine,
    http_get,
)
from .json_shim import (
    json_serialize,
    json_deserialize,
)
from .math_shim import (
    math_abs,
    math_min,
    math_max,
    math_sqrt,
    uuid_v4,
    sha256_hex,
)
from .strings_shim import (
    string_length,
    string_trim,
    string_contains,
    string_starts_with,
    string_ends_with,
    string_replace,
    string_to_lower,
    string_to_upper,
    string_split,
    string_join,
)


class ShimRegistry:
    """Unified registry and query engine for standard library shims."""

    @staticmethod
    def get_collection(kind: str, target_lang: str, elem_type: str = "string", val_type: str = "string") -> str:
        return get_collection_type(kind, target_lang, elem_type, val_type)

    @staticmethod
    def list_add(list_expr: str, item_expr: str, target_lang: str) -> str:
        return list_add(list_expr, item_expr, target_lang)

    @staticmethod
    def list_size(list_expr: str, target_lang: str) -> str:
        return list_size(list_expr, target_lang)

    @staticmethod
    def map_get(map_expr: str, key_expr: str, target_lang: str) -> str:
        return map_get(map_expr, key_expr, target_lang)

    @staticmethod
    def map_put(map_expr: str, key_expr: str, val_expr: str, target_lang: str) -> str:
        return map_put(map_expr, key_expr, val_expr, target_lang)

    @staticmethod
    def get_now_iso(target_lang: str) -> str:
        return now_iso(target_lang)

    @staticmethod
    def get_epoch_millis(target_lang: str) -> str:
        return epoch_millis(target_lang)

    @staticmethod
    def get_log_info(target_lang: str, msg_expr: str) -> str:
        return log_info(target_lang, msg_expr)

    @staticmethod
    def get_log_error(target_lang: str, msg_expr: str) -> str:
        return log_error(target_lang, msg_expr)

    @staticmethod
    def file_read(path_expr: str, target_lang: str) -> str:
        return file_read_text(path_expr, target_lang)

    @staticmethod
    def file_write(path_expr: str, content_expr: str, target_lang: str) -> str:
        return file_write_text(path_expr, content_expr, target_lang)

    @staticmethod
    def get_json_serialize(target_lang: str, expr: str) -> str:
        return json_serialize(expr, target_lang)

    @staticmethod
    def get_json_deserialize(target_lang: str, json_expr: str, type_name: str) -> str:
        return json_deserialize(json_expr, type_name, target_lang)

    @staticmethod
    def get_string_length(target_lang: str, expr: str) -> str:
        return string_length(expr, target_lang)

    @staticmethod
    def get_string_trim(target_lang: str, expr: str) -> str:
        return string_trim(expr, target_lang)

    @staticmethod
    def get_math_abs(target_lang: str, expr: str) -> str:
        return math_abs(expr, target_lang)

    @staticmethod
    def get_uuid(target_lang: str) -> str:
        return uuid_v4(target_lang)

    @staticmethod
    def get_sha256(target_lang: str, expr: str) -> str:
        return sha256_hex(expr, target_lang)


from .ui_shim import UIShimRegistry
from .system_shim import SystemShimRegistry


__all__ = [
    "COLLECTIONS_MAP",
    "get_collection_type",
    "list_add",
    "list_size",
    "list_contains",
    "list_clear",
    "map_get",
    "map_put",
    "map_contains_key",
    "map_remove",
    "set_add",
    "set_contains",
    "string_length",
    "string_trim",
    "string_contains",
    "string_starts_with",
    "string_ends_with",
    "string_replace",
    "string_to_lower",
    "string_to_upper",
    "string_split",
    "string_join",
    "math_abs",
    "math_min",
    "math_max",
    "math_sqrt",
    "uuid_v4",
    "sha256_hex",
    "json_serialize",
    "json_deserialize",
    "log_info",
    "log_error",
    "file_read_text",
    "file_write_text",
    "file_exists",
    "path_combine",
    "http_get",
    "now_iso",
    "epoch_millis",
    "sleep_millis",
    "ShimRegistry",
    "UIShimRegistry",
    "SystemShimRegistry",
]


