"""Authority, policy, typed-tool and sandbox primitives.

No prompt, model name or adapter identity is an authority source. All writes
must carry an environment/workspace-owned snapshot and the current fencing
token. The default tool runtime is inert until a caller registers an explicit
adapter.
"""

from __future__ import annotations

import re
import threading
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .errors import AuthorizationError, ContractError, ErrorInfo
from .models import Status, digest, require_bool, require_mapping, require_string, utc_now
from .storage import DurableStore


class Decision(str):
    DENY = "DENY"
    ASK_USER = "ASK_USER"
    REQUIRE_ESCALATION = "REQUIRE_ESCALATION"
    REQUIRE_SECOND_REVIEW = "REQUIRE_SECOND_REVIEW"
    MODIFY_INPUT = "MODIFY_INPUT"
    ALLOW = "ALLOW"


_DECISION_ORDER = {
    Decision.DENY: 0,
    Decision.ASK_USER: 1,
    Decision.REQUIRE_ESCALATION: 2,
    Decision.REQUIRE_SECOND_REVIEW: 3,
    Decision.MODIFY_INPUT: 4,
    Decision.ALLOW: 5,
}


def aggregate_decisions(decisions: list[str]) -> str:
    if not decisions:
        return Decision.DENY
    unknown = [value for value in decisions if value not in _DECISION_ORDER]
    if unknown:
        return Decision.DENY
    return min(decisions, key=lambda value: _DECISION_ORDER[value])


@dataclass(frozen=True, slots=True)
class ExecutionAuthority:
    environment_id: str
    workspace_id: str
    permission_profile_id: str
    policy_snapshot_hash: str
    fencing_token: int
    allowed_tools: frozenset[str]
    workspace_root: str | None = None
    network_scopes: frozenset[str] = frozenset()
    secret_scopes: frozenset[str] = frozenset()
    source: str = "execution-environment"

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ExecutionAuthority:
        if "environment" in payload or "workspace" in payload or "permission_profile" in payload:
            environment = require_mapping(payload.get("environment"), "environment")
            workspace = require_mapping(payload.get("workspace"), "workspace")
            profile = require_mapping(payload.get("permission_profile"), "permission_profile")
        else:
            # Accept the immutable snapshot emitted by ``snapshot()`` as a
            # composable input, while still requiring every authority field.
            environment = {"id": payload.get("environment_id")}
            workspace = {"id": payload.get("workspace_id"), "root": payload.get("workspace_root")}
            profile = {
                "id": payload.get("permission_profile_id"),
                "policy_snapshot_hash": payload.get("policy_snapshot_hash"),
                "allowed_tools": payload.get("allowed_tools", []),
                "network_scopes": payload.get("network_scopes", []),
                "secret_scopes": payload.get("secret_scopes", []),
                "authority_source": payload.get("authority_source", "execution-environment"),
            }
        token_value = payload.get("fencing_token")
        if isinstance(token_value, Mapping):
            token_value = token_value.get("value")
        if isinstance(token_value, bool) or not isinstance(token_value, int) or token_value < 1:
            raise ContractError("FENCING_REJECTED", "fencing_token must be a positive integer")
        source = str(profile.get("authority_source", "execution-environment"))
        if source.casefold() == "conversation":
            raise AuthorizationError("AUTHORITY_DENIED", "conversation is not an authority source")
        tools = profile.get("allowed_tools", [])
        network = profile.get("network_scopes", [])
        secrets = profile.get("secret_scopes", [])
        if not all(isinstance(item, list) for item in (tools, network, secrets)):
            raise ContractError("INVALID_INPUT", "permission profile scopes must be arrays")
        return cls(
            environment_id=require_string(environment.get("id"), "environment.id"),
            workspace_id=require_string(workspace.get("id"), "workspace.id"),
            permission_profile_id=require_string(profile.get("id"), "permission_profile.id"),
            policy_snapshot_hash=require_string(profile.get("policy_snapshot_hash"), "permission_profile.policy_snapshot_hash"),
            fencing_token=token_value,
            allowed_tools=frozenset(require_string(item, "allowed_tools[]") for item in tools),
            workspace_root=workspace.get("root"),
            network_scopes=frozenset(require_string(item, "network_scopes[]") for item in network),
            secret_scopes=frozenset(require_string(item, "secret_scopes[]") for item in secrets),
            source=source,
        )

    def authorize(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if request.get("authority_source") == "conversation" or self.source == "conversation":
            raise AuthorizationError("AUTHORITY_DENIED", "thread-global authority is forbidden")
        if request.get("environment_id") != self.environment_id or request.get("workspace_id") != self.workspace_id:
            raise AuthorizationError("AUTHORITY_DENIED", "environment/workspace scope mismatch")
        if request.get("fencing_token") != self.fencing_token:
            raise AuthorizationError("FENCING_REJECTED", "fencing token is stale")
        tool_id = require_string(request.get("tool_id"), "tool_request.tool_id")
        if tool_id not in self.allowed_tools:
            raise AuthorizationError("AUTHORITY_DENIED", f"tool is not in the allowlist: {tool_id}")
        requested_network_value = request.get("network_scopes", [])
        requested_secrets_value = request.get("secret_scopes", [])
        if not isinstance(requested_network_value, list) or not isinstance(requested_secrets_value, list):
            raise ContractError("SCHEMA_MISMATCH", "requested scopes must be arrays")
        requested_network = set(requested_network_value)
        if not requested_network.issubset(self.network_scopes):
            raise AuthorizationError("SCOPE_ESCALATION_ATTEMPT", "requested network scope exceeds authority")
        requested_secrets = set(requested_secrets_value)
        if not requested_secrets.issubset(self.secret_scopes):
            raise AuthorizationError("SCOPE_ESCALATION_ATTEMPT", "requested secret scope exceeds authority")
        return {"decision": Decision.ALLOW, "tool_id": tool_id, "environment_id": self.environment_id, "workspace_id": self.workspace_id, "fencing_token": self.fencing_token, "policy_snapshot_hash": self.policy_snapshot_hash}

    def snapshot(self) -> dict[str, Any]:
        return {
            "environment_id": self.environment_id,
            "workspace_id": self.workspace_id,
            "permission_profile_id": self.permission_profile_id,
            "policy_snapshot_hash": self.policy_snapshot_hash,
            "fencing_token": self.fencing_token,
            "allowed_tools": sorted(self.allowed_tools),
            "network_scopes": sorted(self.network_scopes),
            "secret_scopes": sorted(self.secret_scopes),
            "authority_source": self.source,
            "digest": digest({"environment_id": self.environment_id, "workspace_id": self.workspace_id, "permission_profile_id": self.permission_profile_id, "policy_snapshot_hash": self.policy_snapshot_hash, "fencing_token": self.fencing_token, "allowed_tools": sorted(self.allowed_tools), "network_scopes": sorted(self.network_scopes), "secret_scopes": sorted(self.secret_scopes)}),
        }


class PolicyEngine:
    def evaluate(self, hook_event: Mapping[str, Any], policy_layers: list[Mapping[str, Any]], context: Mapping[str, Any]) -> dict[str, Any]:
        decisions: list[str] = []
        reasons: list[str] = []
        modifications: dict[str, Any] = {}
        policy_ids: list[str] = []
        for layer in policy_layers:
            policy_id = str(layer.get("id", "anonymous-policy"))
            policy_ids.append(policy_id)
            decision = str(layer.get("decision", Decision.DENY))
            decisions.append(decision)
            if layer.get("reason"):
                reasons.append(str(layer["reason"]))
            if decision == Decision.MODIFY_INPUT:
                changes = layer.get("modified_input", {})
                if not isinstance(changes, Mapping):
                    raise ContractError("POLICY_CONFLICT", "modified_input must be an object")
                modifications.update(changes)
        decision = aggregate_decisions(decisions)
        if decision == Decision.MODIFY_INPUT and not modifications:
            decision = Decision.DENY
            reasons.append("MODIFY_INPUT requires a non-empty modification")
        if not policy_layers:
            reasons.append("no policy layer supplied; default deny")
        return {"decision": decision, "policy_ids": policy_ids, "reasons": reasons, "modified_input": modifications, "policy_snapshot_hash": digest({"hook_event": hook_event, "policy_layers": policy_layers, "context": context}), "decided_at": utc_now()}


@dataclass(frozen=True, slots=True)
class ToolDescriptor:
    tool_id: str
    version: str
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any]
    side_effects: bool
    idempotency_required: bool
    allowed_operations: frozenset[str]

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ToolDescriptor:
        side_effects = require_bool(payload.get("side_effects", False), "tool_descriptor.side_effects")
        idem = require_bool(payload.get("idempotency_required", side_effects), "tool_descriptor.idempotency_required")
        operations = payload.get("allowed_operations", [])
        if not isinstance(operations, list):
            raise ContractError("SCHEMA_MISMATCH", "allowed_operations must be an array")
        return cls(require_string(payload.get("tool_id"), "tool_descriptor.tool_id"), require_string(payload.get("version"), "tool_descriptor.version"), require_mapping(payload.get("input_schema", {}), "tool_descriptor.input_schema"), require_mapping(payload.get("output_schema", {}), "tool_descriptor.output_schema"), side_effects, idem, frozenset(require_string(item, "allowed_operations[]") for item in operations))


ToolHandler = Callable[[Mapping[str, Any]], Any]


class ToolRuntime:
    """A typed ABI registry. It never shells out or calls a provider implicitly."""

    def __init__(self, store: DurableStore | None = None) -> None:
        self.store = store
        self._descriptors: dict[str, ToolDescriptor] = {}
        self._handlers: dict[str, ToolHandler] = {}
        self._idempotent: dict[tuple[str, str], dict[str, Any]] = {}
        self._lock = threading.RLock()

    @property
    def descriptors(self) -> tuple[ToolDescriptor, ...]:
        return tuple(self._descriptors.values())

    def register(self, descriptor: ToolDescriptor, handler: ToolHandler | None = None) -> None:
        with self._lock:
            if descriptor.tool_id in self._descriptors and self._descriptors[descriptor.tool_id].version != descriptor.version:
                raise ContractError("SCHEMA_MISMATCH", "tool version replacement is not allowed in-place")
            self._descriptors[descriptor.tool_id] = descriptor
            if handler is not None:
                self._handlers[descriptor.tool_id] = handler

    def invoke(self, request: Mapping[str, Any], authority: ExecutionAuthority, policy: Mapping[str, Any] | None = None) -> dict[str, Any]:
        tool_id = require_string(request.get("tool_id"), "tool_call_request.tool_id")
        descriptor = self._descriptors.get(tool_id)
        if descriptor is None:
            raise AuthorizationError("TOOL_DENIED", f"unknown tool: {tool_id}")
        auth = authority.authorize(request)
        if policy and str(policy.get("decision", Decision.DENY)) != Decision.ALLOW:
            raise AuthorizationError("TOOL_DENIED", "policy did not allow tool execution")
        args = require_mapping(request.get("input", {}), "tool_call_request.input")
        operation = str(request.get("operation", ""))
        if descriptor.allowed_operations and operation not in descriptor.allowed_operations:
            raise AuthorizationError("TOOL_DENIED", "operation is not allowed by tool descriptor")
        idempotency_key = request.get("idempotency_key")
        if descriptor.idempotency_required:
            idempotency_key = require_string(idempotency_key, "tool_call_request.idempotency_key")
        key = (tool_id, str(idempotency_key))
        tenant_id = str(request.get("tenant_id", "local"))
        if idempotency_key and self.store is not None:
            persisted = self.store.get_tool_call(tenant_id=tenant_id, tool_id=tool_id, idempotency_key=str(idempotency_key))
            if persisted and persisted.get("state") == "SUCCEEDED":
                return {"tool_call_id": persisted.get("tool_call_id"), "tool_id": tool_id, "tool_version": descriptor.version, "input_hash": persisted.get("input_hash"), "idempotency_key": idempotency_key, "state": persisted.get("state"), "typed_result": persisted.get("result"), "replayed": True}
        with self._lock:
            if idempotency_key and key in self._idempotent:
                return {**self._idempotent[key], "replayed": True}
        handler = self._handlers.get(tool_id)
        record = {"tool_call_id": str(uuid.uuid4()), "tool_id": tool_id, "tool_version": descriptor.version, "input_hash": digest(args), "idempotency_key": idempotency_key, "authorization": auth, "started_at": utc_now(), "state": "NOT_RUN", "replayed": False}
        if handler is None:
            record.update({"state": Status.NOT_RUN.value, "structured_error": ErrorInfo("REMOTE_TOOL_UNAVAILABLE", details={"message": "adapter not registered"}).to_dict(), "finished_at": utc_now()})
        else:
            try:
                value = handler(args)
                record.update({"state": Status.SUCCEEDED.value, "typed_result": value, "finished_at": utc_now()})
            except TimeoutError:
                record.update({"state": "TIMED_OUT", "structured_error": ErrorInfo("TOOL_TIMEOUT", retryable=True, details={"message": "tool handler timed out"}).to_dict(), "finished_at": utc_now()})
            except KeyboardInterrupt:
                record.update({"state": "INTERRUPTED", "structured_error": ErrorInfo("TOOL_INTERRUPTED", interrupted=True, details={"message": "tool handler interrupted"}).to_dict(), "finished_at": utc_now()})
            except Exception as exc:  # noqa: BLE001 - adapter failures are converted to a typed durable result
                record.update({"state": "FAILED", "structured_error": ErrorInfo("TOOL_FAILED", details={"message": "tool handler failed", "type": type(exc).__name__}).to_dict(), "finished_at": utc_now()})
        if idempotency_key and record["state"] == Status.SUCCEEDED.value:
            with self._lock:
                self._idempotent[key] = record
        if self.store is not None:
            persisted = self.store.record_tool_call(tenant_id=tenant_id, run_id=request.get("run_id"), step_id=str(request.get("step_id", "tool")), tool_id=tool_id, tool_version=descriptor.version, state=record["state"], input_hash=record["input_hash"], idempotency_key=str(idempotency_key) if idempotency_key else None, result=record.get("typed_result"), error=record.get("structured_error"))
            record["durable_record_id"] = persisted.get("tool_call_id")
        return record


def sandbox_plan(repository_snapshot: Mapping[str, Any], workspace_profile: Mapping[str, Any], network_policy: Mapping[str, Any], secret_binding_plan: Mapping[str, Any]) -> dict[str, Any]:
    phase = str(workspace_profile.get("phase", "ANALYZE")).upper()
    secret_scopes = list(secret_binding_plan.get("scopes", []))
    if phase == "ANALYZE" and secret_scopes:
        raise AuthorizationError("SECRET_EXPOSURE", "analysis phase cannot bind secrets")
    allowed_network = list(network_policy.get("allow", []))
    if not network_policy.get("deny_by_default", True):
        raise AuthorizationError("NETWORK_POLICY_BYPASS", "sandbox network policy must deny by default")
    execution_id = str(uuid.uuid4())
    analysis = {"sandbox_id": execution_id, "phase": "ANALYZE", "read_only": True, "network": {"default": "DENY", "allow": []}, "secrets": "NONE", "repository_snapshot_hash": digest(repository_snapshot)}
    scopes = sorted({str(item) for item in secret_scopes})
    execution = {"sandbox_id": str(uuid.uuid4()), "phase": "EXECUTE", "read_only": bool(workspace_profile.get("read_only", False)), "network": {"default": "DENY", "allow": allowed_network}, "secret_scopes": scopes}
    return {"analysis_environment": analysis, "execution_environment": execution, "secret_lease": None if not scopes else {"lease_id": str(uuid.uuid4()), "scopes": scopes, "ttl_seconds": int(secret_binding_plan.get("ttl_seconds", 300))}, "sandbox_attestation": {"status": "PLANNED", "policy_hash": digest({"network_policy": network_policy, "workspace_profile": workspace_profile}), "created_at": utc_now()}, "cleanup_report": {"status": "PENDING", "revocation_required": bool(scopes)}}


def redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if re.search(r"secret|token|password|private.?key|authorization", str(key), re.IGNORECASE):
                result[str(key)] = "[REDACTED]"
            else:
                result[str(key)] = redact(item)
        return result
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value
