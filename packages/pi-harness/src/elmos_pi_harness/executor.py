"""Executor replacement and late-message fencing."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .models import ExecutorIdentity, StaleGenerationError


@dataclass(frozen=True)
class ExecutorConnection:
    identity: ExecutorIdentity
    healthy: bool


def refresh(current: ExecutorConnection | None, registered: ExecutorIdentity, *, connection_healthy: bool) -> dict[str, Any]:
    if current is None:
        return {"action": "CONNECT_NEW", "next_generation": registered.generation}
    if current.identity == registered and connection_healthy:
        return {"action": "REUSE_CONNECTION", "next_generation": current.identity.generation}
    if current.identity == registered:
        return {"action": "RECONNECT_SAME_EXECUTOR", "next_generation": current.identity.generation}
    return {
        "action": "REPLACE_EXECUTOR",
        "retire_generation": current.identity.generation,
        "next_generation": registered.generation,
        "requires_live_status_probe": True,
    }


def accept_message(message: ExecutorIdentity, active: ExecutorIdentity) -> None:
    if message != active:
        raise StaleGenerationError("stale_executor_generation")


def fence_payload(payload: Mapping[str, Any], identity: ExecutorIdentity) -> dict[str, Any]:
    return dict(payload) | {"executor_id": identity.executor_id, "executor_generation": identity.generation}
