"""Skill 17 — fine-grained human approval.

An approval here is a signature over a *specific* state, not a general
permission.  It binds four digests — request, plan, recipe lock and patch — and
any change to any of them invalidates it.  That is what stops "approved
yesterday" from covering a different diff today.

Other rules enforced structurally rather than by convention:

* **Timeout is refusal.**  An expired approval is not a weak yes.
* **No self-approval** when policy asks for it: the actor who produced the
  change cannot be the actor who signs it off.
* **Four eyes means two distinct subjects**, not two roles held by one person.
* **Conditions are checkable.**  ``approve-with-conditions`` carries predicates
  that are evaluated before execution, and an unmet condition blocks.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from .contracts import (
    ApprovalDecision as Decision,
)
from .contracts import (
    ContractError,
    RiskClass,
    isoformat_utc,
    optional_string,
    parse_timestamp,
    reject_unknown_fields,
    require_digest,
    require_identifier,
    require_mapping,
    require_string,
    require_string_sequence,
    sha256_payload,
    utc_now,
)
from .expressions import UNKNOWN, compile_expression

#: How long an approval remains valid when the policy does not say.
DEFAULT_TTL_SECONDS = 72 * 3600


@dataclass(frozen=True, slots=True)
class BoundDigests:
    """The exact state an approval covers."""

    request: str
    plan: str
    recipe_lock: str
    patch: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "request": self.request,
            "plan": self.plan,
            "recipeLock": self.recipe_lock,
            "patch": self.patch,
        }

    def differences(self, other: BoundDigests) -> tuple[str, ...]:
        found: list[str] = []
        for name in ("request", "plan", "recipe_lock", "patch"):
            if getattr(self, name) != getattr(other, name):
                found.append(name)
        return tuple(found)

    @classmethod
    def from_payload(cls, value: Mapping[str, Any]) -> BoundDigests:
        reject_unknown_fields(value, {"request", "plan", "recipeLock", "patch"}, "boundDigests")
        return cls(
            request=require_digest(value.get("request"), "boundDigests.request"),
            plan=require_digest(value.get("plan"), "boundDigests.plan"),
            recipe_lock=require_digest(value.get("recipeLock"), "boundDigests.recipeLock"),
            patch=require_digest(value.get("patch"), "boundDigests.patch"),
        )


@dataclass(frozen=True, slots=True)
class ApprovalCondition:
    id: str
    predicate: str
    satisfied: bool | None = None

    def evaluate(self, context: Mapping[str, Any]) -> bool | None:
        result = compile_expression(self.predicate).evaluate(context)
        return None if result is UNKNOWN else bool(result)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"id": self.id, "predicate": self.predicate}
        if self.satisfied is not None:
            payload["satisfied"] = self.satisfied
        return payload


@dataclass(frozen=True, slots=True)
class ApprovalContext:
    """The minimal sufficient context a reviewer needs — no more, no less."""

    run_id: str
    gate_id: str
    goals: tuple[str, ...]
    risk_class: RiskClass
    risk_reasons: tuple[str, ...]
    changed_files: int
    changed_lines: int
    diff_excerpt: str
    validation_summary: Mapping[str, Any]
    rollback_summary: Mapping[str, Any]
    alternatives: tuple[str, ...] = ()
    estimated_cost_usd: Decimal = Decimal("0")

    def to_payload(self) -> dict[str, Any]:
        return {
            "runId": self.run_id,
            "gateId": self.gate_id,
            "goals": list(self.goals),
            "riskClass": self.risk_class.value,
            "riskReasons": list(self.risk_reasons),
            "changedFiles": self.changed_files,
            "changedLines": self.changed_lines,
            "diffExcerpt": self.diff_excerpt[:20_000],
            "validation": dict(self.validation_summary),
            "rollback": dict(self.rollback_summary),
            "alternatives": list(self.alternatives),
            "estimatedCostUsd": str(self.estimated_cost_usd),
        }


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    approval_id: str
    run_id: str
    gate_id: str
    required_roles: tuple[str, ...]
    minimum_approvers: int
    bound: BoundDigests
    context: ApprovalContext
    requested_at: datetime
    expires_at: datetime
    requested_by: str = ""
    forbid_self_approval: bool = True

    def to_payload(self) -> dict[str, Any]:
        return {
            "approvalId": self.approval_id,
            "runId": self.run_id,
            "gateId": self.gate_id,
            "requiredRoles": list(self.required_roles),
            "minimumApprovers": self.minimum_approvers,
            "boundDigests": self.bound.to_payload(),
            "context": self.context.to_payload(),
            "requestedAt": isoformat_utc(self.requested_at),
            "expiresAt": isoformat_utc(self.expires_at),
            "requestedBy": self.requested_by,
            "forbidSelfApproval": self.forbid_self_approval,
        }

    @property
    def digest(self) -> str:
        return sha256_payload(self.to_payload())


@dataclass(frozen=True, slots=True)
class ApprovalRecord:
    approval_id: str
    run_id: str
    gate_id: str
    decision: Decision
    subject: str
    roles: tuple[str, ...]
    bound: BoundDigests
    decided_at: datetime
    conditions: tuple[ApprovalCondition, ...] = ()
    reason: str = ""
    expires_at: datetime | None = None
    signature: str = ""

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "approvalId": self.approval_id,
            "runId": self.run_id,
            "gateId": self.gate_id,
            "decision": self.decision.value,
            "actor": {"subject": self.subject, "roles": list(self.roles)},
            "boundDigests": self.bound.to_payload(),
            "decidedAt": isoformat_utc(self.decided_at),
        }
        if self.conditions:
            payload["conditions"] = [item.to_payload() for item in self.conditions]
        if self.reason:
            payload["reason"] = self.reason
        if self.expires_at:
            payload["expiresAt"] = isoformat_utc(self.expires_at)
        if self.signature:
            payload["signature"] = self.signature
        return payload

    @property
    def digest(self) -> str:
        payload = self.to_payload()
        payload.pop("signature", None)
        return sha256_payload(payload)

    @classmethod
    def from_payload(cls, value: Mapping[str, Any]) -> ApprovalRecord:
        mapping = require_mapping(value, "approval")
        reject_unknown_fields(
            mapping,
            {
                "approvalId",
                "runId",
                "gateId",
                "decision",
                "actor",
                "boundDigests",
                "conditions",
                "reason",
                "decidedAt",
                "expiresAt",
                "signature",
            },
            "approval",
        )
        actor = require_mapping(mapping.get("actor"), "approval.actor")
        reject_unknown_fields(actor, {"subject", "roles"}, "approval.actor")
        conditions = tuple(
            ApprovalCondition(
                id=require_identifier(item.get("id"), "approval.conditions[].id"),
                predicate=require_string(item.get("predicate"), "approval.conditions[].predicate", max_length=4096),
                satisfied=item.get("satisfied"),
            )
            for item in mapping.get("conditions", ())
            if isinstance(item, Mapping)
        )
        for condition in conditions:
            compile_expression(condition.predicate)
        decision_raw = require_string(mapping.get("decision"), "approval.decision", max_length=32)
        try:
            decision = Decision(decision_raw)
        except ValueError as exc:
            raise ContractError("invalid_enum", "approval.decision is not a known decision") from exc
        if decision is Decision.APPROVE_WITH_CONDITIONS and not conditions:
            raise ContractError(
                "conditions_required",
                "approve-with-conditions requires at least one checkable condition",
            )
        expires = mapping.get("expiresAt")
        return cls(
            approval_id=require_identifier(mapping.get("approvalId"), "approval.approvalId"),
            run_id=require_identifier(mapping.get("runId"), "approval.runId"),
            gate_id=require_identifier(mapping.get("gateId"), "approval.gateId"),
            decision=decision,
            subject=require_string(actor.get("subject"), "approval.actor.subject", max_length=256),
            roles=require_string_sequence(actor.get("roles"), "approval.actor.roles", allow_empty=False, unique=True),
            bound=BoundDigests.from_payload(require_mapping(mapping.get("boundDigests"), "approval.boundDigests")),
            decided_at=parse_timestamp(mapping.get("decidedAt"), "approval.decidedAt"),
            conditions=conditions,
            reason=optional_string(mapping.get("reason"), "approval.reason", max_length=4096) or "",
            expires_at=None if expires is None else parse_timestamp(expires, "approval.expiresAt"),
            signature=optional_string(mapping.get("signature"), "approval.signature", max_length=4096) or "",
        )


@dataclass(frozen=True, slots=True)
class ApprovalVerdict:
    satisfied: bool
    reasons: tuple[str, ...]
    accepted: tuple[str, ...] = ()
    rejected: tuple[str, ...] = ()
    unmet_conditions: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "satisfied": self.satisfied,
            "reasons": list(self.reasons),
            "acceptedApprovals": list(self.accepted),
            "rejectedApprovals": list(self.rejected),
            "unmetConditions": list(self.unmet_conditions),
        }


def request_approval(
    *,
    run_id: str,
    gate_id: str,
    roles: Sequence[str],
    minimum_approvers: int,
    bound: BoundDigests,
    context: ApprovalContext,
    now: datetime | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    requested_by: str = "",
    forbid_self_approval: bool = True,
) -> ApprovalRequest:
    moment = now or utc_now()
    return ApprovalRequest(
        approval_id=sha256_payload({"run": run_id, "gate": gate_id, "bound": bound.to_payload()})[:24],
        run_id=run_id,
        gate_id=gate_id,
        required_roles=tuple(sorted(set(roles))),
        minimum_approvers=max(1, minimum_approvers),
        bound=bound,
        context=context,
        requested_at=moment,
        expires_at=moment + timedelta(seconds=ttl_seconds),
        requested_by=requested_by,
        forbid_self_approval=forbid_self_approval,
    )


def evaluate_approvals(
    request: ApprovalRequest,
    records: Sequence[ApprovalRecord],
    *,
    current: BoundDigests,
    now: datetime | None = None,
    condition_context: Mapping[str, Any] | None = None,
) -> ApprovalVerdict:
    """Decide whether a gate is satisfied, and say precisely why not."""

    moment = now or utc_now()
    reasons: list[str] = []
    accepted: list[str] = []
    rejected: list[str] = []
    unmet: list[str] = []
    subjects: set[str] = set()

    drift = request.bound.differences(current)
    if drift:
        return ApprovalVerdict(
            satisfied=False,
            reasons=(
                "the approved state has changed since the request: " + ", ".join(drift)
                + "; an approval never generalises to a different patch",
            ),
        )

    if moment >= request.expires_at:
        reasons.append(
            f"the approval window closed at {isoformat_utc(request.expires_at)}; a timeout is a refusal"
        )

    for record in records:
        if record.run_id != request.run_id or record.gate_id != request.gate_id:
            rejected.append(f"{record.approval_id}: belongs to a different run or gate")
            continue
        record_drift = record.bound.differences(current)
        if record_drift:
            rejected.append(
                f"{record.approval_id}: bound to a different state ({', '.join(record_drift)})"
            )
            continue
        if record.expires_at is not None and moment >= record.expires_at:
            rejected.append(f"{record.approval_id}: expired at {isoformat_utc(record.expires_at)}")
            continue
        if request.forbid_self_approval and record.subject == request.requested_by and request.requested_by:
            rejected.append(f"{record.approval_id}: the requester may not approve their own change")
            continue
        if not set(record.roles) & set(request.required_roles):
            rejected.append(
                f"{record.approval_id}: actor holds {', '.join(record.roles)}, "
                f"none of the required {', '.join(request.required_roles)}"
            )
            continue
        if record.decision is Decision.REJECT:
            return ApprovalVerdict(
                satisfied=False,
                reasons=(f"{record.approval_id}: rejected by {record.subject} — {record.reason or 'no reason given'}",),
                rejected=(record.approval_id,),
            )
        if record.decision is Decision.REQUEST_CHANGES:
            return ApprovalVerdict(
                satisfied=False,
                reasons=(f"{record.approval_id}: changes requested by {record.subject}",),
                rejected=(record.approval_id,),
            )
        if record.decision is Decision.APPROVE_WITH_CONDITIONS:
            for condition in record.conditions:
                verdict = condition.evaluate(condition_context or {})
                if verdict is not True:
                    unmet.append(
                        f"{record.approval_id}/{condition.id}: "
                        + ("undecidable" if verdict is None else "not satisfied")
                    )
            if unmet:
                rejected.append(f"{record.approval_id}: conditions not met")
                continue
        accepted.append(record.approval_id)
        subjects.add(record.subject)

    if len(subjects) < request.minimum_approvers:
        reasons.append(
            f"{len(subjects)} distinct approver(s) recorded; {request.minimum_approvers} required"
        )
    covered = {role for record in records if record.approval_id in accepted for role in record.roles}
    missing = sorted(set(request.required_roles) - covered)
    if missing and len(request.required_roles) > 1:
        reasons.append("no approval from required role(s): " + ", ".join(missing))

    return ApprovalVerdict(
        satisfied=not reasons and not unmet,
        reasons=tuple(reasons),
        accepted=tuple(sorted(accepted)),
        rejected=tuple(sorted(rejected)),
        unmet_conditions=tuple(sorted(unmet)),
    )


def audit_record(
    request: ApprovalRequest,
    records: Sequence[ApprovalRecord],
    verdict: ApprovalVerdict,
) -> dict[str, Any]:
    """The non-repudiable trail for one gate."""

    return {
        "request": request.to_payload(),
        "requestDigest": request.digest,
        "decisions": [
            {**record.to_payload(), "digest": record.digest} for record in records
        ],
        "verdict": verdict.to_payload(),
        "auditDigest": sha256_payload(
            {
                "request": request.digest,
                "decisions": sorted(record.digest for record in records),
                "satisfied": verdict.satisfied,
            }
        ),
    }


def build_context(
    *,
    run_id: str,
    gate_id: str,
    goals: Sequence[str],
    risk_class: RiskClass,
    risk_reasons: Sequence[str],
    patch_summary: Mapping[str, Any],
    diff_excerpt: str,
    validation_summary: Mapping[str, Any],
    rollback_summary: Mapping[str, Any],
    alternatives: Sequence[str] = (),
    estimated_cost_usd: Decimal = Decimal("0"),
) -> ApprovalContext:
    return ApprovalContext(
        run_id=run_id,
        gate_id=gate_id,
        goals=tuple(goals),
        risk_class=risk_class,
        risk_reasons=tuple(risk_reasons),
        changed_files=int(patch_summary.get("changedFiles", 0)),
        changed_lines=int(patch_summary.get("changedLines", 0)),
        diff_excerpt=diff_excerpt,
        validation_summary=dict(validation_summary),
        rollback_summary=dict(rollback_summary),
        alternatives=tuple(alternatives),
        estimated_cost_usd=estimated_cost_usd,
    )


__all__ = [
    "DEFAULT_TTL_SECONDS",
    "ApprovalCondition",
    "ApprovalContext",
    "ApprovalRecord",
    "ApprovalRequest",
    "ApprovalVerdict",
    "BoundDigests",
    "audit_record",
    "build_context",
    "evaluate_approvals",
    "request_approval",
]
