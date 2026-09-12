#!/usr/bin/env python3
"""Deterministic Execution Engine for Batch 97-104 Product Closure."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from scripts.product_closure_b97_104.archetypes import get_closure_archetype
from scripts.product_closure_b97_104.canonical import (
    digest,
    idempotency_key,
)
from scripts.product_closure_b97_104.errors import (
    BudgetExceeded,
    DeterminismViolation,
)


@dataclass
class ClosureJournalEntry:
    step: int
    skill_id: str
    archetype: str
    input_digest: str
    output_digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "skill_id": self.skill_id,
            "archetype": self.archetype,
            "input_digest": self.input_digest,
            "output_digest": self.output_digest,
        }


@dataclass
class ClosureExecutionJournal:
    entries: list[ClosureJournalEntry] = field(default_factory=list)

    def record(
        self, skill_id: str, archetype: str, input_payload: Any, output_data: Any
    ) -> ClosureJournalEntry:
        entry = ClosureJournalEntry(
            step=len(self.entries),
            skill_id=skill_id,
            archetype=archetype,
            input_digest=digest(input_payload),
            output_digest=digest(output_data),
        )
        self.entries.append(entry)
        return entry

    def as_list(self) -> list[dict[str, Any]]:
        return [e.as_dict() for e in self.entries]

    @property
    def journal_digest(self) -> str:
        return digest(self.as_list())


@dataclass(frozen=True)
class ClosureExecutionResult:
    skill_id: str
    archetype: str
    output_data: dict[str, Any]
    output_digest: str
    input_digest: str
    journal: list[dict[str, Any]]
    journal_digest: str
    replayed: bool = False


class ClosureDeterministicEngine:
    """Deterministic engine for product closure tasks."""

    def __init__(self, *, max_steps: int = 1000) -> None:
        self.max_steps = max_steps
        self._journal = ClosureExecutionJournal()
        self._cache: dict[str, ClosureExecutionResult] = {}

    def execute_skill(
        self, skill_id: str, archetype_name: str, payload: dict[str, Any]
    ) -> ClosureExecutionResult:
        if len(self._journal.entries) >= self.max_steps:
            raise BudgetExceeded(f"Step budget exceeded ({self.max_steps})")

        key = idempotency_key(skill_id, archetype_name, payload)
        if key in self._cache:
            cached = self._cache[key]
            return ClosureExecutionResult(
                skill_id=cached.skill_id,
                archetype=cached.archetype,
                output_data=cached.output_data,
                output_digest=cached.output_digest,
                input_digest=cached.input_digest,
                journal=self._journal.as_list(),
                journal_digest=self._journal.journal_digest,
                replayed=True,
            )

        arch = get_closure_archetype(archetype_name)
        res = arch.execute(payload)

        self._journal.record(skill_id, archetype_name, payload, res)
        out_digest = digest(res)
        in_digest = digest(payload)

        result = ClosureExecutionResult(
            skill_id=skill_id,
            archetype=archetype_name,
            output_data=res,
            output_digest=out_digest,
            input_digest=in_digest,
            journal=self._journal.as_list(),
            journal_digest=self._journal.journal_digest,
            replayed=False,
        )
        self._cache[key] = result
        return result
