"""Implementation of B03: Mutation auditor and test suite adequacy evaluation."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from .contracts import GateDecision


@dataclass(frozen=True)
class Mutant:
    mutant_id: str
    target_rule: str
    mutation_description: str
    mutated_behavior_fn: Callable[..., Any]
    critical: bool = True


@dataclass(frozen=True)
class MutationAuditReport:
    total_mutants: int
    killed_mutants: int
    survived_mutants: int
    kill_rate: float
    verdict: GateDecision
    survived_mutant_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_mutants": self.total_mutants,
            "killed_mutants": self.killed_mutants,
            "survived_mutants": self.survived_mutants,
            "kill_rate": f"{self.kill_rate:.2%}",
            "verdict": self.verdict.value,
            "survived_mutant_ids": list(self.survived_mutant_ids),
        }


class MutationAuditor:
    """Audits whether the test suite detects domain-specific semantic mutations."""

    @classmethod
    def audit_test_suite(
        cls,
        mutants: Sequence[Mutant],
        test_evaluator: Callable[[Mutant], bool],
    ) -> MutationAuditReport:
        killed: list[str] = []
        survived: list[str] = []

        for m in mutants:
            # test_evaluator returns True if test detected and rejected the mutant (i.e. killed it)
            was_killed = test_evaluator(m)
            if was_killed:
                killed.append(m.mutant_id)
            else:
                survived.append(m.mutant_id)

        total = len(mutants)
        kill_rate = (len(killed) / total) if total > 0 else 0.0
        # If any critical mutant survived, the audit FAILS
        verdict = GateDecision.FAIL if survived else GateDecision.PASS

        return MutationAuditReport(
            total_mutants=total,
            killed_mutants=len(killed),
            survived_mutants=len(survived),
            kill_rate=kill_rate,
            verdict=verdict,
            survived_mutant_ids=tuple(survived),
        )
