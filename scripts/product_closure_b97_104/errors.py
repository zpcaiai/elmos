#!/usr/bin/env python3
"""Exception hierarchy for Batch 97-104 Product Closure runtime."""

from __future__ import annotations


class ProductClosureError(Exception):
    """Base error for all product closure operations."""


class SkillNotFoundError(ProductClosureError):
    """Raised when a requested skill identifier is not in the registry."""


class ValidationError(ProductClosureError):
    """Raised when inputs or outputs violate closure schema or boundary."""


class SecurityViolation(ProductClosureError):
    """Raised when tenant isolation, least privilege or sandbox is breached."""


class BudgetExceeded(ProductClosureError):
    """Raised when step limit or resource quota is exhausted."""


class DeterminismViolation(ProductClosureError):
    """Raised when deterministic re-execution produces a digest mismatch."""


class GateBlockedError(ProductClosureError):
    """Raised when closure quality gate blocks certification or release."""
