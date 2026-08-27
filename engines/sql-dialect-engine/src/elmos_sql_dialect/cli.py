from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .chinadb import chinadb_capabilities
from .engine import translate_ddl
from .models import Dialect, RouteError
from .scan import render_markdown, report_to_json, scan_repository
from .toolchains import verify_toolchain

SUBCOMMANDS = ("translate", "scan", "chinadb-capabilities")


def _translate_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = subparsers.add_parser("translate", help="translate one certified SQL statement between dialects")
    p.add_argument("--source-file", required=True, type=Path)
    p.add_argument("--source-dialect", required=True, choices=[d.value for d in Dialect])
    p.add_argument("--target-dialect", required=True, choices=[d.value for d in Dialect])
    p.add_argument(
        "--statement-kind",
        default="TABLE",
        choices=[
            "TABLE",
            "INDEX",
            "INSERT",
            "UPDATE",
            "ALTER",
            "DROP",
            "SCHEMA",
            "FUNCTION",
            "PROCEDURE",
            "TRIGGER",
            "VIEW",
            "COMMENT",
            "GRANT",
            "REVOKE",
            "POLICY",
        ],
    )
    p.add_argument("--dsn", default=None, help="optional real-database DSN/connection params for execution validation")
    p.add_argument(
        "--namespace-map",
        default=None,
        help="JSON object mapping source schema names to target schema names",
    )
    p.add_argument("--output", required=True, type=Path)


def _run_translate(args: argparse.Namespace) -> int:
    verify_toolchain()
    sql = args.source_file.read_text(encoding="utf-8")
    namespace_map = None
    if args.namespace_map is not None:
        try:
            raw_map = json.loads(args.namespace_map)
        except json.JSONDecodeError as exc:
            raise RouteError(f"INVALID_NAMESPACE_MAP: {exc}") from exc
        if not isinstance(raw_map, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in raw_map.items()
        ):
            raise RouteError("INVALID_NAMESPACE_MAP: expected a JSON object of string-to-string mappings")
        namespace_map = raw_map
    report = translate_ddl(
        sql,
        args.source_dialect,
        args.target_dialect,
        statement_kind=args.statement_kind,
        dsn=args.dsn,
        namespace_map=namespace_map,
    )
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "translation-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if report["emitted"] is not None:
        extension = {"postgres": "sql", "mysql": "sql", "oracle": "sql", "tsql": "sql"}[args.target_dialect]
        (args.output / f"emitted.{extension}").write_text(report["emitted"] + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASSED" else 2


def _scan_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = subparsers.add_parser(
        "scan",
        help="scan SQL units: automatic candidates plus 100% explicit disposition coverage",
    )
    p.add_argument("--repository", required=True, type=Path)
    p.add_argument("--source-dialect", required=True, choices=[d.value for d in Dialect])
    p.add_argument("--output", default=None, type=Path)
    p.add_argument("--examples", default=5, type=int)
    p.add_argument("--all-findings", action="store_true")
    p.add_argument(
        "--namespace-map", default=None, help="JSON object mapping source schema names to target schema names"
    )
    p.add_argument(
        "--require-disposition-complete",
        action="store_true",
        help="succeed when every discovered unit has a non-unknown disposition",
    )


def _run_scan(args: argparse.Namespace) -> int:
    """The pre-check exists so the subset boundary is visible BEFORE a
    migration is committed to, not from the wreckage of a failed run."""
    namespace_map = None
    if args.namespace_map is not None:
        try:
            raw_map = json.loads(args.namespace_map)
        except json.JSONDecodeError as exc:
            raise RouteError(f"INVALID_NAMESPACE_MAP: {exc}") from exc
        if not isinstance(raw_map, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in raw_map.items()
        ):
            raise RouteError("INVALID_NAMESPACE_MAP: expected a JSON object of string-to-string mappings")
        namespace_map = raw_map
    report = scan_repository(
        args.repository,
        Dialect(args.source_dialect),
        examples_per_blocker=args.examples,
        include_all_findings=args.all_findings,
        namespace_map=namespace_map,
    )
    if args.output is not None:
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "feasibility-report.json").write_text(report_to_json(report), encoding="utf-8")
        # The migration decision gets made by someone who will not read JSON.
        (args.output / "feasibility-report.md").write_text(render_markdown(report), encoding="utf-8")
    print(report_to_json(report))
    if args.require_disposition_complete:
        return (
            0
            if (
                report.disposition_coverage == 1.0
                and report.totals["dispositionUnknown"] == 0
                and report.totals["scanErrors"] == 0
            )
            else 2
        )
    return 0 if report.totals["outOfSubset"] == 0 and report.totals["scanErrors"] == 0 else 2


def _chinadb_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = subparsers.add_parser(
        "chinadb-capabilities",
        help="show the fail-closed ChinaDB domestic target registry",
    )
    p.add_argument("--output", default=None, type=Path)


def _run_chinadb_capabilities(args: argparse.Namespace) -> int:
    payload = json.dumps(chinadb_capabilities(), indent=2, ensure_ascii=False) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="elmos-sql-dialect")
    subparsers = parser.add_subparsers(dest="command", required=True)
    _translate_parser(subparsers)
    _scan_parser(subparsers)
    _chinadb_parser(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "translate":
            return _run_translate(args)
        if args.command == "scan":
            return _run_scan(args)
        if args.command == "chinadb-capabilities":
            return _run_chinadb_capabilities(args)
        raise RouteError(f"UNKNOWN_COMMAND: {args.command!r}")  # pragma: no cover
    except RouteError as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, indent=2))
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
