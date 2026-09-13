#!/usr/bin/env python3
"""Exception hierarchy for Batch 81-95 Language Packs runtime."""

from __future__ import annotations


class LanguagePackError(Exception):
    """Base error for all language pack runtime operations."""


class SkillNotFoundError(LanguagePackError):
    """Raised when a requested skill identifier is not in the registry."""


class ArchetypeNotFoundError(LanguagePackError):
    """Raised when an archetype cannot be resolved for a skill."""


class ValidationError(LanguagePackError):
    """Raised when inputs or outputs violate schema/trust boundary."""


class SecurityViolation(LanguagePackError):
    """Raised when tenant isolation, least privilege or sandbox is breached."""


class BudgetExceeded(LanguagePackError):
    """Raised when step limit or resource quota is exhausted."""


class DeterminismViolation(LanguagePackError):
    """Raised when deterministic re-execution produces a digest mismatch."""


class DifferentialMismatch(LanguagePackError):
    """Raised when target output semantically deviates from legacy source."""


class GateBlockedError(LanguagePackError):
    """Raised when quality gate blocks certification or deployment."""
