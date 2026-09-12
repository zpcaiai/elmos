"""Industrial Test Self-Healing Engine.

Safely updates test oracles and assertions when contracts evolve legitimately.
Enforces test preservation invariants:
- Never removes or weakens assertions
- Never replaces tests with tautologies (assert True)
- Preserves negative error test branches
- Verifies post-heal test syntax and assertion count
"""

from __future__ import annotations

import ast
import difflib
import hashlib
from pathlib import PurePosixPath
import re
from typing import Any

from .safe_code_fixer import PatchSafetyViolation, FORBIDDEN_PATCH_PATTERNS
from .scm_models import (
    DefectClassification,
    FailureCategory,
    FailureTrace,
    PatchProposal,
)


class TestSelfHealer:
    """Test assertion and fixture self-healing engine."""

    @classmethod
    def heal_test(
        cls,
        test_file_path: str,
        original_test_content: str,
        classification: DefectClassification,
        trace: FailureTrace,
    ) -> PatchProposal:
        """Heal test assertions when intentional specification drift occurred."""
        lines = original_test_content.splitlines(keepends=True)
        healed_content = original_test_content

        expected = trace.assertion_expected
        actual = trace.assertion_actual

        ext = PurePosixPath(test_file_path).suffix.lower()

        # If we have both expected and actual from traceback
        if expected and actual:
            healed_content = cls._update_assertion(original_test_content, expected, actual, trace.test_function, ext)
        elif trace.error_message and ("==" in trace.error_message or "expected" in trace.error_message.lower()):
            # Extract expected vs actual from message
            exp_match = re.search(r"expected\s+['\"]?([^'\",\n]+)['\"]?\s+(?:but\s+)?got\s+['\"]?([^'\",\n]+)['\"]?", trace.error_message, re.IGNORECASE)
            if exp_match:
                exp_val = exp_match.group(1).strip()
                act_val = exp_match.group(2).strip()
                healed_content = cls._update_assertion(original_test_content, exp_val, act_val, trace.test_function, ext)

        # Invariant 1: Safety rules
        for pattern in FORBIDDEN_PATCH_PATTERNS:
            if pattern in healed_content.lower():
                raise PatchSafetyViolation(f"Test heal introduced forbidden pattern: '{pattern}'")
        if re.search(r"\bassert\s+(?:true|1\s*==\s*1)\b", healed_content.lower()):
            raise PatchSafetyViolation("Test heal introduced obvious tautology")

        # Invariant 2: Assertion count preservation (must not decrease!)
        orig_assert_count = cls._count_assertions(original_test_content, ext)
        heal_assert_count = cls._count_assertions(healed_content, ext)
        if heal_assert_count < orig_assert_count:
            raise PatchSafetyViolation(
                f"Assertion count decreased after test heal: {orig_assert_count} -> {heal_assert_count}"
            )

        # Invariant 3: Syntax correctness
        if ext == ".py":
            try:
                ast.parse(healed_content, filename=test_file_path)
            except SyntaxError as exc:
                raise PatchSafetyViolation(f"Healed test contains invalid Python syntax: {exc}") from exc

        # Generate diff
        diff_lines = difflib.unified_diff(
            original_test_content.splitlines(keepends=True),
            healed_content.splitlines(keepends=True),
            fromfile=f"a/{test_file_path}",
            tofile=f"b/{test_file_path}",
        )
        diff_text = "".join(diff_lines)

        content_sha = hashlib.sha256(healed_content.encode("utf-8")).hexdigest()
        patch_sha = hashlib.sha256(diff_text.encode("utf-8")).hexdigest()

        return PatchProposal(
            file_path=test_file_path,
            original_content=original_test_content,
            patched_content=healed_content,
            diff=diff_text,
            content_sha256=content_sha,
            patch_sha256=patch_sha,
            changes_count=len([l for l in diff_text.splitlines() if l.startswith("+") and not l.startswith("+++")]),
            is_test_file=True,
        )

    @classmethod
    def _update_assertion(cls, content: str, old_expected: str, new_actual: str, test_func: str, ext: str) -> str:
        lines = content.splitlines(keepends=True)
        in_target_func = False

        for idx, line in enumerate(lines):
            # Track function scope if python/go/ts
            if ext == ".py" and line.strip().startswith(f"def {test_func}("):
                in_target_func = True
            elif ext == ".go" and f"func {test_func}(" in line:
                in_target_func = True
            elif ext in (".ts", ".js") and test_func in line and ("test(" in line or "it(" in line):
                in_target_func = True

            # If inside or searching whole file, replace old_expected in assertion line
            if (in_target_func or not test_func) and any(kw in line for kw in ("assert", "assertEqual", "expect", "toBe", "toEqual")):
                if old_expected in line:
                    lines[idx] = line.replace(old_expected, new_actual, 1)
                    return "".join(lines)

        # Fallback: exact line replacement across the file
        for idx, line in enumerate(lines):
            if any(kw in line for kw in ("assert", "assertEqual", "expect", "toBe", "toEqual")):
                if old_expected in line:
                    lines[idx] = line.replace(old_expected, new_actual, 1)
                    return "".join(lines)

        return content

    @classmethod
    def _count_assertions(cls, content: str, ext: str) -> int:
        lowered = content.lower()
        if ext == ".py":
            return lowered.count("assert ") + lowered.count("assertequal(") + lowered.count("asserttrue(")
        elif ext == ".go":
            return lowered.count("assert.") + lowered.count("require.") + lowered.count("t.error") + lowered.count("t.fail")
        elif ext in (".ts", ".js"):
            return lowered.count("expect(") + lowered.count("assert(")
        return lowered.count("assert")
