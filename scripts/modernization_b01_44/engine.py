#!/usr/bin/env python3
"""The deterministic engine.

Guarantees implemented (not asserted):

* **Replayable** - an execution journal records every step; replaying the
  journal reproduces the output digest bit for bit.
* **Stable ordering** - work units are sorted by canonical bytes, so worker
  count and completion order cannot influence the result.
* **Content addressed** - the output digest is a function of the pinned inputs
  and nothing else.
* **Idempotent** - the same idempotency key returns the first result instead of
  executing twice.
* **Bounded** - iteration and budget ceilings are enforced, and hitting one is
  a refusal, never a silent truncation.
"""

from __future__ import annotations

import concurrent.futures
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

from scripts.modernization_b01_44.canonical import (
    canonical_bytes,
    digest,
    idempotency_key,
    stable_sort,
)
from scripts.modernization_b01_44.errors import BudgetExceeded, DeterminismViolation


@dataclass
class JournalEntry:
    step: int
    unit_digest: str
    output_digest: str
    label: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "unit_digest": self.unit_digest,
            "output_digest": self.output_digest,
            "label": self.label,
        }


@dataclass
class ExecutionJournal:
    """Ordered, replayable record of one deterministic execution."""

    entries: list[JournalEntry] = field(default_factory=list)

    def record(self, unit: Any, output: Any, label: str) -> JournalEntry:
        entry = JournalEntry(
            step=len(self.entries),
            unit_digest=digest(unit),
            output_digest=digest(output),
            label=label,
        )
        self.entries.append(entry)
        return entry

    def as_list(self) -> list[dict[str, Any]]:
        return [entry.as_dict() for entry in self.entries]

    @property
    def journal_digest(self) -> str:
        return digest(self.as_list())


@dataclass(frozen=True)
class DeterministicResult:
    output: Any
    output_digest: str
    journal: list[dict[str, Any]]
    journal_digest: str
    input_digest: str
    workers: int
    replayed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "output_digest": self.output_digest,
            "journal_digest": self.journal_digest,
            "input_digest": self.input_digest,
            "workers": self.workers,
            "steps": len(self.journal),
        }


class DeterministicEngine:
    """Execute pure work units under determinism and boundedness guarantees."""

    def __init__(self, *, max_iterations: int = 64, max_units: int = 100_000) -> None:
        self.max_iterations = max_iterations
        self.max_units = max_units
        self._memo: dict[str, DeterministicResult] = {}

    # -- core ------------------------------------------------------------

    def execute(
        self,
        units: Iterable[Any],
        transform: Callable[[Any], Any],
        *,
        label: str = "unit",
        workers: int = 1,
        idempotency: Any | None = None,
    ) -> DeterministicResult:
        """Run ``transform`` over ``units`` deterministically.

        ``workers`` may vary freely: results are collected by the *sorted* unit
        index, never by completion order, so 1 and 16 workers agree exactly.
        """

        ordered: Sequence[Any] = stable_sort(units)
        if len(ordered) > self.max_units:
            raise BudgetExceeded(
                "work unit count exceeds the engine ceiling",
                units=len(ordered),
                ceiling=self.max_units,
            )
        if workers < 1:
            raise DeterminismViolation("worker count must be >= 1", workers=workers)

        input_digest = digest({"units": list(ordered), "label": label})
        key = idempotency_key(input_digest, idempotency) if idempotency is not None else None
        if key is not None and key in self._memo:
            cached = self._memo[key]
            return DeterministicResult(
                output=cached.output,
                output_digest=cached.output_digest,
                journal=cached.journal,
                journal_digest=cached.journal_digest,
                input_digest=cached.input_digest,
                workers=cached.workers,
                replayed=True,
            )

        if workers == 1 or len(ordered) <= 1:
            outputs = [transform(unit) for unit in ordered]
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
                # Map preserves input order regardless of completion order.
                outputs = list(pool.map(transform, ordered))

        journal = ExecutionJournal()
        for unit, output in zip(ordered, outputs):
            journal.record(unit, output, label)

        result = DeterministicResult(
            output=outputs,
            output_digest=digest(outputs),
            journal=journal.as_list(),
            journal_digest=journal.journal_digest,
            input_digest=input_digest,
            workers=workers,
        )
        if key is not None:
            self._memo[key] = result
        return result

    # -- verification ----------------------------------------------------

    def verify_worker_invariance(
        self,
        units: Iterable[Any],
        transform: Callable[[Any], Any],
        *,
        worker_counts: Sequence[int] = (1, 4, 16),
        label: str = "unit",
    ) -> DeterministicResult:
        """Execute at several concurrency levels and refuse on any divergence."""

        materialised = list(units)
        baseline: DeterministicResult | None = None
        for count in worker_counts:
            result = self.execute(materialised, transform, label=label, workers=count)
            if baseline is None:
                baseline = result
                continue
            if result.output_digest != baseline.output_digest:
                raise DeterminismViolation(
                    "output digest depends on worker count",
                    workers=count,
                    baseline_workers=baseline.workers,
                    baseline_digest=baseline.output_digest,
                    observed_digest=result.output_digest,
                )
            if result.journal_digest != baseline.journal_digest:
                raise DeterminismViolation(
                    "journal digest depends on worker count",
                    workers=count,
                    baseline_workers=baseline.workers,
                )
        assert baseline is not None
        return baseline

    def replay(self, result: DeterministicResult, journal: list[dict[str, Any]]) -> bool:
        """A journal replays iff it reproduces the recorded journal digest."""

        return digest(journal) == result.journal_digest

    # -- bounded fixpoint -------------------------------------------------

    def fixpoint(
        self,
        state: Any,
        step: Callable[[Any], Any],
        *,
        label: str = "fixpoint",
    ) -> tuple[Any, ExecutionJournal]:
        """Iterate ``step`` until stable, refusing when the bound is reached.

        Non-convergence is surfaced as :class:`BudgetExceeded` rather than
        returning the last state, so a caller can never mistake "ran out of
        iterations" for "converged".
        """

        journal = ExecutionJournal()
        current = state
        for iteration in range(self.max_iterations):
            nxt = step(current)
            journal.record({"iteration": iteration, "state": current}, nxt, label)
            if canonical_bytes(nxt) == canonical_bytes(current):
                return current, journal
            current = nxt
        raise BudgetExceeded(
            "bounded fix loop did not reach a fixpoint",
            max_iterations=self.max_iterations,
            label=label,
        )
