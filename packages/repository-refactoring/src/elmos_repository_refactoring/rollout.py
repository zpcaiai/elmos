"""Skill 13 — changesets, canary and guarded rollout.

Splits a verified patch into small, dependency-ordered changesets, and plans a
staged rollout whose every advance is a decision made from measurements rather
than from elapsed time.

The two refusals that matter:

* **No canary without a verified rollback.**  A rollout that cannot be undone
  is a deployment, not a canary, and this module will not start one.
* **Technical metrics alone cannot approve a full rollout of a high-risk
  change.**  When business or data-consistency signals are unavailable, the
  plan holds at a partial stage and says which signal is missing.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any

from .buildgraph import BuildGraph
from .contracts import RiskClass, sha256_payload
from .discovery import RepositoryInventory
from .patch import FileChange, PatchSet

#: Default traffic ladder.  A stage is only entered when the previous stage's
#: guardrails held for its full observation window.
DEFAULT_STAGES: tuple[int, ...] = (1, 5, 25, 50, 100)

#: A changeset larger than this stops being reviewable.
MAX_CHANGESET_FILES = 40
MAX_CHANGESET_LINES = 800


class RolloutDecision(StrEnum):
    ADVANCE = "advance"
    HOLD = "hold"
    ROLLBACK = "rollback"
    COMPLETE = "complete"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class Changeset:
    changeset_id: str
    title: str
    paths: tuple[str, ...]
    changed_lines: int
    depends_on: tuple[str, ...] = ()
    owners: tuple[str, ...] = ()
    build_targets: tuple[str, ...] = ()
    release_note: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "changesetId": self.changeset_id,
            "title": self.title,
            "paths": list(self.paths),
            "changedLines": self.changed_lines,
            "dependsOn": list(self.depends_on),
            "owners": list(self.owners),
            "buildTargets": list(self.build_targets),
            "releaseNote": self.release_note,
        }


@dataclass(frozen=True, slots=True)
class RolloutStage:
    stage_id: str
    traffic_percent: int
    observation_seconds: int
    guardrails: tuple[str, ...]
    required_signals: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "stageId": self.stage_id,
            "trafficPercent": self.traffic_percent,
            "observationSeconds": self.observation_seconds,
            "guardrails": list(self.guardrails),
            "requiredSignals": list(self.required_signals),
        }


@dataclass(frozen=True, slots=True)
class RolloutPlan:
    strategy: str
    stages: tuple[RolloutStage, ...]
    feature_flag: str | None
    dual_path: bool
    shadow_traffic: bool
    rollback_verified: bool
    blocked_reason: str = ""

    @property
    def startable(self) -> bool:
        return self.rollback_verified and not self.blocked_reason

    def to_payload(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "stages": [item.to_payload() for item in self.stages],
            "featureFlag": self.feature_flag,
            "dualPath": self.dual_path,
            "shadowTraffic": self.shadow_traffic,
            "rollbackVerified": self.rollback_verified,
            "startable": self.startable,
            "blockedReason": self.blocked_reason,
        }

    @property
    def digest(self) -> str:
        return sha256_payload(self.to_payload())


@dataclass(frozen=True, slots=True)
class GuardrailReading:
    name: str
    baseline: Decimal | None
    candidate: Decimal | None
    threshold: Decimal | None
    higher_is_worse: bool = True

    @property
    def available(self) -> bool:
        return self.baseline is not None and self.candidate is not None

    @property
    def breached(self) -> bool | None:
        """``None`` when the signal is unavailable — never ``False``."""

        if not self.available or self.threshold is None:
            return None
        assert self.baseline is not None and self.candidate is not None
        delta = self.candidate - self.baseline
        return delta > self.threshold if self.higher_is_worse else -delta > self.threshold

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "baseline": None if self.baseline is None else str(self.baseline),
            "candidate": None if self.candidate is None else str(self.candidate),
            "threshold": None if self.threshold is None else str(self.threshold),
            "available": self.available,
            "breached": self.breached,
        }


@dataclass(frozen=True, slots=True)
class CanaryReport:
    stage_id: str
    decision: RolloutDecision
    readings: tuple[GuardrailReading, ...]
    reasons: tuple[str, ...]
    old_path_usage: int | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "stageId": self.stage_id,
            "decision": self.decision.value,
            "readings": [item.to_payload() for item in self.readings],
            "reasons": list(self.reasons),
            "oldPathUsage": self.old_path_usage,
        }


@dataclass(frozen=True, slots=True)
class ReleaseEvidence:
    changesets: tuple[Changeset, ...]
    plan: RolloutPlan
    reports: tuple[CanaryReport, ...] = field(default_factory=tuple)

    def to_payload(self) -> dict[str, Any]:
        return {
            "changesets": [item.to_payload() for item in self.changesets],
            "rolloutPlan": self.plan.to_payload(),
            "canaryReports": [item.to_payload() for item in self.reports],
        }

    @property
    def digest(self) -> str:
        return sha256_payload(self.to_payload())


# ---------------------------------------------------------------------------
# Changesets
# ---------------------------------------------------------------------------


def split_changesets(
    patch: PatchSet,
    graph: BuildGraph,
    inventory: RepositoryInventory,
    *,
    max_files: int = MAX_CHANGESET_FILES,
    max_lines: int = MAX_CHANGESET_LINES,
) -> tuple[Changeset, ...]:
    """Cut a patch into reviewable, dependency-ordered changesets.

    Cuts follow build targets and ownership rather than an arbitrary file
    count, so a changeset has one owner and one build — which is what makes it
    independently reviewable and independently revertible.
    """

    grouped: dict[str, list[FileChange]] = {}
    for change in patch.changes:
        targets = graph.targets_for(change.path)
        key = targets[0] if targets else "unassigned"
        grouped.setdefault(key, []).append(change)

    changesets: list[Changeset] = []
    previous: str | None = None
    for key in sorted(grouped):
        changes = sorted(grouped[key], key=lambda item: item.path)
        buckets: list[list[FileChange]] = [[]]
        lines = 0
        for change in changes:
            change_lines = change.added_lines + change.removed_lines
            if buckets[-1] and (len(buckets[-1]) >= max_files or lines + change_lines > max_lines):
                buckets.append([])
                lines = 0
            buckets[-1].append(change)
            lines += change_lines
        for index, bucket in enumerate(buckets):
            if not bucket:
                continue
            paths = tuple(item.path for item in bucket)
            owners = sorted({owner for path in paths for owner in inventory.owners_of(path)})
            identifier = f"cs-{key.replace(':', '_')}-{index}"
            changesets.append(
                Changeset(
                    changeset_id=identifier,
                    title=f"{key}: {len(paths)} file(s)" if key != "unassigned" else f"{len(paths)} unassigned file(s)",
                    paths=paths,
                    changed_lines=sum(item.added_lines + item.removed_lines for item in bucket),
                    depends_on=(previous,) if previous and index == 0 else (),
                    owners=tuple(owners),
                    build_targets=(key,) if key != "unassigned" else (),
                    release_note=_release_note(bucket),
                )
            )
            previous = identifier
    return tuple(changesets)


def _release_note(changes: Sequence[FileChange]) -> str:
    created = [item.path for item in changes if item.created]
    deleted = [item.path for item in changes if item.deleted]
    modified = [item.path for item in changes if not item.created and not item.deleted]
    parts: list[str] = []
    if modified:
        parts.append(f"{len(modified)} file(s) modified")
    if created:
        parts.append(f"{len(created)} added")
    if deleted:
        parts.append(f"{len(deleted)} removed")
    return "; ".join(parts)


# ---------------------------------------------------------------------------
# Rollout planning
# ---------------------------------------------------------------------------


def plan_rollout(
    *,
    risk_class: RiskClass,
    rollback_verified: bool,
    touches_data: bool = False,
    touches_contracts: bool = False,
    business_signals_available: bool = False,
    stages: Sequence[int] = DEFAULT_STAGES,
    observation_seconds: int = 900,
) -> RolloutPlan:
    """Choose a rollout strategy and refuse to start an unrecoverable one."""

    blocked = ""
    if not rollback_verified:
        blocked = (
            "no verified rollback: a canary that cannot be reversed is a deployment, not an experiment"
        )
    if risk_class.rank >= RiskClass.R4.rank and not business_signals_available:
        blocked = blocked or (
            "an R4 change cannot be approved to 100% on technical metrics alone; "
            "a business or data-consistency signal is required"
        )

    if touches_data:
        strategy = "expand-contract-with-dual-path"
        dual_path = True
        shadow = True
    elif touches_contracts:
        strategy = "versioned-contract-with-adapter"
        dual_path = True
        shadow = False
    elif risk_class.rank >= RiskClass.R3.rank:
        strategy = "flagged-canary"
        dual_path = False
        shadow = True
    else:
        strategy = "pull-request"
        dual_path = False
        shadow = False

    ladder = tuple(stages) if risk_class.rank >= RiskClass.R3.rank else (100,)
    guardrails = ("error-rate", "latency-p95", "resource-utilisation")
    required: tuple[str, ...] = ("error-rate", "latency-p95")
    if touches_data:
        required = (*required, "data-consistency", "old-path-usage")
    if risk_class.rank >= RiskClass.R4.rank:
        required = (*required, "business-kpi")

    planned = tuple(
        RolloutStage(
            stage_id=f"stage-{percent:03d}",
            traffic_percent=percent,
            observation_seconds=observation_seconds if percent < 100 else observation_seconds * 2,
            guardrails=guardrails,
            required_signals=required,
        )
        for percent in ladder
    )
    return RolloutPlan(
        strategy=strategy,
        stages=planned,
        feature_flag=f"refactor.{strategy.replace('-', '_')}" if strategy != "pull-request" else None,
        dual_path=dual_path,
        shadow_traffic=shadow,
        rollback_verified=rollback_verified,
        blocked_reason=blocked,
    )


def evaluate_stage(
    stage: RolloutStage,
    readings: Sequence[GuardrailReading],
    *,
    old_path_usage: int | None = None,
    is_final: bool = False,
) -> CanaryReport:
    """Decide whether to advance, hold or roll back after one stage."""

    reasons: list[str] = []
    by_name = {item.name: item for item in readings}

    breached = [item.name for item in readings if item.breached is True]
    if breached:
        return CanaryReport(
            stage_id=stage.stage_id,
            decision=RolloutDecision.ROLLBACK,
            readings=tuple(readings),
            reasons=tuple(f"guardrail breached: {name}" for name in breached),
            old_path_usage=old_path_usage,
        )

    missing = [name for name in stage.required_signals if name not in by_name or not by_name[name].available]
    if missing:
        reasons.append(
            "required signal(s) unavailable: " + ", ".join(missing) + "; an unmeasured guardrail is not a passing one"
        )
        return CanaryReport(
            stage_id=stage.stage_id,
            decision=RolloutDecision.HOLD,
            readings=tuple(readings),
            reasons=tuple(reasons),
            old_path_usage=old_path_usage,
        )

    if "old-path-usage" in stage.required_signals and old_path_usage:
        reasons.append(
            f"the old path still served {old_path_usage} request(s); it must reach zero before contraction"
        )
        return CanaryReport(
            stage_id=stage.stage_id,
            decision=RolloutDecision.HOLD,
            readings=tuple(readings),
            reasons=tuple(reasons),
            old_path_usage=old_path_usage,
        )

    return CanaryReport(
        stage_id=stage.stage_id,
        decision=RolloutDecision.COMPLETE if is_final else RolloutDecision.ADVANCE,
        readings=tuple(readings),
        reasons=("all required guardrails measured and within threshold",),
        old_path_usage=old_path_usage,
    )


def run_ladder(
    plan: RolloutPlan,
    measurements: Mapping[str, Sequence[GuardrailReading]],
    *,
    old_path_usage: Mapping[str, int] | None = None,
) -> tuple[CanaryReport, ...]:
    """Walk the ladder, stopping at the first stage that does not advance."""

    if not plan.startable:
        return (
            CanaryReport(
                stage_id="pre-flight",
                decision=RolloutDecision.BLOCKED,
                readings=(),
                reasons=(plan.blocked_reason,),
            ),
        )
    reports: list[CanaryReport] = []
    for index, stage in enumerate(plan.stages):
        readings = measurements.get(stage.stage_id, ())
        report = evaluate_stage(
            stage,
            readings,
            old_path_usage=(old_path_usage or {}).get(stage.stage_id),
            is_final=index == len(plan.stages) - 1,
        )
        reports.append(report)
        if report.decision in (RolloutDecision.HOLD, RolloutDecision.ROLLBACK, RolloutDecision.BLOCKED):
            break
    return tuple(reports)


def release_evidence(
    changesets: Sequence[Changeset],
    plan: RolloutPlan,
    reports: Sequence[CanaryReport] = (),
) -> ReleaseEvidence:
    return ReleaseEvidence(
        changesets=tuple(changesets),
        plan=plan,
        reports=tuple(reports),
    )


__all__ = [
    "DEFAULT_STAGES",
    "MAX_CHANGESET_FILES",
    "MAX_CHANGESET_LINES",
    "CanaryReport",
    "Changeset",
    "GuardrailReading",
    "ReleaseEvidence",
    "RolloutDecision",
    "RolloutPlan",
    "RolloutStage",
    "evaluate_stage",
    "plan_rollout",
    "release_evidence",
    "run_ladder",
    "split_changesets",
]
