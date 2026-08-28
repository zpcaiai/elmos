"""Typed tool dispatch with durable idempotency and authority fencing."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from .models import EffectivePolicy, ExecutorIdentity, ToolInvocation, ToolResult
from .persistence import DurableStore
from .policy import resolve_tool_authority

ToolHandler = Callable[[ToolInvocation, EffectivePolicy], ToolResult]


@dataclass(frozen=True)
class RegisteredTool:
    capability: str
    required_capabilities: frozenset[str]
    handler: ToolHandler


class ToolRegistry:
    """Allowlisted tool registry; there is intentionally no generic shell tool."""

    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, capability: str, handler: ToolHandler, *, required_capabilities: set[str] | frozenset[str] | None = None) -> None:
        if not capability or capability in self._tools:
            raise ValueError("tool capability must be non-empty and unique")
        required = frozenset(required_capabilities or {capability})
        if not required or any(not item for item in required):
            raise ValueError("required capabilities must be non-empty")
        self._tools[capability] = RegisteredTool(capability, required, handler)

    def resolve(self, capability: str) -> RegisteredTool:
        try:
            return self._tools[capability]
        except KeyError as exc:
            raise KeyError(f"tool capability is not registered: {capability}") from exc

    def capabilities(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))


class ToolRuntime:
    def __init__(self, store: DurableStore, registry: ToolRegistry) -> None:
        self.store = store
        self.registry = registry

    def execute(
        self,
        tenant_id: str,
        invocation: ToolInvocation,
        executor: ExecutorIdentity,
        *,
        upper_policy: Mapping[str, object],
    ) -> ToolResult:
        tool = self.registry.resolve(invocation.capability)
        environment = self.store.get_environment(tenant_id, invocation.environment_id)
        snapshot = self.store.get_authority_snapshot(tenant_id, invocation.authority_snapshot_id)
        policy = resolve_tool_authority(invocation, environment, snapshot, upper_policy)
        if not policy.permits(tool.required_capabilities):
            missing = sorted(tool.required_capabilities - policy.allowed_capabilities)
            raise PermissionError("tool capability denied: " + ",".join(missing))

        begun = self.store.begin_tool_call(tenant_id, invocation, executor)
        if begun.get("replayed"):
            return begun["result"]
        self.store.mark_tool_executing(tenant_id, invocation.call_id, executor)
        try:
            result = tool.handler(invocation, policy)
            if not isinstance(result, ToolResult):
                raise TypeError("tool handlers must return ToolResult")
            if result.call_id != invocation.call_id:
                raise ValueError("tool handler returned a different call_id")
        except Exception as exc:  # noqa: BLE001 - tool failures become durable typed results
            result = ToolResult(
                call_id=invocation.call_id,
                items=(),
                status="failed",
                metadata={"error_type": type(exc).__name__, "error": str(exc)[:2000]},
            )
        return self.store.complete_tool_call(tenant_id, invocation.call_id, executor, result)
