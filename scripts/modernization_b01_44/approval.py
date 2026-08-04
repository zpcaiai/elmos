#!/usr/bin/env python3
"""Human approval for irreversible actions.

An approval is bound to the exact request it approved.  Change the request and
the approval stops applying - it is not re-interpreted, it simply no longer
matches.  Critical actions require dual control by two distinct humans.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable

from scripts.modernization_b01_44.canonical import digest, format_instant, parse_instant
from scripts.modernization_b01_44.errors import ApprovalRequired, PolicyViolation
from scripts.modernization_b01_44.policy import Principal

DEFAULT_APPROVAL_TTL = timedelta(hours=24)


@dataclass(frozen=True)
class Approval:
    approval_id: str
    request_digest: str
    approver_id: str
    approver_kind: str
    granted_at: str
    expires_at: str
    action: str
    criticality: str

    def is_expired(self, now: datetime) -> bool:
        return parse_instant(self.expires_at, "expires_at") <= now

    def as_dict(self) -> dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "request_digest": self.request_digest,
            "approver_id": self.approver_id,
            "approver_kind": self.approver_kind,
            "granted_at": self.granted_at,
            "expires_at": self.expires_at,
            "action": self.action,
            "criticality": self.criticality,
        }


class ApprovalLedger:
    """Grant, look up and enforce approvals."""

    def __init__(self, *, approvals_expire: bool = True, ttl: timedelta = DEFAULT_APPROVAL_TTL) -> None:
        self.approvals_expire = approvals_expire
        self.ttl = ttl
        self._approvals: dict[str, Approval] = {}

    def grant(
        self,
        *,
        request: Any,
        approver: Principal,
        action: str,
        now: datetime,
        criticality: str = "normal",
    ) -> Approval:
        if approver.is_agent:
            raise PolicyViolation(
                "an agent may not grant human approval", approver_id=approver.principal_id
            )
        request_digest = digest(request)
        expires = now + self.ttl if self.approvals_expire else now + timedelta(days=3650)
        approval = Approval(
            approval_id="apr-" + digest({"r": request_digest, "a": approver.principal_id, "t": format_instant(now)})[:24],
            request_digest=request_digest,
            approver_id=approver.principal_id,
            approver_kind=approver.kind,
            granted_at=format_instant(now),
            expires_at=format_instant(expires),
            action=action,
            criticality=criticality,
        )
        self._approvals[approval.approval_id] = approval
        return approval

    def get(self, approval_id: str) -> Approval:
        try:
            return self._approvals[approval_id]
        except KeyError:
            raise ApprovalRequired("approval not found", approval_id=approval_id) from None

    def require(
        self,
        *,
        request: Any,
        approval_ids: Iterable[str],
        action: str,
        now: datetime,
        criticality: str = "normal",
    ) -> list[Approval]:
        """Verify approvals cover *this* request, unexpired, dual-controlled."""

        request_digest = digest(request)
        needed = 2 if criticality == "critical" else 1
        matching: list[Approval] = []
        approvers: set[str] = set()
        for approval_id in approval_ids:
            approval = self.get(approval_id)
            if approval.action != action:
                continue
            if approval.request_digest != request_digest:
                raise ApprovalRequired(
                    "approval does not cover this request; the input changed after approval",
                    approval_id=approval_id,
                    approved_digest=approval.request_digest,
                    request_digest=request_digest,
                )
            if approval.is_expired(now):
                raise ApprovalRequired(
                    "approval has expired", approval_id=approval_id, expires_at=approval.expires_at
                )
            if approval.approver_id in approvers:
                continue
            approvers.add(approval.approver_id)
            matching.append(approval)
        if len(matching) < needed:
            raise ApprovalRequired(
                "insufficient human approval for an irreversible action",
                action=action,
                criticality=criticality,
                required_distinct_approvers=needed,
                present=len(matching),
            )
        return matching
