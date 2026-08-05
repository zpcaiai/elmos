#!/usr/bin/env python3
"""Corpus execution, benchmark scoring and cost/quota accounting.

Four corpora with different roles:

* ``development`` - may be inspected and tuned against.
* ``representative`` - the workload a certification claim is *about*.
* ``negative`` - cases that must be refused; a pass here is a failure.
* ``holdout`` - never revealed to tuning; a regression blocks release.

Scores always carry an explicit denominator, and a case that did not run is
counted as ``not_run`` rather than dropped from the denominator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from scripts.modernization_b01_44.canonical import digest, stable_sort
from scripts.modernization_b01_44.errors import BudgetExceeded, RuntimeRefusal

CORPUS_KINDS = ("development", "representative", "negative", "holdout")


@dataclass(frozen=True)
class CorpusCase:
    case_id: str
    kind: str
    payload: dict[str, Any]
    expect: str  # "accept" | "refuse"

    def __post_init__(self) -> None:
        if self.kind not in CORPUS_KINDS:
            raise RuntimeRefusal("unknown corpus kind", kind=self.kind)
        if self.expect not in ("accept", "refuse"):
            raise RuntimeRefusal("unknown expectation", expect=self.expect)


@dataclass
class CaseOutcome:
    case_id: str
    kind: str
    observed: str  # accept | refuse | error | not_run
    expected: str
    detail: str = ""

    @property
    def passed(self) -> bool:
        return self.observed == self.expected

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "kind": self.kind,
            "observed": self.observed,
            "expected": self.expected,
            "passed": self.passed,
            "detail": self.detail,
        }


@dataclass
class CorpusReport:
    kind: str
    outcomes: list[CaseOutcome] = field(default_factory=list)

    @property
    def denominator(self) -> int:
        return len(self.outcomes)

    @property
    def passed(self) -> int:
        return sum(1 for o in self.outcomes if o.passed)

    @property
    def not_run(self) -> int:
        return sum(1 for o in self.outcomes if o.observed == "not_run")

    @property
    def score(self) -> str:
        """Score as an exact decimal string - never a float."""

        if self.denominator == 0:
            return "0/0"
        return f"{self.passed}/{self.denominator}"

    @property
    def clean(self) -> bool:
        return self.denominator > 0 and self.passed == self.denominator

    def failures(self) -> list[CaseOutcome]:
        return [o for o in self.outcomes if not o.passed]

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "score": self.score,
            "denominator": self.denominator,
            "passed": self.passed,
            "not_run": self.not_run,
            "clean": self.clean,
            "outcomes": [o.as_dict() for o in self.outcomes],
        }


class Budget:
    """Hard ceiling on units of work.  Exhaustion refuses; it never truncates."""

    def __init__(self, *, limit: int, label: str = "budget") -> None:
        if limit < 0:
            raise RuntimeRefusal("budget limit must be >= 0", limit=limit)
        self.limit = limit
        self.label = label
        self.spent = 0

    def charge(self, amount: int = 1) -> int:
        if self.spent + amount > self.limit:
            raise BudgetExceeded(
                "budget exhausted", label=self.label, limit=self.limit, spent=self.spent
            )
        self.spent += amount
        return self.spent

    @property
    def remaining(self) -> int:
        return self.limit - self.spent

    def as_dict(self) -> dict[str, Any]:
        return {"label": self.label, "limit": self.limit, "spent": self.spent, "remaining": self.remaining}


class CorpusRunner:
    """Execute corpus cases against a subject under an explicit budget."""

    def __init__(self, subject: Callable[[dict[str, Any]], Any], *, budget: Budget | None = None) -> None:
        self.subject = subject
        self.budget = budget

    def run(self, cases: Iterable[CorpusCase], kind: str) -> CorpusReport:
        selected = [case for case in cases if case.kind == kind]
        report = CorpusReport(kind=kind)
        for case in sorted(selected, key=lambda c: c.case_id):
            if self.budget is not None and self.budget.remaining <= 0:
                report.outcomes.append(
                    CaseOutcome(case.case_id, kind, "not_run", case.expect, "budget exhausted")
                )
                continue
            if self.budget is not None:
                self.budget.charge()
            try:
                self.subject(case.payload)
                observed, detail = "accept", ""
            except RuntimeRefusal as exc:
                observed, detail = "refuse", exc.code
            except Exception as exc:  # noqa: BLE001 - an unexpected crash is a result
                observed, detail = "error", f"{type(exc).__name__}: {exc}"
            report.outcomes.append(CaseOutcome(case.case_id, kind, observed, case.expect, detail))
        return report

    def run_all(self, cases: Iterable[CorpusCase]) -> dict[str, CorpusReport]:
        materialised = list(cases)
        return {kind: self.run(materialised, kind) for kind in CORPUS_KINDS}


@dataclass
class BenchmarkResult:
    reports: dict[str, CorpusReport]
    baseline_digest: str | None = None

    @property
    def corpus_digest(self) -> str:
        return digest({k: v.as_dict() for k, v in sorted(self.reports.items())})

    def evidence_scopes(self) -> list[str]:
        """Which certification evidence scopes this run legitimately supports."""

        mapping = {
            "development": "development-corpus",
            "negative": "negative-corpus",
            "representative": "representative-workload",
            "holdout": "holdout-corpus",
        }
        return stable_sort(
            mapping[kind] for kind, report in self.reports.items() if report.clean
        )

    def holdout_regressed(self, baseline: "BenchmarkResult") -> bool:
        current = self.reports.get("holdout")
        previous = baseline.reports.get("holdout")
        if current is None or previous is None:
            return False
        return current.passed < previous.passed

    def as_dict(self) -> dict[str, Any]:
        return {
            "corpus_digest": self.corpus_digest,
            "reports": {k: v.as_dict() for k, v in sorted(self.reports.items())},
            "evidence_scopes": self.evidence_scopes(),
        }
