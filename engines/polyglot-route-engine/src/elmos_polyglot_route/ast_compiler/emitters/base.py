"""Base emitter and type formatting helpers for target languages."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..ir import UniversalModule, UniversalType


class BaseEmitter(ABC):
    """Abstract base class for code emitters."""

    def __init__(self, language: str) -> None:
        self.language = language

    def emit_module(self, module: UniversalModule) -> str:
        """Emit target source by walking industrial IR statements."""
        from elmos_polyglot_route.industrial.emitter import emit_industrial_module

        return emit_industrial_module(module, self.language)

    @abstractmethod
    def format_type(self, t: UniversalType) -> str:
        """Format UniversalType in target syntax."""
        pass
