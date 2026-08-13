#!/usr/bin/env python3
"""Replay one packed route's frozen evidence-integrity validation.

This launcher does not build or execute the source/target behavior harnesses and
therefore does not reproduce the native Batch 29 route run.  It does perform
compiler-backed semantic re-lift plus formal replay over the copied,
content-addressed closure artifacts with the frozen Batch 29 validator shipped
beside it.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import runpy
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any

REPLAY_SCOPE = "evidence-integrity-and-semantic-closure-only"
NATIVE_REEXECUTION_STATUS = "NOT_RUN"
FROZEN_VALIDATOR_RELATIVE = "certification/replay/scripts/batch29/validate_route.py"
FROZEN_SCHEMA_RELATIVE = (
    "certification/replay/schemas/batch29/formal-equivalence-evidence.schema.json"
)
FROZEN_FORMAL_INPUT_SCHEMA_RELATIVE = (
    "certification/replay/schemas/batch29/formal-input.schema.json"
)
FROZEN_IDENTIFIER_PLAN_SCHEMA_RELATIVE = (
    "certification/replay/schemas/batch29/identifier-plan.schema.json"
)
FROZEN_MODULE_SCHEMA_RELATIVE = (
    "certification/replay/schemas/batch29/module-equivalence-evidence.schema.json"
)
FROZEN_MODULE_CASE_SCHEMA_RELATIVE = (
    "certification/replay/schemas/batch29/module-case-manifest.schema.json"
)
FROZEN_MODULE_FORMAL_INPUT_SCHEMA_RELATIVE = (
    "certification/replay/schemas/batch29/formal-input-module-function.schema.json"
)
LAUNCHER_RELATIVE = "certification/replay/validate_packed_route.py"
REQUIRED_REPLAY_FILES = {
    LAUNCHER_RELATIVE: "replay-tool",
    FROZEN_VALIDATOR_RELATIVE: "replay-tool",
    FROZEN_SCHEMA_RELATIVE: "replay-schema",
}
MODULE_REPLAY_FILES = {
    FROZEN_FORMAL_INPUT_SCHEMA_RELATIVE: "replay-schema",
    FROZEN_IDENTIFIER_PLAN_SCHEMA_RELATIVE: "replay-schema",
    FROZEN_MODULE_SCHEMA_RELATIVE: "replay-schema",
    FROZEN_MODULE_CASE_SCHEMA_RELATIVE: "replay-schema",
    FROZEN_MODULE_FORMAL_INPUT_SCHEMA_RELATIVE: "replay-schema",
}
ENGINE_MANIFEST_RELATIVE = "certification/formal-artifacts/engine-source-manifest.json"
ENGINE_SOURCE_PREFIX = "certification/formal-artifacts/engine-sources/"
ENGINE_SOURCE_ROOT_RELATIVE = ENGINE_SOURCE_PREFIX + "engines/polyglot-route-engine/src"
PYTHON_ARCHIVE_RELATIVE = (
    "runtime/python/sha256-"
    "22625deaf5757e7c266cf1a096c9151a06b598b1e14632a2ec9993d58ec5fe84.tar.gz"
)
PYTHON_ARCHIVE_SHA256 = (
    "22625deaf5757e7c266cf1a096c9151a06b598b1e14632a2ec9993d58ec5fe84"
)
PYTHON_ARCHIVE_BYTES = 17_667_661
PYTHON_SOURCE_TREE_SHA256 = (
    "1400403c757cb4da3ce2df42d17d02e1368c54afd46bbed71ae84e25d081a154"
)
TYPESCRIPT_CAPTURED_ROOT_RELATIVE = (
    "runtime/typescript/sha256-"
    "61c079831c707d58ee72cda08c279d3575f24f4d87f13d93aeed00b1d11a225a"
)
TYPESCRIPT_SOURCE_MANIFEST_SHA256 = (
    "61c079831c707d58ee72cda08c279d3575f24f4d87f13d93aeed00b1d11a225a"
)
TYPESCRIPT_RUNTIME_MANIFEST_SHA256 = (
    "2157e43e757e433c733e144df7409a54f5040faa22af4a9b13de977a663fd939"
)
TYPESCRIPT_CLOSURE_SHA256 = (
    "aaab28fada5888d767a49f86d40e5a0c9073b23412257ccb3755e9c8fb8080d9"
)
TYPESCRIPT_FILE_COUNT = 108
TYPESCRIPT_CLOSURE_BYTES = 19_067_381
TYPESCRIPT_CANONICAL_ROOT = Path(
    "/Users/stephen/.local/share/elmos/toolchains/typescript/5.9.2/"
    "sha256-61c079831c707d58ee72cda08c279d3575f24f4d87f13d93aeed00b1d11a225a"
)
TYPESCRIPT_CANONICAL_UID = 501
TYPESCRIPT_CANONICAL_GID = 20
TYPESCRIPT_CANONICAL_PACKAGE_NLINK = 6
TYPESCRIPT_CANONICAL_DIRECTORY_NLINKS = {"bin": 3, "lib": 107}
MAX_ERROR_BYTES = 2_048

sys.dont_write_bytecode = True


def reject_non_finite_json(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(
        path.read_text(encoding="utf-8"), parse_constant=reject_non_finite_json
    )
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def bounded_error(value: object, route: Path) -> str:
    text = str(value)
    for sensitive in {str(route), str(route.resolve(strict=False))}:
        text = text.replace(sensitive, "<route>")
    text = "".join(
        character if character in "\n\t" or 32 <= ord(character) < 127 else "?"
        for character in text
    )
    text = " | ".join(line[:512] for line in text.splitlines()[-8:])
    return text.encode("utf-8")[:MAX_ERROR_BYTES].decode("utf-8", errors="ignore")


def resolve_route_file(route: Path, relative: str) -> Path:
    if (
        not relative
        or "\\" in relative
        or "://" in relative
        or Path(relative).is_absolute()
        or any(part in {"", ".", ".."} for part in Path(relative).parts)
    ):
        raise ValueError(f"invalid route-relative replay path: {relative}")
    candidate = route / relative
    resolved = candidate.resolve(strict=True)
    resolved.relative_to(route)
    if candidate.is_symlink() or not resolved.is_file():
        raise ValueError(f"replay member is not a regular file: {relative}")
    return resolved


def validate_bound_artifact(
    route: Path,
    references: dict[str, dict[str, Any]],
    relative: str,
    role: str,
) -> Path:
    reference = references.get(relative)
    if reference is None or reference.get("role") != role:
        raise ValueError(f"{relative} is not bound as {role}")
    path = resolve_route_file(route, relative)
    if reference.get("sha256") != sha256_file(path):
        raise ValueError(f"{relative} digest mismatch")
    if reference.get("bytes") != path.stat().st_size:
        raise ValueError(f"{relative} byte count mismatch")
    return path


def validate_runtime_source_receipts(
    manifest: dict[str, Any],
) -> dict[str, tuple[str, int, str]]:
    """Validate fixed Python/TypeScript bootstrap identities independently."""

    receipts = manifest.get("runtime_source_receipts")
    if not isinstance(receipts, dict) or set(receipts) != {
        "python_source_archive",
        "typescript_compiler_closure",
    }:
        raise ValueError("engine runtime source receipts are not exact")
    python = receipts.get("python_source_archive")
    if not isinstance(python, dict) or set(python) != {
        "schema_version",
        "capture_relative_path",
        "sha256",
        "bytes",
        "mode",
        "uid",
        "gid",
        "nlink",
        "source_tree_sha256",
        "source_tree_record_count",
        "source_tree_file_count",
        "source_tree_bytes",
    }:
        raise ValueError("Python source archive receipt is not exact")
    if (
        python.get("schema_version") != 1
        or python.get("capture_relative_path") != PYTHON_ARCHIVE_RELATIVE
        or python.get("sha256") != PYTHON_ARCHIVE_SHA256
        or python.get("bytes") != PYTHON_ARCHIVE_BYTES
        or python.get("mode") != "0444"
        or python.get("nlink") != 1
        or python.get("source_tree_sha256") != PYTHON_SOURCE_TREE_SHA256
        or python.get("source_tree_record_count") != 1_899
        or python.get("source_tree_file_count") != 1_890
        or python.get("source_tree_bytes") != 47_880_708
        or not isinstance(python.get("uid"), int)
        or isinstance(python.get("uid"), bool)
        or not isinstance(python.get("gid"), int)
        or isinstance(python.get("gid"), bool)
    ):
        raise ValueError("Python source archive receipt identity is invalid")

    typescript = receipts.get("typescript_compiler_closure")
    if not isinstance(typescript, dict) or set(typescript) != {
        "schema_version",
        "capture_relative_path",
        "source_manifest_sha256",
        "runtime_manifest_sha256",
        "compiler_closure_sha256",
        "file_count",
        "bytes",
        "files",
        "semantic_soundness",
    }:
        raise ValueError("TypeScript compiler closure receipt is not exact")
    files = typescript.get("files")
    if not isinstance(files, list) or len(files) != TYPESCRIPT_FILE_COUNT:
        raise ValueError("TypeScript compiler closure file set is not exact")
    paths: list[str] = []
    total_bytes = 0
    for index, record in enumerate(files):
        if not isinstance(record, dict) or set(record) != {
            "path",
            "sha256",
            "bytes",
            "mode",
        }:
            raise ValueError(f"TypeScript compiler closure file {index} is invalid")
        relative = record.get("path")
        digest = record.get("sha256")
        byte_count = record.get("bytes")
        mode = record.get("mode")
        if (
            not isinstance(relative, str)
            or not relative
            or Path(relative).is_absolute()
            or "\\" in relative
            or any(part in {"", ".", ".."} for part in Path(relative).parts)
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or not isinstance(byte_count, int)
            or isinstance(byte_count, bool)
            or byte_count <= 0
            or mode not in {"0444", "0555"}
        ):
            raise ValueError(f"TypeScript compiler closure file {index} is invalid")
        paths.append(relative)
        total_bytes += byte_count
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise ValueError("TypeScript compiler closure paths are not exact")
    source_manifest_sha256 = hashlib.sha256(
        json.dumps(
            {
                "files": [
                    {
                        key: record[key]
                        for key in ("path", "bytes", "sha256")
                    }
                    for record in files
                ]
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    runtime_manifest_sha256 = hashlib.sha256(
        json.dumps(
            {"files": files}, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    if (
        typescript.get("schema_version") != 1
        or typescript.get("capture_relative_path")
        != TYPESCRIPT_CAPTURED_ROOT_RELATIVE
        or typescript.get("source_manifest_sha256")
        != TYPESCRIPT_SOURCE_MANIFEST_SHA256
        or source_manifest_sha256 != TYPESCRIPT_SOURCE_MANIFEST_SHA256
        or typescript.get("runtime_manifest_sha256")
        != TYPESCRIPT_RUNTIME_MANIFEST_SHA256
        or runtime_manifest_sha256 != TYPESCRIPT_RUNTIME_MANIFEST_SHA256
        or typescript.get("compiler_closure_sha256")
        != TYPESCRIPT_CLOSURE_SHA256
        or typescript.get("file_count") != TYPESCRIPT_FILE_COUNT
        or typescript.get("bytes") != TYPESCRIPT_CLOSURE_BYTES
        or total_bytes != TYPESCRIPT_CLOSURE_BYTES
        or typescript.get("semantic_soundness") != "NOT_RUN"
    ):
        raise ValueError("TypeScript compiler closure receipt identity is invalid")
    expected = {
        PYTHON_ARCHIVE_RELATIVE: (
            "sha256:" + PYTHON_ARCHIVE_SHA256,
            PYTHON_ARCHIVE_BYTES,
            "0444",
        )
    }
    expected.update(
        {
            f"{TYPESCRIPT_CAPTURED_ROOT_RELATIVE}/{record['path']}": (
                "sha256:" + str(record["sha256"]),
                int(record["bytes"]),
                str(record["mode"]),
            )
            for record in files
        }
    )
    return expected


def validate_and_insert_engine_source(
    route: Path, references: dict[str, dict[str, Any]]
) -> Path:
    """Validate the complete wrapper-bound source closure before one insertion."""

    if any(
        name == "elmos_polyglot_route" or name.startswith("elmos_polyglot_route.")
        for name in sys.modules
    ):
        raise ValueError("engine modules were imported before source validation")
    manifest_references = [
        relative
        for relative, reference in references.items()
        if reference.get("role") == "engine-source-manifest"
    ]
    if manifest_references != [ENGINE_MANIFEST_RELATIVE]:
        raise ValueError("engine source manifest binding is not exact")
    manifest_path = validate_bound_artifact(
        route,
        references,
        ENGINE_MANIFEST_RELATIVE,
        "engine-source-manifest",
    )
    manifest = load_json(manifest_path)
    if set(manifest) != {
        "schema_version",
        "kind",
        "file_count",
        "files",
        "runtime_source_receipts",
    }:
        raise ValueError("engine source manifest fields are not exact")
    if (
        manifest.get("schema_version") != 1
        or manifest.get("kind") != "polyglot-route-engine-source-bundle"
        or not isinstance(manifest.get("files"), list)
        or manifest.get("file_count") != len(manifest["files"])
        or not manifest["files"]
    ):
        raise ValueError("engine source manifest identity is invalid")

    runtime_repository_records = validate_runtime_source_receipts(manifest)
    manifest_paths: set[str] = set()
    manifest_repository_paths: set[str] = set()
    for item in manifest["files"]:
        if not isinstance(item, dict) or set(item) != {
            "repository_path",
            "captured_path",
            "sha256",
            "bytes",
        }:
            raise ValueError("engine source manifest entry is invalid")
        captured = item.get("captured_path")
        repository_path = item.get("repository_path")
        if (
            not isinstance(captured, str)
            or not captured.startswith(ENGINE_SOURCE_PREFIX)
            or captured in manifest_paths
            or repository_path != captured.removeprefix(ENGINE_SOURCE_PREFIX)
        ):
            raise ValueError("engine source manifest path mapping is invalid")
        manifest_paths.add(captured)
        manifest_repository_paths.add(repository_path)
        reference = references.get(captured)
        if (
            reference is None
            or reference.get("role") != "engine-source"
            or reference.get("sha256") != item.get("sha256")
            or reference.get("bytes") != item.get("bytes")
        ):
            raise ValueError(f"engine source is not wrapper-bound: {captured}")
        captured_source = validate_bound_artifact(
            route, references, captured, "engine-source"
        )
        runtime_expected = runtime_repository_records.get(str(repository_path))
        if runtime_expected is not None and (
            item.get("sha256") != runtime_expected[0]
            or item.get("bytes") != runtime_expected[1]
            or f"{captured_source.stat().st_mode & 0o7777:04o}"
            != runtime_expected[2]
        ):
            raise ValueError(
                f"runtime source entry does not match its receipt: {repository_path}"
            )

    bound_source_paths = {
        relative
        for relative, reference in references.items()
        if reference.get("role") == "engine-source"
    }
    if bound_source_paths != manifest_paths:
        raise ValueError("wrapper engine source inventory is not exact")
    observed_runtime_repository_paths = {
        relative
        for relative in manifest_repository_paths
        if relative.startswith("runtime/python/")
        or relative.startswith("runtime/typescript/")
    }
    if observed_runtime_repository_paths != set(runtime_repository_records):
        raise ValueError(
            "runtime bootstrap source inventory has missing or extra entries"
        )
    source_root_candidate = route / ENGINE_SOURCE_ROOT_RELATIVE
    expected_source_root = source_root_candidate.resolve(strict=True)
    expected_source_root.relative_to(route)
    if source_root_candidate.is_symlink() or not expected_source_root.is_dir():
        raise ValueError("captured engine source root is invalid")

    actual_paths: set[str] = set()
    engine_sources_root = (route / ENGINE_SOURCE_PREFIX).resolve(strict=True)
    engine_sources_root.relative_to(route)
    for path in engine_sources_root.rglob("*"):
        if path.is_symlink():
            raise ValueError("captured engine source closure contains a symlink")
        if path.is_file():
            actual_paths.add(path.relative_to(route).as_posix())
        elif not path.is_dir():
            raise ValueError("captured engine source closure contains a special file")
    if actual_paths != manifest_paths:
        raise ValueError("captured engine source closure has missing or extra files")

    source_token = str(expected_source_root)
    for existing in sys.path:
        candidate = Path(existing or ".").resolve(strict=False)
        if (
            candidate == expected_source_root
            or (candidate / "elmos_polyglot_route").exists()
        ):
            raise ValueError("engine source path was preloaded or shadowed")
    sys.path.insert(0, source_token)
    if sys.path.count(source_token) != 1:
        raise ValueError("engine source path insertion is not unique")
    return expected_source_root


def _metadata_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_nlink,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _directory_identity(path: Path, *, mode: int | None = None) -> tuple[int, ...]:
    try:
        before = path.lstat()
        resolved = path.resolve(strict=True)
        after = path.lstat()
    except OSError as exc:
        raise ValueError("TypeScript closure directory is unavailable") from exc
    if (
        resolved != path
        or path.is_symlink()
        or not stat.S_ISDIR(before.st_mode)
        or _metadata_identity(before) != _metadata_identity(after)
        or before.st_uid not in {0, os.getuid()}
        or stat.S_IMODE(before.st_mode) & 0o022
        or (mode is not None and stat.S_IMODE(before.st_mode) != mode)
    ):
        raise ValueError("TypeScript closure directory identity is unsafe")
    return _metadata_identity(after)


def _stable_file_identity(
    path: Path,
    *,
    expected_sha256: str,
    expected_bytes: int,
    expected_mode: str,
    private: bool,
) -> dict[str, str | int]:
    try:
        before = path.lstat()
        if path.resolve(strict=True) != path:
            raise ValueError("TypeScript closure file path is unsafe")
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            opened_before = os.fstat(descriptor)
            digest = hashlib.sha256()
            byte_count = 0
            while chunk := os.read(descriptor, 1024 * 1024):
                digest.update(chunk)
                byte_count += len(chunk)
            opened_after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        after = path.lstat()
    except OSError as exc:
        raise ValueError("TypeScript closure file is unavailable") from exc
    identity = _metadata_identity(before)
    observed_digest = digest.hexdigest()
    if (
        identity != _metadata_identity(opened_before)
        or identity != _metadata_identity(opened_after)
        or identity != _metadata_identity(after)
        or path.is_symlink()
        or not stat.S_ISREG(after.st_mode)
        or after.st_uid not in ({os.getuid()} if private else {0, os.getuid()})
        or after.st_nlink != 1
        or f"{stat.S_IMODE(after.st_mode):04o}" != expected_mode
        or byte_count != expected_bytes
        or observed_digest != expected_sha256
    ):
        raise ValueError("TypeScript closure file identity differs")
    return {
        "path": str(path),
        "sha256": observed_digest,
        "bytes": byte_count,
        "mode": expected_mode,
        "uid": after.st_uid,
        "gid": after.st_gid,
        "nlink": after.st_nlink,
        "device": after.st_dev,
        "inode": after.st_ino,
        "mtime_ns": after.st_mtime_ns,
        "ctime_ns": after.st_ctime_ns,
    }


def _typescript_records(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    receipts = manifest.get("runtime_source_receipts")
    if not isinstance(receipts, dict):
        raise ValueError("engine runtime source receipts are not exact")
    receipt = receipts.get("typescript_compiler_closure")
    if not isinstance(receipt, dict):
        raise ValueError("TypeScript compiler closure receipt is not exact")
    records = receipt.get("files")
    if not isinstance(records, list) or len(records) != TYPESCRIPT_FILE_COUNT:
        raise ValueError("TypeScript compiler closure file set is not exact")
    return records


def _captured_typescript_seal(
    route: Path,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    root = (
        route
        / ENGINE_SOURCE_PREFIX
        / TYPESCRIPT_CAPTURED_ROOT_RELATIVE
    ).resolve(strict=True)
    root.relative_to(route)
    expected_files = {str(record["path"]) for record in records}
    expected_directories = {"bin", "lib"}
    observed_files: set[str] = set()
    observed_directories: set[str] = set()
    for item in root.rglob("*"):
        relative = item.relative_to(root).as_posix()
        metadata = item.lstat()
        if stat.S_ISREG(metadata.st_mode) and not item.is_symlink():
            observed_files.add(relative)
        elif stat.S_ISDIR(metadata.st_mode) and not item.is_symlink():
            observed_directories.add(relative)
        else:
            raise ValueError("captured TypeScript closure contains an unsafe entry")
    if (
        observed_files != expected_files
        or observed_directories != expected_directories
    ):
        raise ValueError("captured TypeScript closure inventory is not exact")
    directories = {
        ".": _directory_identity(root),
        "bin": _directory_identity(root / "bin"),
        "lib": _directory_identity(root / "lib"),
    }
    files = {
        str(record["path"]): _stable_file_identity(
            root / str(record["path"]),
            expected_sha256=str(record["sha256"]),
            expected_bytes=int(record["bytes"]),
            expected_mode=str(record["mode"]),
            private=False,
        )
        for record in records
    }
    if directories != {
        ".": _directory_identity(root),
        "bin": _directory_identity(root / "bin"),
        "lib": _directory_identity(root / "lib"),
    }:
        raise ValueError("captured TypeScript directory changed during sealing")
    return {"root": str(root), "directories": directories, "files": files}


def _write_private_file(path: Path, content: bytes, expected_mode: str) -> None:
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            written = 0
            while written < len(content):
                count = os.write(descriptor, content[written:])
                if count <= 0:
                    raise OSError("zero-byte private TypeScript closure write")
                written += count
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        path.chmod(int(expected_mode, 8))
    except OSError as exc:
        raise ValueError("private TypeScript closure materialization failed") from exc


def _private_typescript_seal(
    private_root: Path,
    compiler_root: Path,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    if (
        _directory_identity(private_root, mode=0o700)
        != _directory_identity(private_root, mode=0o700)
    ):
        raise ValueError("private TypeScript root changed during sealing")
    expected_files = {str(record["path"]) for record in records}
    expected_directories = {"bin", "lib"}
    observed_files: set[str] = set()
    observed_directories: set[str] = set()
    for item in compiler_root.rglob("*"):
        relative = item.relative_to(compiler_root).as_posix()
        metadata = item.lstat()
        if stat.S_ISREG(metadata.st_mode) and not item.is_symlink():
            observed_files.add(relative)
        elif stat.S_ISDIR(metadata.st_mode) and not item.is_symlink():
            observed_directories.add(relative)
        else:
            raise ValueError("private TypeScript closure contains an unsafe entry")
    if (
        observed_files != expected_files
        or observed_directories != expected_directories
        or {item.name for item in private_root.iterdir()} != {compiler_root.name}
    ):
        raise ValueError("private TypeScript closure inventory is not exact")
    directories = {
        "private": _directory_identity(private_root, mode=0o700),
        ".": _directory_identity(compiler_root, mode=0o555),
        "bin": _directory_identity(compiler_root / "bin", mode=0o555),
        "lib": _directory_identity(compiler_root / "lib", mode=0o555),
    }
    files = {
        str(record["path"]): _stable_file_identity(
            compiler_root / str(record["path"]),
            expected_sha256=str(record["sha256"]),
            expected_bytes=int(record["bytes"]),
            expected_mode=str(record["mode"]),
            private=True,
        )
        for record in records
    }
    return {"directories": directories, "files": files}


class _PrivateTypeScriptClosure:
    def __init__(
        self,
        temporary: tempfile.TemporaryDirectory[str],
        route: Path,
        compiler_root: Path,
        records: list[dict[str, Any]],
        captured_seal: dict[str, Any],
        private_seal: dict[str, Any],
    ) -> None:
        self.temporary = temporary
        self.route = route
        self.private_root = Path(temporary.name).resolve(strict=True)
        self.compiler_root = compiler_root
        self.records = records
        self.captured_seal = captured_seal
        self.private_seal = private_seal

    def verify(self) -> None:
        if _captured_typescript_seal(self.route, self.records) != self.captured_seal:
            raise ValueError("captured TypeScript closure changed during replay")
        if (
            _private_typescript_seal(
                self.private_root,
                self.compiler_root,
                self.records,
            )
            != self.private_seal
        ):
            raise ValueError("private TypeScript closure changed during replay")

    def cleanup(self) -> None:
        for directory in (self.compiler_root / "bin", self.compiler_root / "lib"):
            if directory.exists() and not directory.is_symlink():
                directory.chmod(0o700)
        if self.compiler_root.exists() and not self.compiler_root.is_symlink():
            self.compiler_root.chmod(0o700)
        self.temporary.cleanup()


def _materialize_private_typescript_closure(
    route: Path,
    references: dict[str, dict[str, Any]],
) -> _PrivateTypeScriptClosure:
    manifest_path = validate_bound_artifact(
        route,
        references,
        ENGINE_MANIFEST_RELATIVE,
        "engine-source-manifest",
    )
    manifest = load_json(manifest_path)
    validate_runtime_source_receipts(manifest)
    records = _typescript_records(manifest)
    captured_seal = _captured_typescript_seal(route, records)
    temporary = tempfile.TemporaryDirectory(prefix="elmos-packed-typescript-")
    private_root = Path(temporary.name).resolve(strict=True)
    try:
        private_root.chmod(0o700)
        if private_root.is_relative_to(route):
            raise ValueError("private TypeScript root overlaps the route")
        compiler_root = private_root / "typescript-5.9.2"
        compiler_root.mkdir(mode=0o700)
        (compiler_root / "bin").mkdir(mode=0o700)
        (compiler_root / "lib").mkdir(mode=0o700)
        captured_root = Path(str(captured_seal["root"]))
        for record in records:
            relative = Path(str(record["path"]))
            source = captured_root / relative
            content = source.read_bytes()
            if (
                len(content) != int(record["bytes"])
                or hashlib.sha256(content).hexdigest() != record["sha256"]
            ):
                raise ValueError("captured TypeScript closure changed before copy")
            _write_private_file(
                compiler_root / relative,
                content,
                str(record["mode"]),
            )
        (compiler_root / "bin").chmod(0o555)
        (compiler_root / "lib").chmod(0o555)
        compiler_root.chmod(0o555)
        if _captured_typescript_seal(route, records) != captured_seal:
            raise ValueError("captured TypeScript closure changed during copy")
        private_seal = _private_typescript_seal(
            private_root,
            compiler_root,
            records,
        )
        return _PrivateTypeScriptClosure(
            temporary,
            route,
            compiler_root,
            records,
            captured_seal,
            private_seal,
        )
    except Exception:
        for directory in (
            private_root / "typescript-5.9.2" / "bin",
            private_root / "typescript-5.9.2" / "lib",
            private_root / "typescript-5.9.2",
        ):
            if directory.exists() and not directory.is_symlink():
                directory.chmod(0o700)
        temporary.cleanup()
        raise


def _canonical_private_typescript_identity(
    original: Any,
    private_root: Path,
    manifest: dict[str, object],
) -> dict[str, object]:
    copied = json.loads(json.dumps(manifest, sort_keys=True))
    if not isinstance(copied, dict):
        raise ValueError("private TypeScript manifest is invalid")
    package = copied.get("package_root")
    directories = copied.get("directories")
    files = copied.get("files")
    if (
        not isinstance(package, dict)
        or package.get("root") != str(private_root)
        or not isinstance(directories, list)
        or not isinstance(files, list)
    ):
        raise ValueError("private TypeScript manifest path binding is invalid")
    package["root"] = str(TYPESCRIPT_CANONICAL_ROOT)
    package["uid"] = TYPESCRIPT_CANONICAL_UID
    package["gid"] = TYPESCRIPT_CANONICAL_GID
    package["nlink"] = TYPESCRIPT_CANONICAL_PACKAGE_NLINK
    for item in directories:
        if not isinstance(item, dict) or not isinstance(
            item.get("relative_path"), str
        ):
            raise ValueError("private TypeScript directory manifest is invalid")
        relative = Path(str(item["relative_path"]))
        if item.get("resolved_path") != str(private_root / relative):
            raise ValueError("private TypeScript directory binding is invalid")
        if str(item["relative_path"]) not in TYPESCRIPT_CANONICAL_DIRECTORY_NLINKS:
            raise ValueError("private TypeScript directory role is invalid")
        item["resolved_path"] = str(TYPESCRIPT_CANONICAL_ROOT / relative)
        item["uid"] = TYPESCRIPT_CANONICAL_UID
        item["gid"] = TYPESCRIPT_CANONICAL_GID
        item["nlink"] = TYPESCRIPT_CANONICAL_DIRECTORY_NLINKS[str(item["relative_path"])]
    for item in files:
        if not isinstance(item, dict) or not isinstance(
            item.get("resolved_path"), str
        ):
            raise ValueError("private TypeScript file manifest is invalid")
        path = Path(str(item["resolved_path"]))
        try:
            relative = path.relative_to(private_root)
        except ValueError as exc:
            raise ValueError("private TypeScript file binding escapes") from exc
        item["resolved_path"] = str(TYPESCRIPT_CANONICAL_ROOT / relative)
        item["uid"] = TYPESCRIPT_CANONICAL_UID
        item["gid"] = TYPESCRIPT_CANONICAL_GID
        item["nlink"] = 1
    identity = original(copied)
    if not isinstance(identity, dict):
        raise ValueError("private TypeScript canonical identity is invalid")
    return {
        "manifest": manifest,
        "sha256": identity.get("sha256"),
        "file_count": identity.get("file_count"),
        "bytes": identity.get("bytes"),
    }


class _ConfiguredTypeScriptRuntime:
    def __init__(
        self,
        toolchains: Any,
        native: Any,
        closure: _PrivateTypeScriptClosure,
        identity_function: Any,
    ) -> None:
        self.toolchains = toolchains
        self.native = native
        self.closure = closure
        self.identity_function = identity_function

    def verify(self) -> None:
        expected = {
            "_EXPECTED_TYPESCRIPT_CACHE_ANCHOR": self.closure.private_root,
            "_EXPECTED_TYPESCRIPT_ROOT": self.closure.compiler_root,
            "_EXPECTED_TYPESCRIPT_LAUNCHER": self.closure.compiler_root / "bin/tsc",
            "_EXPECTED_TYPESCRIPT_TSC_SHIM": self.closure.compiler_root / "lib/tsc.js",
            "_EXPECTED_TYPESCRIPT_COMPILER": self.closure.compiler_root / "lib/_tsc.js",
            "_EXPECTED_TYPESCRIPT_PARSER": self.closure.compiler_root / "lib/typescript.js",
            "_EXPECTED_TYPESCRIPT_PACKAGE": self.closure.compiler_root / "package.json",
            "_EXPECTED_TYPESCRIPT_LICENSE": self.closure.compiler_root / "LICENSE.txt",
        }
        if any(getattr(self.toolchains, key, None) != value for key, value in expected.items()):
            raise ValueError("captured TypeScript toolchain configuration changed")
        if (
            getattr(self.toolchains, "_typescript_closure_identity", None)
            is not self.identity_function
            or getattr(self.native, "typescript_parser_receipt", None)
            is not getattr(self.toolchains, "typescript_parser_receipt", None)
        ):
            raise ValueError("captured TypeScript/native binding changed")
        receipt = self.toolchains.typescript_parser_receipt()
        if (
            receipt.get("compiler_root") != str(self.closure.compiler_root)
            or receipt.get("path")
            != str(self.closure.compiler_root / "lib/typescript.js")
            or receipt.get("sha256")
            != "e5f1f6b3e82228a89873cc7b941b2465185e839c0692860f83e3e63e53f94c2b"
            or receipt.get("bytes") != 9_111_680
            or receipt.get("compiler_closure_sha256")
            != TYPESCRIPT_CLOSURE_SHA256
            or receipt.get("compiler_closure_file_count") != TYPESCRIPT_FILE_COUNT
            or receipt.get("compiler_closure_bytes") != TYPESCRIPT_CLOSURE_BYTES
        ):
            raise ValueError("private TypeScript parser receipt is invalid")


def _configure_captured_typescript_runtime(
    engine_source_root: Path,
    closure: _PrivateTypeScriptClosure,
) -> _ConfiguredTypeScriptRuntime:
    toolchains = importlib.import_module("elmos_polyglot_route.toolchains")
    native = importlib.import_module("elmos_polyglot_route.native")
    expected_modules = {
        toolchains: engine_source_root / "elmos_polyglot_route/toolchains.py",
        native: engine_source_root / "elmos_polyglot_route/native.py",
    }
    for module, expected_path in expected_modules.items():
        module_path = Path(str(getattr(module, "__file__", ""))).resolve(strict=True)
        if module_path != expected_path:
            raise ValueError("captured TypeScript runtime module path is invalid")
    original_identity = getattr(toolchains, "_typescript_closure_identity", None)
    if not callable(original_identity):
        raise ValueError("captured TypeScript identity function is unavailable")
    configured_paths = {
        "_EXPECTED_TYPESCRIPT_CACHE_ANCHOR": closure.private_root,
        "_EXPECTED_TYPESCRIPT_ROOT": closure.compiler_root,
        "_EXPECTED_TYPESCRIPT_LAUNCHER": closure.compiler_root / "bin/tsc",
        "_EXPECTED_TYPESCRIPT_TSC_SHIM": closure.compiler_root / "lib/tsc.js",
        "_EXPECTED_TYPESCRIPT_COMPILER": closure.compiler_root / "lib/_tsc.js",
        "_EXPECTED_TYPESCRIPT_PARSER": closure.compiler_root / "lib/typescript.js",
        "_EXPECTED_TYPESCRIPT_PACKAGE": closure.compiler_root / "package.json",
        "_EXPECTED_TYPESCRIPT_LICENSE": closure.compiler_root / "LICENSE.txt",
    }
    for key, value in configured_paths.items():
        if not hasattr(toolchains, key):
            raise ValueError("captured TypeScript toolchain constants are incomplete")
        setattr(toolchains, key, value)

    def canonical_identity(manifest: dict[str, object]) -> dict[str, object]:
        return _canonical_private_typescript_identity(
            original_identity,
            closure.compiler_root,
            manifest,
        )

    toolchain_namespace = vars(toolchains)
    native_namespace = vars(native)
    toolchain_namespace["_typescript_closure_identity"] = canonical_identity
    native_namespace["typescript_parser_receipt"] = toolchain_namespace[
        "typescript_parser_receipt"
    ]
    configured = _ConfiguredTypeScriptRuntime(
        toolchains,
        native,
        closure,
        canonical_identity,
    )
    configured.verify()
    return configured


def validate_packed_route(route_arg: Path) -> dict[str, Any]:
    route = route_arg.resolve(strict=True)
    if not route.is_dir():
        raise ValueError(f"route is not a directory: {route_arg}")
    manifest = load_json(route / "route.json")
    certification = load_json(route / "certification" / "certification.json")
    formal_reference = certification.get("formal_equivalence")
    if not isinstance(formal_reference, dict):
        raise ValueError("certification formal_equivalence reference is missing")
    formal_path = resolve_route_file(route, str(formal_reference.get("path", "")))
    if (
        formal_reference.get("sha256") != sha256_file(formal_path)
        or formal_reference.get("bytes") != formal_path.stat().st_size
    ):
        raise ValueError("certification formal_equivalence digest/bytes mismatch")
    formal = load_json(formal_path)
    artifact_refs = formal.get("artifact_refs")
    if not isinstance(artifact_refs, list):
        raise ValueError("formal artifact_refs must be an array")
    references: dict[str, dict[str, Any]] = {}
    by_id: dict[str, dict[str, Any]] = {}
    for reference in artifact_refs:
        if not isinstance(reference, dict):
            raise ValueError("formal artifact_ref must be an object")
        relative = reference.get("path")
        artifact_id = reference.get("artifact_id")
        if not isinstance(relative, str) or relative in references:
            raise ValueError(f"duplicate or invalid artifact path: {relative}")
        if not isinstance(artifact_id, str) or artifact_id in by_id:
            raise ValueError(f"duplicate or invalid artifact id: {artifact_id}")
        references[relative] = reference
        by_id[artifact_id] = reference

    required_replay_files = dict(REQUIRED_REPLAY_FILES)
    module_reference = certification.get("module_equivalence")
    if module_reference is not None:
        if not isinstance(module_reference, dict):
            raise ValueError("certification module_equivalence reference is invalid")
        required_replay_files.update(MODULE_REPLAY_FILES)
    replay_members = {
        relative: validate_bound_artifact(route, references, relative, role)
        for relative, role in required_replay_files.items()
    }
    if replay_members[LAUNCHER_RELATIVE] != Path(__file__).resolve(strict=True):
        raise ValueError("executed launcher is not the wrapper-bound launcher")

    engine_source_root: Path | None = None
    private_typescript: _PrivateTypeScriptClosure | None = None
    configured_typescript: _ConfiguredTypeScriptRuntime | None = None
    try:
        if module_reference is not None:
            engine_source_root = validate_and_insert_engine_source(route, references)
            private_typescript = _materialize_private_typescript_closure(
                route,
                references,
            )
            configured_typescript = _configure_captured_typescript_runtime(
                engine_source_root,
                private_typescript,
            )
        namespace = runpy.run_path(
            str(replay_members[FROZEN_VALIDATOR_RELATIVE]),
            run_name="elmos_packed_batch29_validate_route",
        )
        validator = namespace.get("validate_formal_equivalence")
        if not callable(validator):
            raise ValueError("frozen Batch 29 formal validator is unavailable")
        _validated, failures = validator(route, manifest, certification)
        if failures:
            raise ValueError("; ".join(str(item) for item in failures))
        if module_reference is not None:
            module_validator = namespace.get("validate_packed_module_equivalence")
            if not callable(module_validator):
                raise ValueError(
                    "frozen Batch 29 packed module validator is unavailable"
                )
            _validated_module, module_failures = module_validator(
                route,
                manifest,
                certification,
            )
            if module_failures:
                raise ValueError("; ".join(str(item) for item in module_failures))
    finally:
        try:
            if configured_typescript is not None:
                configured_typescript.verify()
            if private_typescript is not None:
                private_typescript.verify()
        finally:
            if engine_source_root is not None:
                source_token = str(engine_source_root)
                while source_token in sys.path:
                    sys.path.remove(source_token)
                for name in list(sys.modules):
                    if name == "elmos_polyglot_route" or name.startswith(
                        "elmos_polyglot_route."
                    ):
                        sys.modules.pop(name, None)
            if private_typescript is not None:
                private_typescript.cleanup()

    replay = formal.get("formal_proof", {}).get("replay")
    if not isinstance(replay, dict):
        raise ValueError("formal replay record is missing")
    expected_id = replay.get("expected_result_artifact_id")
    expected_digest = replay.get("expected_result_sha256")
    if not isinstance(expected_id, str):
        raise ValueError("expected replay result artifact id is invalid")
    result_reference = by_id.get(expected_id)
    if result_reference is None or result_reference.get("role") != "solver-result":
        raise ValueError("expected replay result is not bound as solver-result")
    result_path = resolve_route_file(route, str(result_reference.get("path", "")))
    if (
        result_reference.get("sha256") != expected_digest
        or sha256_file(result_path) != expected_digest
        or result_reference.get("bytes") != result_path.stat().st_size
    ):
        raise ValueError("expected replay solver-result digest/bytes mismatch")

    return {
        "status": "PASSED",
        "route_key": manifest.get("route_key"),
        "scope": REPLAY_SCOPE,
        "native_route_reexecution": NATIVE_REEXECUTION_STATUS,
        "expected_result_artifact_id": expected_id,
        "expected_result_sha256": expected_digest,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--route", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = validate_packed_route(args.route)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "scope": REPLAY_SCOPE,
                    "native_route_reexecution": NATIVE_REEXECUTION_STATUS,
                    "error": bounded_error(exc, args.route),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
