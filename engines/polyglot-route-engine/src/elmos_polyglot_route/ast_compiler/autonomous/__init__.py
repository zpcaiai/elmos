"""Autonomous diagnostic and self-repair loop for Level 4 cross-language compiler autonomy."""

from __future__ import annotations

from .compiler_diagnostics import CompilerDiagnosticParser, NativeCompilerDiagnostic
from .repair_loop import AutonomousRepairLoop, RepairFix, RepairResult
from .smt_repair import (
    SmtAutonomousRepairEngine,
    SmtBoundsAndOverflowSolver,
    SmtNullabilitySolver,
    SmtOwnershipSolver,
    SmtRepairPatch,
    SmtTypeSolver,
)

__all__ = [
    "NativeCompilerDiagnostic",
    "CompilerDiagnosticParser",
    "AutonomousRepairLoop",
    "RepairResult",
    "RepairFix",
    "SmtAutonomousRepairEngine",
    "SmtTypeSolver",
    "SmtBoundsAndOverflowSolver",
    "SmtNullabilitySolver",
    "SmtOwnershipSolver",
    "SmtRepairPatch",
]
