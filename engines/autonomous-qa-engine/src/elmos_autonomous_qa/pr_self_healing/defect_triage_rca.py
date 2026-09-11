"""Defect Triage and Root Cause Analysis (RCA) Engine.

Analyzes test failures and compiler diagnostics to determine:
- Defect category (Syntax, Symbol, Type, Logic, Specification Drift, Flaky)
- Location of root cause (production code vs test code)
- Strategy: SAFE_CODE_FIX (fix implementation) vs TEST_SELF_HEAL (heal test oracle)
- Detailed explanation with confidence scoring
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath
import re
from typing import Any

from .scm_models import (
    DefectClassification,
    FailureCategory,
    FailureTrace,
    RepairStrategy,
)


class DefectTriageRCA:
    """Industrial RCA and triage analyzer."""

    @classmethod
    def triage_failure(
        cls,
        trace: FailureTrace,
        commit_diff: str = "",
        workspace_files: Mapping[str, str] | None = None,
    ) -> DefectClassification:
        """Triage a single failure trace and determine root cause."""
        category = trace.failure_category
        primary_file = trace.test_file
        primary_line = None
        if trace.diagnostics:
            primary_file = trace.diagnostics[0].file_path or primary_file
            primary_line = trace.diagnostics[0].line_number

        is_test_file = cls._is_test_path(primary_file)

        # Check stack trace to find non-test code if any
        prod_file = None
        prod_line = None
        for frame in reversed(trace.stack_trace):
            match = re.match(r"^([^:]+):(\d+)", frame)
            if match:
                f_path = match.group(1)
                l_no = int(match.group(2))
                if not cls._is_test_path(f_path):
                    prod_file = f_path
                    prod_line = l_no
                    break

        if prod_file and not cls._is_test_path(prod_file):
            primary_file = prod_file
            primary_line = prod_line
            is_test_file = False

        # Extract affected symbols
        affected_symbols: list[str] = []
        sym_match = re.findall(r"['\"]([A-Za-z0-9_]+)['\"]", trace.error_message)
        if sym_match:
            affected_symbols.extend(sym_match[:5])
        if trace.test_function:
            affected_symbols.append(trace.test_function)

        # Determine if this is Specification Drift (intentional change in production code)
        is_spec_drift = False
        strategy = RepairStrategy.SAFE_CODE_FIX
        confidence = 0.85
        explanation = ""

        production = cls._classify_production_defect(trace, primary_file)
        if production is not None:
            category, strategy, confidence, explanation = production
            return DefectClassification(
                category=category,
                primary_file=primary_file,
                primary_line=primary_line,
                is_test_failure_only=is_test_file,
                is_spec_drift=False,
                confidence_score=confidence,
                affected_symbols=list(set(affected_symbols)),
                recommended_strategy=strategy,
                explanation=explanation,
            )

        # Case 1: Syntax or Compiler Error
        if category in (FailureCategory.SYNTAX_ERROR, FailureCategory.IMPORT_OR_SYMBOL_ERROR):
            strategy = RepairStrategy.SAFE_CODE_FIX
            confidence = 0.95
            explanation = (
                f"Defect is a {category.value} in `{primary_file}` at line {primary_line}. "
                f"Error: {trace.error_message}. A safe code repair is required to fix the syntax/import."
            )

        # Case 2: Assertion Failure
        elif category == FailureCategory.ASSERTION_FAILURE:
            # Analyze commit diff: did the user deliberately modify production code return values?
            if commit_diff and not is_test_file and ("+" in commit_diff and "-" in commit_diff):
                # If production code changed and test expects the old value
                if trace.assertion_expected and trace.assertion_actual:
                    if trace.assertion_actual in commit_diff:
                        is_spec_drift = True
                        strategy = RepairStrategy.TEST_SELF_HEAL
                        confidence = 0.90
                        explanation = (
                            f"Specification drift detected: Production code in `{primary_file}` was intentionally updated "
                            f"yielding `{trace.assertion_actual}`, but test `{trace.test_file}` still asserts `{trace.assertion_expected}`. "
                            f"Test oracle must be healed to match new expected contract."
                        )
            if not is_spec_drift:
                if is_test_file:
                    strategy = RepairStrategy.TEST_SELF_HEAL
                    confidence = 0.80
                    explanation = f"Assertion mismatch directly in test `{primary_file}`: {trace.error_message}. Test needs healing."
                else:
                    strategy = RepairStrategy.SAFE_CODE_FIX
                    confidence = 0.85
                    explanation = (
                        f"Assertion failure caused by regression in production code `{primary_file}`: "
                        f"{trace.error_message}. Expected: {trace.assertion_expected}, Actual: {trace.assertion_actual}."
                    )

        # Case 3: Type Mismatch / Runtime Exception
        elif category in (FailureCategory.TYPE_MISMATCH, FailureCategory.RUNTIME_EXCEPTION):
            strategy = RepairStrategy.SAFE_CODE_FIX
            confidence = 0.90
            explanation = (
                f"Runtime exception `{trace.exception_class}` encountered in `{primary_file}`: "
                f"{trace.error_message}. Safe code fix required to handle types/nullability."
            )

        # Case 4: Flaky or Timeout — never heal by sleeping or weakening tests.
        elif category == FailureCategory.FLAKY_OR_TIMEOUT:
            if cls._looks_like_async_timing(trace.error_message):
                category = FailureCategory.ASYNC_TIMING
                strategy = RepairStrategy.SAFE_CODE_FIX
                confidence = 0.88
                explanation = (
                    f"Async timing defect in `{primary_file}`: {trace.error_message}. "
                    "Replace sleep barriers with event/condition waits; do not inject delays."
                )
            else:
                strategy = RepairStrategy.MANUAL_INSPECTION_REQUIRED
                confidence = 0.70
                explanation = f"Potential flaky test or timeout in `{trace.test_file}`: {trace.error_message}."

        else:
            strategy = RepairStrategy.SAFE_CODE_FIX
            confidence = 0.65
            explanation = f"General failure in `{primary_file}`: {trace.error_message}."

        return DefectClassification(
            category=category,
            primary_file=primary_file,
            primary_line=primary_line,
            is_test_failure_only=is_test_file,
            is_spec_drift=is_spec_drift,
            confidence_score=confidence,
            affected_symbols=list(set(affected_symbols)),
            recommended_strategy=strategy,
            explanation=explanation,
        )

    @staticmethod
    def _looks_like_async_timing(message: str) -> bool:
        lowered = message.lower()
        return any(token in lowered for token in ("asyncio", "timing", "sleep", "event loop", "not published"))

    @classmethod
    def _classify_production_defect(
        cls,
        trace: FailureTrace,
        primary_file: str,
    ) -> tuple[FailureCategory, RepairStrategy, float, str] | None:
        blob = " ".join(
            [
                trace.error_message,
                trace.exception_class,
                " ".join(trace.stack_trace),
                primary_file,
            ]
        ).lower()
        if any(token in blob for token in ("stale fencing", "fencing token", "stale lock", "lease expired")):
            return (
                FailureCategory.DISTRIBUTED_LOCK_FAILURE,
                RepairStrategy.SAFE_CODE_FIX,
                0.93,
                f"Distributed lock without fencing in `{primary_file}`: {trace.error_message}.",
            )
        if "database" in blob and "deadlock" in blob:
            return (
                FailureCategory.DATABASE_DEADLOCK,
                RepairStrategy.SAFE_CODE_FIX,
                0.92,
                f"Database deadlock from unordered row locks in `{primary_file}`.",
            )
        if any(token in blob for token in ("deadlock", "lock order", "circular wait")):
            return (
                FailureCategory.DEADLOCK,
                RepairStrategy.SAFE_CODE_FIX,
                0.94,
                f"Lock-order deadlock in `{primary_file}`: {trace.error_message}.",
            )
        if any(token in blob for token in ("lost update", "race condition", "shared state", "lost-update")):
            return (
                FailureCategory.RACE_CONDITION,
                RepairStrategy.SAFE_CODE_FIX,
                0.93,
                f"Shared-state race in `{primary_file}`: {trace.error_message}.",
            )
        if cls._looks_like_async_timing(blob):
            return (
                FailureCategory.ASYNC_TIMING,
                RepairStrategy.SAFE_CODE_FIX,
                0.90,
                f"Async/timing defect in `{primary_file}`: {trace.error_message}.",
            )
        return None

    @staticmethod
    def _is_test_path(path: str) -> bool:
        normalized = path.replace("\\", "/").lower()
        return (
            "/tests/" in normalized
            or "/test/" in normalized
            or normalized.startswith("tests/")
            or normalized.startswith("test/")
            or normalized.endswith("_test.py")
            or normalized.endswith("_test.go")
            or normalized.endswith(".test.ts")
            or normalized.endswith(".test.js")
            or normalized.endswith(".spec.ts")
            or normalized.endswith(".spec.js")
            or "test" in PurePosixPath(normalized).name
        )
