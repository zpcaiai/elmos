"""Dependency-free JSON CLI for the bounded Project Intelligence runtime."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from .runtime import SkillRuntimeError, capability_manifest, dispatch_skill


MAX_REQUEST_BYTES = 16 * 1024 * 1024


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _read_request(path_value: str) -> dict[str, Any]:
    if path_value == "-":
        raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
    else:
        path = Path(path_value)
        if not path.is_file() or path.is_symlink():
            raise ValueError("request path must be a regular file")
        if path.stat().st_size > MAX_REQUEST_BYTES:
            raise ValueError("request exceeds 16 MiB")
        raw = path.read_bytes()
    if len(raw) > MAX_REQUEST_BYTES:
        raise ValueError("request exceeds 16 MiB")
    value = json.loads(
        raw.decode("utf-8", errors="strict"),
        object_pairs_hook=_reject_duplicate_pairs,
        parse_constant=lambda token: (_ for _ in ()).throw(
            ValueError(f"non-finite JSON value: {token}")
        ),
    )
    if not isinstance(value, dict):
        raise ValueError("request must be a JSON object")
    return value


def _write_json(value: Any) -> None:
    sys.stdout.write(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("manifest", help="print the exact 50-Skill binding manifest")
    dispatch = subcommands.add_parser(
        "dispatch", help="execute one bounded local handler"
    )
    dispatch.add_argument("--skill", required=True)
    dispatch.add_argument(
        "--request", default="-", help="JSON request file or - for stdin"
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "manifest":
            result = capability_manifest()
        else:
            result = dispatch_skill(args.skill, _read_request(args.request))
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        ValueError,
        SkillRuntimeError,
    ):
        _write_json(
            {
                "state": "BLOCKED",
                "code": "CLI_REQUEST_REJECTED",
                "error": {
                    "type": "REQUEST_REJECTED",
                    "message": "CLI request rejected",
                },
                "external_effects_performed": False,
                "external_evidence": "NOT_RUN",
                "certification": "NOT_CERTIFIED",
            }
        )
        return 2
    _write_json(result)
    return 0 if result.get("state") != "BLOCKED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
