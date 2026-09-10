"""Systems Standards and Memory Shim Registry."""

from __future__ import annotations

from typing import Dict, Any


class SystemShimRegistry:
    """Maps system-level string, numeric, and memory constructs across C++, Rust, ObjC, Swift, and GC."""

    TYPE_MAPPINGS: Dict[str, Dict[str, str]] = {
        "string": {
            "cpp": "std::string",
            "rust": "String",
            "objc": "NSString *",
            "swift": "String",
            "csharp": "string",
            "java": "String",
            "go": "string",
            "python": "str",
            "typescript": "string",
            "vb6": "String",
            "vcpp6": "CString",
        },
        "i64": {
            "cpp": "int64_t",
            "rust": "i64",
            "objc": "NSInteger",
            "swift": "Int",
            "csharp": "long",
            "java": "long",
            "go": "int64",
            "python": "int",
            "typescript": "number",
            "vb6": "Long",
            "vcpp6": "DWORD",
        },
        "shared_ptr": {
            "cpp": "std::shared_ptr<{T}>",
            "rust": "std::sync::Arc<{T}>",
            "objc": "{T} *",
            "swift": "{T}",
            "csharp": "{T}",
            "java": "{T}",
            "go": "*{T}",
            "python": "{T}",
            "typescript": "{T}",
            "vb6": "{T}",
            "vcpp6": "{T}*",
        }
    }

    @classmethod
    def resolve_type(cls, type_key: str, target_lang: str, inner_type: str = "") -> str:
        lang = target_lang.lower().strip()
        mapping = cls.TYPE_MAPPINGS.get(type_key, {})
        tpl = mapping.get(lang, "{T}")
        return tpl.replace("{T}", inner_type) if inner_type else tpl
