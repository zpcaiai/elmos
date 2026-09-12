"""Systems memory and ownership lowering — delegates to the industrial engine."""

from __future__ import annotations

class SystemsMemoryLowering:
    """Transitions between RAII/ownership, ARC, and GC heap runtimes."""

    @classmethod
    def lower_module(cls, module: UniversalModule, source_lang: str, target_lang: str) -> UniversalModule:
        from elmos_polyglot_route.industrial.ownership import OwnershipMemoryEngine

        return OwnershipMemoryEngine.lower_module(module, source_lang, target_lang)
