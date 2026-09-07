"""Dependency-free JSON CLI for the bounded Project Intelligence runtime."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any

from .export_cli import (
    render_pptx_command,
    render_report_command,
    render_svg_command,
)
from .runtime import SkillRuntimeError, capability_manifest, dispatch_skill
from .safe_paths import open_file_no_symlinks, verify_file_path_binding


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
        if not hasattr(os, "O_NOFOLLOW"):
            raise ValueError("request files require O_NOFOLLOW support")
        path, parent_fd, descriptor = open_file_no_symlinks(
            Path(path_value), os.O_RDONLY
        )
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise ValueError("request path must be a regular file")
            if before.st_size > MAX_REQUEST_BYTES:
                raise ValueError("request exceeds 16 MiB")
            captured = bytearray()
            while len(captured) <= MAX_REQUEST_BYTES:
                chunk = os.read(
                    descriptor,
                    min(64 * 1024, MAX_REQUEST_BYTES + 1 - len(captured)),
                )
                if not chunk:
                    break
                captured.extend(chunk)
            after = os.fstat(descriptor)
            stable_before = (
                before.st_dev,
                before.st_ino,
                before.st_mode,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
            stable_after = (
                after.st_dev,
                after.st_ino,
                after.st_mode,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            )
            if stable_before != stable_after or len(captured) != before.st_size:
                raise ValueError("request file changed while it was read")
            verify_file_path_binding(
                path,
                parent_fd=parent_fd,
                file_fd=descriptor,
            )
            raw = bytes(captured)
        finally:
            os.close(descriptor)
            os.close(parent_fd)
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


def _export(args: argparse.Namespace) -> dict[str, Any]:
    """Run one offline export.

    Exports read a handler result that dispatch already produced and write one
    file.  They never call ``dispatch_skill``, so no contract-pinned handler
    output is widened and no filesystem write happens under the dispatch-time
    audit guard.
    """

    documents = [_read_request(item) for item in (args.spec or [])]
    if args.command == "render-svg":
        return render_svg_command(documents, args.output)
    if args.command == "report":
        return render_report_command(documents, args.output, title=args.title)
    manifest = _read_request(args.manifest) if args.manifest else None
    return render_pptx_command(documents, manifest, args.output, title=args.title)


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
    render = subcommands.add_parser(
        "render-svg", help="render one compiled Diagram Spec to deterministic SVG"
    )
    render.add_argument("--spec", action="append", required=True)
    render.add_argument("--output", required=True)
    report = subcommands.add_parser(
        "report", help="render Diagram Specs into one static HTML report"
    )
    report.add_argument("--spec", action="append", required=True)
    report.add_argument("--output", required=True)
    report.add_argument("--title", default="Project Intelligence report")
    presentation = subcommands.add_parser(
        "pptx", help="write a real PPTX with vector diagram slides"
    )
    presentation.add_argument("--spec", action="append", default=[])
    presentation.add_argument("--manifest", default=None)
    presentation.add_argument("--output", required=True)
    presentation.add_argument("--title", default="Project Intelligence")
    args = parser.parse_args(argv)
    try:
        if args.command == "manifest":
            result = capability_manifest()
        elif args.command == "dispatch":
            result = dispatch_skill(args.skill, _read_request(args.request))
        else:
            result = _export(args)
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
