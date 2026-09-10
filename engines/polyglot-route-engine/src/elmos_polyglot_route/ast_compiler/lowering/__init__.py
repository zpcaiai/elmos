"""Semantic lowering engine for polyglot translation."""

from __future__ import annotations

from typing import Any
from ..ir import UniversalModule
from .concurrency import ConcurrencyLowering
from .exceptions import ExceptionLowering
from .frameworks import FrameworkLowering
from .lifecycle import LifecycleLowering


class SemanticLoweringEngine:
    """Applies all 4 hazard domain lowerings to a UniversalModule."""

    @classmethod
    def lower(cls, module: UniversalModule, *args: Any, **kwargs: Any) -> UniversalModule:
        target_lang = "java"
        source_lang = ""
        if "target_language" in kwargs:
            target_lang = kwargs["target_language"]
        elif "target_lang" in kwargs:
            target_lang = kwargs["target_lang"]
        elif len(args) == 1:
            target_lang = args[0]
        elif len(args) >= 2:
            # (module, source_lang, target_lang)
            source_lang = args[0]
            target_lang = args[1]

        module = LifecycleLowering.lower_module(module, target_lang)
        module = ConcurrencyLowering.lower_module(module, target_lang)
        module = ExceptionLowering.lower_module(module, target_lang)
        module = FrameworkLowering.lower_module(module, target_lang)
        return module
