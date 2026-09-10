"""Systems Memory and Ownership Lowering across C++20, Rust, ObjC, Swift, and GC runtimes."""

from __future__ import annotations

from typing import Any
from ..ir import UniversalModule, UniversalClass, UniversalField, UniversalMethod, UniversalType


class SystemsMemoryLowering:
    """Safely transitions between RAII/Ownership (C++/Rust), ARC (ObjC/Swift), and GC heap runtimes."""

    SYSTEM_LANGUAGES = {"cpp", "c++", "rust", "rs"}
    ARC_LANGUAGES = {"objc", "objective-c", "swift"}

    @classmethod
    def lower_module(cls, module: UniversalModule, source_lang: str, target_lang: str) -> UniversalModule:
        s_lang = source_lang.lower().strip()
        t_lang = target_lang.lower().strip()

        # Iterate over all classes and transform types
        for u_class in module.classes:
            for f in u_class.fields:
                f.type_info = cls._lower_type(f.type_info, s_lang, t_lang)

            for m in u_class.methods:
                m.return_type = cls._lower_type(m.return_type, s_lang, t_lang)
                for p in m.params:
                    p.type_info = cls._lower_type(p.type_info, s_lang, t_lang)

        return module

    @classmethod
    def _lower_type(cls, t: UniversalType, s_lang: str, t_lang: str) -> UniversalType:
        if t.kind == 'custom' and not t.pointer_kind:
            # Target is C++20: default custom reference types to shared_ptr if from GC
            if t_lang in ("cpp", "c++"):
                return UniversalType.shared_ptr_of(t)
            # Target is Rust: default custom reference types to Arc if from GC
            elif t_lang in ("rust", "rs"):
                return UniversalType(kind="pointer", name="Arc", element_type=t, pointer_kind="shared")
            # Target is ObjC: default to ARC strong
            elif t_lang in ("objc", "objective-c"):
                return UniversalType.arc_strong(t)
        elif t.kind == 'pointer':
            # Target is GC language (Java, C#, Go, Python, TS): unwraps smart pointer to standard reference
            if t_lang not in cls.SYSTEM_LANGUAGES and t_lang not in cls.ARC_LANGUAGES:
                return t.element_type or UniversalType.custom("Any")

        return t
