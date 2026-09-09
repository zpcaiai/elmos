"""Concrete executable bridges for external coding agent harnesses and protocols."""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .models import (
    AuthoritySnapshot,
    ExecutorIdentity,
    PolicyDeniedError,
    StaleGenerationError,
    TextContent,
    ToolInvocation,
    ToolResult,
)
from .policy import effective_policy
from .tool_runtime import ToolRuntime


@dataclass(frozen=True)
class BridgeEvent:
    event_id: str
    bridge_type: str
    event_type: str
    payload: Mapping[str, Any]


class CodexHarnessBridge:
    """Bidirectional bridge for OpenAI Codex App Server JSON-RPC communication."""

    def __init__(
        self,
        tenant_id: str,
        task_id: str,
        environment_id: str,
        authority_snapshot_id: str,
        executor_identity: ExecutorIdentity,
        authority: AuthoritySnapshot,
        tool_runtime: ToolRuntime,
        *,
        upper_policy: Mapping[str, Any] | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.task_id = task_id
        self.environment_id = environment_id
        self.authority_snapshot_id = authority_snapshot_id
        self.executor_identity = executor_identity
        self.authority = authority
        self.tool_runtime = tool_runtime
        self.upper_policy = (
            dict(upper_policy)
            if upper_policy is not None
            else {"allowed": sorted(self.authority.allowed_capabilities)}
        )
        self.threads: dict[str, dict[str, Any]] = {}
        self.events: list[BridgeEvent] = []

    def handle_jsonrpc(self, request_json: str) -> str:
        """Handle a raw JSON-RPC request and return a JSON-RPC response."""
        try:
            req = json.loads(request_json)
        except Exception as err:
            return json.dumps({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {err}"},
            })

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        if not isinstance(method, str):
            return json.dumps({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32600, "message": "Invalid Request: missing method"},
            })

        try:
            result = self.dispatch(method, params)
            return json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result})
        except PolicyDeniedError as p_err:
            return json.dumps({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": 4003, "message": f"Policy denied: {p_err}"},
            })
        except StaleGenerationError as s_err:
            return json.dumps({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": 4009, "message": f"Stale generation: {s_err}"},
            })
        except Exception as exc:
            return json.dumps({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32603, "message": f"Internal error: {exc}"},
            })

    def dispatch(self, method: str, params: Mapping[str, Any]) -> dict[str, Any]:
        if method == "thread.create":
            thread_id = str(uuid.uuid4())
            metadata = dict(params.get("metadata", {}))
            self.threads[thread_id] = {"thread_id": thread_id, "status": "active", "metadata": metadata}
            self._emit("thread.created", {"thread_id": thread_id})
            return {"thread_id": thread_id, "status": "active"}

        elif method == "turn.start":
            thread_id = str(params.get("thread_id", ""))
            if thread_id not in self.threads:
                raise ValueError(f"thread not found: {thread_id}")
            turn_id = str(uuid.uuid4())
            prompt = str(params.get("prompt", ""))
            self._emit("turn.started", {"thread_id": thread_id, "turn_id": turn_id, "prompt": prompt})
            return {"turn_id": turn_id, "thread_id": thread_id, "status": "running"}

        elif method == "tool.execute":
            raw_call_id = params.get("call_id")
            try:
                call_id = str(uuid.UUID(str(raw_call_id)))
            except Exception:
                call_id = str(uuid.uuid4())

            capability = str(params.get("capability") or params.get("tool_name", ""))
            arguments = dict(params.get("arguments", {}))
            required_capabilities = set(params.get("required_capabilities", [capability]))

            # Pre-validate policy
            policy = effective_policy(self.authority, self.upper_policy)
            for cap in required_capabilities:
                if cap not in policy.allowed_capabilities:
                    raise PolicyDeniedError(f"capability '{cap}' denied by effective policy")

            invocation = ToolInvocation(
                call_id=call_id,
                task_id=self.task_id,
                environment_id=self.environment_id,
                authority_snapshot_id=self.authority_snapshot_id,
                capability=capability,
                args=arguments,
                idempotency_key=f"codex-{call_id}",
                timeout_ms=10_000,
                sandbox_profile="default",
                required_capabilities=frozenset(required_capabilities),
            )
            result = self.tool_runtime.execute(
                self.tenant_id,
                invocation,
                self.executor_identity,
                upper_policy=self.upper_policy,
            )
            self._emit("tool.executed", {"call_id": call_id, "status": result.status})
            return result.to_dict()

        elif method == "turn.cancel":
            turn_id = str(params.get("turn_id", ""))
            self._emit("turn.cancelled", {"turn_id": turn_id})
            return {"turn_id": turn_id, "status": "cancelled"}

        else:
            raise ValueError(f"Method not supported by Codex bridge: {method}")

    def _emit(self, event_type: str, payload: Mapping[str, Any]) -> None:
        self.events.append(
            BridgeEvent(
                event_id=str(uuid.uuid4()),
                bridge_type="codex",
                event_type=event_type,
                payload=dict(payload),
            )
        )


class ClaudeHarnessBridge:
    """Pre-tool / post-tool hook-based bridge for Claude Code and OpenCode."""

    def __init__(
        self,
        tenant_id: str,
        task_id: str,
        environment_id: str,
        authority_snapshot_id: str,
        executor_identity: ExecutorIdentity,
        authority: AuthoritySnapshot,
        tool_runtime: ToolRuntime,
        *,
        upper_policy: Mapping[str, Any] | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.task_id = task_id
        self.environment_id = environment_id
        self.authority_snapshot_id = authority_snapshot_id
        self.executor_identity = executor_identity
        self.authority = authority
        self.tool_runtime = tool_runtime
        self.upper_policy = (
            dict(upper_policy)
            if upper_policy is not None
            else {"allowed": sorted(self.authority.allowed_capabilities)}
        )
        self.audit_log: list[dict[str, Any]] = []

    def pre_tool_hook(self, capability: str, arguments: Mapping[str, Any], required_capabilities: Sequence[str]) -> dict[str, Any]:
        policy = effective_policy(self.authority, self.upper_policy)
        denied = [cap for cap in required_capabilities if cap not in policy.allowed_capabilities]
        if denied:
            return {"allowed": False, "denied_capabilities": denied, "reason": "denied by effective policy"}
        return {"allowed": True, "denied_capabilities": []}

    def execute_with_hooks(
        self,
        capability: str,
        arguments: Mapping[str, Any],
        required_capabilities: Sequence[str],
        call_id: str | None = None,
    ) -> ToolResult:
        try:
            cid = str(uuid.UUID(str(call_id)))
        except Exception:
            cid = str(uuid.uuid4())

        check = self.pre_tool_hook(capability, arguments, required_capabilities)
        if not check["allowed"]:
            res = ToolResult(
                call_id=cid,
                items=(TextContent(f"Policy denied capabilities: {check['denied_capabilities']}"),),
                status="failed",
                metadata={"reason": check["reason"], "denied_capabilities": check["denied_capabilities"], "policy_denied": True},
            )
            self.audit_log.append({"call_id": cid, "capability": capability, "status": "failed", "reason": check["reason"]})
            return res

        invocation = ToolInvocation(
            call_id=cid,
            task_id=self.task_id,
            environment_id=self.environment_id,
            authority_snapshot_id=self.authority_snapshot_id,
            capability=capability,
            args=dict(arguments),
            idempotency_key=f"claude-{cid}",
            timeout_ms=10_000,
            sandbox_profile="default",
            required_capabilities=frozenset(required_capabilities),
        )
        result = self.tool_runtime.execute(
            self.tenant_id,
            invocation,
            self.executor_identity,
            upper_policy=self.upper_policy,
        )
        self.audit_log.append({"call_id": cid, "capability": capability, "status": result.status})
        return result


class MCPHarnessBridge:
    """Model Context Protocol (MCP) JSON-RPC bridge exposing Elmos tools safely."""

    def __init__(
        self,
        tenant_id: str,
        task_id: str,
        environment_id: str,
        authority_snapshot_id: str,
        executor_identity: ExecutorIdentity,
        authority: AuthoritySnapshot,
        tool_runtime: ToolRuntime,
        *,
        server_name: str = "elmos-mcp-server",
        server_version: str = "1.0.0",
        upper_policy: Mapping[str, Any] | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.task_id = task_id
        self.environment_id = environment_id
        self.authority_snapshot_id = authority_snapshot_id
        self.executor_identity = executor_identity
        self.authority = authority
        self.tool_runtime = tool_runtime
        self.server_name = server_name
        self.server_version = server_version
        self.upper_policy = (
            dict(upper_policy)
            if upper_policy is not None
            else {"allowed": sorted(self.authority.allowed_capabilities)}
        )

    def handle_request(self, request_dict: Mapping[str, Any]) -> dict[str, Any]:
        req_id = request_dict.get("id")
        method = request_dict.get("method")
        params = request_dict.get("params", {})

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": self.server_name, "version": self.server_version},
                    "capabilities": {"tools": {"listChanged": False}, "resources": {}, "prompts": {}},
                },
            }

        elif method == "tools/list":
            tools_list = []
            for name in self.tool_runtime.registry.capabilities():
                tools_list.append({
                    "name": name,
                    "description": f"Elmos registered tool '{name}'",
                    "inputSchema": {
                        "type": "object",
                        "properties": {},
                    },
                })
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": tools_list},
            }

        elif method == "tools/call":
            capability = str(params.get("name", ""))
            arguments = dict(params.get("arguments", {}))
            call_id = str(uuid.uuid4())

            try:
                registered = self.tool_runtime.registry.resolve(capability)
                req_caps = registered.required_capabilities
            except KeyError:
                req_caps = frozenset({capability})

            invocation = ToolInvocation(
                call_id=call_id,
                task_id=self.task_id,
                environment_id=self.environment_id,
                authority_snapshot_id=self.authority_snapshot_id,
                capability=capability,
                args=arguments,
                idempotency_key=f"mcp-{call_id}",
                timeout_ms=10_000,
                sandbox_profile="default",
                required_capabilities=req_caps,
            )
            try:
                result = self.tool_runtime.execute(
                    self.tenant_id,
                    invocation,
                    self.executor_identity,
                    upper_policy=self.upper_policy,
                )
                is_error = result.status != "completed"
                text = ""
                for item in result.items:
                    if hasattr(item, "text"):
                        text += item.text
                    else:
                        text += str(item)
                if not text and result.metadata:
                    text = json.dumps(result.metadata)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": text}],
                        "isError": is_error,
                    },
                }
            except (PolicyDeniedError, PermissionError) as p_err:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Policy denied: {p_err}"}],
                        "isError": True,
                    },
                }
            except Exception as exc:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32603, "message": str(exc)},
                }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }
