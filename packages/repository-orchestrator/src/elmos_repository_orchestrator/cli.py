"""Machine-readable CLI for catalog, preflight, dispatch, plan, and gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from .catalog import MODEL_ALIASES, SKILL_NAMES, SKILL_SPECS
from .contracts import ContractError, Status, canonical_json, require_mapping
from .gates import run_package_gate
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
    if status in {Status.LOCAL_ENGINEERING_VALIDATED.value, Status.READY.value, Status.PLANNED.value}:
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
            result = dispatch("elmos-task-dag-builder", _read_json(args.input, "input"))
        else:
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
        _emit(result)
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


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
