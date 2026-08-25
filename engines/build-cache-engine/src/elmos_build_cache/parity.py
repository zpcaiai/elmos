"""Fail-closed Codex/Claude-class cache parity evaluation.

This module evaluates *measured* observations.  It intentionally does not
generate favourable fixture values and it never emits ``CERTIFIED``: a local
pass can prepare a digest-bound report for an external gate, while missing
scenarios, evidence, cohorts, or zero-tolerance fields remain ``NOT_RUN`` or
``FAILED``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from .canonical import digest_of, require_digest
from .errors import ContractViolation
from .security import ProvenanceSigner, SignedStatement

_MINIMUM_THRESHOLD_FLOORS: dict[str, float] = {
    "stable_turn_cached_token_reuse": 0.90,
    "exact_rerun_weighted_reuse": 0.99,
    "small_edit_weighted_reuse": 0.90,
    "environment_snapshot_hit": 0.95,
    "warm_start_p95_reduction": 0.80,
    "restart_artifact_reuse": 0.999,
    "stable_followup_wall_clock_saved": 0.70,
    "model_input_cost_saved": 0.80,
    "long_session_cached_token_reuse": 0.80,
}
_MAXIMUM_THRESHOLD_CEILINGS: dict[str, float] = {
    "unexpected_full_prefix_miss": 0.02,
    "unnecessary_invalidation": 0.05,
}


class _StringEnum(StrEnum):
    pass


class ScenarioStatus(_StringEnum):
    PASS = "PASS"  # noqa: S105 - verification state, not a credential
    FAIL = "FAIL"
    NOT_RUN = "NOT_RUN"
    BLOCKED = "BLOCKED"


class ParityDecision(_StringEnum):
    NOT_RUN = "NOT_RUN"
    FAILED = "FAILED"
    READY_FOR_EXTERNAL_GATE = "READY_FOR_EXTERNAL_GATE"


MANDATORY_SCENARIOS: tuple[str, ...] = (
    "EXACT_RERUN",
    "STABLE_10_TURN",
    "EDIT_LE_1_PERCENT",
    "IMPLEMENTATION_ONLY",
    "FORMATTING_ONLY",
    "PUBLIC_INTERFACE_CHANGE",
    "LOCKFILE_CHANGE",
    "RULE_PACK_CHANGE",
    "MODEL_SWITCH",
    "EFFORT_SWITCH",
    "TOOL_SCHEMA_CHANGE",
    "ENVIRONMENT_WARM",
    "SERVICE_RESTART",
    "WORKER_FAILOVER",
    "PROVIDER_TTL_EXPIRY",
    "LONG_SESSION_100_TURN",
    "CONTEXT_COMPACTION_ROLLBACK",
    "CACHE_STORE_OUTAGE",
    "CORRUPT_OBJECT_NEGATIVE",
    "CROSS_TENANT_NEGATIVE",
)


@dataclass(frozen=True)
class ParityThresholds:
    stable_turn_cached_token_reuse: float = 0.90
    unexpected_full_prefix_miss: float = 0.02
    exact_rerun_weighted_reuse: float = 0.99
    redundant_validated_rerun_calls: int = 0
    small_edit_weighted_reuse: float = 0.90
    unnecessary_invalidation: float = 0.05
    environment_snapshot_hit: float = 0.95
    warm_start_p95_reduction: float = 0.80
    restart_artifact_reuse: float = 0.999
    stable_followup_wall_clock_saved: float = 0.70
    model_input_cost_saved: float = 0.80
    long_session_cached_token_reuse: float = 0.80
    false_hits: int = 0
    cross_tenant_hits: int = 0
    corrupt_executions: int = 0
    under_validated_publications: int = 0

    def __post_init__(self) -> None:
        ratios = (
            self.stable_turn_cached_token_reuse,
            self.unexpected_full_prefix_miss,
            self.exact_rerun_weighted_reuse,
            self.small_edit_weighted_reuse,
            self.unnecessary_invalidation,
            self.environment_snapshot_hit,
            self.warm_start_p95_reduction,
            self.restart_artifact_reuse,
            self.stable_followup_wall_clock_saved,
            self.model_input_cost_saved,
            self.long_session_cached_token_reuse,
        )
        if any(value < 0.0 or value > 1.0 for value in ratios):
            raise ContractViolation("parity ratio thresholds must be between zero and one")
        for name, floor in _MINIMUM_THRESHOLD_FLOORS.items():
            if float(getattr(self, name)) < floor:
                raise ContractViolation(
                    "minimum parity threshold cannot be weakened",
                    threshold=name,
                    package_floor=floor,
                )
        for name, ceiling in _MAXIMUM_THRESHOLD_CEILINGS.items():
            if float(getattr(self, name)) > ceiling:
                raise ContractViolation(
                    "maximum parity threshold cannot be weakened",
                    threshold=name,
                    package_ceiling=ceiling,
                )
        counts = (
            self.redundant_validated_rerun_calls,
            self.false_hits,
            self.cross_tenant_hits,
            self.corrupt_executions,
            self.under_validated_publications,
        )
        if any(value != 0 for value in counts):
            raise ContractViolation("zero-tolerance parity thresholds cannot be weakened")


_MINIMUM_METRICS = frozenset(
    {
        "stable_turn_cached_token_reuse",
        "exact_rerun_weighted_reuse",
        "small_edit_weighted_reuse",
        "environment_snapshot_hit",
        "warm_start_p95_reduction",
        "restart_artifact_reuse",
        "stable_followup_wall_clock_saved",
        "model_input_cost_saved",
        "long_session_cached_token_reuse",
    }
)
_MAXIMUM_METRICS = frozenset({"unexpected_full_prefix_miss", "unnecessary_invalidation"})
_ZERO_METRICS = frozenset(
    {
        "redundant_validated_rerun_calls",
        "false_hits",
        "cross_tenant_hits",
        "corrupt_executions",
        "under_validated_publications",
    }
)
MANDATORY_METRICS = tuple(sorted(_MINIMUM_METRICS | _MAXIMUM_METRICS | _ZERO_METRICS))


@dataclass(frozen=True)
class EvidenceBinding:
    source_digest: str
    configuration_digest: str
    provider_profiles_digest: str
    corpus_digest: str
    platform_digest: str
    generated_at: str
    executor_identity: str
    verifier_identity: str
    tenant_scope_digest: str | None = None
    authorization_digest: str | None = None

    def __post_init__(self) -> None:
        for value in (
            self.source_digest,
            self.configuration_digest,
            self.provider_profiles_digest,
            self.corpus_digest,
            self.platform_digest,
        ):
            require_digest(value)
        if not self.generated_at or not self.executor_identity or not self.verifier_identity:
            raise ContractViolation("parity evidence binding is incomplete")
        if self.executor_identity == self.verifier_identity:
            raise ContractViolation("parity executor and verifier must be independent")
        scoped_values = (self.tenant_scope_digest, self.authorization_digest)
        if any(value is None for value in scoped_values) and any(
            value is not None for value in scoped_values
        ):
            raise ContractViolation(
                "parity evidence scope and authorization must be bound together"
            )
        for scoped_value in scoped_values:
            if scoped_value is not None:
                require_digest(scoped_value)

    @property
    def authenticated(self) -> bool:
        """Whether this binding is eligible for production API evidence checks."""

        return self.tenant_scope_digest is not None and self.authorization_digest is not None

    def to_dict(self) -> dict[str, Any]:
        document = asdict(self)
        if not self.authenticated:
            document.pop("tenant_scope_digest")
            document.pop("authorization_digest")
        return document


@dataclass(frozen=True)
class ScenarioResult:
    scenario_id: str
    status: ScenarioStatus
    evidence_digests: tuple[str, ...] = ()
    detail: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.scenario_id not in MANDATORY_SCENARIOS:
            raise ContractViolation("unknown parity scenario", scenario_id=self.scenario_id)
        for digest in self.evidence_digests:
            require_digest(digest)
        if self.status is ScenarioStatus.PASS and not self.evidence_digests:
            raise ContractViolation("a passed scenario requires raw evidence", scenario_id=self.scenario_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "status": str(self.status),
            "evidence_digests": sorted(self.evidence_digests),
            "detail": dict(self.detail),
        }


@dataclass(frozen=True)
class MetricCheck:
    name: str
    actual: float | int | None
    expected: float | int
    operator: str
    passed: bool
    scope: str = "global"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ParityReport:
    report_id: str
    decision: ParityDecision
    binding: EvidenceBinding
    metrics: Mapping[str, float | int]
    cohorts: Mapping[str, Mapping[str, float | int]]
    checks: tuple[MetricCheck, ...]
    scenarios: tuple[ScenarioResult, ...]
    failures: tuple[str, ...]
    missing: tuple[str, ...]
    thresholds: ParityThresholds
    report_digest: str

    @property
    def mandatory_pass(self) -> bool:
        return self.decision is ParityDecision.READY_FOR_EXTERNAL_GATE

    def statement(self) -> dict[str, Any]:
        return {
            "schema_version": "1.2.0",
            "kind": "elmos.cache-parity-report/v1.2",
            "report_id": self.report_id,
            "decision": str(self.decision),
            "mandatory_pass": self.mandatory_pass,
            "binding": self.binding.to_dict(),
            "metrics": dict(sorted(self.metrics.items())),
            "cohorts": {
                cohort: dict(sorted(values.items())) for cohort, values in sorted(self.cohorts.items())
            },
            "checks": [check.to_dict() for check in self.checks],
            "scenarios": [scenario.to_dict() for scenario in self.scenarios],
            "failures": list(self.failures),
            "missing": list(self.missing),
            "thresholds": asdict(self.thresholds),
            "claim_policy": "measured_only_external_gate_required",
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.statement(), "report_digest": self.report_digest}

    def sign(self, signer: ProvenanceSigner) -> SignedStatement:
        if not signer.asymmetric:
            raise ContractViolation("parity reports require an asymmetric signer")
        return signer.sign_statement("elmos.cache-parity-report/v1.2", self.to_dict())


def weighted_reuse(costs: Sequence[tuple[bool, float]]) -> float:
    if any(cost < 0.0 for _, cost in costs):
        raise ContractViolation("weighted reuse costs cannot be negative")
    total = sum(cost for _, cost in costs)
    if total <= 0.0:
        raise ContractViolation("weighted reuse requires a positive eligible denominator")
    return sum(cost for hit, cost in costs if hit) / total


def _check_metrics(
    metrics: Mapping[str, float | int],
    thresholds: ParityThresholds,
    *,
    scope: str,
) -> tuple[list[MetricCheck], list[str], list[str]]:
    expected = asdict(thresholds)
    checks: list[MetricCheck] = []
    failures: list[str] = []
    missing: list[str] = []
    for name in MANDATORY_METRICS:
        if name not in metrics:
            missing.append(f"{scope}:{name}")
            checks.append(MetricCheck(name, None, expected[name], "required", False, scope))
            continue
        actual = metrics[name]
        if isinstance(actual, bool) or not isinstance(actual, int | float):
            raise ContractViolation("parity metrics must be numeric", metric=name, scope=scope)
        if name in _ZERO_METRICS:
            passed = int(actual) == 0 and float(actual) == int(actual)
            operator = "=="
        elif name in _MINIMUM_METRICS:
            passed = float(actual) >= float(expected[name])
            operator = ">="
        else:
            passed = float(actual) <= float(expected[name])
            operator = "<="
        checks.append(MetricCheck(name, actual, expected[name], operator, passed, scope))
        if not passed:
            failures.append(f"{scope}:{name} {actual} {operator} {expected[name]} failed")
    return checks, failures, missing


def evaluate_parity(
    *,
    report_id: str,
    metrics: Mapping[str, float | int],
    cohorts: Mapping[str, Mapping[str, float | int]],
    scenarios: Sequence[ScenarioResult],
    binding: EvidenceBinding,
    thresholds: ParityThresholds | None = None,
) -> ParityReport:
    """Evaluate one immutable report without fabricating absent observations."""
    if not report_id:
        raise ContractViolation("report_id is required")
    policy = thresholds or ParityThresholds()
    checks, failures, missing = _check_metrics(metrics, policy, scope="global")
    if not cohorts:
        missing.append("cohorts")
    for cohort, cohort_metrics in sorted(cohorts.items()):
        if not cohort:
            raise ContractViolation("cohort names cannot be empty")
        cohort_checks, cohort_failures, cohort_missing = _check_metrics(
            cohort_metrics, policy, scope=f"cohort:{cohort}"
        )
        checks.extend(cohort_checks)
        failures.extend(cohort_failures)
        missing.extend(cohort_missing)

    by_id: dict[str, ScenarioResult] = {}
    for scenario in scenarios:
        if scenario.scenario_id in by_id:
            raise ContractViolation("duplicate parity scenario", scenario_id=scenario.scenario_id)
        by_id[scenario.scenario_id] = scenario
    ordered_scenarios: list[ScenarioResult] = []
    for scenario_id in MANDATORY_SCENARIOS:
        found_scenario = by_id.get(scenario_id)
        if found_scenario is None:
            missing.append(f"scenario:{scenario_id}")
            continue
        ordered_scenarios.append(found_scenario)
        if found_scenario.status in {ScenarioStatus.NOT_RUN, ScenarioStatus.BLOCKED}:
            missing.append(f"scenario:{scenario_id}:{found_scenario.status}")
        elif found_scenario.status is ScenarioStatus.FAIL:
            failures.append(f"scenario:{scenario_id}:FAIL")

    if missing:
        decision = ParityDecision.NOT_RUN
    elif failures:
        decision = ParityDecision.FAILED
    else:
        decision = ParityDecision.READY_FOR_EXTERNAL_GATE

    body = {
        "schema_version": "1.2.0",
        "report_id": report_id,
        "decision": str(decision),
        "binding": binding.to_dict(),
        "metrics": dict(sorted(metrics.items())),
        "cohorts": {cohort: dict(sorted(values.items())) for cohort, values in sorted(cohorts.items())},
        "checks": [check.to_dict() for check in checks],
        "scenarios": [scenario.to_dict() for scenario in ordered_scenarios],
        "failures": sorted(failures),
        "missing": sorted(missing),
        "thresholds": asdict(policy),
    }
    return ParityReport(
        report_id=report_id,
        decision=decision,
        binding=binding,
        metrics=dict(metrics),
        cohorts={name: dict(values) for name, values in cohorts.items()},
        checks=tuple(checks),
        scenarios=tuple(ordered_scenarios),
        failures=tuple(sorted(failures)),
        missing=tuple(sorted(missing)),
        thresholds=policy,
        report_digest=digest_of(body),
    )


__all__ = [
    "EvidenceBinding",
    "MANDATORY_METRICS",
    "MANDATORY_SCENARIOS",
    "MetricCheck",
    "ParityDecision",
    "ParityReport",
    "ParityThresholds",
    "ScenarioResult",
    "ScenarioStatus",
    "evaluate_parity",
    "weighted_reuse",
]
