"""Operational CLI for validation and a deterministic local qualification run."""

from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import asdict
from importlib.resources import files
from pathlib import Path
from typing import Any

from .artifacts import ContentAddressedStore
from .firewall import ActionFirewall, FirewallContext
from .ledger import EventLedger
from .models import Action, Budget, ExecutionManifest, Identity
from .providers import NativeAgentAdapter, ProviderResponse
from .qualification import default_production_qualification_plan
from .runtime import AgentRuntime, RuntimeTurnInput
from .tools import LocalWorkspaceToolExecutor, ToolGateway, ToolRegistry, ToolSpec
from .workspace import LocalWorkspaceProvider, WorkspaceRequest


EXPECTED_SKILL_IDS = {*(f"P0-{value:02d}" for value in range(1, 10)), *(f"P1-{value:02d}" for value in range(1, 6))}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="elmos-openhands")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate", help="validate the installed implementation manifest")
    subparsers.add_parser("status", help="print code, external qualification and certification status")
    qualification = subparsers.add_parser("qualification-plan", help="materialize a digest-bound external qualification plan without executing it")
    qualification.add_argument("--target-digest", required=True)
    qualification.add_argument("--environment-digest", required=True)
    subparsers.add_parser("demo", help="run a deterministic local action through every safety boundary")
    args = parser.parse_args(argv)
    if args.command == "validate":
        return _validate()
    if args.command == "status":
        manifest = _manifest()
        print(json.dumps({"code_status": manifest["implementation"]["code_status"], "external_qualification": manifest["external_qualification"], "certification": manifest["certification"], "release_status": manifest["release_status"]}, indent=2, sort_keys=True))
        return 0
    if args.command == "qualification-plan":
        plan = default_production_qualification_plan(args.target_digest, args.environment_digest)
        print(json.dumps({"campaigns": {kind.value: {**asdict(target), "status": "NOT_RUN"} for kind, target in plan.items()}, "certification": "NOT_CERTIFIED", "release_status": "NOT_GA"}, indent=2, sort_keys=True))
        return 0
    return _demo()


def _manifest() -> dict[str, Any]:
    value = json.loads(files("elmos_openhands").joinpath("implementation_manifest.json").read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("implementation manifest root must be an object")
    return value


def _validate() -> int:
    errors: list[str] = []
    try:
        manifest = _manifest()
    except (OSError, ValueError, json.JSONDecodeError) as error:
        manifest = {}
        errors.append(f"implementation manifest is invalid: {error}")
    skills = manifest.get("skills", [])
    skill_ids = {row.get("id") for row in skills if isinstance(row, dict)} if isinstance(skills, list) else set()
    if skill_ids != EXPECTED_SKILL_IDS or any(row.get("code_status") != "IMPLEMENTED" for row in skills if isinstance(row, dict)):
        errors.append("the exact 14-Skill implementation set is incomplete")
    external = manifest.get("external_qualification", {})
    if not isinstance(external, dict) or not external or any(status != "NOT_RUN" for status in external.values()):
        errors.append("external qualification status must remain NOT_RUN before real execution")
    if manifest.get("certification") != "NOT_CERTIFIED" or manifest.get("release_status") != "NOT_GA":
        errors.append("certification/GA status is not fail-closed")
    result = {"status": "PASS" if not errors else "FAIL", "engine": "elmos-openhands-absorption", "schema_version": manifest.get("schema_version"), "implemented_skills": len(skill_ids), "external_qualification": external, "certification": manifest.get("certification"), "release_status": manifest.get("release_status"), "errors": errors}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not errors else 1


def _demo() -> int:
    with tempfile.TemporaryDirectory(prefix="elmos-openhands-demo-") as root:
        database = str(Path(root) / "ledger.sqlite")
        artifacts = ContentAddressedStore(Path(root) / "cas")
        ledger = EventLedger(database)
        identity = Identity("tenant-demo", "project-demo", "task-demo", "run-demo")
        manifest = ExecutionManifest("local", "policy-v1", "native", "deterministic")
        workspace = LocalWorkspaceProvider(Path(root) / "workspaces", artifacts)
        request = workspace.allocate(WorkspaceRequest(identity))
        try:
            request = workspace.activate(request)
            registry = ToolRegistry()
            registry.register(ToolSpec("workspace", "1.0", frozenset({"workspace.read", "workspace.write"}), mutating=True, idempotent=True), LocalWorkspaceToolExecutor(workspace, request))
            runtime = AgentRuntime(ledger, NativeAgentAdapter(decisions=[ProviderResponse(action=Action("action-demo", "workspace", {"operation": "write", "path": "out/result.txt", "content": "ok"}, {}, "idem-demo", write_scope=(str(Path(request.root) / "out" / "result.txt"),), required_capabilities=("workspace.write",)))]), ToolGateway(ledger, ActionFirewall(), registry, artifacts))
            runtime.register(identity, manifest)
            result = runtime.run_turn(RuntimeTurnInput(identity, manifest, Budget(max_tool_calls=2), {"turn_id": "demo-1"}, firewall_context=FirewallContext(identity, frozenset({"workspace.write"}), (str(Path(request.root)),))))
            print(json.dumps({"status": result.status, "event_seq": result.event_seq, "chain_valid": ledger.verify_chain(identity.tenant_id, identity.run_id)}, default=str))
            return 0
        finally:
            workspace.destroy(request)
            workspace.close()
            ledger.close()
