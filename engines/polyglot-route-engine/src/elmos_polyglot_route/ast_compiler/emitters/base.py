"""Base emitter and type formatting helpers for target languages."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from ..ir import UniversalClass, UniversalField, UniversalMethod, UniversalModule, UniversalParam, UniversalType


class BaseEmitter(ABC):
    """Abstract base class for code emitters."""

    def __init__(self, language: str) -> None:
        self.language = language

    @abstractmethod
    def emit_module(self, module: UniversalModule) -> str:
        """Emit target source code from UniversalModule."""
        pass

    @abstractmethod
    def format_type(self, t: UniversalType) -> str:
        """Format UniversalType in target syntax."""
        pass
