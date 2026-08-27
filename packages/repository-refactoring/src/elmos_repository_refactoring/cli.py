"""Command-line entry point.

Exit codes are part of the contract, because this is what CI branches on:

===  ==============================================================
  0  the Skill succeeded
  2  the Skill was rejected (contract violation in the input)
  3  the Skill is blocked (approval required, or evidence missing)
  4  the Skill failed
 64  the command line itself was wrong
===  ==============================================================
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .catalog import PACKAGE_NAME, PACKAGE_VERSION, SKILL_NAMES
from .contracts import (
    ContractError,
    Status,
    canonical_json,
    optional_mapping,
    reject_unknown_fields,
)
from .runtime import describe, dispatch, skill_catalog_payload
from .workspace import WorkspaceSnapshot

_EXIT_CODES = {
    Status.SUCCEEDED.value: 0,
    Status.REJECTED.value: 2,
    Status.BLOCKED.value: 3,
    Status.FAILED.value: 4,
}


def _load_json(path: str | None) -> dict[str, Any] | None:
    if path is None:
        return None
    if path == "-":
        return dict(json.load(sys.stdin))
    text = Path(path).read_text(encoding="utf-8")
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ContractError("invalid_json", f"'{path}' must contain a JSON object")
    return value


def _snapshot_payload(root: Path, revision: str, repository_id: str) -> dict[str, Any]:
    snapshot = WorkspaceSnapshot.from_directory(
        root, repository_id=repository_id, revision=revision
    )
    return {
        "source": "inline",
        "repository_id": snapshot.repository_id,
        "revision": snapshot.revision,
        "files": [
            {"path": record.path, "content": record.text}
            if record.text is not None
            else {
                "path": record.path,
                "content_digest": record.content_digest,
                "size_bytes": record.size_bytes,
                "binary": record.binary,
                "unreadable_reason": record.unreadable_reason,
            }
            for record in snapshot
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="elmos-repository-refactoring",
        description="Deterministic, resumable, auditable repository refactoring runtime.",
    )
    parser.add_argument("--version", action="version", version=f"{PACKAGE_NAME} {PACKAGE_VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="dispatch one Skill")
    run_parser.add_argument("skill", choices=SKILL_NAMES)
    run_parser.add_argument("--payload", help="path to a JSON payload, or '-' for stdin")
    run_parser.add_argument("--trusted-context", help="path to a JSON trusted-context document")
    run_parser.add_argument(
        "--envelope",
        help=(
            "path to a JSON object with 'payload' and 'trustedContext' keys, or '-' for stdin; "
            "one document so a host that pipes input does not have to read stdin twice"
        ),
    )
    run_parser.add_argument("--compact", action="store_true", help="emit canonical single-line JSON")

    sub.add_parser("describe", help="print the runtime description")
    sub.add_parser("catalog", help="print the generated skill catalog")

    snapshot_parser = sub.add_parser("snapshot", help="build an inline workspace payload from a directory")
    snapshot_parser.add_argument("root")
    snapshot_parser.add_argument("--revision", required=True)
    snapshot_parser.add_argument("--repository-id", required=True)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "describe":
            print(json.dumps(describe(), indent=2, ensure_ascii=False))
            return 0
        if args.command == "catalog":
            print(json.dumps(skill_catalog_payload(), indent=2, ensure_ascii=False))
            return 0
        if args.command == "snapshot":
            payload = _snapshot_payload(Path(args.root), args.revision, args.repository_id)
            print(json.dumps({"workspace": payload}, indent=2, ensure_ascii=False))
            return 0
        if args.command == "run":
            payload_document: Mapping[str, Any] | None
            context_document: Mapping[str, Any] | None
            if args.envelope is not None:
                if args.payload is not None or args.trusted_context is not None:
                    raise ContractError(
                        "conflicting_input",
                        "--envelope carries both documents; do not combine it with --payload or "
                        "--trusted-context",
                    )
                envelope = _load_json(args.envelope) or {}
                reject_unknown_fields(envelope, {"payload", "trustedContext"}, "envelope")
                payload_document = optional_mapping(envelope.get("payload"), "envelope.payload")
                context_document = optional_mapping(
                    envelope.get("trustedContext"), "envelope.trustedContext"
                )
            else:
                payload_document = _load_json(args.payload)
                context_document = _load_json(args.trusted_context)
            result = dispatch(
                args.skill,
                payload_document,
                trusted_context=context_document,
            )
            rendered = canonical_json(result) if args.compact else json.dumps(result, indent=2, ensure_ascii=False)
            print(rendered)
            return _EXIT_CODES.get(str(result.get("status")), 4)
    except ContractError as error:
        print(json.dumps({"error": error.to_payload()}, indent=2, ensure_ascii=False), file=sys.stderr)
        return 2
    except (OSError, json.JSONDecodeError) as error:
        print(json.dumps({"error": {"code": "input_unreadable", "message": str(error)}}), file=sys.stderr)
        return 64
    return 64


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
