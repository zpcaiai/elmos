"""Repository gym and golden routes: benchmarks that cannot move their own goalposts.

A benchmark lies in three ways, and each one has a countermeasure here.

It lies by **editing the acceptance after seeing the result**.  So acceptance is
frozen at registration: :meth:`GymRegistry.register_route` computes an
acceptance digest and stores it, and :meth:`GymRegistry.score` refuses any run
whose route or run carries a different one.  Loosening a criterion is then a
visible ``ACCEPTANCE_MUTATED`` under a new route version, not a quiet edit that
turns yesterday's failure into today's pass.

It lies by **not being reproducible**.  A score is only meaningful against a
pinned fixture and a pinned toolchain, so every scorecard carries a
``reproducible`` flag that is true only when the run's fixture digest *and*
toolchain fingerprint match the ones the route was registered with.  A
non-reproducible run still produces a scorecard — hiding it would lose the
information — but it can never reach certification tier E2 or above.

It lies by **hiding what it did not measure**.  A criterion nobody reported is
``measured: false`` with ``passed: null``, never a pass and never a zero; a
skipped step is ``SKIPPED``; an interrupted run is ``INTERRUPTED``.  The
certification ladder E1–E5 is a prefix ladder that stops at the first unmet
rung, which is how "the static checks passed" is kept from being read as
"certified for production" — E1 is the first rung, not the destination.

Route definitions are read with :func:`parse_yaml_subset`, a deliberately tiny
stdlib reader whose exact limits are documented on the function.  It exists
because a benchmark's definition should be parsed by something a reviewer can
read in one sitting, and because the alternative was a dependency.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .contracts import (
    digest,
    reject_unknown_fields,
    require_bool,
    require_identifier,
    require_int,
    require_mapping,
    require_str,
    require_str_seq,
)
from .errors import Category, KernelError, register_codes
from .ports import Clock, EventStore
from .registry import register

__all__ = [
    "Acceptance",
    "AcceptanceCriterion",
    "CERTIFICATION_LADDER",
    "ChaosOutcome",
    "CommercialMeasurement",
    "CommercialThresholds",
    "CriterionResult",
    "FixtureRepository",
    "GoldenRoute",
    "GymRegistry",
    "RegressionReport",
    "RouteRun",
    "RouteStep",
    "Scorecard",
    "StepEvidence",
    "StepStatus",
    "assert_no_regression",
    "certify",
    "compare",
    "handle",
    "parse_yaml_subset",
    "record_gym_run",
    "require_reproducible",
    "route_from_yaml",
    "run",
    "validate_fixture_set",
]

register_codes(
    Category.VERIFICATION,
    "BENCHMARK_REGRESSION",
    "NON_REPRODUCIBLE",
    "ACCEPTANCE_MUTATED",
)
register_codes(
    Category.SEMANTIC,
    "ENVIRONMENT_DRIFT",
    "ROUTE_YAML_UNSUPPORTED",
    "ROUTE_NOT_REGISTERED",
    "GYM_FIXTURE_SET_INVALID",
)
register_codes(
    Category.RELEASE,
    "COMMERCIAL_GATE_FAILED",
)

_KEY_RE = re.compile(r"^([A-Za-z0-9_.\-]+):(?:[ \t]+(.*))?$")
_UNSUPPORTED_SCALAR_PREFIXES = "[{&*!|>%@`"


def _yaml_error(line: int, detail: str) -> KernelError:
    return KernelError(
        code="ROUTE_YAML_UNSUPPORTED",
        message=f"line {line}: {detail}",
        retryable=False,
        recommended_action=(
            "rewrite the file inside the supported subset; see parse_yaml_subset's "
            "docstring for the exact limits"
        ),
        details={"line": line},
    )


def _scalar(text: str, line: int) -> str:
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        inner = text[1:-1]
        if "\\" in inner:
            raise _yaml_error(line, "escape sequences in quoted scalars are not supported")
        if text[0] in inner:
            raise _yaml_error(line, "nested quotes in a quoted scalar are not supported")
        return inner
    if text and text[0] in _UNSUPPORTED_SCALAR_PREFIXES:
        raise _yaml_error(
            line,
            f"scalar starting with {text[0]!r} (flow collection, anchor, alias, tag, "
            "block scalar or directive) is not supported",
        )
    if text.endswith(":"):
        raise _yaml_error(line, "a scalar may not end with a colon")
    return text


def _parse_block(lines: Sequence[tuple[int, int, str]], index: int,
                 indent: int) -> tuple[Any, int]:
    if lines[index][2].startswith("- ") or lines[index][2] == "-":
        items: list[str] = []
        while index < len(lines) and lines[index][1] == indent:
            line, _, content = lines[index]
            if not content.startswith("- "):
                raise _yaml_error(line, "mixed sequence and mapping entries at one indent")
            entry = content[2:].strip()
            if not entry:
                raise _yaml_error(line, "empty sequence entry")
            if _KEY_RE.match(entry) or entry.endswith(":"):
                raise _yaml_error(line, "mappings nested inside a sequence are not supported")
            items.append(_scalar(entry, line))
            index += 1
        return tuple(items), index

    result: dict[str, Any] = {}
    while index < len(lines) and lines[index][1] == indent:
        line, _, content = lines[index]
        if content.startswith("- "):
            raise _yaml_error(line, "sequence entry where a mapping key was expected")
        match = _KEY_RE.match(content)
        if match is None:
            raise _yaml_error(line, f"unsupported line {content!r}; expected 'key: value'")
        key, rest = match.group(1), (match.group(2) or "").strip()
        if key in result:
            raise _yaml_error(line, f"duplicate key {key!r}; a silently overwritten key "
                                    "makes the file mean two things")
        index += 1
        if rest:
            result[key] = _scalar(rest, line)
            continue
        if index >= len(lines) or lines[index][1] <= indent:
            raise _yaml_error(
                line, f"key {key!r} has neither a value nor an indented block; "
                      "null values are not supported")
        result[key], index = _parse_block(lines, index, lines[index][1])
    return result, index


def parse_yaml_subset(text: str) -> Mapping[str, Any]:
    """Read a deliberately tiny subset of YAML, with the stdlib only.

    **Supported, and nothing else:** a single document whose top level is a
    mapping; nested mappings written ``key: value`` or ``key:`` followed by an
    indented block; block sequences of plain scalars written ``- item``;
    single- or double-quoted scalars without escapes; whole-line ``#``
    comments; blank lines.  Indentation is spaces only, in multiples of two,
    and a child block must be indented deeper than its parent.

    **Rejected with ``ROUTE_YAML_UNSUPPORTED``:** tabs; document separators and
    multiple documents; anchors, aliases, tags and directives; flow collections
    (``[a, b]``, ``{a: b}``); block scalars (``|``, ``>``); mappings nested
    inside sequences; keys with neither a value nor a block; duplicate keys;
    escapes inside quoted scalars.

    **Every scalar is returned as a string.**  There is no type coercion at
    all: ``true``, ``null`` and ``42`` come back as ``"true"``, ``"null"`` and
    ``"42"``.  Guessing types is how a config file and its reader come to
    disagree about what ``no`` means, and this reader would rather hand the
    caller a string it can decode deliberately.
    """

    lines: list[tuple[int, int, str]] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        if "\t" in raw:
            raise _yaml_error(number, "tabs are not supported; indent with spaces")
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped in {"---", "..."} or stripped.startswith("--- "):
            raise _yaml_error(number, "document separators and multi-document files "
                                      "are not supported")
        if stripped.startswith("%"):
            raise _yaml_error(number, "directives are not supported")
        indent = len(raw) - len(raw.lstrip(" "))
        if indent % 2:
            raise _yaml_error(number, f"indent of {indent} is not a multiple of two")
        lines.append((number, indent, stripped))
    if not lines:
        raise KernelError(
            code="ROUTE_YAML_UNSUPPORTED",
            message="the document is empty",
            recommended_action="supply a route definition",
        )
    if lines[0][1] != 0:
        raise _yaml_error(lines[0][0], "the document must start at indent 0")
    value, index = _parse_block(lines, 0, 0)
    if index != len(lines):
        raise _yaml_error(lines[index][0], "inconsistent indentation")
    if not isinstance(value, dict):
        raise _yaml_error(lines[0][0], "the top level of a route document must be a mapping")
    return value


# --- route definition --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AcceptanceCriterion:
    """One thing the route must demonstrate.

    ``final`` marks the release gate, which is a criterion like any other so
    that it is scored, digested and frozen with the rest.  A final gate held
    outside the acceptance set is a criterion nobody hashes.
    """

    criterion_id: str
    description: str = ""
    required: bool = True
    final: bool = False

    def __post_init__(self) -> None:
        require_identifier(self.criterion_id, "criterion.criterion_id")

    def to_payload(self) -> dict[str, Any]:
        return {
            "criterionId": self.criterion_id,
            "description": self.description,
            "required": self.required,
            "final": self.final,
        }


@dataclass(frozen=True, slots=True)
class Acceptance:
    """The frozen contract of a route.

    Its digest is computed from the criteria themselves, so adding, removing,
    renaming or de-requiring one changes it.  That digest is the thing the
    registry pins.
    """

    criteria: tuple[AcceptanceCriterion, ...]

    def __post_init__(self) -> None:
        if not self.criteria:
            raise KernelError(
                code="MISSING_REQUIRED_INPUT",
                message="an acceptance with no criteria would pass everything",
                recommended_action="declare at least one criterion",
            )
        seen: set[str] = set()
        for criterion in self.criteria:
            if criterion.criterion_id in seen:
                raise KernelError(
                    code="MALFORMED_INPUT",
                    message=f"duplicate criterion {criterion.criterion_id!r}",
                    recommended_action="give each criterion a unique id",
                )
            seen.add(criterion.criterion_id)
        if sum(1 for item in self.criteria if item.final) != 1:
            raise KernelError(
                code="MALFORMED_INPUT",
                message="an acceptance must declare exactly one final gate",
                recommended_action="mark the release gate criterion as final",
            )

    @classmethod
    def from_gates(cls, mandatory: Sequence[str], final_gate: str) -> Acceptance:
        """Build the acceptance a shipped ``acceptance.yaml`` describes."""

        criteria = [
            AcceptanceCriterion(criterion_id=gate, description=f"mandatory gate {gate}")
            for gate in mandatory
        ]
        criteria.append(AcceptanceCriterion(
            criterion_id=final_gate,
            description=f"release gate {final_gate}",
            final=True,
        ))
        return cls(criteria=tuple(criteria))

    @property
    def final_gate(self) -> str:
        return next(item.criterion_id for item in self.criteria if item.final)

    def to_payload(self) -> dict[str, Any]:
        return {
            "criteria": [item.to_payload() for item in self.criteria],
            "finalGate": self.final_gate,
        }

    @property
    def acceptance_digest(self) -> str:
        return digest(self.to_payload())


@dataclass(frozen=True, slots=True)
class RouteStep:
    """One executable step of a golden route."""

    step_id: str
    description: str = ""
    criteria: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_identifier(self.step_id, "step.step_id")

    def to_payload(self) -> dict[str, Any]:
        return {
            "stepId": self.step_id,
            "description": self.description,
            "criteria": list(self.criteria),
        }


@dataclass(frozen=True, slots=True)
class GoldenRoute:
    """A benchmark: a pinned fixture, a pinned toolchain, steps, and frozen acceptance."""

    route_id: str
    fixture_digest: str
    steps: tuple[RouteStep, ...]
    acceptance: Acceptance
    toolchain_fingerprint: str
    version: str = "2.0.0"

    def __post_init__(self) -> None:
        require_identifier(self.route_id, "route.route_id")
        require_str(self.fixture_digest, "route.fixture_digest", max_length=128)
        require_str(self.toolchain_fingerprint, "route.toolchain_fingerprint", max_length=128)
        if not self.steps:
            raise KernelError(
                code="MISSING_REQUIRED_INPUT",
                message=f"route {self.route_id!r} has no steps",
                recommended_action="declare the steps the route executes",
            )
        declared = {item.criterion_id for item in self.acceptance.criteria}
        for step in self.steps:
            unknown = sorted(set(step.criteria) - declared)
            if unknown:
                raise KernelError(
                    code="MALFORMED_INPUT",
                    message=(
                        f"step {step.step_id!r} claims criteria {unknown} that the "
                        "acceptance does not declare"
                    ),
                    recommended_action="declare the criterion or drop the claim",
                )

    @property
    def acceptance_digest(self) -> str:
        return self.acceptance.acceptance_digest

    def to_payload(self) -> dict[str, Any]:
        return {
            "routeId": self.route_id,
            "version": self.version,
            "fixtureDigest": self.fixture_digest,
            "toolchainFingerprint": self.toolchain_fingerprint,
            "steps": [item.to_payload() for item in self.steps],
            "acceptance": self.acceptance.to_payload(),
            "acceptanceDigest": self.acceptance_digest,
        }


def route_from_yaml(route_text: str, acceptance_text: str, *, fixture_digest: str,
                    toolchain_fingerprint: str) -> GoldenRoute:
    """Build a route from a shipped ``route.yaml`` and its ``acceptance.yaml``.

    The two files are cross-checked: the route's ``mandatoryGates`` and the
    acceptance's ``mandatory`` list must agree, and the route's ``releaseGate``
    must be the acceptance's ``final``.  Two files that disagree about what the
    route requires are two benchmarks, and scoring against either of them is a
    coin toss.
    """

    route_doc = parse_yaml_subset(route_text)
    acceptance_doc = parse_yaml_subset(acceptance_text)
    spec = route_doc.get("spec")
    if not isinstance(spec, Mapping):
        raise KernelError(
            code="MALFORMED_INPUT",
            message="route.yaml has no spec mapping",
            recommended_action="supply spec with mandatoryGates and releaseGate",
        )
    metadata = route_doc.get("metadata")
    if not isinstance(metadata, Mapping):
        raise KernelError(
            code="MALFORMED_INPUT",
            message="route.yaml has no metadata mapping",
            recommended_action="supply metadata.name",
        )
    gates = spec.get("mandatoryGates")
    mandatory = acceptance_doc.get("mandatory")
    if not isinstance(gates, tuple) or not isinstance(mandatory, tuple):
        raise KernelError(
            code="MALFORMED_INPUT",
            message="mandatoryGates and mandatory must both be sequences",
            recommended_action="declare the gate lists in both files",
        )
    if tuple(gates) != tuple(mandatory):
        raise KernelError(
            code="ACCEPTANCE_MUTATED",
            message=(
                f"route.yaml declares gates {list(gates)} but acceptance.yaml declares "
                f"{list(mandatory)}; the two files disagree about what the route requires"
            ),
            retryable=False,
            recommended_action="reconcile the two files before running the route",
            details={"routeGates": list(gates), "acceptanceGates": list(mandatory)},
        )
    release_gate = spec.get("releaseGate")
    final_gate = acceptance_doc.get("final")
    if release_gate != final_gate:
        raise KernelError(
            code="ACCEPTANCE_MUTATED",
            message=(
                f"route.yaml releaseGate {release_gate!r} does not match acceptance.yaml "
                f"final {final_gate!r}"
            ),
            retryable=False,
            recommended_action="reconcile the release gate across the two files",
        )
    acceptance = Acceptance.from_gates(tuple(gates), str(final_gate))
    steps = tuple(
        RouteStep(step_id=gate, description=f"execute {gate}", criteria=(gate,))
        for gate in gates
    ) + (
        RouteStep(step_id=str(final_gate), description=f"reach {final_gate}",
                  criteria=(str(final_gate),)),
    )
    return GoldenRoute(
        route_id=str(metadata.get("name")),
        fixture_digest=fixture_digest,
        steps=steps,
        acceptance=acceptance,
        toolchain_fingerprint=toolchain_fingerprint,
        version=str(metadata.get("version", "2.0.0")),
    )


# --- runs --------------------------------------------------------------------


class StepStatus(StrEnum):
    """How one step of a route ended.

    ``SKIPPED`` is reported as itself, never as a pass; ``INTERRUPTED`` is
    reported as itself, never as a failure.  Both distinctions are the ones a
    regression report needs in order to be believed.
    """

    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    INTERRUPTED = "INTERRUPTED"


@dataclass(frozen=True, slots=True)
class StepEvidence:
    """What one step actually produced, recorded rather than inferred."""

    step_id: str
    status: StepStatus
    criteria: tuple[tuple[str, bool], ...] = ()
    evidence_ids: tuple[str, ...] = ()
    wall_clock_ms: int = 0
    output_digest: str = ""
    reason: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "stepId": self.step_id,
            "status": str(self.status),
            "criteria": [
                {"criterionId": criterion, "passed": passed}
                for criterion, passed in self.criteria
            ],
            "evidenceIds": list(self.evidence_ids),
            "wallClockMs": self.wall_clock_ms,
            "outputDigest": self.output_digest,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class RouteRun:
    """One execution of a route, carrying the environment it actually ran in."""

    run_id: str
    route_id: str
    fixture_digest: str
    toolchain_fingerprint: str
    acceptance_digest: str
    steps: tuple[StepEvidence, ...]
    manual_interventions: int = 0

    def __post_init__(self) -> None:
        require_identifier(self.run_id, "run.run_id")
        require_identifier(self.route_id, "run.route_id")
        require_int(self.manual_interventions, "run.manual_interventions", minimum=0)

    @property
    def interrupted(self) -> bool:
        return any(item.status is StepStatus.INTERRUPTED for item in self.steps)

    def to_payload(self) -> dict[str, Any]:
        return {
            "runId": self.run_id,
            "routeId": self.route_id,
            "fixtureDigest": self.fixture_digest,
            "toolchainFingerprint": self.toolchain_fingerprint,
            "acceptanceDigest": self.acceptance_digest,
            "steps": [item.to_payload() for item in self.steps],
            "manualInterventions": self.manual_interventions,
            "interrupted": self.interrupted,
            "wallClockMs": sum(item.wall_clock_ms for item in self.steps),
        }

    @property
    def digest(self) -> str:
        return digest(self.to_payload())

    @property
    def evidence_digest(self) -> str:
        """Content address of the step evidence alone, for reproducibility checks."""

        return digest([item.to_payload() for item in self.steps])


Executor = Callable[[RouteStep], Mapping[str, Any]]


def _decode_step_result(step: RouteStep, result: Mapping[str, Any],
                        elapsed_ms: int) -> StepEvidence:
    reject_unknown_fields(result, {"status", "criteria", "evidenceIds", "outputs", "reason"},
                          field_name=f"executor result for {step.step_id}")
    status = require_str(result.get("status"), "step.status", max_length=32)
    if status not in {item.value for item in StepStatus}:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"executor returned unknown step status {status!r}",
            recommended_action=f"use one of {sorted(s.value for s in StepStatus)}",
        )
    criteria_payload = require_mapping(result.get("criteria", {}), "step.criteria")
    unknown = sorted(set(criteria_payload) - set(step.criteria))
    if unknown:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=(
                f"step {step.step_id!r} reported criteria {unknown} it does not own; a step "
                "cannot vouch for a criterion it was not asked to demonstrate"
            ),
            recommended_action="report only the criteria declared on the step",
        )
    criteria = tuple(
        (key, require_bool(criteria_payload[key], f"criteria[{key}]"))
        for key in sorted(criteria_payload)
    )
    return StepEvidence(
        step_id=step.step_id,
        status=StepStatus(status),
        criteria=criteria,
        evidence_ids=require_str_seq(result.get("evidenceIds", ()), "step.evidenceIds"),
        wall_clock_ms=elapsed_ms,
        output_digest=digest(result.get("outputs", {})),
        reason=str(result.get("reason", "")),
    )


def run(route: GoldenRoute, executor: Executor, *, run_id: str, clock: Clock,
        fixture_digest: str | None = None, toolchain_fingerprint: str | None = None,
        manual_interventions: int = 0) -> RouteRun:
    """Execute a route step by step and record what each step produced.

    An executor that raises does not abort the run: the step is recorded as
    ``FAILED`` (or ``INTERRUPTED`` for an interruption) with the reason, and
    the remaining steps are recorded as ``SKIPPED``.  A run that stops halfway
    and reports nothing about the rest is indistinguishable from one that
    passed the rest, which is exactly the confusion a benchmark must not
    create.

    ``fixture_digest`` and ``toolchain_fingerprint`` default to the route's
    own.  They are overridable so that a caller can honestly record a run that
    happened somewhere else — and be told, at scoring time, that it is not
    reproducible.
    """

    require_identifier(run_id, "run_id")
    evidence: list[StepEvidence] = []
    stopped = False
    for step in route.steps:
        if stopped:
            evidence.append(StepEvidence(
                step_id=step.step_id,
                status=StepStatus.SKIPPED,
                reason="an earlier step did not complete; this step was never attempted",
            ))
            continue
        started = clock.monotonic_ns()
        try:
            result = executor(step)
        except KernelError as exc:
            elapsed = (clock.monotonic_ns() - started) // 1_000_000
            status = StepStatus.INTERRUPTED if exc.interrupted else StepStatus.FAILED
            evidence.append(StepEvidence(
                step_id=step.step_id,
                status=status,
                wall_clock_ms=elapsed,
                reason=f"{exc.code}: {exc.message}",
            ))
            stopped = True
            continue
        except Exception as exc:  # noqa: BLE001 - deliberate boundary
            elapsed = (clock.monotonic_ns() - started) // 1_000_000
            evidence.append(StepEvidence(
                step_id=step.step_id,
                status=StepStatus.FAILED,
                wall_clock_ms=elapsed,
                reason=f"executor raised {type(exc).__name__}: {exc}",
            ))
            stopped = True
            continue
        elapsed = (clock.monotonic_ns() - started) // 1_000_000
        recorded = _decode_step_result(step, require_mapping(result, "executor result"),
                                       elapsed)
        evidence.append(recorded)
        if recorded.status in {StepStatus.FAILED, StepStatus.INTERRUPTED}:
            stopped = True
    return RouteRun(
        run_id=run_id,
        route_id=route.route_id,
        fixture_digest=fixture_digest or route.fixture_digest,
        toolchain_fingerprint=toolchain_fingerprint or route.toolchain_fingerprint,
        acceptance_digest=route.acceptance_digest,
        steps=tuple(evidence),
        manual_interventions=manual_interventions,
    )


# --- scoring -----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CriterionResult:
    """One criterion's outcome, including "nobody reported this"."""

    criterion_id: str
    required: bool
    final: bool
    measured: bool
    passed: bool | None
    reason: str
    evidence_ids: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "criterionId": self.criterion_id,
            "required": self.required,
            "final": self.final,
            "measured": self.measured,
            "passed": self.passed,
            "reason": self.reason,
            "evidenceIds": list(self.evidence_ids),
        }


@dataclass(frozen=True, slots=True)
class Scorecard:
    """The result of scoring one run against one frozen acceptance."""

    run_id: str
    route_id: str
    acceptance_digest: str
    criteria: tuple[CriterionResult, ...]
    reproducible: bool
    reproducibility_reasons: tuple[str, ...]
    interrupted: bool
    failed_steps: tuple[str, ...]
    skipped_steps: tuple[str, ...]
    manual_interventions: int

    @property
    def passed(self) -> bool:
        """True only when every required criterion was measured and passed."""

        if self.interrupted or self.failed_steps:
            return False
        return all(
            item.measured and item.passed
            for item in self.criteria if item.required
        )

    @property
    def unmeasured(self) -> tuple[str, ...]:
        return tuple(item.criterion_id for item in self.criteria if not item.measured)

    def to_payload(self) -> dict[str, Any]:
        return {
            "runId": self.run_id,
            "routeId": self.route_id,
            "acceptanceDigest": self.acceptance_digest,
            "criteria": [item.to_payload() for item in self.criteria],
            "passed": self.passed,
            "reproducible": self.reproducible,
            "reproducibilityReasons": list(self.reproducibility_reasons),
            "interrupted": self.interrupted,
            "failedSteps": list(self.failed_steps),
            "skippedSteps": list(self.skipped_steps),
            "unmeasuredCriteria": list(self.unmeasured),
            "manualInterventions": self.manual_interventions,
            "note": (
                "a criterion nobody reported is measured:false with passed:null; it is "
                "never counted as a pass"
            ),
        }

    @property
    def digest(self) -> str:
        return digest(self.to_payload())


def _reproducibility(run_record: RouteRun, route: GoldenRoute) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []
    if run_record.fixture_digest != route.fixture_digest:
        reasons.append(
            f"fixture digest {run_record.fixture_digest} does not match the registered "
            f"{route.fixture_digest}"
        )
    if run_record.toolchain_fingerprint != route.toolchain_fingerprint:
        reasons.append(
            f"toolchain fingerprint {run_record.toolchain_fingerprint} does not match the "
            f"registered {route.toolchain_fingerprint}"
        )
    if not reasons:
        reasons.append("fixture digest and toolchain fingerprint match registration")
    return (len(reasons) == 1 and reasons[0].startswith("fixture digest and"), tuple(reasons))


def require_reproducible(run_record: RouteRun, route: GoldenRoute) -> None:
    """Raise ``ENVIRONMENT_DRIFT`` unless the run happened where it claims."""

    reproducible, reasons = _reproducibility(run_record, route)
    if not reproducible:
        raise KernelError(
            code="ENVIRONMENT_DRIFT",
            message=(
                f"run {run_record.run_id!r} did not execute in the registered environment: "
                f"{list(reasons)}"
            ),
            retryable=False,
            recommended_action="re-run against the pinned fixture and toolchain",
            details={"runId": run_record.run_id, "reasons": list(reasons)},
        )


def _score(run_record: RouteRun, route: GoldenRoute) -> Scorecard:
    observations: dict[str, list[tuple[str, bool, tuple[str, ...]]]] = {}
    for step in run_record.steps:
        for criterion_id, passed in step.criteria:
            observations.setdefault(criterion_id, []).append(
                (step.step_id, passed, step.evidence_ids))
    results = []
    for criterion in route.acceptance.criteria:
        entries = observations.get(criterion.criterion_id, [])
        if not entries:
            results.append(CriterionResult(
                criterion_id=criterion.criterion_id,
                required=criterion.required,
                final=criterion.final,
                measured=False,
                passed=None,
                reason="no step reported this criterion; unmeasured is not a pass",
            ))
            continue
        passed = all(entry[1] for entry in entries)
        results.append(CriterionResult(
            criterion_id=criterion.criterion_id,
            required=criterion.required,
            final=criterion.final,
            measured=True,
            passed=passed,
            reason=(
                f"reported by {sorted(entry[0] for entry in entries)}: "
                + ("all observations passed" if passed else "at least one observation failed")
            ),
            evidence_ids=tuple(sorted({
                evidence for entry in entries for evidence in entry[2]
            })),
        ))
    reproducible, reasons = _reproducibility(run_record, route)
    return Scorecard(
        run_id=run_record.run_id,
        route_id=route.route_id,
        acceptance_digest=route.acceptance_digest,
        criteria=tuple(results),
        reproducible=reproducible,
        reproducibility_reasons=reasons,
        interrupted=run_record.interrupted,
        failed_steps=tuple(item.step_id for item in run_record.steps
                           if item.status is StepStatus.FAILED),
        skipped_steps=tuple(item.step_id for item in run_record.steps
                            if item.status is StepStatus.SKIPPED),
        manual_interventions=run_record.manual_interventions,
    )


class GymRegistry:
    """Where a route's acceptance is frozen, and where a moved goalpost is caught.

    The registry stores the acceptance digest computed at registration.  Every
    later score is checked against it, so a route object edited in memory — or
    a run recorded under a different contract — is refused instead of being
    scored against whichever version happened to be in scope.
    """

    def __init__(self, events: EventStore | None = None, *,
                 stream_id: str = "gym-runs") -> None:
        self._routes: dict[str, GoldenRoute] = {}
        self._acceptance: dict[str, str] = {}
        self._events = events
        self._stream_id = stream_id

    def register_route(self, route: GoldenRoute) -> str:
        """Freeze the route's acceptance and return the digest that was pinned."""

        existing = self._acceptance.get(route.route_id)
        if existing is not None and existing != route.acceptance_digest:
            raise KernelError(
                code="ACCEPTANCE_MUTATED",
                message=(
                    f"route {route.route_id!r} is registered with acceptance digest "
                    f"{existing}; re-registering it with {route.acceptance_digest} would "
                    "move the goalposts under the runs already scored against it"
                ),
                retryable=False,
                recommended_action="register the changed acceptance as a new route version",
                details={"routeId": route.route_id, "registered": existing,
                         "offered": route.acceptance_digest},
            )
        self._routes[route.route_id] = route
        self._acceptance[route.route_id] = route.acceptance_digest
        return route.acceptance_digest

    def route(self, route_id: str) -> GoldenRoute:
        route = self._routes.get(route_id)
        if route is None:
            raise KernelError(
                code="ROUTE_NOT_REGISTERED",
                message=f"route {route_id!r} is not registered",
                recommended_action="register the route before running or scoring it",
                details={"routeId": route_id, "registered": sorted(self._routes)},
            )
        return route

    def frozen_acceptance_digest(self, route_id: str) -> str:
        self.route(route_id)
        return self._acceptance[route_id]

    def score(self, run_record: RouteRun, route: GoldenRoute) -> Scorecard:
        """Score a run, refusing anything scored against a different contract."""

        registered = self.frozen_acceptance_digest(route.route_id)
        if route.acceptance_digest != registered:
            raise KernelError(
                code="ACCEPTANCE_MUTATED",
                message=(
                    f"route {route.route_id!r} now carries acceptance digest "
                    f"{route.acceptance_digest} but was registered as {registered}"
                ),
                retryable=False,
                recommended_action="score against the registered acceptance",
                details={"routeId": route.route_id},
            )
        if run_record.acceptance_digest != registered:
            raise KernelError(
                code="ACCEPTANCE_MUTATED",
                message=(
                    f"run {run_record.run_id!r} was executed against acceptance "
                    f"{run_record.acceptance_digest}, not the registered {registered}; "
                    "scoring it here would grade one contract with another"
                ),
                retryable=False,
                recommended_action="re-run against the registered acceptance",
                details={"runId": run_record.run_id, "routeId": route.route_id},
            )
        if run_record.route_id != route.route_id:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=(
                    f"run {run_record.run_id!r} is for route {run_record.route_id!r}, "
                    f"scored against {route.route_id!r}"
                ),
                recommended_action="score each run against its own route",
            )
        return _score(run_record, route)


def record_gym_run(events: EventStore, stream_id: str, scorecard: Scorecard, *,
                   fencing_token: int) -> Mapping[str, Any]:
    """Append a scorecard to the gym stream, once, under a fencing token."""

    require_int(fencing_token, "fencing_token", minimum=1)
    event = events.append(stream_id, scorecard.to_payload(),
                          idempotency_key=scorecard.digest, fencing_token=fencing_token)
    return {
        "sequence": event.sequence,
        "eventId": event.event_id,
        "hashChain": event.hash_chain,
        "scorecardDigest": scorecard.digest,
    }


# --- regression --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RegressionReport:
    """Per-criterion movement between two scorecards."""

    route_id: str
    baseline_run_id: str
    candidate_run_id: str
    entries: tuple[Mapping[str, Any], ...]

    @property
    def regressions(self) -> tuple[str, ...]:
        return tuple(
            str(item["criterionId"]) for item in self.entries
            if item["movement"] in {"REGRESSED", "MEASUREMENT_LOST"}
        )

    @property
    def regressed(self) -> bool:
        return bool(self.regressions)

    def to_payload(self) -> dict[str, Any]:
        return {
            "routeId": self.route_id,
            "baselineRunId": self.baseline_run_id,
            "candidateRunId": self.candidate_run_id,
            "entries": [dict(item) for item in self.entries],
            "regressions": list(self.regressions),
            "regressed": self.regressed,
        }


def compare(baseline: Scorecard, candidate: Scorecard) -> RegressionReport:
    """Report what moved, in both directions, and what stopped being measured.

    ``MEASUREMENT_LOST`` counts as a regression.  A criterion that passed
    yesterday and is unmeasured today has not been shown to still hold, and
    treating "we stopped checking" as neutral is how a benchmark's coverage
    quietly erodes while its pass rate stays flat.
    """

    if baseline.route_id != candidate.route_id:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=(
                f"cannot compare scorecards from different routes: "
                f"{baseline.route_id!r} and {candidate.route_id!r}"
            ),
            recommended_action="compare runs of the same route",
        )
    if baseline.acceptance_digest != candidate.acceptance_digest:
        raise KernelError(
            code="ACCEPTANCE_MUTATED",
            message=(
                "the two scorecards were produced against different acceptance digests; "
                "the comparison would measure the contract change, not the change"
            ),
            retryable=False,
            recommended_action="compare runs scored against one frozen acceptance",
            details={"baseline": baseline.acceptance_digest,
                     "candidate": candidate.acceptance_digest},
        )
    before = {item.criterion_id: item for item in baseline.criteria}
    after = {item.criterion_id: item for item in candidate.criteria}
    entries: list[Mapping[str, Any]] = []
    for criterion_id in sorted(set(before) | set(after)):
        old = before.get(criterion_id)
        new = after.get(criterion_id)
        if old is None:
            movement = "NEW"
        elif new is None:
            movement = "REMOVED"
        elif old.measured and not new.measured:
            movement = "MEASUREMENT_LOST"
        elif not old.measured and new.measured:
            movement = "MEASUREMENT_GAINED"
        elif not old.measured and not new.measured:
            movement = "STILL_UNMEASURED"
        elif old.passed and not new.passed:
            movement = "REGRESSED"
        elif not old.passed and new.passed:
            movement = "FIXED"
        else:
            movement = "UNCHANGED"
        entries.append({
            "criterionId": criterion_id,
            "movement": movement,
            "baseline": None if old is None else {"measured": old.measured,
                                                  "passed": old.passed},
            "candidate": None if new is None else {"measured": new.measured,
                                                   "passed": new.passed},
        })
    return RegressionReport(
        route_id=baseline.route_id,
        baseline_run_id=baseline.run_id,
        candidate_run_id=candidate.run_id,
        entries=tuple(entries),
    )


def assert_no_regression(report: RegressionReport) -> RegressionReport:
    """Raise ``BENCHMARK_REGRESSION`` when anything went backwards."""

    if report.regressed:
        raise KernelError(
            code="BENCHMARK_REGRESSION",
            message=(
                f"route {report.route_id!r} regressed on {list(report.regressions)} between "
                f"{report.baseline_run_id!r} and {report.candidate_run_id!r}"
            ),
            retryable=False,
            recommended_action="fix the regression or withdraw the change",
            details={"routeId": report.route_id, "regressions": list(report.regressions)},
        )
    return report


def assert_reproducible_between(first: RouteRun, second: RouteRun) -> None:
    """Two runs of one route in one environment must produce identical evidence."""

    if first.route_id != second.route_id:
        raise KernelError(
            code="MALFORMED_INPUT",
            message="reproducibility is compared between runs of the same route",
            recommended_action="compare runs of one route",
        )
    if first.evidence_digest != second.evidence_digest:
        raise KernelError(
            code="NON_REPRODUCIBLE",
            message=(
                f"runs {first.run_id!r} and {second.run_id!r} of route {first.route_id!r} "
                "produced different step evidence; the route is not reproducible"
            ),
            retryable=False,
            recommended_action="pin whatever varied between the two runs",
            details={"routeId": first.route_id,
                     "digests": [first.evidence_digest, second.evidence_digest]},
        )


# --- fixtures, chaos, certification, commercial ------------------------------


@dataclass(frozen=True, slots=True)
class FixtureRepository:
    """One benchmark repository, pinned and measured."""

    repo_id: str
    snapshot_sha: str
    lines_of_code: int
    language: str

    def __post_init__(self) -> None:
        require_identifier(self.repo_id, "fixture.repo_id")
        require_str(self.snapshot_sha, "fixture.snapshot_sha", max_length=128)
        require_int(self.lines_of_code, "fixture.lines_of_code", minimum=1)

    def to_payload(self) -> dict[str, Any]:
        return {
            "repoId": self.repo_id,
            "snapshotSha": self.snapshot_sha,
            "linesOfCode": self.lines_of_code,
            "language": self.language,
        }


def validate_fixture_set(repositories: Sequence[FixtureRepository], *,
                         min_repositories: int = 3, min_lines: int = 500_000,
                         min_large_lines: int = 1_000_000,
                         min_large_repositories: int = 1) -> Mapping[str, Any]:
    """Check the benchmark set is actually the size it claims to be.

    The thresholds are arguments rather than constants so a caller can state a
    weaker set deliberately.  What they cannot do is leave them unstated: a
    gym that quietly benchmarks three toy repositories reports the same green
    tick as one that benchmarks three real ones.
    """

    large = [item for item in repositories if item.lines_of_code >= min_large_lines]
    qualifying = [item for item in repositories if item.lines_of_code >= min_lines]
    problems: list[str] = []
    if len(qualifying) < min_repositories:
        problems.append(
            f"{len(qualifying)} repositor(y/ies) at or above {min_lines} LOC, "
            f"{min_repositories} required"
        )
    if len(large) < min_large_repositories:
        problems.append(
            f"{len(large)} repositor(y/ies) at or above {min_large_lines} LOC, "
            f"{min_large_repositories} required"
        )
    duplicates = sorted({
        item.repo_id for item in repositories
        if sum(1 for other in repositories if other.repo_id == item.repo_id) > 1
    })
    if duplicates:
        problems.append(f"duplicate repository ids {duplicates}")
    if problems:
        raise KernelError(
            code="GYM_FIXTURE_SET_INVALID",
            message=f"the benchmark repository set is not valid: {problems}",
            retryable=False,
            recommended_action="add the missing repositories or lower the stated thresholds",
            details={"problems": problems},
        )
    return {
        "repositoryCount": len(repositories),
        "qualifyingCount": len(qualifying),
        "largeCount": len(large),
        "totalLinesOfCode": sum(item.lines_of_code for item in repositories),
        "thresholds": {
            "minRepositories": min_repositories,
            "minLines": min_lines,
            "minLargeLines": min_large_lines,
            "minLargeRepositories": min_large_repositories,
        },
        "measured": True,
    }


@dataclass(frozen=True, slots=True)
class ChaosOutcome:
    """One injected failure and whether the run came back from it.

    ``injected=False`` means the scenario was declared and never run.  It is
    reported as unmeasured rather than as a recovery, because a fault nobody
    injected has demonstrated nothing.
    """

    scenario_id: str
    injected: bool
    recovered: bool | None = None
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_identifier(self.scenario_id, "chaos.scenario_id")
        if self.injected and self.recovered is None:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"chaos scenario {self.scenario_id!r} was injected with no outcome",
                recommended_action="record whether the run recovered",
            )
        if not self.injected and self.recovered is not None:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=(
                    f"chaos scenario {self.scenario_id!r} was not injected but claims an "
                    "outcome"
                ),
                recommended_action="inject the fault or drop the outcome",
            )

    def to_payload(self) -> dict[str, Any]:
        return {
            "scenarioId": self.scenario_id,
            "injected": self.injected,
            "recovered": self.recovered,
            "measured": self.injected,
            "evidenceIds": list(self.evidence_ids),
        }


@dataclass(frozen=True, slots=True)
class CommercialThresholds:
    """What "ready to sell" means, in integers, stated before the run."""

    min_success_rate_bp: int
    max_manual_interventions: int
    max_open_defects: int

    def __post_init__(self) -> None:
        require_int(self.min_success_rate_bp, "thresholds.min_success_rate_bp", minimum=0,
                    maximum=10_000)
        require_int(self.max_manual_interventions, "thresholds.max_manual_interventions",
                    minimum=0)
        require_int(self.max_open_defects, "thresholds.max_open_defects", minimum=0)

    def to_payload(self) -> dict[str, Any]:
        return {
            "minSuccessRateBp": self.min_success_rate_bp,
            "maxManualInterventions": self.max_manual_interventions,
            "maxOpenDefects": self.max_open_defects,
        }


@dataclass(frozen=True, slots=True)
class CommercialMeasurement:
    """What was actually observed, with ``None`` where nothing was.

    Every field is optional and every absence is reported as unmeasured.  Zero
    open defects is a fine result; "we did not count the defects" is not the
    same result, and a gate that cannot tell them apart passes on ignorance.
    """

    success_rate_bp: int | None = None
    manual_interventions: int | None = None
    open_defects: int | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "successRateBp": self.success_rate_bp,
            "manualInterventions": self.manual_interventions,
            "openDefects": self.open_defects,
            "successRateMeasured": self.success_rate_bp is not None,
            "manualInterventionsMeasured": self.manual_interventions is not None,
            "openDefectsMeasured": self.open_defects is not None,
        }


def _commercial_gate(thresholds: CommercialThresholds,
                     measurement: CommercialMeasurement) -> tuple[bool, tuple[str, ...]]:
    problems: list[str] = []
    if measurement.success_rate_bp is None:
        problems.append("success rate was not measured; unmeasured is not a pass")
    elif measurement.success_rate_bp < thresholds.min_success_rate_bp:
        problems.append(
            f"success rate {measurement.success_rate_bp} bp is below the required "
            f"{thresholds.min_success_rate_bp} bp"
        )
    if measurement.manual_interventions is None:
        problems.append("manual interventions were not counted; unmeasured is not zero")
    elif measurement.manual_interventions > thresholds.max_manual_interventions:
        problems.append(
            f"{measurement.manual_interventions} manual intervention(s) against a maximum "
            f"of {thresholds.max_manual_interventions}"
        )
    if measurement.open_defects is None:
        problems.append("open defects were not counted; unmeasured is not zero")
    elif measurement.open_defects > thresholds.max_open_defects:
        problems.append(
            f"{measurement.open_defects} open defect(s) against a maximum of "
            f"{thresholds.max_open_defects}"
        )
    return (not problems, tuple(problems))


#: The certification ladder.  It is a *prefix* ladder: each rung presupposes
#: every rung below it, so a tier can never be reached by skipping one, and E1
#: — the static pass — is explicitly not certification.
CERTIFICATION_LADDER: tuple[tuple[str, str], ...] = (
    ("E1", "every required acceptance criterion measured and passed"),
    ("E2", "the run is reproducible: pinned fixture and pinned toolchain"),
    ("E3", "every declared chaos scenario was injected and recovered"),
    ("E4", "the commercial thresholds are met on measured numbers"),
    ("E5", "the route completed without manual intervention"),
)


def certify(scorecard: Scorecard, *, chaos: Sequence[ChaosOutcome],
            thresholds: CommercialThresholds,
            measurement: CommercialMeasurement) -> Mapping[str, Any]:
    """Walk the E1–E5 ladder and stop at the first rung that is not met.

    Nothing above the failed rung is evaluated as passed, and the reason for
    stopping is returned with the tier.  This is the shape that keeps "E1
    passed" from being reported as "certified": ``tier`` is the highest rung
    actually reached, and it is ``None`` when even E1 was not.
    """

    unmet: list[Mapping[str, Any]] = []
    reached: str | None = None
    rungs: list[Mapping[str, Any]] = []
    blocked = False
    for tier, requirement in CERTIFICATION_LADDER:
        if blocked:
            rungs.append({"tier": tier, "requirement": requirement, "status": "NOT_EVALUATED",
                          "reason": "a lower rung was not met"})
            continue
        if tier == "E1":
            met = scorecard.passed
            reason = ("every required criterion measured and passed" if met else
                      f"unmeasured {list(scorecard.unmeasured)}, failed steps "
                      f"{list(scorecard.failed_steps)}, interrupted={scorecard.interrupted}")
        elif tier == "E2":
            met = scorecard.reproducible
            reason = "; ".join(scorecard.reproducibility_reasons)
        elif tier == "E3":
            if not chaos:
                met = False
                reason = "no chaos scenario was declared; recovery is unproven"
            else:
                uninjected = sorted(item.scenario_id for item in chaos if not item.injected)
                unrecovered = sorted(item.scenario_id for item in chaos
                                     if item.injected and not item.recovered)
                met = not uninjected and not unrecovered
                reason = ("every declared scenario was injected and recovered" if met else
                          f"not injected {uninjected}, not recovered {unrecovered}")
        elif tier == "E4":
            met, problems = _commercial_gate(thresholds, measurement)
            reason = ("the commercial thresholds are met" if met else "; ".join(problems))
        else:
            met = scorecard.manual_interventions == 0
            reason = (
                "the route completed without manual intervention" if met else
                f"{scorecard.manual_interventions} manual intervention(s) recorded"
            )
        rungs.append({"tier": tier, "requirement": requirement,
                      "status": "MET" if met else "NOT_MET", "reason": reason})
        if met:
            reached = tier
        else:
            blocked = True
            unmet.append({"tier": tier, "reason": reason})
    return {
        "tier": reached,
        "ladder": rungs,
        "firstUnmet": unmet[0] if unmet else None,
        "certified": reached == CERTIFICATION_LADDER[-1][0],
        "note": (
            "E1 is a static pass, not a production certification; the ladder is a prefix "
            "ladder and a tier is never reached by skipping a lower rung"
        ),
    }


# --- registry entry point ----------------------------------------------------

_REQUEST_FIELDS = frozenset({
    "benchmark_repositories", "golden_task_specs", "fixed_images", "expected_contracts",
    "chaos_scenarios",
})


def _decode_route(payload: Mapping[str, Any], *, toolchain: str) -> GoldenRoute:
    reject_unknown_fields(
        payload,
        {"routeId", "version", "fixtureDigest", "steps", "acceptance"},
        field_name="route",
    )
    acceptance_payload = require_mapping(payload.get("acceptance"), "route.acceptance")
    reject_unknown_fields(acceptance_payload, {"mandatoryGates", "finalGate"},
                          field_name="route.acceptance")
    acceptance = Acceptance.from_gates(
        require_str_seq(acceptance_payload.get("mandatoryGates", ()),
                        "acceptance.mandatoryGates", allow_empty=False),
        require_identifier(acceptance_payload.get("finalGate"), "acceptance.finalGate"),
    )
    steps = tuple(
        RouteStep(
            step_id=require_identifier(require_mapping(item, "steps[]").get("stepId"),
                                       "step.stepId"),
            description=str(require_mapping(item, "steps[]").get("description", "")),
            criteria=require_str_seq(require_mapping(item, "steps[]").get("criteria", ()),
                                     "step.criteria"),
        )
        for item in payload.get("steps", ())
    )
    return GoldenRoute(
        route_id=require_identifier(payload.get("routeId"), "route.routeId"),
        fixture_digest=require_str(payload.get("fixtureDigest"), "route.fixtureDigest",
                                   max_length=128),
        steps=steps,
        acceptance=acceptance,
        toolchain_fingerprint=toolchain,
        version=str(payload.get("version", "2.0.0")),
    )


def _decode_run(payload: Mapping[str, Any], route: GoldenRoute) -> RouteRun:
    reject_unknown_fields(
        payload,
        {"runId", "routeId", "fixtureDigest", "toolchainFingerprint", "acceptanceDigest",
         "steps", "manualInterventions"},
        field_name="run",
    )
    steps = []
    by_step = {item.step_id: item for item in route.steps}
    for item in payload.get("steps", ()):
        entry = require_mapping(item, "run.steps[]")
        reject_unknown_fields(
            entry,
            {"stepId", "status", "criteria", "evidenceIds", "wallClockMs", "outputDigest",
             "reason"},
            field_name="run.step",
        )
        step_id = require_identifier(entry.get("stepId"), "run.step.stepId")
        if step_id not in by_step:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"run reports step {step_id!r} that route {route.route_id!r} "
                        "does not declare",
                recommended_action="report only the route's own steps",
            )
        status = require_str(entry.get("status"), "run.step.status", max_length=32)
        if status not in {value.value for value in StepStatus}:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"unknown step status {status!r}",
                recommended_action=f"use one of {sorted(s.value for s in StepStatus)}",
            )
        criteria_payload = require_mapping(entry.get("criteria", {}), "run.step.criteria")
        unknown = sorted(set(criteria_payload) - set(by_step[step_id].criteria))
        if unknown:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"step {step_id!r} reported criteria {unknown} it does not own",
                recommended_action="report only the criteria declared on the step",
            )
        steps.append(StepEvidence(
            step_id=step_id,
            status=StepStatus(status),
            criteria=tuple(
                (key, require_bool(criteria_payload[key], f"criteria[{key}]"))
                for key in sorted(criteria_payload)
            ),
            evidence_ids=require_str_seq(entry.get("evidenceIds", ()), "run.step.evidenceIds"),
            wall_clock_ms=require_int(entry.get("wallClockMs", 0), "run.step.wallClockMs",
                                      minimum=0),
            output_digest=str(entry.get("outputDigest", "")),
            reason=str(entry.get("reason", "")),
        ))
    return RouteRun(
        run_id=require_identifier(payload.get("runId"), "run.runId"),
        route_id=require_identifier(payload.get("routeId"), "run.routeId"),
        fixture_digest=require_str(payload.get("fixtureDigest"), "run.fixtureDigest",
                                   max_length=128),
        toolchain_fingerprint=require_str(payload.get("toolchainFingerprint"),
                                          "run.toolchainFingerprint", max_length=128),
        acceptance_digest=require_str(payload.get("acceptanceDigest", route.acceptance_digest),
                                      "run.acceptanceDigest", max_length=128),
        steps=tuple(steps),
        manual_interventions=require_int(payload.get("manualInterventions", 0),
                                         "run.manualInterventions", minimum=0),
    )


@register("repository-gym-golden-routes")
def handle(request: Mapping[str, Any]) -> Mapping[str, Any]:
    """Registry entry point.

    Validates the fixture set, freezes each route's acceptance, scores the
    recorded runs against the frozen contract, compares them with the baseline
    runs, and walks the E1–E5 ladder.  A run that drifted from the pinned
    environment still produces a scorecard — with ``reproducible: false`` — and
    is stopped at E2 rather than being silently discarded.
    """

    reject_unknown_fields(request, _REQUEST_FIELDS,
                          field_name="repository-gym-golden-routes request")
    for name in ("benchmark_repositories", "golden_task_specs", "fixed_images"):
        if name not in request:
            raise KernelError(
                code="MISSING_REQUIRED_INPUT",
                message=f"{name} is required",
                recommended_action=f"supply {name}",
            )

    images = require_mapping(request.get("fixed_images"), "fixed_images")
    reject_unknown_fields(images, {"toolchainFingerprint"}, field_name="fixed_images")
    toolchain = require_str(images.get("toolchainFingerprint"),
                            "fixed_images.toolchainFingerprint", max_length=128)

    repositories_payload = require_mapping(request.get("benchmark_repositories"),
                                           "benchmark_repositories")
    reject_unknown_fields(repositories_payload, {"repositories", "thresholds"},
                          field_name="benchmark_repositories")
    repositories = tuple(
        FixtureRepository(
            repo_id=require_identifier(require_mapping(item, "repositories[]").get("repoId"),
                                       "repository.repoId"),
            snapshot_sha=require_str(require_mapping(item, "repositories[]").get("snapshotSha"),
                                     "repository.snapshotSha", max_length=128),
            lines_of_code=require_int(
                require_mapping(item, "repositories[]").get("linesOfCode"),
                "repository.linesOfCode", minimum=1),
            language=str(require_mapping(item, "repositories[]").get("language", "")),
        )
        for item in repositories_payload.get("repositories", ())
    )
    thresholds_payload = require_mapping(repositories_payload.get("thresholds", {}),
                                         "benchmark_repositories.thresholds")
    reject_unknown_fields(
        thresholds_payload,
        {"minRepositories", "minLines", "minLargeLines", "minLargeRepositories"},
        field_name="benchmark_repositories.thresholds",
    )
    fixture_report = validate_fixture_set(
        repositories,
        min_repositories=require_int(thresholds_payload.get("minRepositories", 3),
                                     "thresholds.minRepositories", minimum=1),
        min_lines=require_int(thresholds_payload.get("minLines", 500_000),
                              "thresholds.minLines", minimum=1),
        min_large_lines=require_int(thresholds_payload.get("minLargeLines", 1_000_000),
                                    "thresholds.minLargeLines", minimum=1),
        min_large_repositories=require_int(thresholds_payload.get("minLargeRepositories", 1),
                                           "thresholds.minLargeRepositories", minimum=0),
    )

    specs = require_mapping(request.get("golden_task_specs"), "golden_task_specs")
    reject_unknown_fields(specs, {"routes", "runs", "baselineRuns"},
                          field_name="golden_task_specs")
    registry = GymRegistry()
    routes = {}
    for item in specs.get("routes", ()):
        route = _decode_route(require_mapping(item, "routes[]"), toolchain=toolchain)
        registry.register_route(route)
        routes[route.route_id] = route
    if not routes:
        raise KernelError(
            code="MISSING_REQUIRED_INPUT",
            message="golden_task_specs.routes is empty",
            recommended_action="supply at least one golden route",
        )

    def decode_runs(container: str) -> tuple[RouteRun, ...]:
        decoded = []
        for item in specs.get(container, ()):
            payload = require_mapping(item, f"golden_task_specs.{container}[]")
            route_id = require_identifier(payload.get("routeId"), "run.routeId")
            decoded.append(_decode_run(payload, registry.route(route_id)))
        return tuple(decoded)

    runs = decode_runs("runs")
    baselines = decode_runs("baselineRuns")
    if not runs:
        raise KernelError(
            code="MISSING_REQUIRED_INPUT",
            message="golden_task_specs.runs is empty; there is nothing to score",
            recommended_action="supply at least one recorded run",
        )

    chaos_payload = request.get("chaos_scenarios")
    chaos: list[ChaosOutcome] = []
    if chaos_payload is not None:
        chaos_payload = require_mapping(chaos_payload, "chaos_scenarios")
        reject_unknown_fields(chaos_payload, {"scenarios"}, field_name="chaos_scenarios")
        for item in chaos_payload.get("scenarios", ()):
            entry = require_mapping(item, "chaos_scenarios.scenarios[]")
            reject_unknown_fields(entry, {"scenarioId", "injected", "recovered",
                                          "evidenceIds"}, field_name="chaos scenario")
            injected = require_bool(entry.get("injected", False), "scenario.injected")
            recovered = entry.get("recovered")
            chaos.append(ChaosOutcome(
                scenario_id=require_identifier(entry.get("scenarioId"), "scenario.scenarioId"),
                injected=injected,
                recovered=None if recovered is None else require_bool(recovered,
                                                                      "scenario.recovered"),
                evidence_ids=require_str_seq(entry.get("evidenceIds", ()),
                                             "scenario.evidenceIds"),
            ))

    contracts = require_mapping(request.get("expected_contracts", {}), "expected_contracts")
    reject_unknown_fields(contracts, {"commercialThresholds", "commercialMeasurement"},
                          field_name="expected_contracts")
    thresholds_map = require_mapping(contracts.get("commercialThresholds", {}),
                                     "expected_contracts.commercialThresholds")
    reject_unknown_fields(thresholds_map, {"minSuccessRateBp", "maxManualInterventions",
                                           "maxOpenDefects"},
                          field_name="commercialThresholds")
    thresholds = CommercialThresholds(
        min_success_rate_bp=require_int(thresholds_map.get("minSuccessRateBp", 9_500),
                                        "thresholds.minSuccessRateBp", minimum=0,
                                        maximum=10_000),
        max_manual_interventions=require_int(
            thresholds_map.get("maxManualInterventions", 0),
            "thresholds.maxManualInterventions", minimum=0),
        max_open_defects=require_int(thresholds_map.get("maxOpenDefects", 0),
                                     "thresholds.maxOpenDefects", minimum=0),
    )
    measurement_map = require_mapping(contracts.get("commercialMeasurement", {}),
                                      "expected_contracts.commercialMeasurement")
    reject_unknown_fields(measurement_map, {"successRateBp", "manualInterventions",
                                            "openDefects"},
                          field_name="commercialMeasurement")

    def optional_int(name: str) -> int | None:
        value = measurement_map.get(name)
        return None if value is None else require_int(value, f"measurement.{name}", minimum=0)

    measurement = CommercialMeasurement(
        success_rate_bp=optional_int("successRateBp"),
        manual_interventions=optional_int("manualInterventions"),
        open_defects=optional_int("openDefects"),
    )

    scorecards = [registry.score(item, routes[item.route_id]) for item in runs]
    baseline_cards = {
        item.route_id: registry.score(item, routes[item.route_id]) for item in baselines
    }
    reports = []
    for card in scorecards:
        baseline = baseline_cards.get(card.route_id)
        if baseline is None:
            reports.append({
                "routeId": card.route_id,
                "candidateRunId": card.run_id,
                "compared": False,
                "reason": "no baseline run was supplied for this route",
                "regressed": None,
            })
            continue
        report = compare(baseline, card)
        reports.append({**report.to_payload(), "compared": True})

    certifications = [
        {
            "routeId": card.route_id,
            "runId": card.run_id,
            **certify(card, chaos=chaos, thresholds=thresholds, measurement=measurement),
        }
        for card in scorecards
    ]
    commercial_met, commercial_problems = _commercial_gate(thresholds, measurement)

    return {
        "gym_runs": {
            "toolchainFingerprint": toolchain,
            "fixtureSet": fixture_report,
            "repositories": [item.to_payload() for item in repositories],
            "routes": [routes[key].to_payload() for key in sorted(routes)],
            "runs": [item.to_payload() for item in runs],
            "chaos": [item.to_payload() for item in chaos],
        },
        "golden_artifacts": {
            "acceptanceDigests": {
                key: registry.frozen_acceptance_digest(key) for key in sorted(routes)
            },
            "runDigests": {item.run_id: item.digest for item in runs},
            "evidenceDigests": {item.run_id: item.evidence_digest for item in runs},
        },
        "scorecards": [item.to_payload() for item in scorecards],
        "regression_trends": reports,
        "commercial_readiness": {
            "thresholds": thresholds.to_payload(),
            "measurement": measurement.to_payload(),
            "met": commercial_met,
            "problems": list(commercial_problems),
            "certifications": certifications,
            "note": (
                "commercial readiness requires E5; a static PASS at E1 is not a production "
                "certification"
            ),
        },
        "evidenceIds": sorted({
            evidence for item in runs for step in item.steps for evidence in step.evidence_ids
        } | {
            evidence for item in chaos for evidence in item.evidence_ids
        }),
    }
