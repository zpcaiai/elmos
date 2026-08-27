"""High-level orchestration facade binding durable state to the typed kernel."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .environment import restore_environment, snapshot_environment
from .executor import ExecutorConnection, refresh
from .models import (
    AuthoritySnapshot,
    EnvironmentRef,
    ExecutorIdentity,
    ToolInvocation,
    ToolResult,
)
from .persistence import DurableStore
from .tool_runtime import ToolRegistry, ToolRuntime


@dataclass
class ExecutionRuntime:
    store: DurableStore
    tools: ToolRegistry

    def __post_init__(self) -> None:
        self.tool_runtime = ToolRuntime(self.store, self.tools)

    def bind_environment(self, tenant_id: str, execution_id: str, *, environment_type: str, config: Mapping[str, Any], authority_owner_id: str, permission_profile_version: str, allowed_capabilities: set[str], denied_capabilities: set[str] | None = None, sandbox_overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
        environment = self.store.create_environment(tenant_id, execution_id, environment_type, config=config, sandbox_overrides=sandbox_overrides)
        snapshot = AuthoritySnapshot(authority_owner_id, environment["environment_id"], permission_profile_version, frozenset(allowed_capabilities), frozenset(denied_capabilities or set()), sandbox_overrides or {})
        snapshot_id = uuid.uuid4()
        authority = self.store.create_authority_snapshot(tenant_id, str(snapshot_id), snapshot)
        return {"environment": environment, "authority": authority}

    def register_executor(self, tenant_id: str, environment_id: str, identity: ExecutorIdentity) -> dict[str, Any]:
        return self.store.register_executor(tenant_id, environment_id, identity)

    def executor_refresh(self, current: ExecutorConnection | None, registered: ExecutorIdentity, *, connection_healthy: bool) -> dict[str, Any]:
        return refresh(current, registered, connection_healthy=connection_healthy)

    def execute_tool(self, tenant_id: str, invocation: ToolInvocation, identity: ExecutorIdentity, *, upper_policy: Mapping[str, object]) -> ToolResult:
        return self.tool_runtime.execute(tenant_id, invocation, identity, upper_policy=upper_policy)

    @staticmethod
    def capture_environment(ref: EnvironmentRef, authority: AuthoritySnapshot, *, sandbox_overrides: Mapping[str, Any]) -> dict[str, Any]:
        return snapshot_environment(ref, authority, sandbox_overrides=sandbox_overrides)

    @staticmethod
    def resume_environment(snapshot: Mapping[str, Any], current: EnvironmentRef, *, current_sandbox_overrides: Mapping[str, Any]) -> dict[str, Any]:
        return restore_environment(snapshot, current, current_sandbox_overrides=current_sandbox_overrides)
