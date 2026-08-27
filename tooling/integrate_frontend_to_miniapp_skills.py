#!/usr/bin/env python3
"""Safely extract, normalize, install, and verify the MiniApp Skill bundle.

The ZIP and its extracted directory are immutable source inputs.  Package
scripts are never imported or executed.  This importer validates the archive,
checksums, manifest, Skill DAG, and output contracts before producing identical
repository Runtime Skill trees.  Handler bytes remain DECLARED until a separate
fixed local qualification produces a digest-bound receipt with raw logs.  Even a
valid local receipt is engineering evidence only: official platform execution
remains NOT_RUN and certification remains NOT_CERTIFIED.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unicodedata
import zipfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

import skill_creator_tools

ROOT = Path(__file__).resolve().parents[1]
SYSTEM_TEMP_ROOT = Path(tempfile.gettempdir()).resolve(strict=True)
PACKAGE_DIRECTORY = "elmos-frontend-to-miniapp-skills-v1.0.0"
ARCHIVE_RELATIVE = (
    Path("skills") / "subskills" / f"{PACKAGE_DIRECTORY}.zip"
)
PACKAGE_RELATIVE = Path("skills") / PACKAGE_DIRECTORY
RUNTIME_RELATIVE = Path("agent-skills") / "runtime"
WORKSPACE_RELATIVE = Path(".agents") / "skills"
DOC_RELATIVE = Path("docs") / "frontend-to-miniapp-skills"
LOCAL_RECEIPT_ROOT_RELATIVE = (
    Path("artifacts") / "frontend-to-miniapp" / "local-runtime-receipt-v1"
)
LOCAL_RECEIPT_RELATIVE = LOCAL_RECEIPT_ROOT_RELATIVE / "receipt.json"

PACKAGE_ID = "elmos.frontend-to-miniapp.skills"
PACKAGE_NAME = "elmos-frontend-to-miniapp-skills"
PACKAGE_VERSION = "1.0.0"
NAMESPACE = "frontend-to-miniapp-v1"
EXPECTED_ARCHIVE_SHA256 = (
    "e8fabbe19f96a432e3ba77470e1c35a000cc683cd4ac0c084bbabcf31df79d82"
)
EXPECTED_ARCHIVE_ENTRY_COUNT = 217
EXPECTED_ARCHIVE_UNCOMPRESSED_BYTES = 492_647
EXPECTED_SOURCE_FILE_COUNT = 217
EXPECTED_CHECKSUM_ENTRY_COUNT = 216
EXPECTED_CHECKSUMS_SHA256 = (
    "816a46308633ad6903714ab8f38c15f2035b4ef81cf21a744b471538819bf81b"
)
MAX_ARCHIVE_ENTRY_BYTES = 128 * 1024
MAX_ARCHIVE_TOTAL_BYTES = 1024 * 1024
MAX_COMPRESSION_RATIO = 100
MAX_LOCAL_RECEIPT_BYTES = 2 * 1024 * 1024
MAX_LOCAL_QUALIFICATION_LOG_BYTES = 16 * 1024 * 1024
MAX_LOCAL_QUALIFICATION_TOOL_BYTES = 32 * 1024 * 1024
EXPECTED_MODE_COUNTS = {0o644: 205, 0o755: 12}

EXPECTED_SKILLS = (
    "frontend-to-miniapp-orchestrator",
    "miniapp-source-framework-detector",
    "vue-to-miniapp-analyzer",
    "react-to-miniapp-analyzer",
    "flutter-widget-semantic-reconstructor",
    "miniapp-semantic-ir",
    "miniapp-capability-registry",
    "miniapp-component-mapping-engine",
    "miniapp-state-event-lifecycle-converter",
    "miniapp-style-layout-converter",
    "miniapp-third-party-dependency-migrator",
    "wechat-miniapp-codegen",
    "alipay-miniapp-codegen",
    "douyin-miniapp-codegen",
    "xiaohongshu-miniapp-codegen",
    "miniapp-commerce-social-adapter",
    "miniapp-privacy-permission-auditor",
    "miniapp-differential-testing",
    "miniapp-visual-regression-testing",
    "miniapp-auto-repair-loop",
    "miniapp-ci-build-release",
    "miniapp-migration-evidence-reporter",
)
EXPECTED_SOURCE_FRAMEWORKS = (
    "vue2",
    "vue3",
    "react",
    "flutter",
    "h5",
    "typescript",
    "javascript",
    "taro",
    "uni-app",
    "native-miniapp",
)
EXPECTED_TARGET_PLATFORMS = ("wechat", "alipay", "douyin", "xiaohongshu")
EXPECTED_INVENTORY_COUNTS = {
    "total_canonical_files": 216,
    "skills": 22,
    "skill_support_files": 66,
    "schemas": 14,
    "fixtures": 14,
    "docs": 19,
    "templates": 17,
    "examples": 19,
    "plans": 5,
    "scripts": 9,
    "tests": 12,
    "task_ids": 40,
    "target_platforms": 4,
}
EXPECTED_SKILL_FILES = {
    "SKILL.md",
    "assets/output-contract.yaml",
    "examples/invocation.md",
    "references/contract.md",
}
DOC_FILES = {
    "README.md",
    "compiled-contracts.json",
    "installed-manifest.json",
    "local-runtime-evidence.json",
}

FRONTEND_ENGINE_PATH = "engines/frontend-client-engine"
FRONTEND_ENGINE_CLI_COMMAND = "npm run miniapp"
FRONTEND_ENGINE_CLI_ENTRYPOINT = "dist/src/miniapp-cli.js"
FRONTEND_ENGINE_STRUCTURED_HANDLER = "handleMiniappSkillRequest"
FRONTEND_ENGINE_JSON_HANDLER = "runMiniappSkillJson"
FRONTEND_ENGINE_CONVERSION_HANDLER = "runMiniappConversion"
FRONTEND_ENGINE_PACKAGE_HANDLER = "runMiniappPackageConversion"
FRONTEND_ENGINE_PACKAGE_ACTION = "run-package"
FRONTEND_ENGINE_PACKAGE_INPUT_FIELD = "packageInput"
FRONTEND_ENGINE_PACKAGE_VALIDATOR = "validateMiniappPackageConversionInput"
FRONTEND_ENGINE_PACKAGE_COMPILER = "compileMiniappPackageConversionInput"
FRONTEND_ENGINE_SINGLE_SKILL_HANDLER = "executeMiniappSkill"
COMPONENT_ADAPTER_PATH = "engines/component-dialect-engine"
COMPONENT_ADAPTER_CLI_COMMAND = "npm run miniapp-worker"
COMPONENT_ADAPTER_CLI_ENTRYPOINT = "dist/miniapp-worker.js"
COMPONENT_ADAPTER_HANDLER = "handleMiniAppWorkerRequest"
COMPONENT_ADAPTER_JSON_HANDLER = "runMiniAppWorkerJson"
COMPONENT_ADAPTER_EMITTER = "emitPlatformMiniApp"
FRONTEND_TSC_RELATIVE = (
    Path(FRONTEND_ENGINE_PATH) / "node_modules" / ".bin" / "tsc"
)
COMPONENT_TSC_RELATIVE = (
    Path(COMPONENT_ADAPTER_PATH) / "node_modules" / ".bin" / "tsc"
)
COMPONENT_JEST_RELATIVE = (
    Path(COMPONENT_ADAPTER_PATH) / "node_modules" / ".bin" / "jest"
)
RUNTIME_IMPLEMENTATION_FILES = (
    "tooling/integrate_frontend_to_miniapp_skills.py",
    "tests/frontend-to-miniapp/test_integration.py",
    "engines/frontend-client-engine/package.json",
    "engines/frontend-client-engine/pnpm-lock.yaml",
    "engines/frontend-client-engine/tsconfig.json",
    "engines/frontend-client-engine/src/index.ts",
    "engines/frontend-client-engine/src/miniapp-types.ts",
    "engines/frontend-client-engine/src/miniapp-contract-validation.ts",
    "engines/frontend-client-engine/src/miniapp-inventory.ts",
    "engines/frontend-client-engine/src/miniapp-semantic-ir.ts",
    "engines/frontend-client-engine/src/miniapp-planning.ts",
    "engines/frontend-client-engine/src/miniapp-target-generation.ts",
    "engines/frontend-client-engine/src/miniapp-skill-runtime.ts",
    "engines/frontend-client-engine/src/miniapp-validation.ts",
    "engines/frontend-client-engine/src/miniapp-cli.ts",
    "engines/frontend-client-engine/src/miniapp-package-contract.ts",
    "engines/frontend-client-engine/src/miniapp-output-contracts.ts",
    "engines/frontend-client-engine/test/miniapp-contract-validation.test.ts",
    "engines/frontend-client-engine/test/miniapp-inventory.test.ts",
    "engines/frontend-client-engine/test/miniapp-semantic-ir.test.ts",
    "engines/frontend-client-engine/test/miniapp-four-platform-generation.test.ts",
    "engines/frontend-client-engine/test/miniapp-skill-runtime.test.ts",
    "engines/frontend-client-engine/test/miniapp-validation.test.ts",
    "engines/frontend-client-engine/test/miniapp-package-contract.test.ts",
    "engines/frontend-client-engine/test/miniapp-output-contracts.test.ts",
    "engines/frontend-client-engine/test/miniapp-test-fixture.ts",
    "engines/component-dialect-engine/package.json",
    "engines/component-dialect-engine/jest.config.js",
    "engines/component-dialect-engine/package-lock.json",
    "engines/component-dialect-engine/pnpm-lock.yaml",
    "engines/component-dialect-engine/tsconfig.json",
    "engines/component-dialect-engine/src/models.ts",
    "engines/component-dialect-engine/src/miniapp-worker.ts",
    "engines/component-dialect-engine/src/parsers/expressions.ts",
    "engines/component-dialect-engine/src/parsers/miniprogram.ts",
    "engines/component-dialect-engine/src/parsers/react.ts",
    "engines/component-dialect-engine/src/parsers/vue2.ts",
    "engines/component-dialect-engine/src/parsers/vue3.ts",
    "engines/component-dialect-engine/src/emitters/miniprogram.ts",
    "engines/component-dialect-engine/src/emitters/platform-miniapps.ts",
    "engines/component-dialect-engine/src/emitters/react.ts",
    "engines/component-dialect-engine/src/emitters/vue3.ts",
    "engines/component-dialect-engine/src/validator.ts",
    "engines/component-dialect-engine/tests/miniapp-worker.test.ts",
    "engines/component-dialect-engine/tests/platform-miniapps.test.ts",
)
FRONTEND_QUALIFICATION_TESTS = tuple(
    "dist/test/" + Path(relative).name.removesuffix(".ts") + ".js"
    for relative in RUNTIME_IMPLEMENTATION_FILES
    if relative.startswith("engines/frontend-client-engine/test/miniapp-")
    and relative.endswith(".test.ts")
)
DECLARED_RUNTIME_EVIDENCE_STATUS = "DECLARED"
EXECUTED_RUNTIME_EVIDENCE_STATUS = "LOCAL_EXECUTED"
EXTERNAL_EVIDENCE_STATUS = "NOT_RUN"
CERTIFICATION_STATUS = "NOT_CERTIFIED"
QUALIFICATION_ENVIRONMENT_KEYS = (
    "CI",
    "COREPACK_ENABLE_DOWNLOAD_PROMPT",
    "FORCE_COLOR",
    "NO_COLOR",
    "NPM_CONFIG_UPDATE_NOTIFIER",
    "PYTHONDONTWRITEBYTECODE",
)


class IntegrationError(RuntimeError):
    """A fail-closed archive, package, or installation validation error."""


@dataclass(frozen=True)
class ArchiveRecord:
    archive_name: str
    relative: str
    size: int
    mode: int
    sha256: str


@dataclass(frozen=True)
class FilePayload:
    content: bytes
    mode: int = 0o644


@dataclass(frozen=True)
class DirectoryIdentity:
    device: int
    inode: int


@dataclass
class ReceiptWriterReservation:
    parent_path: Path
    parent_descriptor: int
    parent_identity: DirectoryIdentity
    lock_parent_path: Path
    lock_parent_descriptor: int
    lock_parent_identity: DirectoryIdentity
    lock_name: str
    lock_descriptor: int
    lock_identity: DirectoryIdentity

    def assert_current(self, stage: str) -> None:
        """Prove that both the held parent and fixed lock path still bind our fds."""

        _assert_directory_path_identity(
            self.parent_path,
            self.parent_identity,
            f"local runtime receipt parent during {stage}",
        )
        _assert_directory_path_identity(
            self.lock_parent_path,
            self.lock_parent_identity,
            f"local runtime receipt lock parent during {stage}",
        )
        try:
            current = os.stat(
                self.lock_name,
                dir_fd=self.lock_parent_descriptor,
                follow_symlinks=False,
            )
        except OSError as exc:
            fail(f"local runtime receipt reservation disappeared during {stage}: {exc}")
        opened = os.fstat(self.lock_descriptor)
        if (
            not stat.S_ISREG(current.st_mode)
            or not stat.S_ISREG(opened.st_mode)
            or DirectoryIdentity(current.st_dev, current.st_ino)
            != self.lock_identity
            or DirectoryIdentity(opened.st_dev, opened.st_ino)
            != self.lock_identity
        ):
            fail(f"local runtime receipt reservation identity drifted during {stage}")


@dataclass
class OwnedTreeCommit:
    index: int
    destination: Path
    backup: Path
    old_tree: dict[str, FilePayload]
    new_tree: dict[str, FilePayload]
    old_identity: DirectoryIdentity
    published_identity: DirectoryIdentity | None = None


@dataclass(frozen=True)
class QualificationCommand:
    command_id: str
    relative_cwd: str
    argv: tuple[str, ...]
    display: str
    claim: str
    result_parser: str | None = None
    expected_test_count: int | None = None


LOCAL_QUALIFICATION_COMMANDS = (
    QualificationCommand(
        command_id="component-build",
        relative_cwd=COMPONENT_ADAPTER_PATH,
        argv=("./node_modules/.bin/tsc", "-p", "tsconfig.json"),
        display=(
            "cd engines/component-dialect-engine && "
            "./node_modules/.bin/tsc -p tsconfig.json"
        ),
        claim="TypeScript build",
    ),
    QualificationCommand(
        command_id="component-tests",
        relative_cwd=COMPONENT_ADAPTER_PATH,
        argv=(
            "./node_modules/.bin/jest",
            "tests/platform-miniapps.test.ts",
            "tests/miniapp-worker.test.ts",
            "--runInBand",
        ),
        display=(
            "cd engines/component-dialect-engine && "
            "./node_modules/.bin/jest tests/platform-miniapps.test.ts "
            "tests/miniapp-worker.test.ts --runInBand"
        ),
        claim="canonical component worker and four direct IR emitters",
        result_parser="jest",
        expected_test_count=63,
    ),
    QualificationCommand(
        command_id="frontend-build",
        relative_cwd=FRONTEND_ENGINE_PATH,
        argv=("./node_modules/.bin/tsc", "-p", "tsconfig.json"),
        display=(
            "cd engines/frontend-client-engine && "
            "./node_modules/.bin/tsc -p tsconfig.json"
        ),
        claim="strict TypeScript build",
    ),
    QualificationCommand(
        command_id="frontend-tests",
        relative_cwd=FRONTEND_ENGINE_PATH,
        argv=(
            "node",
            "--test",
            "--test-concurrency=1",
            *FRONTEND_QUALIFICATION_TESTS,
        ),
        display=(
            "cd engines/frontend-client-engine && "
            "node --test --test-concurrency=1 "
            + " ".join(FRONTEND_QUALIFICATION_TESTS)
        ),
        claim=(
            "contracts, inventory, semantic IR, source labels, target generators, "
            "Skill handlers, checkpoints and evidence gates"
        ),
        result_parser="node-test",
        expected_test_count=60,
    ),
    QualificationCommand(
        command_id="integration-tests",
        relative_cwd=".",
        argv=(
            "uv",
            "run",
            "--quiet",
            "--with",
            "pyyaml==6.0.2",
            "--with",
            "jsonschema==4.25.1",
            "python",
            "tests/frontend-to-miniapp/test_integration.py",
        ),
        display=(
            "uv run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 "
            "python tests/frontend-to-miniapp/test_integration.py"
        ),
        claim="archive, package, DAG, compiled contract and dual-root integration",
        result_parser="unittest",
        expected_test_count=15,
    ),
)


def fail(message: str) -> None:
    raise IntegrationError(message)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest(value: bytes) -> str:
    return "sha256:" + sha256_bytes(value)


def sha256_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _directory_identity_from_stat(value: os.stat_result) -> DirectoryIdentity:
    return DirectoryIdentity(value.st_dev, value.st_ino)


def _open_verified_directory(path: Path, label: str) -> tuple[int, DirectoryIdentity]:
    no_follow = getattr(os, "O_NOFOLLOW", None)
    directory_flag = getattr(os, "O_DIRECTORY", None)
    if no_follow is None or directory_flag is None:
        fail(f"{label} requires O_NOFOLLOW and O_DIRECTORY support")
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | no_follow | directory_flag | getattr(os, "O_CLOEXEC", 0),
        )
    except OSError as exc:
        fail(f"{label} is missing or unsafe: {path}: {exc}")
    try:
        opened = os.fstat(descriptor)
        current = os.lstat(path)
        identity = _directory_identity_from_stat(opened)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or not stat.S_ISDIR(current.st_mode)
            or _directory_identity_from_stat(current) != identity
        ):
            fail(f"{label} path identity drifted: {path}")
        return descriptor, identity
    except OSError as exc:
        os.close(descriptor)
        fail(f"{label} identity could not be verified: {path}: {exc}")
    except BaseException:
        os.close(descriptor)
        raise


def _directory_identity(path: Path, label: str = "directory") -> DirectoryIdentity:
    descriptor, identity = _open_verified_directory(path, label)
    os.close(descriptor)
    return identity


def _assert_directory_path_identity(
    path: Path,
    expected: DirectoryIdentity,
    label: str,
) -> None:
    descriptor, current = _open_verified_directory(path, label)
    os.close(descriptor)
    if current != expected:
        fail(
            f"{label} identity drifted: expected={expected.device}:{expected.inode} "
            f"actual={current.device}:{current.inode}"
        )


def _entry_stat_at(parent_descriptor: int, name: str) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return None


def _ensure_relative_directory(
    root: Path,
    relative: Path,
    label: str,
) -> Path:
    """Create a fixed relative directory without following any path-component link."""

    relative_path = _validate_relative_path(relative.as_posix(), label)
    root_descriptor, _root_identity = _open_verified_directory(root, f"{label} root")
    descriptors = [root_descriptor]
    try:
        current_descriptor = root_descriptor
        for component in relative_path.parts:
            try:
                os.mkdir(component, 0o755, dir_fd=current_descriptor)
            except FileExistsError:
                pass
            try:
                child_descriptor = os.open(
                    component,
                    os.O_RDONLY
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_CLOEXEC", 0),
                    dir_fd=current_descriptor,
                )
            except OSError as exc:
                fail(f"{label} contains an unsafe directory component {component!r}: {exc}")
            opened = os.fstat(child_descriptor)
            current = os.stat(
                component,
                dir_fd=current_descriptor,
                follow_symlinks=False,
            )
            if (
                not stat.S_ISDIR(opened.st_mode)
                or not stat.S_ISDIR(current.st_mode)
                or _directory_identity_from_stat(opened)
                != _directory_identity_from_stat(current)
            ):
                os.close(child_descriptor)
                fail(f"{label} directory component identity drifted: {component!r}")
            descriptors.append(child_descriptor)
            current_descriptor = child_descriptor
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
    destination = root / relative_path
    _assert_inside(root, destination, label)
    return destination


def _read_bounded_regular_file(
    root: Path,
    relative: str | PurePosixPath,
    label: str,
    maximum_bytes: int,
    *,
    missing_ok: bool = False,
    after_open: Callable[[], None] | None = None,
    expected_root_identity: DirectoryIdentity | None = None,
) -> bytes | None:
    """Read one relative regular file through held no-follow directory descriptors."""

    relative_path = _validate_relative_path(PurePosixPath(relative).as_posix(), label)
    root_descriptor, root_identity = _open_verified_directory(root, f"{label} root")
    directory_descriptors = [root_descriptor]
    directory_bindings: list[tuple[int, str, DirectoryIdentity]] = []
    file_descriptor: int | None = None
    try:
        if expected_root_identity is not None and root_identity != expected_root_identity:
            fail(
                f"{label} root identity drifted: "
                f"expected={expected_root_identity.device}:{expected_root_identity.inode} "
                f"actual={root_identity.device}:{root_identity.inode}"
            )
        current_descriptor = root_descriptor
        for component in relative_path.parts[:-1]:
            try:
                child_descriptor = os.open(
                    component,
                    os.O_RDONLY
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_CLOEXEC", 0),
                    dir_fd=current_descriptor,
                )
            except FileNotFoundError:
                if missing_ok:
                    return None
                raise
            except OSError as exc:
                fail(f"{label} contains an unsafe directory component {component!r}: {exc}")
            opened_directory = os.fstat(child_descriptor)
            current_directory = os.stat(
                component,
                dir_fd=current_descriptor,
                follow_symlinks=False,
            )
            identity = _directory_identity_from_stat(opened_directory)
            if (
                not stat.S_ISDIR(opened_directory.st_mode)
                or not stat.S_ISDIR(current_directory.st_mode)
                or _directory_identity_from_stat(current_directory) != identity
            ):
                os.close(child_descriptor)
                fail(f"{label} directory component identity drifted: {component!r}")
            directory_bindings.append((current_descriptor, component, identity))
            directory_descriptors.append(child_descriptor)
            current_descriptor = child_descriptor

        file_name = relative_path.parts[-1]
        try:
            file_descriptor = os.open(
                file_name,
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=current_descriptor,
            )
        except FileNotFoundError:
            if missing_ok:
                return None
            raise
        except OSError as exc:
            fail(f"{label} is missing or unsafe: {relative_path}: {exc}")
        before = os.fstat(file_descriptor)
        current_file = os.stat(
            file_name,
            dir_fd=current_descriptor,
            follow_symlinks=False,
        )
        file_identity = _directory_identity_from_stat(before)
        if (
            not stat.S_ISREG(before.st_mode)
            or not stat.S_ISREG(current_file.st_mode)
            or _directory_identity_from_stat(current_file) != file_identity
            or before.st_size < 0
            or before.st_size > maximum_bytes
        ):
            fail(f"{label} is not a bounded regular file: {relative_path}")
        if after_open is not None:
            after_open()
        chunks: list[bytes] = []
        observed = 0
        while True:
            chunk = os.read(file_descriptor, min(64 * 1024, maximum_bytes + 1 - observed))
            if not chunk:
                break
            chunks.append(chunk)
            observed += len(chunk)
            if observed > maximum_bytes:
                fail(f"{label} exceeds the {maximum_bytes}-byte limit: {relative_path}")
        after = os.fstat(file_descriptor)
        if (
            _directory_identity_from_stat(after) != file_identity
            or after.st_size != before.st_size
            or after.st_mtime_ns != before.st_mtime_ns
            or after.st_ctime_ns != before.st_ctime_ns
            or observed != before.st_size
        ):
            fail(f"{label} changed while it was read: {relative_path}")
        rebound_file = os.stat(
            file_name,
            dir_fd=current_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(rebound_file.st_mode)
            or _directory_identity_from_stat(rebound_file) != file_identity
        ):
            fail(f"{label} path identity drifted while it was read: {relative_path}")
        for parent_descriptor, component, identity in reversed(directory_bindings):
            rebound = os.stat(
                component,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            if (
                not stat.S_ISDIR(rebound.st_mode)
                or _directory_identity_from_stat(rebound) != identity
            ):
                fail(f"{label} directory path drifted while it was read: {component!r}")
        _assert_directory_path_identity(root, root_identity, f"{label} root")
        return b"".join(chunks)
    except FileNotFoundError as exc:
        fail(f"{label} is missing: {relative_path}: {exc}")
    except OSError as exc:
        fail(f"{label} could not be read safely: {relative_path}: {exc}")
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        for descriptor in reversed(directory_descriptors):
            os.close(descriptor)


def _load_bounded_json_bytes(content: bytes, label: str) -> Any:
    try:
        return json.loads(content.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        fail(f"invalid {label}: {exc}")


def _frontend_make_target_payload(repository_root: Path) -> bytes:
    raw = _read_bounded_regular_file(
        repository_root,
        "Makefile",
        "frontend-to-miniapp Make target",
        MAX_LOCAL_RECEIPT_BYTES,
    )
    if raw is None:
        fail("frontend-to-miniapp Make target is missing")
    try:
        lines = raw.decode("utf-8").splitlines(keepends=True)
    except UnicodeError as exc:
        fail(f"frontend-to-miniapp Make target is not UTF-8: {exc}")
    marker = ".PHONY: frontend-to-miniapp-skills\n"
    matches = [index for index, line in enumerate(lines) if line == marker]
    if len(matches) != 1:
        fail("frontend-to-miniapp Make target marker must occur exactly once")
    start = matches[0]
    if (
        start + 1 >= len(lines)
        or lines[start + 1] != "frontend-to-miniapp-skills:\n"
    ):
        fail("frontend-to-miniapp Make target header is missing or drifted")
    end = start + 2
    while end < len(lines) and lines[end].startswith("\t"):
        end += 1
    payload = "".join(lines[start:end]).encode("utf-8")
    required = (
        b"trap closeout EXIT",
        b"--qualify-local",
        b"--refresh-owned",
        b"integrate_frontend_to_miniapp_skills.py --check",
        b"replay-local-runtime.mjs --check",
        b"run_client_gate.py",
        b"--closeout-portable",
    )
    for value in required:
        if payload.count(value) != 1:
            fail(
                "frontend-to-miniapp Make target binding is missing or duplicated: "
                f"{value.decode('ascii')}"
            )
    if not (
        payload.index(b"--qualify-local")
        < payload.index(b"--refresh-owned")
        < payload.index(b"integrate_frontend_to_miniapp_skills.py --check")
        < payload.index(b"replay-local-runtime.mjs --check")
        < payload.index(b"run_client_gate.py")
    ):
        fail("frontend-to-miniapp Make target execution order drifted")
    return payload


def _runtime_implementation(repository_root: Path = ROOT) -> dict[str, Any]:
    """Bind the installed contracts to the exact local implementation bytes."""

    records: list[dict[str, Any]] = []
    tree = hashlib.sha256()
    for relative in RUNTIME_IMPLEMENTATION_FILES:
        path = repository_root / relative
        if not path.is_file() or path.is_symlink():
            fail(f"runtime implementation file is missing or unsafe: {relative}")
        content = path.read_bytes()
        mode = stat.S_IMODE(path.stat().st_mode)
        record = {
            "path": relative,
            "bytes": len(content),
            "mode": f"{mode:04o}",
            "sha256": digest(content),
        }
        records.append(record)
        tree.update(relative.encode("utf-8"))
        tree.update(b"\0")
        tree.update(record["mode"].encode("ascii"))
        tree.update(b"\0")
        tree.update(bytes.fromhex(record["sha256"].removeprefix("sha256:")))

    make_target = _frontend_make_target_payload(repository_root)
    make_mode = stat.S_IMODE((repository_root / "Makefile").stat().st_mode)
    make_record = {
        "path": "Makefile#frontend-to-miniapp-skills",
        "bytes": len(make_target),
        "mode": f"{make_mode:04o}",
        "sha256": digest(make_target),
    }
    records.append(make_record)
    tree.update(make_record["path"].encode("utf-8"))
    tree.update(b"\0")
    tree.update(make_record["mode"].encode("ascii"))
    tree.update(b"\0")
    tree.update(bytes.fromhex(make_record["sha256"].removeprefix("sha256:")))

    frontend_package = _load_json(
        repository_root / FRONTEND_ENGINE_PATH / "package.json",
        "frontend engine package",
    )
    component_package = _load_json(
        repository_root / COMPONENT_ADAPTER_PATH / "package.json",
        "component adapter package",
    )
    if frontend_package.get("scripts", {}).get("miniapp") != "node dist/src/miniapp-cli.js":
        fail("frontend engine miniapp CLI script is missing or drifted")
    if component_package.get("scripts", {}).get("miniapp-worker") != "node dist/miniapp-worker.js":
        fail("component adapter miniapp-worker script is missing or drifted")
    for label, package in (
        ("frontend engine", frontend_package),
        ("component adapter", component_package),
    ):
        scripts = package.get("scripts")
        if not isinstance(scripts, dict) or scripts.get("build") != "tsc -p tsconfig.json":
            fail(f"{label} qualification build script is missing or drifted")
        for lifecycle_hook in ("prebuild", "postbuild"):
            if lifecycle_hook in scripts:
                fail(
                    f"{label} qualification refuses implicit npm lifecycle hook: "
                    f"{lifecycle_hook}"
                )

    marker_files = {
        "engines/frontend-client-engine/src/miniapp-skill-runtime.ts": (
            "export function handleMiniappSkillRequest",
            "export function runMiniappSkillJson",
            "export function runMiniappConversion",
            "export function runMiniappPackageConversion",
            "export function executeMiniappSkill",
            "readonly declaredOutputs: readonly MiniappDeclaredOutputArtifact[]",
            "MINIAPP_SKILL_CATALOG",
        ),
        "engines/frontend-client-engine/src/miniapp-package-contract.ts": (
            "export function validateMiniappPackageConversionInput",
            "export function compileMiniappPackageConversionInput",
        ),
        "engines/frontend-client-engine/src/miniapp-output-contracts.ts": (
            "export function materializeMiniappDeclaredOutputs",
            "export function materializeMiniappGeneratedProjectArtifacts",
            "export function materializeMiniappCombinedOutputIndex",
        ),
        "engines/component-dialect-engine/src/miniapp-worker.ts": (
            "export function handleMiniAppWorkerRequest",
            "export function runMiniAppWorkerJson",
        ),
        "engines/component-dialect-engine/src/emitters/platform-miniapps.ts": (
            "export function emitPlatformMiniApp",
        ),
    }
    for relative, markers in marker_files.items():
        source = (repository_root / relative).read_text(encoding="utf-8")
        for marker in markers:
            if marker not in source:
                fail(f"runtime implementation marker is missing: {relative}: {marker}")

    implementation_digest = "sha256:" + tree.hexdigest()
    return {
        "state": "HANDLER_IMPLEMENTED",
        "implementation_digest": implementation_digest,
        "files": records,
        "capability_scope": {
            "source_labels": list(EXPECTED_SOURCE_FRAMEWORKS),
            "target_platforms": list(EXPECTED_TARGET_PLATFORMS),
            "skill_handlers": len(EXPECTED_SKILLS),
            "task_ids": 40,
            "project_generators": 4,
            "component_worker_sources": [
                "react",
                "typescript",
                "react-native",
                "vue2",
                "vue3",
                "miniprogram",
            ],
        },
        "evidence_boundary": (
            "Digest-bound handlers and bounded local tests are implemented. "
            "Official MiniApp builds, browser/emulator/device journeys, independent "
            "corpora, platform review, upload and release remain NOT_RUN."
        ),
    }


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _qualification_suite_payload() -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for command in LOCAL_QUALIFICATION_COMMANDS:
        argv = list(command.argv)
        payload.append({
            "id": command.command_id,
            "cwd": command.relative_cwd,
            "argv": argv,
            "command": command.display,
            "claim": command.claim,
            "result_parser": command.result_parser or "none",
            "expected_test_count": command.expected_test_count,
        })
    return payload


def _qualification_command_binding(
    command: QualificationCommand,
) -> dict[str, Any]:
    return {
        "cwd": command.relative_cwd,
        "argv": list(command.argv),
        "command": command.display,
        "claim": command.claim,
    }


def _qualification_suite_digest() -> str:
    return digest(_canonical_json_bytes(_qualification_suite_payload()))


def _qualification_environment_variables() -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "CI": "1",
            "COREPACK_ENABLE_DOWNLOAD_PROMPT": "0",
            "FORCE_COLOR": "0",
            "NO_COLOR": "1",
            "NPM_CONFIG_UPDATE_NOTIFIER": "false",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    return environment


def _executable_binding(
    name: str,
    executable: str,
    environment: dict[str, str],
    *,
    content_root: Path | None = None,
    repository_relative_path: Path | None = None,
) -> dict[str, Any]:
    invocation = Path(executable)
    if not invocation.is_absolute():
        located = shutil.which(executable, path=environment.get("PATH"))
        if located is None:
            fail(f"local qualification executable is unavailable: {name}: {executable}")
        invocation = Path(located)
    invocation = invocation.absolute()
    if not invocation.is_file():
        fail(f"local qualification executable is not a file: {name}: {invocation}")

    def canonical_content_binding() -> tuple[Path, dict[str, Any] | None]:
        canonical_path = invocation.resolve(strict=True)
        if content_root is None:
            return canonical_path, None
        canonical_root = content_root.resolve(strict=True)
        try:
            canonical_path.relative_to(canonical_root)
        except ValueError:
            fail(
                f"local qualification executable escapes its canonical root: "
                f"{name}: {canonical_path}"
            )
        parent_identity = _directory_identity(
            canonical_path.parent,
            f"local qualification executable parent for {name}",
        )
        content = _read_bounded_regular_file(
            canonical_path.parent,
            canonical_path.name,
            f"local qualification executable {name}",
            MAX_LOCAL_QUALIFICATION_TOOL_BYTES,
            expected_root_identity=parent_identity,
        )
        if content is None:
            fail(f"local qualification executable disappeared: {name}")
        return canonical_path, {
            "bytes": len(content),
            "sha256": digest(content),
        }

    try:
        real_path, content_binding_before = canonical_content_binding()
        completed = subprocess.run(
            [str(real_path), "--version"],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        fail(f"local qualification executable version failed: {name}: {exc}")
    if completed.returncode != 0:
        fail(
            f"local qualification executable version failed: {name}: "
            f"exit={completed.returncode}"
        )
    try:
        output = completed.stdout.decode("utf-8")
    except UnicodeError as exc:
        fail(f"local qualification executable version is not UTF-8: {name}: {exc}")
    version_lines: list[str] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if name == "uv":
            match = re.fullmatch(
                r"uv\s+(v?[0-9]+(?:\.[0-9A-Za-z+-]+)+)(?:\s+\([^)]*\))?",
                line,
            )
            if match:
                version_lines.append(match.group(1))
            continue
        if re.fullmatch(
            r"(?:Python\s+|Version\s+)?v?[0-9]+(?:\.[0-9A-Za-z+-]+)+",
            line,
        ):
            version_lines.append(line)
    if len(version_lines) != 1:
        fail(f"local qualification executable version is invalid: {name}")
    version = version_lines[0]
    real_path_after, content_binding_after = canonical_content_binding()
    if real_path_after != real_path or content_binding_after != content_binding_before:
        fail(f"local qualification executable changed during version binding: {name}")
    binding: dict[str, Any] = {
        "path": str(invocation),
        "real_path": str(real_path),
        "canonical_path": str(real_path),
        "execution_path": str(real_path),
        "version": version,
        "version_argv": [str(real_path), "--version"],
    }
    if repository_relative_path is not None:
        binding["repository_relative_path"] = repository_relative_path.as_posix()
    if content_binding_before is not None:
        binding.update(content_binding_before)
    return binding


def _local_qualification_environment(
    environment: dict[str, str] | None = None,
    repository_root: Path = ROOT,
) -> dict[str, Any]:
    environment = environment or _qualification_environment_variables()
    repository_root = repository_root.resolve()
    try:
        canonical_python = Path(sys.executable).resolve(strict=True)
    except OSError as exc:
        fail(f"local qualification Python executable cannot be resolved: {exc}")
    executables = {
        "node": _executable_binding("node", "node", environment),
        "npm": _executable_binding("npm", "npm", environment),
        "pnpm": _executable_binding("pnpm", "pnpm", environment),
        "uv": _executable_binding("uv", "uv", environment),
        "python": _executable_binding(
            "python", str(canonical_python), environment
        ),
        "schema_python": _executable_binding(
            "schema_python", "python3.11", environment
        ),
        "frontend_tsc": _executable_binding(
            "frontend_tsc",
            str(repository_root / FRONTEND_TSC_RELATIVE),
            environment,
            content_root=repository_root / FRONTEND_ENGINE_PATH / "node_modules",
            repository_relative_path=FRONTEND_TSC_RELATIVE,
        ),
        "component_tsc": _executable_binding(
            "component_tsc",
            str(repository_root / COMPONENT_TSC_RELATIVE),
            environment,
            content_root=repository_root / COMPONENT_ADAPTER_PATH / "node_modules",
            repository_relative_path=COMPONENT_TSC_RELATIVE,
        ),
        "component_jest": _executable_binding(
            "component_jest",
            str(repository_root / COMPONENT_JEST_RELATIVE),
            environment,
            content_root=repository_root / COMPONENT_ADAPTER_PATH / "node_modules",
            repository_relative_path=COMPONENT_JEST_RELATIVE,
        ),
    }
    return {
        "os": {
            "name": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
        },
        "architecture": platform.machine(),
        "executables": executables,
        "variables": {
            **{
                name: environment[name]
                for name in QUALIFICATION_ENVIRONMENT_KEYS
            },
            "ELMOS_MINIAPP_SCHEMA_PYTHON": executables["schema_python"]["path"],
        },
    }


def _utc_timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _parse_utc_timestamp(value: Any, path: str) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z",
        value,
    ):
        fail(f"{path} must be an exact UTC millisecond timestamp")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        fail(f"{path} is invalid: {exc}")


def _qualification_execution_argv(
    command: QualificationCommand,
    environment_binding: dict[str, Any],
    repository_root: Path,
) -> tuple[str, ...]:
    repository_root = repository_root.resolve()
    executable_name = {
        "component-build": "component_tsc",
        "component-tests": "component_jest",
        "frontend-build": "frontend_tsc",
        "frontend-tests": "node",
        "integration-tests": "uv",
    }.get(command.command_id)
    if executable_name is None:
        executable = Path(command.argv[0])
        if not executable.is_absolute():
            executable = (
                repository_root / command.relative_cwd / executable
            ).absolute()
        return (str(executable), *command.argv[1:])
    executable = environment_binding["executables"][executable_name]["execution_path"]
    return (executable, *command.argv[1:])


def _receipt_digest(receipt: dict[str, Any]) -> str:
    payload = {key: value for key, value in receipt.items() if key != "receipt_digest"}
    return digest(_canonical_json_bytes(payload))


def _parse_test_counts(parser: str, content: str, label: str) -> dict[str, int]:
    if parser == "jest":
        line_match = re.search(r"(?m)^Tests:\s+(.+)$", content)
        if line_match is None:
            fail(f"qualification log does not contain a Jest Tests summary: {label}")
        summary = line_match.group(1)
        total_match = re.search(r"(\d+)\s+total", summary)
        passed_match = re.search(r"(\d+)\s+passed", summary)
        skipped_match = re.search(r"(\d+)\s+skipped", summary)
        failed_match = re.search(r"(\d+)\s+failed", summary)
        if total_match is None or passed_match is None:
            fail(f"qualification Jest counts are incomplete: {label}")
        total = int(total_match.group(1))
        passed = int(passed_match.group(1))
        skipped = int(skipped_match.group(1)) if skipped_match else 0
        failed = int(failed_match.group(1)) if failed_match else 0
    elif parser == "node-test":
        def node_count(name: str) -> int:
            match = re.search(rf"(?m)^(?:ℹ|#)\s+{re.escape(name)}\s+(\d+)\s*$", content)
            if match is None:
                fail(f"qualification Node test log is missing {name}: {label}")
            return int(match.group(1))

        total = node_count("tests")
        passed = node_count("pass")
        failed = node_count("fail")
        skipped = node_count("skipped")
    elif parser == "unittest":
        total_match = re.search(r"(?m)^Ran\s+(\d+)\s+tests?\s+in\s+", content)
        if total_match is None or not re.search(r"(?m)^OK\s*$", content):
            fail(f"qualification unittest log has no successful summary: {label}")
        total = int(total_match.group(1))
        skipped_match = re.search(r"skipped=(\d+)", content)
        skipped = int(skipped_match.group(1)) if skipped_match else 0
        failed = 0
        passed = total - skipped
    else:
        fail(f"unsupported qualification result parser: {parser}")
    if total < 1 or passed < 1 or min(failed, skipped) < 0:
        fail(f"qualification test counts are invalid: {label}")
    if failed != 0 or skipped != 0 or passed != total:
        fail(
            f"qualification test counts do not represent a complete no-skip run: {label}: "
            f"total={total} passed={passed} failed={failed} skipped={skipped}"
        )
    return {
        "total_tests": total,
        "passed_tests": passed,
        "failed_tests": failed,
        "skipped_tests": skipped,
    }


def _assert_json_keys(
    value: Any,
    label: str,
    required: set[str],
    optional: set[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(f"{label} must be an object")
    optional = optional or set()
    missing = sorted(required - set(value))
    extra = sorted(set(value) - required - optional)
    if missing or extra:
        fail(f"{label} keys drifted: missing={missing} extra={extra}")
    return value


def _load_local_runtime_receipt(
    repository_root: Path,
    runtime: dict[str, Any],
) -> tuple[dict[str, Any], bytes] | None:
    probed_receipt_bytes = _read_bounded_regular_file(
        repository_root,
        LOCAL_RECEIPT_RELATIVE.as_posix(),
        "local runtime receipt",
        MAX_LOCAL_RECEIPT_BYTES,
        missing_ok=True,
    )
    if probed_receipt_bytes is None:
        return None
    receipt_root = repository_root / LOCAL_RECEIPT_ROOT_RELATIVE
    receipt_root_identity = _directory_identity(
        receipt_root,
        "local runtime receipt bundle",
    )
    receipt_bytes = _read_bounded_regular_file(
        receipt_root,
        "receipt.json",
        "local runtime receipt",
        MAX_LOCAL_RECEIPT_BYTES,
        expected_root_identity=receipt_root_identity,
    )
    if receipt_bytes is None or receipt_bytes != probed_receipt_bytes:
        fail("local runtime receipt bundle changed while it was opened")
    receipt = _assert_json_keys(
        _load_bounded_json_bytes(receipt_bytes, "local runtime receipt"),
        "local runtime receipt",
        {
            "schema_version",
            "implementation_digest",
            "qualification_suite_digest",
            "environment",
            "started_at",
            "ended_at",
            "duration_ms",
            "commands",
            "receipt_digest",
        },
    )
    if receipt.get("schema_version") != "elmos.frontend-to-miniapp.local-runtime-receipt.v1":
        fail("local runtime receipt schema version is invalid")
    supplied_receipt_digest = receipt.get("receipt_digest")
    if not isinstance(supplied_receipt_digest, str) or supplied_receipt_digest != _receipt_digest(receipt):
        fail("local runtime receipt digest mismatch")
    if receipt.get("implementation_digest") != runtime["implementation_digest"]:
        fail(
            "local runtime receipt implementation digest drifted: "
            f"receipt={receipt.get('implementation_digest')} "
            f"current={runtime['implementation_digest']}"
        )
    if receipt.get("qualification_suite_digest") != _qualification_suite_digest():
        fail("local runtime receipt qualification command catalog drifted")
    current_environment = _local_qualification_environment(
        repository_root=repository_root,
    )
    if receipt.get("environment") != current_environment:
        fail("local runtime receipt execution environment drifted")
    started_at = _parse_utc_timestamp(
        receipt.get("started_at"),
        "local runtime receipt started_at",
    )
    ended_at = _parse_utc_timestamp(
        receipt.get("ended_at"),
        "local runtime receipt ended_at",
    )
    duration_ms = receipt.get("duration_ms")
    if ended_at < started_at:
        fail("local runtime receipt ended_at precedes started_at")
    if not isinstance(duration_ms, int) or isinstance(duration_ms, bool) or duration_ms < 0:
        fail("local runtime receipt duration_ms must be a non-negative integer")
    commands = receipt.get("commands")
    if not isinstance(commands, list) or len(commands) != len(LOCAL_QUALIFICATION_COMMANDS):
        fail("local runtime receipt command count drifted")
    for index, (record_value, expected) in enumerate(
        zip(commands, LOCAL_QUALIFICATION_COMMANDS, strict=True)
    ):
        required = {
            "id",
            "cwd",
            "resolved_cwd",
            "argv",
            "resolved_argv",
            "command",
            "claim",
            "started_at",
            "ended_at",
            "duration_ms",
            "state",
            "exit_code",
            "evidence",
        }
        if expected.result_parser:
            required.update(
                {
                    "expected_test_count",
                    "total_tests",
                    "passed_tests",
                    "failed_tests",
                    "skipped_tests",
                }
            )
        record = _assert_json_keys(
            record_value,
            f"local runtime receipt commands[{index}]",
            required,
        )
        binding = _qualification_command_binding(expected)
        if record.get("id") != expected.command_id or any(
            record.get(key) != value for key, value in binding.items()
        ) or record.get("resolved_cwd") != str(
            (repository_root / expected.relative_cwd).resolve()
        ) or record.get("resolved_argv") != list(
            _qualification_execution_argv(
                expected,
                current_environment,
                repository_root,
            )
        ) or record.get("state") != "PASSED" or record.get("exit_code") != 0:
            fail(f"local runtime receipt command binding drifted: {expected.command_id}")
        command_started_at = _parse_utc_timestamp(
            record.get("started_at"),
            f"local runtime receipt commands[{index}].started_at",
        )
        command_ended_at = _parse_utc_timestamp(
            record.get("ended_at"),
            f"local runtime receipt commands[{index}].ended_at",
        )
        command_duration_ms = record.get("duration_ms")
        if command_ended_at < command_started_at:
            fail(
                "local runtime receipt command ended_at precedes started_at: "
                f"{expected.command_id}"
            )
        if (
            not isinstance(command_duration_ms, int)
            or isinstance(command_duration_ms, bool)
            or command_duration_ms < 0
        ):
            fail(
                "local runtime receipt command duration_ms must be a non-negative "
                f"integer: {expected.command_id}"
            )
        evidence = _assert_json_keys(
            record.get("evidence"),
            f"local runtime receipt commands[{index}].evidence",
            {"path", "bytes", "sha256"},
        )
        expected_log_relative = (
            LOCAL_RECEIPT_ROOT_RELATIVE / "logs" / f"{expected.command_id}.log"
        ).as_posix()
        if evidence.get("path") != expected_log_relative:
            fail(f"local runtime receipt log path drifted: {expected.command_id}")
        _validate_relative_path(expected_log_relative, "local runtime receipt evidence")
        bundle_log_relative = (Path("logs") / f"{expected.command_id}.log").as_posix()
        log_bytes = _read_bounded_regular_file(
            receipt_root,
            bundle_log_relative,
            "local runtime receipt log",
            MAX_LOCAL_QUALIFICATION_LOG_BYTES,
            expected_root_identity=receipt_root_identity,
        )
        if log_bytes is None:
            fail(f"local runtime receipt log is missing: {expected_log_relative}")
        if evidence.get("bytes") != len(log_bytes) or evidence.get("sha256") != digest(log_bytes):
            fail(f"local runtime receipt log digest or byte count drifted: {expected.command_id}")
        try:
            log_text = log_bytes.decode("utf-8")
        except UnicodeError as exc:
            fail(f"local runtime receipt log is not UTF-8: {expected.command_id}: {exc}")
        if expected.result_parser:
            observed_counts = _parse_test_counts(
                expected.result_parser,
                log_text,
                expected.command_id,
            )
            supplied_counts = {
                key: record.get(key)
                for key in (
                    "total_tests",
                    "passed_tests",
                    "failed_tests",
                    "skipped_tests",
                )
            }
            if supplied_counts != observed_counts:
                fail(
                    f"local runtime receipt test counts drifted: {expected.command_id}: "
                    f"receipt={supplied_counts} log={observed_counts}"
                )
            if (
                expected.expected_test_count is None
                or record.get("expected_test_count") != expected.expected_test_count
                or observed_counts["total_tests"] != expected.expected_test_count
            ):
                fail(
                    f"local runtime receipt exact test count drifted: "
                    f"{expected.command_id}: expected={expected.expected_test_count} "
                    f"observed={observed_counts['total_tests']}"
                )
    _assert_directory_path_identity(
        receipt_root,
        receipt_root_identity,
        "local runtime receipt bundle after validation",
    )
    return receipt, receipt_bytes


def _local_runtime_evidence(
    runtime: dict[str, Any],
    repository_root: Path,
) -> dict[str, Any]:
    loaded_receipt = _load_local_runtime_receipt(repository_root, runtime)
    executed = loaded_receipt is not None
    if executed:
        assert loaded_receipt is not None
        receipt, receipt_bytes = loaded_receipt
        commands = receipt["commands"]
        receipt_binding: dict[str, Any] = {
            "state": "VERIFIED",
            "path": LOCAL_RECEIPT_RELATIVE.as_posix(),
            "receipt_digest": receipt["receipt_digest"],
            "file_sha256": digest(receipt_bytes),
            "qualification_suite_digest": receipt["qualification_suite_digest"],
            "environment": receipt["environment"],
            "started_at": receipt["started_at"],
            "ended_at": receipt["ended_at"],
            "duration_ms": receipt["duration_ms"],
        }
    else:
        commands = []
        for command in LOCAL_QUALIFICATION_COMMANDS:
            record: dict[str, Any] = {
                "id": command.command_id,
                "command": command.display,
                "state": "NOT_RUN",
                "claim": command.claim,
            }
            if command.expected_test_count is not None:
                record["expected_test_count"] = command.expected_test_count
            commands.append(record)
        receipt_binding = {
            "state": "ABSENT",
            "path": LOCAL_RECEIPT_RELATIVE.as_posix(),
        }
    return {
        "schema_version": "elmos.frontend-to-miniapp.local-runtime-evidence.v1",
        "implementation_digest": runtime["implementation_digest"],
        "state": (
            EXECUTED_RUNTIME_EVIDENCE_STATUS
            if executed
            else DECLARED_RUNTIME_EVIDENCE_STATUS
        ),
        "scope": "bounded-local-engineering",
        "receipt": receipt_binding,
        "commands": commands,
        "local_claims": {
            "handlers_callable": executed,
            "source_labels_exercised": executed,
            "native_candidates_generated": executed,
            "resume_and_idempotency_exercised": executed,
            "negative_schema_and_path_cases_exercised": executed,
        },
        "official_platform_builds": "NOT_RUN",
        "emulator_device_runtime": "NOT_RUN",
        "visual_accessibility_performance": "NOT_RUN",
        "independent_holdout_and_representative": "NOT_RUN",
        "platform_review_upload_release": "NOT_RUN",
        "independent_verification": "NOT_RUN",
        "external_evidence_status": EXTERNAL_EVIDENCE_STATUS,
        "certification": CERTIFICATION_STATUS,
    }


def _open_receipt_writer_lock_root(
    destination: Path,
    repository_root: Path | None,
) -> tuple[Path, int, DirectoryIdentity]:
    if repository_root is not None:
        try:
            SYSTEM_TEMP_ROOT.relative_to(repository_root.resolve())
        except ValueError:
            pass
        else:
            fail("local runtime receipt writer lock root may not be inside repository")
    lock_root = SYSTEM_TEMP_ROOT / "elmos-frontend-miniapp-writer-locks-v1"
    system_descriptor, _system_identity = _open_verified_directory(
        SYSTEM_TEMP_ROOT,
        "system temporary root for receipt writer lock",
    )
    try:
        try:
            os.mkdir(lock_root.name, 0o700, dir_fd=system_descriptor)
        except FileExistsError:
            pass
    finally:
        os.close(system_descriptor)
    descriptor, identity = _open_verified_directory(
        lock_root,
        "local runtime receipt writer lock root",
    )
    opened = os.fstat(descriptor)
    if opened.st_uid != os.getuid() or stat.S_IMODE(opened.st_mode) != 0o700:
        os.close(descriptor)
        fail(
            "local runtime receipt writer lock root is not an owned 0700 directory: "
            f"{lock_root}"
        )
    return lock_root, descriptor, identity


@contextmanager
def _reserve_local_receipt_bundle(
    destination: Path,
    repository_root: Path | None = None,
) -> Iterator[ReceiptWriterReservation]:
    parent = destination.parent
    if repository_root is not None:
        _assert_inside(repository_root, parent, "local runtime receipt parent")
    parent_descriptor, parent_identity = _open_verified_directory(
        parent,
        "local runtime receipt parent",
    )
    try:
        lock_parent, lock_parent_descriptor, lock_parent_identity = (
            _open_receipt_writer_lock_root(destination, repository_root)
        )
    except BaseException:
        os.close(parent_descriptor)
        raise
    canonical_destination = parent.resolve(strict=True) / destination.name
    lock_key = sha256_bytes(str(canonical_destination).encode("utf-8"))
    lock_name = f"{lock_key}.lock"
    flags = (
        os.O_RDWR
        | os.O_CREAT
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(
            lock_name,
            flags,
            0o600,
            dir_fd=lock_parent_descriptor,
        )
    except OSError as exc:
        os.close(parent_descriptor)
        os.close(lock_parent_descriptor)
        fail(f"local runtime receipt reservation failed: {lock_parent / lock_name}: {exc}")
    reservation: ReceiptWriterReservation | None = None
    body_failed = False
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail(
                "local runtime receipt is reserved by another writer: "
                f"{parent / lock_name}"
            )
        opened = os.fstat(descriptor)
        current = os.stat(
            lock_name,
            dir_fd=lock_parent_descriptor,
            follow_symlinks=False,
        )
        lock_identity = _directory_identity_from_stat(opened)
        if (
            not stat.S_ISREG(opened.st_mode)
            or not stat.S_ISREG(current.st_mode)
            or _directory_identity_from_stat(current) != lock_identity
            or opened.st_nlink != 1
            or opened.st_uid != os.getuid()
            or stat.S_IMODE(opened.st_mode) != 0o600
            or opened.st_size != 0
        ):
            fail(
                "local runtime receipt reservation is not an owned empty regular file: "
                f"{lock_parent / lock_name}"
            )
        reservation = ReceiptWriterReservation(
            parent_path=parent,
            parent_descriptor=parent_descriptor,
            parent_identity=parent_identity,
            lock_parent_path=lock_parent,
            lock_parent_descriptor=lock_parent_descriptor,
            lock_parent_identity=lock_parent_identity,
            lock_name=lock_name,
            lock_descriptor=descriptor,
            lock_identity=lock_identity,
        )
        reservation.assert_current("acquisition")
        try:
            yield reservation
        except BaseException:
            body_failed = True
            raise
    finally:
        try:
            if reservation is not None:
                try:
                    reservation.assert_current("release")
                except IntegrationError:
                    if not body_failed:
                        raise
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            except OSError:
                pass
            os.close(descriptor)
            os.close(parent_descriptor)
            os.close(lock_parent_descriptor)


def _assert_replaceable_receipt_bundle(
    destination: Path,
) -> tuple[int, int, str] | None:
    if not destination.exists() and not destination.is_symlink():
        return None
    if not destination.is_dir() or destination.is_symlink():
        fail(f"local runtime receipt destination is unowned or unsafe: {destination}")
    destination_identity = _directory_identity(
        destination,
        "local runtime receipt destination",
    )
    for path in destination.rglob("*"):
        if path.is_symlink() or (not path.is_file() and not path.is_dir()):
            fail(f"local runtime receipt bundle contains an unsafe entry: {path}")
    _assert_directory_path_identity(
        destination,
        destination_identity,
        "local runtime receipt destination after inventory",
    )
    receipt_bytes = _read_bounded_regular_file(
        destination,
        "receipt.json",
        "prior local runtime receipt",
        MAX_LOCAL_RECEIPT_BYTES,
        expected_root_identity=destination_identity,
    )
    if receipt_bytes is None:
        fail(f"local runtime receipt destination is unowned: {destination}")
    receipt = _assert_json_keys(
        _load_bounded_json_bytes(receipt_bytes, "prior local runtime receipt"),
        "prior local runtime receipt",
        {
            "schema_version",
            "implementation_digest",
            "qualification_suite_digest",
            "environment",
            "started_at",
            "ended_at",
            "duration_ms",
            "commands",
            "receipt_digest",
        },
    )
    if (
        receipt.get("schema_version")
        != "elmos.frontend-to-miniapp.local-runtime-receipt.v1"
        or receipt.get("receipt_digest") != _receipt_digest(receipt)
    ):
        fail(f"local runtime receipt destination is identity-drifted: {destination}")
    commands = receipt.get("commands")
    if not isinstance(commands, list):
        fail(f"local runtime receipt destination has no command inventory: {destination}")
    owned_files = {"receipt.json"}
    for index, command in enumerate(commands):
        if not isinstance(command, dict) or not isinstance(command.get("evidence"), dict):
            fail(f"prior local runtime receipt command is invalid: {index}")
        evidence_path = command["evidence"].get("path")
        if not isinstance(evidence_path, str):
            fail(f"prior local runtime receipt evidence path is invalid: {index}")
        _validate_relative_path(evidence_path, "prior local runtime receipt evidence")
        try:
            relative = PurePosixPath(evidence_path).relative_to(
                PurePosixPath(LOCAL_RECEIPT_ROOT_RELATIVE.as_posix())
            )
        except ValueError:
            fail(f"prior local runtime receipt evidence escapes its bundle: {evidence_path}")
        bundle_relative = relative.as_posix()
        evidence_bytes = _read_bounded_regular_file(
            destination,
            bundle_relative,
            "prior local runtime receipt evidence",
            MAX_LOCAL_QUALIFICATION_LOG_BYTES,
            expected_root_identity=destination_identity,
        )
        if evidence_bytes is None:
            fail(f"prior local runtime receipt evidence is missing: {evidence_path}")
        if (
            command["evidence"].get("bytes") != len(evidence_bytes)
            or command["evidence"].get("sha256") != digest(evidence_bytes)
        ):
            fail(f"prior local runtime receipt evidence drifted: {evidence_path}")
        owned_files.add(bundle_relative)
    actual_files = {
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_file()
    }
    if actual_files != owned_files:
        fail(
            "local runtime receipt destination contains unowned or missing files: "
            f"missing={sorted(owned_files - actual_files)} "
            f"extra={sorted(actual_files - owned_files)}"
        )
    _assert_directory_path_identity(
        destination,
        destination_identity,
        "local runtime receipt destination after validation",
    )
    receipt_digest = receipt.get("receipt_digest")
    if not isinstance(receipt_digest, str):
        fail(f"local runtime receipt destination has no digest: {destination}")
    return (
        destination_identity.device,
        destination_identity.inode,
        receipt_digest,
    )


def record_local_runtime_qualification(
    repository_root: Path = ROOT,
) -> dict[str, Any]:
    """Run the fixed trusted local suite and atomically record raw receipt bytes."""

    repository_root = repository_root.resolve()
    runtime = _runtime_implementation(repository_root)
    destination = repository_root / LOCAL_RECEIPT_ROOT_RELATIVE
    receipt_parent = _ensure_relative_directory(
        repository_root,
        LOCAL_RECEIPT_ROOT_RELATIVE.parent,
        "local runtime receipt parent",
    )
    if receipt_parent != destination.parent:
        fail("local runtime receipt parent path drifted")
    qualification_started_at = _utc_timestamp()
    qualification_started_ns = time.monotonic_ns()
    environment = _qualification_environment_variables()
    environment_binding = _local_qualification_environment(
        environment,
        repository_root,
    )
    environment.update(environment_binding["variables"])
    with (
        _reserve_local_receipt_bundle(destination, repository_root) as reservation,
        tempfile.TemporaryDirectory(
            prefix=".frontend-miniapp-qualification-",
            dir=destination.parent,
        ) as temporary,
    ):
        reservation.assert_current("before qualification")
        original_destination_identity = _assert_replaceable_receipt_bundle(destination)
        temporary_root = Path(temporary)
        _assert_inside(repository_root, temporary_root, "local qualification staging")
        _assert_directory_path_identity(
            destination.parent,
            reservation.parent_identity,
            "local runtime receipt parent before qualification",
        )
        staging = temporary_root / "staging"
        logs = staging / "logs"
        logs.mkdir(parents=True)
        command_records: list[dict[str, Any]] = []
        for command in LOCAL_QUALIFICATION_COMMANDS:
            cwd = repository_root / command.relative_cwd
            if not cwd.is_dir() or cwd.is_symlink():
                fail(f"qualification working directory is missing or unsafe: {cwd}")
            argv = _qualification_execution_argv(
                command,
                environment_binding,
                repository_root,
            )
            command_started_at = _utc_timestamp()
            command_started_ns = time.monotonic_ns()
            try:
                completed = subprocess.run(
                    argv,
                    cwd=cwd,
                    env=environment,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    check=False,
                    timeout=900,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                fail(f"local qualification command could not complete: {command.command_id}: {exc}")
            command_ended_at = _utc_timestamp()
            command_duration_ms = max(
                0,
                (time.monotonic_ns() - command_started_ns) // 1_000_000,
            )
            output = completed.stdout
            if len(output) > MAX_LOCAL_QUALIFICATION_LOG_BYTES:
                fail(
                    "local qualification output exceeds the bounded receipt limit: "
                    f"{command.command_id}: {len(output)} bytes"
                )
            if completed.returncode != 0:
                tail = output.decode("utf-8", errors="replace")[-2000:]
                fail(
                    f"local qualification command failed: {command.command_id}: "
                    f"exit={completed.returncode}: {tail}"
                )
            try:
                output_text = output.decode("utf-8")
            except UnicodeError as exc:
                fail(f"local qualification output is not UTF-8: {command.command_id}: {exc}")
            log = logs / f"{command.command_id}.log"
            log.write_bytes(output)
            record: dict[str, Any] = {
                "id": command.command_id,
                **_qualification_command_binding(command),
                "resolved_cwd": str(cwd.resolve()),
                "resolved_argv": list(argv),
                "started_at": command_started_at,
                "ended_at": command_ended_at,
                "duration_ms": command_duration_ms,
                "state": "PASSED",
                "exit_code": completed.returncode,
                "evidence": {
                    "path": (
                        LOCAL_RECEIPT_ROOT_RELATIVE
                        / "logs"
                        / f"{command.command_id}.log"
                    ).as_posix(),
                    "bytes": len(output),
                    "sha256": digest(output),
                },
            }
            if command.result_parser:
                counts = _parse_test_counts(
                    command.result_parser,
                    output_text,
                    command.command_id,
                )
                if counts["total_tests"] != command.expected_test_count:
                    fail(
                        f"local qualification exact test count drifted: "
                        f"{command.command_id}: expected={command.expected_test_count} "
                        f"observed={counts['total_tests']}"
                    )
                record["expected_test_count"] = command.expected_test_count
                record.update(counts)
            command_records.append(record)
        current_environment = _local_qualification_environment(
            environment,
            repository_root,
        )
        if current_environment != environment_binding:
            fail("local qualification execution environment changed during the run")
        current_runtime = _runtime_implementation(repository_root)
        if current_runtime["implementation_digest"] != runtime["implementation_digest"]:
            fail(
                "runtime implementation changed during local qualification: "
                f"before={runtime['implementation_digest']} "
                f"after={current_runtime['implementation_digest']}"
            )
        qualification_ended_at = _utc_timestamp()
        qualification_duration_ms = max(
            0,
            (time.monotonic_ns() - qualification_started_ns) // 1_000_000,
        )
        receipt: dict[str, Any] = {
            "schema_version": "elmos.frontend-to-miniapp.local-runtime-receipt.v1",
            "implementation_digest": runtime["implementation_digest"],
            "qualification_suite_digest": _qualification_suite_digest(),
            "environment": environment_binding,
            "started_at": qualification_started_at,
            "ended_at": qualification_ended_at,
            "duration_ms": qualification_duration_ms,
            "commands": command_records,
        }
        receipt["receipt_digest"] = _receipt_digest(receipt)
        (staging / "receipt.json").write_bytes(
            json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
            + b"\n"
        )
        staged_receipt_identity = _assert_replaceable_receipt_bundle(staging)
        if (
            staged_receipt_identity is None
            or staged_receipt_identity[2] != receipt["receipt_digest"]
        ):
            fail("staged local runtime receipt bundle failed identity validation")
        published_identity = DirectoryIdentity(
            staged_receipt_identity[0],
            staged_receipt_identity[1],
        )
        backup = temporary_root / "backup"
        committed = False
        try:
            reservation.assert_current("before receipt commit")
            if _assert_replaceable_receipt_bundle(destination) != original_destination_identity:
                fail("local runtime receipt destination changed during qualification")
            destination_entry = _entry_stat_at(
                reservation.parent_descriptor,
                destination.name,
            )
            if destination_entry is not None:
                if original_destination_identity is None:
                    fail("local runtime receipt destination appeared during qualification")
                if not stat.S_ISDIR(destination_entry.st_mode):
                    fail(f"local runtime receipt destination is not a directory: {destination}")
                reservation.assert_current("immediately before receipt backup")
                os.replace(
                    destination.name,
                    backup,
                    src_dir_fd=reservation.parent_descriptor,
                )
                moved_identity = _directory_identity(
                    backup,
                    "moved local runtime receipt backup",
                )
                if (
                    moved_identity.device != original_destination_identity[0]
                    or moved_identity.inode != original_destination_identity[1]
                    or _assert_replaceable_receipt_bundle(backup)
                    != original_destination_identity
                ):
                    os.replace(
                        backup,
                        destination.name,
                        dst_dir_fd=reservation.parent_descriptor,
                    )
                    fail("local runtime receipt destination identity drifted during commit")
            reservation.assert_current("immediately before receipt publish")
            os.replace(
                staging,
                destination.name,
                dst_dir_fd=reservation.parent_descriptor,
            )
            committed = True
            reservation.assert_current("after receipt publish")
            published_entry = _entry_stat_at(
                reservation.parent_descriptor,
                destination.name,
            )
            if (
                published_entry is None
                or not stat.S_ISDIR(published_entry.st_mode)
                or _directory_identity_from_stat(published_entry) != published_identity
                or _assert_replaceable_receipt_bundle(destination)
                != staged_receipt_identity
            ):
                fail("local runtime receipt published destination identity drifted")
            loaded = _load_local_runtime_receipt(repository_root, runtime)
            if loaded is None:
                fail("local runtime receipt disappeared after atomic commit")
        except BaseException as exc:
            rollback_failures: list[str] = []
            preserve_from_temporary: list[tuple[Path, str]] = []
            destination_entry = _entry_stat_at(
                reservation.parent_descriptor,
                destination.name,
            )
            if committed and destination_entry is not None:
                current_identity = _directory_identity_from_stat(destination_entry)
                if (
                    not stat.S_ISDIR(destination_entry.st_mode)
                    or current_identity != published_identity
                ):
                    rollback_failures.append(
                        "published receipt destination was replaced before rollback"
                    )
                else:
                    failed_destination = temporary_root / "failed-published-receipt"
                    try:
                        os.replace(
                            destination.name,
                            failed_destination,
                            src_dir_fd=reservation.parent_descriptor,
                        )
                        if (
                            _directory_identity(
                                failed_destination,
                                "failed published local runtime receipt",
                            )
                            != published_identity
                            or _assert_replaceable_receipt_bundle(failed_destination)
                            != staged_receipt_identity
                        ):
                            rollback_failures.append(
                                "receipt rollback moved an identity-drifted published bundle"
                            )
                            preserve_from_temporary.append(
                                (failed_destination, "published-receipt")
                            )
                    except (OSError, IntegrationError) as rollback_exc:
                        rollback_failures.append(
                            f"published receipt could not be quarantined: {rollback_exc}"
                        )
                        if failed_destination.exists() or failed_destination.is_symlink():
                            preserve_from_temporary.append(
                                (failed_destination, "published-receipt")
                            )
            if backup.exists() or backup.is_symlink():
                try:
                    if (
                        original_destination_identity is None
                        or _assert_replaceable_receipt_bundle(backup)
                        != original_destination_identity
                    ):
                        raise IntegrationError(
                            "local runtime receipt backup identity drifted before rollback"
                        )
                    if _entry_stat_at(
                        reservation.parent_descriptor,
                        destination.name,
                    ) is not None:
                        raise IntegrationError(
                            "competing local runtime receipt destination blocks rollback"
                        )
                    os.replace(
                        backup,
                        destination.name,
                        dst_dir_fd=reservation.parent_descriptor,
                    )
                    if (
                        _assert_replaceable_receipt_bundle(destination)
                        != original_destination_identity
                    ):
                        raise IntegrationError(
                            "restored local runtime receipt identity drifted"
                        )
                except (OSError, IntegrationError) as rollback_exc:
                    rollback_failures.append(str(rollback_exc))
                    if backup.exists() or backup.is_symlink():
                        preserve_from_temporary.append((backup, "prior-receipt-backup"))
            if preserve_from_temporary:
                recovery_root = Path(
                    tempfile.mkdtemp(
                        prefix=".frontend-miniapp-receipt-recovery-",
                        dir=destination.parent,
                    )
                )
                for recovery_source, recovery_name in preserve_from_temporary:
                    if recovery_source.exists() or recovery_source.is_symlink():
                        os.replace(recovery_source, recovery_root / recovery_name)
                rollback_failures.append(
                    f"unrestored receipt data preserved at {recovery_root}"
                )
            if rollback_failures:
                raise IntegrationError(
                    "local runtime receipt commit failed and rollback was incomplete: "
                    f"original={exc}; rollback={rollback_failures}"
                ) from exc
            raise
    return _local_runtime_evidence(runtime, repository_root)


def _load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        fail(f"invalid {label}: {path}: {exc}")


def _load_yaml(path: Path, label: str) -> Any:
    try:
        import yaml
    except ModuleNotFoundError as exc:
        fail("PyYAML is required for MiniApp Skill contract validation")
        raise AssertionError from exc
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        fail(f"invalid {label}: {path}: {exc}")


def _validate_schemas_and_fixtures(source: Path) -> dict[str, Any]:
    """Validate package Schemas and fixtures without executing package scripts."""

    try:
        from jsonschema import Draft202012Validator, FormatChecker
        from jsonschema.exceptions import SchemaError
    except ModuleNotFoundError as exc:
        fail("jsonschema is required for MiniApp Schema and fixture validation")
        raise AssertionError from exc

    schema_paths = sorted(source.glob("schemas/*.schema.json"))
    if len(schema_paths) != 14:
        fail(
            "source package must contain exactly 14 JSON Schemas; "
            f"found {len(schema_paths)}"
        )
    fixture_index = _load_yaml(
        source / "fixtures" / "index.yaml",
        "fixture index",
    )
    if not isinstance(fixture_index, dict) or set(fixture_index) != {"fixtures"}:
        fail("fixture index must contain only the fixtures mapping")
    mapping = fixture_index["fixtures"]
    if (
        not isinstance(mapping, dict)
        or len(mapping) != 14
        or any(
            not isinstance(schema_name, str)
            or not isinstance(fixture_name, str)
            for schema_name, fixture_name in mapping.items()
        )
    ):
        fail("fixture index must contain exactly 14 string-to-string mappings")
    schema_names = [path.name for path in schema_paths]
    if set(mapping) != set(schema_names):
        fail(
            "fixture index Schema coverage is not exact: "
            f"missing={sorted(set(schema_names) - set(mapping))} "
            f"extra={sorted(set(mapping) - set(schema_names))}"
        )
    fixture_names = list(mapping.values())
    if len(set(fixture_names)) != len(fixture_names):
        fail("fixture index must map each Schema to a distinct fixture")
    actual_fixture_names = sorted(
        path.name for path in (source / "fixtures").glob("*.json")
    )
    if sorted(fixture_names) != actual_fixture_names:
        fail(
            "fixture index coverage is not exact: "
            f"missing={sorted(set(actual_fixture_names) - set(fixture_names))} "
            f"extra={sorted(set(fixture_names) - set(actual_fixture_names))}"
        )

    validated: list[dict[str, str]] = []
    format_checker = FormatChecker()
    for schema_path in schema_paths:
        schema = _load_json(schema_path, "JSON Schema")
        if (
            not isinstance(schema, dict)
            or schema.get("$schema")
            != "https://json-schema.org/draft/2020-12/schema"
            or not isinstance(schema.get("$id"), str)
            or schema.get("type") != "object"
        ):
            fail(f"JSON Schema metadata is invalid: {schema_path.relative_to(source)}")
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as exc:
            fail(f"JSON Schema is not Draft 2020-12 valid: {schema_path.name}: {exc}")
        fixture_name = mapping[schema_path.name]
        fixture_relative = _validate_relative_path(
            f"fixtures/{fixture_name}",
            "fixture",
        )
        if len(fixture_relative.parts) != 2:
            fail(f"fixture index path must be a direct fixture filename: {fixture_name}")
        fixture_path = source / fixture_relative
        fixture = _load_json(fixture_path, "Schema fixture")
        if not isinstance(fixture, dict):
            fail(f"Schema fixture must be an object: {fixture_name}")
        errors = sorted(
            Draft202012Validator(
                schema,
                format_checker=format_checker,
            ).iter_errors(fixture),
            key=lambda error: [str(value) for value in error.absolute_path],
        )
        if errors:
            error = errors[0]
            instance_path = ".".join(str(value) for value in error.absolute_path)
            fail(
                f"Schema fixture validation failed: {fixture_name}:"
                f"{instance_path or '<root>'}: {error.message}"
            )
        validated.append(
            {
                "schema": schema_path.name,
                "fixture": fixture_name,
            }
        )
    return {
        "schema_count": len(schema_paths),
        "fixture_count": len(validated),
        "bindings": validated,
    }


def _validate_relative_path(relative: str, label: str) -> PurePosixPath:
    if not relative or "\\" in relative or "\x00" in relative:
        fail(f"invalid {label} path: {relative!r}")
    if unicodedata.normalize("NFC", relative) != relative:
        fail(f"{label} path is not NFC-normalized: {relative!r}")
    value = PurePosixPath(relative)
    if (
        value.is_absolute()
        or value.as_posix() != relative
        or any(part in {"", ".", ".."} for part in value.parts)
    ):
        fail(f"{label} path escapes or is not normalized: {relative!r}")
    return value


def _archive_relative(name: str) -> str:
    path = _validate_relative_path(name, "archive")
    if len(path.parts) < 2 or path.parts[0] != PACKAGE_DIRECTORY:
        fail(f"archive entry is outside the single package root: {name!r}")
    return PurePosixPath(*path.parts[1:]).as_posix()


def inspect_archive(
    archive: Path,
    *,
    trusted_sha256: str | None = EXPECTED_ARCHIVE_SHA256,
    expected_entry_count: int | None = EXPECTED_ARCHIVE_ENTRY_COUNT,
    expected_total_bytes: int | None = EXPECTED_ARCHIVE_UNCOMPRESSED_BYTES,
    expected_mode_counts: dict[int, int] | None = EXPECTED_MODE_COUNTS,
) -> dict[str, ArchiveRecord]:
    """Inspect every ZIP entry without writing it or executing package code."""

    if not archive.is_file() or archive.is_symlink():
        fail(f"source archive must be a regular file: {archive}")
    actual_archive_sha256 = sha256_file(archive)
    if trusted_sha256 is not None and actual_archive_sha256 != trusted_sha256:
        fail(
            "archive trusted SHA-256 mismatch: "
            f"expected={trusted_sha256} actual={actual_archive_sha256}"
        )
    records: dict[str, ArchiveRecord] = {}
    raw_names: set[str] = set()
    folded_names: set[str] = set()
    total_bytes = 0
    mode_counts: dict[int, int] = {}
    try:
        with zipfile.ZipFile(archive) as handle:
            infos = handle.infolist()
            for info in infos:
                if info.filename in raw_names:
                    fail(f"duplicate archive entry: {info.filename!r}")
                raw_names.add(info.filename)
                relative = _archive_relative(info.filename)
                folded = unicodedata.normalize("NFC", relative).casefold()
                if folded in folded_names:
                    fail(f"case-folded duplicate archive entry: {relative!r}")
                folded_names.add(folded)
                if info.is_dir() or info.filename.endswith("/"):
                    fail(f"directory entries are not allowed in the archive: {info.filename!r}")
                if info.flag_bits & 0x1:
                    fail(f"encrypted archive entry is not allowed: {info.filename!r}")
                if info.compress_type != zipfile.ZIP_DEFLATED:
                    fail(f"unsupported archive compression for {info.filename!r}")
                unix_mode = (info.external_attr >> 16) & 0xFFFF
                if info.create_system != 3 or stat.S_IFMT(unix_mode) != stat.S_IFREG:
                    fail(f"archive entry is not a Unix regular file: {info.filename!r}")
                mode = stat.S_IMODE(unix_mode)
                if mode not in {0o644, 0o755}:
                    fail(f"archive entry has unsupported mode {mode:#o}: {info.filename!r}")
                if info.file_size > MAX_ARCHIVE_ENTRY_BYTES:
                    fail(f"archive entry exceeds size limit: {info.filename!r}")
                ratio = info.file_size / max(info.compress_size, 1)
                if ratio > MAX_COMPRESSION_RATIO:
                    fail(f"archive entry exceeds compression-ratio limit: {info.filename!r}")
                total_bytes += info.file_size
                if total_bytes > MAX_ARCHIVE_TOTAL_BYTES:
                    fail("archive exceeds total uncompressed size limit")
                value = hashlib.sha256()
                observed_size = 0
                with handle.open(info, "r") as member:
                    for chunk in iter(lambda: member.read(64 * 1024), b""):
                        observed_size += len(chunk)
                        if observed_size > MAX_ARCHIVE_ENTRY_BYTES:
                            fail(f"expanded archive entry exceeds size limit: {info.filename!r}")
                        value.update(chunk)
                if observed_size != info.file_size:
                    fail(f"archive entry size changed while reading: {info.filename!r}")
                records[relative] = ArchiveRecord(
                    archive_name=info.filename,
                    relative=relative,
                    size=info.file_size,
                    mode=mode,
                    sha256=value.hexdigest(),
                )
                mode_counts[mode] = mode_counts.get(mode, 0) + 1
    except (OSError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        fail(f"cannot validate source archive: {archive}: {exc}")
    if expected_entry_count is not None and len(records) != expected_entry_count:
        fail(
            f"archive must contain exactly {expected_entry_count} files; found {len(records)}"
        )
    if expected_total_bytes is not None and total_bytes != expected_total_bytes:
        fail(
            "archive uncompressed byte count mismatch: "
            f"expected={expected_total_bytes} actual={total_bytes}"
        )
    if expected_mode_counts is not None and mode_counts != expected_mode_counts:
        fail(
            f"archive mode distribution mismatch: expected={expected_mode_counts} "
            f"actual={mode_counts}"
        )
    return dict(sorted(records.items()))


def validate_archive(archive: Path = ROOT / ARCHIVE_RELATIVE) -> dict[str, ArchiveRecord]:
    return inspect_archive(archive)


def _assert_inside(root: Path, candidate: Path, label: str) -> None:
    try:
        candidate.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (OSError, ValueError):
        fail(f"{label} path escapes root: {candidate}")


def _source_files(source: Path) -> dict[str, Path]:
    if not source.is_dir() or source.is_symlink():
        fail(f"extracted package must be a real directory: {source}")
    values: dict[str, Path] = {}
    for entry in source.rglob("*"):
        relative = entry.relative_to(source).as_posix()
        if entry.is_symlink():
            fail(f"extracted package may not contain symbolic links: {relative}")
        if entry.is_file():
            _assert_inside(source, entry, "source file")
            values[relative] = entry
        elif not entry.is_dir():
            fail(f"unsupported extracted package entry: {relative}")
    return dict(sorted(values.items()))


def _parse_checksums(source: Path, files: dict[str, Path]) -> dict[str, str]:
    checksum_path = source / "CHECKSUMS.sha256"
    checksum_bytes = checksum_path.read_bytes()
    if sha256_bytes(checksum_bytes) != EXPECTED_CHECKSUMS_SHA256:
        fail("CHECKSUMS.sha256 trusted digest mismatch")
    try:
        lines = checksum_bytes.decode("utf-8").splitlines()
    except UnicodeError as exc:
        fail(f"CHECKSUMS.sha256 is not UTF-8: {exc}")
    entries: dict[str, str] = {}
    for line_number, line in enumerate(lines, 1):
        match = re.fullmatch(r"([0-9a-f]{64})  (\S(?:.*\S)?)", line)
        if match is None:
            fail(f"invalid CHECKSUMS.sha256 line {line_number}")
        expected, relative = match.groups()
        _validate_relative_path(relative, "checksum")
        if relative == "CHECKSUMS.sha256" or relative in entries:
            fail(f"duplicate or self-referential checksum path: {relative}")
        if relative not in files:
            fail(f"checksummed file is missing: {relative}")
        actual = sha256_file(files[relative])
        if actual != expected:
            fail(
                f"checksum mismatch for {relative}: expected={expected} actual={actual}"
            )
        entries[relative] = expected
    if len(entries) != EXPECTED_CHECKSUM_ENTRY_COUNT:
        fail(
            "CHECKSUMS.sha256 entry count mismatch: "
            f"expected={EXPECTED_CHECKSUM_ENTRY_COUNT} actual={len(entries)}"
        )
    if list(entries) != sorted(entries):
        fail("CHECKSUMS.sha256 entries must be in deterministic path order")
    expected_coverage = set(files) - {"CHECKSUMS.sha256"}
    if set(entries) != expected_coverage:
        fail(
            "CHECKSUMS.sha256 coverage is not exact: "
            f"missing={sorted(expected_coverage - set(entries))} "
            f"extra={sorted(set(entries) - expected_coverage)}"
        )
    return entries


def assert_dependency_dag(skills: list[dict[str, Any]]) -> list[str]:
    names = [entry.get("name") for entry in skills]
    if names != list(EXPECTED_SKILLS):
        fail("Skill manifest must preserve the exact ordered 22-Skill inventory")
    identifiers = set(EXPECTED_SKILLS)
    graph: dict[str, list[str]] = {}
    for entry in skills:
        name = entry["name"]
        dependencies = entry.get("depends_on")
        if not isinstance(dependencies, list) or any(
            not isinstance(value, str) for value in dependencies
        ):
            fail(f"Skill dependency list is invalid: {name}")
        if len(dependencies) != len(set(dependencies)):
            fail(f"Skill dependency is duplicated: {name}")
        if name in dependencies:
            fail(f"Skill may not depend on itself: {name}")
        unknown = sorted(set(dependencies) - identifiers)
        if unknown:
            fail(f"Skill has unknown dependencies: {name}: {unknown}")
        graph[name] = dependencies

    visiting: set[str] = set()
    visited: set[str] = set()
    topological: list[str] = []

    def visit(name: str) -> None:
        if name in visiting:
            fail(f"Skill dependency cycle detected at {name}")
        if name in visited:
            return
        visiting.add(name)
        for dependency in graph[name]:
            visit(dependency)
        visiting.remove(name)
        visited.add(name)
        topological.append(name)

    for name in EXPECTED_SKILLS:
        visit(name)
    if len(topological) != len(EXPECTED_SKILLS):
        fail("Skill dependency DAG is incomplete")
    return topological


def _parse_frontmatter(skill_path: Path) -> dict[str, Any]:
    text = skill_path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if match is None:
        fail(f"Skill frontmatter is invalid: {skill_path}")
    try:
        import yaml
    except ModuleNotFoundError as exc:
        fail("PyYAML is required for Skill frontmatter validation")
        raise AssertionError from exc
    try:
        value = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        fail(f"Skill frontmatter is invalid: {skill_path}: {exc}")
    if not isinstance(value, dict):
        fail(f"Skill frontmatter must be an object: {skill_path}")
    return value


def _validate_skill(
    source: Path,
    entry: dict[str, Any],
    files: dict[str, Path],
) -> dict[str, Any]:
    name = entry["name"]
    expected_path = f".agents/skills/{name}"
    if entry.get("path") != expected_path:
        fail(f"Skill path is invalid: {name}")
    if entry.get("entrypoint") != f"{expected_path}/SKILL.md":
        fail(f"Skill entrypoint is invalid: {name}")
    if not isinstance(entry.get("stage"), str) or not entry["stage"]:
        fail(f"Skill stage is invalid: {name}")
    if not isinstance(entry.get("description"), str) or not entry["description"].strip():
        fail(f"Skill description is invalid: {name}")
    task_ids = entry.get("task_ids")
    outputs = entry.get("outputs")
    if not isinstance(task_ids, list) or not task_ids:
        fail(f"Skill task IDs are invalid: {name}")
    if not isinstance(outputs, list) or not outputs or any(
        not isinstance(value, str) or not value for value in outputs
    ):
        fail(f"Skill outputs are invalid: {name}")

    skill_root = source / ".agents" / "skills" / name
    actual_files = {
        path.relative_to(skill_root).as_posix()
        for path in skill_root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    if actual_files != EXPECTED_SKILL_FILES:
        fail(
            f"Skill support-file inventory is invalid: {name}: "
            f"missing={sorted(EXPECTED_SKILL_FILES - actual_files)} "
            f"extra={sorted(actual_files - EXPECTED_SKILL_FILES)}"
        )
    valid, reason = skill_creator_tools.validate_skill(skill_root)
    if not valid:
        fail(f"Skill Creator validation failed for {name}: {reason}")
    skill_path = skill_root / "SKILL.md"
    frontmatter = _parse_frontmatter(skill_path)
    metadata = frontmatter.get("metadata")
    if (
        frontmatter.get("name") != name
        or frontmatter.get("description") != entry["description"]
        or not isinstance(metadata, dict)
        or metadata.get("package") != PACKAGE_ID
        or metadata.get("version") != PACKAGE_VERSION
        or metadata.get("stage") != entry["stage"]
        or metadata.get("task_ids") != task_ids
        or metadata.get("maturity") != "implementation-ready"
    ):
        fail(f"Skill frontmatter/manifest binding is invalid: {name}")

    output_contract_path = skill_root / "assets" / "output-contract.yaml"
    output_contract = _load_yaml(output_contract_path, f"{name} output contract")
    if not isinstance(output_contract, dict):
        fail(f"Skill output contract must be an object: {name}")
    required_outputs = output_contract.get("required_outputs")
    gates = output_contract.get("gates")
    failure_policy = output_contract.get("failure_policy")
    if (
        output_contract.get("skill") != name
        or output_contract.get("version") != PACKAGE_VERSION
        or output_contract.get("task_ids") != task_ids
        or not isinstance(required_outputs, list)
        or [value.get("path") for value in required_outputs if isinstance(value, dict)]
        != outputs
        or any(value.get("required") is not True for value in required_outputs)
        or not isinstance(gates, list)
        or not gates
        or any(
            not isinstance(value, dict)
            or not isinstance(value.get("name"), str)
            or not value["name"]
            or value.get("required") is not True
            for value in gates
        )
        or not isinstance(failure_policy, dict)
        or failure_policy.get("silent_drop") != "deny"
        or not isinstance(failure_policy.get("max_retries"), int)
        or not isinstance(failure_policy.get("escalate_on"), list)
    ):
        fail(f"Skill output contract is invalid: {name}")

    support_records = []
    for relative in sorted(EXPECTED_SKILL_FILES):
        package_relative = f".agents/skills/{name}/{relative}"
        path = files[package_relative]
        support_records.append(
            {
                "path": package_relative,
                "bytes": path.stat().st_size,
                "mode": f"{stat.S_IMODE(path.stat().st_mode):04o}",
                "sha256": digest(path.read_bytes()),
            }
        )
    return {
        "name": name,
        "stage": entry["stage"],
        "description": entry["description"],
        "depends_on": list(entry["depends_on"]),
        "task_ids": list(task_ids),
        "outputs": list(outputs),
        "source_path": f".agents/skills/{name}/SKILL.md",
        "source_sha256": digest(skill_path.read_bytes()),
        "output_contract": output_contract,
        "support_files": support_records,
    }


def _tree_digest_from_records(records: dict[str, ArchiveRecord]) -> str:
    value = hashlib.sha256()
    for relative, record in sorted(records.items()):
        value.update(relative.encode("utf-8"))
        value.update(b"\0")
        value.update(f"{record.mode:04o}".encode("ascii"))
        value.update(b"\0")
        value.update(str(record.size).encode("ascii"))
        value.update(b"\0")
        value.update(bytes.fromhex(record.sha256))
    return "sha256:" + value.hexdigest()


def validate_source(
    source: Path = ROOT / PACKAGE_RELATIVE,
    archive: Path = ROOT / ARCHIVE_RELATIVE,
) -> dict[str, Any]:
    """Validate extracted bytes against the pinned ZIP and package contracts."""

    archive_records = validate_archive(archive)
    files = _source_files(source)
    if len(files) != EXPECTED_SOURCE_FILE_COUNT:
        fail(
            f"extracted package must contain exactly {EXPECTED_SOURCE_FILE_COUNT} files; "
            f"found {len(files)}"
        )
    if set(files) != set(archive_records):
        fail(
            "extracted package inventory differs from the archive: "
            f"missing={sorted(set(archive_records) - set(files))} "
            f"extra={sorted(set(files) - set(archive_records))}"
        )
    for relative, record in archive_records.items():
        path = files[relative]
        actual_mode = stat.S_IMODE(path.stat().st_mode)
        actual_sha256 = sha256_file(path)
        if (
            path.stat().st_size != record.size
            or actual_mode != record.mode
            or actual_sha256 != record.sha256
        ):
            fail(
                f"extracted file differs from pinned archive: {relative}: "
                f"size={path.stat().st_size}/{record.size} "
                f"mode={actual_mode:#o}/{record.mode:#o} "
                f"sha256={actual_sha256}/{record.sha256}"
            )

    checksums = _parse_checksums(source, files)
    manifest = _load_json(source / "skill-manifest.json", "Skill manifest")
    yaml_manifest = _load_yaml(source / "skill-manifest.yaml", "YAML Skill manifest")
    if yaml_manifest != manifest:
        fail("YAML and JSON Skill manifests are not semantically identical")
    package = manifest.get("package") if isinstance(manifest, dict) else None
    if (
        not isinstance(package, dict)
        or manifest.get("schema_version") != "1.0"
        or package.get("id") != PACKAGE_ID
        or package.get("name") != PACKAGE_NAME
        or package.get("version") != PACKAGE_VERSION
        or package.get("canonical_skill_root") != ".agents/skills"
        or package.get("skill_count") != len(EXPECTED_SKILLS)
        or package.get("task_count") != 40
        or package.get("schema_count") != 14
        or tuple(package.get("source_frameworks", [])) != EXPECTED_SOURCE_FRAMEWORKS
        or tuple(package.get("target_platforms", [])) != EXPECTED_TARGET_PLATFORMS
    ):
        fail("source package identity, count, or platform scope is invalid")
    defaults = manifest.get("defaults")
    if (
        not isinstance(defaults, dict)
        or defaults.get("native_output_required") is not True
        or defaults.get("webview_fallback") != "deny"
        or defaults.get("full_page_canvas_fallback") != "deny"
        or defaults.get("silent_feature_drop") != "deny"
        or defaults.get("release_requires_human_approval") is not True
        or defaults.get("credential_policy") != "references-only-no-secret-values"
    ):
        fail("source package safety defaults are invalid")
    skills = manifest.get("skills")
    if not isinstance(skills, list):
        fail("Skill manifest inventory is invalid")
    topological_order = assert_dependency_dag(skills)
    if sum(len(entry["depends_on"]) for entry in skills) != 53:
        fail("Skill dependency edge count must be exactly 53")
    task_ids = [task for entry in skills for task in entry.get("task_ids", [])]
    expected_task_ids = [f"MAPP-{value:03d}" for value in range(1, 41)]
    if task_ids != expected_task_ids:
        fail("Skill task IDs must be exactly MAPP-001 through MAPP-040")

    inventory = _load_json(source / "PACKAGE-INVENTORY.json", "package inventory")
    if (
        not isinstance(inventory, dict)
        or inventory.get("schema_version") != "1.0"
        or inventory.get("package_id") != PACKAGE_ID
        or inventory.get("package_version") != PACKAGE_VERSION
        or inventory.get("canonical_root") != ".agents/skills"
        or inventory.get("counts") != EXPECTED_INVENTORY_COUNTS
        or inventory.get("files") != sorted(checksums)
    ):
        fail("PACKAGE-INVENTORY.json does not exactly own the canonical files")

    schema_validation = _validate_schemas_and_fixtures(source)

    skill_records = [_validate_skill(source, entry, files) for entry in skills]
    return {
        "source": source.resolve(),
        "archive": archive.resolve(),
        "archive_sha256": EXPECTED_ARCHIVE_SHA256,
        "archive_records": archive_records,
        "source_tree_sha256": _tree_digest_from_records(archive_records),
        "checksums": checksums,
        "manifest": manifest,
        "inventory": inventory,
        "skills": skill_records,
        "topological_order": topological_order,
        "dependency_edge_count": 53,
        "schema_validation": schema_validation,
    }


def extract_archive(
    archive: Path = ROOT / ARCHIVE_RELATIVE,
    destination: Path = ROOT / PACKAGE_RELATIVE,
) -> dict[str, Any]:
    """Extract the pinned archive atomically while preserving regular-file modes."""

    records = validate_archive(archive)
    destination_parent = destination.parent
    destination_parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        return validate_source(destination, archive)
    with tempfile.TemporaryDirectory(
        prefix=".frontend-miniapp-extract-", dir=destination_parent
    ) as temporary:
        staging = Path(temporary) / PACKAGE_DIRECTORY
        staging.mkdir()
        try:
            with zipfile.ZipFile(archive) as handle:
                by_name = {info.filename: info for info in handle.infolist()}
                for relative, record in sorted(records.items()):
                    path = staging / PurePosixPath(relative)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with (
                        handle.open(by_name[record.archive_name], "r") as source_handle,
                        path.open("xb") as destination_handle,
                    ):
                        shutil.copyfileobj(source_handle, destination_handle, 64 * 1024)
                    os.chmod(path, record.mode)
        except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
            fail(f"safe archive extraction failed: {exc}")
        summary = validate_source(staging, archive)
        if destination.exists() or destination.is_symlink():
            fail(f"extraction destination appeared concurrently: {destination}")
        os.replace(staging, destination)
    return {**summary, "source": destination.resolve()}


def _render_skill(
    summary: dict[str, Any],
    skill: dict[str, Any],
    runtime_evidence_status: str,
) -> bytes:
    source_path = summary["source"] / skill["source_path"]
    evidence_statement = (
        "The digest-bound repository handler has a verified local qualification "
        "receipt and is `LOCAL_EXECUTED`"
        if runtime_evidence_status == EXECUTED_RUNTIME_EVIDENCE_STATUS
        else "The repository handler bytes are present but no valid local qualification "
        "receipt exists, so runtime evidence is `DECLARED`"
    )
    boundary = "\n".join(
        [
            "",
            "## Repository Integration Boundary",
            "",
            f"- Source identity is pinned to `{PACKAGE_ID}` `{PACKAGE_VERSION}`, Skill `{skill['name']}`, and `{skill['source_sha256']}`.",
            f"- The source label `implementation-ready` describes package intent only. {evidence_statement}; external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.",
            "- Local contracts, parsers, typed IR, planners, four candidate generators, handlers, CLI, checkpoints and fail-closed tests are implemented. They do not prove an official-toolchain build, emulator/device journey, visual or behavior equivalence, upload, review, payment, or release.",
            f"- Runtime dispatch is owned by `{FRONTEND_ENGINE_PATH}`: `{FRONTEND_ENGINE_CLI_COMMAND}` (`{FRONTEND_ENGINE_CLI_ENTRYPOINT}`), structured handler `{FRONTEND_ENGINE_STRUCTURED_HANDLER}`, JSON handler `{FRONTEND_ENGINE_JSON_HANDLER}`, full flow `{FRONTEND_ENGINE_CONVERSION_HANDLER}`, strict package flow `{FRONTEND_ENGINE_PACKAGE_HANDLER}`, and single-Skill handler `{FRONTEND_ENGINE_SINGLE_SKILL_HANDLER}` with Skill key `{skill['name']}`.",
            f"- The canonical snake_case request at `{PACKAGE_RELATIVE.as_posix()}/schemas/conversion-request.schema.json` is callable as `{FRONTEND_ENGINE_CLI_COMMAND} -- package`; handler action `{FRONTEND_ENGINE_PACKAGE_ACTION}` receives `{FRONTEND_ENGINE_PACKAGE_INPUT_FIELD}` and invokes `{FRONTEND_ENGINE_PACKAGE_VALIDATOR}` then `{FRONTEND_ENGINE_PACKAGE_COMPILER}` without disk discovery or package-script execution.",
            f"- Component analysis/emission is an explicit downstream adapter at `{COMPONENT_ADAPTER_PATH}`: `{COMPONENT_ADAPTER_CLI_COMMAND}` (`{COMPONENT_ADAPTER_CLI_ENTRYPOINT}`), `{COMPONENT_ADAPTER_HANDLER}` / `{COMPONENT_ADAPTER_JSON_HANDLER}`, emitter `{COMPONENT_ADAPTER_EMITTER}`.",
            "- Every route remains directional and exact to source framework/runtime/providers and target MiniApp platform/toolchain/API versions. A reverse MiniApp-to-frontend route is separate and is not implied.",
            "- Transform through typed UI Interaction/MiniApp Semantic IR with source traces. Regex, screenshot, WebView, full-page Canvas, silent feature drops, weakened tests, or widened permissions cannot establish equivalence.",
            "- Real source and target builds, browser/emulator/device journeys, negative and independent holdout corpora, accessibility, privacy, permission, visual, business, and rollback evidence remain required.",
            "- Platform credentials are references only. Upload, review, payment, refund, release, and other side effects require separate authorization and auditable idempotency controls.",
            "- Only the conservative Batch 32 client gate may raise readiness; static package validation cannot certify this Skill.",
            "",
        ]
    )
    return (
        source_path.read_text(encoding="utf-8").rstrip() + "\n" + boundary
    ).encode("utf-8")


def _render_interface(name: str, runtime_evidence_status: str) -> bytes:
    display = skill_creator_tools.format_display_name(name).replace("Miniapp", "MiniApp")
    short = "Run this frontend-to-MiniApp Skill with evidence controls"
    prompt = (
        f"Use ${name} with its compiled contract, dispatch Skill key {name} through "
        f"`{FRONTEND_ENGINE_PATH}` via `{FRONTEND_ENGINE_CLI_COMMAND}` / "
        f"`{FRONTEND_ENGINE_SINGLE_SKILL_HANDLER}`. Treat bounded runtime evidence as "
        f"{runtime_evidence_status}, while external evidence stays NOT_RUN and certification "
        "stays NOT_CERTIFIED until exact Batch 32 gates pass."
    )
    return (
        "\n".join(
            [
                "interface:",
                f"  display_name: {skill_creator_tools.yaml_quote(display)}",
                f"  short_description: {skill_creator_tools.yaml_quote(short)}",
                f"  default_prompt: {skill_creator_tools.yaml_quote(prompt)}",
                "",
            ]
        )
    ).encode("utf-8")


def _runtime_binding(name: str) -> dict[str, Any]:
    return {
        "runtime_authority": {
            "package_path": FRONTEND_ENGINE_PATH,
            "cli_command": FRONTEND_ENGINE_CLI_COMMAND,
            "cli_entrypoint": FRONTEND_ENGINE_CLI_ENTRYPOINT,
            "structured_request_handler": FRONTEND_ENGINE_STRUCTURED_HANDLER,
            "json_handler": FRONTEND_ENGINE_JSON_HANDLER,
            "full_conversion_handler": FRONTEND_ENGINE_CONVERSION_HANDLER,
            "package_conversion_handler": FRONTEND_ENGINE_PACKAGE_HANDLER,
            "package_cli_command": f"{FRONTEND_ENGINE_CLI_COMMAND} -- package",
            "single_skill_handler": FRONTEND_ENGINE_SINGLE_SKILL_HANDLER,
            "skill_key": name,
        },
        "canonical_package_request": _package_request_binding(),
        "component_adapter": {
            "package_path": COMPONENT_ADAPTER_PATH,
            "cli_command": COMPONENT_ADAPTER_CLI_COMMAND,
            "cli_entrypoint": COMPONENT_ADAPTER_CLI_ENTRYPOINT,
            "structured_request_handler": COMPONENT_ADAPTER_HANDLER,
            "json_handler": COMPONENT_ADAPTER_JSON_HANDLER,
            "emitter": COMPONENT_ADAPTER_EMITTER,
        },
    }


def _package_request_binding() -> dict[str, Any]:
    return {
        "source_schema": (
            PACKAGE_RELATIVE / "schemas" / "conversion-request.schema.json"
        ).as_posix(),
        "request_case": "snake_case",
        "wrapper_fields": [
            "packageRequest",
            "files",
            "versionBindings",
            "evidenceBindings",
        ],
        "handler_action": FRONTEND_ENGINE_PACKAGE_ACTION,
        "handler_input_field": FRONTEND_ENGINE_PACKAGE_INPUT_FIELD,
        "validator": FRONTEND_ENGINE_PACKAGE_VALIDATOR,
        "compiler": FRONTEND_ENGINE_PACKAGE_COMPILER,
        "runner": FRONTEND_ENGINE_PACKAGE_HANDLER,
        "cli_command": f"{FRONTEND_ENGINE_CLI_COMMAND} -- package",
        "input_boundary": "caller-supplied-in-memory-files-no-disk-discovery",
    }


def _compiled_contract(
    skill: dict[str, Any],
    runtime: dict[str, Any],
    runtime_evidence_status: str,
) -> dict[str, Any]:
    contract = skill["output_contract"]
    return {
        "schema_version": "elmos.frontend-to-miniapp.compiled-skill-contract.v1",
        "package_id": PACKAGE_ID,
        "package_version": PACKAGE_VERSION,
        "source_name": skill["name"],
        "source_path": (PACKAGE_RELATIVE / skill["source_path"]).as_posix(),
        "source_sha256": skill["source_sha256"],
        "stage": skill["stage"],
        "description": skill["description"],
        "depends_on": skill["depends_on"],
        "task_ids": skill["task_ids"],
        "declared_outputs": skill["outputs"],
        "required_outputs": contract["required_outputs"],
        "gates": contract["gates"],
        "failure_policy": contract["failure_policy"],
        "runtime_binding": _runtime_binding(skill["name"]),
        "contract_state": "HANDLER_IMPLEMENTED",
        "runtime_implementation_digest": runtime["implementation_digest"],
        "runtime_evidence_status": runtime_evidence_status,
        "external_evidence_status": EXTERNAL_EVIDENCE_STATUS,
        "certification": CERTIFICATION_STATUS,
        "side_effects_authorized": False,
        "maximum_local_claim": (
            "LOCAL_ENGINEERING_EXECUTED"
            if runtime_evidence_status == EXECUTED_RUNTIME_EVIDENCE_STATUS
            else "HANDLER_IMPLEMENTED_NOT_EXECUTED"
        ),
    }


def _tree_digest(trees: dict[str, dict[str, FilePayload]]) -> str:
    value = hashlib.sha256()
    for name, tree in sorted(trees.items()):
        for relative, payload in sorted(tree.items()):
            value.update(name.encode("utf-8"))
            value.update(b"/")
            value.update(relative.encode("utf-8"))
            value.update(b"\0")
            value.update(f"{payload.mode:04o}".encode("ascii"))
            value.update(b"\0")
            value.update(bytes.fromhex(sha256_bytes(payload.content)))
    return "sha256:" + value.hexdigest()


def _read_tree(root: Path) -> dict[str, FilePayload]:
    if not root.is_dir() or root.is_symlink():
        fail(f"installed Skill is missing or not a real directory: {root}")
    values: dict[str, FilePayload] = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            fail(f"installed Skill may not contain symbolic links: {path}")
        if path.is_file():
            _assert_inside(root, path, "installed Skill file")
            values[path.relative_to(root).as_posix()] = FilePayload(
                path.read_bytes(), stat.S_IMODE(path.stat().st_mode)
            )
        elif not path.is_dir():
            fail(f"unsupported installed Skill entry: {path}")
    return dict(sorted(values.items()))


def _render_readme(runtime_evidence_status: str) -> bytes:
    return f"""# Frontend to MiniApp Skills Integration

This directory records the repository installation of `{PACKAGE_ID}` version `{PACKAGE_VERSION}`.

- Trusted archive: `{ARCHIVE_RELATIVE.as_posix()}` (`sha256:{EXPECTED_ARCHIVE_SHA256}`)
- Canonical extracted source: `{PACKAGE_RELATIVE.as_posix()}/`
- Installed names: 22 exact source names under both `{RUNTIME_RELATIVE.as_posix()}/` and `{WORKSPACE_RELATIVE.as_posix()}/`
- Compiled contract: `compiled-contract.json` in each installed Skill plus this directory's aggregate `compiled-contracts.json`
- Runtime authority: `{FRONTEND_ENGINE_PATH}` — `{FRONTEND_ENGINE_CLI_COMMAND}` (`{FRONTEND_ENGINE_CLI_ENTRYPOINT}`), `{FRONTEND_ENGINE_STRUCTURED_HANDLER}` / `{FRONTEND_ENGINE_JSON_HANDLER}`, full flow `{FRONTEND_ENGINE_CONVERSION_HANDLER}`, strict package flow `{FRONTEND_ENGINE_PACKAGE_HANDLER}`, single-Skill `{FRONTEND_ENGINE_SINGLE_SKILL_HANDLER}`
- Canonical package request entry: source snake_case Schema `{PACKAGE_RELATIVE.as_posix()}/schemas/conversion-request.schema.json`; CLI `{FRONTEND_ENGINE_CLI_COMMAND} -- package`; handler envelope `{{"schemaVersion":"1.0","action":"{FRONTEND_ENGINE_PACKAGE_ACTION}","{FRONTEND_ENGINE_PACKAGE_INPUT_FIELD}":...}}`; validator `{FRONTEND_ENGINE_PACKAGE_VALIDATOR}`; compiler `{FRONTEND_ENGINE_PACKAGE_COMPILER}`
- Component adapter: `{COMPONENT_ADAPTER_PATH}` — `{COMPONENT_ADAPTER_CLI_COMMAND}` (`{COMPONENT_ADAPTER_CLI_ENTRYPOINT}`), `{COMPONENT_ADAPTER_HANDLER}` / `{COMPONENT_ADAPTER_JSON_HANDLER}`, `{COMPONENT_ADAPTER_EMITTER}`
- Current evidence: bounded runtime `{runtime_evidence_status}`, external `NOT_RUN`, certification `NOT_CERTIFIED`
- Digest-bound local evidence projection: `local-runtime-evidence.json`
- Qualification receipt source: `{LOCAL_RECEIPT_RELATIVE.as_posix()}`; it is machine-local, is not committed, and absence keeps the portable repository state `DECLARED`

The importer validates the ZIP before extraction: fixed digest and root, normalized unique paths, regular-file type, exact modes, per-entry and total size limits, compression ratio, CRC/readability, exact file count, and archive-to-source byte binding. It then verifies `CHECKSUMS.sha256`, YAML/JSON manifest parity, package inventory, 22 Skill frontmatters, all 14 Draft 2020-12 Schemas against their exact indexed fixtures (including format checks), 40 task IDs, output contracts, and the 53-edge acyclic dependency graph without executing any source-package script.

`--refresh-owned` only refreshes identity-verified owned trees and never creates execution evidence. Run `--qualify-local` explicitly to execute the fixed trusted repository suite, capture raw logs, dynamically parse test counts, record exact executable paths/versions, OS/architecture, working directories and observed timing, and atomically update the implementation-bound receipt. The two builds execute the canonical frontend/component `node_modules/.bin/tsc` entrypoint inodes and the component tests execute its canonical `node_modules/.bin/jest` entrypoint inode; the receipt binds each invocation path, canonical execution path, version, entrypoint byte count, and SHA-256 digest. These entrypoint digests do not claim a digest of the entire dependency tree. Then run `--refresh-owned` and `--check` to project and verify that receipt in the installed contracts. The receipt and its `LOCAL_EXECUTED` projection are host-specific working-tree evidence: do not commit them. An environment or project-tool byte mismatch remains a hard failure and is never treated as execution success.

Use `--closeout-portable` before a portable release commit. Under the fixed receipt writer lock it validates and atomically moves any host receipt into an owned `0700` system temporary archive, transactionally refreshes every owned tree to `DECLARED`, and runs the installation check. An absent receipt is valid and remains `DECLARED`. On failure it restores the original receipt only when the archived inode still matches and the destination remains absent; it never overwrites a competing object, and reports the archive path for recovery. The canonical `make frontend-to-miniapp-skills` target installs an EXIT/signal closeout handler so success and ordinary command failure both attempt this portable projection; a closeout failure remains a failing result and must be resolved before staging.

These Skills now have callable local handlers for source discovery, typed UI/MiniApp IR, planning, four native candidate generators, checkpoints, bounded repair planning, evidence reporting and a strict CLI. Local execution is not proof of official MiniApp builds, browser/emulator/device journeys, privacy and permission review, accessibility, visual and business equivalence, upload/review/release, independent holdout evidence, or reverse MiniApp-to-frontend routes. Only the conservative Batch 32 gate can raise readiness.

The `package` CLI reads one exact wrapper with `packageRequest`, `files`, `versionBindings`, and `evidenceBindings`; it never reads a source tree from disk or executes package scripts. The equivalent structured handler action is `run-package` with that wrapper in `packageInput`.

Verify the immutable archive, extracted source, compiled contracts, documentation, and byte-identical dual roots with:

```sh
uv run --quiet --with pyyaml==6.0.2 --with jsonschema==4.25.1 python tooling/integrate_frontend_to_miniapp_skills.py --check
```

Run the repository target with:

```sh
make frontend-to-miniapp-skills
```
""".encode()


def build_expected(
    source: Path = ROOT / PACKAGE_RELATIVE,
    archive: Path = ROOT / ARCHIVE_RELATIVE,
    repository_root: Path = ROOT,
) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    summary = validate_source(source, archive)
    runtime = _runtime_implementation(repository_root)
    local_runtime_evidence = _local_runtime_evidence(runtime, repository_root)
    runtime_evidence_status = local_runtime_evidence["state"]
    trees: dict[str, dict[str, FilePayload]] = {}
    contracts: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    for skill in summary["skills"]:
        name = skill["name"]
        compiled = _compiled_contract(skill, runtime, runtime_evidence_status)
        compiled_bytes = (json.dumps(compiled, ensure_ascii=False, indent=2) + "\n").encode(
            "utf-8"
        )
        source_root = summary["source"] / ".agents" / "skills" / name
        tree = {
            "SKILL.md": FilePayload(
                _render_skill(summary, skill, runtime_evidence_status)
            ),
            "agents/openai.yaml": FilePayload(
                _render_interface(name, runtime_evidence_status)
            ),
            "compiled-contract.json": FilePayload(compiled_bytes),
        }
        for relative in sorted(EXPECTED_SKILL_FILES - {"SKILL.md"}):
            path = source_root / PurePosixPath(relative)
            tree[relative] = FilePayload(
                path.read_bytes(), stat.S_IMODE(path.stat().st_mode)
            )
        trees[name] = dict(sorted(tree.items()))
        contracts.append(compiled)
        records.append(
            {
                "source_name": name,
                "stage": skill["stage"],
                "source_path": (PACKAGE_RELATIVE / skill["source_path"]).as_posix(),
                "source_sha256": skill["source_sha256"],
                "depends_on": skill["depends_on"],
                "task_ids": skill["task_ids"],
                "runtime_skill_path": (RUNTIME_RELATIVE / name / "SKILL.md").as_posix(),
                "workspace_skill_path": (WORKSPACE_RELATIVE / name / "SKILL.md").as_posix(),
                "compiled_contract_path": (
                    RUNTIME_RELATIVE / name / "compiled-contract.json"
                ).as_posix(),
                "installed_skill_sha256": digest(tree["SKILL.md"].content),
                "interface_sha256": digest(tree["agents/openai.yaml"].content),
                "compiled_contract_sha256": digest(compiled_bytes),
                "installed_tree_sha256": _tree_digest({name: tree}),
                "contract_state": "HANDLER_IMPLEMENTED",
                "runtime_implementation_digest": runtime["implementation_digest"],
                "runtime_evidence_status": runtime_evidence_status,
                "external_evidence_status": EXTERNAL_EVIDENCE_STATUS,
                "certification": CERTIFICATION_STATUS,
            }
        )

    aggregate_contracts = {
        "schema_version": "elmos.frontend-to-miniapp.compiled-contracts.v1",
        "package_id": PACKAGE_ID,
        "package_version": PACKAGE_VERSION,
        "source_archive_sha256": "sha256:" + EXPECTED_ARCHIVE_SHA256,
        "skill_count": len(EXPECTED_SKILLS),
        "dependency_edge_count": summary["dependency_edge_count"],
        "topological_order": summary["topological_order"],
        "runtime_binding": {
            "runtime_authority": {
                "package_path": FRONTEND_ENGINE_PATH,
                "cli_command": FRONTEND_ENGINE_CLI_COMMAND,
                "cli_entrypoint": FRONTEND_ENGINE_CLI_ENTRYPOINT,
                "structured_request_handler": FRONTEND_ENGINE_STRUCTURED_HANDLER,
                "json_handler": FRONTEND_ENGINE_JSON_HANDLER,
                "full_conversion_handler": FRONTEND_ENGINE_CONVERSION_HANDLER,
                "package_conversion_handler": FRONTEND_ENGINE_PACKAGE_HANDLER,
                "package_cli_command": f"{FRONTEND_ENGINE_CLI_COMMAND} -- package",
                "single_skill_handler": FRONTEND_ENGINE_SINGLE_SKILL_HANDLER,
            },
            "canonical_package_request": _package_request_binding(),
            "component_adapter": _runtime_binding(EXPECTED_SKILLS[0])["component_adapter"],
        },
        "runtime_implementation": runtime,
        "local_runtime_evidence_path": (
            DOC_RELATIVE / "local-runtime-evidence.json"
        ).as_posix(),
        "local_runtime_receipt_path": LOCAL_RECEIPT_RELATIVE.as_posix(),
        "local_runtime_receipt_state": local_runtime_evidence["receipt"]["state"],
        "runtime_evidence_status": runtime_evidence_status,
        "external_evidence_status": EXTERNAL_EVIDENCE_STATUS,
        "certification": CERTIFICATION_STATUS,
        "contracts": contracts,
    }
    compiled_contracts_bytes = (
        json.dumps(aggregate_contracts, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    local_runtime_evidence_bytes = (
        json.dumps(local_runtime_evidence, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    readme_bytes = _render_readme(runtime_evidence_status)
    tree_sha256 = _tree_digest(trees)
    source_inventory = [
        {
            "path": (PACKAGE_RELATIVE / relative).as_posix(),
            "bytes": record.size,
            "mode": f"{record.mode:04o}",
            "sha256": "sha256:" + record.sha256,
        }
        for relative, record in summary["archive_records"].items()
    ]
    install_manifest = {
        "schema_version": "elmos.frontend-to-miniapp.installed-manifest.v1",
        "namespace": NAMESPACE,
        "source_package_id": PACKAGE_ID,
        "source_package_name": PACKAGE_NAME,
        "source_package_version": PACKAGE_VERSION,
        "source_archive_path": ARCHIVE_RELATIVE.as_posix(),
        "source_archive_bytes": summary["archive"].stat().st_size,
        "source_archive_sha256": "sha256:" + EXPECTED_ARCHIVE_SHA256,
        "canonical_source_path": PACKAGE_RELATIVE.as_posix(),
        "source_file_count": EXPECTED_SOURCE_FILE_COUNT,
        "source_checksum_entry_count": EXPECTED_CHECKSUM_ENTRY_COUNT,
        "source_checksums_sha256": "sha256:" + EXPECTED_CHECKSUMS_SHA256,
        "source_tree_sha256": summary["source_tree_sha256"],
        "source_files": source_inventory,
        "skill_count": len(EXPECTED_SKILLS),
        "task_count": 40,
        "schema_count": 14,
        "dependency_edge_count": summary["dependency_edge_count"],
        "dependency_dag_valid": True,
        "topological_order": summary["topological_order"],
        "source_frameworks": list(EXPECTED_SOURCE_FRAMEWORKS),
        "target_platforms": list(EXPECTED_TARGET_PLATFORMS),
        "reverse_routes_implied": False,
        "runtime_binding": aggregate_contracts["runtime_binding"],
        "runtime_root": RUNTIME_RELATIVE.as_posix(),
        "workspace_root": WORKSPACE_RELATIVE.as_posix(),
        "runtime_tree_sha256": tree_sha256,
        "workspace_tree_sha256": tree_sha256,
        "dual_root_byte_identical": True,
        "compiled_contracts_path": (DOC_RELATIVE / "compiled-contracts.json").as_posix(),
        "compiled_contracts_sha256": digest(compiled_contracts_bytes),
        "local_runtime_evidence_path": (
            DOC_RELATIVE / "local-runtime-evidence.json"
        ).as_posix(),
        "local_runtime_evidence_sha256": digest(local_runtime_evidence_bytes),
        "local_runtime_receipt_path": LOCAL_RECEIPT_RELATIVE.as_posix(),
        "local_runtime_receipt_state": local_runtime_evidence["receipt"]["state"],
        "integration_readme_path": (DOC_RELATIVE / "README.md").as_posix(),
        "integration_readme_sha256": digest(readme_bytes),
        "source_maturity_label": "implementation-ready (source package intent only)",
        "contract_state": "HANDLER_IMPLEMENTED",
        "runtime_implementation": runtime,
        "runtime_evidence_status": runtime_evidence_status,
        "external_evidence_status": EXTERNAL_EVIDENCE_STATUS,
        "certification": CERTIFICATION_STATUS,
        "maximum_local_claim": (
            "LOCAL_ENGINEERING_EXECUTED"
            if runtime_evidence_status == EXECUTED_RUNTIME_EVIDENCE_STATUS
            else "HANDLER_IMPLEMENTED_NOT_EXECUTED"
        ),
        "skills": records,
    }
    manifest_bytes = (
        json.dumps(install_manifest, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    docs = {
        "README.md": FilePayload(readme_bytes),
        "compiled-contracts.json": FilePayload(compiled_contracts_bytes),
        "installed-manifest.json": FilePayload(manifest_bytes),
        "local-runtime-evidence.json": FilePayload(local_runtime_evidence_bytes),
    }
    return {
        "summary": summary,
        "trees": trees,
        "docs": docs,
        "manifest": install_manifest,
        "manifest_bytes": manifest_bytes,
        "compiled_contracts": aggregate_contracts,
    }


def _compare_tree(
    label: str, actual: dict[str, FilePayload], expected: dict[str, FilePayload]
) -> list[str]:
    if actual == expected:
        return []
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    changed = sorted(
        path for path in set(actual) & set(expected) if actual[path] != expected[path]
    )
    return [f"{label}:missing={missing}:extra={extra}:changed={changed}"]


def check_install(
    repository_root: Path = ROOT,
    source: Path | None = None,
    archive: Path | None = None,
) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    source = source or repository_root / PACKAGE_RELATIVE
    archive = archive or repository_root / ARCHIVE_RELATIVE
    expected = build_expected(source, archive, repository_root)
    failures: list[str] = []
    for relative_root, label in (
        (RUNTIME_RELATIVE, "runtime"),
        (WORKSPACE_RELATIVE, "workspace"),
    ):
        root = repository_root / relative_root
        for name, tree in expected["trees"].items():
            destination = root / name
            try:
                actual = _read_tree(destination)
            except IntegrationError as exc:
                failures.append(f"{label}:{name}:{exc}")
                continue
            failures.extend(_compare_tree(f"{label}:{name}", actual, tree))
    doc_root = repository_root / DOC_RELATIVE
    try:
        actual_docs = _read_tree(doc_root)
    except IntegrationError as exc:
        failures.append(f"docs:{exc}")
    else:
        failures.extend(_compare_tree("docs", actual_docs, expected["docs"]))
    if failures:
        fail(
            f"frontend-to-MiniApp installation drifted: {failures[:12]} "
            f"({len(failures)} total)"
        )
    return expected


def _populate_tree_at_directory_descriptor(
    root_descriptor: int,
    tree: dict[str, FilePayload],
) -> None:
    for relative, payload in sorted(tree.items()):
        relative_path = _validate_relative_path(relative, "installed")
        current_descriptor = root_descriptor
        opened_directories: list[int] = []
        try:
            for component in relative_path.parts[:-1]:
                try:
                    os.mkdir(component, 0o755, dir_fd=current_descriptor)
                except FileExistsError:
                    pass
                child_descriptor = os.open(
                    component,
                    os.O_RDONLY
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_CLOEXEC", 0),
                    dir_fd=current_descriptor,
                )
                opened = os.fstat(child_descriptor)
                current = os.stat(
                    component,
                    dir_fd=current_descriptor,
                    follow_symlinks=False,
                )
                if (
                    not stat.S_ISDIR(opened.st_mode)
                    or not stat.S_ISDIR(current.st_mode)
                    or _directory_identity_from_stat(opened)
                    != _directory_identity_from_stat(current)
                ):
                    os.close(child_descriptor)
                    fail(f"installed directory component is unsafe: {relative}")
                opened_directories.append(child_descriptor)
                current_descriptor = child_descriptor
            descriptor = os.open(
                relative_path.parts[-1],
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                payload.mode,
                dir_fd=current_descriptor,
            )
            try:
                offset = 0
                while offset < len(payload.content):
                    written = os.write(descriptor, payload.content[offset:])
                    if written <= 0:
                        fail(f"installed file write made no progress: {relative}")
                    offset += written
                os.fchmod(descriptor, payload.mode)
            finally:
                os.close(descriptor)
        except OSError as exc:
            fail(f"failed to populate reserved installation path {relative}: {exc}")
        finally:
            for descriptor in reversed(opened_directories):
                os.close(descriptor)


def _write_tree(
    destination: Path,
    tree: dict[str, FilePayload],
    *,
    before_reserve: Callable[[Path], None] | None = None,
    containment_root: Path | None = None,
) -> None:
    if destination.exists() or destination.is_symlink():
        fail(f"refusing to overwrite existing destination: {destination}")
    if containment_root is None:
        destination.parent.mkdir(parents=True, exist_ok=True)
    else:
        containment_root = containment_root.resolve()
        try:
            parent_relative = destination.parent.relative_to(containment_root)
        except ValueError:
            fail(f"installation destination parent escapes repository: {destination.parent}")
        installed_parent = _ensure_relative_directory(
            containment_root,
            parent_relative,
            "installation destination parent",
        )
        if installed_parent != destination.parent:
            fail(f"installation destination parent path drifted: {destination.parent}")
    with tempfile.TemporaryDirectory(
        prefix=f".{destination.name}-install-", dir=destination.parent
    ) as temporary:
        staging = Path(temporary) / destination.name
        staging.mkdir()
        for relative, payload in sorted(tree.items()):
            _validate_relative_path(relative, "installed")
            path = staging / PurePosixPath(relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload.content)
            os.chmod(path, payload.mode)
        if _read_tree(staging) != tree:
            fail(f"staged installation differs before rename: {destination}")
        if before_reserve is not None:
            before_reserve(destination)
        try:
            os.mkdir(destination, 0o755)
        except FileExistsError:
            fail(f"installation destination appeared concurrently: {destination}")
        reserved_identity = _directory_identity(
            destination,
            "reserved installation destination",
        )
        descriptor: int | None = None
        try:
            descriptor, opened_identity = _open_verified_directory(
                destination,
                "reserved installation destination",
            )
            if opened_identity != reserved_identity:
                fail(f"reserved installation destination identity drifted: {destination}")
            _populate_tree_at_directory_descriptor(descriptor, tree)
            _assert_directory_path_identity(
                destination,
                reserved_identity,
                "reserved installation destination after population",
            )
            if _read_tree(destination) != tree:
                fail(f"reserved installation differs after population: {destination}")
        except BaseException:
            try:
                current_identity = _directory_identity(
                    destination,
                    "failed reserved installation destination",
                )
                actual = _read_tree(destination)
                safely_owned_subset = (
                    current_identity == reserved_identity
                    and set(actual).issubset(tree)
                    and all(actual[path] == tree[path] for path in actual)
                )
                if safely_owned_subset:
                    failed = Path(temporary) / "failed-reservation"
                    os.replace(destination, failed)
                    if _directory_identity(
                        failed,
                        "failed reserved installation quarantine",
                    ) != reserved_identity:
                        fail(
                            "failed reserved installation moved a different directory: "
                            f"{destination}"
                        )
            except IntegrationError:
                pass
            raise
        finally:
            if descriptor is not None:
                os.close(descriptor)


def _assert_refreshable_owned_tree(
    destination: Path,
    name: str,
    source_sha256: str,
    expected_tree: dict[str, FilePayload],
) -> dict[str, FilePayload]:
    tree = _read_tree(destination)
    if set(tree) != set(expected_tree):
        fail(
            f"refusing to refresh an owned Skill with path drift: {destination}: "
            f"missing={sorted(set(expected_tree) - set(tree))} "
            f"extra={sorted(set(tree) - set(expected_tree))}"
        )
    compiled_payload = tree.get("compiled-contract.json")
    skill_payload = tree.get("SKILL.md")
    if compiled_payload is None or skill_payload is None:
        fail(f"refusing to refresh incomplete owned Skill: {destination}")
    try:
        compiled = json.loads(compiled_payload.content.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        fail(f"refusing to refresh invalid compiled contract: {destination}: {exc}")
    if (
        compiled.get("package_id") != PACKAGE_ID
        or compiled.get("package_version") != PACKAGE_VERSION
        or compiled.get("source_name") != name
        or compiled.get("source_sha256") != source_sha256
        or b"## Repository Integration Boundary" not in skill_payload.content
        or source_sha256.encode("ascii") not in skill_payload.content
    ):
        fail(f"refusing to refresh unowned or identity-drifted Skill: {destination}")
    for relative in EXPECTED_SKILL_FILES - {"SKILL.md"}:
        if tree.get(relative) != expected_tree.get(relative):
            fail(
                "refusing to refresh an owned Skill with immutable support-file "
                f"drift: {destination}: {relative}"
            )
    return tree


def _assert_prior_install_manifest_bindings(
    repository_root: Path,
    old_manifest: dict[str, Any],
    runtime_trees: dict[str, dict[str, FilePayload]],
    workspace_trees: dict[str, dict[str, FilePayload]],
    docs: dict[str, FilePayload],
) -> None:
    """Bind refresh ownership to the prior manifest's actual installed bytes."""

    if (
        old_manifest.get("schema_version")
        != "elmos.frontend-to-miniapp.installed-manifest.v1"
        or old_manifest.get("namespace") != NAMESPACE
        or old_manifest.get("source_package_id") != PACKAGE_ID
        or old_manifest.get("source_package_version") != PACKAGE_VERSION
        or old_manifest.get("source_archive_path") != ARCHIVE_RELATIVE.as_posix()
        or old_manifest.get("source_archive_sha256")
        != "sha256:" + EXPECTED_ARCHIVE_SHA256
        or old_manifest.get("canonical_source_path") != PACKAGE_RELATIVE.as_posix()
        or old_manifest.get("runtime_root") != RUNTIME_RELATIVE.as_posix()
        or old_manifest.get("workspace_root") != WORKSPACE_RELATIVE.as_posix()
        or old_manifest.get("skill_count") != len(EXPECTED_SKILLS)
        or old_manifest.get("dependency_edge_count") != 53
        or old_manifest.get("topological_order") != list(EXPECTED_SKILLS)
        or old_manifest.get("dual_root_byte_identical") is not True
    ):
        fail("refusing to refresh unowned or identity-drifted documentation")

    runtime_digest = _tree_digest(runtime_trees)
    workspace_digest = _tree_digest(workspace_trees)
    if (
        old_manifest.get("runtime_tree_sha256") != runtime_digest
        or old_manifest.get("workspace_tree_sha256") != workspace_digest
        or runtime_digest != workspace_digest
    ):
        fail("refusing to refresh because prior installed tree digests drifted")

    records = old_manifest.get("skills")
    if not isinstance(records, list) or [
        record.get("source_name") if isinstance(record, dict) else None
        for record in records
    ] != list(EXPECTED_SKILLS):
        fail("refusing to refresh because prior Skill ownership inventory drifted")
    for record in records:
        name = record["source_name"]
        tree = runtime_trees[name]
        expected_paths = {
            "runtime_skill_path": (RUNTIME_RELATIVE / name / "SKILL.md").as_posix(),
            "workspace_skill_path": (WORKSPACE_RELATIVE / name / "SKILL.md").as_posix(),
            "compiled_contract_path": (
                RUNTIME_RELATIVE / name / "compiled-contract.json"
            ).as_posix(),
        }
        if (
            any(record.get(key) != value for key, value in expected_paths.items())
            or record.get("installed_tree_sha256") != _tree_digest({name: tree})
            or record.get("installed_skill_sha256")
            != digest(tree["SKILL.md"].content)
            or record.get("interface_sha256")
            != digest(tree["agents/openai.yaml"].content)
            or record.get("compiled_contract_sha256")
            != digest(tree["compiled-contract.json"].content)
        ):
            fail(f"refusing to refresh because prior Skill bytes drifted: {name}")

    doc_bindings = {
        "compiled_contracts_sha256": "compiled-contracts.json",
        "local_runtime_evidence_sha256": "local-runtime-evidence.json",
        "integration_readme_sha256": "README.md",
    }
    for manifest_key, relative in doc_bindings.items():
        payload = docs.get(relative)
        if payload is None or old_manifest.get(manifest_key) != digest(payload.content):
            fail(
                "refusing to refresh because prior documentation bytes drifted: "
                f"{relative}"
            )
    aggregate_payload = docs.get("compiled-contracts.json")
    if aggregate_payload is None:
        fail("refusing to refresh without prior compiled contracts")
    try:
        aggregate = json.loads(aggregate_payload.content.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        fail(f"refusing to refresh invalid prior compiled contracts: {exc}")
    if (
        not isinstance(aggregate, dict)
        or aggregate.get("schema_version")
        != "elmos.frontend-to-miniapp.compiled-contracts.v1"
        or aggregate.get("package_id") != PACKAGE_ID
        or aggregate.get("package_version") != PACKAGE_VERSION
        or aggregate.get("source_archive_sha256")
        != "sha256:" + EXPECTED_ARCHIVE_SHA256
        or aggregate.get("skill_count") != len(EXPECTED_SKILLS)
        or aggregate.get("dependency_edge_count") != 53
        or aggregate.get("topological_order") != list(EXPECTED_SKILLS)
        or not isinstance(aggregate.get("contracts"), list)
        or len(aggregate["contracts"]) != len(EXPECTED_SKILLS)
    ):
        fail("refusing to refresh identity-drifted prior compiled contracts")

    for path in (
        repository_root / RUNTIME_RELATIVE,
        repository_root / WORKSPACE_RELATIVE,
        repository_root / DOC_RELATIVE,
    ):
        _assert_inside(repository_root, path, "prior installed root")


def _stage_refresh_tree(
    staging: Path,
    destination: Path,
    tree: dict[str, FilePayload],
) -> None:
    staging.mkdir()
    for relative, payload in sorted(tree.items()):
        _validate_relative_path(relative, "refreshed installed")
        path = staging / PurePosixPath(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload.content)
        os.chmod(path, payload.mode)
    if _read_tree(staging) != tree:
        fail(f"refreshed staging tree differs before transactional commit: {destination}")


def _transactionally_replace_owned_trees(
    repository_root: Path,
    destinations: list[
        tuple[
            Path,
            dict[str, FilePayload],
            dict[str, FilePayload],
            DirectoryIdentity,
        ]
    ],
    verify: Callable[[], dict[str, Any]],
    failure_injector: Callable[[str, int, Path], None] | None = None,
) -> dict[str, Any]:
    """Stage every tree, retain every backup, and rollback the whole set on error."""

    with tempfile.TemporaryDirectory(
        prefix=".frontend-miniapp-refresh-transaction-",
        dir=repository_root,
    ) as temporary:
        transaction_root = Path(temporary)
        staging_root = transaction_root / "staging"
        backup_root = transaction_root / "backup"
        discarded_root = transaction_root / "discarded"
        staging_root.mkdir()
        backup_root.mkdir()
        discarded_root.mkdir()
        staged_identities: dict[int, DirectoryIdentity] = {}
        for index, (destination, tree, _old_tree, _old_identity) in enumerate(destinations):
            staged = staging_root / f"{index:03d}"
            _stage_refresh_tree(staged, destination, tree)
            staged_identities[index] = _directory_identity(
                staged,
                "owned refresh staging tree",
            )
            if failure_injector is not None:
                failure_injector("after_stage", index, destination)

        committed: list[OwnedTreeCommit] = []
        try:
            for index, (destination, tree, old_tree, old_identity) in enumerate(destinations):
                if (
                    _directory_identity(
                        destination,
                        "owned refresh destination before commit",
                    )
                    != old_identity
                    or _read_tree(destination) != old_tree
                    or _directory_identity(
                        destination,
                        "owned refresh destination after precommit read",
                    )
                    != old_identity
                ):
                    fail(
                        "owned refresh destination identity changed after preflight and before "
                        f"commit: {destination}"
                    )
                backup = backup_root / f"{index:03d}"
                os.replace(destination, backup)
                commit = OwnedTreeCommit(
                    index=index,
                    destination=destination,
                    backup=backup,
                    old_tree=old_tree,
                    new_tree=tree,
                    old_identity=old_identity,
                )
                committed.append(commit)
                if (
                    _directory_identity(backup, "owned refresh backup after move")
                    != old_identity
                    or _read_tree(backup) != old_tree
                    or _directory_identity(backup, "owned refresh backup after read")
                    != old_identity
                ):
                    fail(f"owned refresh backup identity drifted during commit: {destination}")
                if failure_injector is not None:
                    failure_injector("after_backup", index, destination)
                staged = staging_root / f"{index:03d}"
                os.replace(staged, destination)
                commit.published_identity = staged_identities[index]
                if (
                    _directory_identity(
                        destination,
                        "owned refresh published destination",
                    )
                    != commit.published_identity
                    or _read_tree(destination) != tree
                    or _directory_identity(
                        destination,
                        "owned refresh published destination after read",
                    )
                    != commit.published_identity
                ):
                    fail(f"owned refresh published a different tree: {destination}")
                if failure_injector is not None:
                    failure_injector("after_commit", index, destination)
            if failure_injector is not None:
                failure_injector("before_verify", len(destinations), repository_root)
            result = verify()
        except BaseException as exc:
            rollback_failures: list[str] = []
            recovery_root: Path | None = None
            for commit in reversed(committed):
                index = commit.index
                destination = commit.destination
                backup = commit.backup
                try:
                    if destination.exists() or destination.is_symlink():
                        if commit.published_identity is None:
                            raise IntegrationError(
                                f"competing destination appeared before publish: {destination}"
                            )
                        if (
                            _directory_identity(
                                destination,
                                "owned refresh rollback destination",
                            )
                            != commit.published_identity
                            or _read_tree(destination) != commit.new_tree
                        ):
                            raise IntegrationError(
                                f"published destination was replaced before rollback: {destination}"
                            )
                        os.replace(destination, discarded_root / f"{index:03d}")
                        if (
                            _directory_identity(
                                discarded_root / f"{index:03d}",
                                "owned refresh discarded published tree",
                            )
                            != commit.published_identity
                        ):
                            raise IntegrationError(
                                f"rollback discarded a different destination: {destination}"
                            )
                    if not backup.exists() or backup.is_symlink() or (
                        _directory_identity(backup, "owned refresh rollback backup")
                        != commit.old_identity
                    ) or _read_tree(backup) != commit.old_tree:
                        raise IntegrationError(
                            f"transaction backup disappeared or drifted for {destination}"
                        )
                    os.replace(backup, destination)
                    if (
                        _directory_identity(
                            destination,
                            "owned refresh restored destination",
                        )
                        != commit.old_identity
                        or _read_tree(destination) != commit.old_tree
                    ):
                        raise IntegrationError(
                            f"transaction restored a different tree for {destination}"
                        )
                except (OSError, IntegrationError) as rollback_exc:
                    rollback_failures.append(f"{destination}: {rollback_exc}")
            if rollback_failures:
                remaining_backups = [
                    commit.backup
                    for commit in committed
                    if commit.backup.exists() or commit.backup.is_symlink()
                ]
                if remaining_backups:
                    recovery_root = Path(
                        tempfile.mkdtemp(
                            prefix=".frontend-miniapp-refresh-recovery-",
                            dir=repository_root,
                        )
                    )
                    for commit in committed:
                        if commit.backup.exists() or commit.backup.is_symlink():
                            os.replace(
                                commit.backup,
                                recovery_root / f"{commit.index:03d}-backup",
                            )
                    rollback_failures.append(
                        f"unrestored backups preserved at {recovery_root}"
                    )
            for commit in committed:
                try:
                    if (
                        _directory_identity(
                            commit.destination,
                            "owned refresh rollback verification",
                        )
                        != commit.old_identity
                        or _read_tree(commit.destination) != commit.old_tree
                    ):
                        rollback_failures.append(
                            f"{commit.destination}: restored bytes or identity differ from preflight"
                        )
                except IntegrationError as rollback_exc:
                    rollback_failures.append(f"{commit.destination}: {rollback_exc}")
            if rollback_failures:
                raise IntegrationError(
                    "transactional refresh failed and rollback was incomplete: "
                    f"original={exc}; rollback={rollback_failures}"
                ) from exc
            raise
    return result


def refresh_owned_install(
    repository_root: Path = ROOT,
    source: Path | None = None,
    archive: Path | None = None,
    *,
    failure_injector: Callable[[str, int, Path], None] | None = None,
    final_verifier: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Transactionally refresh an identity-verified prior installation."""

    repository_root = repository_root.resolve()
    source = source or repository_root / PACKAGE_RELATIVE
    archive = archive or repository_root / ARCHIVE_RELATIVE
    expected = build_expected(source, archive, repository_root)
    skill_by_name = {
        record["source_name"]: record for record in expected["manifest"]["skills"]
    }
    destinations: list[
        tuple[
            Path,
            dict[str, FilePayload],
            dict[str, FilePayload],
            DirectoryIdentity,
        ]
    ] = []
    for relative_root in (RUNTIME_RELATIVE, WORKSPACE_RELATIVE):
        for name, tree in expected["trees"].items():
            destination = repository_root / relative_root / name
            old_identity = _directory_identity(
                destination,
                "owned Skill before refresh preflight",
            )
            old_tree = _assert_refreshable_owned_tree(
                destination,
                name,
                skill_by_name[name]["source_sha256"],
                tree,
            )
            if _directory_identity(
                destination,
                "owned Skill after refresh preflight",
            ) != old_identity:
                fail(f"owned Skill identity changed during refresh preflight: {destination}")
            destinations.append((destination, tree, old_tree, old_identity))
    runtime_trees = {
        name: _read_tree(repository_root / RUNTIME_RELATIVE / name)
        for name in EXPECTED_SKILLS
    }
    workspace_trees = {
        name: _read_tree(repository_root / WORKSPACE_RELATIVE / name)
        for name in EXPECTED_SKILLS
    }
    if runtime_trees != workspace_trees:
        fail("refusing to refresh because the two installed roots already drifted")
    docs_destination = repository_root / DOC_RELATIVE
    docs_identity = _directory_identity(
        docs_destination,
        "owned documentation before refresh preflight",
    )
    docs = _read_tree(docs_destination)
    if _directory_identity(
        docs_destination,
        "owned documentation after refresh preflight",
    ) != docs_identity:
        fail("owned documentation identity changed during refresh preflight")
    if set(docs) != set(expected["docs"]):
        fail(
            "refusing to refresh documentation with path drift: "
            f"missing={sorted(set(expected['docs']) - set(docs))} "
            f"extra={sorted(set(docs) - set(expected['docs']))}"
        )
    manifest_payload = docs.get("installed-manifest.json")
    if manifest_payload is None:
        fail("refusing to refresh documentation without an installed manifest")
    try:
        old_manifest = json.loads(manifest_payload.content.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        fail(f"refusing to refresh invalid installed manifest: {exc}")
    _assert_prior_install_manifest_bindings(
        repository_root,
        old_manifest,
        runtime_trees,
        workspace_trees,
        docs,
    )
    destinations.append(
        (docs_destination, expected["docs"], docs, docs_identity)
    )
    def verify_refreshed_install() -> dict[str, Any]:
        result = check_install(repository_root, source, archive)
        if final_verifier is not None:
            final_verifier(result)
        return result

    return _transactionally_replace_owned_trees(
        repository_root,
        destinations,
        verify_refreshed_install,
        failure_injector,
    )


def closeout_portable(
    repository_root: Path = ROOT,
    source: Path | None = None,
    archive: Path | None = None,
    *,
    failure_injector: Callable[[str, int, Path], None] | None = None,
) -> dict[str, Any]:
    """Archive host evidence and transactionally project a portable DECLARED tree."""

    repository_root = repository_root.resolve()
    source = source or repository_root / PACKAGE_RELATIVE
    archive = archive or repository_root / ARCHIVE_RELATIVE
    destination = repository_root / LOCAL_RECEIPT_ROOT_RELATIVE
    receipt_parent = _ensure_relative_directory(
        repository_root,
        LOCAL_RECEIPT_ROOT_RELATIVE.parent,
        "portable closeout receipt parent",
    )
    if receipt_parent != destination.parent:
        fail("portable closeout receipt parent path drifted")

    with _reserve_local_receipt_bundle(destination, repository_root) as reservation:
        reservation.assert_current("portable closeout acquisition")
        original_receipt_identity = _assert_replaceable_receipt_bundle(destination)
        archived_name = LOCAL_RECEIPT_ROOT_RELATIVE.name
        archive_root: Path | None = None
        archived_path: Path | None = None
        archive_descriptor: int | None = None
        receipt_archived = False
        try:
            if original_receipt_identity is not None:
                archive_root = Path(
                    tempfile.mkdtemp(
                        prefix="elmos-frontend-miniapp-portable-closeout-"
                    )
                ).resolve(strict=True)
                try:
                    archive_root.relative_to(repository_root)
                except ValueError:
                    pass
                else:
                    os.rmdir(archive_root)
                    fail(
                        "portable closeout system archive must remain outside the "
                        f"repository: {archive_root}"
                    )
                os.chmod(archive_root, 0o700)
                archive_descriptor, archive_identity = _open_verified_directory(
                    archive_root,
                    "portable closeout system archive",
                )
                archive_stat = os.fstat(archive_descriptor)
                if (
                    stat.S_IMODE(archive_stat.st_mode) != 0o700
                    or archive_stat.st_uid != os.getuid()
                ):
                    fail(
                        "portable closeout system archive is not an owned 0700 directory: "
                        f"{archive_root}"
                    )
                archived_path = archive_root / archived_name
                if archive_identity.device != reservation.parent_identity.device:
                    fail(
                        "portable closeout system archive is on a different device; "
                        f"atomic receipt move is unavailable: {archive_root}"
                    )
                receipt_entry = _entry_stat_at(
                    reservation.parent_descriptor,
                    destination.name,
                )
                if (
                    receipt_entry is None
                    or not stat.S_ISDIR(receipt_entry.st_mode)
                    or receipt_entry.st_dev != original_receipt_identity[0]
                    or receipt_entry.st_ino != original_receipt_identity[1]
                ):
                    fail("portable closeout receipt identity drifted before archive")
                reservation.assert_current("immediately before portable receipt archive")
                os.replace(
                    destination.name,
                    archived_name,
                    src_dir_fd=reservation.parent_descriptor,
                    dst_dir_fd=archive_descriptor,
                )
                receipt_archived = True
                if (
                    _directory_identity(
                        archived_path,
                        "portable closeout archived receipt",
                    )
                    != DirectoryIdentity(
                        original_receipt_identity[0],
                        original_receipt_identity[1],
                    )
                    or _assert_replaceable_receipt_bundle(archived_path)
                    != original_receipt_identity
                ):
                    fail("portable closeout archived a different receipt identity")
                reservation.assert_current("after portable receipt archive")
            elif _entry_stat_at(
                reservation.parent_descriptor,
                destination.name,
            ) is not None:
                fail("portable closeout receipt appeared after absent preflight")

            def verify_portable_closeout(result: dict[str, Any]) -> None:
                if (
                    result.get("manifest", {}).get("runtime_evidence_status")
                    != DECLARED_RUNTIME_EVIDENCE_STATUS
                ):
                    fail("portable closeout did not produce DECLARED installed state")
                if _entry_stat_at(
                    reservation.parent_descriptor,
                    destination.name,
                ) is not None:
                    fail("portable closeout receipt destination is no longer absent")
                if receipt_archived:
                    assert archived_path is not None
                    if (
                        _assert_replaceable_receipt_bundle(archived_path)
                        != original_receipt_identity
                    ):
                        fail("portable closeout archived receipt drifted after refresh")
                reservation.assert_current("portable closeout transactional verification")

            refreshed = refresh_owned_install(
                repository_root,
                source,
                archive,
                failure_injector=failure_injector,
                final_verifier=verify_portable_closeout,
            )
            reservation.assert_current("portable closeout completion")
            return {
                **refreshed,
                "runtime_evidence_status": DECLARED_RUNTIME_EVIDENCE_STATUS,
                "receipt_state_before": (
                    "VERIFIED" if original_receipt_identity is not None else "ABSENT"
                ),
                "receipt_state_after": "ABSENT",
                "receipt_archive_root": (
                    str(archive_root) if archive_root is not None else None
                ),
                "receipt_archive_path": (
                    str(archived_path) if archived_path is not None else None
                ),
            }
        except BaseException as exc:
            rollback_failures: list[str] = []
            receipt_restored = False
            archived_identity = None
            if archived_path is not None and (
                archived_path.exists() or archived_path.is_symlink()
            ):
                try:
                    archived_identity = _assert_replaceable_receipt_bundle(archived_path)
                except IntegrationError as archive_exc:
                    rollback_failures.append(
                        f"archived receipt validation failed: {archive_exc}"
                    )
            if receipt_archived:
                try:
                    reservation.assert_current("before portable closeout receipt rollback")
                    if archived_identity != original_receipt_identity:
                        raise IntegrationError(
                            "portable closeout archived receipt identity drifted before rollback"
                        )
                    if _entry_stat_at(
                        reservation.parent_descriptor,
                        destination.name,
                    ) is not None:
                        raise IntegrationError(
                            "competing receipt destination blocks portable closeout rollback"
                        )
                    os.replace(
                        archived_name,
                        destination.name,
                        src_dir_fd=archive_descriptor,
                        dst_dir_fd=reservation.parent_descriptor,
                    )
                    if (
                        _assert_replaceable_receipt_bundle(destination)
                        != original_receipt_identity
                    ):
                        raise IntegrationError(
                            "portable closeout restored receipt identity drifted"
                        )
                    reservation.assert_current("after portable closeout receipt rollback")
                    receipt_restored = True
                except (OSError, IntegrationError) as rollback_exc:
                    rollback_failures.append(str(rollback_exc))
            raise IntegrationError(
                "portable closeout failed: "
                f"original={exc}; receipt_archive_root={archive_root}; "
                f"receipt_restored={receipt_restored}; rollback={rollback_failures}"
            ) from exc
        finally:
            if archive_descriptor is not None:
                os.close(archive_descriptor)


def write_install(
    repository_root: Path = ROOT,
    source: Path | None = None,
    archive: Path | None = None,
) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    source = source or repository_root / PACKAGE_RELATIVE
    archive = archive or repository_root / ARCHIVE_RELATIVE
    expected = build_expected(source, archive, repository_root)

    destinations: list[tuple[Path, dict[str, FilePayload], str]] = []
    for relative_root, label in (
        (RUNTIME_RELATIVE, "Runtime"),
        (WORKSPACE_RELATIVE, "workspace"),
    ):
        for name, tree in expected["trees"].items():
            destinations.append((repository_root / relative_root / name, tree, f"{label} Skill"))
    destinations.append((repository_root / DOC_RELATIVE, expected["docs"], "documentation"))

    to_write: list[tuple[Path, dict[str, FilePayload], str]] = []
    for destination, tree, label in destinations:
        if destination.exists() or destination.is_symlink():
            try:
                actual = _read_tree(destination)
            except IntegrationError as exc:
                fail(f"refusing to overwrite invalid {label}: {destination}: {exc}")
            if actual != tree:
                fail(f"refusing to overwrite unowned or drifted {label}: {destination}")
        else:
            to_write.append((destination, tree, label))
    for destination, tree, _label in to_write:
        _write_tree(destination, tree, containment_root=repository_root)
    return check_install(repository_root, source, archive)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Safely integrate the pinned frontend-to-MiniApp Skill package"
    )
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--check", action="store_true", help="verify without writing")
    operation.add_argument(
        "--extract", action="store_true", help="safely extract the pinned source package only"
    )
    operation.add_argument(
        "--refresh-owned",
        action="store_true",
        help="atomically refresh only an identity-verified prior installation",
    )
    operation.add_argument(
        "--qualify-local",
        action="store_true",
        help=(
            "run the fixed trusted local command suite and atomically write a "
            "digest-bound receipt; does not refresh installed Skills"
        ),
    )
    operation.add_argument(
        "--closeout-portable",
        action="store_true",
        help=(
            "atomically archive any valid host receipt in an owned 0700 system "
            "temporary directory and transactionally refresh installed Skills to DECLARED"
        ),
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    repository_root = args.root.resolve()
    archive = repository_root / ARCHIVE_RELATIVE
    source = repository_root / PACKAGE_RELATIVE
    try:
        if args.qualify_local:
            evidence = record_local_runtime_qualification(repository_root)
            result = {"runtime_evidence_status": evidence["state"]}
            decision = "LOCAL_RUNTIME_RECEIPT_RECORDED"
        elif args.closeout_portable:
            result = closeout_portable(repository_root, source, archive)
            decision = "PORTABLE_DECLARED_CLOSEOUT_COMPLETED"
        elif args.extract:
            result = extract_archive(archive, source)
            decision = "SOURCE_EXTRACTED_AND_VERIFIED"
        elif args.refresh_owned:
            result = refresh_owned_install(repository_root, source, archive)
            decision = "OWNED_INSTALLATION_REFRESHED"
        elif args.check:
            result = check_install(repository_root, source, archive)
            decision = "INSTALLED_ARTIFACTS_VERIFIED"
        else:
            if not source.is_dir() or source.is_symlink():
                fail(
                    f"canonical source is absent; run this importer with --extract first: {source}"
                )
            result = write_install(repository_root, source, archive)
            decision = "SKILL_CONTRACTS_INSTALLED"
    except IntegrationError as exc:
        print(json.dumps({"decision": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 1
    runtime_evidence_status = (
        result.get("runtime_evidence_status")
        or result.get("manifest", {}).get("runtime_evidence_status")
        or DECLARED_RUNTIME_EVIDENCE_STATUS
    )
    output = {
        "decision": decision,
        "source_archive_sha256": "sha256:" + EXPECTED_ARCHIVE_SHA256,
        "skills": len(EXPECTED_SKILLS),
        "dependency_edges": result.get("dependency_edge_count")
        or result.get("summary", {}).get("dependency_edge_count"),
        "runtime_evidence_status": runtime_evidence_status,
        "external_evidence_status": EXTERNAL_EVIDENCE_STATUS,
        "certification": CERTIFICATION_STATUS,
    }
    if "receipt_archive_root" in result:
        output.update(
            {
                "receipt_state_before": result["receipt_state_before"],
                "receipt_state_after": result["receipt_state_after"],
                "receipt_archive_root": result["receipt_archive_root"],
                "receipt_archive_path": result["receipt_archive_path"],
            }
        )
    print(
        json.dumps(
            output,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
