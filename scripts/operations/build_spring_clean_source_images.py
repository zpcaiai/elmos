#!/usr/bin/env python3
"""Build all three Spring images from one exact, safely extracted Git commit.

This is a local engineering-evidence wrapper.  It deliberately refuses dirty
worktree input, abbreviated revisions, existing image tags, submodules, Git LFS
pointers, links, unsafe archive paths, and low-capacity starts.  It does not
promote, publish, certify, prune, or remove Docker state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TAG_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")
NAME_COMPONENT_RE = re.compile(
    r"^[a-z0-9]+(?:(?:[._]|__|[-]+)[a-z0-9]+)*$"
)
HOST_RE = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")
GIT_OBJECT_RE = re.compile(rb"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/v1"
LFS_ATTRIBUTE_RE = re.compile(rb"(?mi)^[^#\r\n]*\bfilter\s*=\s*lfs(?:\s|$)")

GIB = 1024**3
MINIMUM_BUILD_FREE_BYTES = 12 * GIB
HARD_STOP_FREE_BYTES = 8 * GIB
CAPACITY_POLL_SECONDS = 2.0
MAX_ARCHIVE_ENTRY_COUNT = 200_000
MAX_ARCHIVE_REGULAR_BYTES = 3 * GIB
EXTRACTION_BATCH_BYTES = 4 * 1024 * 1024
EXTRACTION_METADATA_RESERVE_BYTES = 64 * 1024 * 1024
EXTRACTION_ENTRY_ALLOCATION_GUARD_BYTES = 4096

PLATFORM_IMAGE_METADATA = {
    "linux/arm64": ("linux", "arm64", "v8"),
    "linux/amd64": ("linux", "amd64", ""),
}


class BuildFailure(RuntimeError):
    """Fail-closed error whose message is safe to persist in evidence."""

    def __init__(self, stage: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage


class CapacityFailure(BuildFailure):
    """Capacity policy stopped the operation."""


@dataclass(frozen=True)
class ImageSpec:
    key: str
    dockerfile: str
    expected_user: str


IMAGE_SPECS = (
    ImageSpec("runtime", "apps/java-runtime-runner/Dockerfile", "10003:10003"),
    ImageSpec("transformer", "apps/java-engine-transformer/Dockerfile", "10001:10001"),
    ImageSpec("verifier", "apps/java-engine-verifier/Dockerfile", "10002:10002"),
)


@dataclass(frozen=True)
class BuildConfig:
    repository_root: Path
    source_commit: str
    evidence_dir: Path
    platform: str
    tags: dict[str, str]


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    log_path: Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json_bytes(value: Any) -> bytes:
    """Return the one byte representation used for all source-status digests."""

    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def write_canonical_json(path: Path, value: Any) -> str:
    payload = canonical_json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(payload)
    os.chmod(temporary, 0o600)
    temporary.replace(path)
    return sha256_bytes(payload)


def validate_commit(commit: str) -> str:
    if not COMMIT_RE.fullmatch(commit):
        raise BuildFailure(
            "validate-input",
            "source commit must be exactly 40 lowercase hexadecimal characters",
        )
    return commit


def validate_image_tag(reference: str) -> str:
    if not isinstance(reference, str) or not reference or len(reference) > 384:
        raise BuildFailure("validate-input", "image tag is empty or too long")
    if any(character.isspace() for character in reference) or "@" in reference:
        raise BuildFailure("validate-input", "image reference must be an explicit local tag")
    last_slash = reference.rfind("/")
    last_colon = reference.rfind(":")
    if last_colon <= last_slash:
        raise BuildFailure("validate-input", "image reference must include an explicit tag")
    repository, tag = reference[:last_colon], reference[last_colon + 1 :]
    if not repository or not TAG_RE.fullmatch(tag) or tag.lower() == "latest":
        raise BuildFailure("validate-input", "image reference has an invalid or floating tag")
    components = repository.split("/")
    if any(not component for component in components):
        raise BuildFailure("validate-input", "image repository contains an empty component")
    first = components[0]
    if ":" in first:
        host, port = first.rsplit(":", 1)
        if not HOST_RE.fullmatch(host) or not port.isdigit() or not (1 <= int(port) <= 65535):
            raise BuildFailure("validate-input", "image registry host or port is invalid")
        components = components[1:]
    for component in components:
        if not NAME_COMPONENT_RE.fullmatch(component):
            raise BuildFailure("validate-input", "image repository component is invalid")
    return reference


def validate_config(config: BuildConfig) -> None:
    validate_commit(config.source_commit)
    if config.platform not in {"linux/arm64", "linux/amd64"}:
        raise BuildFailure("validate-input", "platform must be linux/arm64 or linux/amd64")
    expected_keys = {spec.key for spec in IMAGE_SPECS}
    if set(config.tags) != expected_keys:
        raise BuildFailure("validate-input", "runtime, transformer, and verifier tags are required")
    validated = [validate_image_tag(config.tags[spec.key]) for spec in IMAGE_SPECS]
    if len(set(validated)) != len(validated):
        raise BuildFailure("validate-input", "all three image tags must be distinct")
    root = config.repository_root.resolve()
    if not root.is_dir():
        raise BuildFailure("validate-input", "repository root is not a directory")


def capacity_snapshot(
    path: Path,
    stage: str,
    evidence: list[dict[str, Any]],
    *,
    minimum_free_bytes: int = HARD_STOP_FREE_BYTES + 1,
) -> dict[str, Any]:
    free = shutil.disk_usage(path).free
    snapshot = {
        "stage": stage,
        "checked_at": utc_now(),
        "free_bytes": free,
        "free_gib": round(free / GIB, 3),
        "required_free_bytes": minimum_free_bytes,
        "hard_stop_bytes": HARD_STOP_FREE_BYTES,
    }
    evidence.append(snapshot)
    if free <= HARD_STOP_FREE_BYTES:
        raise CapacityFailure(
            stage,
            f"capacity hard stop reached ({free} bytes free; must remain above {HARD_STOP_FREE_BYTES})",
        )
    if free < minimum_free_bytes:
        raise CapacityFailure(
            stage,
            f"insufficient capacity ({free} bytes free; requires at least {minimum_free_bytes})",
        )
    return snapshot


def terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=10)


def run_command(
    argv: Sequence[str],
    *,
    cwd: Path,
    log_path: Path,
    stage: str,
    capacity_path: Path,
    capacity_evidence: list[dict[str, Any]],
    command_evidence: list[dict[str, Any]],
    minimum_start_bytes: int = HARD_STOP_FREE_BYTES + 1,
    allow_failure: bool = False,
) -> CommandResult:
    """Run an argv-only subprocess while enforcing the hard capacity floor."""

    if not argv or not all(isinstance(item, str) and item for item in argv):
        raise BuildFailure(stage, "command must be a non-empty argv sequence")
    capacity_snapshot(
        capacity_path,
        f"{stage}:before",
        capacity_evidence,
        minimum_free_bytes=minimum_start_bytes,
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    event: dict[str, Any] = {
        "stage": stage,
        "argv": list(argv),
        "log_path": str(log_path),
        "started_at": utc_now(),
        "status": "RUNNING",
    }
    command_evidence.append(event)
    with log_path.open("wb") as log:
        try:
            process = subprocess.Popen(
                list(argv),
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                shell=False,
                start_new_session=True,
            )
        except OSError as exc:
            event.update(status="FAILED_TO_START", completed_at=utc_now())
            raise BuildFailure(stage, f"command could not start: {type(exc).__name__}") from exc
        try:
            while True:
                try:
                    returncode = process.wait(timeout=CAPACITY_POLL_SECONDS)
                    break
                except subprocess.TimeoutExpired:
                    try:
                        capacity_snapshot(
                            capacity_path,
                            f"{stage}:running",
                            capacity_evidence,
                        )
                    except CapacityFailure:
                        terminate_process_group(process)
                        event.update(status="STOPPED_CAPACITY", completed_at=utc_now())
                        raise
        except KeyboardInterrupt:
            terminate_process_group(process)
            event.update(status="INTERRUPTED", completed_at=utc_now())
            raise
    event.update(
        status="PASSED" if returncode == 0 else "FAILED",
        returncode=returncode,
        completed_at=utc_now(),
    )
    capacity_snapshot(capacity_path, f"{stage}:after", capacity_evidence)
    if returncode != 0 and not allow_failure:
        raise BuildFailure(stage, f"command failed with exit code {returncode}; see evidence log")
    return CommandResult(returncode=returncode, log_path=log_path)


def validate_archive_path(name: str) -> PurePosixPath:
    if not name or "\x00" in name or "\\" in name or name.startswith("/"):
        raise BuildFailure("extract-archive", "archive contains an unsafe path")
    if name.endswith("/"):
        name = name[:-1]
    path = PurePosixPath(name)
    if not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise BuildFailure("extract-archive", "archive contains path traversal")
    if len(name.encode("utf-8")) > 4096 or any(
        len(part.encode("utf-8")) > 255 for part in path.parts
    ):
        raise BuildFailure("extract-archive", "archive path exceeds filesystem limits")
    if unicodedata.normalize("NFC", name) != name:
        raise BuildFailure("extract-archive", "archive path is not Unicode NFC canonical")
    return path


def parse_git_tree(payload: bytes) -> dict[str, str]:
    entries: dict[str, str] = {}
    collision_keys: set[str] = set()
    for raw_record in payload.split(b"\x00"):
        if not raw_record:
            continue
        try:
            metadata, raw_path = raw_record.split(b"\t", 1)
            mode, object_type, object_id = metadata.split(b" ", 2)
            path = raw_path.decode("utf-8", errors="strict")
        except (ValueError, UnicodeDecodeError) as exc:
            raise BuildFailure("inspect-tree", "git tree record is malformed") from exc
        validate_archive_path(path)
        if mode == b"160000" or object_type == b"commit":
            raise BuildFailure("inspect-tree", f"submodule is forbidden: {path}")
        if mode == b"120000":
            raise BuildFailure("inspect-tree", f"symbolic link is forbidden: {path}")
        if object_type != b"blob" or mode not in {b"100644", b"100755"}:
            raise BuildFailure("inspect-tree", f"unsupported git tree entry: {path}")
        if not GIT_OBJECT_RE.fullmatch(object_id):
            raise BuildFailure("inspect-tree", "git tree object identity is malformed")
        collision_key = unicodedata.normalize("NFC", path).casefold()
        if path in entries or collision_key in collision_keys:
            raise BuildFailure("inspect-tree", f"colliding git tree path: {path}")
        entries[path] = mode.decode("ascii")
        collision_keys.add(collision_key)
    if not entries:
        raise BuildFailure("inspect-tree", "git commit has no regular files")
    return entries


def file_declares_git_lfs(path: Path) -> bool:
    if path.name == ".lfsconfig":
        return True
    if path.name != ".gitattributes":
        return False
    with path.open("rb") as stream:
        for line in stream:
            if len(line) > 1024 * 1024:
                raise BuildFailure("extract-archive", ".gitattributes line is unreasonably large")
            if LFS_ATTRIBUTE_RE.search(line):
                return True
    return False


def inspect_git_archive_limits(archive_path: Path) -> dict[str, int]:
    """Count tar entries and regular bytes before creating an extraction root."""

    entry_count = 0
    regular_byte_count = 0
    with tarfile.open(archive_path, mode="r:") as archive:
        for member in archive:
            entry_count += 1
            if entry_count > MAX_ARCHIVE_ENTRY_COUNT:
                raise BuildFailure(
                    "extract-archive:preflight",
                    f"archive exceeds the {MAX_ARCHIVE_ENTRY_COUNT} entry hard limit",
                )
            if member.isfile():
                if not isinstance(member.size, int) or member.size < 0:
                    raise BuildFailure(
                        "extract-archive:preflight", "archive has an invalid regular-file size"
                    )
                regular_byte_count += member.size
                if regular_byte_count > MAX_ARCHIVE_REGULAR_BYTES:
                    raise BuildFailure(
                        "extract-archive:preflight",
                        f"archive exceeds the {MAX_ARCHIVE_REGULAR_BYTES} regular-byte hard limit",
                    )
    return {
        "entry_count": entry_count,
        "regular_byte_count": regular_byte_count,
    }


def safe_extract_git_archive(
    archive_path: Path,
    destination: Path,
    expected_files: dict[str, str],
    *,
    capacity_path: Path | None = None,
    capacity_evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Extract only exact regular files from a validated ``git archive`` tar."""

    effective_capacity_path = capacity_path or destination.parent
    effective_capacity_evidence = capacity_evidence if capacity_evidence is not None else []
    archive_limits = inspect_git_archive_limits(archive_path)
    capacity_snapshot(
        effective_capacity_path,
        "extract-archive:preflight",
        effective_capacity_evidence,
        minimum_free_bytes=(
            HARD_STOP_FREE_BYTES
            + archive_limits["regular_byte_count"]
            + EXTRACTION_METADATA_RESERVE_BYTES
            + archive_limits["entry_count"] * EXTRACTION_ENTRY_ALLOCATION_GUARD_BYTES
            + 1
        ),
    )
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    destination_root = destination.resolve()
    extracted: set[str] = set()
    collision_keys: set[str] = set()
    manifest_entries: list[dict[str, Any]] = []
    expected_directories = {
        PurePosixPath(*PurePosixPath(file_path).parts[:index]).as_posix()
        for file_path in expected_files
        for index in range(1, len(PurePosixPath(file_path).parts))
    }
    with tarfile.open(archive_path, mode="r:") as archive:
        for entry_index, member in enumerate(archive):
            capacity_snapshot(
                effective_capacity_path,
                f"extract-archive:file-{entry_index}:before",
                effective_capacity_evidence,
                minimum_free_bytes=(
                    HARD_STOP_FREE_BYTES
                    + (
                        max(
                            min(member.size, EXTRACTION_BATCH_BYTES),
                            EXTRACTION_ENTRY_ALLOCATION_GUARD_BYTES,
                        )
                        if member.isfile()
                        else EXTRACTION_ENTRY_ALLOCATION_GUARD_BYTES
                    )
                    + 1
                ),
            )
            path = validate_archive_path(member.name)
            relative = path.as_posix()
            collision_key = unicodedata.normalize("NFC", relative).casefold()
            if collision_key in collision_keys:
                raise BuildFailure("extract-archive", f"archive path collision: {relative}")
            collision_keys.add(collision_key)
            target = destination.joinpath(*path.parts)
            resolved_parent = target.parent.resolve()
            if resolved_parent != destination_root and destination_root not in resolved_parent.parents:
                raise BuildFailure("extract-archive", "archive path escapes the destination")
            if member.isdir():
                if relative not in expected_directories:
                    raise BuildFailure(
                        "extract-archive", f"archive contains an undeclared directory: {relative}"
                    )
                target.mkdir(mode=0o755, parents=True, exist_ok=True)
                continue
            if not member.isfile() or member.issym() or member.islnk():
                raise BuildFailure("extract-archive", f"archive link or special entry is forbidden: {relative}")
            if member.sparse is not None:
                raise BuildFailure("extract-archive", f"sparse archive entry is forbidden: {relative}")
            expected_mode = expected_files.get(relative)
            if expected_mode is None or relative in extracted:
                raise BuildFailure("extract-archive", f"archive contains an undeclared file: {relative}")
            member_executable = bool(member.mode & 0o111)
            expected_executable = expected_mode == "100755"
            if member_executable != expected_executable:
                raise BuildFailure("extract-archive", f"archive mode differs from git tree: {relative}")
            target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise BuildFailure("extract-archive", f"archive file cannot be read: {relative}")
            digest = hashlib.sha256()
            byte_count = 0
            prefix = bytearray()
            try:
                with target.open("xb") as output:
                    batch_index = 0
                    while byte_count < member.size:
                        requested_bytes = min(EXTRACTION_BATCH_BYTES, member.size - byte_count)
                        capacity_snapshot(
                            effective_capacity_path,
                            f"extract-archive:file-{entry_index}:batch-{batch_index}:before",
                            effective_capacity_evidence,
                            minimum_free_bytes=(
                                HARD_STOP_FREE_BYTES
                                + max(requested_bytes, EXTRACTION_ENTRY_ALLOCATION_GUARD_BYTES)
                                + 1
                            ),
                        )
                        chunk = source.read(requested_bytes)
                        if not chunk:
                            break
                        if len(chunk) > requested_bytes:
                            raise BuildFailure(
                                "extract-archive", f"archive reader exceeded batch bound: {relative}"
                            )
                        if len(prefix) < 256:
                            prefix.extend(chunk[: 256 - len(prefix)])
                        digest.update(chunk)
                        output.write(chunk)
                        byte_count += len(chunk)
                        batch_index += 1
            finally:
                source.close()
            if byte_count != member.size:
                raise BuildFailure("extract-archive", f"archive size mismatch: {relative}")
            if bytes(prefix).startswith(LFS_POINTER_PREFIX):
                raise BuildFailure("extract-archive", f"Git LFS pointer is forbidden: {relative}")
            if file_declares_git_lfs(target):
                raise BuildFailure("extract-archive", f"Git LFS configuration is forbidden: {relative}")
            os.chmod(target, 0o755 if expected_executable else 0o644)
            extracted.add(relative)
            manifest_entries.append(
                {
                    "path": relative,
                    "mode": expected_mode,
                    "byte_count": byte_count,
                    "sha256": digest.hexdigest(),
                }
            )
    missing = sorted(set(expected_files) - extracted)
    if missing:
        raise BuildFailure("extract-archive", f"archive omitted {len(missing)} git tree files")
    manifest_entries.sort(key=lambda entry: entry["path"].encode("utf-8"))
    manifest = {
        "schema_version": "1.0",
        "algorithm": "sha256-canonical-git-tree-v1",
        "files": manifest_entries,
    }
    return {
        "manifest": manifest,
        "context_sha256": sha256_bytes(canonical_json_bytes(manifest)),
        "file_count": len(manifest_entries),
        "byte_count": sum(entry["byte_count"] for entry in manifest_entries),
        "archive_entry_count": archive_limits["entry_count"],
        "archive_regular_byte_count": archive_limits["regular_byte_count"],
    }


def source_status_document(
    *,
    source_commit: str,
    context_sha256: str,
    file_count: int,
    byte_count: int,
) -> dict[str, Any]:
    validate_commit(source_commit)
    if not SHA256_RE.fullmatch(context_sha256):
        raise BuildFailure("source-status", "context digest is malformed")
    if (
        not isinstance(file_count, int)
        or isinstance(file_count, bool)
        or file_count < 1
        or not isinstance(byte_count, int)
        or isinstance(byte_count, bool)
        or byte_count < 0
    ):
        raise BuildFailure("source-status", "source file and byte counts are invalid")
    return {
        "schema_version": "1.0",
        "source_commit": source_commit,
        "source_state": "CLEAN_SOURCE",
        "source_dirty": False,
        "source_context": {
            "algorithm": "sha256-canonical-git-tree-v1",
            "sha256": context_sha256,
            "file_count": file_count,
            "byte_count": byte_count,
        },
        "archive_validation": {
            "archive_format": "git-archive-tar",
            "safe_extraction": "PASSED",
            "path_validation": "PASSED",
            "submodules": "ABSENT",
            "symlinks_and_hardlinks": "ABSENT",
            "git_lfs_pointers": "ABSENT",
        },
    }


def docker_build_argv(
    spec: ImageSpec,
    *,
    tag: str,
    platform: str,
    source_commit: str,
    context_sha256: str,
    source_status_sha256: str,
    context_dir: Path,
) -> list[str]:
    validate_image_tag(tag)
    validate_commit(source_commit)
    if not SHA256_RE.fullmatch(context_sha256) or not SHA256_RE.fullmatch(source_status_sha256):
        raise BuildFailure("build-argv", "source context or status digest is malformed")
    return [
        "docker",
        "buildx",
        "build",
        "--load",
        "--pull=false",
        "--progress=plain",
        "--platform",
        platform,
        "--tag",
        tag,
        "--file",
        spec.dockerfile,
        "--build-arg",
        f"ELMOS_SOURCE_REVISION={source_commit}",
        "--build-arg",
        f"ELMOS_SOURCE_CONTEXT_SHA256={context_sha256}",
        "--build-arg",
        f"ELMOS_SOURCE_STATUS_SHA256={source_status_sha256}",
        str(context_dir),
    ]


def validate_built_image(
    record: dict[str, Any],
    *,
    spec: ImageSpec,
    platform: str,
    source_commit: str,
    context_sha256: str,
    source_status_sha256: str,
) -> str:
    image_id = record.get("Id")
    if not isinstance(image_id, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise BuildFailure(f"inspect-{spec.key}", "built image has no immutable local image ID")
    expected_platform = PLATFORM_IMAGE_METADATA.get(platform)
    if expected_platform is None:
        raise BuildFailure(f"inspect-{spec.key}", "requested image platform is unsupported")
    expected_os, expected_architecture, expected_variant = expected_platform
    actual_variant = record.get("Variant")
    # Docker Desktop's local image inspect omits Variant for images loaded from
    # a single-platform build.  The requested OS and architecture still remain
    # explicit.  Treat a missing variant as unspecified, while rejecting a
    # variant that is present and conflicts with the requested platform.
    variant_mismatch = actual_variant not in (None, "", expected_variant)
    if (
        record.get("Os") != expected_os
        or record.get("Architecture") != expected_architecture
        or variant_mismatch
    ):
        raise BuildFailure(
            f"inspect-{spec.key}",
            "built image OS, architecture, or variant differs from the requested platform",
        )
    config = record.get("Config") or {}
    if config.get("User") != spec.expected_user:
        raise BuildFailure(f"inspect-{spec.key}", "built image non-root user is incorrect")
    labels = config.get("Labels") or {}
    required = {
        "org.opencontainers.image.revision": source_commit,
        "io.elmos.evidence.scope": "spring-modernization-local",
        "io.elmos.evidence.class": "LOCAL_NON_CERTIFYING",
        "io.elmos.build.source-status": "CLEAN_SOURCE",
        "io.elmos.build.source-dirty": "false",
        "io.elmos.build.context-sha256": context_sha256,
        "io.elmos.build.context-status-sha256": source_status_sha256,
    }
    for key, expected in required.items():
        if labels.get(key) != expected:
            raise BuildFailure(f"inspect-{spec.key}", f"built image label is absent or incorrect: {key}")
    return image_id


def parse_single_inspect(log_path: Path, *, stage: str) -> dict[str, Any]:
    try:
        value = json.loads(log_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BuildFailure(stage, "docker inspect returned malformed JSON") from exc
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        raise BuildFailure(stage, "docker inspect did not return exactly one image")
    return value[0]


def ensure_tag_absent(
    tag: str,
    *,
    root: Path,
    evidence_dir: Path,
    capacity_evidence: list[dict[str, Any]],
    command_evidence: list[dict[str, Any]],
) -> None:
    key = hashlib.sha256(tag.encode("utf-8")).hexdigest()[:12]
    result = run_command(
        ["docker", "image", "inspect", tag],
        cwd=root,
        log_path=evidence_dir / f"preflight-image-{key}.log",
        stage=f"preflight-tag-{key}",
        capacity_path=root,
        capacity_evidence=capacity_evidence,
        command_evidence=command_evidence,
        minimum_start_bytes=MINIMUM_BUILD_FREE_BYTES,
        allow_failure=True,
    )
    if result.returncode == 0:
        raise BuildFailure("preflight-tags", f"refusing to overwrite existing image tag: {tag}")
    detail = result.log_path.read_text(encoding="utf-8", errors="replace").lower()
    if "no such image" not in detail and "no such object" not in detail:
        raise BuildFailure("preflight-tags", "docker image inspection failed for a reason other than absence")


def smoke_argv(
    *,
    config: BuildConfig,
    image_ids: dict[str, str],
    context_sha256: str,
    source_status_sha256: str,
    source_root: Path | None = None,
) -> list[str]:
    smoke_script = (source_root or config.repository_root) / (
        "scripts/operations/run_spring_docker_smoke.py"
    )
    argv = [
        sys.executable,
        str(smoke_script),
        "--runtime",
        config.tags["runtime"],
        "--transformer",
        config.tags["transformer"],
        "--verifier",
        config.tags["verifier"],
        "--runtime-image-id",
        image_ids["runtime"],
        "--transformer-image-id",
        image_ids["transformer"],
        "--verifier-image-id",
        image_ids["verifier"],
        "--expected-revision",
        config.source_commit,
    ]
    for key in ("runtime", "transformer", "verifier"):
        argv.extend([f"--{key}-context-digest", context_sha256])
    for key in ("runtime", "transformer", "verifier"):
        argv.extend([f"--{key}-source-status-digest", source_status_sha256])
    for key in ("runtime", "transformer", "verifier"):
        argv.extend([f"--{key}-source-state", "CLEAN_SOURCE"])
    return argv


def verify_repository_and_commit(
    *,
    config: BuildConfig,
    capacity_evidence: list[dict[str, Any]],
    command_evidence: list[dict[str, Any]],
) -> None:
    root = config.repository_root.resolve()
    top = run_command(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=root,
        log_path=config.evidence_dir / "git-toplevel.log",
        stage="verify-repository",
        capacity_path=root,
        capacity_evidence=capacity_evidence,
        command_evidence=command_evidence,
    )
    if Path(top.log_path.read_text(encoding="utf-8").strip()).resolve() != root:
        raise BuildFailure("verify-repository", "repository root is not the exact Git top level")
    commit = run_command(
        ["git", "rev-parse", "--verify", f"{config.source_commit}^{{commit}}"],
        cwd=root,
        log_path=config.evidence_dir / "git-commit.log",
        stage="verify-commit",
        capacity_path=root,
        capacity_evidence=capacity_evidence,
        command_evidence=command_evidence,
    )
    if commit.log_path.read_text(encoding="utf-8").strip() != config.source_commit:
        raise BuildFailure("verify-commit", "Git did not resolve the exact requested commit")


def base_receipt(config: BuildConfig) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "evidence_class": "LOCAL_NON_CERTIFYING_CONTAINER_BUILD",
        "certification_eligible": False,
        "status": "RUNNING",
        "overall_status": "RUNNING",
        "created_at": utc_now(),
        "source_commit": config.source_commit,
        "platform": config.platform,
        "tags": dict(config.tags),
        "capacity_policy": {
            "minimum_build_start_bytes": MINIMUM_BUILD_FREE_BYTES,
            "hard_stop_bytes": HARD_STOP_FREE_BYTES,
        },
        "capacity_checks": [],
        "commands": [],
        "images": {spec.key: {"status": "NOT_RUN"} for spec in IMAGE_SPECS},
        "external_boundaries": {
            "registry_push": "NOT_RUN",
            "customer_repository": "NOT_RUN",
            "independent_verification": "NOT_RUN",
            "external_certification": "NOT_RUN",
        },
        "production_ready": False,
        "certified": False,
    }


def finalize_failed_receipt(
    receipt: dict[str, Any],
    *,
    failure: dict[str, str],
) -> None:
    """Close every active receipt state without manufacturing unrun results."""

    receipt.update(
        status="FAILED",
        overall_status="FAILED",
        completed_at=utc_now(),
        failure=failure,
    )
    for image in receipt.get("images", {}).values():
        if image.get("status") == "RUNNING":
            image["status"] = "FAILED"
            image["failure"] = dict(failure)


def build_clean_source_images(config: BuildConfig) -> tuple[int, dict[str, Any], Path]:
    """Execute the build and always persist a pass or fail receipt."""

    receipt = base_receipt(config)
    evidence_path = config.evidence_dir / "spring-clean-source-image-build.json"
    try:
        validate_config(config)
        config.evidence_dir.mkdir(parents=True, exist_ok=True)
        capacity_snapshot(
            config.repository_root,
            "preflight-capacity",
            receipt["capacity_checks"],
            minimum_free_bytes=MINIMUM_BUILD_FREE_BYTES,
        )
        verify_repository_and_commit(
            config=config,
            capacity_evidence=receipt["capacity_checks"],
            command_evidence=receipt["commands"],
        )
        for spec in IMAGE_SPECS:
            ensure_tag_absent(
                config.tags[spec.key],
                root=config.repository_root,
                evidence_dir=config.evidence_dir,
                capacity_evidence=receipt["capacity_checks"],
                command_evidence=receipt["commands"],
            )
        with tempfile.TemporaryDirectory(prefix="elmos-spring-clean-source-") as temporary:
            work = Path(temporary)
            archive_path = work / "source.tar"
            context_dir = work / "context"
            tree = run_command(
                ["git", "ls-tree", "-r", "-z", "--full-tree", config.source_commit],
                cwd=config.repository_root,
                log_path=config.evidence_dir / "git-tree.bin",
                stage="inspect-tree",
                capacity_path=config.repository_root,
                capacity_evidence=receipt["capacity_checks"],
                command_evidence=receipt["commands"],
                minimum_start_bytes=MINIMUM_BUILD_FREE_BYTES,
            )
            expected_files = parse_git_tree(tree.log_path.read_bytes())
            run_command(
                [
                    "git",
                    "archive",
                    "--format=tar",
                    f"--output={archive_path}",
                    config.source_commit,
                ],
                cwd=config.repository_root,
                log_path=config.evidence_dir / "git-archive.log",
                stage="create-archive",
                capacity_path=config.repository_root,
                capacity_evidence=receipt["capacity_checks"],
                command_evidence=receipt["commands"],
                minimum_start_bytes=MINIMUM_BUILD_FREE_BYTES,
            )
            extracted = safe_extract_git_archive(
                archive_path,
                context_dir,
                expected_files,
                capacity_path=config.repository_root,
                capacity_evidence=receipt["capacity_checks"],
            )
            capacity_snapshot(
                config.repository_root,
                "extract-archive:after",
                receipt["capacity_checks"],
                minimum_free_bytes=MINIMUM_BUILD_FREE_BYTES,
            )
            context_sha256 = extracted["context_sha256"]
            manifest_path = config.evidence_dir / "spring-clean-source-context-manifest.json"
            manifest_sha256 = write_canonical_json(manifest_path, extracted["manifest"])
            if manifest_sha256 != context_sha256:
                raise BuildFailure("source-manifest", "persisted context manifest digest changed")
            status = source_status_document(
                source_commit=config.source_commit,
                context_sha256=context_sha256,
                file_count=extracted["file_count"],
                byte_count=extracted["byte_count"],
            )
            status_path = config.evidence_dir / "spring-clean-source-status.json"
            source_status_sha256 = write_canonical_json(status_path, status)
            receipt["source"] = {
                "state": "CLEAN_SOURCE",
                "dirty": False,
                "context_sha256": context_sha256,
                "context_manifest_path": str(manifest_path),
                "context_manifest_sha256": manifest_sha256,
                "status_path": str(status_path),
                "status_sha256": source_status_sha256,
                "file_count": extracted["file_count"],
                "byte_count": extracted["byte_count"],
                "archive_entry_count": extracted["archive_entry_count"],
                "archive_regular_byte_count": extracted["archive_regular_byte_count"],
                "archive_sha256": sha256_file(archive_path),
            }
            image_ids: dict[str, str] = {}
            for spec in IMAGE_SPECS:
                capacity_snapshot(
                    config.repository_root,
                    f"build-{spec.key}:capacity-gate",
                    receipt["capacity_checks"],
                    minimum_free_bytes=MINIMUM_BUILD_FREE_BYTES,
                )
                receipt["images"][spec.key] = {"status": "RUNNING", "tag": config.tags[spec.key]}
                run_command(
                    docker_build_argv(
                        spec,
                        tag=config.tags[spec.key],
                        platform=config.platform,
                        source_commit=config.source_commit,
                        context_sha256=context_sha256,
                        source_status_sha256=source_status_sha256,
                        context_dir=context_dir,
                    ),
                    cwd=context_dir,
                    log_path=config.evidence_dir / f"docker-build-{spec.key}.log",
                    stage=f"build-{spec.key}",
                    capacity_path=config.repository_root,
                    capacity_evidence=receipt["capacity_checks"],
                    command_evidence=receipt["commands"],
                    minimum_start_bytes=MINIMUM_BUILD_FREE_BYTES,
                )
                inspect = run_command(
                    ["docker", "image", "inspect", config.tags[spec.key]],
                    cwd=config.repository_root,
                    log_path=config.evidence_dir / f"docker-inspect-{spec.key}.json",
                    stage=f"inspect-{spec.key}",
                    capacity_path=config.repository_root,
                    capacity_evidence=receipt["capacity_checks"],
                    command_evidence=receipt["commands"],
                )
                record = parse_single_inspect(inspect.log_path, stage=f"inspect-{spec.key}")
                image_id = validate_built_image(
                    record,
                    spec=spec,
                    platform=config.platform,
                    source_commit=config.source_commit,
                    context_sha256=context_sha256,
                    source_status_sha256=source_status_sha256,
                )
                image_ids[spec.key] = image_id
                receipt["images"][spec.key] = {
                    "status": "BUILT_LOCAL",
                    "tag": config.tags[spec.key],
                    "image_id": image_id,
                    "declared_user": spec.expected_user,
                }
            capacity_snapshot(
                config.repository_root,
                "smoke:capacity-gate",
                receipt["capacity_checks"],
                minimum_free_bytes=MINIMUM_BUILD_FREE_BYTES,
            )
            smoke = run_command(
                smoke_argv(
                    config=config,
                    image_ids=image_ids,
                    context_sha256=context_sha256,
                    source_status_sha256=source_status_sha256,
                    source_root=context_dir,
                ),
                cwd=context_dir,
                log_path=config.evidence_dir / "spring-docker-smoke.json",
                stage="smoke",
                capacity_path=config.repository_root,
                capacity_evidence=receipt["capacity_checks"],
                command_evidence=receipt["commands"],
                minimum_start_bytes=MINIMUM_BUILD_FREE_BYTES,
            )
            try:
                smoke_result = json.loads(smoke.log_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise BuildFailure("smoke", "smoke runner did not emit valid JSON evidence") from exc
            if smoke_result.get("status") != "PASSED_LOCAL":
                raise BuildFailure("smoke", "smoke runner did not pass all three images")
            receipt["smoke"] = {
                "status": "PASSED_LOCAL",
                "path": str(smoke.log_path),
                "sha256": sha256_file(smoke.log_path),
            }
        receipt["status"] = "PASSED_LOCAL"
        receipt["overall_status"] = "PASSED_LOCAL"
        receipt["completed_at"] = utc_now()
        write_json(evidence_path, receipt)
        return 0, receipt, evidence_path
    except (Exception, KeyboardInterrupt) as exc:  # noqa: BLE001 - CLI must emit evidence.
        interrupted_command = next(
            (
                command
                for command in reversed(receipt["commands"])
                if command.get("status") == "INTERRUPTED"
            ),
            None,
        )
        if isinstance(exc, BuildFailure):
            stage = exc.stage
            message = str(exc)
        elif isinstance(exc, KeyboardInterrupt):
            stage = (
                interrupted_command.get("stage", "interrupted")
                if interrupted_command
                else "interrupted"
            )
            message = "operation interrupted"
        else:
            stage = "unexpected"
            message = f"unexpected {type(exc).__name__}"
        finalize_failed_receipt(
            receipt,
            failure={"stage": stage, "type": type(exc).__name__, "message": message},
        )
        try:
            config.evidence_dir.mkdir(parents=True, exist_ok=True)
            write_json(evidence_path, receipt)
        except OSError:
            pass
        return (130 if isinstance(exc, KeyboardInterrupt) else 1), receipt, evidence_path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--runtime-tag", required=True)
    parser.add_argument("--transformer-tag", required=True)
    parser.add_argument("--verifier-tag", required=True)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--repository-root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument(
        "--platform",
        choices=("linux/arm64", "linux/amd64"),
        default="linux/arm64",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    config = BuildConfig(
        repository_root=args.repository_root.resolve(),
        source_commit=args.source_commit,
        evidence_dir=args.evidence_dir.resolve(),
        platform=args.platform,
        tags={
            "runtime": args.runtime_tag,
            "transformer": args.transformer_tag,
            "verifier": args.verifier_tag,
        },
    )
    returncode, receipt, evidence_path = build_clean_source_images(config)
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "evidence": str(evidence_path),
                "source_commit": config.source_commit,
                "certification_eligible": False,
                "certified": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
