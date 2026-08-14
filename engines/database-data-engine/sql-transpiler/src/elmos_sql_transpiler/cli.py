from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .commercial import assess_commercial, commercial_capabilities
from .commercial_request import parse_commercial_request_json
from .materialize import materialize
from .models import ParameterContract, TranspileRequest
from .profiles import capabilities
from .qualification import run_qualification
from .runner import (
    RunnerBlockedError,
    runner_capabilities,
    verify_local_matrix,
    verify_route,
)
from .transpiler import transpile


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _request(path: Path, source: str, target: str, query_id: str | None) -> TranspileRequest:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("request must be a JSON object")
    parameters = tuple(
        ParameterContract(
            name=str(item["name"]),
            logical_type=str(item["logicalType"]),
            nullable=bool(item["nullable"]),
        )
        for item in raw.get("parameters", [])
    )
    return TranspileRequest(
        query_id=query_id or str(raw["queryId"]),
        source_profile=source or str(raw["sourceProfile"]),
        target_profile=target or str(raw["targetProfile"]),
        sql=str(raw["sql"]),
        parameters=parameters,
    )


def _create_only_output(path: Path | None, rendered: str, *, label: str) -> None:
    if path is None:
        sys.stdout.write(rendered)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(rendered)
    except FileExistsError as error:
        raise FileExistsError(f"{label} output already exists") from error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="elmos-sql-transpiler")
    subparsers = parser.add_subparsers(dest="command", required=True)

    capability_parser = subparsers.add_parser("capabilities")
    capability_parser.add_argument("--output", type=Path)

    commercial_capability_parser = subparsers.add_parser("commercial-capabilities")
    commercial_capability_parser.add_argument("--output", type=Path)

    commercial_assess_parser = subparsers.add_parser("commercial-assess")
    commercial_assess_parser.add_argument("request", type=Path)
    commercial_assess_parser.add_argument("--output", type=Path)

    runner_capability_parser = subparsers.add_parser("runner-capabilities")
    runner_capability_parser.add_argument("--output", type=Path)

    transpile_parser = subparsers.add_parser("transpile")
    transpile_parser.add_argument("request", type=Path)
    transpile_parser.add_argument("output", type=Path)
    transpile_parser.add_argument("--source", default="")
    transpile_parser.add_argument("--target", default="")
    transpile_parser.add_argument("--query-id")

    qualification_parser = subparsers.add_parser("qualify")
    qualification_parser.add_argument("corpora", nargs="+", type=Path)
    qualification_parser.add_argument("--output", type=Path)

    verify_parser = subparsers.add_parser("verify-route")
    verify_parser.add_argument("source")
    verify_parser.add_argument("target")
    verify_parser.add_argument("output", type=Path)

    matrix_parser = subparsers.add_parser("verify-local-matrix")
    matrix_parser.add_argument("output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "capabilities":
            value = capabilities()
            rendered = _json(value) + "\n"
            if args.output:
                if args.output.exists():
                    raise FileExistsError("capability output already exists")
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(rendered, encoding="utf-8")
            else:
                sys.stdout.write(rendered)
            return 0
        if args.command == "commercial-capabilities":
            rendered = _json(commercial_capabilities()) + "\n"
            _create_only_output(args.output, rendered, label="commercial capability")
            return 0
        if args.command == "commercial-assess":
            assessment = assess_commercial(parse_commercial_request_json(args.request.read_bytes()))
            rendered = _json(assessment.to_dict()) + "\n"
            _create_only_output(args.output, rendered, label="commercial assessment")
            return 3
        if args.command == "runner-capabilities":
            value = runner_capabilities()
            rendered = _json(value) + "\n"
            if args.output:
                if args.output.exists():
                    raise FileExistsError("Runner capability output already exists")
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(rendered, encoding="utf-8")
            else:
                sys.stdout.write(rendered)
            return 0
        if args.command == "transpile":
            request = _request(args.request, args.source, args.target, args.query_id)
            transpilation = transpile(request)
            if transpilation.state != "SYNTAX_READY":
                sys.stderr.write(_json(transpilation.to_dict(include_sql=False)) + "\n")
                return 2
            sys.stdout.write(_json(materialize(transpilation, args.output)) + "\n")
            return 0
        if args.command == "qualify":
            report = run_qualification(args.corpora)
            rendered = _json(report) + "\n"
            if args.output:
                if args.output.exists():
                    raise FileExistsError("qualification output already exists")
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(rendered, encoding="utf-8")
            else:
                sys.stdout.write(rendered)
            return 0 if report["localDecision"] == "READY_FOR_ENGINE_EXECUTION" else 3
        if args.command == "verify-route":
            gate_result = verify_route(args.source, args.target, args.output)
            sys.stdout.write(_json(gate_result) + "\n")
            return 0 if gate_result["localDecision"] == "READY_FOR_EXTERNAL_GATE" else 4
        if args.command == "verify-local-matrix":
            matrix_result = verify_local_matrix(args.output)
            sys.stdout.write(_json(matrix_result) + "\n")
            return 0 if matrix_result["localDecision"] == "READY_FOR_EXTERNAL_GATE" else 4
    except (
        FileExistsError,
        KeyError,
        RunnerBlockedError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as error:
        sys.stderr.write(
            _json(
                {
                    "status": "BLOCKED",
                    "error": type(error).__name__,
                    "message": str(error),
                    "certification": "NOT_CERTIFIED",
                }
            )
            + "\n"
        )
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
