"""Async & concurrency semantic lowering — delegates to the industrial engine."""

from __future__ import annotations

class ConcurrencyLowering:
    """Harmonizes async/await, Tasks, Promises, Futures, goroutines and channels."""

    @classmethod
    def lower_module(cls, module: UniversalModule, target_language: str) -> UniversalModule:
        from elmos_polyglot_route.industrial.concurrency import ConcurrencySemanticEngine

        return ConcurrencySemanticEngine.lower_module(module, target_language)
