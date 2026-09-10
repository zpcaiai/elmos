"""Semantic lowering engine for polyglot translation across 15 enterprise languages."""

from __future__ import annotations

from typing import Any
from ..ir import UniversalModule
from .concurrency import ConcurrencyLowering
from .exceptions import ExceptionLowering
from .frameworks import FrameworkLowering
from .lifecycle import LifecycleLowering
from .systems_memory import SystemsMemoryLowering
from .apple_concurrency import AppleConcurrencyLowering
from .ui_components import UIComponentLowering
from .enterprise_shims import EnterpriseShimsLowering


class SemanticLoweringEngine:
    """Applies all hazard domain, system, memory, and UI lowerings to a UniversalModule."""

    @classmethod
    def lower(cls, module: UniversalModule, *args: Any, **kwargs: Any) -> UniversalModule:
        target_lang = "java"
        source_lang = module.source_language or ""
        if "target_language" in kwargs:
            target_lang = kwargs["target_language"]
        elif "target_lang" in kwargs:
            target_lang = kwargs["target_lang"]
        elif len(args) == 1:
            target_lang = args[0]
        elif len(args) >= 2:
            source_lang = args[0]
            target_lang = args[1]

        # 1. Object graph lifecycle & GC / RAII
        module = LifecycleLowering.lower_module(module, target_lang)
        # 2. Concurrency & Async
        module = ConcurrencyLowering.lower_module(module, target_lang)
        # 3. Exception unwinding & Result/error
        module = ExceptionLowering.lower_module(module, target_lang)
        # 4. Web frameworks & REST controllers
        module = FrameworkLowering.lower_module(module, target_lang)
        # 5. Systems memory, pointers & ARC
        module = SystemsMemoryLowering.lower_module(module, source_lang, target_lang)
        # 6. Apple Concurrency (Swift / ObjC)
        module = AppleConcurrencyLowering.lower_module(module, source_lang, target_lang)
        # 7. UI components & State Machine (React / Flutter / VB6)
        module = UIComponentLowering.lower_module(module, source_lang, target_lang)
        # 8. Enterprise Standard Library, Concurrency & Stream Shims
        module = EnterpriseShimsLowering.lower_module(module, target_lang)
        return module

__all__ = [
    "SemanticLoweringEngine",
    "LifecycleLowering",
    "ConcurrencyLowering",
    "ExceptionLowering",
    "FrameworkLowering",
    "SystemsMemoryLowering",
    "AppleConcurrencyLowering",
    "UIComponentLowering",
    "EnterpriseShimsLowering",
]

