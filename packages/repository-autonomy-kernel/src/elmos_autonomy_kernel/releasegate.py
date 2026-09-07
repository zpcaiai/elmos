"""Evidence release gate: the P05_DEPLOYMENT_COMPLETE decision.

This module exists to keep two things apart that everything else wants to
merge: what an agent *says* it finished, and what the machine evidence
*shows*.  A completion claim is an input here, never a reason — it can move the
decision towards ``BLOCKED`` (a run that hit its turn limit did not finish) and
never towards ``ACCEPTED``.

Every rule produces its own reason entry and no rule can be satisfied by
silence.  The one that catches most real releases is the third: a gate whose
status is ``NOT_RUN`` or ``SKIPPED`` is not a gate that passed, and treating
"no result" as "no objection" is precisely how an unrun security scan ships.
Health probes are the same shape — an unmeasured probe is ``None`` and is
rejected as unmeasured, distinct from a probe that measured false.

Waivers are deliberately narrow.  A human with a name and an expiry can waive a
*finding* or a *failing gate* within a stated scope.  Nobody can waive the
evidence chain itself: a broken seal, a stale bundle, a missing rollback plan,
an unmeasured health probe or a gate that never ran stay rejections, because a
waiver over those would be a waiver over the ability to know anything at all.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from .contracts import (
    digest,
    format_timestamp,
    parse_timestamp,
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
from .evidence import (
    BundleVerification,
    EvidenceKind,
    Outcome,
    SealedBundle,
    verify_bundle,
)
from .ports import EventStore
from .registry import register

__all__ = [
    "AcceptanceDecision",
    "CompletionClaim",
    "Decision",
    "Finding",
    "FindingStatus",
    "GateResult",
    "GateStatus",
    "HealthProbes",
    "ReleaseInputs",
    "ReleasePolicy",
    "Reason",
    "ReasonCode",
    "Severity",
    "Waiver",
    "default_seal_key",
    "evaluate",
    "handle",
    "record_decision",
    "set_default_seal_key",
]

register_codes(
    Category.RELEASE,
    "ACCEPTANCE_REJECTED",
    "RELEASE_BLOCKED",
    "ROLLBACK_NOT_READY",
    "DEPLOYMENT_GATE_FAILED",
    "WAIVER_INVALID",
)

#: A gate's status uses the same vocabulary as evidence outcomes on purpose:
#: "a skipped check is not a passed check" must mean one thing in both places.
GateStatus = Outcome


class Decision(StrEnum):
    """The only three verdicts this gate can issue.

    ``BLOCKED`` outranks ``REJECTED``: it means the gate could not reach a
    verdict (a blocked check, an escalation, a truncated run) and a human has
    to act, whereas ``REJECTED`` is a verdict.  Both withhold release, so the
    ordering is about routing, not about safety — and every reason for both is
    preserved in the decision either way.
    """

    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"


class Severity(StrEnum):
    """Finding severity.  P0/P1 are release-blocking by definition."""

    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    INFO = "INFO"

    @property
    def is_blocking(self) -> bool:
        return self in (Severity.P0, Severity.P1)


class FindingStatus(StrEnum):
    """Lifecycle of a finding.

    Only ``FIXED`` and ``REJECTED_FALSE_POSITIVE`` resolve one.  ``VALIDATED``
    is *worse* than ``OPEN`` — it means a second verifier reproduced it — so it
    blocks too, and ``WAIVED`` blocks unless a live, in-scope waiver backs it.
    """

    OPEN = "OPEN"
    VALIDATED = "VALIDATED"
    REJECTED_FALSE_POSITIVE = "REJECTED_FALSE_POSITIVE"
    FIXED = "FIXED"
    WAIVED = "WAIVED"

    @property
    def is_resolved(self) -> bool:
        return self in (FindingStatus.FIXED, FindingStatus.REJECTED_FALSE_POSITIVE)


class ReasonCode(StrEnum):
    """Why the decision came out the way it did, one entry per triggered rule."""

    GATE_BLOCKED = "GATE_BLOCKED"
    GATE_FAILED = "GATE_FAILED"
    GATE_NOT_RUN = "GATE_NOT_RUN"
    MANDATORY_GATE_MISSING = "MANDATORY_GATE_MISSING"
    EVIDENCE_BUNDLE_INVALID = "EVIDENCE_BUNDLE_INVALID"
    EVIDENCE_STALE = "EVIDENCE_STALE"
    EVIDENCE_UNKNOWN = "EVIDENCE_UNKNOWN"
    EVIDENCE_KIND_MISSING = "EVIDENCE_KIND_MISSING"
    EVIDENCE_NOT_OBSERVED = "EVIDENCE_NOT_OBSERVED"
    OPEN_BLOCKING_FINDING = "OPEN_BLOCKING_FINDING"
    ROLLBACK_NOT_READY = "ROLLBACK_NOT_READY"
    HEALTH_PROBE_FAILED = "HEALTH_PROBE_FAILED"
    HEALTH_PROBE_UNMEASURED = "HEALTH_PROBE_UNMEASURED"
    POLICY_DENIED = "POLICY_DENIED"
    POLICY_REQUIRES_HUMAN = "POLICY_REQUIRES_HUMAN"
    POLICY_DECISION_MISSING = "POLICY_DECISION_MISSING"
    MAX_TURNS_EXHAUSTED = "MAX_TURNS_EXHAUSTED"
    RUN_INTERRUPTED = "RUN_INTERRUPTED"
    NO_JUSTIFYING_EVIDENCE = "NO_JUSTIFYING_EVIDENCE"
    WAIVER_APPLIED = "WAIVER_APPLIED"
    WAIVER_EXPIRED = "WAIVER_EXPIRED"
    WAIVER_OUT_OF_SCOPE = "WAIVER_OUT_OF_SCOPE"


_BLOCKING_REASONS = frozenset({
    ReasonCode.GATE_BLOCKED,
    ReasonCode.POLICY_REQUIRES_HUMAN,
    ReasonCode.MAX_TURNS_EXHAUSTED,
    ReasonCode.RUN_INTERRUPTED,
})
_INFORMATIONAL_REASONS = frozenset({ReasonCode.WAIVER_APPLIED})


@dataclass(frozen=True, slots=True)
class Reason:
    """One rule firing against one subject."""

    code: ReasonCode
    subject: str
    detail: str

    def __post_init__(self) -> None:
        require_str(self.subject, "reason.subject", max_length=256)
        require_str(self.detail, "reason.detail")

    @property
    def blocks(self) -> bool:
        return self.code in _BLOCKING_REASONS

    @property
    def rejects(self) -> bool:
        return self.code not in _BLOCKING_REASONS and self.code not in _INFORMATIONAL_REASONS

    def to_payload(self) -> dict[str, Any]:
        return {"code": str(self.code), "subject": self.subject, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class GateResult:
    """One mandatory check and the evidence it says justifies it.

    ``required_evidence_kinds`` is on the gate rather than on a global policy
    because the requirement is a property of the check: "unit tests passed" is
    only meaningful with a test report, and a gate that passes while citing an
    execution trace instead has not demonstrated what it claims.
    """

    gate_id: str
    status: GateStatus
    evidence_ids: tuple[str, ...] = ()
    required_evidence_kinds: tuple[EvidenceKind, ...] = ()
    detail: str = ""

    def __post_init__(self) -> None:
        require_identifier(self.gate_id, "gate.gate_id")
        if not isinstance(self.status, Outcome):
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"gate {self.gate_id!r} has unknown status {self.status!r}",
                recommended_action=f"use one of {sorted(item.value for item in Outcome)}",
            )
        for index, item in enumerate(self.evidence_ids):
            require_identifier(item, f"gate.evidence_ids[{index}]")
        for item in self.required_evidence_kinds:
            if not isinstance(item, EvidenceKind):
                raise KernelError(
                    code="MALFORMED_INPUT",
                    message=f"gate {self.gate_id!r} requires unknown evidence kind {item!r}",
                    recommended_action=f"use one of {sorted(k.value for k in EvidenceKind)}",
                )

    def to_payload(self) -> dict[str, Any]:
        return {
            "gateId": self.gate_id,
            "status": str(self.status),
            "evidenceIds": list(self.evidence_ids),
            "requiredEvidenceKinds": [str(item) for item in self.required_evidence_kinds],
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class Finding:
    """A defect with a severity and a lifecycle state.

    ``confidence`` is optional and, when absent, is reported as unmeasured.  It
    never downgrades a P0/P1: "we are not sure how sure we are" is not a reason
    to ship.
    """

    finding_id: str
    severity: Severity
    status: FindingStatus
    evidence_ids: tuple[str, ...] = ()
    confidence: Decimal | None = None
    description: str = ""

    def __post_init__(self) -> None:
        require_identifier(self.finding_id, "finding.finding_id")
        if not isinstance(self.severity, Severity):
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"finding {self.finding_id!r} has unknown severity {self.severity!r}",
                recommended_action=f"use one of {sorted(s.value for s in Severity)}",
            )
        if not isinstance(self.status, FindingStatus):
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"finding {self.finding_id!r} has unknown status {self.status!r}",
                recommended_action=f"use one of {sorted(s.value for s in FindingStatus)}",
            )
        if self.confidence is not None and not isinstance(self.confidence, Decimal):
            raise KernelError(
                code="MALFORMED_INPUT",
                message="finding.confidence must be a Decimal or None",
                recommended_action="send confidence as a decimal string, never a float",
            )

    def to_payload(self) -> dict[str, Any]:
        return {
            "findingId": self.finding_id,
            "severity": str(self.severity),
            "status": str(self.status),
            "evidenceIds": list(self.evidence_ids),
            "confidence": self.confidence,
            "confidenceMeasured": self.confidence is not None,
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class RollbackPlan:
    """How the release is undone.

    ``complete`` is stated by whoever built the plan and verified separately;
    an incomplete plan is not a plan, and its absence is not "no rollback
    needed".
    """

    plan_id: str
    complete: bool
    steps: tuple[str, ...] = ()
    evidence_id: str = ""

    def __post_init__(self) -> None:
        require_identifier(self.plan_id, "rollback.plan_id")
        require_bool(self.complete, "rollback.complete")
        if self.complete and not self.steps:
            raise KernelError(
                code="ROLLBACK_NOT_READY",
                message=f"rollback plan {self.plan_id!r} claims completeness with no steps",
                recommended_action="record the rollback steps or mark the plan incomplete",
            )

    def to_payload(self) -> dict[str, Any]:
        return {
            "planId": self.plan_id,
            "complete": self.complete,
            "steps": list(self.steps),
            "evidenceId": self.evidence_id,
        }


@dataclass(frozen=True, slots=True)
class HealthProbes:
    """Post-deployment probes.  ``None`` means unmeasured, not false.

    The distinction is load bearing: a probe that failed tells you the deploy
    is bad, a probe that never ran tells you nothing, and collapsing the second
    into the first (or, worse, into ``True``) is how a release is accepted on
    the strength of a probe that never executed.
    """

    livez: bool | None = None
    readyz: bool | None = None
    metrics: bool | None = None
    version: bool | None = None

    def __post_init__(self) -> None:
        for name in ("livez", "readyz", "metrics", "version"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, bool):
                raise KernelError(
                    code="MALFORMED_INPUT",
                    message=f"health probe {name!r} must be true, false or absent",
                    recommended_action="report an unrun probe as absent, never as false",
                )

    def items(self) -> tuple[tuple[str, bool | None], ...]:
        return (
            ("livez", self.livez),
            ("readyz", self.readyz),
            ("metrics", self.metrics),
            ("version", self.version),
        )

    @property
    def all_true(self) -> bool:
        return all(value is True for _, value in self.items())

    def to_payload(self) -> dict[str, Any]:
        return {
            name: value for name, value in self.items()
        } | {"measured": [name for name, value in self.items() if value is not None]}


@dataclass(frozen=True, slots=True)
class Waiver:
    """A named human accepting a named risk until a named time.

    All three are required.  A waiver without an approver is anonymous, one
    without an expiry is permanent, and one without a scope is a blank cheque;
    each of those has been used at least once to ship something nobody would
    have signed for.
    """

    waiver_id: str
    approver: str
    scope: tuple[str, ...]
    expires_at: datetime
    reason: str

    def __post_init__(self) -> None:
        require_identifier(self.waiver_id, "waiver.waiver_id")
        require_str(self.approver, "waiver.approver", max_length=256)
        if not self.scope:
            raise KernelError(
                code="WAIVER_INVALID",
                message=f"waiver {self.waiver_id!r} has an empty scope",
                recommended_action="name the gate ids or finding ids the waiver covers",
            )
        for index, item in enumerate(self.scope):
            require_identifier(item, f"waiver.scope[{index}]")
        format_timestamp(self.expires_at)
        require_str(self.reason, "waiver.reason")

    def is_live(self, now: datetime) -> bool:
        """True only while the waiver has not expired."""

        return self.expires_at > now

    def covers(self, subject: str, *, now: datetime) -> bool:
        return subject in self.scope and self.is_live(now)

    def to_payload(self) -> dict[str, Any]:
        return {
            "waiverId": self.waiver_id,
            "approver": self.approver,
            "scope": list(self.scope),
            "expiresAt": format_timestamp(self.expires_at),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class CompletionClaim:
    """What the agent says.  It has no acceptance force whatsoever.

    The only influence it has is negative: a run that exhausted its turns or
    was interrupted cannot be accepted, regardless of how confident the claim
    is, because the work simply did not finish.
    """

    claimant: str
    asserts_complete: bool = False
    max_turns_exhausted: bool = False
    interrupted: bool = False
    statement: str = ""

    def __post_init__(self) -> None:
        require_identifier(self.claimant, "completion_claim.claimant")
        require_bool(self.asserts_complete, "completion_claim.asserts_complete")
        require_bool(self.max_turns_exhausted, "completion_claim.max_turns_exhausted")
        require_bool(self.interrupted, "completion_claim.interrupted")

    def to_payload(self) -> dict[str, Any]:
        return {
            "claimant": self.claimant,
            "assertsComplete": self.asserts_complete,
            "maxTurnsExhausted": self.max_turns_exhausted,
            "interrupted": self.interrupted,
            "statement": self.statement,
            "acceptanceForce": "none",
        }


@dataclass(frozen=True, slots=True)
class ReleasePolicy:
    """What must exist before a release can even be evaluated."""

    mandatory_gate_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.mandatory_gate_ids:
            raise KernelError(
                code="POLICY_DENIED",
                message="a release policy with no mandatory gates cannot accept anything",
                recommended_action="declare at least one mandatory gate",
            )
        for index, item in enumerate(self.mandatory_gate_ids):
            require_identifier(item, f"policy.mandatory_gate_ids[{index}]")

    def to_payload(self) -> dict[str, Any]:
        return {"mandatoryGateIds": list(self.mandatory_gate_ids)}


@dataclass(frozen=True, slots=True)
class ReleaseInputs:
    """Everything the decision is allowed to look at."""

    run_id: str
    repo_snapshot_sha: str
    decided_at: datetime
    policy: ReleasePolicy
    gate_results: tuple[GateResult, ...] = ()
    findings: tuple[Finding, ...] = ()
    rollback_plan: RollbackPlan | None = None
    health: HealthProbes = HealthProbes()
    bundle: SealedBundle | None = None
    policy_decision: Mapping[str, Any] | None = None
    completion_claim: CompletionClaim | None = None
    waivers: tuple[Waiver, ...] = ()

    def __post_init__(self) -> None:
        require_identifier(self.run_id, "inputs.run_id")
        require_str(self.repo_snapshot_sha, "inputs.repo_snapshot_sha", max_length=128)
        format_timestamp(self.decided_at)
        seen: set[str] = set()
        for gate in self.gate_results:
            if gate.gate_id in seen:
                raise KernelError(
                    code="MALFORMED_INPUT",
                    message=f"gate {gate.gate_id!r} appears twice in the gate results",
                    recommended_action="deduplicate gate results before gating",
                )
            seen.add(gate.gate_id)

    def to_payload(self) -> dict[str, Any]:
        return {
            "runId": self.run_id,
            "repoSnapshotSha": self.repo_snapshot_sha,
            "decidedAt": format_timestamp(self.decided_at),
            "policy": self.policy.to_payload(),
            "gateResults": [gate.to_payload()
                            for gate in sorted(self.gate_results, key=lambda g: g.gate_id)],
            "findings": [item.to_payload()
                         for item in sorted(self.findings, key=lambda f: f.finding_id)],
            "rollbackPlan": (
                self.rollback_plan.to_payload() if self.rollback_plan is not None else None
            ),
            "health": self.health.to_payload(),
            "bundleDigest": self.bundle.bundle_digest if self.bundle is not None else None,
            "bundleSeal": self.bundle.seal if self.bundle is not None else None,
            "policyDecision": (
                dict(self.policy_decision) if self.policy_decision is not None else None
            ),
            "completionClaim": (
                self.completion_claim.to_payload() if self.completion_claim is not None else None
            ),
            "waivers": [item.to_payload()
                        for item in sorted(self.waivers, key=lambda w: w.waiver_id)],
        }

    @property
    def digest(self) -> str:
        return digest(self.to_payload())


@dataclass(frozen=True, slots=True)
class AcceptanceDecision:
    """The gate's verdict, its reasons, and the evidence that justified it.

    An ``ACCEPTED`` decision must name the evidence ids that carried it — the
    construction refuses otherwise — so "accepted" is never a bare word an
    auditor has to take on trust.  ``digest`` is a pure function of the
    decision payload, and the payload is a pure function of the inputs, so
    re-running the gate on the same inputs is byte-identical.
    """

    decision_id: str
    run_id: str
    decision: Decision
    reasons: tuple[Reason, ...]
    justifying_evidence_ids: tuple[str, ...]
    waivers_applied: tuple[str, ...]
    gate_results: tuple[GateResult, ...]
    deployment_complete: bool
    decided_at: datetime
    inputs_digest: str

    def __post_init__(self) -> None:
        require_identifier(self.decision_id, "decision.decision_id")
        require_identifier(self.run_id, "decision.run_id")
        if self.decision is Decision.ACCEPTED and not self.justifying_evidence_ids:
            raise KernelError(
                code="EVIDENCE_MISSING",
                message="an ACCEPTED decision must name the evidence that justified it",
                recommended_action="do not accept a release no evidence supports",
            )
        if self.deployment_complete and self.decision is not Decision.ACCEPTED:
            raise KernelError(
                code="DEPLOYMENT_GATE_FAILED",
                message="P05_DEPLOYMENT_COMPLETE cannot be attested on a non-accepted decision",
                recommended_action="treat this as a kernel defect",
            )

    def to_payload(self) -> dict[str, Any]:
        return {
            "acceptanceDecisionId": self.decision_id,
            "runId": self.run_id,
            "decision": str(self.decision),
            "reasons": [reason.to_payload() for reason in self.reasons],
            "justifyingEvidenceIds": list(self.justifying_evidence_ids),
            "waiversApplied": list(self.waivers_applied),
            "gateResults": [gate.to_payload() for gate in self.gate_results],
            "deploymentComplete": self.deployment_complete,
            "decidedAt": format_timestamp(self.decided_at),
            "inputsDigest": self.inputs_digest,
        }

    @property
    def digest(self) -> str:
        return digest(self.to_payload())

    def reason_codes(self) -> tuple[str, ...]:
        return tuple(str(reason.code) for reason in self.reasons)


def _waiver_for(waivers: Sequence[Waiver], subject: str, now: datetime,
                reasons: list[Reason]) -> Waiver | None:
    """Find a live, in-scope waiver, recording why a candidate did not apply."""

    expired: list[Waiver] = []
    for waiver in sorted(waivers, key=lambda item: item.waiver_id):
        if subject not in waiver.scope:
            continue
        if waiver.is_live(now):
            return waiver
        expired.append(waiver)
    for waiver in expired:
        reasons.append(Reason(
            code=ReasonCode.WAIVER_EXPIRED,
            subject=subject,
            detail=(
                f"waiver {waiver.waiver_id} by {waiver.approver} expired at "
                f"{format_timestamp(waiver.expires_at)} and does not unblock "
                f"{subject}"
            ),
        ))
    return None


def _check_bundle(inputs: ReleaseInputs, seal_key: bytes,
                  reasons: list[Reason]) -> BundleVerification | None:
    if inputs.bundle is None:
        reasons.append(Reason(
            code=ReasonCode.EVIDENCE_BUNDLE_INVALID,
            subject="evidence-bundle",
            detail="no evidence bundle was supplied; a release without evidence is not a release",
        ))
        return None
    verification = verify_bundle(inputs.bundle, key=seal_key)
    if not verification.valid:
        reasons.append(Reason(
            code=ReasonCode.EVIDENCE_BUNDLE_INVALID,
            subject="evidence-bundle",
            detail=f"evidence bundle failed verification: {verification.reason}",
        ))
        return None
    if verification.repo_snapshot_sha != inputs.repo_snapshot_sha:
        reasons.append(Reason(
            code=ReasonCode.EVIDENCE_STALE,
            subject="evidence-bundle",
            detail=(
                f"bundle is bound to snapshot {verification.repo_snapshot_sha} "
                f"but the release is for {inputs.repo_snapshot_sha}"
            ),
        ))
        return None
    return verification


def _check_policy(inputs: ReleaseInputs, reasons: list[Reason]) -> None:
    decision = inputs.policy_decision
    if decision is None:
        reasons.append(Reason(
            code=ReasonCode.POLICY_DECISION_MISSING,
            subject="policy",
            detail="no policy decision accompanied the release; absence is a deny",
        ))
        return
    verdict = str(decision.get("decision", ""))
    if verdict == "ALLOW":
        return
    if verdict == "DENY":
        reasons.append(Reason(
            code=ReasonCode.POLICY_DENIED,
            subject="policy",
            detail=f"policy denied the release: {decision.get('reason', 'no reason given')}",
        ))
        return
    reasons.append(Reason(
        code=(
            ReasonCode.POLICY_REQUIRES_HUMAN if verdict in {
                "ASK_USER", "REQUIRE_ESCALATION", "REQUIRE_SECOND_REVIEW", "MODIFY_INPUT",
            } else ReasonCode.POLICY_DENIED
        ),
        subject="policy",
        detail=f"policy returned {verdict!r}, which is not an allow",
    ))


def _check_gates(inputs: ReleaseInputs, verification: BundleVerification | None,
                 reasons: list[Reason], waived: set[str]) -> tuple[str, ...]:
    """Apply the gate rules and return the evidence ids that justify passes."""

    known = {eid for eid, _ in verification.evidence_kinds} if verification else set()
    kinds = dict(verification.evidence_kinds) if verification else {}
    outcomes = dict(verification.evidence_outcomes) if verification else {}
    present = {gate.gate_id for gate in inputs.gate_results}
    for gate_id in sorted(set(inputs.policy.mandatory_gate_ids) - present):
        reasons.append(Reason(
            code=ReasonCode.MANDATORY_GATE_MISSING,
            subject=gate_id,
            detail="the policy requires this gate and no result was supplied for it",
        ))

    justifying: set[str] = set()
    for gate in sorted(inputs.gate_results, key=lambda item: item.gate_id):
        if gate.status in (Outcome.BLOCKED, Outcome.INFRA_FAILURE):
            reasons.append(Reason(
                code=ReasonCode.GATE_BLOCKED,
                subject=gate.gate_id,
                detail=f"gate is {gate.status}; the release cannot be decided on it",
            ))
            continue
        if gate.status is Outcome.FAIL:
            waiver = _waiver_for(inputs.waivers, gate.gate_id, inputs.decided_at, reasons)
            if waiver is None:
                reasons.append(Reason(
                    code=ReasonCode.GATE_FAILED,
                    subject=gate.gate_id,
                    detail="gate failed",
                ))
            else:
                waived.add(waiver.waiver_id)
                reasons.append(Reason(
                    code=ReasonCode.WAIVER_APPLIED,
                    subject=gate.gate_id,
                    detail=(
                        f"failing gate waived by {waiver.approver} under waiver "
                        f"{waiver.waiver_id} until {format_timestamp(waiver.expires_at)}"
                    ),
                ))
            continue
        if not gate.status.is_pass:
            reasons.append(Reason(
                code=ReasonCode.GATE_NOT_RUN,
                subject=gate.gate_id,
                detail=(
                    f"gate status is {gate.status}; an unrun, skipped or partial check "
                    "is not a passed check and cannot be waived"
                ),
            ))
            continue

        # From here the gate claims PASS, so its evidence has to hold it up.
        satisfied: set[str] = set()
        for evidence_id in gate.evidence_ids:
            if evidence_id not in known:
                reasons.append(Reason(
                    code=ReasonCode.EVIDENCE_UNKNOWN,
                    subject=gate.gate_id,
                    detail=f"gate cites evidence {evidence_id} that is not in the sealed bundle",
                ))
                continue
            if outcomes.get(evidence_id) != str(Outcome.PASS):
                reasons.append(Reason(
                    code=ReasonCode.EVIDENCE_NOT_OBSERVED,
                    subject=gate.gate_id,
                    detail=(
                        f"gate passed citing evidence {evidence_id} whose outcome is "
                        f"{outcomes.get(evidence_id, 'unknown')}"
                    ),
                ))
                continue
            satisfied.add(kinds.get(evidence_id, ""))
            justifying.add(evidence_id)
        for required in sorted(str(item) for item in gate.required_evidence_kinds):
            if required not in satisfied:
                reasons.append(Reason(
                    code=ReasonCode.EVIDENCE_KIND_MISSING,
                    subject=gate.gate_id,
                    detail=f"gate passed without any verified {required} evidence",
                ))
    return tuple(sorted(justifying))


def _check_findings(inputs: ReleaseInputs, reasons: list[Reason], waived: set[str]) -> None:
    for finding in sorted(inputs.findings, key=lambda item: item.finding_id):
        if not finding.severity.is_blocking or finding.status.is_resolved:
            continue
        waiver = _waiver_for(inputs.waivers, finding.finding_id, inputs.decided_at, reasons)
        if waiver is None:
            reasons.append(Reason(
                code=ReasonCode.OPEN_BLOCKING_FINDING,
                subject=finding.finding_id,
                detail=(
                    f"{finding.severity} finding is {finding.status} and no live waiver "
                    "covers it"
                ),
            ))
            continue
        waived.add(waiver.waiver_id)
        reasons.append(Reason(
            code=ReasonCode.WAIVER_APPLIED,
            subject=finding.finding_id,
            detail=(
                f"{finding.severity} finding waived by {waiver.approver} under waiver "
                f"{waiver.waiver_id} until {format_timestamp(waiver.expires_at)}"
            ),
        ))


def _check_rollback_and_health(inputs: ReleaseInputs, reasons: list[Reason]) -> None:
    plan = inputs.rollback_plan
    if plan is None:
        reasons.append(Reason(
            code=ReasonCode.ROLLBACK_NOT_READY,
            subject="rollback",
            detail="no rollback plan was supplied",
        ))
    elif not plan.complete:
        reasons.append(Reason(
            code=ReasonCode.ROLLBACK_NOT_READY,
            subject=plan.plan_id,
            detail="rollback plan is marked incomplete",
        ))
    for name, value in inputs.health.items():
        if value is None:
            reasons.append(Reason(
                code=ReasonCode.HEALTH_PROBE_UNMEASURED,
                subject=f"health.{name}",
                detail="probe was not measured; an unmeasured probe is not a passing probe",
            ))
        elif value is not True:
            reasons.append(Reason(
                code=ReasonCode.HEALTH_PROBE_FAILED,
                subject=f"health.{name}",
                detail="probe reported false",
            ))


def _check_claim(inputs: ReleaseInputs, reasons: list[Reason]) -> None:
    claim = inputs.completion_claim
    if claim is None:
        return
    if claim.max_turns_exhausted:
        reasons.append(Reason(
            code=ReasonCode.MAX_TURNS_EXHAUSTED,
            subject=claim.claimant,
            detail="the run hit its turn limit; that is BLOCKED, never complete",
        ))
    if claim.interrupted:
        reasons.append(Reason(
            code=ReasonCode.RUN_INTERRUPTED,
            subject=claim.claimant,
            detail="the run was interrupted; no verdict was reached",
        ))


def evaluate(inputs: ReleaseInputs, *, seal_key: bytes) -> AcceptanceDecision:
    """Decide the release from evidence alone.

    Rules run in a fixed order and each appends its own reason entries; nothing
    short-circuits, so the decision carries the complete list of what was wrong
    rather than the first thing that was wrong.  The verdict is then the worst
    of what the reasons say: any blocking reason gives ``BLOCKED``, any
    rejecting reason gives ``REJECTED``, and only a clean sweep gives
    ``ACCEPTED``.
    """

    reasons: list[Reason] = []
    waived: set[str] = set()
    _check_claim(inputs, reasons)
    verification = _check_bundle(inputs, seal_key, reasons)
    _check_policy(inputs, reasons)
    justifying = _check_gates(inputs, verification, reasons, waived)
    _check_findings(inputs, reasons, waived)
    _check_rollback_and_health(inputs, reasons)

    if any(reason.blocks for reason in reasons):
        decision = Decision.BLOCKED
    elif any(reason.rejects for reason in reasons):
        decision = Decision.REJECTED
    else:
        decision = Decision.ACCEPTED
    if decision is Decision.ACCEPTED and not justifying:
        # Nothing objected, but nothing testified either.  Fail closed.
        reasons.append(Reason(
            code=ReasonCode.NO_JUSTIFYING_EVIDENCE,
            subject=inputs.run_id,
            detail="no verified evidence supports any passing gate",
        ))
        decision = Decision.REJECTED
        justifying = ()

    inputs_digest = inputs.digest
    return AcceptanceDecision(
        decision_id=f"acceptance-{inputs_digest.split(':', 1)[1][:32]}",
        run_id=inputs.run_id,
        decision=decision,
        reasons=tuple(reasons),
        justifying_evidence_ids=justifying if decision is Decision.ACCEPTED else (),
        waivers_applied=tuple(sorted(waived)),
        gate_results=tuple(sorted(inputs.gate_results, key=lambda item: item.gate_id)),
        # P05_DEPLOYMENT_COMPLETE mirrors policies/rego/release.rego: every gate
        # passed on its own merits.  A waiver is a human decision to release
        # anyway, which is an acceptance but never an attestation.
        deployment_complete=decision is Decision.ACCEPTED and not waived,
        decided_at=inputs.decided_at,
        inputs_digest=inputs_digest,
    )


def record_decision(events: EventStore, stream_id: str, decision: AcceptanceDecision, *,
                    fencing_token: int) -> Mapping[str, Any]:
    """Append the decision to the run's event stream, once.

    The idempotency key is the decision digest, so a duplicated delivery of the
    same decision returns the original event instead of recording a second
    acceptance, and a superseded worker is fenced out rather than allowed to
    write an acceptance behind the current owner's back.
    """

    require_int(fencing_token, "fencing_token", minimum=1)
    payload = decision.to_payload()
    event = events.append(stream_id, payload, idempotency_key=decision.digest,
                          fencing_token=fencing_token)
    return {
        "sequence": event.sequence,
        "eventId": event.event_id,
        "hashChain": event.hash_chain,
        "decisionDigest": decision.digest,
    }


# --- registry entry point ----------------------------------------------------

_DEFAULT_SEAL_KEY: bytes | None = None


def set_default_seal_key(key: bytes | None) -> None:
    """Bind the bundle-seal key used by :func:`handle`.

    The key is a secret, so it is bound out of band and never travels in a
    request, a response, a log line or an error message.
    """

    global _DEFAULT_SEAL_KEY
    _DEFAULT_SEAL_KEY = bytes(key) if key is not None else None


def default_seal_key() -> bytes:
    """Return the bound seal key or fail closed."""

    if _DEFAULT_SEAL_KEY is None:
        raise KernelError(
            code="EVIDENCE_UNVERIFIABLE",
            message="no evidence seal key is bound; the bundle cannot be verified",
            recommended_action="bind the seal key with set_default_seal_key at startup",
        )
    return _DEFAULT_SEAL_KEY


def _decode_gate(payload: Mapping[str, Any]) -> GateResult:
    reject_unknown_fields(
        payload,
        {"gateId", "status", "evidenceIds", "requiredEvidenceKinds", "detail"},
        field_name="gate result",
    )
    status = require_str(payload.get("status"), "gate.status", max_length=32)
    if status not in {item.value for item in Outcome}:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"unknown gate status {status!r}",
            recommended_action=f"use one of {sorted(item.value for item in Outcome)}",
        )
    kinds: list[EvidenceKind] = []
    for item in require_str_seq(payload.get("requiredEvidenceKinds", ()),
                                "gate.requiredEvidenceKinds"):
        if item not in {kind.value for kind in EvidenceKind}:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"unknown required evidence kind {item!r}",
                recommended_action=f"use one of {sorted(k.value for k in EvidenceKind)}",
            )
        kinds.append(EvidenceKind(item))
    return GateResult(
        gate_id=require_identifier(payload.get("gateId"), "gate.gateId"),
        status=Outcome(status),
        evidence_ids=require_str_seq(payload.get("evidenceIds", ()), "gate.evidenceIds"),
        required_evidence_kinds=tuple(kinds),
        detail=str(payload.get("detail", "")),
    )


def _decode_finding(payload: Mapping[str, Any]) -> Finding:
    reject_unknown_fields(
        payload,
        {"findingId", "severity", "status", "evidenceIds", "confidence", "description"},
        field_name="finding",
    )
    severity = require_str(payload.get("severity"), "finding.severity", max_length=16)
    if severity not in {item.value for item in Severity}:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"unknown finding severity {severity!r}",
            recommended_action=f"use one of {sorted(s.value for s in Severity)}",
        )
    status = require_str(payload.get("status"), "finding.status", max_length=32)
    if status not in {item.value for item in FindingStatus}:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"unknown finding status {status!r}",
            recommended_action=f"use one of {sorted(s.value for s in FindingStatus)}",
        )
    raw_confidence = payload.get("confidence")
    confidence = (
        None if raw_confidence is None
        else require_decimal(raw_confidence, "finding.confidence", minimum=Decimal(0))
    )
    return Finding(
        finding_id=require_identifier(payload.get("findingId"), "finding.findingId"),
        severity=Severity(severity),
        status=FindingStatus(status),
        evidence_ids=require_str_seq(payload.get("evidenceIds", ()), "finding.evidenceIds"),
        confidence=confidence,
        description=str(payload.get("description", "")),
    )


def _decode_waiver(payload: Mapping[str, Any]) -> Waiver:
    reject_unknown_fields(
        payload,
        {"waiverId", "approver", "scope", "expiresAt", "reason"},
        field_name="waiver",
    )
    return Waiver(
        waiver_id=require_identifier(payload.get("waiverId"), "waiver.waiverId"),
        approver=require_str(payload.get("approver"), "waiver.approver", max_length=256),
        scope=require_str_seq(payload.get("scope", ()), "waiver.scope", allow_empty=False),
        expires_at=parse_timestamp(payload.get("expiresAt"), "waiver.expiresAt"),
        reason=require_str(payload.get("reason"), "waiver.reason"),
    )


def _decode_health(payload: Mapping[str, Any]) -> HealthProbes:
    reject_unknown_fields(payload, {"livez", "readyz", "metrics", "version"},
                          field_name="health")
    values: dict[str, bool | None] = {}
    for name in ("livez", "readyz", "metrics", "version"):
        raw = payload.get(name)
        values[name] = None if raw is None else require_bool(raw, f"health.{name}")
    return HealthProbes(**values)


def _decode_bundle(payload: Mapping[str, Any]) -> SealedBundle:
    reject_unknown_fields(payload, {"payload", "seal", "algorithm"}, field_name="bundle")
    return SealedBundle(
        payload=require_mapping(payload.get("payload"), "bundle.payload"),
        seal=require_str(payload.get("seal"), "bundle.seal", max_length=256),
        algorithm=str(payload.get("algorithm", "hmac-sha256")),
    )


@register("evidence-release-gate")
def handle(request: Mapping[str, Any]) -> Mapping[str, Any]:
    """Registry entry point.

    A rejected or blocked release is *not* reported as a successful skill run
    with a sad payload: it raises ``ACCEPTANCE_REJECTED`` / ``RELEASE_BLOCKED``
    carrying the full decision in ``details``, so no caller can read
    ``status == SUCCEEDED`` and conclude the release went out.
    """

    reject_unknown_fields(
        request,
        {"completion_claim", "acceptance_criteria", "validation_results", "artifacts",
         "approvals", "deployment_results"},
        field_name="evidence-release-gate request",
    )
    criteria = require_mapping(request.get("acceptance_criteria"), "acceptance_criteria")
    reject_unknown_fields(
        criteria,
        {"runId", "repoSnapshotSha", "decidedAt", "mandatoryGateIds", "policyDecision"},
        field_name="acceptance_criteria",
    )
    validation = require_mapping(request.get("validation_results"), "validation_results")
    reject_unknown_fields(validation, {"gateResults", "findings"},
                          field_name="validation_results")
    artifacts = require_mapping(request.get("artifacts"), "artifacts")
    reject_unknown_fields(artifacts, {"bundle"}, field_name="artifacts")
    approvals = require_mapping(request.get("approvals", {}), "approvals")
    reject_unknown_fields(approvals, {"waivers"}, field_name="approvals")
    deployment = require_mapping(request.get("deployment_results"), "deployment_results")
    reject_unknown_fields(deployment, {"health", "rollbackPlan"},
                          field_name="deployment_results")

    claim_payload = request.get("completion_claim")
    claim: CompletionClaim | None = None
    if claim_payload is not None:
        mapping = require_mapping(claim_payload, "completion_claim")
        reject_unknown_fields(
            mapping,
            {"claimant", "assertsComplete", "maxTurnsExhausted", "interrupted", "statement"},
            field_name="completion_claim",
        )
        claim = CompletionClaim(
            claimant=require_identifier(mapping.get("claimant"), "completion_claim.claimant"),
            asserts_complete=bool(mapping.get("assertsComplete", False)),
            max_turns_exhausted=bool(mapping.get("maxTurnsExhausted", False)),
            interrupted=bool(mapping.get("interrupted", False)),
            statement=str(mapping.get("statement", "")),
        )

    rollback_payload = deployment.get("rollbackPlan")
    rollback: RollbackPlan | None = None
    if rollback_payload is not None:
        mapping = require_mapping(rollback_payload, "rollbackPlan")
        reject_unknown_fields(mapping, {"planId", "complete", "steps", "evidenceId"},
                              field_name="rollbackPlan")
        rollback = RollbackPlan(
            plan_id=require_identifier(mapping.get("planId"), "rollbackPlan.planId"),
            complete=require_bool(mapping.get("complete"), "rollbackPlan.complete"),
            steps=require_str_seq(mapping.get("steps", ()), "rollbackPlan.steps"),
            evidence_id=str(mapping.get("evidenceId", "")),
        )

    inputs = ReleaseInputs(
        run_id=require_identifier(criteria.get("runId"), "acceptance_criteria.runId"),
        repo_snapshot_sha=require_str(criteria.get("repoSnapshotSha"),
                                      "acceptance_criteria.repoSnapshotSha", max_length=128),
        decided_at=parse_timestamp(criteria.get("decidedAt"), "acceptance_criteria.decidedAt"),
        policy=ReleasePolicy(
            mandatory_gate_ids=require_str_seq(criteria.get("mandatoryGateIds", ()),
                                               "acceptance_criteria.mandatoryGateIds",
                                               allow_empty=False),
        ),
        gate_results=tuple(
            _decode_gate(require_mapping(item, "gateResults[]"))
            for item in validation.get("gateResults", ())
        ),
        findings=tuple(
            _decode_finding(require_mapping(item, "findings[]"))
            for item in validation.get("findings", ())
        ),
        rollback_plan=rollback,
        health=_decode_health(require_mapping(deployment.get("health", {}), "health")),
        bundle=_decode_bundle(require_mapping(artifacts.get("bundle"), "artifacts.bundle")),
        policy_decision=(
            require_mapping(criteria["policyDecision"], "policyDecision")
            if criteria.get("policyDecision") is not None else None
        ),
        completion_claim=claim,
        waivers=tuple(
            _decode_waiver(require_mapping(item, "waivers[]"))
            for item in approvals.get("waivers", ())
        ),
    )

    decision = evaluate(inputs, seal_key=default_seal_key())
    payload = decision.to_payload()
    if decision.decision is not Decision.ACCEPTED:
        code = ("RELEASE_BLOCKED" if decision.decision is Decision.BLOCKED
                else "ACCEPTANCE_REJECTED")
        raise KernelError(
            code=code,
            message=(
                f"release {decision.decision} for run {decision.run_id}: "
                + "; ".join(sorted(set(decision.reason_codes())))
            ),
            retryable=False,
            evidence_ids=decision.justifying_evidence_ids,
            recommended_action="fix the reasons listed in details.acceptanceDecision and re-gate",
            details={"acceptanceDecision": payload, "decisionDigest": decision.digest},
        )

    verification = verify_bundle(inputs.bundle, key=default_seal_key())
    return {
        "acceptance_decision": payload,
        "gate_results": [gate.to_payload() for gate in decision.gate_results],
        "release_bundle": {
            "bundleId": verification.bundle_id,
            "repoSnapshotSha": verification.repo_snapshot_sha,
            "artifactDigests": list(verification.artifact_digests),
            "evidenceIds": list(decision.justifying_evidence_ids),
        },
        "rollback_bundle": (
            inputs.rollback_plan.to_payload() if inputs.rollback_plan is not None else None
        ),
        "deployment_complete_attestation": {
            "gate": "P05_DEPLOYMENT_COMPLETE",
            "attested": decision.deployment_complete,
            "decisionDigest": decision.digest,
            "decisionId": decision.decision_id,
            "waiversApplied": list(decision.waivers_applied),
        },
        "evidenceIds": list(decision.justifying_evidence_ids),
    }
