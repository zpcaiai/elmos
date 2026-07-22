from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from .intake import approve_request, create_draft
from .models import RequestValidationError
from .verification import verify_workspace
from .workspace import WorkspaceConflictError, generate_workspace


def _read_json(path: Path) -> dict[str, Any]:
    if path.stat().st_size > 1_048_576:
        raise ValueError("REQUEST_FILE_TOO_LARGE")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("JSON_OBJECT_REQUIRED")
    return loaded


def _write_json(path: Path, value: dict[str, Any]) -> None:
    output = path.expanduser()
    if output.exists() and (output.is_symlink() or not output.is_file()):
        raise ValueError("OUTPUT_MUST_BE_REGULAR_FILE")
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.elmos-",
        suffix=".tmp",
        dir=output.parent,
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="elmos-project-synthesis")
    subparsers = parser.add_subparsers(dest="command", required=True)

    draft = subparsers.add_parser("draft", help="Organize an initial natural-language request into a reviewable draft")
    draft.add_argument("--name", required=True)
    draft.add_argument("--description", required=True)
    draft.add_argument("--entity")
    draft.add_argument("--namespace")
    draft.add_argument("--language", action="append", choices=["java", "python", "csharp"])
    draft.add_argument("--output", type=Path, required=True)

    approve = subparsers.add_parser("approve", help="Hash-bind a reviewed requirement baseline")
    approve.add_argument("--request", type=Path, required=True)
    approve.add_argument("--actor", required=True)
    approve.add_argument("--output", type=Path, required=True)

    generate = subparsers.add_parser("generate", help="Generate projects from an approved requirement baseline")
    generate.add_argument("--request", type=Path, required=True)
    generate.add_argument("--output", type=Path, required=True)

    verify = subparsers.add_parser("verify", help="Run real target builds and tests")
    verify.add_argument("--workspace", type=Path, required=True)
    verify.add_argument("--evidence", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "draft":
            result = create_draft(
                name=args.name,
                description=args.description,
                entity=args.entity,
                namespace=args.namespace,
                languages=args.language or ("java", "python", "csharp"),
            )
            _write_json(args.output, result)
        elif args.command == "approve":
            result = approve_request(_read_json(args.request), actor=args.actor)
            _write_json(args.output, result)
        elif args.command == "generate":
            result = generate_workspace(_read_json(args.request), args.output)
        else:
            result = verify_workspace(args.workspace)
            if args.evidence:
                _write_json(args.evidence, result)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if result.get("status") != "FAILED" else 1
    except (
        OSError,
        ValueError,
        RequestValidationError,
        WorkspaceConflictError,
        RuntimeError,
        json.JSONDecodeError,
    ) as error:
        print(json.dumps({"status": "BLOCKED", "reason": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
