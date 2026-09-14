"""Session/environment resume helpers with non-widening policy semantics."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .canonical import digest
from .models import AuthoritySnapshot, EffectivePolicy, EnvironmentRef
from .policy import effective_policy


def build_turn_policy(
    snapshot: AuthoritySnapshot,
    *,
    tenant_policy: Mapping[str, Any],
    harness_policy: Mapping[str, Any],
) -> EffectivePolicy:
    """Intersect the environment snapshot with both upper policy layers."""

    allowed = set(tenant_policy.get("allowed", ())) & set(harness_policy.get("allowed", ()))
    denied = set(tenant_policy.get("denied", ())) | set(harness_policy.get("denied", ()))
    return effective_policy(snapshot, {"allowed": sorted(allowed), "denied": sorted(denied)})


def _restrict_overrides(saved: Mapping[str, Any], current: Mapping[str, Any]) -> dict[str, Any]:
    """Intersect known restrictions; incomparable changes require a new binding."""
    merged = dict(saved)
    restrictive_values = {
        "network": frozenset({"deny", "disabled"}),
        "filesystem": frozenset({"readonly", "read-only"}),
    }
    for key, value in current.items():
        if key not in merged or merged[key] == value:
            merged[key] = value
            continue
        previous = merged[key]
        restrictions = restrictive_values.get(key, frozenset())
        if isinstance(previous, str) and previous in restrictions:
            continue
        if isinstance(value, str) and value in restrictions:
            merged[key] = value
            continue
        if isinstance(previous, Mapping) and isinstance(value, Mapping):
            merged[key] = _restrict_overrides(previous, value)
            continue
        raise ValueError("sandbox override change cannot be proven restrictive: " + str(key))
    return merged


def snapshot_environment(ref: EnvironmentRef, snapshot: AuthoritySnapshot, *, sandbox_overrides: Mapping[str, Any]) -> dict[str, Any]:
    if ref.environment_id != snapshot.environment_id:
        raise ValueError("environment and authority snapshot do not match")
    return {
        "environment_ref": ref.to_dict(),
        "authority_snapshot": snapshot.to_dict(),
        "authority_snapshot_digest": snapshot.snapshot_digest,
        "sandbox_overrides": _restrict_overrides(snapshot.sandbox_overrides, sandbox_overrides),
    }


def restore_environment(snapshot: Mapping[str, Any], current: EnvironmentRef, *, current_sandbox_overrides: Mapping[str, Any]) -> dict[str, Any]:
    raw_ref = snapshot.get("environment_ref")
    if not isinstance(raw_ref, Mapping) or raw_ref.get("environment_id") != current.environment_id:
        return {"restored": False, "reason": "environment_identity_changed"}
    if raw_ref.get("owner_execution_id") != current.owner_execution_id:
        return {"restored": False, "reason": "environment_owner_changed"}
    if raw_ref.get("environment_type") != current.environment_type:
        return {"restored": False, "reason": "environment_type_changed"}
    saved_generation = raw_ref.get("generation")
    if type(saved_generation) is not int or saved_generation < 0:
        return {"restored": False, "reason": "invalid_environment_generation"}
    if saved_generation > current.generation:
        return {"restored": False, "reason": "current_environment_generation_is_stale"}
    authority = snapshot.get("authority_snapshot")
    if not isinstance(authority, Mapping) or authority.get("environment_id") != current.environment_id:
        return {"restored": False, "reason": "authority_environment_mismatch"}
    try:
        if digest(dict(authority)) != snapshot.get("authority_snapshot_digest"):
            return {"restored": False, "reason": "authority_snapshot_digest_mismatch"}
        saved = snapshot.get("sandbox_overrides")
        authority_overrides = authority.get("sandbox_overrides")
        if not isinstance(saved, Mapping) or not isinstance(authority_overrides, Mapping) or not isinstance(current_sandbox_overrides, Mapping):
            return {"restored": False, "reason": "invalid_sandbox_overrides"}
        merged = _restrict_overrides(_restrict_overrides(authority_overrides, saved), current_sandbox_overrides)
    except (TypeError, ValueError):
        return {"restored": False, "reason": "sandbox_or_authority_snapshot_invalid"}
    return {
        "restored": True,
        "environment_ref": current.to_dict(),
        "sandbox_overrides": merged,
        "authority_snapshot_digest": snapshot.get("authority_snapshot_digest"),
    }
