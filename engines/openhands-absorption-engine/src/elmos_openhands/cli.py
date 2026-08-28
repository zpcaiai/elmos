"""Operational CLI for validation and a deterministic local qualification run."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from .artifacts import ContentAddressedStore
from .firewall import ActionFirewall, FirewallContext
from .ledger import EventLedger
from .models import Action, Budget, ExecutionManifest, Identity
from .providers import NativeAgentAdapter, ProviderResponse
from .runtime import AgentRuntime, RuntimeTurnInput
from .tools import ToolGateway, ToolRegistry, ToolSpec
from .workspace import LocalWorkspaceProvider, WorkspaceRequest
from .tools import LocalWorkspaceToolExecutor


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="elmos-openhands")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate", help="validate that the package imports")
    subparsers.add_parser("demo", help="run a deterministic local action through every safety boundary")
    args = parser.parse_args(argv)
    if args.command == "validate":
        print(json.dumps({"status": "PASS", "engine": "elmos-openhands-absorption", "schema_version": "1.0"}))
        return 0
    return _demo()


def _demo() -> int:
    with tempfile.TemporaryDirectory(prefix="elmos-openhands-demo-") as root:
        database = str(Path(root) / "ledger.sqlite")
        artifacts = ContentAddressedStore(Path(root) / "cas")
        ledger = EventLedger(database)
        identity = Identity("tenant-demo", "project-demo", "task-demo", "run-demo")
        manifest = ExecutionManifest("local", "policy-v1", "native", "deterministic")
        workspace = LocalWorkspaceProvider(Path(root) / "workspaces", artifacts)
        request = workspace.allocate(WorkspaceRequest(identity))
        request = workspace.activate(request)
        registry = ToolRegistry()
        registry.register(ToolSpec("workspace", "1.0", frozenset({"workspace.read", "workspace.write"}), mutating=True, idempotent=True), LocalWorkspaceToolExecutor(workspace, request))
        runtime = AgentRuntime(ledger, NativeAgentAdapter(decisions=[ProviderResponse(action=Action("action-demo", "workspace", {"operation": "write", "path": "out/result.txt", "content": "ok"}, {}, "idem-demo", write_scope=(str(Path(request.root) / "out" / "result.txt"),), required_capabilities=("workspace.write",)))]), ToolGateway(ledger, ActionFirewall(), registry, artifacts))
        runtime.register(identity, manifest)
        result = runtime.run_turn(RuntimeTurnInput(identity, manifest, Budget(max_tool_calls=2), {"turn_id": "demo-1"}, firewall_context=FirewallContext(identity, frozenset({"workspace.write"}), (str(Path(request.root)),))))
        print(json.dumps({"status": result.status, "event_seq": result.event_seq, "chain_valid": ledger.verify_chain(identity.tenant_id, identity.run_id)}, default=str))
        return 0
