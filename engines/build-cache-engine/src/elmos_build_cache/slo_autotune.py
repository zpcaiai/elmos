"""Off-hot-path parity SLO tuning, progressive rollout, and rollback.

Only performance knobs appear here.  ActionKey semantics, digest checks,
tenancy, authorisation, validation floors, staging, and publication are absent
from the tunable contract by design, so no optimiser can weaken them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from typing import Any

from .canonical import digest_of, require_digest
from .errors import ContractViolation
from .parity import ParityDecision, ParityReport


class _StringEnum(StrEnum):
    pass


class RolloutPhase(_StringEnum):
    OBSERVE = "OBSERVE"
    SHADOW = "SHADOW"
    INTERNAL = "INTERNAL"
    CANARY = "CANARY"
    FIVE_PERCENT = "FIVE_PERCENT"
    TWENTY_FIVE_PERCENT = "TWENTY_FIVE_PERCENT"
    FIFTY_PERCENT = "FIFTY_PERCENT"
    FULL = "FULL"


ROLLOUT_ORDER: tuple[RolloutPhase, ...] = tuple(RolloutPhase)


class RollbackReason(_StringEnum):
    FALSE_HIT = "FALSE_HIT"
    CROSS_TENANT_HIT = "CROSS_TENANT_HIT"
    CORRUPT_EXECUTION = "CORRUPT_EXECUTION"
    UNDER_VALIDATED_PUBLICATION = "UNDER_VALIDATED_PUBLICATION"
    SLO_BREACH = "SLO_BREACH"
    PROVIDER_ACCOUNTING_MISMATCH = "PROVIDER_ACCOUNTING_MISMATCH"
    FAIRNESS_REGRESSION = "FAIRNESS_REGRESSION"
    UNKNOWN_OUTCOME_BUDGET = "UNKNOWN_OUTCOME_BUDGET"
    OUT_OF_DISTRIBUTION = "OUT_OF_DISTRIBUTION"
    COST_GUARDRAIL = "COST_GUARDRAIL"
    CLEAN_FALLBACK_UNAVAILABLE = "CLEAN_FALLBACK_UNAVAILABLE"
    APPROVAL_INVALID = "APPROVAL_INVALID"


@dataclass(frozen=True)
class CacheTuningParameters:
    capacity_bytes: int
    provider_prefix_ttl_seconds: int = 300
    environment_ttl_seconds: int = 86_400
    affinity_locality_weight: float = 1.0
    prefetch_max_bytes: int = 512 * 1024 * 1024
    context_compaction_soft_ratio: float = 0.72
    restore_cost_bias: float = 1.0

    def __post_init__(self) -> None:
        if self.capacity_bytes < 1:
            raise ContractViolation("cache capacity must be positive")
        if not 30 <= self.provider_prefix_ttl_seconds <= 86_400:
            raise ContractViolation("provider prefix TTL is outside certified bounds")
        if not 300 <= self.environment_ttl_seconds <= 30 * 86_400:
            raise ContractViolation("environment TTL is outside certified bounds")
        if not 0.0 <= self.affinity_locality_weight <= 4.0:
            raise ContractViolation("affinity locality weight is outside certified bounds")
        if not 0 <= self.prefetch_max_bytes <= 8 * 1024 * 1024 * 1024:
            raise ContractViolation("prefetch budget is outside certified bounds")
        if not 0.50 <= self.context_compaction_soft_ratio < 0.90:
            raise ContractViolation("context compaction ratio is outside certified bounds")
        if not 0.5 <= self.restore_cost_bias <= 2.0:
            raise ContractViolation("restore cost bias is outside certified bounds")

    @property
    def digest(self) -> str:
        return digest_of({"schema_version": "1.2.0", **asdict(self)})


@dataclass(frozen=True)
class TuningObservation:
    sample_count: int
    unexpected_prefix_miss_rate: float
    wrong_shard_rate: float
    environment_hit_rate: float
    storage_pressure: float
    useful_prefetch_rate: float
    context_limit_pressure: float
    restore_bypass_rate: float
    out_of_distribution: bool = False

    def __post_init__(self) -> None:
        if self.sample_count < 0:
            raise ContractViolation("sample_count cannot be negative")
        for name, value in asdict(self).items():
            if name in {"sample_count", "out_of_distribution"}:
                continue
            if not 0.0 <= float(value) <= 1.0:
                raise ContractViolation("tuning observations must be ratios", field=name)


@dataclass(frozen=True)
class TuningProposal:
    baseline_digest: str
    candidate: CacheTuningParameters
    reason_codes: tuple[str, ...]
    shadow_only: bool = True

    @property
    def proposal_digest(self) -> str:
        return digest_of(
            {
                "schema_version": "1.2.0",
                "baseline_digest": self.baseline_digest,
                "candidate_digest": self.candidate.digest,
                "reason_codes": list(self.reason_codes),
                "shadow_only": self.shadow_only,
            }
        )


class SloAutotuner:
    """Produce bounded proposals; it cannot activate them."""

    def __init__(self, minimum_samples: int = 1_000) -> None:
        if minimum_samples < 1:
            raise ContractViolation("minimum_samples must be positive")
        self.minimum_samples = minimum_samples

    def propose(
        self, baseline: CacheTuningParameters, observation: TuningObservation
    ) -> TuningProposal:
        if observation.out_of_distribution:
            return TuningProposal(baseline.digest, baseline, ("OOD_PIN_BASELINE",))
        if observation.sample_count < self.minimum_samples:
            return TuningProposal(baseline.digest, baseline, ("INSUFFICIENT_SAMPLE",))

        candidate = baseline
        reasons: list[str] = []
        if observation.storage_pressure > 0.90:
            candidate = replace(
                candidate,
                provider_prefix_ttl_seconds=max(
                    30, int(candidate.provider_prefix_ttl_seconds * 0.8)
                ),
            )
            reasons.append("REDUCE_PREFIX_TTL_FOR_PRESSURE")
        elif observation.unexpected_prefix_miss_rate > 0.02:
            candidate = replace(
                candidate,
                provider_prefix_ttl_seconds=min(86_400, int(candidate.provider_prefix_ttl_seconds * 1.2)),
            )
            reasons.append("INCREASE_PREFIX_TTL_FOR_MISSES")
        if observation.wrong_shard_rate > 0.01:
            candidate = replace(
                candidate,
                affinity_locality_weight=min(4.0, candidate.affinity_locality_weight + 0.1),
            )
            reasons.append("INCREASE_LOCALITY_WEIGHT")
        if observation.environment_hit_rate < 0.95 and observation.storage_pressure < 0.90:
            candidate = replace(
                candidate,
                environment_ttl_seconds=min(30 * 86_400, int(candidate.environment_ttl_seconds * 1.1)),
            )
            reasons.append("INCREASE_ENVIRONMENT_TTL")
        if observation.useful_prefetch_rate < 0.25:
            candidate = replace(candidate, prefetch_max_bytes=int(candidate.prefetch_max_bytes * 0.8))
            reasons.append("REDUCE_LOW_VALUE_PREFETCH")
        if observation.context_limit_pressure > 0.70:
            candidate = replace(
                candidate,
                context_compaction_soft_ratio=max(0.50, candidate.context_compaction_soft_ratio - 0.02),
            )
            reasons.append("COMPACT_CONTEXT_EARLIER")
        if observation.restore_bypass_rate > 0.30:
            candidate = replace(candidate, restore_cost_bias=min(2.0, candidate.restore_cost_bias + 0.1))
            reasons.append("PREFER_RECOMPUTE_WHEN_RESTORE_EXPENSIVE")
        if not reasons:
            reasons.append("NO_MATERIAL_CHANGE")
        return TuningProposal(baseline.digest, candidate, tuple(reasons))


@dataclass(frozen=True)
class RolloutEvidence:
    parity_report: ParityReport
    provider_accounting_matches: bool
    worst_cohort_regressed: bool
    unknown_outcome_rate: float
    unknown_outcome_budget: float
    out_of_distribution: bool
    cost_guardrail_passed: bool
    clean_fallback_exercised: bool
    rollback_exercised: bool

    def __post_init__(self) -> None:
        if not 0.0 <= self.unknown_outcome_rate <= 1.0:
            raise ContractViolation("unknown outcome rate must be a ratio")
        if not 0.0 <= self.unknown_outcome_budget <= 1.0:
            raise ContractViolation("unknown outcome budget must be a ratio")


@dataclass(frozen=True)
class RolloutState:
    baseline_digest: str
    candidate_digest: str | None
    serving_digest: str
    phase: RolloutPhase = RolloutPhase.OBSERVE
    consecutive_passes: int = 0
    epoch: int = 1
    rollback_reason: RollbackReason | None = None

    def __post_init__(self) -> None:
        require_digest(self.baseline_digest)
        require_digest(self.serving_digest)
        if self.candidate_digest is not None:
            require_digest(self.candidate_digest)
        if self.epoch < 1 or self.consecutive_passes < 0:
            raise ContractViolation("invalid rollout counters")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.2.0",
            "baseline_digest": self.baseline_digest,
            "candidate_digest": self.candidate_digest,
            "serving_digest": self.serving_digest,
            "phase": str(self.phase),
            "consecutive_passes": self.consecutive_passes,
            "epoch": self.epoch,
            "rollback_reason": str(self.rollback_reason) if self.rollback_reason is not None else None,
        }


class ProgressiveRolloutController:
    """Advance only on measured evidence; any safety trigger rolls back."""

    def __init__(self, state: RolloutState, required_windows: int = 3) -> None:
        if required_windows < 1:
            raise ContractViolation("required_windows must be positive")
        self.state = state
        self.required_windows = required_windows

    def install_candidate(self, proposal: TuningProposal) -> RolloutState:
        if proposal.baseline_digest != self.state.baseline_digest:
            raise ContractViolation("proposal was tuned against a different baseline")
        self.state = replace(
            self.state,
            candidate_digest=proposal.candidate.digest,
            phase=RolloutPhase.SHADOW,
            consecutive_passes=0,
            rollback_reason=None,
            epoch=self.state.epoch + 1,
        )
        return self.state

    def observe(self, evidence: RolloutEvidence) -> RolloutState:
        trigger = self._rollback_trigger(evidence)
        if trigger is not None:
            return self.rollback(trigger)
        if self.state.candidate_digest is None:
            return self.state
        passes = self.state.consecutive_passes + 1
        if passes < self.required_windows:
            self.state = replace(self.state, consecutive_passes=passes)
            return self.state
        if not evidence.rollback_exercised or not evidence.clean_fallback_exercised:
            return self.rollback(RollbackReason.CLEAN_FALLBACK_UNAVAILABLE)
        index = ROLLOUT_ORDER.index(self.state.phase)
        following = ROLLOUT_ORDER[min(index + 1, len(ROLLOUT_ORDER) - 1)]
        candidate_digest = self.state.candidate_digest
        if candidate_digest is None:  # guarded above; keeps the state transition total
            raise ContractViolation("candidate disappeared during rollout transition")
        serving = (
            candidate_digest
            if following not in {RolloutPhase.OBSERVE, RolloutPhase.SHADOW}
            else self.state.serving_digest
        )
        self.state = replace(
            self.state,
            phase=following,
            serving_digest=serving,
            consecutive_passes=0,
            rollback_reason=None,
            epoch=self.state.epoch + 1,
        )
        return self.state

    def rollback(self, reason: RollbackReason) -> RolloutState:
        self.state = replace(
            self.state,
            candidate_digest=None,
            serving_digest=self.state.baseline_digest,
            phase=RolloutPhase.OBSERVE,
            consecutive_passes=0,
            rollback_reason=reason,
            epoch=self.state.epoch + 1,
        )
        return self.state

    @staticmethod
    def _rollback_trigger(evidence: RolloutEvidence) -> RollbackReason | None:
        metrics = evidence.parity_report.metrics
        for metric, reason in (
            ("false_hits", RollbackReason.FALSE_HIT),
            ("cross_tenant_hits", RollbackReason.CROSS_TENANT_HIT),
            ("corrupt_executions", RollbackReason.CORRUPT_EXECUTION),
            ("under_validated_publications", RollbackReason.UNDER_VALIDATED_PUBLICATION),
        ):
            if int(metrics.get(metric, 0)) > 0:
                return reason
        if evidence.parity_report.decision is not ParityDecision.READY_FOR_EXTERNAL_GATE:
            return RollbackReason.SLO_BREACH
        if not evidence.provider_accounting_matches:
            return RollbackReason.PROVIDER_ACCOUNTING_MISMATCH
        if evidence.worst_cohort_regressed:
            return RollbackReason.FAIRNESS_REGRESSION
        if evidence.unknown_outcome_rate > evidence.unknown_outcome_budget:
            return RollbackReason.UNKNOWN_OUTCOME_BUDGET
        if evidence.out_of_distribution:
            return RollbackReason.OUT_OF_DISTRIBUTION
        if not evidence.cost_guardrail_passed:
            return RollbackReason.COST_GUARDRAIL
        return None


__all__ = [
    "CacheTuningParameters",
    "ProgressiveRolloutController",
    "ROLLOUT_ORDER",
    "RollbackReason",
    "RolloutEvidence",
    "RolloutPhase",
    "RolloutState",
    "SloAutotuner",
    "TuningObservation",
    "TuningProposal",
]
