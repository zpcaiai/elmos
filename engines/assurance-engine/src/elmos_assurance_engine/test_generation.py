"""Implementation of B02: Test fixtures, environments, and test generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GeneratedTestCase:
    case_id: str
    obligation_id: str
    title: str
    given: str
    when: str
    then: str
    severity: str = "critical"

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "obligation_id": self.obligation_id,
            "title": self.title,
            "given": self.given,
            "when": self.when,
            "then": self.then,
            "severity": self.severity,
        }


class TestGenerator:
    """Generates independent test cases bound to approved obligations."""

    @classmethod
    def generate_for_obligation(cls, obligation_id: str, feature_id: str) -> list[GeneratedTestCase]:
        cases = [
            GeneratedTestCase(
                case_id=f"tc:{obligation_id}:positive",
                obligation_id=obligation_id,
                title=f"Positive path validation for {feature_id}",
                given=f"Valid configuration and inputs for {feature_id}",
                when="Invoking standard operational path",
                then="Returns 200/SUCCESS and satisfies schema and side effect contracts",
            ),
            GeneratedTestCase(
                case_id=f"tc:{obligation_id}:negative",
                obligation_id=obligation_id,
                title=f"Negative authorization/boundary check for {feature_id}",
                given=f"Malformed input or cross-tenant context for {feature_id}",
                when="Invoking operation",
                then="Fails closed with appropriate error code, no unauthorized side effects",
            ),
        ]
        return cases
