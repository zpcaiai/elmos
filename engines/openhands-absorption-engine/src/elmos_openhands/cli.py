"""Operational CLI for validation and a deterministic local qualification run."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import asdict
from importlib.resources import files
from pathlib import Path
from typing import Any

from .artifacts import ContentAddressedStore
from .command_campaigns import CommandCampaignExecutor, CommandCampaignManifest
from .firewall import ActionFirewall, FirewallContext
from .ledger import EventLedger
from .models import Action, Budget, ExecutionManifest, Identity
from .providers import NativeAgentAdapter, ProviderResponse
from .qualification import (
    CampaignType,
    QualificationRunner,
    QualificationStore,
    default_production_qualification_plan,
)
from .runtime import AgentRuntime, RuntimeTurnInput
from .tools import LocalWorkspaceToolExecutor, ToolGateway, ToolRegistry, ToolSpec
from .workspace import LocalWorkspaceProvider, WorkspaceRequest

EXPECTED_SKILL_IDS = {*(f"P0-{value:02d}" for value in range(1, 10)), *(f"P1-{value:02d}" for value in range(1, 6))}


def main(argv: list[str] | None = None) -> int:
    actual_argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog="elmos-openhands")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate", help="validate the installed implementation manifest")
    subparsers.add_parser("status", help="print code, external qualification and certification status")
    qualification = subparsers.add_parser("qualification-plan", help="materialize a digest-bound external qualification plan without executing it")
    qualification.add_argument("--target-digest", required=True)
    qualification.add_argument("--environment-digest", required=True)
    execute = subparsers.add_parser(
        "qualification-execute",
        help="execute one explicitly authorized, digest-bound campaign and store self-attested evidence",
    )
    execute.add_argument("--manifest", required=True)
    execute.add_argument("--manifest-digest", required=True)
    execute.add_argument("--workspace-root", required=True)
    execute.add_argument("--campaign", required=True, choices=[item.value for item in CampaignType])
    execute.add_argument("--target-digest", required=True)
    execute.add_argument("--environment-digest", required=True)
    execute.add_argument("--authorization-ref", required=True)
    execute.add_argument("--tenant-id", required=True)
    execute.add_argument("--project-id", required=True)
    execute.add_argument("--task-id", required=True)
    execute.add_argument("--run-id", required=True)
    execute.add_argument("--node-id", default="root")
    execute.add_argument("--evidence-root", required=True)
    subparsers.add_parser("demo", help="run a deterministic local action through every safety boundary")
    args = parser.parse_args(actual_argv)
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
    if args.command == "qualification-execute":
        return _execute_qualification(args, actual_argv)
    return _demo()


def _execute_qualification(args: argparse.Namespace, actual_argv: list[str]) -> int:
    root = Path(args.evidence_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    manifest = CommandCampaignManifest.load(
        args.manifest,
        expected_digest=args.manifest_digest,
        workspace_root=args.workspace_root,
    )
    campaign = CampaignType(args.campaign)
    target = default_production_qualification_plan(args.target_digest, args.environment_digest)[campaign]
    identity = Identity(args.tenant_id, args.project_id, args.task_id, args.run_id, args.node_id)
    store = QualificationStore(str(root / "qualification.sqlite"))
    try:
        runner = QualificationRunner(store, ContentAddressedStore(root / "cas"))
        replay = (sys.executable, "-m", "elmos_openhands.cli", *actual_argv)
        result = runner.run(
            identity,
            campaign,
            target,
            authorization_ref=args.authorization_ref,
            executor=CommandCampaignExecutor(manifest),
            independent_verifier=None,
            replay_command=replay,
        )
        output = root / f"{result.qualification_id}.json"
        output.write_text(json.dumps(result.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({**result.as_dict(), "result_path": str(output)}, indent=2, sort_keys=True))
        # A self-attested command can execute successfully, but it must not be
        # consumed as a passed external gate without an independent verifier.
        return 0 if result.status == "PASS" else 2
    finally:
        store.close()


def _manifest() -> dict[str, Any]:
    value = json.loads(files("elmos_openhands").joinpath("implementation_manifest.json").read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("implementation manifest root must be an object")
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
