"""Session/environment resume helpers with non-widening policy semantics."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

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


def snapshot_environment(ref: EnvironmentRef, snapshot: AuthoritySnapshot, *, sandbox_overrides: Mapping[str, Any]) -> dict[str, Any]:
    if ref.environment_id != snapshot.environment_id:
        raise ValueError("environment and authority snapshot do not match")
    return {
        "environment_ref": ref.to_dict(),
        "authority_snapshot": snapshot.to_dict(),
        "authority_snapshot_digest": snapshot.snapshot_digest,
        "sandbox_overrides": dict(sandbox_overrides),
    }


def restore_environment(snapshot: Mapping[str, Any], current: EnvironmentRef, *, current_sandbox_overrides: Mapping[str, Any]) -> dict[str, Any]:
    raw_ref = snapshot.get("environment_ref")
    if not isinstance(raw_ref, Mapping) or raw_ref.get("environment_id") != current.environment_id:
        return {"restored": False, "reason": "environment_identity_changed"}
    saved_generation = int(raw_ref.get("generation", -1))
    if saved_generation > current.generation:
        return {"restored": False, "reason": "current_environment_generation_is_stale"}
    # Saved sandbox overrides are preserved, but a current explicit deny always wins.
    saved = dict(snapshot.get("sandbox_overrides", {}))
    merged = saved | dict(current_sandbox_overrides)
    return {
        "restored": True,
        "environment_ref": current.to_dict(),
        "sandbox_overrides": merged,
        "authority_snapshot_digest": snapshot.get("authority_snapshot_digest"),
    }
