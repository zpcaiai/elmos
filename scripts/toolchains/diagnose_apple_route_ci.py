#!/usr/bin/env python3
"""Emit bounded, read-only identity records for the hosted Apple route toolchain.

This program deliberately diagnoses the live installation rather than comparing it
with the legacy pins in ``scripts/batch29/validate_route.py``.  It imports that
repository-owned module from bytes read with no-follow/stability checks, maps its
Swift component and tree specifications onto the Xcode installation selected by
``xcode-select``, and emits deterministic JSON Lines records.  The output is input
for review and pin updates; it is not route certification evidence by itself.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import types
from pathlib import Path
from typing import Iterable, Mapping


SCHEMA = "elmos-apple-route-ci-diagnostic-v1"
MAX_VALIDATOR_BYTES = 2_000_000
MAX_COMPONENT_BYTES = 400_000_000
MAX_TREE_ENTRIES = 10_000
MAX_TREE_BYTES = 1_000_000_000
MAX_COMMAND_OUTPUT_BYTES = 1_000_000
MAX_DIAGNOSTIC_OUTPUT_BYTES = 10_000_000
EXPECTED_IMAGE_OS = "macos26"
EXPECTED_IMAGE_VERSION = "20260728.0273.1"
EXPECTED_PRODUCT_VERSION = "26.5.2"
EXPECTED_BUILD_VERSION = "25F84"
EXPECTED_HOST_PROFILES = {
    EXPECTED_IMAGE_VERSION: (EXPECTED_PRODUCT_VERSION, EXPECTED_BUILD_VERSION),
    "20260831.0337.3": ("26.6.2", "25G83"),
}
HOSTED_SOURCE_XCODE_APP = Path("/Applications/Xcode_26.6.app")
EXPECTED_XCODE_APP = Path("/Applications/Xcode.app")
EXPECTED_XCODE_VERSION = "Xcode 26.6\nBuild version 17F113\n"
EXPECTED_SDK_ALIAS_NAME = "MacOSX26.5.sdk"
EXPECTED_SDK_ALIAS_TARGET = "MacOSX.sdk"
EXPECTED_COMPONENT_COUNT = 28
EXPECTED_TREE_COUNT = 13
EXPECTED_KIND_COUNTS = {
    "environment": 1,
    "xcode_source_normalization": 1,
    "xcode_physical": 1,
    "sdk_selected": 1,
    "sdk_spec_alias": 1,
    "swift_component": EXPECTED_COMPONENT_COUNT,
    "swift_tree": EXPECTED_TREE_COUNT,
    "apple_git": 1,
    "system_tool": 2,
    "compiler_tool": 3,
    "network_probe": 1,
}
SYSTEM_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
_UNSET = object()


class DiagnosticError(RuntimeError):
    """Raised when a live path is unsafe, unreadable, or changes during capture."""


def _expected_host_versions(image_version: object) -> tuple[str, str]:
    if not isinstance(image_version, str):
        raise DiagnosticError("Apple route image version is invalid")
    expected = EXPECTED_HOST_PROFILES.get(image_version)
    if expected is None:
        raise DiagnosticError("Apple route image version is not allowlisted")
    return expected


def _identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _stable_read_regular_file(
    path: Path,
    *,
    maximum_bytes: int,
    allowed_uids: frozenset[int],
    require_single_link: bool,
) -> tuple[bytes, os.stat_result]:
    if not hasattr(os, "O_NOFOLLOW"):
        raise DiagnosticError("O_NOFOLLOW is required")
    before = path.lstat()
    if stat.S_ISLNK(before.st_mode):
        raise DiagnosticError(f"refusing to follow file symlink: {path}")
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_size < 0
        or before.st_size > maximum_bytes
        or before.st_uid not in allowed_uids
        or stat.S_IMODE(before.st_mode) & 0o022
        or (require_single_link and before.st_nlink != 1)
    ):
        raise DiagnosticError(f"unsafe file metadata: {path}")
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | os.O_NOFOLLOW,
    )
    try:
        opened_before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened_before.st_mode)
            or opened_before.st_size < 0
            or opened_before.st_size > maximum_bytes
            or opened_before.st_uid not in allowed_uids
            or stat.S_IMODE(opened_before.st_mode) & 0o022
            or (require_single_link and opened_before.st_nlink != 1)
        ):
            raise DiagnosticError(f"unsafe opened file metadata: {path}")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > maximum_bytes:
                raise DiagnosticError(f"file exceeds bounded read limit: {path}")
            chunks.append(chunk)
        opened_after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    after = path.lstat()
    expected_identity = _identity(before)
    if any(
        _identity(observed) != expected_identity
        for observed in (opened_before, opened_after, after)
    ):
        raise DiagnosticError(f"file changed while read: {path}")
    content = b"".join(chunks)
    if (
        not stat.S_ISREG(after.st_mode)
        or after.st_uid not in allowed_uids
        or stat.S_IMODE(after.st_mode) & 0o022
        or (require_single_link and after.st_nlink != 1)
        or len(content) != after.st_size
    ):
        raise DiagnosticError(f"unsafe file metadata: {path}")
    return content, after


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _load_validator(repository_root: Path) -> tuple[types.ModuleType, str]:
    root = repository_root.resolve(strict=True)
    path = root / "scripts/batch29/validate_route.py"
    if path.resolve(strict=True) != path or not path.is_relative_to(root):
        raise DiagnosticError("validator path is not an exact repository file")
    allowed_uids = frozenset({0, os.getuid()})
    content_before, metadata_before = _stable_read_regular_file(
        path,
        maximum_bytes=MAX_VALIDATOR_BYTES,
        allowed_uids=allowed_uids,
        require_single_link=True,
    )
    module = types.ModuleType("elmos_live_batch29_validate_route")
    module.__file__ = str(path)
    module.__package__ = None
    exec(compile(content_before, str(path), "exec"), module.__dict__)
    content_after, metadata_after = _stable_read_regular_file(
        path,
        maximum_bytes=MAX_VALIDATOR_BYTES,
        allowed_uids=allowed_uids,
        require_single_link=True,
    )
    if content_before != content_after or _identity(metadata_before) != _identity(
        metadata_after
    ):
        raise DiagnosticError("validator changed while imported")
    return module, "sha256:" + hashlib.sha256(content_after).hexdigest()


def _run(
    argv: list[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    timeout: int = 60,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=dict(environment),
        check=False,
        capture_output=True,
        text=True,
        input=input_text,
        timeout=timeout,
    )
    output_bytes = len(completed.stdout.encode("utf-8")) + len(
        completed.stderr.encode("utf-8")
    )
    if output_bytes > MAX_COMMAND_OUTPUT_BYTES:
        raise DiagnosticError(f"command output exceeds bound: {argv[0]}")
    return completed


def _run_exact(
    argv: list[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    completed = _run(argv, cwd=cwd, environment=environment, timeout=timeout)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-500:]
        raise DiagnosticError(f"command failed ({argv[0]}): {detail}")
    return completed


def _directory_identity(
    path: Path, metadata: os.stat_result | None = None
) -> tuple[object, ...]:
    if metadata is None:
        metadata = path.lstat()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != 0
    ):
        raise DiagnosticError(f"unsafe directory in Xcode chain: {path}")
    if metadata.st_gid != 0 or stat.S_IMODE(metadata.st_mode) & 0o022:
        raise DiagnosticError(f"writable directory in Xcode chain: {path}")
    return (
        str(path),
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _xcode_directory_chain(path: Path) -> tuple[tuple[object, ...], ...]:
    if not path.is_absolute() or not path.is_relative_to(Path("/Applications")):
        raise DiagnosticError(f"Xcode path is outside /Applications: {path}")
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise DiagnosticError("no-follow Xcode directory traversal is required")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | os.O_DIRECTORY
        | os.O_NOFOLLOW
    )
    cursor = Path("/Applications")
    lexical_root = cursor.lstat()
    descriptor = os.open(cursor, flags)
    try:
        opened_root = os.fstat(descriptor)
        if _identity(opened_root) != _identity(lexical_root):
            raise DiagnosticError("/Applications changed while opened")
        root_device = opened_root.st_dev
        identities = [_directory_identity(cursor, opened_root)]
        for part in path.relative_to(cursor).parts:
            lexical_child = os.stat(part, dir_fd=descriptor, follow_symlinks=False)
            child_descriptor = os.open(part, flags, dir_fd=descriptor)
            try:
                opened_child = os.fstat(child_descriptor)
                if (
                    _identity(opened_child) != _identity(lexical_child)
                    or opened_child.st_dev != root_device
                ):
                    raise DiagnosticError(
                        f"Xcode directory changed or crossed a mount: {cursor / part}"
                    )
            except BaseException:
                os.close(child_descriptor)
                raise
            os.close(descriptor)
            descriptor = child_descriptor
            cursor = cursor / part
            identities.append(_directory_identity(cursor, opened_child))
    finally:
        os.close(descriptor)
    if path.resolve(strict=True) != path:
        raise DiagnosticError(f"physical Xcode directory resolves elsewhere: {path}")
    return tuple(identities)


def _path_identity(path: Path) -> dict[str, object]:
    metadata_before = path.lstat()
    link_target_before = (
        os.readlink(path) if stat.S_ISLNK(metadata_before.st_mode) else None
    )
    resolved = path.resolve(strict=True)
    metadata_after = path.lstat()
    link_target_after = (
        os.readlink(path) if stat.S_ISLNK(metadata_after.st_mode) else None
    )
    if (
        _identity(metadata_before) != _identity(metadata_after)
        or link_target_before != link_target_after
        or path.resolve(strict=True) != resolved
    ):
        raise DiagnosticError(f"path identity changed during capture: {path}")
    return {
        "lexical": str(path),
        "link_target": link_target_before,
        "resolved": str(resolved),
        "type": (
            "symlink"
            if stat.S_ISLNK(metadata_after.st_mode)
            else "directory"
            if stat.S_ISDIR(metadata_after.st_mode)
            else "regular"
            if stat.S_ISREG(metadata_after.st_mode)
            else "other"
        ),
        "mode": f"{stat.S_IMODE(metadata_after.st_mode):04o}",
        "uid": metadata_after.st_uid,
        "gid": metadata_after.st_gid,
        "nlink": metadata_after.st_nlink,
        "device": metadata_after.st_dev,
        "inode": metadata_after.st_ino,
        "bytes": metadata_after.st_size,
        "mtime_ns": metadata_after.st_mtime_ns,
        "ctime_ns": metadata_after.st_ctime_ns,
    }


def _map_spec_path(
    spec_path: str,
    *,
    spec_contents_root: Path,
    physical_contents_root: Path,
) -> Path:
    lexical = Path(spec_path)
    if not lexical.is_absolute() or not lexical.is_relative_to(spec_contents_root):
        raise DiagnosticError(f"Swift specification escapes Xcode root: {spec_path}")
    mapped = physical_contents_root / lexical.relative_to(spec_contents_root)
    if not mapped.is_relative_to(physical_contents_root):
        raise DiagnosticError(f"mapped Swift path escapes Xcode root: {spec_path}")
    return mapped


def _exact_relative_directory_alias(
    alias: Path,
    *,
    expected_target_name: str,
    expected_resolved: Path,
) -> tuple[dict[str, object], dict[str, object]]:
    identity = _path_identity(alias)
    target_identity = _path_identity(expected_resolved)
    if (
        identity["type"] != "symlink"
        or identity["link_target"] != expected_target_name
        or identity["uid"] != 0
        or identity["gid"] != 0
        or int(str(identity["mode"]), 8) & 0o022
        or Path(str(identity["resolved"])) != expected_resolved
        or expected_resolved != alias.parent / expected_target_name
        or target_identity["type"] != "directory"
        or target_identity["link_target"] is not None
        or target_identity["uid"] != 0
        or target_identity["gid"] != 0
        or int(str(target_identity["mode"]), 8) & 0o022
    ):
        raise DiagnosticError(f"unsafe exact directory alias: {alias}")
    return identity, target_identity


def _component_receipt(
    *,
    role: str,
    lexical: Path,
    physical_contents_root: Path,
) -> dict[str, object]:
    lexical_before = lexical.lstat()
    link_target = (
        os.readlink(lexical) if stat.S_ISLNK(lexical_before.st_mode) else None
    )
    if link_target is not None and (
        Path(link_target).is_absolute() or ".." in Path(link_target).parts
    ):
        raise DiagnosticError(f"unsafe component symlink: {role}")
    if (
        lexical_before.st_uid != 0
        or lexical_before.st_gid != 0
        or stat.S_IMODE(lexical_before.st_mode) & 0o022
        or not (stat.S_ISLNK(lexical_before.st_mode) or stat.S_ISREG(lexical_before.st_mode))
    ):
        raise DiagnosticError(f"unsafe component lexical metadata: {role}")
    resolved = lexical.resolve(strict=True)
    if not resolved.is_relative_to(physical_contents_root):
        raise DiagnosticError(f"component resolves outside Xcode root: {role}")
    parent_before = _xcode_directory_chain(resolved.parent)
    content, metadata = _stable_read_regular_file(
        resolved,
        maximum_bytes=MAX_COMPONENT_BYTES,
        allowed_uids=frozenset({0}),
        require_single_link=False,
    )
    if metadata.st_gid != 0:
        raise DiagnosticError(f"unsafe component resolved group: {role}")
    lexical_after = lexical.lstat()
    if _identity(lexical_before) != _identity(lexical_after) or (
        os.readlink(lexical) if stat.S_ISLNK(lexical_after.st_mode) else None
    ) != link_target:
        raise DiagnosticError(f"component lexical identity changed: {role}")
    if (
        lexical.resolve(strict=True) != resolved
        or _xcode_directory_chain(resolved.parent) != parent_before
    ):
        raise DiagnosticError(f"component parent chain changed: {role}")
    return {
        "kind": "swift_component",
        "role": role,
        "lexical": str(lexical),
        "link_target": link_target,
        "lexical_identity": {
            "type": "symlink" if stat.S_ISLNK(lexical_before.st_mode) else "regular",
            "link_target": link_target,
            "mode": f"{stat.S_IMODE(lexical_before.st_mode):04o}",
            "uid": lexical_before.st_uid,
            "gid": lexical_before.st_gid,
            "nlink": lexical_before.st_nlink,
            "device": lexical_before.st_dev,
            "inode": lexical_before.st_ino,
            "bytes": lexical_before.st_size,
            "mtime_ns": lexical_before.st_mtime_ns,
            "ctime_ns": lexical_before.st_ctime_ns,
        },
        "resolved": str(resolved),
        "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
        "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
        "uid": metadata.st_uid,
        "gid": metadata.st_gid,
        "nlink": metadata.st_nlink,
    }


def _discover_tree(
    root: Path,
    *,
    allowed_uids: frozenset[int],
    allowed_gids: frozenset[int],
) -> tuple[list[Path], dict[str, tuple[int, ...]]]:
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise DiagnosticError("no-follow directory traversal is required")
    root_before = root.lstat()
    if (
        stat.S_ISLNK(root_before.st_mode)
        or not stat.S_ISDIR(root_before.st_mode)
        or root_before.st_uid not in allowed_uids
        or root_before.st_gid not in allowed_gids
        or stat.S_IMODE(root_before.st_mode) & 0o022
    ):
        raise DiagnosticError(f"unsafe tree root metadata: {root}")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | os.O_DIRECTORY
        | os.O_NOFOLLOW
    )
    root_descriptor = os.open(root, flags)
    stack: list[tuple[int, Path]] = [(root_descriptor, Path("."))]
    files: list[Path] = []
    identities: dict[str, tuple[int, ...]] = {}
    try:
        if _identity(os.fstat(root_descriptor)) != _identity(root_before):
            raise DiagnosticError(f"tree root changed while opened: {root}")
        root_device = root_before.st_dev
        while stack:
            directory_descriptor, relative_directory = stack.pop()
            try:
                directory_metadata = os.fstat(directory_descriptor)
                if (
                    not stat.S_ISDIR(directory_metadata.st_mode)
                    or directory_metadata.st_dev != root_device
                ):
                    raise DiagnosticError(f"tree crosses device boundary: {root}")
                with os.scandir(directory_descriptor) as scanner:
                    names = sorted(entry.name for entry in scanner)
                for name in names:
                    metadata = os.stat(
                        name,
                        dir_fd=directory_descriptor,
                        follow_symlinks=False,
                    )
                    relative = relative_directory / name
                    relative_text = relative.as_posix()
                    if (
                        metadata.st_dev != root_device
                        or stat.S_ISLNK(metadata.st_mode)
                        or metadata.st_uid not in allowed_uids
                        or metadata.st_gid not in allowed_gids
                        or stat.S_IMODE(metadata.st_mode) & 0o022
                        or not (
                            stat.S_ISDIR(metadata.st_mode)
                            or stat.S_ISREG(metadata.st_mode)
                        )
                    ):
                        raise DiagnosticError(f"unsafe tree entry: {root / relative}")
                    identities[relative_text] = _identity(metadata)
                    if len(identities) > MAX_TREE_ENTRIES:
                        raise DiagnosticError(f"tree exceeds entry bound: {root}")
                    if stat.S_ISDIR(metadata.st_mode):
                        child_descriptor = os.open(
                            name,
                            flags,
                            dir_fd=directory_descriptor,
                        )
                        try:
                            if _identity(os.fstat(child_descriptor)) != _identity(
                                metadata
                            ):
                                raise DiagnosticError(
                                    f"tree directory changed while opened: {root / relative}"
                                )
                        except BaseException:
                            os.close(child_descriptor)
                            raise
                        stack.append((child_descriptor, relative))
                    else:
                        files.append(root / relative)
            finally:
                os.close(directory_descriptor)
    finally:
        for pending_descriptor, _relative in stack:
            os.close(pending_descriptor)
    root_after = root.lstat()
    if _identity(root_after) != _identity(root_before) or root.resolve(strict=True) != root:
        raise DiagnosticError(f"tree root changed during traversal: {root}")
    files.sort(key=lambda item: item.relative_to(root).as_posix())
    return files, identities


def _tree_receipt(
    *,
    role: str,
    lexical: Path,
    physical_contents_root: Path,
    allowed_uids: frozenset[int] | None = None,
    allowed_gids: frozenset[int] | None = None,
) -> dict[str, object]:
    if allowed_uids is None:
        allowed_uids = frozenset({0})
    if allowed_gids is None:
        allowed_gids = frozenset({0})
    lexical_metadata_before = lexical.lstat()
    link_target = (
        os.readlink(lexical)
        if stat.S_ISLNK(lexical_metadata_before.st_mode)
        else None
    )
    if link_target is not None and (
        Path(link_target).is_absolute() or ".." in Path(link_target).parts
    ):
        raise DiagnosticError(f"unsafe tree root symlink: {role}")
    if (
        lexical_metadata_before.st_uid not in allowed_uids
        or lexical_metadata_before.st_gid not in allowed_gids
        or stat.S_IMODE(lexical_metadata_before.st_mode) & 0o022
    ):
        raise DiagnosticError(f"unsafe tree root metadata: {role}")
    resolved = lexical.resolve(strict=True)
    if not resolved.is_relative_to(physical_contents_root) or not resolved.is_dir():
        raise DiagnosticError(f"tree resolves outside Xcode root: {role}")
    root_chain_before = _xcode_directory_chain(resolved)
    paths, inventory_before = _discover_tree(
        resolved,
        allowed_uids=allowed_uids,
        allowed_gids=allowed_gids,
    )
    file_records: list[dict[str, object]] = []
    total_bytes = 0
    for path in paths:
        remaining = MAX_TREE_BYTES - total_bytes
        if remaining <= 0:
            raise DiagnosticError(f"tree exceeds byte bound: {role}")
        content, _metadata = _stable_read_regular_file(
            path,
            maximum_bytes=remaining,
            allowed_uids=allowed_uids,
            require_single_link=False,
        )
        total_bytes += len(content)
        file_records.append(
            {
                "path": path.relative_to(resolved).as_posix(),
                "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
                "bytes": len(content),
            }
        )
    second_paths, inventory_after = _discover_tree(
        resolved,
        allowed_uids=allowed_uids,
        allowed_gids=allowed_gids,
    )
    if (
        [path.relative_to(resolved).as_posix() for path in second_paths]
        != [record["path"] for record in file_records]
        or inventory_after != inventory_before
    ):
        raise DiagnosticError(f"tree changed while read: {role}")
    for path, record in zip(second_paths, file_records, strict=True):
        record_bytes = record.get("bytes")
        if not isinstance(record_bytes, int) or record_bytes < 0:
            raise DiagnosticError(f"tree record byte count is invalid: {role}")
        content, metadata = _stable_read_regular_file(
            path,
            maximum_bytes=record_bytes,
            allowed_uids=allowed_uids,
            require_single_link=False,
        )
        relative = path.relative_to(resolved).as_posix()
        if (
            inventory_after.get(relative) != _identity(metadata)
            or record["bytes"] != len(content)
            or record["sha256"]
            != "sha256:" + hashlib.sha256(content).hexdigest()
        ):
            raise DiagnosticError(f"tree content changed while read: {role}")
    lexical_metadata_after = lexical.lstat()
    if (
        _identity(lexical_metadata_before) != _identity(lexical_metadata_after)
        or _xcode_directory_chain(resolved) != root_chain_before
        or (
            os.readlink(lexical)
            if stat.S_ISLNK(lexical_metadata_after.st_mode)
            else None
        )
        != link_target
    ):
        raise DiagnosticError(f"tree root changed while read: {role}")
    return {
        "kind": "swift_tree",
        "role": role,
        "lexical": str(lexical),
        "link_target": link_target,
        "resolved": str(resolved),
        "sha256": _canonical_sha256({"files": file_records}),
        "file_count": len(file_records),
        "bytes": total_bytes,
    }


def _system_directory_chain(directory: Path) -> tuple[tuple[object, ...], ...]:
    if directory != Path("/usr/bin"):
        raise DiagnosticError(f"system tool is outside /usr/bin: {directory}")
    identities: list[tuple[object, ...]] = []
    for path in (Path("/"), Path("/usr"), Path("/usr/bin")):
        metadata = path.lstat()
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != 0
            or stat.S_IMODE(metadata.st_mode) & 0o022
        ):
            raise DiagnosticError(f"unsafe system directory: {path}")
        identities.append(
            (
                str(path),
                metadata.st_dev,
                metadata.st_ino,
                metadata.st_mode,
                metadata.st_uid,
                metadata.st_gid,
                metadata.st_mtime_ns,
                metadata.st_ctime_ns,
            )
        )
    return tuple(identities)


def _codesign_details(
    path: Path,
    *,
    cwd: Path,
    environment: Mapping[str, str],
) -> dict[str, object]:
    verify = _run(
        ["/usr/bin/codesign", "--verify", "--strict", str(path)],
        cwd=cwd,
        environment=environment,
    )
    display = _run(
        ["/usr/bin/codesign", "-d", "--verbose=4", str(path)],
        cwd=cwd,
        environment=environment,
    )
    if verify.returncode != 0 or display.returncode != 0:
        raise DiagnosticError(f"code signature verification failed: {path}")
    details = display.stdout + display.stderr
    cdhash_full = next(
        (
            line.split("=", 1)[1]
            for line in details.splitlines()
            if line.startswith("CandidateCDHashFull sha256=")
        ),
        None,
    )
    return {
        "verify_returncode": verify.returncode,
        "verify_stdout": verify.stdout,
        "verify_stderr": verify.stderr,
        "display_returncode": display.returncode,
        "display_stdout": display.stdout,
        "display_stderr": display.stderr,
        "cdhash_full": cdhash_full,
    }


def _system_tool_receipt(
    path: Path,
    *,
    cwd: Path,
    environment: Mapping[str, str],
) -> dict[str, object]:
    chain_before = _system_directory_chain(path.parent)
    content, metadata = _stable_read_regular_file(
        path,
        maximum_bytes=10_000_000,
        allowed_uids=frozenset({0}),
        require_single_link=True,
    )
    signature = _codesign_details(path, cwd=cwd, environment=environment)
    content_after, metadata_after = _stable_read_regular_file(
        path,
        maximum_bytes=10_000_000,
        allowed_uids=frozenset({0}),
        require_single_link=True,
    )
    if (
        chain_before != _system_directory_chain(path.parent)
        or content != content_after
        or _identity(metadata) != _identity(metadata_after)
    ):
        raise DiagnosticError(f"system tool changed during receipt: {path}")
    return {
        "kind": "system_tool",
        "role": path.name,
        "lexical": str(path),
        "link_target": None,
        "resolved": str(path),
        "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
        "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
        "uid": metadata.st_uid,
        "gid": metadata.st_gid,
        "nlink": metadata.st_nlink,
        "codesign": signature,
    }


def _extract_macho_identity(validator: types.ModuleType, content: bytes) -> dict[str, object]:
    observed = dict(validator._inspect_swift_network_probe_macho(content))
    observed.pop("cdhash_full", None)
    return observed


def _diagnose_network_probe(
    *,
    validator: types.ModuleType,
    clang: Path,
    sdk: Path,
    sandbox: Path,
    environment: Mapping[str, str],
) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="elmos-apple-route-diagnostic-") as raw:
        root = Path(raw).resolve(strict=True)
        root.chmod(0o700)
        home = root / "home"
        temporary = root / "tmp"
        home.mkdir(mode=0o700)
        temporary.mkdir(mode=0o700)
        output = root / str(validator.SWIFT_NETWORK_PROBE_BINARY_NAME)
        probe_environment = {
            **environment,
            "HOME": str(home),
            "TMPDIR": str(temporary),
            "PATH": f"{clang.parent}:{SYSTEM_PATH}",
            "SOURCE_DATE_EPOCH": "0",
            "SWIFT_DETERMINISTIC_HASHING": "1",
            "ZERO_AR_DATE": "1",
            "TZ": "UTC",
            "NO_COLOR": "1",
            "CLICOLOR": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_TERMINAL_PROMPT": "0",
            "XDG_CACHE_HOME": str(home / ".cache"),
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
        }
        command = [
            str(sandbox),
            "-p",
            str(validator.SWIFT_NETWORK_POLICY_TEXT),
            str(clang),
            "-x",
            "c",
            "-std=c17",
            "-target",
            "arm64-apple-macosx26.0",
            "-Os",
            "-fno-ident",
            "-isysroot",
            str(sdk),
            "-Wl,-dead_strip",
            "-o",
            str(output),
            "-",
        ]
        build = _run(
            command,
            cwd=root,
            environment=probe_environment,
            timeout=120,
            input_text=str(validator.SWIFT_NETWORK_PROBE_SOURCE),
        )
        canonical_command = [
            "<sandbox-exec>" if item == str(sandbox) else
            "<clang>" if item == str(clang) else
            "<sdk>" if item == str(sdk) else
            "<probe-output>" if item == str(output) else item
            for item in command
        ]
        if build.returncode != 0:
            return {
                "kind": "network_probe",
                "status": "UNAVAILABLE",
                "build_returncode": build.returncode,
                "build_stdout": build.stdout.replace(str(root), "<probe-root>"),
                "build_stderr": build.stderr.replace(str(root), "<probe-root>"),
                "argv": canonical_command,
            }
        content, metadata = _stable_read_regular_file(
            output,
            maximum_bytes=10_000_000,
            allowed_uids=frozenset({os.getuid()}),
            require_single_link=True,
        )
        macho = _extract_macho_identity(validator, content)
        signature = _codesign_details(
            output,
            cwd=root,
            environment=probe_environment,
        )
        for key in ("verify_stdout", "verify_stderr", "display_stdout", "display_stderr"):
            signature[key] = str(signature[key]).replace(str(root), "<probe-root>")
        execution = _run(
            [str(sandbox), "-p", str(validator.SWIFT_NETWORK_POLICY_TEXT), str(output)],
            cwd=root,
            environment=probe_environment,
            timeout=30,
        )
        content_after, metadata_after = _stable_read_regular_file(
            output,
            maximum_bytes=10_000_000,
            allowed_uids=frozenset({os.getuid()}),
            require_single_link=True,
        )
        if content != content_after or _identity(metadata) != _identity(metadata_after):
            raise DiagnosticError("network probe changed during inspection")
        return {
            "kind": "network_probe",
            "status": "OBSERVED",
            "argv": canonical_command,
            "source_sha256": "sha256:"
            + hashlib.sha256(
                str(validator.SWIFT_NETWORK_PROBE_SOURCE).encode("utf-8")
            ).hexdigest(),
            "source_bytes": len(
                str(validator.SWIFT_NETWORK_PROBE_SOURCE).encode("utf-8")
            ),
            "build_returncode": build.returncode,
            "build_stdout": build.stdout.replace(str(root), "<probe-root>"),
            "build_stderr": build.stderr.replace(str(root), "<probe-root>"),
            "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
            "bytes": len(content),
            "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
            "uuid": macho["uuid"],
            "architecture": macho["architecture"],
            "file_type": macho["file_type"],
            "linked_libraries": macho["linked_libraries"],
            "cdhash_full": signature["cdhash_full"],
            "codesign": signature,
            "execution_returncode": execution.returncode,
            "execution_stdout": execution.stdout,
            "execution_stderr": execution.stderr,
        }


def _sequenced_records(
    records: Iterable[dict[str, object]],
) -> list[dict[str, object]]:
    return [
        {"schema": SCHEMA, "sequence": sequence, **record}
        for sequence, record in enumerate(records)
    ]


def _script_sha256(repository_root: Path) -> str:
    root = repository_root.resolve(strict=True)
    script_path = root / "scripts/toolchains/diagnose_apple_route_ci.py"
    if script_path.resolve(strict=True) != Path(__file__).resolve(strict=True):
        raise DiagnosticError("diagnostic script is not the repository-owned file")
    content, _metadata = _stable_read_regular_file(
        script_path,
        maximum_bytes=MAX_VALIDATOR_BYTES,
        allowed_uids=frozenset({0, os.getuid()}),
        require_single_link=True,
    )
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _exact_validator_specs(
    validator: types.ModuleType,
    attribute: str,
    *,
    expected_count: int,
) -> tuple[tuple[str, str], ...]:
    raw_specs = getattr(validator, attribute, None)
    if not isinstance(raw_specs, (tuple, list)):
        raise DiagnosticError(f"validator {attribute} inventory is invalid")
    specs: list[tuple[str, str]] = []
    for raw_spec in raw_specs:
        if not isinstance(raw_spec, (tuple, list)) or len(raw_spec) < 2:
            raise DiagnosticError(f"validator {attribute} entry is invalid")
        role, raw_path = raw_spec[0], raw_spec[1]
        if not isinstance(role, str) or not role:
            raise DiagnosticError(f"validator {attribute} role is invalid")
        path = Path(str(raw_path))
        if (
            not path.is_absolute()
            or not path.is_relative_to(EXPECTED_XCODE_APP / "Contents")
            or ".." in path.parts
        ):
            raise DiagnosticError(f"validator {attribute} path is invalid")
        specs.append((role, str(path)))
    if (
        len(specs) != expected_count
        or len({role for role, _path in specs}) != expected_count
        or len({path for _role, path in specs}) != expected_count
    ):
        raise DiagnosticError(f"validator {attribute} inventory is incomplete")
    return tuple(specs)


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(
        r"sha256:[0-9a-f]{64}", value
    ) is not None


def _is_nonnegative_integer(value: object, *, maximum: int | None = None) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0
        and (maximum is None or value <= maximum)
    )


def _is_mode(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-7]{4}", value) is not None


def _is_safe_mode(value: object) -> bool:
    return _is_mode(value) and int(str(value), 8) & 0o022 == 0


def _validate_path_identity(
    value: object,
    *,
    label: str,
    expected_lexical: str | None = None,
    expected_type: str | None = None,
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise DiagnosticError(f"{label} identity is missing")
    required = {
        "lexical",
        "link_target",
        "resolved",
        "type",
        "mode",
        "uid",
        "gid",
        "nlink",
        "device",
        "inode",
        "bytes",
        "mtime_ns",
        "ctime_ns",
    }
    if not required.issubset(value):
        raise DiagnosticError(f"{label} identity is incomplete")
    lexical = value.get("lexical")
    resolved = value.get("resolved")
    if (
        not isinstance(lexical, str)
        or not Path(lexical).is_absolute()
        or (expected_lexical is not None and lexical != expected_lexical)
        or not isinstance(resolved, str)
        or not Path(resolved).is_absolute()
        or value.get("type") not in {"symlink", "directory", "regular"}
        or (expected_type is not None and value.get("type") != expected_type)
        or not _is_safe_mode(value.get("mode"))
        or value.get("uid") != 0
        or value.get("gid") != 0
        or not _is_nonnegative_integer(value.get("device"))
        or not _is_nonnegative_integer(value.get("inode"))
        or not _is_nonnegative_integer(value.get("bytes"))
        or not _is_nonnegative_integer(value.get("mtime_ns"))
        or not _is_nonnegative_integer(value.get("ctime_ns"))
        or not _is_nonnegative_integer(value.get("nlink"))
        or value.get("nlink") == 0
        or not (
            value.get("link_target") is None
            or isinstance(value.get("link_target"), str)
        )
    ):
        raise DiagnosticError(f"{label} identity is invalid")
    return value


def _validate_codesign_receipt(value: object, *, label: str) -> None:
    if not isinstance(value, dict):
        raise DiagnosticError(f"{label} codesign receipt is missing")
    required_strings = (
        "verify_stdout",
        "verify_stderr",
        "display_stdout",
        "display_stderr",
    )
    cdhash = value.get("cdhash_full")
    if (
        value.get("verify_returncode") != 0
        or value.get("display_returncode") != 0
        or not all(isinstance(value.get(key), str) for key in required_strings)
        or not isinstance(cdhash, str)
        or re.fullmatch(r"[0-9A-Fa-f]{40}|[0-9A-Fa-f]{64}", cdhash) is None
    ):
        raise DiagnosticError(f"{label} codesign receipt is invalid")


def _validate_file_receipt(
    record: Mapping[str, object],
    *,
    label: str,
    expected_lexical: str,
    expected_resolved: str | None = None,
    expected_link_target: object = _UNSET,
    maximum_bytes: int = MAX_COMPONENT_BYTES,
) -> None:
    resolved = record.get("resolved")
    link_target = record.get("link_target")
    lexical_identity = record.get("lexical_identity")
    lexical_type = (
        lexical_identity.get("type") if isinstance(lexical_identity, dict) else None
    )
    lexical_link_target = (
        lexical_identity.get("link_target")
        if isinstance(lexical_identity, dict)
        else _UNSET
    )
    if (
        record.get("lexical") != expected_lexical
        or not isinstance(resolved, str)
        or not Path(resolved).is_absolute()
        or not Path(resolved).is_relative_to(EXPECTED_XCODE_APP / "Contents")
        or ".." in Path(resolved).parts
        or (expected_resolved is not None and resolved != expected_resolved)
        or (
            expected_link_target is not _UNSET
            and link_target != expected_link_target
        )
        or not _is_sha256(record.get("sha256"))
        or not _is_nonnegative_integer(record.get("bytes"), maximum=maximum_bytes)
        or not _is_safe_mode(record.get("mode"))
        or record.get("uid") != 0
        or record.get("gid") != 0
        or not _is_nonnegative_integer(record.get("nlink"))
        or record.get("nlink") == 0
        or not isinstance(lexical_identity, dict)
        or lexical_type not in {"symlink", "regular"}
        or (
            lexical_type == "regular"
            and (
                link_target is not None
                or lexical_link_target is not None
                or not isinstance(resolved, str)
                or Path(resolved).name != Path(expected_lexical).name
            )
        )
        or (
            lexical_type == "symlink"
            and (
                not isinstance(link_target, str)
                or not link_target
                or lexical_link_target != link_target
                or Path(link_target).is_absolute()
                or ".." in Path(link_target).parts
                or resolved == expected_lexical
            )
        )
        or not _is_safe_mode(lexical_identity.get("mode"))
        or lexical_identity.get("uid") != 0
        or lexical_identity.get("gid") != 0
        or not _is_nonnegative_integer(lexical_identity.get("nlink"))
        or lexical_identity.get("nlink") == 0
        or not _is_nonnegative_integer(lexical_identity.get("device"))
        or not _is_nonnegative_integer(lexical_identity.get("inode"))
        or not _is_nonnegative_integer(lexical_identity.get("bytes"))
        or not _is_nonnegative_integer(lexical_identity.get("mtime_ns"))
        or not _is_nonnegative_integer(lexical_identity.get("ctime_ns"))
        or not (
            link_target is None
            or isinstance(link_target, str)
        )
    ):
        raise DiagnosticError(f"{label} file receipt is invalid")


def _validate_diagnostic_records(
    records: list[dict[str, object]],
    *,
    validator: types.ModuleType,
    validator_sha256: str,
    allow_network_not_run: bool,
) -> None:
    component_specs = _exact_validator_specs(
        validator,
        "SWIFT_BUILD_CLOSURE_COMPONENT_SPECS",
        expected_count=EXPECTED_COMPONENT_COUNT,
    )
    tree_specs = _exact_validator_specs(
        validator,
        "SWIFT_BUILD_CLOSURE_TREE_SPECS",
        expected_count=EXPECTED_TREE_COUNT,
    )
    raw_component_specs = getattr(
        validator, "SWIFT_BUILD_CLOSURE_COMPONENT_SPECS"
    )
    raw_tree_specs = getattr(validator, "SWIFT_BUILD_CLOSURE_TREE_SPECS")
    component_contracts: list[tuple[str, str, str, str | None]] = []
    for (role, path), raw_spec in zip(
        component_specs, raw_component_specs, strict=True
    ):
        if len(raw_spec) < 4:
            raise DiagnosticError("validator Swift component contract is incomplete")
        resolved_path = Path(str(raw_spec[2]))
        link_target = raw_spec[3]
        if (
            not resolved_path.is_absolute()
            or not resolved_path.is_relative_to(EXPECTED_XCODE_APP / "Contents")
            or ".." in resolved_path.parts
            or not (link_target is None or isinstance(link_target, str))
        ):
            raise DiagnosticError("validator Swift component contract is invalid")
        component_contracts.append((role, path, str(resolved_path), link_target))
    tree_contracts: list[tuple[str, str, str]] = []
    for (role, path), raw_spec in zip(tree_specs, raw_tree_specs, strict=True):
        if len(raw_spec) < 3:
            raise DiagnosticError("validator Swift tree contract is incomplete")
        resolved_path = Path(str(raw_spec[2]))
        if (
            not resolved_path.is_absolute()
            or not resolved_path.is_relative_to(EXPECTED_XCODE_APP / "Contents")
            or ".." in resolved_path.parts
        ):
            raise DiagnosticError("validator Swift tree contract is invalid")
        tree_contracts.append((role, path, str(resolved_path)))
    expected_sequence = [
        ("environment", None),
        ("xcode_source_normalization", None),
        ("xcode_physical", None),
        ("sdk_selected", None),
        ("sdk_spec_alias", None),
        *(("swift_component", role) for role, _path in component_specs),
        *(("swift_tree", role) for role, _path in tree_specs),
        ("apple_git", "apple-git"),
        ("system_tool", "sandbox-exec"),
        ("system_tool", "codesign"),
        ("compiler_tool", "xcrun-clang"),
        ("compiler_tool", "xcrun-swiftc"),
        ("compiler_tool", "xcrun-swift"),
        ("network_probe", None),
    ]
    observed_sequence = [
        (
            record.get("kind"),
            record.get("role")
            if record.get("kind")
            in {"swift_component", "swift_tree", "apple_git", "system_tool", "compiler_tool"}
            else None,
        )
        for record in records
    ]
    if observed_sequence != expected_sequence:
        raise DiagnosticError("Apple route diagnostic exact inventory is incomplete")

    environment = records[0]
    expected_product_version, expected_build_version = _expected_host_versions(
        environment.get("image_version")
    )
    if (
        environment.get("image_os") != EXPECTED_IMAGE_OS
        or environment.get("product_version") != expected_product_version
        or environment.get("build_version") != expected_build_version
        or environment.get("machine") != "arm64"
        or environment.get("validator_sha256") != validator_sha256
        or environment.get("xcode_version_stdout") != EXPECTED_XCODE_VERSION
        or environment.get("xcode_version_stderr") != ""
        or environment.get("sdk_version") != "26.5"
    ):
        raise DiagnosticError("Apple route diagnostic environment is invalid")

    source_normalization = records[1]
    if {
        key: value
        for key, value in source_normalization.items()
        if key not in {"schema", "sequence"}
    } != {
        "kind": "xcode_source_normalization",
        "source": str(HOSTED_SOURCE_XCODE_APP),
        "status": "ABSENT_AFTER_VERIFIED_RENAME",
    }:
        raise DiagnosticError("Xcode source normalization record is invalid")
    xcode = _validate_path_identity(
        records[2],
        label="Xcode",
        expected_lexical=str(EXPECTED_XCODE_APP),
        expected_type="directory",
    )
    if (
        xcode.get("link_target") is not None
        or xcode.get("resolved") != str(EXPECTED_XCODE_APP)
        or xcode.get("selected_developer_lexical")
        != str(EXPECTED_XCODE_APP / "Contents/Developer")
        or xcode.get("selected_developer_physical")
        != str(EXPECTED_XCODE_APP / "Contents/Developer")
    ):
        raise DiagnosticError("Xcode physical record is invalid")
    _validate_path_identity(
        xcode.get("selected_developer_identity"),
        label="selected Developer",
        expected_lexical=str(EXPECTED_XCODE_APP / "Contents/Developer"),
        expected_type="directory",
    )

    canonical_contents = Path("/Applications/Xcode.app/Contents")
    canonical_sdk_directory = (
        canonical_contents / "Developer/Platforms/MacOSX.platform/Developer/SDKs"
    )
    canonical_sdk_alias = canonical_sdk_directory / EXPECTED_SDK_ALIAS_NAME
    canonical_sdk_target = canonical_sdk_directory / EXPECTED_SDK_ALIAS_TARGET
    validator_sdk_alias = Path(str(getattr(validator, "SWIFT_SDK_ROOT")))
    if (
        EXPECTED_XCODE_APP / "Contents" != canonical_contents
        or validator_sdk_alias != canonical_sdk_alias
        or validator_sdk_alias.name != EXPECTED_SDK_ALIAS_NAME
        or canonical_sdk_alias.parent != canonical_sdk_target.parent
        or EXPECTED_SDK_ALIAS_TARGET != canonical_sdk_target.name
        or Path(EXPECTED_SDK_ALIAS_TARGET).is_absolute()
        or len(Path(EXPECTED_SDK_ALIAS_TARGET).parts) != 1
    ):
        raise DiagnosticError("validator SDK alias contract is not canonical")
    sdk_target = str(canonical_sdk_target)
    selected_sdk = _validate_path_identity(records[3], label="selected SDK")
    if (
        selected_sdk.get("lexical")
        not in {str(canonical_sdk_alias), sdk_target}
        or selected_sdk.get("resolved") != sdk_target
        or (
            selected_sdk.get("lexical") == str(canonical_sdk_alias)
            and (
                selected_sdk.get("type") != "symlink"
                or selected_sdk.get("link_target") != EXPECTED_SDK_ALIAS_TARGET
            )
        )
        or (
            selected_sdk.get("lexical") == sdk_target
            and (
                selected_sdk.get("type") != "directory"
                or selected_sdk.get("link_target") is not None
            )
        )
    ):
        raise DiagnosticError("selected SDK record is invalid")
    sdk_alias = _validate_path_identity(
        records[4],
        label="validator SDK alias",
        expected_lexical=str(canonical_sdk_alias),
        expected_type="symlink",
    )
    if (
        sdk_alias.get("link_target") != EXPECTED_SDK_ALIAS_TARGET
        or sdk_alias.get("resolved") != sdk_target
    ):
        raise DiagnosticError("validator SDK alias record is invalid")
    sdk_target_identity = _validate_path_identity(
        sdk_alias.get("target_identity"),
        label="validator SDK target",
        expected_lexical=sdk_target,
        expected_type="directory",
    )
    if (
        sdk_target_identity.get("resolved") != sdk_target
        or sdk_target_identity.get("link_target") is not None
    ):
        raise DiagnosticError("validator SDK target record is invalid")

    component_records = records[5 : 5 + EXPECTED_COMPONENT_COUNT]
    for record, (role, path, expected_resolved, link_target) in zip(
        component_records, component_contracts, strict=True
    ):
        if record.get("kind") != "swift_component" or record.get("role") != role:
            raise DiagnosticError("Swift component record identity is invalid")
        _validate_file_receipt(
            record,
            label=f"Swift component {role}",
            expected_lexical=path,
            expected_resolved=expected_resolved,
            expected_link_target=link_target,
        )

    tree_start = 5 + EXPECTED_COMPONENT_COUNT
    tree_records = records[tree_start : tree_start + EXPECTED_TREE_COUNT]
    for record, (role, path, expected_resolved) in zip(
        tree_records, tree_contracts, strict=True
    ):
        observed_resolved = record.get("resolved")
        if (
            record.get("kind") != "swift_tree"
            or record.get("role") != role
            or record.get("lexical") != path
            or not isinstance(observed_resolved, str)
            or not Path(observed_resolved).is_absolute()
            or not Path(observed_resolved).is_relative_to(
                EXPECTED_XCODE_APP / "Contents"
            )
            or observed_resolved != expected_resolved
            or record.get("link_target") is not None
            or not _is_sha256(record.get("sha256"))
            or not _is_nonnegative_integer(
                record.get("file_count"), maximum=MAX_TREE_ENTRIES
            )
            or not _is_nonnegative_integer(
                record.get("bytes"), maximum=MAX_TREE_BYTES
            )
        ):
            raise DiagnosticError(f"Swift tree {role} receipt is invalid")

    suffix_start = tree_start + EXPECTED_TREE_COUNT
    apple_git, sandbox, codesign, clang, swiftc, swift, network = records[suffix_start:]
    _validate_file_receipt(
        apple_git,
        label="Apple git",
        expected_lexical=str(getattr(validator, "SWIFT_GIT_PATH")),
        expected_resolved=str(getattr(validator, "SWIFT_GIT_PATH")),
        expected_link_target=None,
    )
    if not all(
        isinstance(apple_git.get(key), str)
        for key in ("version_stdout", "version_stderr")
    ):
        raise DiagnosticError("Apple git version receipt is invalid")

    for record, role in ((sandbox, "sandbox-exec"), (codesign, "codesign")):
        expected_path = f"/usr/bin/{role}"
        if (
            record.get("kind") != "system_tool"
            or record.get("role") != role
            or record.get("lexical") != expected_path
            or record.get("resolved") != expected_path
            or record.get("link_target") is not None
            or not _is_sha256(record.get("sha256"))
            or not _is_nonnegative_integer(record.get("bytes"), maximum=10_000_000)
            or not _is_safe_mode(record.get("mode"))
            or record.get("uid") != 0
            or record.get("gid") != 0
            or record.get("nlink") != 1
        ):
            raise DiagnosticError(f"system tool {role} receipt is invalid")
        _validate_codesign_receipt(record.get("codesign"), label=role)

    component_by_role = {
        role: (path, resolved, link_target)
        for role, path, resolved, link_target in component_contracts
    }
    compiler_paths = {
        "xcrun-clang": component_by_role["clang"],
        "xcrun-swiftc": component_by_role["swiftc-dispatcher"],
        "xcrun-swift": component_by_role["swift-dispatcher"],
    }
    for record in (clang, swiftc, swift):
        role = str(record.get("role"))
        expected_contract = compiler_paths.get(role)
        if expected_contract is None:
            raise DiagnosticError("compiler tool role is invalid")
        expected_path, expected_resolved, expected_link_target = expected_contract
        _validate_file_receipt(
            record,
            label=f"compiler tool {role}",
            expected_lexical=expected_path,
            expected_resolved=expected_resolved,
            expected_link_target=expected_link_target,
        )
        if not all(
            isinstance(record.get(key), str)
            for key in ("version_stdout", "version_stderr")
        ):
            raise DiagnosticError(f"compiler tool {role} version receipt is invalid")

    network_status = network.get("status")
    if network_status == "NOT_RUN":
        if not allow_network_not_run or network != {
            "kind": "network_probe",
            "status": "NOT_RUN",
        }:
            raise DiagnosticError("network probe NOT_RUN receipt is invalid")
    elif network_status == "UNAVAILABLE":
        network_argv = network.get("argv")
        if (
            not _is_nonnegative_integer(network.get("build_returncode"))
            or network.get("build_returncode") == 0
            or not all(
                isinstance(network.get(key), str)
                for key in ("build_stdout", "build_stderr")
            )
            or not isinstance(network_argv, list)
            or not all(isinstance(item, str) for item in network_argv)
        ):
            raise DiagnosticError("network probe unavailable receipt is invalid")
    elif network_status == "OBSERVED":
        network_argv = network.get("argv")
        linked_libraries = network.get("linked_libraries")
        if (
            network.get("build_returncode") != 0
            or not _is_sha256(network.get("source_sha256"))
            or not _is_sha256(network.get("sha256"))
            or not _is_nonnegative_integer(network.get("source_bytes"))
            or not _is_nonnegative_integer(network.get("bytes"), maximum=10_000_000)
            or not _is_safe_mode(network.get("mode"))
            or not isinstance(network_argv, list)
            or not all(isinstance(item, str) for item in network_argv)
            or not _is_nonnegative_integer(network.get("execution_returncode"))
            or not all(
                isinstance(network.get(key), str)
                for key in (
                    "build_stdout",
                    "build_stderr",
                    "execution_stdout",
                    "execution_stderr",
                    "uuid",
                    "architecture",
                    "file_type",
                )
            )
            or not isinstance(linked_libraries, list)
            or not all(isinstance(item, str) for item in linked_libraries)
        ):
            raise DiagnosticError("observed network probe receipt is invalid")
        _validate_codesign_receipt(network.get("codesign"), label="network probe")
        codesign_receipt = network["codesign"]
        if (
            not isinstance(codesign_receipt, dict)
            or network.get("cdhash_full") != codesign_receipt.get("cdhash_full")
        ):
            raise DiagnosticError("network probe code identity is invalid")
    else:
        raise DiagnosticError("network probe status is invalid")


def _complete_records(
    records: list[dict[str, object]],
    *,
    validator: types.ModuleType,
    validator_sha256: str,
    script_sha256: str,
    allow_network_not_run: bool,
) -> list[dict[str, object]]:
    _validate_diagnostic_records(
        records,
        validator=validator,
        validator_sha256=validator_sha256,
        allow_network_not_run=allow_network_not_run,
    )
    component_roles = [
        str(record.get("role"))
        for record in records
        if record.get("kind") == "swift_component"
    ]
    tree_roles = [
        str(record.get("role"))
        for record in records
        if record.get("kind") == "swift_tree"
    ]
    if (
        len(component_roles) != EXPECTED_COMPONENT_COUNT
        or len(set(component_roles)) != EXPECTED_COMPONENT_COUNT
        or len(tree_roles) != EXPECTED_TREE_COUNT
        or len(set(tree_roles)) != EXPECTED_TREE_COUNT
    ):
        raise DiagnosticError("Apple route diagnostic role inventory is incomplete")
    expected_kind_counts = EXPECTED_KIND_COUNTS
    observed_kind_counts = {
        kind: sum(record.get("kind") == kind for record in records)
        for kind in expected_kind_counts
    }
    if observed_kind_counts != expected_kind_counts or len(records) != sum(
        expected_kind_counts.values()
    ):
        raise DiagnosticError("Apple route diagnostic record inventory is incomplete")
    sequenced = _sequenced_records(records)
    completion = {
        "kind": "completion",
        "status": "COMPLETE_DIAGNOSTIC_ONLY",
        "certification": "NOT_CERTIFIED",
        "validator_sha256": validator_sha256,
        "script_sha256": script_sha256,
        "expected_component_count": EXPECTED_COMPONENT_COUNT,
        "observed_component_count": len(component_roles),
        "expected_tree_count": EXPECTED_TREE_COUNT,
        "observed_tree_count": len(tree_roles),
        "record_count": len(records),
        "total_record_count": len(records) + 1,
        "kind_counts": observed_kind_counts,
        "records_sha256": _canonical_sha256({"records": sequenced}),
    }
    return [*records, completion]


def _verify_jsonl(path: Path, repository_root: Path) -> None:
    validator, validator_sha256 = _load_validator(repository_root)
    script_sha256 = _script_sha256(repository_root)
    content, _metadata = _stable_read_regular_file(
        path,
        maximum_bytes=MAX_DIAGNOSTIC_OUTPUT_BYTES,
        allowed_uids=frozenset({0, os.getuid()}),
        require_single_link=True,
    )
    def reject_duplicate_keys(
        pairs: list[tuple[str, object]],
    ) -> dict[str, object]:
        payload: dict[str, object] = {}
        for key, value in pairs:
            if key in payload:
                raise ValueError(f"duplicate JSON key: {key}")
            payload[key] = value
        return payload

    def reject_nonfinite(value: str) -> object:
        raise ValueError(f"non-finite JSON value: {value}")

    try:
        payloads = [
            json.loads(
                line,
                object_pairs_hook=reject_duplicate_keys,
                parse_constant=reject_nonfinite,
            )
            for line in content.decode("utf-8").splitlines()
        ]
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise DiagnosticError("diagnostic JSONL is invalid") from exc
    if not payloads or not all(isinstance(payload, dict) for payload in payloads):
        raise DiagnosticError("diagnostic JSONL record set is empty or invalid")
    if any(
        payload.get("schema") != SCHEMA or payload.get("sequence") != sequence
        for sequence, payload in enumerate(payloads)
    ):
        raise DiagnosticError("diagnostic JSONL sequence is incomplete")
    completion = payloads[-1]
    preceding = payloads[:-1]
    expected_kind_counts = EXPECTED_KIND_COUNTS
    observed_kind_counts = {
        kind: sum(payload.get("kind") == kind for payload in preceding)
        for kind in expected_kind_counts
    }
    component_roles = [
        payload.get("role")
        for payload in preceding
        if payload.get("kind") == "swift_component"
    ]
    tree_roles = [
        payload.get("role")
        for payload in preceding
        if payload.get("kind") == "swift_tree"
    ]
    if (
        completion.get("kind") != "completion"
        or completion.get("status") != "COMPLETE_DIAGNOSTIC_ONLY"
        or completion.get("certification") != "NOT_CERTIFIED"
        or completion.get("validator_sha256") != validator_sha256
        or completion.get("script_sha256") != script_sha256
        or completion.get("record_count") != len(preceding)
        or completion.get("total_record_count") != len(payloads)
        or completion.get("expected_component_count") != EXPECTED_COMPONENT_COUNT
        or completion.get("observed_component_count") != EXPECTED_COMPONENT_COUNT
        or completion.get("expected_tree_count") != EXPECTED_TREE_COUNT
        or completion.get("observed_tree_count") != EXPECTED_TREE_COUNT
        or completion.get("kind_counts") != observed_kind_counts
        or observed_kind_counts != expected_kind_counts
        or len(preceding) != sum(expected_kind_counts.values())
        or not all(isinstance(role, str) for role in component_roles)
        or not all(isinstance(role, str) for role in tree_roles)
        or len(component_roles) != len(set(component_roles))
        or len(tree_roles) != len(set(tree_roles))
        or completion.get("records_sha256")
        != _canonical_sha256({"records": preceding})
    ):
        raise DiagnosticError("diagnostic completion record is invalid")
    _validate_diagnostic_records(
        preceding,
        validator=validator,
        validator_sha256=validator_sha256,
        allow_network_not_run=False,
    )
    validator_after, validator_sha256_after = _load_validator(repository_root)
    del validator_after
    if (
        validator_sha256_after != validator_sha256
        or _script_sha256(repository_root) != script_sha256
    ):
        raise DiagnosticError("diagnostic authority changed during verification")


def _emit(records: Iterable[dict[str, object]]) -> None:
    for payload in _sequenced_records(records):
        print(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        )


def diagnose(repository_root: Path, *, skip_network_probe: bool) -> list[dict[str, object]]:
    validator, validator_sha256 = _load_validator(repository_root)
    environment = {"LANG": "C", "LC_ALL": "C", "PATH": SYSTEM_PATH}
    cwd = repository_root.resolve(strict=True)
    script_sha256 = _script_sha256(repository_root)
    image_version = os.environ.get("ImageVersion")
    if (
        os.environ.get("GITHUB_ACTIONS") != "true"
        or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
        or os.environ.get("ELMOS_APPLE_ROUTE_XCODE_SEALED") != "1"
        or os.environ.get("ELMOS_APPLE_ROUTE_XCODE_PHYSICAL")
        != str(EXPECTED_XCODE_APP)
        or os.environ.get("ImageOS") != EXPECTED_IMAGE_OS
        or image_version not in EXPECTED_HOST_PROFILES
        or os.uname().machine != "arm64"
    ):
        raise DiagnosticError("diagnostic requires the exact prepared GitHub host")
    selected = _run_exact(
        ["/usr/bin/xcode-select", "-p"], cwd=cwd, environment=environment
    ).stdout.strip()
    selected_developer = Path(selected)
    physical_developer = selected_developer.resolve(strict=True)
    if (
        selected_developer != EXPECTED_XCODE_APP / "Contents/Developer"
        or physical_developer != selected_developer
        or physical_developer.name != "Developer"
    ):
        raise DiagnosticError("xcode-select path is not a Developer directory")
    physical_contents = physical_developer.parent
    physical_app = physical_contents.parent
    if physical_app != EXPECTED_XCODE_APP:
        raise DiagnosticError("selected Xcode is not the exact physical bundle")
    _xcode_directory_chain(physical_developer)
    spec_contents = Path(str(validator.SWIFT_XCODE_ROOT))
    if spec_contents != EXPECTED_XCODE_APP / "Contents":
        raise DiagnosticError("validator Xcode root is not the canonical physical root")
    if HOSTED_SOURCE_XCODE_APP.exists() or HOSTED_SOURCE_XCODE_APP.is_symlink():
        raise DiagnosticError("versioned hosted Xcode source still exists after prepare")
    physical_app_identity = _path_identity(physical_app)
    if (
        physical_app_identity["type"] != "directory"
        or physical_app_identity["link_target"] is not None
        or physical_app_identity["uid"] != 0
        or physical_app_identity["gid"] != 0
        or int(str(physical_app_identity["mode"]), 8) & 0o022
    ):
        raise DiagnosticError("canonical physical Xcode root is unsafe")

    xcode_version = _run_exact(
        ["/usr/bin/xcodebuild", "-version"], cwd=cwd, environment=environment
    )
    product_version = _run_exact(
        ["/usr/bin/sw_vers", "-productVersion"], cwd=cwd, environment=environment
    )
    build_version = _run_exact(
        ["/usr/bin/sw_vers", "-buildVersion"], cwd=cwd, environment=environment
    )
    sdk_version = _run_exact(
        ["/usr/bin/xcrun", "--sdk", "macosx", "--show-sdk-version"],
        cwd=cwd,
        environment=environment,
    )
    sdk_path_output = _run_exact(
        ["/usr/bin/xcrun", "--sdk", "macosx", "--show-sdk-path"],
        cwd=cwd,
        environment=environment,
    ).stdout.strip()
    sdk_path = Path(sdk_path_output)
    sdk_resolved = sdk_path.resolve(strict=True)
    if not sdk_resolved.is_relative_to(physical_contents):
        raise DiagnosticError("xcrun SDK resolves outside selected Xcode")

    spec_sdk_path = _map_spec_path(
        str(validator.SWIFT_SDK_ROOT),
        spec_contents_root=spec_contents,
        physical_contents_root=physical_contents,
    )
    expected_sdk_target = spec_sdk_path.parent / EXPECTED_SDK_ALIAS_TARGET
    spec_sdk_identity, sdk_target_identity = _exact_relative_directory_alias(
        spec_sdk_path,
        expected_target_name=EXPECTED_SDK_ALIAS_TARGET,
        expected_resolved=expected_sdk_target,
    )
    if (
        spec_sdk_path.name != EXPECTED_SDK_ALIAS_NAME
        or sdk_resolved != expected_sdk_target
        or sdk_path not in {spec_sdk_path, expected_sdk_target}
    ):
        raise DiagnosticError("validator SDK alias and xcrun SDK differ")

    selected_developer_identity = _path_identity(physical_developer)
    selected_sdk_identity = _path_identity(sdk_path)
    expected_product_version, expected_build_version = _expected_host_versions(
        image_version
    )
    if (
        product_version.stdout.strip() != expected_product_version
        or build_version.stdout.strip() != expected_build_version
        or xcode_version.stdout != EXPECTED_XCODE_VERSION
        or xcode_version.stderr
        or sdk_version.stdout.strip() != "26.5"
    ):
        raise DiagnosticError("hosted Apple version identity drifted")
    records: list[dict[str, object]] = [
        {
            "kind": "environment",
            "image_os": os.environ.get("ImageOS", "UNSET"),
            "image_version": os.environ.get("ImageVersion", "UNSET"),
            "product_version": product_version.stdout.strip(),
            "build_version": build_version.stdout.strip(),
            "machine": os.uname().machine,
            "validator_sha256": validator_sha256,
            "xcode_version_stdout": xcode_version.stdout,
            "xcode_version_stderr": xcode_version.stderr,
            "sdk_version": sdk_version.stdout.strip(),
        },
        {
            "kind": "xcode_source_normalization",
            "source": str(HOSTED_SOURCE_XCODE_APP),
            "status": "ABSENT_AFTER_VERIFIED_RENAME",
        },
        {
            "kind": "xcode_physical",
            **physical_app_identity,
            "selected_developer_lexical": str(selected_developer),
            "selected_developer_physical": str(physical_developer),
            "selected_developer_identity": selected_developer_identity,
        },
        {"kind": "sdk_selected", **selected_sdk_identity},
        {
            "kind": "sdk_spec_alias",
            **spec_sdk_identity,
            "target_identity": sdk_target_identity,
        },
    ]

    for component in validator.SWIFT_BUILD_CLOSURE_COMPONENT_SPECS:
        role, path_text = component[0], component[1]
        mapped = _map_spec_path(
            str(path_text),
            spec_contents_root=spec_contents,
            physical_contents_root=physical_contents,
        )
        records.append(
            _component_receipt(
                role=str(role),
                lexical=mapped,
                physical_contents_root=physical_contents,
            )
        )

    for tree in validator.SWIFT_BUILD_CLOSURE_TREE_SPECS:
        role, root_text = tree[0], tree[1]
        mapped = _map_spec_path(
            str(root_text),
            spec_contents_root=spec_contents,
            physical_contents_root=physical_contents,
        )
        records.append(
            _tree_receipt(
                role=str(role),
                lexical=mapped,
                physical_contents_root=physical_contents,
            )
        )

    git_path = _map_spec_path(
        str(validator.SWIFT_GIT_PATH),
        spec_contents_root=spec_contents,
        physical_contents_root=physical_contents,
    )
    git_receipt = _component_receipt(
        role="apple-git",
        lexical=git_path,
        physical_contents_root=physical_contents,
    )
    git_version = _run_exact(
        [str(git_path), "--version"], cwd=cwd, environment=environment
    )
    records.append(
        {
            **git_receipt,
            "kind": "apple_git",
            "version_stdout": git_version.stdout,
            "version_stderr": git_version.stderr,
        }
    )

    sandbox_path = Path("/usr/bin/sandbox-exec")
    codesign_path = Path("/usr/bin/codesign")
    records.append(
        _system_tool_receipt(
            sandbox_path, cwd=cwd, environment=environment
        )
    )
    records.append(
        _system_tool_receipt(
            codesign_path, cwd=cwd, environment=environment
        )
    )

    tool_paths: dict[str, Path] = {}
    for role in ("clang", "swiftc", "swift"):
        lexical = Path(
            _run_exact(
                ["/usr/bin/xcrun", "--find", role],
                cwd=cwd,
                environment=environment,
            ).stdout.strip()
        )
        resolved = lexical.resolve(strict=True)
        if not resolved.is_relative_to(physical_contents):
            raise DiagnosticError(f"xcrun {role} resolves outside selected Xcode")
        tool_paths[role] = lexical
        receipt = _component_receipt(
            role=f"xcrun-{role}",
            lexical=lexical,
            physical_contents_root=physical_contents,
        )
        version = _run_exact(
            [str(lexical), "--version"], cwd=cwd, environment=environment
        )
        records.append(
            {
                **receipt,
                "kind": "compiler_tool",
                "version_stdout": version.stdout,
                "version_stderr": version.stderr,
            }
        )

    if skip_network_probe:
        records.append({"kind": "network_probe", "status": "NOT_RUN"})
    else:
        records.append(
            _diagnose_network_probe(
                validator=validator,
                clang=tool_paths["clang"],
                sdk=sdk_path,
                sandbox=sandbox_path,
                environment=environment,
            )
        )
    if (
        HOSTED_SOURCE_XCODE_APP.exists()
        or HOSTED_SOURCE_XCODE_APP.is_symlink()
        or _path_identity(physical_app) != physical_app_identity
        or _path_identity(physical_developer) != selected_developer_identity
        or _path_identity(sdk_path) != selected_sdk_identity
        or _path_identity(spec_sdk_path) != spec_sdk_identity
        or _path_identity(expected_sdk_target) != sdk_target_identity
    ):
        raise DiagnosticError("Xcode or SDK identity changed during capture")
    _validator_after, validator_sha256_after = _load_validator(repository_root)
    if (
        validator_sha256_after != validator_sha256
        or _script_sha256(repository_root) != script_sha256
    ):
        raise DiagnosticError("diagnostic authority changed during capture")
    return _complete_records(
        records,
        validator=validator,
        validator_sha256=validator_sha256,
        script_sha256=script_sha256,
        allow_network_not_run=skip_network_probe,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
    )
    parser.add_argument("--skip-network-probe", action="store_true")
    parser.add_argument("--verify-jsonl", type=Path)
    arguments = parser.parse_args(argv)
    try:
        if arguments.verify_jsonl is not None:
            if arguments.skip_network_probe:
                raise DiagnosticError(
                    "--verify-jsonl cannot be combined with --skip-network-probe"
                )
            _verify_jsonl(arguments.verify_jsonl, arguments.repository_root)
            return 0
        records = diagnose(
            arguments.repository_root,
            skip_network_probe=arguments.skip_network_probe,
        )
    except (DiagnosticError, FileNotFoundError, OSError, subprocess.SubprocessError) as exc:
        print(
            json.dumps(
                {"schema": SCHEMA, "kind": "error", "error": str(exc)},
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1
    _emit(records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
