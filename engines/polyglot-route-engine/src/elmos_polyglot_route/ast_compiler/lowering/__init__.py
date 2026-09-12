"""Semantic lowering engine for polyglot translation across 15 enterprise languages."""

from __future__ import annotations

from typing import Any

from ..ir import UniversalModule
from .apple_concurrency import AppleConcurrencyLowering
from .concurrency import ConcurrencyLowering
from .enterprise_shims import EnterpriseShimsLowering
from .exceptions import ExceptionLowering
from .frameworks import FrameworkLowering
from .lifecycle import LifecycleLowering
from .systems_memory import SystemsMemoryLowering
from .ui_components import UIComponentLowering


class SemanticLoweringEngine:
    """Applies industrial hazard-domain lowering, then legacy shims."""

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
        if "source_lang" in kwargs:
            source_lang = kwargs["source_lang"]
        elif "source_language" in kwargs:
            source_lang = kwargs["source_language"]
        if len(args) >= 2:
            source_lang = args[0]
            target_lang = args[1]

        from elmos_polyglot_route.industrial.concurrency import ConcurrencySemanticEngine
        from elmos_polyglot_route.industrial.exceptions import ExceptionErrorEngine
        from elmos_polyglot_route.industrial.framework import FrameworkSubsetEngine
        from elmos_polyglot_route.industrial.io_ops import SystemIoEngine
        from elmos_polyglot_route.industrial.ownership import OwnershipMemoryEngine

        module = OwnershipMemoryEngine.lower_module(module, source_lang, target_lang)
        module = ConcurrencySemanticEngine.lower_module(module, target_lang)
        module = ExceptionErrorEngine.lower_module(module, target_lang)
        module = SystemIoEngine.lower_module(module, target_lang)
        module = FrameworkSubsetEngine.lower_module(module, target_lang)
        module = LifecycleLowering.lower_module(module, target_lang)
        module = ConcurrencyLowering.lower_module(module, target_lang)
        module = ExceptionLowering.lower_module(module, target_lang)
        module = FrameworkLowering.lower_module(module, target_lang)
        module = SystemsMemoryLowering.lower_module(module, source_lang, target_lang)
        module = AppleConcurrencyLowering.lower_module(module, source_lang, target_lang)
        module = UIComponentLowering.lower_module(module, source_lang, target_lang)
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
