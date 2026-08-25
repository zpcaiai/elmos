"""Command-line interface returning stable JSON results and errors."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from .canonical import parse_json_strict
from .catalog import load_catalog
from .errors import GoldenRouteError, RequestValidationError
from .runtime import build_registry, parse_request
from .state import BLOCKED, RunStore


def _default_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _read(path: str) -> bytes:
    if path == "-":
        return sys.stdin.buffer.read(65_537)
    return Path(path).read_bytes()


def _emit(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))


def _add_scope(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--run", required=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="elmos-spring-golden-route")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-catalog")
    validate.add_argument("--repo-root", type=Path, default=_default_root())

    invoke = subparsers.add_parser("invoke")
    invoke.add_argument("--repo-root", type=Path, default=_default_root())
    invoke.add_argument("--request", required=True, help="strict JSON file or - for stdin")

    create = subparsers.add_parser("create-run")
    create.add_argument("--repo-root", type=Path, default=_default_root())
    create.add_argument("--database", type=Path, required=True)
    create.add_argument("--request", required=True, help="strict plan JSON file or - for stdin")

    get_run = subparsers.add_parser("get-run")
    get_run.add_argument("--database", type=Path, required=True)
    _add_scope(get_run)

    events = subparsers.add_parser("list-events")
    events.add_argument("--database", type=Path, required=True)
    _add_scope(events)

    for command in ("pause-run", "resume-run", "cancel-run"):
        transition = subparsers.add_parser(command)
        transition.add_argument("--database", type=Path, required=True)
        _add_scope(transition)
        transition.add_argument("--actor", required=True)
        transition.add_argument("--expected-version", required=True, type=int)

    evidence = subparsers.add_parser("record-evidence")
    evidence.add_argument("--database", type=Path, required=True)
    _add_scope(evidence)
    evidence.add_argument("--evidence", required=True, help="strict evidence JSON file or - for stdin")

    evaluate = subparsers.add_parser("evaluate")
    evaluate.add_argument("--database", type=Path, required=True)
    _add_scope(evaluate)
    return parser


def _strict_evidence(raw: bytes) -> dict[str, object]:
    value = parse_json_strict(raw)
    expected = {
        "evidence_id",
        "role",
        "payload",
        "executor_id",
        "verifier_id",
        "authorization_id",
    }
    if not isinstance(value, dict) or set(value) != expected:
        actual = set(value) if isinstance(value, dict) else set()
        raise RequestValidationError(
            "evidence input has an invalid field set",
            details={"missing": sorted(expected - actual), "extra": sorted(actual - expected)},
        )
    if not isinstance(value["payload"], dict):
        raise RequestValidationError("evidence payload must be an object")
    for field in ("evidence_id", "role", "executor_id", "verifier_id", "authorization_id"):
        if not isinstance(value[field], str):
            raise RequestValidationError(f"evidence.{field} must be a string")
    return value


def _run(args: argparse.Namespace) -> tuple[object, int]:
    if args.command == "validate-catalog":
        catalog = load_catalog(args.repo_root)
        return (
            {
                "decision": "VALID",
                "skill_count": catalog.skill_count,
                "handler_count": len(build_registry(catalog).handlers),
                "source_archive_sha256": catalog.source_archive_sha256,
                "compiled_contracts_sha256": catalog.compiled_contracts_sha256,
                "runtime_evidence_status": "NOT_RUN",
                "customer_evidence_status": "NOT_RUN",
                "external_evidence_status": "NOT_RUN",
                "certification": "NOT_CERTIFIED",
            },
            0,
        )
    if args.command in {"invoke", "create-run"}:
        request = parse_request(_read(args.request))
        catalog = load_catalog(args.repo_root)
        registry = build_registry(catalog)
        result = registry.dispatch(request)
        if args.command == "invoke":
            return result, 0
        run = RunStore(args.database, registry=registry).create_run(request, result)
        return run.as_dict(), 0

    store = RunStore(args.database, create=False)
    if args.command == "get-run":
        return store.get_run(args.tenant, args.project, args.run).as_dict(), 0
    if args.command == "list-events":
        return {"events": store.list_events(args.tenant, args.project, args.run)}, 0
    if args.command in {"pause-run", "resume-run", "cancel-run"}:
        method = {
            "pause-run": store.pause,
            "resume-run": store.resume,
            "cancel-run": store.cancel,
        }[args.command]
        result = method(
            args.tenant,
            args.project,
            args.run,
            actor_id=args.actor,
            expected_version=args.expected_version,
        )
        return result.as_dict(), 0
    if args.command == "record-evidence":
        evidence = _strict_evidence(_read(args.evidence))
        return (
            store.record_evidence(
                args.tenant,
                args.project,
                args.run,
                evidence_id=evidence["evidence_id"],
                role=evidence["role"],
                payload=evidence["payload"],
                executor_id=evidence["executor_id"],
                verifier_id=evidence["verifier_id"],
                authorization_id=evidence["authorization_id"],
            ),
            0,
        )
    if args.command == "evaluate":
        result = store.evaluate_readiness(args.tenant, args.project, args.run)
        return result, 2 if result["decision"] == BLOCKED else 0
    raise RequestValidationError("unknown CLI command")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        result, exit_code = _run(args)
    except GoldenRouteError as exc:
        _emit(exc.as_dict())
        return 2
    except (OSError, sqlite3.Error) as exc:
        _emit(
            {
                "decision": "BLOCKED",
                "error": "LOCAL_IO_ERROR",
                "message": str(exc),
                "customer_evidence_status": "NOT_RUN",
                "external_evidence_status": "NOT_RUN",
                "certification": "NOT_CERTIFIED",
            }
        )
        return 2
    _emit(result)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
