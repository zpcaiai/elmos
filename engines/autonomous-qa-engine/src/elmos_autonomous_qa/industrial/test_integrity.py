"""Strict-test oracle: self-healing must never weaken or skip assertions."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import re


FORBIDDEN = (
    "assert true",
    "asserttrue(true)",
    "@disabled",
    "pytest.mark.skip",
    "pytest.mark.xfail",
    "test.skip(",
    "describe.skip(",
    "unittest.skip",
    "time.sleep(",
    "asyncio.sleep(",
    "thread.sleep(",
    "quality_gate",
    "authorization_bypass",
)

_ASSERT_RE = re.compile(r"\bassert(Equal|True|False|In|NotIn|Is|IsNone|IsNotNone)?\b|\bexpect\(|\btoBe\(|\btoEqual\(")
_EQ_RE = re.compile(r"assert\s+([A-Za-z0-9_.]+)\s*==\s*(-?\d+(?:\.\d+)?)")
_BOUND_RE = re.compile(r"assert\s+([A-Za-z0-9_.]+)\s*(>=|>|<=|<)\s*(-?\d+(?:\.\d+)?)")


@dataclass(frozen=True)
class TestIntegrityReport:
    ok: bool
    before_assertions: int
    after_assertions: int
    violations: tuple[str, ...]

    @property
    def weakened(self) -> bool:
        return (not self.ok) or self.after_assertions < self.before_assertions


class TestIntegrityOracle:
    """Compares pre/post heal test (or production) source for strictness."""

    @classmethod
    def evaluate(
        cls,
        before: str,
        after: str,
        *,
        is_test: bool = True,
        allow_oracle_update: bool = False,
    ) -> TestIntegrityReport:
        violations: list[str] = []
        lowered = after.lower()
        for pattern in FORBIDDEN:
            if pattern in lowered and pattern not in before.lower():
                violations.append(f"introduced forbidden pattern: {pattern}")

        if re.search(r"\bassert\s+(?:True|1\s*==\s*1)\b", after):
            violations.append("tautological assertion")

        before_count = cls._count_assertions(before)
        after_count = cls._count_assertions(after)
        if after_count < before_count:
            violations.append(f"assertion count decreased: {before_count} -> {after_count}")

        if is_test and not allow_oracle_update:
            violations.extend(cls._bound_relaxations(before, after))

        if after.endswith(".py") or "def " in after:
            try:
                ast.parse(after)
            except SyntaxError as exc:
                violations.append(f"invalid syntax after heal: {exc}")

        return TestIntegrityReport(
            ok=not violations,
            before_assertions=before_count,
            after_assertions=after_count,
            violations=tuple(violations),
        )

    @staticmethod
    def _count_assertions(source: str) -> int:
        return len(_ASSERT_RE.findall(source))

    @staticmethod
    def _bound_relaxations(before: str, after: str) -> list[str]:
        issues: list[str] = []
        before_eq = {name: value for name, value in _EQ_RE.findall(before)}
        after_eq = {name: value for name, value in _EQ_RE.findall(after)}
        for name, value in before_eq.items():
            if name not in after_eq:
                # Equality removed or replaced with a weaker comparison.
                after_bounds = _BOUND_RE.findall(after)
                if any(row[0] == name for row in after_bounds):
                    issues.append(f"equality on {name} relaxed to inequality")
                elif f"assert {name}" in after and f"assert {name} ==" not in after:
                    issues.append(f"equality on {name} dropped")
            elif after_eq[name] != value:
                issues.append(f"expected constant for {name} changed: {value} -> {after_eq[name]}")
        return issues
