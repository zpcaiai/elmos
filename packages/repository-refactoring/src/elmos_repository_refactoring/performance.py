"""Skill 18 — benchmark comparison that separates noise from regression.

The hard part of a performance gate is not measuring; it is refusing to call
a difference real when the evidence cannot carry that claim.  Three rules are
structural here:

* **Environments must match.**  A run whose environment digest differs from
  the baseline's is ``not-comparable`` — not "slightly slower".  Comparing a
  cold container against a warm one and reporting a percentage is the most
  common way a performance report lies.
* **Too few samples is undecided, never pass.**  Below
  :data:`MIN_SAMPLES` the verdict is ``undecided``; a guardrail that a
  two-sample benchmark cannot decide *blocks* rather than waving through.
* **The noise band comes from the baseline's own spread**, not from a
  constant.  A 5% change on a metric whose baseline varies by 20% run to run
  is not a regression, and a 3% change on a metric that varies by 0.2% is.

Everything is computed with the standard library, deterministically, from
supplied samples.  This module never runs a benchmark: producing the samples
is an executor's job, and with no samples the verdict is ``not-run``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any

from .contracts import ContractError, sha256_payload

#: Below this many samples per side, no verdict beyond "undecided" is honest.
MIN_SAMPLES = 5

#: Metrics where a *larger* number is better.  Everything else is "lower is
#: better", which is the safe default for latency, CPU, memory and cost.
HIGHER_IS_BETTER = frozenset({"throughput", "rps", "qps", "ops_per_second", "hit_rate"})


class WorkloadClass(StrEnum):
    MICRO = "micro"
    COMPONENT = "component"
    END_TO_END = "end-to-end"
    PRODUCTION_SHADOW = "production-shadow"


class Verdict(StrEnum):
    IMPROVED = "improved"
    UNCHANGED = "unchanged"
    REGRESSED = "regressed"
    #: Measured, but the evidence cannot separate the change from noise.
    UNDECIDED = "undecided"
    #: The two sides are not comparable at all (environment mismatch).
    NOT_COMPARABLE = "not-comparable"
    #: No samples were produced.  Never a pass.
    NOT_RUN = "not-run"


@dataclass(frozen=True, slots=True)
class Environment:
    """Everything that must be identical for two samples to be comparable."""

    cpu_model: str
    cpu_count: int
    memory_mb: int
    container_image: str
    dataset_id: str
    warmup_iterations: int
    concurrency: int
    isolation: str = "dedicated"

    def to_payload(self) -> dict[str, Any]:
        return {
            "cpuModel": self.cpu_model,
            "cpuCount": self.cpu_count,
            "memoryMb": self.memory_mb,
            "containerImage": self.container_image,
            "datasetId": self.dataset_id,
            "warmupIterations": self.warmup_iterations,
            "concurrency": self.concurrency,
            "isolation": self.isolation,
        }

    @property
    def digest(self) -> str:
        return sha256_payload(self.to_payload())

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> Environment:
        try:
            return cls(
                cpu_model=str(payload["cpuModel"]),
                cpu_count=int(payload["cpuCount"]),
                memory_mb=int(payload["memoryMb"]),
                container_image=str(payload["containerImage"]),
                dataset_id=str(payload["datasetId"]),
                warmup_iterations=int(payload["warmupIterations"]),
                concurrency=int(payload["concurrency"]),
                isolation=str(payload.get("isolation", "dedicated")),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ContractError(
                "invalid_environment",
                "an environment needs cpuModel, cpuCount, memoryMb, containerImage, datasetId, "
                "warmupIterations and concurrency",
                {"received": sorted(payload)},
            ) from error


@dataclass(frozen=True, slots=True)
class Guardrail:
    """The budget for one metric, as a fraction of the baseline."""

    metric: str
    max_regression: Decimal
    blocking: bool = True

    def to_payload(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "maxRegression": str(self.max_regression),
            "blocking": self.blocking,
        }


@dataclass(frozen=True, slots=True)
class Samples:
    """Raw measurements for one metric on one side of the comparison."""

    metric: str
    workload: WorkloadClass
    values: tuple[Decimal, ...]
    unit: str
    environment: Environment

    def __post_init__(self) -> None:
        if not self.metric.strip():
            raise ContractError("invalid_metric", "a sample set needs a metric name")
        if any(value < 0 for value in self.values):
            raise ContractError(
                "invalid_sample", f"metric '{self.metric}' has a negative measurement"
            )

    @property
    def count(self) -> int:
        return len(self.values)

    def quantile(self, fraction: Decimal) -> Decimal:
        """Nearest-rank quantile — deterministic and free of interpolation drift."""

        if not self.values:
            raise ContractError("no_samples", f"metric '{self.metric}' has no measurements")
        ordered = sorted(self.values)
        rank = int((fraction * Decimal(len(ordered))).to_integral_value(rounding="ROUND_CEILING"))
        return ordered[max(0, min(len(ordered) - 1, rank - 1))]

    @property
    def median(self) -> Decimal:
        return self.quantile(Decimal("0.5"))

    @property
    def p95(self) -> Decimal:
        return self.quantile(Decimal("0.95"))

    @property
    def spread(self) -> Decimal:
        """Interquartile range as a fraction of the median — the metric's own noise."""

        median = self.median
        if median == 0:
            return Decimal(0)
        iqr = self.quantile(Decimal("0.75")) - self.quantile(Decimal("0.25"))
        return (iqr / median).copy_abs()

    def to_payload(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "workload": self.workload.value,
            "unit": self.unit,
            "count": self.count,
            "median": str(self.median),
            "p95": str(self.p95),
            "spread": str(self.spread),
            "environmentDigest": self.environment.digest,
        }


@dataclass(frozen=True, slots=True)
class MetricComparison:
    metric: str
    workload: WorkloadClass
    unit: str
    baseline_median: Decimal | None
    candidate_median: Decimal | None
    baseline_p95: Decimal | None
    candidate_p95: Decimal | None
    relative_change: Decimal | None
    noise_band: Decimal | None
    guardrail: Decimal | None
    verdict: Verdict
    detail: str
    sample_counts: tuple[int, int] = (0, 0)

    @property
    def blocks(self) -> bool:
        """Anything other than a decided non-regression blocks a blocking guardrail."""

        return self.verdict in (
            Verdict.REGRESSED,
            Verdict.UNDECIDED,
            Verdict.NOT_COMPARABLE,
            Verdict.NOT_RUN,
        )

    def to_payload(self) -> dict[str, Any]:
        def text(value: Decimal | None) -> str | None:
            return None if value is None else str(value)

        return {
            "metric": self.metric,
            "workload": self.workload.value,
            "unit": self.unit,
            "baselineMedian": text(self.baseline_median),
            "candidateMedian": text(self.candidate_median),
            "baselineP95": text(self.baseline_p95),
            "candidateP95": text(self.candidate_p95),
            "relativeChange": text(self.relative_change),
            "noiseBand": text(self.noise_band),
            "guardrail": text(self.guardrail),
            "verdict": self.verdict.value,
            "detail": self.detail,
            "baselineSamples": self.sample_counts[0],
            "candidateSamples": self.sample_counts[1],
            "blocks": self.blocks,
        }


@dataclass(frozen=True, slots=True)
class PerformanceReport:
    comparisons: tuple[MetricComparison, ...]
    profile_diff: tuple[Mapping[str, Any], ...]
    suspects: tuple[Mapping[str, Any], ...]
    reasons: tuple[str, ...]

    @property
    def blocking(self) -> tuple[MetricComparison, ...]:
        return tuple(item for item in self.comparisons if item.blocks)

    @property
    def allowed(self) -> bool:
        return not self.blocking

    def to_payload(self) -> dict[str, Any]:
        return {
            "performanceDiff": [item.to_payload() for item in self.comparisons],
            "profileDiff": [dict(item) for item in self.profile_diff],
            "regressionSuspects": [dict(item) for item in self.suspects],
            "guardrailDecision": {
                "allowed": self.allowed,
                "blockingMetrics": [item.metric for item in self.blocking],
            },
            "reasons": list(self.reasons),
        }

    @property
    def digest(self) -> str:
        return sha256_payload(self.to_payload())


# ---------------------------------------------------------------------------
# Benchmark planning
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BenchmarkSpec:
    name: str
    workload: WorkloadClass
    command: str
    metrics: tuple[str, ...]
    repetitions: int
    warmup: int

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "workload": self.workload.value,
            "command": self.command,
            "metrics": list(self.metrics),
            "repetitions": self.repetitions,
            "warmup": self.warmup,
        }


def plan_benchmarks(
    targets: Sequence[str],
    *,
    repetitions: int = 11,
    warmup: int = 3,
) -> tuple[BenchmarkSpec, ...]:
    """A repeatable benchmark per workload class for each declared target.

    ``repetitions`` defaults to an odd number so the median is an actual
    observation rather than an average of two, and to a value at or above
    :data:`MIN_SAMPLES` so the result is decidable at all.
    """

    if repetitions < MIN_SAMPLES:
        raise ContractError(
            "insufficient_repetitions",
            f"at least {MIN_SAMPLES} repetitions are needed for a decidable comparison",
            {"requested": repetitions},
        )
    specs: list[BenchmarkSpec] = []
    for target in targets:
        for workload, metrics in (
            (WorkloadClass.MICRO, ("latency_ns", "allocations")),
            (WorkloadClass.COMPONENT, ("latency_ms", "cpu_seconds", "memory_mb")),
            (WorkloadClass.END_TO_END, ("latency_ms", "throughput", "cost_per_1k")),
        ):
            specs.append(
                BenchmarkSpec(
                    name=f"{target}:{workload.value}",
                    workload=workload,
                    command=f"benchmark --target {target} --workload {workload.value}",
                    metrics=metrics,
                    repetitions=repetitions,
                    warmup=warmup,
                )
            )
    return tuple(specs)


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def compare_metric(
    baseline: Samples | None,
    candidate: Samples | None,
    guardrail: Guardrail | None,
    *,
    noise_floor: Decimal = Decimal("0.02"),
) -> MetricComparison:
    """Decide one metric, refusing to decide when the evidence cannot."""

    known = baseline if baseline is not None else candidate
    metric = known.metric if known is not None else "unknown"
    workload = known.workload if known is not None else WorkloadClass.MICRO
    unit = known.unit if known is not None else ""
    budget = guardrail.max_regression if guardrail else None

    if baseline is None or candidate is None:
        return MetricComparison(
            metric=metric,
            workload=workload,
            unit=unit,
            baseline_median=None,
            candidate_median=None,
            baseline_p95=None,
            candidate_p95=None,
            relative_change=None,
            noise_band=None,
            guardrail=budget,
            verdict=Verdict.NOT_RUN,
            detail=(
                "only one side of the comparison produced measurements; a missing benchmark is "
                "not evidence that nothing changed"
            ),
            sample_counts=(baseline.count if baseline else 0, candidate.count if candidate else 0),
        )

    counts = (baseline.count, candidate.count)
    if baseline.environment.digest != candidate.environment.digest:
        return MetricComparison(
            metric=metric,
            workload=workload,
            unit=unit,
            baseline_median=baseline.median,
            candidate_median=candidate.median,
            baseline_p95=baseline.p95,
            candidate_p95=candidate.p95,
            relative_change=None,
            noise_band=None,
            guardrail=budget,
            verdict=Verdict.NOT_COMPARABLE,
            detail=(
                "the two sides ran in different environments; the difference between them is not "
                "attributable to the change"
            ),
            sample_counts=counts,
        )

    band = max(baseline.spread, candidate.spread, noise_floor)
    base_median = baseline.median
    if base_median == 0:
        change = Decimal(0) if candidate.median == 0 else Decimal(1)
    else:
        change = (candidate.median - base_median) / base_median
    if metric.lower() in HIGHER_IS_BETTER:
        change = -change

    if min(counts) < MIN_SAMPLES:
        return MetricComparison(
            metric=metric,
            workload=workload,
            unit=unit,
            baseline_median=base_median,
            candidate_median=candidate.median,
            baseline_p95=baseline.p95,
            candidate_p95=candidate.p95,
            relative_change=change,
            noise_band=band,
            guardrail=budget,
            verdict=Verdict.UNDECIDED,
            detail=(
                f"only {min(counts)} sample(s) on the smaller side; below {MIN_SAMPLES} a "
                "difference cannot be separated from run-to-run variation"
            ),
            sample_counts=counts,
        )

    if change.copy_abs() <= band:
        verdict = Verdict.UNCHANGED
        detail = (
            f"the {change:.2%} change sits inside the {band:.2%} noise band derived from the "
            "benchmark's own spread"
        )
    elif change < 0:
        verdict = Verdict.IMPROVED
        detail = f"{(-change):.2%} better than baseline, beyond the {band:.2%} noise band"
    elif budget is not None and change > budget:
        verdict = Verdict.REGRESSED
        detail = f"{change:.2%} worse than baseline, over the {budget:.2%} guardrail"
    elif budget is None:
        verdict = Verdict.REGRESSED
        detail = (
            f"{change:.2%} worse than baseline, beyond the {band:.2%} noise band, and no guardrail "
            "declares how much regression is acceptable for this metric"
        )
    else:
        verdict = Verdict.UNCHANGED
        detail = f"{change:.2%} worse than baseline but within the {budget:.2%} guardrail"

    return MetricComparison(
        metric=metric,
        workload=workload,
        unit=unit,
        baseline_median=base_median,
        candidate_median=candidate.median,
        baseline_p95=baseline.p95,
        candidate_p95=candidate.p95,
        relative_change=change,
        noise_band=band,
        guardrail=budget,
        verdict=verdict,
        detail=detail,
        sample_counts=counts,
    )


def diff_profiles(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    top: int = 15,
) -> tuple[Mapping[str, Any], ...]:
    """Per-symbol self-time delta between two flat profiles."""

    names = sorted(set(baseline) | set(candidate))
    rows: list[Mapping[str, Any]] = []
    for name in names:
        before = Decimal(str(baseline.get(name, 0)))
        after = Decimal(str(candidate.get(name, 0)))
        delta = after - before
        if delta == 0:
            continue
        rows.append(
            {
                "symbol": name,
                "baseline": str(before),
                "candidate": str(after),
                "delta": str(delta),
                "appeared": name not in baseline,
                "disappeared": name not in candidate,
            }
        )
    rows.sort(key=lambda row: (-abs(Decimal(str(row["delta"]))), str(row["symbol"])))
    return tuple(rows[:top])


def locate_suspects(
    profile_delta: Sequence[Mapping[str, Any]],
    changed_symbols: Sequence[str],
) -> tuple[Mapping[str, Any], ...]:
    """Cross the profile delta with what the patch actually touched."""

    touched = set(changed_symbols)
    suspects: list[Mapping[str, Any]] = []
    for row in profile_delta:
        symbol = str(row["symbol"])
        if Decimal(str(row["delta"])) <= 0:
            continue
        in_patch = symbol in touched or any(symbol.startswith(f"{item}.") for item in touched)
        suspects.append(
            {
                "symbol": symbol,
                "delta": row["delta"],
                "changedByThisPatch": in_patch,
                "detail": (
                    "this symbol was modified by the patch and got slower"
                    if in_patch
                    else "this symbol got slower but the patch did not touch it; look for a "
                    "changed caller, a changed data shape, or environmental drift before "
                    "attributing it to the refactor"
                ),
            }
        )
    return tuple(suspects)


def evaluate(
    baselines: Sequence[Samples],
    candidates: Sequence[Samples],
    guardrails: Sequence[Guardrail],
    *,
    profile_before: Mapping[str, Any] | None = None,
    profile_after: Mapping[str, Any] | None = None,
    changed_symbols: Sequence[str] = (),
) -> PerformanceReport:
    """Compare every declared guardrail, plus every metric that was measured."""

    budget = {item.metric: item for item in guardrails}
    left = {(item.metric, item.workload): item for item in baselines}
    right = {(item.metric, item.workload): item for item in candidates}
    keys = sorted(set(left) | set(right), key=lambda item: (item[0], item[1].value))

    comparisons = [compare_metric(left.get(key), right.get(key), budget.get(key[0])) for key in keys]

    measured = {item.metric for item in comparisons}
    for name in sorted(set(budget) - measured):
        rail = budget[name]
        comparisons.append(
            MetricComparison(
                metric=name,
                workload=WorkloadClass.COMPONENT,
                unit="",
                baseline_median=None,
                candidate_median=None,
                baseline_p95=None,
                candidate_p95=None,
                relative_change=None,
                noise_band=None,
                guardrail=rail.max_regression,
                verdict=Verdict.NOT_RUN,
                detail=(
                    f"a guardrail is declared for '{name}' but nothing measured it; an unmeasured "
                    "guardrail is undecided, and undecided blocks"
                ),
            )
        )

    profile_diff = (
        diff_profiles(profile_before, profile_after)
        if profile_before is not None and profile_after is not None
        else ()
    )
    suspects = locate_suspects(profile_diff, changed_symbols)

    reasons: list[str] = []
    if not profile_diff:
        reasons.append(
            "no profile pair was supplied; a regression can be reported but not located"
        )
    for item in comparisons:
        if item.blocks:
            reasons.append(f"{item.metric} ({item.workload.value}): {item.verdict.value} — {item.detail}")
    return PerformanceReport(
        comparisons=tuple(comparisons),
        profile_diff=profile_diff,
        suspects=suspects,
        reasons=tuple(reasons),
    )


def samples_from_payload(payload: Mapping[str, Any]) -> Samples:
    """Parse one measured metric, refusing anything the comparison cannot use."""

    try:
        workload = WorkloadClass(str(payload.get("workload", "component")))
    except ValueError as error:
        raise ContractError(
            "invalid_workload",
            f"unknown workload class '{payload.get('workload')}'",
            {"supported": [item.value for item in WorkloadClass]},
        ) from error
    raw = payload.get("values")
    if not isinstance(raw, Sequence) or isinstance(raw, str | bytes) or not raw:
        raise ContractError(
            "invalid_samples", "a sample set needs a non-empty 'values' array of measurements"
        )
    try:
        values = tuple(Decimal(str(item)) for item in raw)
    except ArithmeticError as error:
        raise ContractError("invalid_samples", "every measurement must be numeric") from error
    return Samples(
        metric=str(payload.get("metric", "")).strip(),
        workload=workload,
        values=values,
        unit=str(payload.get("unit", "")),
        environment=Environment.from_payload(
            environment if isinstance(environment := payload.get("environment"), Mapping) else {}
        ),
    )


def guardrails_from_payload(payload: Sequence[Mapping[str, Any]]) -> tuple[Guardrail, ...]:
    rails: list[Guardrail] = []
    for entry in payload:
        try:
            rails.append(
                Guardrail(
                    metric=str(entry["metric"]),
                    max_regression=Decimal(str(entry["maxRegression"])),
                    blocking=bool(entry.get("blocking", True)),
                )
            )
        except (KeyError, ArithmeticError, TypeError) as error:
            raise ContractError(
                "invalid_guardrail",
                "each guardrail needs 'metric' and a numeric 'maxRegression'",
                {"entry": dict(entry)},
            ) from error
    return tuple(rails)


__all__ = [
    "HIGHER_IS_BETTER",
    "MIN_SAMPLES",
    "BenchmarkSpec",
    "Environment",
    "Guardrail",
    "MetricComparison",
    "PerformanceReport",
    "Samples",
    "Verdict",
    "WorkloadClass",
    "compare_metric",
    "diff_profiles",
    "evaluate",
    "guardrails_from_payload",
    "locate_suspects",
    "plan_benchmarks",
    "samples_from_payload",
]
