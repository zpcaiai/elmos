from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

@dataclass(frozen=True)
class Approval:
    action_digest: str
    approver_id: str
    role: str
    status: str
    expires_at: datetime


def authorize_action(*, action_digest: str, approvals: Iterable[Approval], allowed_roles: set[str], required_distinct: int, now: datetime | None=None) -> str:
    now=now or datetime.now(timezone.utc)
    valid={a.approver_id for a in approvals if a.action_digest==action_digest and a.role in allowed_roles and a.status=="approved" and a.expires_at>now}
    if len(valid) < required_distinct:
        return "DENY"
    return "ALLOW"
