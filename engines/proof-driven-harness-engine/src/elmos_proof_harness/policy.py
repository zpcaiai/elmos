"""Deterministic fail-closed policy evaluation.

This is a small local Policy Enforcement Point, not a replacement for an
externally governed policy service.  Rules are declarative and exact.  Deny
always wins, review never becomes allow without a bound approval, and a policy
error or an unmatched request is denied.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Iterable, Protocol

from .canonical import digest_object, require_sha256_digest
from .contracts import SecurityContext
from .errors import AuthorizationError, ValidationError


class PolicyDecision(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REVIEW = "REVIEW"


@dataclass(frozen=True, slots=True)
class PolicyRequest:
    context: SecurityContext
    capability: str
    tool: str
    operation: str
    path: str | None = None
    network_host: str | None = None
    side_effect: bool = False


@dataclass(frozen=True, slots=True)
class PolicyRule:
    rule_id: str
    decision: PolicyDecision
    capabilities: frozenset[str]
    tools: frozenset[str]
    operations: frozenset[str]
    tenants: frozenset[str] = frozenset()
    projects: frozenset[str] = frozenset()
    actors: frozenset[str] = frozenset()
    allow_side_effects: bool = False
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.rule_id or not self.capabilities or not self.tools or not self.operations:
            raise ValidationError("policy rule identity and selectors are required")
        if self.decision is PolicyDecision.ALLOW and not self.reason:
            raise ValidationError("allow rule requires an auditable reason")

    def matches(self, request: PolicyRequest) -> bool:
        context = request.context
        return (
            request.capability in self.capabilities
            and request.tool in self.tools
            and request.operation in self.operations
            and (not self.tenants or context.tenant_id in self.tenants)
            and (not self.projects or context.project_id in self.projects)
            and (not self.actors or context.actor_id in self.actors)
            # Side-effect permission narrows only ALLOW rules.  A DENY or
            # REVIEW selector must continue to match side-effecting requests;
            # otherwise a default-false flag could silently bypass deny-wins.
            and (
                self.decision is not PolicyDecision.ALLOW
                or not request.side_effect
                or self.allow_side_effects
            )
        )


@dataclass(frozen=True, slots=True)
class PolicyApproval:
    approval_id: str
    tenant_id: str
    project_id: str
    actor_id: str
    request_digest: str
    approver_id: str
    receipt_id: str
    receipt_sha256: str
    issued_at: datetime
    expires_at: datetime
    policy_revision: str

    def __post_init__(self) -> None:
        require_sha256_digest(self.request_digest, field="request_digest")
        require_sha256_digest(self.policy_revision, field="policy_revision")
        require_sha256_digest(self.receipt_sha256, field="receipt_sha256")
        if not all(
            (
                self.approval_id,
                self.tenant_id,
                self.project_id,
                self.actor_id,
                self.approver_id,
                self.receipt_id,
            )
        ):
            raise ValidationError("approval bindings are incomplete")
        if (
            self.issued_at.tzinfo is None
            or self.issued_at.utcoffset() is None
            or self.expires_at.tzinfo is None
            or self.expires_at.utcoffset() is None
            or self.issued_at >= self.expires_at
        ):
            raise ValidationError("approval validity must be timezone-aware and increasing", code="INVALID_TIMESTAMP")


class ApprovalVerifier(Protocol):
    """Trusted durable receipt/revocation adapter injected at startup."""

    external: bool
    durable: bool

    def verify(
        self,
        approval: PolicyApproval,
        *,
        request_digest: str,
        policy_revision: str,
        now: datetime,
    ) -> bool: ...


@dataclass(frozen=True, slots=True)
class PolicyEvaluation:
    decision: PolicyDecision
    policy_revision: str
    matched_rule_ids: tuple[str, ...]
    reason: str


class PolicyEngine:
    """Evaluate exact rules; default and any internal failure are DENY."""

    def __init__(
        self,
        rules: Iterable[PolicyRule],
        *,
        revision: str | None = None,
        approval_verifier: ApprovalVerifier | None = None,
        allow_local_self_attested_approvals: bool = False,
    ) -> None:
        self._rules = tuple(rules)
        ids = [rule.rule_id for rule in self._rules]
        if len(ids) != len(set(ids)):
            raise ValidationError("policy rule ids must be unique")
        calculated = digest_object(self._rules, domain="policy-bundle")
        if revision is not None and revision != calculated:
            raise ValidationError("policy revision does not match rules", code="POLICY_REVISION_MISMATCH")
        self.revision = calculated
        if approval_verifier is not None and (
            not getattr(approval_verifier, "external", False)
            or not getattr(approval_verifier, "durable", False)
        ):
            raise ValidationError("approval verifier must be external and durable")
        self._approval_verifier = approval_verifier
        self._allow_local_self_attested_approvals = allow_local_self_attested_approvals

    @staticmethod
    def request_digest(request: PolicyRequest) -> str:
        return digest_object(request, domain="policy-request")

    def evaluate(self, request: PolicyRequest, *, now: datetime, approval: PolicyApproval | None = None) -> PolicyEvaluation:
        if now.tzinfo is None or now.utcoffset() is None:
            return PolicyEvaluation(PolicyDecision.DENY, self.revision, (), "evaluation time is not timezone-aware")
        try:
            matched = tuple(rule for rule in self._rules if rule.matches(request))
        except Exception as exc:  # fail closed across a policy boundary
            return PolicyEvaluation(PolicyDecision.DENY, self.revision, (), f"policy evaluation failed: {type(exc).__name__}")
        if not matched:
            return PolicyEvaluation(PolicyDecision.DENY, self.revision, (), "no policy rule matched")
        if any(rule.decision is PolicyDecision.DENY for rule in matched):
            denied = tuple(rule.rule_id for rule in matched if rule.decision is PolicyDecision.DENY)
            return PolicyEvaluation(PolicyDecision.DENY, self.revision, denied, "explicit deny")
        reviews = tuple(rule for rule in matched if rule.decision is PolicyDecision.REVIEW)
        if reviews:
            if not self._valid_approval(request, approval, now):
                return PolicyEvaluation(PolicyDecision.REVIEW, self.revision, tuple(rule.rule_id for rule in reviews), "approval required")
        allows = tuple(rule for rule in matched if rule.decision is PolicyDecision.ALLOW)
        if not allows and not reviews:
            return PolicyEvaluation(PolicyDecision.DENY, self.revision, (), "no allow decision")
        return PolicyEvaluation(PolicyDecision.ALLOW, self.revision, tuple(rule.rule_id for rule in matched), "authorized")

    def require_allow(self, request: PolicyRequest, *, now: datetime, approval: PolicyApproval | None = None) -> PolicyEvaluation:
        evaluation = self.evaluate(request, now=now, approval=approval)
        if evaluation.decision is not PolicyDecision.ALLOW:
            raise AuthorizationError(
                "policy did not allow request",
                code="POLICY_REVIEW_REQUIRED" if evaluation.decision is PolicyDecision.REVIEW else "POLICY_DENIED",
                details={"decision": evaluation.decision.value, "reason": evaluation.reason},
            )
        return evaluation

    def _valid_approval(self, request: PolicyRequest, approval: PolicyApproval | None, now: datetime) -> bool:
        if approval is None or now >= approval.expires_at:
            return False
        context = request.context
        bindings_valid = (
            approval.tenant_id == context.tenant_id
            and approval.project_id == context.project_id
            and approval.actor_id == context.actor_id
            and approval.policy_revision == self.revision
            and approval.request_digest == self.request_digest(request)
            and approval.approver_id != context.actor_id
        )
        if not bindings_valid or now < approval.issued_at:
            return False
        if self._approval_verifier is None:
            return self._allow_local_self_attested_approvals
        try:
            return self._approval_verifier.verify(
                approval,
                request_digest=self.request_digest(request),
                policy_revision=self.revision,
                now=now,
            ) is True
        except Exception:
            return False
