"""Machine-readable CLI for catalog, preflight, dispatch, plan, and gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from .catalog import MODEL_ALIASES, SKILL_NAMES, SKILL_SPECS
from .contracts import ContractError, Status, canonical_json, require_mapping
from .external_execution import execute_external_integrations
from .external_gate import external_preflight, evaluate_production_certification
from .gates import run_package_gate
from .production_runtime import probe_production_runtime, runtime_preflight
from .runtime import dispatch, handler_names


MAX_INPUT_BYTES = 5 * 1024 * 1024
PACKAGE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HANDLER_REGISTRY = PACKAGE_ROOT / "config" / "handler-registry.json"


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ContractError("cli_arguments", message)


def _read_json(path_text: str, field_name: str) -> Mapping[str, Any]:
    if path_text == "-":
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    else:
        path = Path(path_text)
        try:
            if path.stat().st_size > MAX_INPUT_BYTES:
                raise ContractError("input_too_large", f"{field_name} exceeds {MAX_INPUT_BYTES} bytes")
            raw = path.read_bytes()
        except OSError as exc:
            raise ContractError("input_unavailable", f"cannot read {field_name}") from exc
    if len(raw) > MAX_INPUT_BYTES:
        raise ContractError("input_too_large", f"{field_name} exceeds {MAX_INPUT_BYTES} bytes")
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError("invalid_json", f"{field_name} must be UTF-8 JSON") from exc
    return require_mapping(parsed, field_name)


def _trusted_context(path_text: str | None) -> Mapping[str, Any] | None:
    return None if path_text is None else _read_json(path_text, "trusted_context")


def _emit(payload: Mapping[str, Any]) -> None:
    sys.stdout.write(canonical_json(payload) + "\n")


def _result_exit(status: str) -> int:
    if status in {
        Status.LOCAL_ENGINEERING_VALIDATED.value,
        Status.READY.value,
        Status.PLANNED.value,
        "EXECUTED_UNVERIFIED",
    }:
        return 0
    if status in {Status.BLOCKED.value, Status.FAILED.value}:
        return 2
    return 3


def _parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(prog="elmos-repository-orchestrator", add_help=True)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("catalog")

    preflight = subcommands.add_parser("preflight")
    preflight.add_argument("--input", required=True)
    preflight.add_argument("--trusted-context")

    execute = subcommands.add_parser("execute-skill")
    execute.add_argument("skill_name")
    execute.add_argument("--input", required=True)
    execute.add_argument("--trusted-context")

    plan = subcommands.add_parser("validate-plan")
    plan.add_argument("--input", required=True)

    gate = subcommands.add_parser("gate")
    gate.add_argument("--input", required=True)
    gate.add_argument("--evidence-root", required=True)
    gate.add_argument("--registry", default=str(DEFAULT_HANDLER_REGISTRY))

    external_preflight_parser = subcommands.add_parser("external-preflight")
    external_preflight_parser.add_argument("--plan", required=True)
    external_preflight_parser.add_argument("--expect-blocked", action="store_true")

    external_execute = subcommands.add_parser("external-execute")
    external_execute.add_argument("--input", required=True)
    external_execute.add_argument("--execute", action="store_true")

    runtime_preflight_parser = subcommands.add_parser("runtime-preflight")
    runtime_preflight_parser.add_argument("--plan", required=True)
    runtime_preflight_parser.add_argument("--expect-blocked", action="store_true")

    runtime_probe = subcommands.add_parser("runtime-probe")
    runtime_probe.add_argument("--plan", required=True)
    runtime_probe.add_argument("--execute", action="store_true")

    external_certify = subcommands.add_parser("external-certify")
    external_certify.add_argument("--plan", required=True)
    external_certify.add_argument("--report", required=True)
    external_certify.add_argument("--evidence-root", required=True)
    external_certify.add_argument("--certificate")
    external_certify.add_argument("--public-key")
    return parser


def _catalog() -> dict[str, Any]:
    return {
        "status": Status.LOCAL_ENGINEERING_VALIDATED.value,
        "certification": Status.NOT_CERTIFIED.value,
        "runtime_binding": "elmos_repository_orchestrator.runtime:dispatch",
        "model_aliases": list(MODEL_ALIASES),
        "skills": [
            {
                "name": name,
                "handler": SKILL_SPECS[name].handler,
                "canonical_owner": SKILL_SPECS[name].canonical_owner,
                "adapter_requirement": SKILL_SPECS[name].adapter_requirement,
            }
            for name in SKILL_NAMES
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        if args.command == "catalog":
            result = _catalog()
        elif args.command == "preflight":
            result = dispatch(
                "elmos-model-selection-controller",
                _read_json(args.input, "input"),
                trusted_context=_trusted_context(args.trusted_context),
            )
        elif args.command == "execute-skill":
            result = dispatch(
                args.skill_name,
                _read_json(args.input, "input"),
                trusted_context=_trusted_context(args.trusted_context),
            )
        elif args.command == "validate-plan":
            plan_input = _read_json(args.input, "input")
            if "nodes" in plan_input or "required_scenarios" in plan_input:
                result = dispatch("elmos-plan-graph-verifier", plan_input)
            else:
                result = dispatch("elmos-task-dag-builder", plan_input)
        elif args.command == "gate":
            request = _read_json(args.input, "gate_request")
            registry = _read_json(args.registry, "handler_registry")
            evidence_root = Path(args.evidence_root)
            try:
                evidence_root = evidence_root.resolve(strict=True)
            except OSError as exc:
                raise ContractError("evidence_root_unavailable", "evidence root does not exist") from exc
            if not evidence_root.is_dir():
                raise ContractError("evidence_root_not_directory", "evidence root must be a directory")
            result = run_package_gate(
                request,
                evidence_root=evidence_root,
                static_registry=registry,
                handler_names=handler_names(),
            ).to_payload()
        elif args.command == "external-preflight":
            result = external_preflight(_read_json(args.plan, "external_plan"))
        elif args.command == "external-execute":
            if not args.execute:
                raise ContractError("execution_flag_required", "external-execute requires --execute")
            result = execute_external_integrations(_read_json(args.input, "external_execution_request"))
        elif args.command == "runtime-preflight":
            result = runtime_preflight(_read_json(args.plan, "runtime_plan"))
        elif args.command == "runtime-probe":
            if not args.execute:
                raise ContractError("execution_flag_required", "runtime-probe requires --execute")
            result = probe_production_runtime(_read_json(args.plan, "runtime_plan"))
        else:
            certificate = None if args.certificate is None else _read_json(args.certificate, "certificate")
            public_key = None if args.public_key is None else Path(args.public_key)
            result = evaluate_production_certification(
                _read_json(args.plan, "external_plan"),
                _read_json(args.report, "external_report"),
                evidence_root=Path(args.evidence_root),
                certificate_value=certificate,
                public_key=public_key,
            )
        _emit(result)
        if (
            args.command in {"external-preflight", "runtime-preflight"}
            and args.expect_blocked
            and result.get("status") == "BLOCKED"
        ):
            return 0
        return _result_exit(str(result.get("status")))
    except ContractError as exc:
        _emit(
            {
                "status": Status.BLOCKED.value,
                "certification": Status.NOT_CERTIFIED.value,
                "certified": False,
                "reasons": [f"{exc.code}:{exc}"],
            }
        )
        return 2
    except Exception:
        if getattr(args, "command", None) not in {"external-execute", "runtime-probe"}:
            raise
        _emit(
            {
                "status": Status.UNKNOWN.value,
                "certification": Status.NOT_CERTIFIED.value,
                "certified": False,
                "reasons": ["external_result_unknown:reconcile before retry"],
            }
        )
        return 3


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
