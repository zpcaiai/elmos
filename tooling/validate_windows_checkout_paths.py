#!/usr/bin/env python3
"""Validate that a Git checkout is representable and readable on Windows.

This is an engineering checkout check only.  It does not execute, validate, or
certify any language runtime on Windows.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import unicodedata
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

SCHEMA_VERSION = "1.0.0"
KIND = "elmos.windows-checkout-path-inventory"
SCOPE = "CHECKOUT_AND_TRACKED_PATH_ACCESS_ONLY"
WINDOWS_RUNTIME_STATUS = "NOT_RUN"
CERTIFICATION_STATUS = "NOT_CERTIFIED"
WINDOWS_RESERVED_COMPONENT = re.compile(
    r"^(?:CON|PRN|AUX|NUL|CLOCK\$|COM[1-9]|LPT[1-9])(?:\..*)?$",
    re.IGNORECASE,
)
WINDOWS_INVALID_CHARACTERS = frozenset('<>:"\\|?*')
MAX_NTFS_COMPONENT_UTF16_UNITS = 255
MAX_EXTENDED_WINDOWS_PATH_UTF16_UNITS = 32_767


def utf16_units(value: str) -> int:
    """Return the length Windows path APIs use for a Unicode string."""

    return len(value.encode("utf-16-le")) // 2


def canonical_windows_key(path: str) -> str:
    """Approximate the default case-insensitive NTFS identity of a Git path."""

    return unicodedata.normalize("NFC", path).casefold()


def audit_path_names(paths: Iterable[str]) -> list[str]:
    """Return deterministic Windows-name and collision findings."""

    findings: list[str] = []
    seen: dict[str, str] = {}
    for path in paths:
        pure_path = PurePosixPath(path)
        if not path or path.startswith("/") or pure_path.is_absolute():
            findings.append(f"absolute or empty tracked path: {path!r}")
            continue
        if pure_path.parts in {(), (".",)} or any(
            part in {"", ".", ".."} for part in pure_path.parts
        ):
            findings.append(f"non-canonical tracked path: {path!r}")
            continue

        key = canonical_windows_key(path)
        previous = seen.setdefault(key, path)
        if previous != path:
            findings.append(
                f"case or Unicode-normalization collision: {previous!r} and {path!r}"
            )

        for component in pure_path.parts:
            if component.endswith((" ", ".")):
                findings.append(f"component ends in a space or period: {path!r}")
                break
            if WINDOWS_RESERVED_COMPONENT.fullmatch(component):
                findings.append(f"reserved Windows component {component!r}: {path!r}")
                break
            if any(
                character in WINDOWS_INVALID_CHARACTERS or ord(character) < 32
                for character in component
            ):
                findings.append(
                    f"invalid Windows character in component {component!r}: {path!r}"
                )
                break
            if utf16_units(component) > MAX_NTFS_COMPONENT_UTF16_UNITS:
                findings.append(
                    f"component exceeds {MAX_NTFS_COMPONENT_UTF16_UNITS} UTF-16 units: {path!r}"
                )
                break
    return sorted(set(findings))


def inventory_digest(paths: Iterable[str]) -> str:
    """Bind the ordered tracked-path inventory without depending on line endings."""

    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def run_git(
    root: Path, *arguments: str, check: bool = True
) -> subprocess.CompletedProcess[bytes]:
    # Every caller supplies a fixed Git subcommand; tracked repository content
    # is data returned by Git and never becomes a subprocess argument.
    return subprocess.run(  # noqa: S603
        ("git", *arguments),
        cwd=root,
        check=check,
        capture_output=True,
    )


def tracked_paths(root: Path) -> list[str]:
    result = run_git(root, "ls-files", "-z")
    raw_paths = result.stdout.split(b"\0")
    if raw_paths and raw_paths[-1] == b"":
        raw_paths.pop()
    paths = [raw_path.decode("utf-8", errors="strict") for raw_path in raw_paths]
    if not paths:
        raise ValueError("tracked path inventory is empty")
    if len(paths) != len(set(paths)):
        raise ValueError("tracked path inventory contains duplicate entries")
    return paths


def git_longpaths_enabled(root: Path) -> bool:
    result = run_git(
        root, "config", "--global", "--bool", "core.longpaths", check=False
    )
    return result.returncode == 0 and result.stdout.strip().lower() == b"true"


def worktree_is_clean(root: Path) -> bool:
    result = run_git(root, "status", "--porcelain=v1", "-z", "--untracked-files=no")
    return not result.stdout


def validate_checkout(
    root: Path,
    *,
    relative_length_threshold: int,
    require_git_longpaths: bool,
    require_clean: bool,
) -> dict[str, object]:
    root = root.resolve(strict=True)
    paths = tracked_paths(root)
    findings = audit_path_names(paths)
    long_paths: list[str] = []
    missing_paths: list[str] = []
    unreadable_paths: list[str] = []
    extended_limit_paths: list[str] = []

    for path in paths:
        candidate = root.joinpath(*PurePosixPath(path).parts)
        if not os.path.lexists(candidate):
            missing_paths.append(path)
            continue
        if utf16_units(str(candidate)) >= MAX_EXTENDED_WINDOWS_PATH_UTF16_UNITS:
            extended_limit_paths.append(path)
        if utf16_units(path) >= relative_length_threshold:
            long_paths.append(path)
            try:
                if candidate.is_file():
                    with candidate.open("rb") as tracked_file:
                        tracked_file.read(1)
            except OSError as error:
                unreadable_paths.append(f"{path}: {error}")

    longpaths_enabled = git_longpaths_enabled(root)
    clean = worktree_is_clean(root)
    if require_git_longpaths and not longpaths_enabled:
        findings.append("Git core.longpaths is not enabled globally")
    if require_clean and not clean:
        findings.append("tracked checkout is not clean after checkout")
    if not long_paths:
        findings.append(
            f"no tracked path reaches the required {relative_length_threshold} UTF-16-unit threshold"
        )
    findings.extend(
        f"tracked path is missing after checkout: {path}" for path in missing_paths[:20]
    )
    findings.extend(
        f"tracked path is unreadable: {path}" for path in unreadable_paths[:20]
    )
    findings.extend(
        f"tracked path exceeds the extended Windows path ceiling: {path}"
        for path in extended_limit_paths[:20]
    )
    if findings:
        raise ValueError("\n".join(sorted(set(findings))))

    longest = max(paths, key=lambda path: (utf16_units(path), path))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "scope": SCOPE,
        "status": "PASSED",
        "host_platform": platform.system(),
        "tracked_path_count": len(paths),
        "inventory_sha256": inventory_digest(paths),
        "git_core_longpaths": longpaths_enabled,
        "tracked_worktree_clean": clean,
        "required_relative_length_utf16_units": relative_length_threshold,
        "long_relative_path_count": len(long_paths),
        "max_relative_path_utf16_units": utf16_units(longest),
        "max_relative_path": longest,
        "windows_runtime_status": WINDOWS_RUNTIME_STATUS,
        "external_certification_status": "NOT_RUN",
        "certification_status": CERTIFICATION_STATUS,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-relative-length", type=int, default=260)
    parser.add_argument("--require-git-longpaths", action="store_true")
    parser.add_argument("--require-clean", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.require_relative_length < 1:
        print("--require-relative-length must be positive", file=sys.stderr)
        return 2
    try:
        report = validate_checkout(
            args.root,
            relative_length_threshold=args.require_relative_length,
            require_git_longpaths=args.require_git_longpaths,
            require_clean=args.require_clean,
        )
    except (OSError, subprocess.CalledProcessError, UnicodeError, ValueError) as error:
        print(f"Windows checkout path inventory BLOCKED: {error}", file=sys.stderr)
        return 1

    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
