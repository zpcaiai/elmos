"""Cost, ETA and effort observability: three quantities that must never merge.

Every incident review of a "we saved 400 hours this week" dashboard ends in the
same place: somebody added machine seconds to an engineer-hour estimate and to
time a human spent asleep before approving a pull request.  This module makes
that addition impossible rather than discouraged.  :class:`MachineWallClock`,
:class:`HumanEquivalentEffort` and :class:`HitlWaitTime` are three distinct
types; ``+`` between two of them raises ``UNIT_MISMATCH``, and :class:`Eta`
reports all three side by side with a :meth:`Eta.total` that refuses to exist.

The second rule is the one this repository has broken three times: a component
whose provider reported no usage has cost ``None`` and ``measured: false`` — it
never becomes ``0``.  Zero is a real, reachable business value (a cached call
genuinely costs nothing, a budget can genuinely be exhausted to exactly zero),
so "we did not measure it" and "it was nothing" have to be different words.  A
:class:`CostReport` containing any unmeasured component reports ``total: null``
and ``partial: true``, and the skill returns ``PARTIAL`` rather than dressing an
incomplete figure up as a final one.

ETA estimation is deliberately dull: integer arithmetic over historical
samples, a median-scaled P50/P90 range, and the sample count reported next to
it.  Below the declared minimum sample count the range still comes out but is
labelled ``insufficient-data``, because a bare point estimate is read as a
promise and a wide range is read as a warning.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Any

from .contracts import (
    Status,
    digest,
    reject_unknown_fields,
    require_bool,
    require_decimal,
    require_identifier,
    require_int,
    require_mapping,
    require_str,
    require_str_seq,
)
from .errors import Category, KernelError, register_codes
from .ports import EventStore
from .registry import register

__all__ = [
    "BudgetLedger",
    "CacheSavings",
    "Confidence",
    "CostComponent",
    "CostReport",
    "CriticalPath",
    "DurationSample",
    "Eta",
    "HitlWaitTime",
    "HumanEquivalentEffort",
    "LedgerEntry",
    "MIN_SAMPLES",
    "MachineWallClock",
    "MeterPrice",
    "Phase",
    "PriceProfile",
    "ProgressSnapshot",
    "SloMetric",
    "Span",
    "UsageRecord",
    "cache_savings",
    "coverage_report",
    "critical_path",
    "estimate_eta",
    "handle",
    "price_usage",
    "reconcile_billing",
    "record_billing",
    "slo_metrics",
]

register_codes(
    Category.RESOURCE,
    "ETA_UNAVAILABLE",
    "METRIC_GAP",
    "PRICE_PROFILE_MISSING",
    "BILLING_RECONCILIATION_FAILED",
)
register_codes(
    Category.SEMANTIC,
    "UNIT_MISMATCH",
)

#: Below this many historical samples an ETA is labelled ``insufficient-data``.
#: Five is not a statistical claim; it is the point at which the median of the
#: samples stops being one lucky run.
MIN_SAMPLES = 5

#: Rate arithmetic is scaled integer arithmetic.  Milliseconds per size unit are
#: multiplied by this factor before the integer division so that a small repo
#: does not round its rate to zero.
_RATE_SCALE = 1_000_000

#: Currency amounts are exact to the micro-unit.  Anything finer is provider
#: noise; anything coarser loses per-token prices.
_MICRO = Decimal("0.000001")


def _quantize(amount: Decimal) -> Decimal:
    """Round a currency amount to the micro-unit, half-up and deterministically."""

    return amount.quantize(_MICRO, rounding=ROUND_HALF_UP)


def _mixed(left: object, right: object) -> KernelError:
    return KernelError(
        code="UNIT_MISMATCH",
        message=(
            f"{type(left).__name__} and {type(right).__name__} are different quantities "
            "and cannot be combined"
        ),
        recommended_action="report machine time, human-equivalent effort and HITL wait separately",
    )


# --- the three quantities ----------------------------------------------------


@dataclass(frozen=True, slots=True)
class MachineWallClock:
    """Milliseconds a machine actually spent.

    Integer milliseconds, measured, never estimated.  This is the only quantity
    an SLO or an ETA is allowed to be stated in, and it is a separate type from
    the other two precisely so that ``eta + human_equivalent`` is a
    ``TypeError``-shaped failure at the call site rather than a plausible number
    on a slide.
    """

    milliseconds: int

    def __post_init__(self) -> None:
        require_int(self.milliseconds, "machineWallClockMs", minimum=0)

    @property
    def unit(self) -> str:
        return "machine-wall-clock-ms"

    def __add__(self, other: object) -> MachineWallClock:
        if not isinstance(other, MachineWallClock):
            raise _mixed(self, other)
        return MachineWallClock(self.milliseconds + other.milliseconds)

    def to_payload(self) -> dict[str, Any]:
        return {
            "unit": self.unit,
            "milliseconds": self.milliseconds,
            "measured": True,
            "estimate": False,
        }


@dataclass(frozen=True, slots=True)
class HumanEquivalentEffort:
    """An *estimate* of the engineer time the work replaces.

    Stored as integer milli-hours so nothing here is a float, and it always
    carries the ``method`` that produced it.  It is never reported without the
    ``estimate: true`` flag, because the number's only honest use is comparative
    — this change was roughly twice the work of that one — and the moment it is
    added to machine time it starts being quoted as a fact.
    """

    milli_hours: int
    method: str
    basis: str = ""

    def __post_init__(self) -> None:
        require_int(self.milli_hours, "humanEquivalentMilliHours", minimum=0)
        require_str(self.method, "humanEquivalent.method", max_length=256)

    @property
    def unit(self) -> str:
        return "human-equivalent-milli-hours"

    @property
    def hours(self) -> Decimal:
        return Decimal(self.milli_hours) / Decimal(1000)

    def __add__(self, other: object) -> HumanEquivalentEffort:
        if not isinstance(other, HumanEquivalentEffort):
            raise _mixed(self, other)
        if other.method != self.method:
            raise KernelError(
                code="UNIT_MISMATCH",
                message=(
                    f"human-equivalent estimates from different methods "
                    f"({self.method!r} and {other.method!r}) are not additive"
                ),
                recommended_action="report each estimation method's total separately",
            )
        return HumanEquivalentEffort(self.milli_hours + other.milli_hours, self.method, self.basis)

    def to_payload(self) -> dict[str, Any]:
        return {
            "unit": self.unit,
            "milliHours": self.milli_hours,
            "hours": self.hours,
            "estimate": True,
            "method": self.method,
            "basis": self.basis,
        }


@dataclass(frozen=True, slots=True)
class HitlWaitTime:
    """Milliseconds spent waiting for a human.

    Separated from machine time because it is the number that actually explains
    a slow run, and because folding it into machine time makes the pipeline look
    slow while folding it out makes the run look fast.  Invariant I4: approval
    wait is reported on its own line.
    """

    milliseconds: int

    def __post_init__(self) -> None:
        require_int(self.milliseconds, "hitlWaitMs", minimum=0)

    @property
    def unit(self) -> str:
        return "hitl-wait-ms"

    def __add__(self, other: object) -> HitlWaitTime:
        if not isinstance(other, HitlWaitTime):
            raise _mixed(self, other)
        return HitlWaitTime(self.milliseconds + other.milliseconds)

    def to_payload(self) -> dict[str, Any]:
        return {"unit": self.unit, "milliseconds": self.milliseconds, "measured": True}


# --- ETA ---------------------------------------------------------------------


class Confidence(StrEnum):
    """How much the sample set behind an ETA is worth.

    ``INSUFFICIENT_DATA`` is not an error: the range is still produced and still
    useful.  It exists so that a caller cannot tell the difference between one
    sample and fifty by looking at the shape of the answer alone.
    """

    MODELLED = "modelled"
    INSUFFICIENT_DATA = "insufficient-data"


@dataclass(frozen=True, slots=True)
class DurationSample:
    """One historical observation: a size, and the machine time it took."""

    size_units: int
    duration_ms: int

    def __post_init__(self) -> None:
        require_int(self.size_units, "sample.sizeUnits", minimum=1)
        require_int(self.duration_ms, "sample.durationMs", minimum=0)

    @property
    def rate(self) -> int:
        """Scaled integer milliseconds per size unit."""

        return self.duration_ms * _RATE_SCALE // self.size_units

    def to_payload(self) -> dict[str, Any]:
        return {"sizeUnits": self.size_units, "durationMs": self.duration_ms}


@dataclass(frozen=True, slots=True)
class Eta:
    """A P50/P90 machine-time range, its sample count, and its neighbours.

    ``human_equivalent`` and ``hitl_wait`` ride along because callers always
    want all three, and they are three fields rather than one sum because
    :meth:`total` refuses to add them.  A reader who wants one number has to
    choose which one, in the open.
    """

    p50: MachineWallClock
    p90: MachineWallClock
    sample_count: int
    confidence: Confidence
    method: str
    size_units: int
    hitl_wait: HitlWaitTime | None = None
    human_equivalent: HumanEquivalentEffort | None = None

    def __post_init__(self) -> None:
        require_int(self.sample_count, "eta.sampleCount", minimum=0)
        if self.p90.milliseconds < self.p50.milliseconds:
            raise KernelError(
                code="ETA_UNAVAILABLE",
                message="an ETA whose P90 is below its P50 is not an ETA",
                recommended_action="treat as a kernel defect in the estimator",
            )

    def total(self) -> None:
        """Always raises.  There is no meaningful sum of these three quantities."""

        raise KernelError(
            code="UNIT_MISMATCH",
            message=(
                "machine wall-clock, human-equivalent effort and HITL wait have no "
                "common unit and must not be totalled"
            ),
            recommended_action="present the three figures separately",
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "machineWallClock": {
                "p50": self.p50.to_payload(),
                "p90": self.p90.to_payload(),
            },
            "sampleCount": self.sample_count,
            "confidence": str(self.confidence),
            "method": self.method,
            "sizeUnits": self.size_units,
            "hitlWait": self.hitl_wait.to_payload() if self.hitl_wait is not None else None,
            "hitlWaitMeasured": self.hitl_wait is not None,
            "humanEquivalent": (
                self.human_equivalent.to_payload() if self.human_equivalent is not None else None
            ),
            "totalsRefused": "machine time, human-equivalent effort and HITL wait are not summed",
        }

    @property
    def digest(self) -> str:
        return digest(self.to_payload())


def _percentile(values: Sequence[int], permille: int) -> int:
    """Nearest-rank percentile over pre-sorted integers, no floats anywhere."""

    count = len(values)
    index = (permille * count + 999) // 1000 - 1
    return values[min(max(index, 0), count - 1)]


def _median(values: Sequence[int]) -> int:
    count = len(values)
    middle = count // 2
    if count % 2 == 1:
        return values[middle]
    return (values[middle - 1] + values[middle]) // 2


def estimate_eta(samples: Sequence[DurationSample], size_units: int, *,
                 minimum_samples: int = MIN_SAMPLES,
                 hitl_wait: HitlWaitTime | None = None,
                 human_equivalent: HumanEquivalentEffort | None = None) -> Eta:
    """Fit a median-scaled model and report a range, never a bare point.

    The model is intentionally the simplest thing that survives contact with a
    real repository: milliseconds per size unit, taken from the median of the
    samples for P50 and the nearest-rank 90th percentile for P90, all in scaled
    integer arithmetic so two machines agree byte for byte.  With no samples at
    all the honest answer is ``ETA_UNAVAILABLE``; inventing a default here is
    how a fabricated ETA ends up in a customer-facing status page.
    """

    require_int(size_units, "sizeUnits", minimum=1)
    require_int(minimum_samples, "minimumSamples", minimum=1)
    if not samples:
        raise KernelError(
            code="ETA_UNAVAILABLE",
            message="no historical samples: an ETA cannot be estimated, only invented",
            retryable=False,
            recommended_action="record at least one completed run before requesting an ETA",
        )
    rates = sorted(sample.rate for sample in samples)
    p50_rate = _median(rates)
    p90_rate = max(_percentile(rates, 900), p50_rate)
    p50_ms = p50_rate * size_units // _RATE_SCALE
    p90_ms = max(p90_rate * size_units // _RATE_SCALE, p50_ms)
    confidence = (
        Confidence.MODELLED if len(samples) >= minimum_samples
        else Confidence.INSUFFICIENT_DATA
    )
    return Eta(
        p50=MachineWallClock(p50_ms),
        p90=MachineWallClock(p90_ms),
        sample_count=len(samples),
        confidence=confidence,
        method=f"median-scaled-integer/min-samples={minimum_samples}",
        size_units=size_units,
        hitl_wait=hitl_wait,
        human_equivalent=human_equivalent,
    )


# --- progress ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProgressSnapshot:
    """Completion measured in completed steps, with token share kept beside it.

    Invariant I1: token consumption is not progress.  The two are reported in
    the same object on purpose — the temptation is to show token share *as* a
    progress bar, so the payload states in words that it is not one, and
    :attr:`progress_permille` is computed from steps and nothing else.
    """

    run_id: str
    completed_steps: int
    total_steps: int
    tokens_used: int | None = None
    token_budget: int | None = None

    def __post_init__(self) -> None:
        require_identifier(self.run_id, "progress.runId")
        require_int(self.completed_steps, "progress.completedSteps", minimum=0)
        require_int(self.total_steps, "progress.totalSteps", minimum=0)
        if self.completed_steps > self.total_steps:
            raise KernelError(
                code="METRIC_GAP",
                message=(
                    f"run {self.run_id!r} reports {self.completed_steps} completed steps "
                    f"of {self.total_steps}"
                ),
                recommended_action="re-derive progress from the run event log",
            )
        for name in ("tokens_used", "token_budget"):
            value = getattr(self, name)
            if value is not None:
                require_int(value, f"progress.{name}", minimum=0)

    @property
    def progress_permille(self) -> int | None:
        """Completion in parts per thousand, or ``None`` when nothing is planned."""

        if self.total_steps == 0:
            return None
        return self.completed_steps * 1000 // self.total_steps

    @property
    def token_share_permille(self) -> int | None:
        if self.tokens_used is None or not self.token_budget:
            return None
        return self.tokens_used * 1000 // self.token_budget

    def to_payload(self) -> dict[str, Any]:
        return {
            "runId": self.run_id,
            "completedSteps": self.completed_steps,
            "totalSteps": self.total_steps,
            "progressPermille": self.progress_permille,
            "progressMeasured": self.total_steps > 0,
            "progressBasis": "completed-steps",
            "tokenShare": {
                "tokensUsed": self.tokens_used,
                "tokenBudget": self.token_budget,
                "sharePermille": self.token_share_permille,
                "measured": self.tokens_used is not None,
                "isProgress": False,
            },
        }


# --- spans, coverage and the critical path ----------------------------------


class Phase(StrEnum):
    """Where a span's time went.

    ``APPROVAL`` is the odd one out and is treated as such everywhere: its time
    is HITL wait, not machine time, and no code path is allowed to add it into a
    machine total.
    """

    QUEUE = "queue"
    MODEL = "model"
    TOOL = "tool"
    BUILD = "build"
    TEST = "test"
    APPROVAL = "approval"
    RETRY = "retry"
    CACHE = "cache"

    @property
    def is_human_wait(self) -> bool:
        return self is Phase.APPROVAL


@dataclass(frozen=True, slots=True)
class Span:
    """One measured (or unmeasured) interval in a run.

    ``duration_ms is None`` means the emitter never reported it.  It is not
    zero, it does not shorten the critical path, and any path that contains one
    reports itself as unmeasured.
    """

    span_id: str
    phase: Phase
    duration_ms: int | None = None
    depends_on: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_identifier(self.span_id, "span.spanId")
        if not isinstance(self.phase, Phase):
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"span {self.span_id!r} has unknown phase {self.phase!r}",
                recommended_action=f"use one of {sorted(item.value for item in Phase)}",
            )
        if self.duration_ms is not None:
            require_int(self.duration_ms, f"span[{self.span_id}].durationMs", minimum=0)
        for index, item in enumerate(self.depends_on):
            require_identifier(item, f"span[{self.span_id}].dependsOn[{index}]")

    @property
    def measured(self) -> bool:
        return self.duration_ms is not None

    def quantity(self) -> MachineWallClock | HitlWaitTime:
        """Return the span's duration as the right *type* of quantity.

        An approval span becomes :class:`HitlWaitTime`, everything else becomes
        :class:`MachineWallClock`, so the type system carries the distinction
        into whatever the caller does next.
        """

        if self.duration_ms is None:
            raise KernelError(
                code="METRIC_GAP",
                message=f"span {self.span_id!r} has no measured duration",
                recommended_action="emit the span's duration or report the gap, never assume zero",
                details={"spanId": self.span_id, "phase": str(self.phase)},
            )
        if self.phase.is_human_wait:
            return HitlWaitTime(self.duration_ms)
        return MachineWallClock(self.duration_ms)

    def to_payload(self) -> dict[str, Any]:
        return {
            "spanId": self.span_id,
            "phase": str(self.phase),
            "durationMs": self.duration_ms,
            "measured": self.measured,
            "isHumanWait": self.phase.is_human_wait,
            "dependsOn": list(self.depends_on),
        }


def coverage_report(spans: Sequence[Span],
                    required_phases: Sequence[Phase] = ()) -> dict[str, Any]:
    """Report, per phase, how much was observed and what is missing.

    A required phase with no spans is a ``gap``; a phase whose spans exist but
    carry no durations is *also* a gap.  Both are named, because an ETA built on
    a phase nobody instrumented is a guess wearing a number's clothes.
    """

    phases: dict[str, Any] = {}
    gaps: list[str] = []
    for phase in sorted(set(required_phases) | {span.phase for span in spans},
                        key=lambda item: item.value):
        owned = [span for span in spans if span.phase is phase]
        measured = [span for span in owned if span.measured]
        complete = bool(owned) and len(measured) == len(owned)
        phases[str(phase)] = {
            "spanCount": len(owned),
            "measuredSpanCount": len(measured),
            "complete": complete,
            "required": phase in set(required_phases),
        }
        if phase in set(required_phases) and not complete:
            gaps.append(str(phase))
    return {"phases": phases, "gaps": gaps, "complete": not gaps}


@dataclass(frozen=True, slots=True)
class CriticalPath:
    """The longest dependency chain, with machine time and HITL wait split.

    There is no ``duration_ms`` on this object.  There are two durations, each
    with its own ``measured`` flag, and a path that touched an unmeasured span
    reports ``None`` for the affected side rather than a total that silently
    omits it.
    """

    span_ids: tuple[str, ...]
    machine: MachineWallClock | None
    hitl_wait: HitlWaitTime | None
    unmeasured_span_ids: tuple[str, ...]

    @property
    def measured(self) -> bool:
        return not self.unmeasured_span_ids

    def to_payload(self) -> dict[str, Any]:
        return {
            "spanIds": list(self.span_ids),
            "machineWallClock": self.machine.to_payload() if self.machine is not None else None,
            "machineMeasured": self.machine is not None,
            "hitlWait": self.hitl_wait.to_payload() if self.hitl_wait is not None else None,
            "hitlWaitMeasured": self.hitl_wait is not None,
            "unmeasuredSpanIds": list(self.unmeasured_span_ids),
            "complete": self.measured,
        }


def critical_path(spans: Sequence[Span]) -> CriticalPath:
    """Longest chain through the span DAG, machine time and human wait apart.

    Chain selection uses elapsed milliseconds (an unmeasured span contributes
    nothing to the ordering and is recorded by id), but the *reported* totals
    keep the two quantities separate and go to ``None`` the moment a span on the
    chosen path was never measured.  Ties break on the span-id sequence so the
    answer is byte-identical across runs.
    """

    by_id = {span.span_id: span for span in spans}
    if len(by_id) != len(spans):
        raise KernelError(
            code="MALFORMED_INPUT",
            message="duplicate span ids in the critical-path input",
            recommended_action="deduplicate spans before computing the critical path",
        )
    if not spans:
        return CriticalPath((), MachineWallClock(0), HitlWaitTime(0), ())
    for span in spans:
        for parent in span.depends_on:
            if parent not in by_id:
                raise KernelError(
                    code="MALFORMED_INPUT",
                    message=f"span {span.span_id!r} depends on unknown span {parent!r}",
                    recommended_action="supply the complete span set",
                )

    order: list[str] = []
    indegree = {span_id: len(by_id[span_id].depends_on) for span_id in by_id}
    ready = sorted(span_id for span_id, degree in indegree.items() if degree == 0)
    while ready:
        current = ready.pop(0)
        order.append(current)
        for span_id in sorted(by_id):
            if current in by_id[span_id].depends_on:
                indegree[span_id] -= 1
                if indegree[span_id] == 0:
                    ready.append(span_id)
        ready.sort()
    if len(order) != len(by_id):
        raise KernelError(
            code="MALFORMED_INPUT",
            message="the span graph contains a cycle and has no critical path",
            recommended_action="fix the emitted dependencies; a run graph is a DAG",
        )

    best: dict[str, tuple[int, tuple[str, ...]]] = {}
    for span_id in order:
        span = by_id[span_id]
        weight = span.duration_ms or 0
        candidates = [best[parent] for parent in sorted(span.depends_on)]
        prefix = max(candidates, default=(0, ()))
        best[span_id] = (prefix[0] + weight, prefix[1] + (span_id,))
    _, chosen = max(best.values())

    machine_ms = 0
    hitl_ms = 0
    unmeasured: list[str] = []
    machine_gap = False
    hitl_gap = False
    for span_id in chosen:
        span = by_id[span_id]
        if not span.measured:
            unmeasured.append(span_id)
            if span.phase.is_human_wait:
                hitl_gap = True
            else:
                machine_gap = True
            continue
        if span.phase.is_human_wait:
            hitl_ms += span.duration_ms or 0
        else:
            machine_ms += span.duration_ms or 0
    return CriticalPath(
        span_ids=chosen,
        machine=None if machine_gap else MachineWallClock(machine_ms),
        hitl_wait=None if hitl_gap else HitlWaitTime(hitl_ms),
        unmeasured_span_ids=tuple(unmeasured),
    )


# --- cost --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MeterPrice:
    """The price of ``per_units`` units of one meter, exactly.

    ``per_units`` is restricted to a power of ten so that the division stays
    exact in :class:`~decimal.Decimal`; a price of "3 dollars per 1000 tokens"
    must not become a repeating decimal that two services round differently.
    """

    meter_key: str
    price: Decimal
    per_units: int = 1000

    def __post_init__(self) -> None:
        require_str(self.meter_key, "price.meterKey", max_length=256)
        require_decimal(self.price, "price.price", minimum=Decimal(0))
        require_int(self.per_units, "price.perUnits", minimum=1)
        text = str(self.per_units)
        if text != "1" + "0" * (len(text) - 1):
            # A non-power-of-ten divisor makes the price division non-terminating,
            # and two services then round the same usage to two different bills.
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"price.perUnits={self.per_units} must be a power of ten",
                recommended_action="express the price per 1, 1000 or 1000000 units",
            )

    def cost_for(self, quantity: int) -> Decimal:
        return _quantize(self.price * Decimal(quantity) / Decimal(self.per_units))

    def to_payload(self) -> dict[str, Any]:
        return {"meterKey": self.meter_key, "price": self.price, "perUnits": self.per_units}


@dataclass(frozen=True, slots=True)
class PriceProfile:
    """A versioned price list plus the tools it is allowed to price.

    Invariant I3: the price list is versioned and the version travels with every
    figure derived from it, so a cost report can be re-derived and disputed
    rather than merely believed.  ``allowed_tools`` is an allow-list: a usage
    record naming a tool the profile does not know is denied, never priced at a
    convenient zero.
    """

    profile_id: str
    version: str
    currency: str
    prices: Mapping[str, MeterPrice]
    allowed_tools: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_identifier(self.profile_id, "pricingProfile.profileId")
        require_str(self.version, "pricingProfile.version", max_length=64)
        require_str(self.currency, "pricingProfile.currency", max_length=8)
        if not self.prices:
            raise KernelError(
                code="PRICE_PROFILE_MISSING",
                message="an empty price profile cannot price anything",
                recommended_action="bind a price list before requesting a cost report",
            )

    def price_for(self, meter_key: str) -> MeterPrice:
        price = self.prices.get(meter_key)
        if price is None:
            raise KernelError(
                code="PRICE_PROFILE_MISSING",
                message=(
                    f"price profile {self.profile_id!r}@{self.version} has no price for "
                    f"meter {meter_key!r}"
                ),
                retryable=False,
                recommended_action="add the meter to the price profile; do not price it at zero",
                details={"meterKey": meter_key, "profileVersion": self.version},
            )
        return price

    def to_payload(self) -> dict[str, Any]:
        return {
            "profileId": self.profile_id,
            "version": self.version,
            "currency": self.currency,
            "meters": sorted(self.prices),
            "allowedTools": sorted(self.allowed_tools),
        }


@dataclass(frozen=True, slots=True)
class UsageRecord:
    """What one component reported it consumed.

    ``quantity is None`` is the whole point of this type: the provider returned
    a response without usage accounting.  That is a measurement failure and it
    is carried as one all the way to the total.
    """

    component_id: str
    meter_key: str
    quantity: int | None
    tool: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        require_identifier(self.component_id, "usage.componentId")
        require_str(self.meter_key, "usage.meterKey", max_length=256)
        if self.quantity is not None:
            require_int(self.quantity, "usage.quantity", minimum=0)

    @property
    def measured(self) -> bool:
        return self.quantity is not None


@dataclass(frozen=True, slots=True)
class CostComponent:
    """One priced (or explicitly unpriceable) line of a cost report."""

    component_id: str
    meter_key: str
    quantity: int | None
    unit_price: Decimal
    per_units: int
    cost: Decimal | None
    measured: bool
    reason: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "componentId": self.component_id,
            "meterKey": self.meter_key,
            "quantity": self.quantity,
            "unitPrice": self.unit_price,
            "perUnits": self.per_units,
            "cost": self.cost,
            "measured": self.measured,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class CostReport:
    """Per-component costs, and a total that refuses to be complete on request.

    ``total`` is ``None`` whenever any component is unmeasured.  The measured
    part is still published as ``measured_subtotal`` — hiding it would be its
    own dishonesty — but it is a different field with a different name, so a
    dashboard that prints ``total`` prints nothing rather than a number that is
    quietly too small.
    """

    report_id: str
    currency: str
    price_profile_id: str
    price_profile_version: str
    components: tuple[CostComponent, ...]

    @property
    def unmeasured_component_ids(self) -> tuple[str, ...]:
        return tuple(sorted(item.component_id for item in self.components if not item.measured))

    @property
    def partial(self) -> bool:
        return bool(self.unmeasured_component_ids)

    @property
    def measured_subtotal(self) -> Decimal:
        subtotal = Decimal(0)
        for item in self.components:
            if item.cost is not None:
                subtotal += item.cost
        return _quantize(subtotal)

    @property
    def total(self) -> Decimal | None:
        """The final figure, or ``None`` when any component went unmeasured."""

        return None if self.partial else self.measured_subtotal

    def to_payload(self) -> dict[str, Any]:
        return {
            "costReportId": self.report_id,
            "currency": self.currency,
            "priceProfile": {
                "profileId": self.price_profile_id,
                "version": self.price_profile_version,
            },
            "components": [item.to_payload()
                           for item in sorted(self.components, key=lambda c: c.component_id)],
            "total": self.total,
            "measuredSubtotal": self.measured_subtotal,
            "partial": self.partial,
            "final": not self.partial,
            "unmeasuredComponentIds": list(self.unmeasured_component_ids),
        }

    @property
    def digest(self) -> str:
        return digest(self.to_payload())


def price_usage(usage: Sequence[UsageRecord], profile: PriceProfile, *,
                report_id: str = "cost-report") -> CostReport:
    """Price every usage record, keeping unmeasured ones unmeasured.

    A record whose provider reported no usage yields ``cost: None`` and
    ``measured: false``.  It does *not* yield ``0``: this is the silent-zero
    defect class, and it has shipped in this repository three times, each time
    as an under-reported bill that nobody could explain afterwards.  A record
    naming a tool outside the profile's allow-list is denied outright.
    """

    require_identifier(report_id, "costReportId")
    allowed = set(profile.allowed_tools)
    components: list[CostComponent] = []
    for record in usage:
        if record.tool and allowed and record.tool not in allowed:
            raise KernelError(
                code="TOOL_DENIED",
                message=(
                    f"usage record {record.component_id!r} names tool {record.tool!r}, "
                    f"which price profile {profile.profile_id!r} does not authorise"
                ),
                retryable=False,
                recommended_action="add the tool to the price profile or stop invoking it",
                details={"tool": record.tool, "componentId": record.component_id},
            )
        price = profile.price_for(record.meter_key)
        if record.quantity is None:
            components.append(CostComponent(
                component_id=record.component_id,
                meter_key=record.meter_key,
                quantity=None,
                unit_price=price.price,
                per_units=price.per_units,
                cost=None,
                measured=False,
                reason=record.note or "provider reported no usage for this component",
            ))
            continue
        components.append(CostComponent(
            component_id=record.component_id,
            meter_key=record.meter_key,
            quantity=record.quantity,
            unit_price=price.price,
            per_units=price.per_units,
            cost=price.cost_for(record.quantity),
            measured=True,
            reason="",
        ))
    return CostReport(
        report_id=report_id,
        currency=profile.currency,
        price_profile_id=profile.profile_id,
        price_profile_version=profile.version,
        components=tuple(components),
    )


def reconcile_billing(report: CostReport, invoiced: Decimal | None, *,
                      tolerance: Decimal = Decimal("0.000001")) -> dict[str, Any]:
    """Compare the derived total with what the provider says it charged.

    A partial report cannot be reconciled at all — the comparison would be
    between a complete invoice and an incomplete derivation, and "close enough"
    is exactly the reasoning that hides a missing component.  An absent invoice
    is reported as unreconciled, not as agreement.
    """

    if invoiced is None:
        return {"reconciled": False, "reason": "no provider invoice was supplied",
                "invoiced": None, "derived": report.total, "measured": False}
    require_decimal(invoiced, "providerInvoice.amount", minimum=Decimal(0))
    if report.partial:
        raise KernelError(
            code="BILLING_RECONCILIATION_FAILED",
            message=(
                "a partial cost report cannot be reconciled against an invoice; "
                f"unmeasured components: {list(report.unmeasured_component_ids)}"
            ),
            retryable=False,
            recommended_action="recover the missing usage records, then reconcile",
            details={"unmeasuredComponentIds": list(report.unmeasured_component_ids)},
        )
    derived = report.total or Decimal(0)
    delta = derived - invoiced
    if abs(delta) > tolerance:
        raise KernelError(
            code="BILLING_RECONCILIATION_FAILED",
            message=(
                f"derived cost {derived} does not match the invoiced {invoiced} "
                f"(delta {delta})"
            ),
            retryable=False,
            recommended_action="re-price against the invoiced price profile version",
            details={"derived": str(derived), "invoiced": str(invoiced), "delta": str(delta)},
        )
    return {"reconciled": True, "reason": "", "invoiced": invoiced, "derived": derived,
            "measured": True}


# --- budget ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """One immutable movement in a budget ledger."""

    sequence: int
    kind: str
    reservation_id: str
    amount: Decimal
    remaining_after: Decimal

    def to_payload(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "kind": self.kind,
            "reservationId": self.reservation_id,
            "amount": self.amount,
            "remainingAfter": self.remaining_after,
        }


class BudgetLedger:
    """Reserve / commit / release with exact Decimal arithmetic.

    A reservation holds money that has not been spent yet, which is what stops
    two concurrent steps from each seeing the same headroom.  ``remaining`` may
    legitimately be exactly ``0``; that is a measured zero and it is not the
    same fact as an unmeasured cost, which is why this class deals only in
    Decimals it was actually given.  Reserving beyond the remaining balance
    raises ``BUDGET_EXHAUSTED`` instead of going negative.
    """

    def __init__(self, budget_id: str, limit: Decimal, *, currency: str = "USD") -> None:
        require_identifier(budget_id, "budget.budgetId")
        require_decimal(limit, "budget.limit", minimum=Decimal(0))
        self._budget_id = budget_id
        self._limit = _quantize(limit)
        self._currency = require_str(currency, "budget.currency", max_length=8)
        self._reserved: dict[str, Decimal] = {}
        self._committed: dict[str, Decimal] = {}
        self._entries: list[LedgerEntry] = []

    @property
    def budget_id(self) -> str:
        return self._budget_id

    @property
    def limit(self) -> Decimal:
        return self._limit

    @property
    def reserved(self) -> Decimal:
        return _quantize(sum(self._reserved.values(), Decimal(0)))

    @property
    def committed(self) -> Decimal:
        return _quantize(sum(self._committed.values(), Decimal(0)))

    @property
    def remaining(self) -> Decimal:
        """Exact remaining balance.  Zero is a legal, meaningful value."""

        return _quantize(self._limit - self.reserved - self.committed)

    @property
    def entries(self) -> tuple[LedgerEntry, ...]:
        return tuple(self._entries)

    def _record(self, kind: str, reservation_id: str, amount: Decimal) -> LedgerEntry:
        entry = LedgerEntry(
            sequence=len(self._entries) + 1,
            kind=kind,
            reservation_id=reservation_id,
            amount=amount,
            remaining_after=self.remaining,
        )
        self._entries.append(entry)
        return entry

    def reserve(self, reservation_id: str, amount: Decimal) -> LedgerEntry:
        """Hold ``amount`` against the budget, or raise ``BUDGET_EXHAUSTED``."""

        require_identifier(reservation_id, "reservationId")
        require_decimal(amount, "reservation.amount", minimum=Decimal(0))
        amount = _quantize(amount)
        existing = self._reserved.get(reservation_id)
        if existing is not None:
            if existing != amount:
                raise KernelError(
                    code="IDEMPOTENCY_CONFLICT",
                    message=(
                        f"reservation {reservation_id!r} already holds {existing}; "
                        f"cannot re-reserve {amount}"
                    ),
                    recommended_action="release the reservation before re-reserving",
                )
            return self._entries[
                max(index for index, entry in enumerate(self._entries)
                    if entry.reservation_id == reservation_id and entry.kind == "reserve")
            ]
        if reservation_id in self._committed:
            raise KernelError(
                code="IDEMPOTENCY_CONFLICT",
                message=f"reservation {reservation_id!r} has already been committed",
                recommended_action="use a fresh reservation id",
            )
        if amount > self.remaining:
            raise KernelError(
                code="BUDGET_EXHAUSTED",
                message=(
                    f"budget {self._budget_id!r} has {self.remaining} {self._currency} "
                    f"remaining and cannot reserve {amount}"
                ),
                retryable=False,
                recommended_action="raise the budget or shrink the plan",
                details={"remaining": str(self.remaining), "requested": str(amount)},
            )
        self._reserved[reservation_id] = amount
        return self._record("reserve", reservation_id, amount)

    def commit(self, reservation_id: str, actual: Decimal) -> LedgerEntry:
        """Turn a reservation into spend, settling the difference exactly."""

        require_identifier(reservation_id, "reservationId")
        require_decimal(actual, "commit.actual", minimum=Decimal(0))
        actual = _quantize(actual)
        held = self._reserved.get(reservation_id)
        if held is None:
            if self._committed.get(reservation_id) == actual:
                return self._entries[
                    max(index for index, entry in enumerate(self._entries)
                        if entry.reservation_id == reservation_id and entry.kind == "commit")
                ]
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"reservation {reservation_id!r} is not held and cannot be committed",
                recommended_action="reserve before committing",
            )
        overspend = actual - held
        if overspend > 0 and overspend > self.remaining:
            raise KernelError(
                code="BUDGET_EXHAUSTED",
                message=(
                    f"committing {actual} against reservation {reservation_id!r} of {held} "
                    f"overruns the remaining {self.remaining}"
                ),
                retryable=False,
                recommended_action="raise the budget before committing the overspend",
                details={"reserved": str(held), "actual": str(actual)},
            )
        del self._reserved[reservation_id]
        self._committed[reservation_id] = actual
        return self._record("commit", reservation_id, actual)

    def release(self, reservation_id: str) -> LedgerEntry:
        """Give a reservation back untouched.  Releasing twice is not an error."""

        require_identifier(reservation_id, "reservationId")
        held = self._reserved.pop(reservation_id, None)
        return self._record("release", reservation_id, held if held is not None else Decimal(0))

    def to_payload(self) -> dict[str, Any]:
        return {
            "budgetId": self._budget_id,
            "currency": self._currency,
            "limit": self._limit,
            "reserved": self.reserved,
            "committed": self.committed,
            "remaining": self.remaining,
            "exhausted": self.remaining == 0,
            "entries": [entry.to_payload() for entry in self._entries],
        }


# --- cache savings and SLOs --------------------------------------------------


@dataclass(frozen=True, slots=True)
class CacheSavings:
    """Cache effectiveness, with unmeasured counters kept unmeasured."""

    hits: int | None = None
    misses: int | None = None
    saved_tokens: int | None = None

    def __post_init__(self) -> None:
        for name in ("hits", "misses", "saved_tokens"):
            value = getattr(self, name)
            if value is not None:
                require_int(value, f"cacheMetrics.{name}", minimum=0)

    @property
    def hit_rate_permille(self) -> int | None:
        if self.hits is None or self.misses is None:
            return None
        total = self.hits + self.misses
        if total == 0:
            return None
        return self.hits * 1000 // total

    def to_payload(self) -> dict[str, Any]:
        """Render the counters.

        The flag is ``countersMeasured``, not ``measured``.  These counters and
        the *saving priced from them* are two different measurements that can
        succeed independently: a cache can report hits and misses while failing
        to report the tokens it saved, and vice versa.  They were both called
        ``measured`` once, and spreading this payload into the saving's dict
        silently overwrote the saving's flag with the counters' — an unmeasured
        cost was reported as measured, which is the silent-zero defect inverted.
        Distinct names make that collision impossible to write again.
        """

        return {
            "hits": self.hits,
            "misses": self.misses,
            "savedTokens": self.saved_tokens,
            "hitRatePermille": self.hit_rate_permille,
            "countersMeasured": self.hits is not None and self.misses is not None,
        }


def cache_savings(metrics: CacheSavings, profile: PriceProfile,
                  meter_key: str) -> dict[str, Any]:
    """Price the tokens the cache avoided, or report the saving as unmeasured."""

    if metrics.saved_tokens is None:
        return {**metrics.to_payload(), "savedCost": None, "measured": False,
                "reason": "cache did not report saved tokens"}
    price = profile.price_for(meter_key)
    return {**metrics.to_payload(), "savedCost": price.cost_for(metrics.saved_tokens),
            "measured": True, "reason": ""}


@dataclass(frozen=True, slots=True)
class SloMetric:
    """One SLO line: the observed percentile, its target, and whether it was met.

    ``met`` is ``None`` when the percentile could not be measured.  A missing
    measurement is not a breach and is emphatically not a pass.
    """

    name: str
    observed_ms: int | None
    target_ms: int | None

    @property
    def met(self) -> bool | None:
        if self.observed_ms is None or self.target_ms is None:
            return None
        return self.observed_ms <= self.target_ms

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "observedMs": self.observed_ms,
            "targetMs": self.target_ms,
            "measured": self.observed_ms is not None,
            "met": self.met,
        }


def slo_metrics(durations_ms: Sequence[int],
                targets: Mapping[str, int] | None = None) -> tuple[SloMetric, ...]:
    """P50/P95 machine wall-clock against declared targets, integers throughout."""

    targets = dict(targets or {})
    if not durations_ms:
        return (
            SloMetric("machine-wall-clock-p50", None, targets.get("machine-wall-clock-p50")),
            SloMetric("machine-wall-clock-p95", None, targets.get("machine-wall-clock-p95")),
        )
    ordered = sorted(require_int(value, "slo.durationMs", minimum=0) for value in durations_ms)
    return (
        SloMetric("machine-wall-clock-p50", _median(ordered),
                  targets.get("machine-wall-clock-p50")),
        SloMetric("machine-wall-clock-p95", _percentile(ordered, 950),
                  targets.get("machine-wall-clock-p95")),
    )


# --- durable side effect -----------------------------------------------------


def record_billing(events: EventStore, stream_id: str, record: Mapping[str, Any], *,
                   fencing_token: int) -> Mapping[str, Any]:
    """Append a billing record once, under the current lease.

    The idempotency key is the record's own digest, so a redelivered billing
    record returns the original event rather than billing twice, and a worker
    whose lease has been superseded is fenced out rather than writing a bill
    behind the current owner's back.
    """

    require_int(fencing_token, "fencing_token", minimum=1)
    body = require_mapping(record, "billingRecord")
    event = events.append(stream_id, body, idempotency_key=digest(body),
                          fencing_token=fencing_token)
    return {
        "sequence": event.sequence,
        "eventId": event.event_id,
        "hashChain": event.hash_chain,
        "billingRecordDigest": digest(body),
    }


# --- decoding ----------------------------------------------------------------


def _decode_span(payload: Mapping[str, Any]) -> Span:
    reject_unknown_fields(payload, {"spanId", "phase", "durationMs", "dependsOn"},
                          field_name="span")
    phase = require_str(payload.get("phase"), "span.phase", max_length=32)
    if phase not in {item.value for item in Phase}:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"unknown span phase {phase!r}",
            recommended_action=f"use one of {sorted(item.value for item in Phase)}",
        )
    raw_duration = payload.get("durationMs")
    return Span(
        span_id=require_identifier(payload.get("spanId"), "span.spanId"),
        phase=Phase(phase),
        duration_ms=None if raw_duration is None else require_int(
            raw_duration, "span.durationMs", minimum=0),
        depends_on=require_str_seq(payload.get("dependsOn", ()), "span.dependsOn"),
    )


def _decode_usage(payload: Mapping[str, Any]) -> UsageRecord:
    reject_unknown_fields(payload, {"componentId", "meterKey", "quantity", "tool", "note"},
                          field_name="usage record")
    raw_quantity = payload.get("quantity")
    return UsageRecord(
        component_id=require_identifier(payload.get("componentId"), "usage.componentId"),
        meter_key=require_str(payload.get("meterKey"), "usage.meterKey", max_length=256),
        quantity=None if raw_quantity is None else require_int(
            raw_quantity, "usage.quantity", minimum=0),
        tool=str(payload.get("tool", "")),
        note=str(payload.get("note", "")),
    )


def _decode_profile(payload: Mapping[str, Any]) -> PriceProfile:
    reject_unknown_fields(payload, {"profileId", "version", "currency", "prices", "allowedTools"},
                          field_name="pricing_profile")
    prices: dict[str, MeterPrice] = {}
    for item in payload.get("prices", ()):
        body = require_mapping(item, "pricing_profile.prices[]")
        reject_unknown_fields(body, {"meterKey", "price", "perUnits"}, field_name="price")
        meter_key = require_str(body.get("meterKey"), "price.meterKey", max_length=256)
        prices[meter_key] = MeterPrice(
            meter_key=meter_key,
            price=require_decimal(body.get("price"), "price.price", minimum=Decimal(0)),
            per_units=require_int(body.get("perUnits", 1000), "price.perUnits", minimum=1),
        )
    return PriceProfile(
        profile_id=require_identifier(payload.get("profileId"), "pricing_profile.profileId"),
        version=require_str(payload.get("version"), "pricing_profile.version", max_length=64),
        currency=require_str(payload.get("currency", "USD"), "pricing_profile.currency",
                             max_length=8),
        prices=prices,
        allowed_tools=require_str_seq(payload.get("allowedTools", ()),
                                      "pricing_profile.allowedTools"),
    )


# --- registry entry point ----------------------------------------------------


@register("cost-eta-observability")
def handle(request: Mapping[str, Any]) -> Mapping[str, Any]:
    """Registry entry point.

    The status is the interesting part.  A run with an unmeasured cost component
    or an instrumentation gap returns ``PARTIAL`` — the numbers are published,
    they are simply not final — and an interrupted run raises rather than
    reporting an ETA for something that stopped.  Nothing here widens ``PARTIAL``
    into ``SUCCEEDED``.
    """

    reject_unknown_fields(
        request,
        {"run_events", "historical_runs", "repo_features", "model_tool_usage",
         "cache_metrics", "pricing_profile"},
        field_name="cost-eta-observability request",
    )
    run_events = require_mapping(request.get("run_events"), "run_events")
    reject_unknown_fields(
        run_events,
        {"runId", "repoSnapshotSha", "spans", "completedSteps", "totalSteps", "interrupted",
         "requiredPhases", "note"},
        field_name="run_events",
    )
    historical = require_mapping(request.get("historical_runs", {}), "historical_runs")
    reject_unknown_fields(historical, {"samples", "minimumSamples", "durationsMs", "sloTargets"},
                          field_name="historical_runs")
    features = require_mapping(request.get("repo_features"), "repo_features")
    reject_unknown_fields(features, {"repoSnapshotSha", "sizeUnits", "humanEquivalent"},
                          field_name="repo_features")
    usage_body = require_mapping(request.get("model_tool_usage", {}), "model_tool_usage")
    reject_unknown_fields(usage_body, {"records", "tokensUsed", "tokenBudget", "providerInvoice"},
                          field_name="model_tool_usage")
    cache_body = require_mapping(request.get("cache_metrics", {}), "cache_metrics")
    reject_unknown_fields(cache_body, {"hits", "misses", "savedTokens", "meterKey"},
                          field_name="cache_metrics")
    profile = _decode_profile(require_mapping(request.get("pricing_profile"), "pricing_profile"))

    run_id = require_identifier(run_events.get("runId"), "run_events.runId")
    snapshot = require_str(run_events.get("repoSnapshotSha"), "run_events.repoSnapshotSha",
                           max_length=128)
    feature_snapshot = require_str(features.get("repoSnapshotSha"),
                                   "repo_features.repoSnapshotSha", max_length=128)
    if feature_snapshot != snapshot:
        raise KernelError(
            code="STALE_SNAPSHOT",
            message=(
                f"repo features are bound to snapshot {feature_snapshot} but the run is on "
                f"{snapshot}; sizing this run from them would be a guess"
            ),
            retryable=False,
            recommended_action="re-derive repo features for the run's snapshot",
            details={"runSnapshot": snapshot, "featureSnapshot": feature_snapshot},
        )

    if require_bool(run_events.get("interrupted", False), "run_events.interrupted"):
        raise KernelError(
            code="ETA_UNAVAILABLE",
            message=f"run {run_id!r} was interrupted; there is no ETA for a run that stopped",
            retryable=False,
            interrupted=True,
            recommended_action="reconcile the run, then request an ETA for the resumed run",
            details={"runId": run_id},
        )

    spans = tuple(_decode_span(require_mapping(item, "run_events.spans[]"))
                  for item in run_events.get("spans", ()))
    declared_phases = require_str_seq(run_events.get("requiredPhases", ()),
                                      "run_events.requiredPhases")
    known_phases = {phase.value for phase in Phase}
    unknown_phases = sorted(set(declared_phases) - known_phases)
    if unknown_phases:
        # Dropping an unrecognised required phase made coverage look complete by
        # deleting the requirement that was not met.  A caller who asks for a
        # phase this build does not know about must be told, not quietly served
        # a report that answers an easier question.
        raise KernelError(
            code="MALFORMED_INPUT",
            message=(
                f"run_events.requiredPhases names phases this build does not know: "
                f"{unknown_phases}"
            ),
            retryable=False,
            recommended_action=f"use one of {sorted(known_phases)}",
            details={"unknownPhases": unknown_phases, "knownPhases": sorted(known_phases)},
        )
    required_phases = tuple(Phase(item) for item in declared_phases)
    coverage = coverage_report(spans, required_phases)
    path = critical_path(spans)

    progress = ProgressSnapshot(
        run_id=run_id,
        completed_steps=require_int(run_events.get("completedSteps", 0),
                                    "run_events.completedSteps", minimum=0),
        total_steps=require_int(run_events.get("totalSteps", 0), "run_events.totalSteps",
                                minimum=0),
        tokens_used=(None if usage_body.get("tokensUsed") is None
                     else require_int(usage_body.get("tokensUsed"), "tokensUsed", minimum=0)),
        token_budget=(None if usage_body.get("tokenBudget") is None
                      else require_int(usage_body.get("tokenBudget"), "tokenBudget", minimum=0)),
    )

    samples = tuple(
        DurationSample(
            size_units=require_int(require_mapping(item, "samples[]").get("sizeUnits"),
                                   "sample.sizeUnits", minimum=1),
            duration_ms=require_int(require_mapping(item, "samples[]").get("durationMs"),
                                    "sample.durationMs", minimum=0),
        )
        for item in historical.get("samples", ())
    )
    human_payload = features.get("humanEquivalent")
    human: HumanEquivalentEffort | None = None
    if human_payload is not None:
        body = require_mapping(human_payload, "repo_features.humanEquivalent")
        reject_unknown_fields(body, {"milliHours", "method", "basis"},
                              field_name="humanEquivalent")
        human = HumanEquivalentEffort(
            milli_hours=require_int(body.get("milliHours"), "humanEquivalent.milliHours",
                                    minimum=0),
            method=require_str(body.get("method"), "humanEquivalent.method", max_length=256),
            basis=str(body.get("basis", "")),
        )
    eta = estimate_eta(
        samples,
        require_int(features.get("sizeUnits"), "repo_features.sizeUnits", minimum=1),
        minimum_samples=require_int(historical.get("minimumSamples", MIN_SAMPLES),
                                    "historical_runs.minimumSamples", minimum=1),
        hitl_wait=path.hitl_wait,
        human_equivalent=human,
    )

    usage = tuple(_decode_usage(require_mapping(item, "model_tool_usage.records[]"))
                  for item in usage_body.get("records", ()))
    cost = price_usage(usage, profile, report_id=f"cost-{run_id}")
    invoice_body = usage_body.get("providerInvoice")
    invoiced = (
        None if invoice_body is None
        else require_decimal(require_mapping(invoice_body, "providerInvoice").get("amount"),
                             "providerInvoice.amount", minimum=Decimal(0))
    )
    reconciliation = (
        {"reconciled": False, "reason": "cost report is partial", "invoiced": None,
         "derived": None, "measured": False}
        if cost.partial and invoiced is None
        else reconcile_billing(cost, invoiced)
    )

    cache = CacheSavings(
        hits=None if cache_body.get("hits") is None else require_int(
            cache_body.get("hits"), "cache_metrics.hits", minimum=0),
        misses=None if cache_body.get("misses") is None else require_int(
            cache_body.get("misses"), "cache_metrics.misses", minimum=0),
        saved_tokens=None if cache_body.get("savedTokens") is None else require_int(
            cache_body.get("savedTokens"), "cache_metrics.savedTokens", minimum=0),
    )
    cache_meter = str(cache_body.get("meterKey", ""))
    savings = (
        cache_savings(cache, profile, cache_meter) if cache_meter and cache.saved_tokens is not None
        else {**cache.to_payload(), "savedCost": None, "measured": False,
              "reason": "no cache meter or no reported saved tokens"}
    )

    slos = slo_metrics(
        tuple(require_int(value, "historical_runs.durationsMs[]", minimum=0)
              for value in historical.get("durationsMs", ())),
        {key: require_int(value, f"sloTargets.{key}", minimum=0)
         for key, value in require_mapping(historical.get("sloTargets", {}),
                                           "sloTargets").items()},
    )

    billing_record = {
        "billingRecordId": f"billing-{run_id}",
        "runId": run_id,
        "repoSnapshotSha": snapshot,
        "currency": profile.currency,
        "amount": cost.total,
        "measuredSubtotal": cost.measured_subtotal,
        "final": not cost.partial,
        "priceProfile": profile.to_payload(),
        "costReportDigest": cost.digest,
        "reconciliation": reconciliation,
    }

    partial = cost.partial or not coverage["complete"] or not path.measured
    return {
        "status": Status.PARTIAL if partial else Status.SUCCEEDED,
        "progress_snapshot": progress.to_payload(),
        "eta_distribution": eta.to_payload(),
        "critical_path": path.to_payload() | {"coverage": coverage},
        "cost_breakdown": cost.to_payload() | {"cacheSavings": savings},
        "billing_record": billing_record,
        "slo_metrics": [item.to_payload() for item in slos],
    }
