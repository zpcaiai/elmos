"""Action/Observation protocol and the policy-enforcing Tool Gateway."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, cast

from .artifacts import ContentAddressedStore
from .errors import ContractViolation, IdempotencyConflict
from .firewall import ActionFirewall, FirewallContext
from .ledger import EventLedger
from .models import Action, ActionStatus, ArtifactRef, Identity, Observation
from .models import canonical_json
from .workspace import LocalWorkspaceProvider, WorkspaceLease


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    version: str
    capabilities: frozenset[str] = frozenset()
    mutating: bool = False
    idempotent: bool = False
    reconcileable: bool = False
    max_output_bytes: int = 1_048_576
    required_args: frozenset[str] = frozenset()
    allowed_operations: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not self.name or not self.version:
            raise ContractViolation("tool name and version are required")
        if self.max_output_bytes <= 0:
            raise ContractViolation("tool output limit must be positive")
        for field_name in ("capabilities", "required_args", "allowed_operations"):
            values = getattr(self, field_name)
            if any(not isinstance(value, str) or not value for value in values):
                raise ContractViolation(f"tool.{field_name} must contain non-empty strings")


@dataclass(frozen=True, slots=True)
class ToolResult:
    status: ActionStatus
    result: Any = None
    stdout: str = ""
    stderr: str = ""
    changed_resources: tuple[str, ...] = ()
    metrics: Mapping[str, Any] = field(default_factory=dict)
    error: Mapping[str, Any] | None = None
    reconciliation_hint: str | None = None


class ToolExecutor(Protocol):
    def execute(self, action: Action, *, timeout_seconds: float) -> ToolResult: ...

    def reconcile(self, action: Action) -> ToolResult | None: ...


class CancellationToken:
    """Cooperative cancellation signal shared across gateway and executors."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._reason = "cancelled"

    def cancel(self, reason: str) -> None:
        if not reason.strip():
            raise ContractViolation("cancellation reason is required")
        self._reason = reason[:500]
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    @property
    def reason(self) -> str:
        return self._reason

    def wait(self, timeout: float | None = None) -> bool:
        return self._event.wait(timeout)


class ToolRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}
        self._executors: dict[str, ToolExecutor] = {}

    def register(self, spec: ToolSpec, executor: ToolExecutor) -> None:
        if spec.name in self._specs:
            raise ContractViolation(f"tool already registered: {spec.name}")
        if spec.name != getattr(executor, "name", spec.name) and hasattr(executor, "name"):
            raise ContractViolation("tool executor name does not match registry name")
        self._specs[spec.name] = spec
        self._executors[spec.name] = executor

    def spec(self, name: str) -> ToolSpec:
        if name not in self._specs:
            raise ContractViolation(f"unknown tool: {name}")
        return self._specs[name]

    def executor(self, name: str) -> ToolExecutor:
        self.spec(name)
        return self._executors[name]

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._specs))


class ToolGateway:
    """PEP that makes an action lifecycle durable and policy-gated."""

    def __init__(self, ledger: EventLedger, firewall: ActionFirewall, registry: ToolRegistry, artifacts: ContentAddressedStore) -> None:
        self.ledger = ledger
        self.firewall = firewall
        self.registry = registry
        self.artifacts = artifacts

    def execute(
        self,
        identity: Identity,
        action: Action,
        context: FirewallContext,
        *,
        approved_by: str | None = None,
        cancellation: CancellationToken | None = None,
    ) -> Observation:
        spec = self.registry.spec(action.tool)
        if set(action.required_capabilities) - set(spec.capabilities):
            raise ContractViolation("action asks for capabilities not declared by its tool")
        missing_args = spec.required_args - set(action.args)
        if missing_args:
            raise ContractViolation("tool action is missing required arguments: " + ",".join(sorted(missing_args)))
        operation = action.args.get("operation")
        if spec.allowed_operations and operation not in spec.allowed_operations:
            raise ContractViolation("tool operation is not declared by its registry contract")
        proposed = self.ledger.event_by_idempotency(identity.tenant_id, identity.run_id, "action:" + action.idempotency_key)
        replaying_unfinished_action = proposed is not None
        if proposed is not None and canonical_json(dict(proposed.payload)) != canonical_json(action.as_dict()):
            raise IdempotencyConflict("action idempotency key was reused for different content")
        previous = self.ledger.event_by_idempotency(identity.tenant_id, identity.run_id, "observation:" + action.idempotency_key)
        if previous is not None:
            return _observation_from_payload(previous.payload)
        if proposed is None:
            self.ledger.append(identity, "action.proposed", action.as_dict(), idempotency_key="action:" + action.idempotency_key)
        if cancellation is not None and cancellation.cancelled:
            observation = Observation(action.action_id, ActionStatus.CANCELLED, error={"code": "TOOL_CANCELLED", "reason": cancellation.reason})
            self._record_observation(identity, action, observation)
            return observation
        decision = self.firewall.decide(action, context, approved_by=approved_by).decision
        self.ledger.append(identity, "policy.decided", {"action_id": action.action_id, **decision.as_dict()}, idempotency_key="policy:" + action.idempotency_key, policy_decision=decision.as_dict())
        if decision.decision != "allow":
            observation = Observation(action.action_id, ActionStatus.BLOCKED, error={"code": "APPROVAL_REQUIRED" if decision.decision == "require_approval" else "POLICY_DENIED", "reasons": list(decision.reasons)})
            self._record_observation(identity, action, observation)
            return observation

        executor = self.registry.executor(action.tool)
        if spec.mutating and spec.reconcileable and not callable(getattr(executor, "reconcile", None)):
            raise ContractViolation("reconcileable tool does not implement reconciliation")
        if spec.mutating and not (spec.idempotent or spec.reconcileable):
            observation = Observation(action.action_id, ActionStatus.BLOCKED, error={"code": "MUTATION_RECONCILIATION_REQUIRED"})
            self._record_observation(identity, action, observation)
            return observation
        try:
            reconciled = executor.reconcile(action) if spec.mutating and replaying_unfinished_action else None
            if reconciled is not None:
                result = reconciled
            elif cancellation is not None and callable(getattr(executor, "execute_cancellable", None)):
                result = cast(Any, executor).execute_cancellable(action, timeout_seconds=action.timeout_seconds, cancellation=cancellation)
            else:
                result = executor.execute(action, timeout_seconds=action.timeout_seconds)
        except TimeoutError:
            result = ToolResult(ActionStatus.TIMEOUT, error={"code": "TOOL_TIMEOUT"}, reconciliation_hint="reconcile before retry")
        except Exception as error:  # executor failure is an observation, not a gateway crash
            result = ToolResult(ActionStatus.FAILURE, error={"code": "TOOL_EXECUTION_FAILED", "message": str(error)[:500]}, reconciliation_hint="inspect executor state")
        if cancellation is not None and cancellation.cancelled and result.status == ActionStatus.SUCCESS:
            result = ToolResult(ActionStatus.CANCELLED, result=result.result, stdout=result.stdout, stderr=result.stderr, changed_resources=result.changed_resources, metrics=result.metrics, error={"code": "TOOL_CANCELLED", "reason": cancellation.reason}, reconciliation_hint=result.reconciliation_hint or "reconcile mutations before retry")
        observation = self._to_observation(action, spec, result, identity.tenant_id, context.secret_values)
        self._record_observation(identity, action, observation)
        return observation

    def _to_observation(self, action: Action, spec: ToolSpec, result: ToolResult, tenant_id: str, secrets: tuple[str, ...]) -> Observation:
        artifacts: list[ArtifactRef] = []
        stdout = redact(result.stdout, secrets)
        stderr = redact(result.stderr, secrets)
        if len(stdout.encode()) > spec.max_output_bytes:
            ref = self.artifacts.put(tenant_id, stdout.encode(), kind="tool-stdout", media_type="text/plain")
            artifacts.append(ref)
            stdout = _truncate_utf8(stdout, spec.max_output_bytes)
        if len(stderr.encode()) > spec.max_output_bytes:
            ref = self.artifacts.put(tenant_id, stderr.encode(), kind="tool-stderr", media_type="text/plain")
            artifacts.append(ref)
            stderr = _truncate_utf8(stderr, spec.max_output_bytes)
        value = result.result
        if stdout or stderr:
            value = {"result": value, "stdout": stdout, "stderr": stderr}
        return Observation(action.action_id, result.status, value, tuple(artifacts), dict(result.metrics), result.error, result.changed_resources, result.reconciliation_hint)

    def _record_observation(self, identity: Identity, action: Action, observation: Observation) -> None:
        payload = {
            "action_id": observation.action_id,
            "status": observation.status.value,
            "result": observation.result,
            "artifacts": [ref.as_dict() for ref in observation.artifacts],
            "metrics": dict(observation.metrics),
            "error": observation.error,
            "changed_resources": list(observation.changed_resources),
            "reconciliation_hint": observation.reconciliation_hint,
        }
        self.ledger.append(identity, "tool.observed", payload, idempotency_key="observation:" + action.idempotency_key, artifact_refs=observation.artifacts)


def _observation_from_payload(payload: Mapping[str, Any]) -> Observation:
    return Observation(
        str(payload["action_id"]),
        ActionStatus(str(payload["status"])),
        payload.get("result"),
        tuple(ArtifactRef(**ref) for ref in payload.get("artifacts", [])),
        payload.get("metrics", {}),
        payload.get("error"),
        tuple(payload.get("changed_resources", [])),
        payload.get("reconciliation_hint"),
    )


def redact(value: str, secrets: tuple[str, ...]) -> str:
    for secret in secrets:
        if secret:
            value = value.replace(secret, "[REDACTED]")
    return value


def _truncate_utf8(value: str, limit: int) -> str:
    suffix = "\n[TRUNCATED; full output in artifact]"
    suffix_bytes = len(suffix.encode("utf-8"))
    if limit <= suffix_bytes:
        return suffix.encode("utf-8")[:limit].decode("utf-8", errors="ignore")
    prefix = value.encode("utf-8")[: limit - suffix_bytes].decode("utf-8", errors="ignore")
    return prefix + suffix


class LocalWorkspaceToolExecutor:
    """Built-in filesystem and shell tools bound to one workspace lease."""

    def __init__(self, provider: LocalWorkspaceProvider, lease: WorkspaceLease, *, name: str = "workspace") -> None:
        self.provider = provider
        self.lease = lease
        self.name = name

    def execute(self, action: Action, *, timeout_seconds: float) -> ToolResult:
        operation = str(action.args.get("operation", ""))
        if operation == "read":
            path = self._path(str(action.args.get("path", "")))
            return ToolResult(ActionStatus.SUCCESS, path.read_text(encoding="utf-8"))
        if operation == "write":
            path = self._path(str(action.args.get("path", "")))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(action.args.get("content", "")), encoding="utf-8")
            return ToolResult(ActionStatus.SUCCESS, {"path": str(path.relative_to(self.lease.root))}, changed_resources=(str(path),))
        if operation == "shell":
            command = action.args.get("command")
            if not isinstance(command, list) or not command or not all(isinstance(item, str) for item in command):
                raise ContractViolation("local shell requires argv list")
            completed = self.provider.execute(self.lease, command, timeout_seconds=timeout_seconds)
            status = ActionStatus.SUCCESS if completed.returncode == 0 else ActionStatus.FAILURE
            return ToolResult(status, {"exit_code": completed.returncode}, completed.stdout, completed.stderr, metrics={"exit_code": completed.returncode})
        raise ContractViolation("unsupported workspace operation")

    def reconcile(self, action: Action) -> ToolResult | None:
        operation = str(action.args.get("operation", ""))
        if operation == "write":
            path = self._path(str(action.args.get("path", "")))
            if not path.exists():
                return None
            if not path.is_file() or path.is_symlink():
                return ToolResult(ActionStatus.FAILURE, error={"code": "WORKSPACE_RECONCILIATION_CONFLICT"}, reconciliation_hint="target is not a regular file")
            expected = str(action.args.get("content", ""))
            if path.read_text(encoding="utf-8") == expected:
                return ToolResult(ActionStatus.SUCCESS, {"path": str(path.relative_to(self.lease.root)), "reconciled": True}, changed_resources=(str(path),))
            return ToolResult(ActionStatus.FAILURE, error={"code": "WORKSPACE_RECONCILIATION_CONFLICT"}, reconciliation_hint="target content differs; do not overwrite without a new approved action")
        if operation == "shell":
            return ToolResult(ActionStatus.FAILURE, error={"code": "SIDE_EFFECT_STATE_UNKNOWN"}, reconciliation_hint="inspect sandbox/process state before issuing a new action")
        return None

    def _path(self, relative: str) -> Path:
        if not relative or relative.startswith("/") or ".." in relative.split("/"):
            raise ContractViolation("workspace tool path must be relative")
        root = Path(self.lease.root) / relative
        resolved = root.resolve()
        if not resolved.is_relative_to(Path(self.lease.root).resolve()):
            raise ContractViolation("workspace tool path escapes root")
        return resolved
