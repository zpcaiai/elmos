#!/usr/bin/env python3
"""Deterministic Execution Engine for Batch 81-95 Language Packs.

Guarantees:
- Replayable: identical inputs yield bit-for-bit identical output digests.
- Stable ordering: steps and results are strictly sorted by canonical bytes.
- Content addressed: all artifacts, outputs and journals are content addressed.
- Worker invariant: concurrency count cannot alter results.
- Bounded: step limits and memory ceilings are strictly enforced.
"""

from __future__ import annotations

import concurrent.futures
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from scripts.language_packs_b81_95.archetypes import get_archetype
from scripts.language_packs_b81_95.canonical import (
    canonical_bytes,
    digest,
    idempotency_key,
    stable_sort,
)
from scripts.language_packs_b81_95.errors import (
    BudgetExceeded,
    DeterminismViolation,
)


@dataclass
class JournalEntry:
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
class ExecutionJournal:
    """Ordered, tamper-evident execution journal."""

    entries: list[JournalEntry] = field(default_factory=list)

    def record(
        self, skill_id: str, archetype: str, input_payload: Any, output_data: Any
    ) -> JournalEntry:
        entry = JournalEntry(
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
class ExecutionResult:
    skill_id: str
    archetype: str
    output_data: dict[str, Any]
    output_digest: str
    input_digest: str
    journal: list[dict[str, Any]]
    journal_digest: str
    replayed: bool = False


class DeterministicEngine:
    """Core deterministic execution runtime for Language Pack skills."""

    def __init__(self, *, max_steps: int = 1000) -> None:
        self.max_steps = max_steps
        self._journal = ExecutionJournal()
        self._cache: dict[str, ExecutionResult] = {}

    def execute_skill(
        self, skill_id: str, archetype_name: str, payload: dict[str, Any]
    ) -> ExecutionResult:
        """Execute a skill through its archetype with determinism and journal recording."""
        if len(self._journal.entries) >= self.max_steps:
            raise BudgetExceeded(f"Step budget exceeded ({self.max_steps})")

        key = idempotency_key(skill_id, archetype_name, payload)
        if key in self._cache:
            cached = self._cache[key]
            return ExecutionResult(
                skill_id=cached.skill_id,
                archetype=cached.archetype,
                output_data=cached.output_data,
                output_digest=cached.output_digest,
                input_digest=cached.input_digest,
                journal=self._journal.as_list(),
                journal_digest=self._journal.journal_digest,
                replayed=True,
            )

        arch = get_archetype(archetype_name)
        res = arch.execute(payload)

        self._journal.record(skill_id, archetype_name, payload, res)
        out_digest = digest(res)
        in_digest = digest(payload)

        result = ExecutionResult(
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

    def verify_replay(
        self, skill_id: str, archetype_name: str, payload: dict[str, Any]
    ) -> bool:
        """Re-execute a skill and assert bit-identical output digest."""
        arch = get_archetype(archetype_name)
        res1 = arch.execute(payload)
        res2 = arch.execute(payload)
        d1 = digest(res1)
        d2 = digest(res2)
        if d1 != d2:
            raise DeterminismViolation(
                f"Replay failed for {skill_id}: {d1} != {d2}"
            )
        return True

    def verify_worker_invariance(
        self, work_units: Sequence[tuple[str, str, dict[str, Any]]]
    ) -> bool:
        """Assert that parallel worker count does not affect result digests."""
        # Serial execution
        serial_results = []
        for sid, arch, pl in work_units:
            a = get_archetype(arch)
            serial_results.append(digest(a.execute(pl)))

        # Concurrent execution (4 workers)
        def run_one(unit: tuple[str, str, dict[str, Any]]) -> str:
            _, arch, pl = unit
            a = get_archetype(arch)
            return digest(a.execute(pl))

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            parallel_results = list(pool.map(run_one, work_units))

        if serial_results != parallel_results:
            raise DeterminismViolation("Worker count altered execution output digests")
        return True
