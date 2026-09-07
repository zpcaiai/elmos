"""Skill 14 — rollback, compensation and recovery.

Recovery has to work when the run is already in a bad state, so it never
assumes anything it can check:

* **The last consistent checkpoint is found, not assumed.**  A checkpoint is
  only usable if its workspace tree digest still matches something we can
  reproduce.
* **Source-only damage is reversed with a patch.**  Inverting the patch is
  preferable to restoring a snapshot because it composes with anything that
  legitimately changed alongside.
* **External side effects are compensated in reverse order**, each with its own
  idempotency key, because a compensation delivered twice must not undo twice.
* **Data is never rolled back automatically when reversibility is unknown.**
  Stopping writes, switching reads back and *keeping* the additive structures
  is the safe move; dropping the new column to "clean up" destroys the only
  copy of the backfilled data.
* **Recovery never deletes investigation evidence.**  The journal, the patch
  and the failing artifacts survive the rollback.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from .contracts import RiskClass, isoformat_utc, sha256_payload, utc_now
from .journal import Checkpoint, RunJournal, SideEffect
from .patch import PatchSet
from .workspace import WorkspaceSnapshot


class RecoveryAction(StrEnum):
    REVERSE_PATCH = "reverse-patch"
    SNAPSHOT_RESTORE = "snapshot-restore"
    COMPENSATE = "compensate"
    STOP_WRITES = "stop-writes"
    SWITCH_READS = "switch-reads"
    HOLD_FOR_APPROVAL = "hold-for-approval"
    NONE = "none"


#: Side-effect kinds whose reversal is a data operation and therefore never
#: automatic without an explicit reversibility proof.
_DATA_EFFECTS = frozenset({"migration.apply", "backfill.run", "index.rebuild", "cache.purge", "topic.delete"})


@dataclass(frozen=True, slots=True)
class RecoveryStep:
    order: int
    action: RecoveryAction
    target: str
    idempotency_key: str
    detail: str
    automatic: bool = True
    approval_reason: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "order": self.order,
            "action": self.action.value,
            "target": self.target,
            "idempotencyKey": self.idempotency_key,
            "detail": self.detail,
            "automatic": self.automatic,
            "approvalReason": self.approval_reason,
        }


@dataclass(frozen=True, slots=True)
class RollbackPlan:
    checkpoint: Checkpoint | None
    steps: tuple[RecoveryStep, ...]
    blocked_reason: str = ""

    @property
    def automatic_steps(self) -> tuple[RecoveryStep, ...]:
        return tuple(item for item in self.steps if item.automatic)

    @property
    def approval_steps(self) -> tuple[RecoveryStep, ...]:
        return tuple(item for item in self.steps if not item.automatic)

    @property
    def executable(self) -> bool:
        return not self.blocked_reason and bool(self.steps)

    def to_payload(self) -> dict[str, Any]:
        return {
            "checkpoint": None if self.checkpoint is None else self.checkpoint.to_payload(),
            "steps": [item.to_payload() for item in self.steps],
            "automaticSteps": len(self.automatic_steps),
            "approvalSteps": len(self.approval_steps),
            "executable": self.executable,
            "blockedReason": self.blocked_reason,
        }

    @property
    def digest(self) -> str:
        return sha256_payload(self.to_payload())


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    workspace_matches: bool
    artifact_manifest_matches: bool
    side_effects_outstanding: int
    details: tuple[str, ...] = ()

    @property
    def consistent(self) -> bool:
        return self.workspace_matches and self.artifact_manifest_matches and self.side_effects_outstanding == 0

    def to_payload(self) -> dict[str, Any]:
        return {
            "workspaceMatches": self.workspace_matches,
            "artifactManifestMatches": self.artifact_manifest_matches,
            "sideEffectsOutstanding": self.side_effects_outstanding,
            "consistent": self.consistent,
            "details": list(self.details),
        }


@dataclass(frozen=True, slots=True)
class IncidentReport:
    run_id: str
    created_at: datetime
    trigger: str
    failure_boundary: str
    plan: RollbackPlan
    reconciliation: ReconciliationResult
    executed: tuple[RecoveryStep, ...] = field(default_factory=tuple)
    preserved_evidence: tuple[str, ...] = field(default_factory=tuple)

    def to_payload(self) -> dict[str, Any]:
        return {
            "runId": self.run_id,
            "createdAt": isoformat_utc(self.created_at),
            "trigger": self.trigger,
            "failureBoundary": self.failure_boundary,
            "rollbackPlan": self.plan.to_payload(),
            "reconciliation": self.reconciliation.to_payload(),
            "executedSteps": [item.to_payload() for item in self.executed],
            "preservedEvidence": list(self.preserved_evidence),
        }

    @property
    def digest(self) -> str:
        return sha256_payload(self.to_payload())


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------


def find_failure_boundary(journal: RunJournal) -> tuple[str, str]:
    """The step where things went wrong, and what signalled it."""

    for event in reversed(journal.events):
        if event.event_type in ("step.failed", "step.blocked", "rollback.started"):
            return (event.step_id or "unknown", str(event.payload.get("signature", event.event_type)))
    return ("unknown", "no failure event recorded")


def last_consistent_checkpoint(
    journal: RunJournal,
    *,
    known_tree_digests: Sequence[str] = (),
    now: datetime | None = None,
) -> Checkpoint | None:
    """The newest unexpired checkpoint whose workspace we can still reproduce.

    A checkpoint pointing at a tree nobody can produce is not a recovery
    point; treating it as one is how a "successful" rollback lands on a state
    that never existed.
    """

    moment = now or utc_now()
    reproducible = set(known_tree_digests)
    for checkpoint in reversed(journal.checkpoints):
        if checkpoint.expires_at is not None and checkpoint.expires_at <= moment:
            continue
        if reproducible and checkpoint.workspace_tree_digest not in reproducible:
            continue
        return checkpoint
    return None


def plan_rollback(
    journal: RunJournal,
    *,
    patch: PatchSet | None,
    checkpoint: Checkpoint | None,
    data_reversibility_known: bool = False,
    risk_class: RiskClass = RiskClass.R2,
) -> RollbackPlan:
    """Build an ordered recovery plan for the current run state."""

    steps: list[RecoveryStep] = []
    order = 0
    blocked = ""

    if patch is not None and not patch.empty:
        order += 1
        steps.append(
            RecoveryStep(
                order=order,
                action=RecoveryAction.REVERSE_PATCH,
                target=f"{patch.changed_files} file(s)",
                idempotency_key=sha256_payload({"reverse": patch.digest})[:32],
                detail=(
                    "apply the inverse patch; this composes with unrelated changes, "
                    "unlike a whole-tree restore"
                ),
            )
        )
    elif checkpoint is not None:
        order += 1
        steps.append(
            RecoveryStep(
                order=order,
                action=RecoveryAction.SNAPSHOT_RESTORE,
                target=checkpoint.checkpoint_id,
                idempotency_key=sha256_payload({"restore": checkpoint.digest})[:32],
                detail=f"restore workspace tree {checkpoint.workspace_tree_digest}",
            )
        )

    cursor = checkpoint.side_effect_cursor if checkpoint is not None else 0
    outstanding: Sequence[SideEffect] = journal.uncompensated_since(cursor)
    for effect in outstanding:
        order += 1
        is_data = effect.kind in _DATA_EFFECTS
        if is_data and not data_reversibility_known:
            steps.append(
                RecoveryStep(
                    order=order,
                    action=RecoveryAction.HOLD_FOR_APPROVAL,
                    target=effect.target,
                    idempotency_key=effect.idempotency_key,
                    detail=(
                        f"'{effect.kind}' on '{effect.target}' has unknown reversibility; "
                        "an automatic data rollback could destroy the only copy of migrated data"
                    ),
                    automatic=False,
                    approval_reason="data rollback with unproven reversibility",
                )
            )
            continue
        if not effect.reversible:
            steps.append(
                RecoveryStep(
                    order=order,
                    action=RecoveryAction.HOLD_FOR_APPROVAL,
                    target=effect.target,
                    idempotency_key=effect.idempotency_key,
                    detail=f"'{effect.kind}' was recorded as irreversible; manual compensation required",
                    automatic=False,
                    approval_reason="irreversible side effect",
                )
            )
            continue
        steps.append(
            RecoveryStep(
                order=order,
                action=RecoveryAction.COMPENSATE,
                target=effect.target,
                idempotency_key=effect.idempotency_key,
                detail=(
                    f"compensate '{effect.kind}' using the recorded compensation; "
                    "the idempotency key makes a duplicate delivery a no-op"
                ),
            )
        )

    if any(effect.kind in _DATA_EFFECTS for effect in outstanding):
        steps.insert(
            0,
            RecoveryStep(
                order=0,
                action=RecoveryAction.STOP_WRITES,
                target="dual-write switch",
                idempotency_key=sha256_payload({"stop-writes": journal.run_id})[:32],
                detail="stop writing through the new path before anything else changes",
            ),
        )
        steps.insert(
            1,
            RecoveryStep(
                order=0,
                action=RecoveryAction.SWITCH_READS,
                target="read path",
                idempotency_key=sha256_payload({"switch-reads": journal.run_id})[:32],
                detail=(
                    "switch reads back to the old path and keep the additive structures in place; "
                    "dropping them would discard backfilled data"
                ),
            ),
        )

    if not steps:
        blocked = "nothing to roll back: no patch, no checkpoint and no outstanding side effects"
    if risk_class.rank >= RiskClass.R4.rank and any(not item.automatic for item in steps):
        blocked = blocked or "an R4 recovery contains steps that require approval before they may run"

    return RollbackPlan(
        checkpoint=checkpoint,
        steps=tuple(sorted(steps, key=lambda item: (item.order, item.action.value))),
        blocked_reason=blocked,
    )


# ---------------------------------------------------------------------------
# Execution and reconciliation
# ---------------------------------------------------------------------------


def execute_rollback(
    plan: RollbackPlan,
    journal: RunJournal,
    *,
    current: WorkspaceSnapshot,
    patch: PatchSet | None,
    now: datetime | None = None,
) -> tuple[WorkspaceSnapshot, tuple[RecoveryStep, ...]]:
    """Run the automatic steps, marking each compensation in the journal."""

    moment = now or utc_now()
    snapshot = current
    executed: list[RecoveryStep] = []
    for step in plan.automatic_steps:
        if step.action is RecoveryAction.REVERSE_PATCH and patch is not None:
            snapshot = patch.invert().apply(snapshot, verify_base=False)
            executed.append(step)
        elif step.action is RecoveryAction.COMPENSATE:
            effect = next(
                (item for item in journal.side_effects if item.idempotency_key == step.idempotency_key),
                None,
            )
            if effect is not None:
                journal.mark_compensated(effect.cursor, now=moment)
            executed.append(step)
        elif step.action in (RecoveryAction.STOP_WRITES, RecoveryAction.SWITCH_READS):
            #: These are declarations for the host to enact; the runtime
            #: records the intent and its idempotency key rather than
            #: pretending it flipped a production switch itself.
            executed.append(step)
    journal.append("rollback.completed", {"steps": len(executed)}, now=moment)
    return snapshot, tuple(executed)


def reconcile(
    journal: RunJournal,
    checkpoint: Checkpoint | None,
    snapshot: WorkspaceSnapshot,
    *,
    artifact_manifest_digest: str = "",
) -> ReconciliationResult:
    """Check that the world matches the state we claim to have recovered to."""

    details: list[str] = []
    workspace_matches = True
    manifest_matches = True

    if checkpoint is not None:
        workspace_matches = snapshot.tree_digest == checkpoint.workspace_tree_digest
        if not workspace_matches:
            details.append(
                f"workspace tree is {snapshot.tree_digest} but the checkpoint expects "
                f"{checkpoint.workspace_tree_digest}"
            )
        if artifact_manifest_digest:
            manifest_matches = artifact_manifest_digest == checkpoint.artifact_manifest_digest
            if not manifest_matches:
                details.append("artifact manifest does not match the checkpoint")
    else:
        details.append("no checkpoint to reconcile against; consistency is unverified")
        workspace_matches = False

    outstanding = len(journal.uncompensated_since(checkpoint.side_effect_cursor if checkpoint else 0))
    if outstanding:
        details.append(f"{outstanding} side effect(s) remain uncompensated")
    return ReconciliationResult(
        workspace_matches=workspace_matches,
        artifact_manifest_matches=manifest_matches,
        side_effects_outstanding=outstanding,
        details=tuple(details),
    )


def build_incident_report(
    journal: RunJournal,
    plan: RollbackPlan,
    reconciliation: ReconciliationResult,
    executed: Sequence[RecoveryStep],
    *,
    now: datetime | None = None,
    extra_evidence: Sequence[str] = (),
) -> IncidentReport:
    boundary, trigger = find_failure_boundary(journal)
    preserved = [
        f"journal:{journal.head_digest}",
        f"events:{journal.sequence}",
        *extra_evidence,
    ]
    return IncidentReport(
        run_id=journal.run_id,
        created_at=now or utc_now(),
        trigger=trigger,
        failure_boundary=boundary,
        plan=plan,
        reconciliation=reconciliation,
        executed=tuple(executed),
        preserved_evidence=tuple(preserved),
    )


def recovery_summary(report: IncidentReport) -> Mapping[str, Any]:
    return {
        "rollbackExecution": {
            "steps": [item.to_payload() for item in report.executed],
            "automatic": len(report.executed),
            "pendingApproval": [item.to_payload() for item in report.plan.approval_steps],
        },
        "recoveredCheckpoint": None if report.plan.checkpoint is None else report.plan.checkpoint.to_payload(),
        "incidentReport": report.to_payload(),
    }


__all__ = [
    "IncidentReport",
    "ReconciliationResult",
    "RecoveryAction",
    "RecoveryStep",
    "RollbackPlan",
    "build_incident_report",
    "execute_rollback",
    "find_failure_boundary",
    "last_consistent_checkpoint",
    "plan_rollback",
    "reconcile",
    "recovery_summary",
]
