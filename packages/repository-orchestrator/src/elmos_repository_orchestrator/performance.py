"""Measured performance and retrieval-quality evidence helpers."""

from __future__ import annotations

import math
import platform
import statistics
import sys
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Mapping, Sequence

from .contracts import ContractError, decimal_value
from .retrieval import HybridIndex, RetrievalQuery, SearchDocument, ndcg_at_k, recall_at_k


def percentile(samples: Sequence[float], percentile_value: float) -> float:
    if not samples:
        raise ContractError("empty_samples", "performance samples must not be empty")
    if not 0 <= percentile_value <= 100:
        raise ContractError("invalid_percentile", "percentile must be between 0 and 100")
    values = sorted(float(item) for item in samples)
    rank = (len(values) - 1) * percentile_value / 100
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return values[lower]
    return values[lower] + (values[upper] - values[lower]) * (rank - lower)


@dataclass(frozen=True, slots=True)
class LatencySummary:
    count: int
    p50_ms: float
    p95_ms: float
    p99_ms: float
    mean_ms: float

    @classmethod
    def from_samples(cls, samples: Sequence[float]) -> "LatencySummary":
        return cls(
            count=len(samples),
            p50_ms=percentile(samples, 50),
            p95_ms=percentile(samples, 95),
            p99_ms=percentile(samples, 99),
            mean_ms=statistics.fmean(samples),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "p50_ms": self.p50_ms,
            "p95_ms": self.p95_ms,
            "p99_ms": self.p99_ms,
            "mean_ms": self.mean_ms,
        }


@dataclass(frozen=True, slots=True)
class RetrievalCase:
    query: RetrievalQuery
    relevant: frozenset[str]
    graded_relevance: Mapping[str, float]


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    workload: str
    representative: bool
    documents: int
    cases: int
    repetitions: int
    index_latency: LatencySummary
    query_latency: LatencySummary
    recall_at_10: float
    ndcg_at_10: float
    resume_latency: LatencySummary | None
    duplicate_side_effects: int
    token_cost: Decimal
    currency: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "workload": self.workload,
            "representative": self.representative,
            "documents": self.documents,
            "cases": self.cases,
            "repetitions": self.repetitions,
            "index_latency": self.index_latency.to_payload(),
            "query_latency": self.query_latency.to_payload(),
            "recall_at_10": self.recall_at_10,
            "ndcg_at_10": self.ndcg_at_10,
            "resume_latency": None if self.resume_latency is None else self.resume_latency.to_payload(),
            "duplicate_side_effects": self.duplicate_side_effects,
            "token_cost": format(self.token_cost, "f"),
            "currency": self.currency,
            "environment": {"python": sys.version.split()[0], "platform": platform.platform()},
            "external_provider_evidence": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }


def token_cost(
    *,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    input_per_million: Decimal | str,
    cached_input_per_million: Decimal | str,
    output_per_million: Decimal | str,
) -> Decimal:
    if min(input_tokens, cached_input_tokens, output_tokens) < 0 or cached_input_tokens > input_tokens:
        raise ContractError("invalid_token_usage", "token usage is invalid")
    uncached = input_tokens - cached_input_tokens
    return (
        Decimal(uncached) * decimal_value(input_per_million, "input_per_million", minimum=Decimal("0"))
        + Decimal(cached_input_tokens) * decimal_value(cached_input_per_million, "cached_input_per_million", minimum=Decimal("0"))
        + Decimal(output_tokens) * decimal_value(output_per_million, "output_per_million", minimum=Decimal("0"))
    ) / Decimal(1_000_000)


def _milliseconds(call: Callable[[], Any]) -> tuple[float, Any]:
    started = time.perf_counter_ns()
    value = call()
    return (time.perf_counter_ns() - started) / 1_000_000, value


def benchmark_retrieval(
    documents: Sequence[SearchDocument],
    cases: Sequence[RetrievalCase],
    *,
    repetitions: int = 5,
    workload: str = "synthetic-local-contract",
    representative: bool = False,
    resume_probe: Callable[[], Any] | None = None,
    duplicate_side_effects: int = 0,
    measured_token_cost: Decimal = Decimal("0"),
    currency: str = "USD",
) -> BenchmarkReport:
    if not documents or not cases:
        raise ContractError("empty_benchmark", "benchmark requires documents and cases")
    if not 1 <= repetitions <= 1000:
        raise ContractError("invalid_repetitions", "repetitions must be between 1 and 1000")
    index_samples: list[float] = []
    query_samples: list[float] = []
    recalls: list[float] = []
    ndcgs: list[float] = []
    for _ in range(repetitions):
        index = HybridIndex()
        elapsed, _ = _milliseconds(lambda: index.upsert(documents))
        index_samples.append(elapsed)
        for case in cases:
            elapsed, hits = _milliseconds(lambda case=case: index.search(case.query))
            query_samples.append(elapsed)
            actual = [hit.document.document_id for hit in hits]
            recalls.append(recall_at_k(actual, case.relevant, k=10))
            ndcgs.append(ndcg_at_k(actual, case.graded_relevance, k=10))
    resume_samples: list[float] = []
    if resume_probe is not None:
        for _ in range(repetitions):
            elapsed, _ = _milliseconds(resume_probe)
            resume_samples.append(elapsed)
    return BenchmarkReport(
        workload=workload,
        representative=representative,
        documents=len(documents),
        cases=len(cases),
        repetitions=repetitions,
        index_latency=LatencySummary.from_samples(index_samples),
        query_latency=LatencySummary.from_samples(query_samples),
        recall_at_10=statistics.fmean(recalls),
        ndcg_at_10=statistics.fmean(ndcgs),
        resume_latency=None if not resume_samples else LatencySummary.from_samples(resume_samples),
        duplicate_side_effects=duplicate_side_effects,
        token_cost=measured_token_cost,
        currency=currency,
    )
