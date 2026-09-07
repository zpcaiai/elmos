from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .runtime import HANDLERS, RuntimeScope, SkillRuntimeError, invoke


def _load_object(path: str | None, *, stdin: bool = False) -> dict[str, Any]:
    try:
        if stdin:
            value = json.load(sys.stdin)
        elif path:
            value = json.loads(Path(path).read_text(encoding="utf-8"))
        else:
            raise SkillRuntimeError("JSON path is required")
    except (OSError, json.JSONDecodeError) as exc:
        raise SkillRuntimeError(f"cannot read JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise SkillRuntimeError("JSON document must be an object")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="elmos-repository-orchestrator")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list")
    invoke_parser = subparsers.add_parser("invoke")
    invoke_parser.add_argument("skill", choices=sorted(HANDLERS))
    invoke_parser.add_argument("--scope-json", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "list":
            print(json.dumps({"skills": sorted(HANDLERS)}, indent=2))
            return 0
        scope_data = _load_object(args.scope_json)
        scope = RuntimeScope(**scope_data)
        result = invoke(args.skill, _load_object(None, stdin=True), scope)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (SkillRuntimeError, TypeError) as exc:
        print(json.dumps({"error": str(exc), "code": "REQUEST_REJECTED"}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
