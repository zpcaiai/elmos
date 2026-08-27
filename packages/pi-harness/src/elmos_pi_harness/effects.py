"""Approval policy and durable effect-journal decisions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def requires_approval(action_kind: str, policy: Mapping[str, Any]) -> bool:
    actions = policy.get("actions", {})
    if isinstance(actions, Mapping) and action_kind in actions:
        return bool(actions[action_kind])
    return bool(policy.get("default_require_approval", True))


def prepare_effect(effect_id: str, action_kind: str, *, parent_call_id: str | None, metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if not effect_id or not action_kind:
        raise ValueError("effect_id and action_kind are required")
    return {"effect_id": effect_id, "action_kind": action_kind, "parent_call_id": parent_call_id, "status": "PENDING", "metadata": dict(metadata or {})}
