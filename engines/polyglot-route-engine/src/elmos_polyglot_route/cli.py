from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .batch import run_batch
from .discovery import discover_repository, write_report
from .engine import migrate, migrate_module
from .models import REPOSITORY_SURFACE_LANGUAGES, RouteError
from .pipeline import run_repository_pipeline
from .preflight import repository_preflight
from .repository import plan_repository
from .single_unit import check_only, emit_only

SUBCOMMANDS = (
    "inventory",
    "repository-preflight",
    "discover",
    "batch",
    "assemble",
    "repository-pipeline",
    "emit",
    "check",
    "module",
)


def _migration_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="elmos-polyglot-route")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--source-language", choices=REPOSITORY_SURFACE_LANGUAGES, required=True)
    parser.add_argument("--target-language", choices=REPOSITORY_SURFACE_LANGUAGES, required=True)
    parser.add_argument("--function", required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _inventory_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="elmos-polyglot-route inventory")
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--repository-ref", required=True)
    parser.add_argument("--source-language", choices=REPOSITORY_SURFACE_LANGUAGES, required=True)
    parser.add_argument("--target-language", choices=REPOSITORY_SURFACE_LANGUAGES, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _discover_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="elmos-polyglot-route discover")
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Classify only the first N work units; the remainder stays undiscovered.",
    )
    return parser


def _repository_preflight_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="elmos-polyglot-route repository-preflight")
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--repository-ref", required=True)
    parser.add_argument("--source-language", choices=REPOSITORY_SURFACE_LANGUAGES, required=True)
    parser.add_argument("--target-language", choices=REPOSITORY_SURFACE_LANGUAGES, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _batch_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="elmos-polyglot-route batch")
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--discovery", type=Path, required=True)
    parser.add_argument("--cases-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Attempt only the first N discovered units; the batch stays PARTIAL.",
    )
    return parser


def _assemble_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="elmos-polyglot-route assemble")
    parser.add_argument("--batch-report", type=Path, required=True)
    parser.add_argument("--batch-output", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Also run a real whole-project build/compile check after assembling.",
    )
    return parser


def _repository_pipeline_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="elmos-polyglot-route repository-pipeline")
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--repository-ref", required=True)
    parser.add_argument("--source-language", choices=REPOSITORY_SURFACE_LANGUAGES, required=True)
    parser.add_argument("--target-language", choices=REPOSITORY_SURFACE_LANGUAGES, required=True)
    parser.add_argument("--cases-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _emit_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="elmos-polyglot-route emit")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--source-language", choices=REPOSITORY_SURFACE_LANGUAGES, required=True)
    parser.add_argument("--target-language", choices=REPOSITORY_SURFACE_LANGUAGES, required=True)
    parser.add_argument("--function", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _check_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="elmos-polyglot-route check")
    parser.add_argument("--target-language", choices=REPOSITORY_SURFACE_LANGUAGES, required=True)
    parser.add_argument("--file", type=Path, required=True, help="Path to the already-emitted file to check.")
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _module_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="elmos-polyglot-route module")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--source-language", choices=REPOSITORY_SURFACE_LANGUAGES, required=True)
    parser.add_argument("--target-language", choices=REPOSITORY_SURFACE_LANGUAGES, required=True)
    parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="Exact typed-pure-module-v1 symbol, signature, and behavior-case manifest.",
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RouteError("JSON_OBJECT_REQUIRED")
    return value


def _emit(result: dict[str, Any]) -> int:
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = list(argv) if argv is not None else sys.argv[1:]
    subcommand = arguments[0] if arguments and arguments[0] in SUBCOMMANDS else None
    remainder = arguments[1:] if subcommand else arguments

    try:
        if subcommand == "inventory":
            inventory_args = _inventory_parser().parse_args(remainder)
            if inventory_args.output.exists():
                raise RouteError("INVENTORY_OUTPUT_ALREADY_EXISTS")
            result = plan_repository(
                inventory_args.repository,
                inventory_args.repository_ref,
                inventory_args.source_language,
                inventory_args.target_language,
            )
            inventory_args.output.parent.mkdir(parents=True, exist_ok=True)
            inventory_args.output.write_text(
                json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            return _emit(result)

        if subcommand == "discover":
            discover_args = _discover_parser().parse_args(remainder)
            if discover_args.limit is not None and discover_args.limit < 1:
                raise RouteError("DISCOVERY_LIMIT_INVALID")
            report = discover_repository(
                _load_json(discover_args.plan),
                discover_args.repository,
                limit=discover_args.limit,
            )
            write_report(report, discover_args.output)
            return _emit(report)

        if subcommand == "repository-preflight":
            preflight_args = _repository_preflight_parser().parse_args(remainder)
            if preflight_args.output.exists() or preflight_args.output.is_symlink():
                raise RouteError("PREFLIGHT_OUTPUT_ALREADY_EXISTS_OR_UNSAFE")
            report = repository_preflight(
                preflight_args.repository,
                preflight_args.repository_ref,
                preflight_args.source_language,
                preflight_args.target_language,
            )
            preflight_args.output.parent.mkdir(parents=True, exist_ok=True)
            temporary = preflight_args.output.with_suffix(preflight_args.output.suffix + ".tmp")
            if temporary.exists() or temporary.is_symlink():
                raise RouteError("PREFLIGHT_OUTPUT_TEMPORARY_UNSAFE")
            temporary.write_text(
                json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temporary.replace(preflight_args.output)
            return _emit(report)

        if subcommand == "batch":
            batch_args = _batch_parser().parse_args(remainder)
            if batch_args.limit is not None and batch_args.limit < 1:
                raise RouteError("BATCH_LIMIT_INVALID")
            report = run_batch(
                _load_json(batch_args.discovery),
                batch_args.repository,
                batch_args.cases_directory,
                batch_args.output,
                limit=batch_args.limit,
            )
            return _emit(report)

        if subcommand == "assemble":
            _assemble_parser().parse_args(remainder)
            raise RouteError(
                "STANDALONE_ASSEMBLY_DISABLED_UNTRUSTED_BATCH_REPORT:"
                "use repository-pipeline so batch evidence is produced and consumed in one execution"
            )

        if subcommand == "repository-pipeline":
            pipeline_args = _repository_pipeline_parser().parse_args(remainder)
            report = run_repository_pipeline(
                pipeline_args.repository,
                pipeline_args.repository_ref,
                pipeline_args.source_language,
                pipeline_args.target_language,
                pipeline_args.cases_directory,
                pipeline_args.output,
            )
            return _emit(report)

        if subcommand == "emit":
            emit_args = _emit_parser().parse_args(remainder)
            report = emit_only(
                emit_args.source,
                emit_args.source_language,
                emit_args.target_language,
                emit_args.function,
                emit_args.output,
            )
            return _emit(report)

        if subcommand == "check":
            check_args = _check_parser().parse_args(remainder)
            content = check_args.file.read_text(encoding="utf-8")
            report = check_only(check_args.target_language, content, check_args.output)
            return _emit(report)

        if subcommand == "module":
            module_args = _module_parser().parse_args(remainder)
            report = migrate_module(
                module_args.source,
                module_args.source_language,
                module_args.target_language,
                module_args.manifest,
                module_args.output,
            )
            return _emit(report)

        args = _migration_parser().parse_args(remainder)
        result = migrate(
            args.source,
            args.source_language,
            args.target_language,
            args.function,
            args.cases,
            args.output,
        )
        return _emit(result)
    except (OSError, ValueError, RouteError, RuntimeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "BLOCKED", "reason": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
