#!/usr/bin/env python3
"""Validate the Live Workbench source pack as inert data; never run archive code."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path, PurePosixPath

EXPECTED_ARCHIVE_SHA256 = "c7619ce2955b083e39660a159166b6c9b498855203a55b5b8dd3b2cc68d84cfe"
PREFIX = "elmos-live-workbench/"


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, default=Path("skills/subskills/elmos-live-workbench-skills-v1.0.0.zip"))
    parser.add_argument("--mirror", type=Path, default=Path("skills/elmos-live-workbench-skills-v1.0.0/elmos-live-workbench"))
    parser.add_argument("--handler-map", type=Path, default=Path("docs/live-workbench/HANDLER_MAP.json"))
    args = parser.parse_args()
    errors: list[str] = []
    if not args.archive.is_file():
        fail(errors, f"archive missing: {args.archive}")
    elif digest(args.archive.read_bytes()) != EXPECTED_ARCHIVE_SHA256:
        fail(errors, "archive digest mismatch")
    if errors:
        print("\n".join(f"ERROR: {error}" for error in errors), file=sys.stderr)
        return 1
    with zipfile.ZipFile(args.archive) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            fail(errors, "archive has duplicate members")
        for name in names:
            path = PurePosixPath(name)
            if not name.startswith(PREFIX) or path.is_absolute() or ".." in path.parts:
                fail(errors, f"unsafe archive member: {name}")
        try:
            checksums = archive.read(PREFIX + "FILES.sha256").decode().splitlines()
        except KeyError:
            fail(errors, "FILES.sha256 missing")
            checksums = []
        indexed: set[str] = set()
        for line in checksums:
            expected, _, relative = line.partition("  ")
            if len(expected) != 64 or not relative or relative in indexed:
                fail(errors, f"invalid checksum entry: {line}")
                continue
            indexed.add(relative)
            member = PREFIX + relative
            try:
                content = archive.read(member)
            except KeyError:
                fail(errors, f"checksum target missing: {relative}")
                continue
            if digest(content) != expected:
                fail(errors, f"checksum mismatch: {relative}")
            mirror = args.mirror / relative
            if not mirror.is_file() or digest(mirror.read_bytes()) != expected:
                fail(errors, f"immutable mirror mismatch: {relative}")
        manifest = json.loads(archive.read(PREFIX + "manifest.json"))
        expected_skills = {f"LW-{number:02d}" for number in range(1, 29)}
        actual_skills = {item.get("id") for item in manifest.get("skills", [])}
        if manifest.get("name") != "elmos-live-workbench" or manifest.get("version") != "1.0.0":
            fail(errors, "unexpected package identity")
        if manifest.get("external_router_count") != 1 or manifest.get("internal_workflow_count") != 28 or actual_skills != expected_skills:
            fail(errors, "manifest workflow inventory drift")
        if not args.handler_map.is_file():
            fail(errors, f"handler map missing: {args.handler_map}")
        else:
            handler_map = json.loads(args.handler_map.read_text())
            handlers = handler_map.get("handlers", {})
            if handler_map.get("source_archive_sha256") != EXPECTED_ARCHIVE_SHA256 or set(handlers) != {item["name"] for item in manifest["skills"]}:
                fail(errors, "handler map does not exactly cover source skills")
            source = Path("modules/live-workbench/src/main/java/io/elmos/liveworkbench/LiveWorkbenchService.java")
            if not source.is_file():
                fail(errors, "repository-owned workbench service missing")
            else:
                implementation = source.read_text()
                for skill, method in handlers.items():
                    if f" {method}(" not in implementation:
                        fail(errors, f"handler method missing for {skill}: {method}")
            if set(handler_map.get("host_bound_skills", [])) != {"elmos-lw-distributed-coordinated-debug", "elmos-lw-native-device-lab"}:
                fail(errors, "host-bound runtime inventory drift")
        preview = json.loads(archive.read(PREFIX + "examples/preview-session.json"))
        artifact = json.loads(archive.read(PREFIX + "examples/artifact-delivery.json"))
        if preview.get("window_seconds") != 600 or preview.get("client_can_extend") is not False:
            fail(errors, "preview example weakens fixed-window policy")
        if artifact.get("production_credentials_allowed") is not False:
            fail(errors, "artifact example permits production credentials")
    if errors:
        print("\n".join(f"ERROR: {error}" for error in errors), file=sys.stderr)
        return 1
    print(f"OK: live workbench source archive {EXPECTED_ARCHIVE_SHA256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
