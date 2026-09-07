"""Environment-owned authority resolution.

The task payload never supplies an authority snapshot.  Callers must resolve
the snapshot from the durable environment registry before a tool can run.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import (
    AuthoritySnapshot,
    EffectivePolicy,
    PolicyDeniedError,
    ToolInvocation,
)


def effective_policy(snapshot: AuthoritySnapshot, upper_policy: Mapping[str, Any]) -> EffectivePolicy:
    upper_allowed = set(upper_policy.get("allowed", ()))
    upper_denied = set(upper_policy.get("denied", ()))
    if not upper_allowed:
        raise PolicyDeniedError("upper policy has no allowed capabilities")
    allowed = set(snapshot.allowed_capabilities) & upper_allowed
    denied = set(snapshot.denied_capabilities) | upper_denied
    return EffectivePolicy(frozenset(allowed - denied), frozenset(denied), dict(snapshot.sandbox_overrides), snapshot.snapshot_digest)


def resolve_tool_authority(
    invocation: ToolInvocation,
    environment: Mapping[str, Any] | None,
    snapshot: AuthoritySnapshot | None,
    upper_policy: Mapping[str, Any],
) -> EffectivePolicy:
    if environment is None:
        raise PolicyDeniedError("environment_not_found")
    if snapshot is None:
        raise PolicyDeniedError("authority_snapshot_unresolved")
    if snapshot.environment_id != invocation.environment_id:
        raise PolicyDeniedError("authority_environment_mismatch")
    owner_execution_id = environment.get("owner_execution_id")
    if owner_execution_id and owner_execution_id != environment.get("execution_id", owner_execution_id):
        raise PolicyDeniedError("environment_owner_binding_invalid")
    if environment.get("execution_id") and environment.get("execution_id") != invocation.task_id:
        raise PolicyDeniedError("environment_execution_mismatch")
    policy = effective_policy(snapshot, upper_policy)
    required = set(invocation.required_capabilities) | {invocation.capability}
    if not policy.permits(required):
        missing = sorted(required - policy.allowed_capabilities)
        raise PolicyDeniedError("capability_denied: " + ",".join(missing))
    return policy
