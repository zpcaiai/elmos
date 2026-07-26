from __future__ import annotations

import argparse
import json
from pathlib import Path

from .engine import migrate
from .models import SUPPORTED_LANGUAGES, RouteError
from .repository import plan_repository


def _migration_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="elmos-polyglot-route")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--source-language", choices=SUPPORTED_LANGUAGES, required=True)
    parser.add_argument("--target-language", choices=SUPPORTED_LANGUAGES, required=True)
    parser.add_argument("--function", required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _inventory_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="elmos-polyglot-route inventory")
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--repository-ref", required=True)
    parser.add_argument("--source-language", choices=SUPPORTED_LANGUAGES, required=True)
    parser.add_argument("--target-language", choices=SUPPORTED_LANGUAGES, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = list(argv) if argv is not None else None
    inventory_mode = bool(arguments and arguments[0] == "inventory")
    if arguments is None:
        import sys

        arguments = sys.argv[1:]
        inventory_mode = bool(arguments and arguments[0] == "inventory")
    if inventory_mode:
        args = _inventory_parser().parse_args(arguments[1:])
        try:
            if args.output.exists():
                raise RouteError("INVENTORY_OUTPUT_ALREADY_EXISTS")
            result = plan_repository(
                args.repository,
                args.repository_ref,
                args.source_language,
                args.target_language,
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except (OSError, ValueError, RouteError, RuntimeError, json.JSONDecodeError) as error:
            print(json.dumps({"status": "BLOCKED", "reason": str(error)}, ensure_ascii=False))
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    args = _migration_parser().parse_args(arguments)
    try:
        result = migrate(
            args.source,
            args.source_language,
            args.target_language,
            args.function,
            args.cases,
            args.output,
        )
    except (OSError, ValueError, RouteError, RuntimeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "BLOCKED", "reason": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
