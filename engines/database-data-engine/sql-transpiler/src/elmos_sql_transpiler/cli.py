from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .materialize import materialize
from .models import ParameterContract, TranspileRequest
from .profiles import capabilities
from .qualification import run_qualification
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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="elmos-sql-transpiler")
    subparsers = parser.add_subparsers(dest="command", required=True)

    capability_parser = subparsers.add_parser("capabilities")
    capability_parser.add_argument("--output", type=Path)

    transpile_parser = subparsers.add_parser("transpile")
    transpile_parser.add_argument("request", type=Path)
    transpile_parser.add_argument("output", type=Path)
    transpile_parser.add_argument("--source", default="")
    transpile_parser.add_argument("--target", default="")
    transpile_parser.add_argument("--query-id")

    qualification_parser = subparsers.add_parser("qualify")
    qualification_parser.add_argument("corpora", nargs="+", type=Path)
    qualification_parser.add_argument("--output", type=Path)
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
        if args.command == "transpile":
            request = _request(args.request, args.source, args.target, args.query_id)
            result = transpile(request)
            if result.state != "SYNTAX_READY":
                sys.stderr.write(_json(result.to_dict(include_sql=False)) + "\n")
                return 2
            sys.stdout.write(_json(materialize(result, args.output)) + "\n")
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
    except (FileExistsError, KeyError, TypeError, ValueError) as error:
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
