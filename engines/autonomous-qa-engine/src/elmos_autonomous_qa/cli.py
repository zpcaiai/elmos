"""Command-line entry point for the bounded autonomous-QA runtime.

The CLI accepts structured JSON only.  It never converts source Skill text,
workflow actions, or caller strings into shell commands.
"""

from __future__ import annotations

import argparse
import os
import stat
import sys
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from .canonical import parse_json_strict
from .contracts import ContractError, canonical_json, strict_json
from .control_plane import ControlPlaneError, QaControlPlane
from .project import SnapshotPolicy, build_project_snapshot
from .skill_runtime import (
    SKILL_REGISTRY,
    SkillRuntimeError,
    dispatch_skill,
    resolve_skill,
)


class CliError(ValueError):
    """Raised for malformed CLI input without exposing implementation details."""


MAX_JSON_INPUT_BYTES = 16 * 1024 * 1024


def _load_object(path: str, field: str) -> dict[str, Any]:
    try:
        if path == "-":
            payload = sys.stdin.buffer.read(MAX_JSON_INPUT_BYTES + 1)
            if len(payload) > MAX_JSON_INPUT_BYTES:
                raise CliError(f"{field} exceeds the JSON input limit")
        else:
            flags = os.O_RDONLY
            for name in ("O_CLOEXEC", "O_NOFOLLOW", "O_NONBLOCK"):
                flags |= getattr(os, name, 0)
            descriptor = os.open(path, flags)
            try:
                before = os.fstat(descriptor)
                if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                    raise CliError(f"{field} must be a singly-linked regular file")
                if before.st_size > MAX_JSON_INPUT_BYTES:
                    raise CliError(f"{field} exceeds the JSON input limit")
                chunks: list[bytes] = []
                remaining = MAX_JSON_INPUT_BYTES + 1
                while remaining:
                    chunk = os.read(descriptor, min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
                payload = b"".join(chunks)
                after = os.fstat(descriptor)
                identity = lambda value: (
                    value.st_dev,
                    value.st_ino,
                    value.st_size,
                    value.st_mtime_ns,
                    value.st_ctime_ns,
                    value.st_nlink,
                )
                if len(payload) > MAX_JSON_INPUT_BYTES or identity(before) != identity(after):
                    raise CliError(f"{field} changed while being read")
            finally:
                os.close(descriptor)
        value = parse_json_strict(payload)
    except (OSError, ValueError) as exc:
        raise CliError(f"unable to read valid JSON for {field}") from exc
    if not isinstance(value, dict):
        raise CliError(f"{field} must contain a JSON object")
    try:
        normalized = strict_json(value, field)
    except ContractError as exc:
        raise CliError(f"unable to read valid JSON for {field}") from exc
    if not isinstance(normalized, dict):
        raise CliError(f"{field} must contain a JSON object")
    return normalized


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def _emit(value: Any) -> None:
    sys.stdout.write(canonical_json(_jsonable(value)) + "\n")


def _database(args: argparse.Namespace) -> QaControlPlane:
    return QaControlPlane(Path(args.database))


def _add_identity(parser: argparse.ArgumentParser, *, run: bool = True) -> None:
    parser.add_argument("--database", required=True)
    parser.add_argument("--tenant", required=True)
    if run:
        parser.add_argument("--run-id", required=True)


def _add_mutation(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--idempotency-key", required=True)


def _local_actor() -> str:
    """Bind local mutations to the operating-system principal, not argv."""

    return f"local-uid-{os.getuid()}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="elmos-autonomous-qa")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("skills", help="list the exact installed runtime bindings")

    execute = commands.add_parser("execute", help="dispatch one exact Skill request")
    execute.add_argument("skill")
    execute.add_argument("--request", required=True, help="JSON file, or - for stdin")

    snapshot_defaults = SnapshotPolicy()
    snapshot = commands.add_parser("snapshot", help="create a bounded read-only project snapshot")
    snapshot.add_argument("root")
    snapshot.add_argument("--required", action="append", default=[])
    snapshot.add_argument("--max-files", type=int, default=snapshot_defaults.max_files)
    snapshot.add_argument("--max-entries", type=int, default=snapshot_defaults.max_entries)
    snapshot.add_argument(
        "--max-directories", type=int, default=snapshot_defaults.max_directories
    )
    snapshot.add_argument(
        "--max-diagnostics", type=int, default=snapshot_defaults.max_diagnostics
    )
    snapshot.add_argument("--max-depth", type=int, default=snapshot_defaults.max_depth)
    snapshot.add_argument(
        "--max-total-bytes", type=int, default=snapshot_defaults.max_total_bytes
    )
    snapshot.add_argument(
        "--max-single-file-bytes",
        type=int,
        default=snapshot_defaults.max_single_file_bytes,
    )

    create = commands.add_parser("run-create", help="create a durable run")
    _add_identity(create)
    _add_mutation(create)
    create.add_argument("--project", required=True)
    create.add_argument("--mode", required=True)
    create.add_argument("--payload", required=True, help="JSON file, or - for stdin")

    get = commands.add_parser("run-get", help="get one tenant-scoped run")
    _add_identity(get)

    recover = commands.add_parser("run-recover", help="list active tenant-scoped runs")
    _add_identity(recover, run=False)

    transition = commands.add_parser("run-transition", help="apply one legal run transition")
    _add_identity(transition)
    _add_mutation(transition)
    transition.add_argument(
        "action",
        choices=("start", "pause", "resume", "cancel", "request_approval", "fail", "complete"),
    )
    transition.add_argument("--details", help="optional JSON file, or - for stdin")

    retry = commands.add_parser("run-retry", help="retry a terminal run with a new identity")
    _add_identity(retry)
    _add_mutation(retry)
    retry.add_argument("--new-run-id", required=True)

    events = commands.add_parser("run-events", help="list the immutable event chain")
    _add_identity(events)

    audit = commands.add_parser("run-audit", help="list tenant-scoped audit records")
    _add_identity(audit)

    return parser


def _execute(args: argparse.Namespace) -> tuple[Any, int]:
    if args.command == "skills":
        bindings = [
            {
                "skill": binding.skill,
                "source_id": binding.source_id,
                "handler_id": binding.handler_id,
                "operation_id": binding.operation_id,
                "phase": binding.phase,
                "mutating": binding.mutating,
            }
            for binding in SKILL_REGISTRY.values()
        ]
        return {
            "schema_version": "1.0",
            "skills": bindings,
            "external_evidence": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }, 0
    if args.command == "execute":
        request = _load_object(args.request, "request")
        alias = resolve_skill(args.skill)
        if SKILL_REGISTRY[alias].mutating:
            raise CliError(
                "mutating Skill execution requires a trusted tenant/project scope binder"
            )
        # The command line owns only the local OS identity.  A JSON document
        # cannot impersonate an actor.  Mutating bindings are rejected above
        # because the local CLI cannot independently authorize tenant/project
        # scope.
        request["actor_id"] = _local_actor()
        result = dispatch_skill(alias, request)
        return result, 0 if result["state"] == "SUCCEEDED" else 3
    if args.command == "snapshot":
        policy = SnapshotPolicy(
            max_files=args.max_files,
            max_entries=args.max_entries,
            max_directories=args.max_directories,
            max_diagnostics=args.max_diagnostics,
            max_depth=args.max_depth,
            max_total_bytes=args.max_total_bytes,
            max_single_file_bytes=args.max_single_file_bytes,
        )
        snapshot = build_project_snapshot(
            Path(args.root), required_paths=tuple(args.required), policy=policy
        )
        return snapshot, 0 if snapshot["complete"] is True else 3

    control_plane = _database(args)
    if args.command == "run-create":
        run = control_plane.create_run(
            tenant_id=args.tenant,
            run_id=args.run_id,
            project_id=args.project,
            mode=args.mode,
            payload=_load_object(args.payload, "payload"),
            idempotency_key=args.idempotency_key,
            actor=_local_actor(),
        )
        return run, 0
    if args.command == "run-get":
        return control_plane.get_run(tenant_id=args.tenant, run_id=args.run_id), 0
    if args.command == "run-recover":
        return {"runs": control_plane.recover_active_runs(tenant_id=args.tenant)}, 0
    if args.command == "run-transition":
        details = _load_object(args.details, "details") if args.details else {}
        run = control_plane.transition(
            tenant_id=args.tenant,
            run_id=args.run_id,
            action=args.action,
            idempotency_key=args.idempotency_key,
            actor=_local_actor(),
            details=details,
        )
        return run, 0
    if args.command == "run-retry":
        run = control_plane.retry_run(
            tenant_id=args.tenant,
            source_run_id=args.run_id,
            new_run_id=args.new_run_id,
            idempotency_key=args.idempotency_key,
            actor=_local_actor(),
        )
        return run, 0
    if args.command == "run-events":
        return {"events": control_plane.list_events(tenant_id=args.tenant, run_id=args.run_id)}, 0
    if args.command == "run-audit":
        return {"audit": control_plane.list_audit(tenant_id=args.tenant, run_id=args.run_id)}, 0
    raise CliError("unsupported command")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        result, code = _execute(parser.parse_args(argv))
        _emit(result)
        return code
    except (CliError, ContractError, ControlPlaneError, SkillRuntimeError, OSError, ValueError) as exc:
        _emit(
            {
                "schema_version": "1.0",
                "state": "BLOCKED",
                "code": "AUTONOMOUS_QA_CLI_REJECTED",
                "error_type": type(exc).__name__,
                "external_evidence": "NOT_RUN",
                "certification": "NOT_CERTIFIED",
            }
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
