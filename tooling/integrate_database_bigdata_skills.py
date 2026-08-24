#!/usr/bin/env python3
"""Install the pinned database and Big Data Skill package safely.

The attached ZIP and its extracted tree are immutable source inputs.  This
repository-owned importer validates their identity without importing or
executing package code, normalizes the 46 Skill interfaces for Codex, records
provenance, and keeps provider/runtime/certification claims fail-closed.

Local reference-tool execution remains disabled because Python isolated mode
is not a filesystem/network sandbox.  The qualification command validates the
pinned source and reports ``NOT_RUN`` without executing package code.
"""

from __future__ import annotations

import argparse
import ast
import fcntl
import hashlib
import io
import json
import os
import platform
import re
import shutil
import stat
import sys
import tempfile
import uuid
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

try:
    import yaml
    from jsonschema import Draft202012Validator
except ModuleNotFoundError as exc:  # pragma: no cover - dependency diagnostic
    raise SystemExit(
        "PyYAML and jsonschema are required; use the repository Make target"
    ) from exc

import skill_creator_tools


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIRECTORY = "elmos-database-bigdata-skills-v1.0.0"
PACKAGE_NAME = "elmos-database-bigdata-skills"
PACKAGE_VERSION = "1.0.0"
NAMESPACE = "elmos-database-bigdata-v1"

ARCHIVE_RELATIVE = Path("skills/subskills") / f"{PACKAGE_DIRECTORY}.zip"
SOURCE_RELATIVE = Path("skills") / PACKAGE_DIRECTORY
RUNTIME_RELATIVE = Path("agent-skills/runtime")
WORKSPACE_RELATIVE = Path(".agents/skills")
DOC_RELATIVE = Path("docs/database-bigdata-skills")
INSTALL_MANIFEST_NAME = "installed-manifest.json"
QUALIFICATION_NAME = "local-reference-tool-qualification.json"
QUALIFICATION_EVIDENCE_DIRECTORY = "local-reference-tool-evidence"
README_NAME = "README.md"
FILE_MODE = 0o644
DIRECTORY_MODE = 0o755
PRIVATE_DIRECTORY_MODE = 0o700
LOCK_FILE_MODE = 0o600

# Executing source-package code requires an operating-system sandbox that
# default-denies filesystem writes and network access.  Python isolated mode
# and static AST checks are not such a sandbox, so local execution remains
# deliberately disabled until that boundary exists.
LOCAL_QUALIFICATION_EXECUTION_ENABLED = False

EXPECTED_ARCHIVE_SHA256 = (
    "e5baae82593d84f4784900de7be93a7fa0b582dc081ac97bc35a4d6e12865e53"
)
EXPECTED_ARCHIVE_BYTES = 218_486
EXPECTED_ARCHIVE_ENTRIES = 156
EXPECTED_SOURCE_FILES = 98
EXPECTED_SOURCE_BYTES = 497_188
EXPECTED_MANIFEST_SHA256 = (
    "285164d0264b2d5e141fd98c8a1ce3578bafdd5470463485ee1e8cb429ea5115"
)
EXPECTED_CHECKSUM_ENTRIES = 96
EXPECTED_SKILLS = 46
EXPECTED_PROFILES = 10
EXPECTED_SCHEMAS = 7
EXPECTED_TECHNOLOGIES = 29
EXPECTED_PATTERNS = 10
EXPECTED_TEMPLATES = 10
EXPECTED_ADAPTER_BLUEPRINTS = 13
EXPECTED_TASK_IDS = 554
EXPECTED_GROUP_COUNTS = {
    "bigdata-core": 22,
    "bigdata-templates": 10,
    "database-intelligence": 13,
    "orchestration": 1,
}
EXPECTED_CHECKSUM_EXCLUSIONS = [
    "**/*.pyc",
    "**/__pycache__/**",
    "MANIFEST.json",
    "VALIDATION-REPORT.md",
]

REQUIRED_SKILL_SECTIONS = (
    "## 目标",
    "## 适用触发条件",
    "## 输入",
    "## 执行流程",
    "## 强制决策规则",
    "## 必需产物",
    "## 验收标准",
    "## 失败、降级与恢复",
    "## 完成检查表",
)
SOURCE_FRONTMATTER_KEYS = {
    "name",
    "description",
    "version",
    "group",
    "dependencies",
    "triggers",
    "outputs",
}
TASK_ID = re.compile(r"\*\*([A-Z][A-Z0-9]*-\d{3})\*\*")
SAFE_NAME = re.compile(r"^elmos-[a-z0-9][a-z0-9-]*$")

REFERENCE_TOOLS: dict[str, dict[str, Any]] = {
    "database-selector": {
        "path": "tools/database_selector.py",
        "expected": "database-decision.json",
        "related_skills": [
            "elmos-database-constraint-filter",
            "elmos-database-mcda-ranker",
            "elmos-polyglot-persistence-planner",
        ],
        "mapping_basis": "repository-inference",
        "qualified_subcapability": (
            "heuristic hard filtering and role-based ranking over the pinned "
            "catalog; sensitivity and representative benchmarks remain NOT_RUN"
        ),
    },
    "architecture-selector": {
        "path": "tools/architecture_selector.py",
        "expected": "architecture-decision.json",
        "related_skills": ["elmos-bigdata-pattern-selector"],
        "mapping_basis": "repository-inference",
        "qualified_subcapability": (
            "deterministic architecture-pattern selection for the three package "
            "examples; target platform execution remains NOT_RUN"
        ),
    },
    "plan-estimator": {
        "path": "tools/plan_estimator.py",
        "expected": "cost-and-eta.json",
        "related_skills": ["elmos-bigdata-project-orchestrator"],
        "mapping_basis": "repository-inference",
        "qualified_subcapability": (
            "parametric autonomous runtime, human-equivalent effort, and unpriced "
            "token-cost estimation for the three package examples; database capacity, "
            "provider pricing, and TCO validation remain NOT_RUN"
        ),
    },
}


class IntegrationError(RuntimeError):
    """A fail-closed source, qualification, or installation error."""


def fail(message: str) -> None:
    raise IntegrationError(message)


def resolved_repository_root(repository_root: Path) -> Path:
    """Return one real repository root used for every confinement decision."""

    try:
        resolved = repository_root.resolve(strict=True)
    except OSError as exc:
        fail(f"repository root cannot be resolved: {repository_root}: {exc}")
    if not resolved.is_dir() or resolved.is_symlink():
        fail(f"repository root must resolve to a real directory: {repository_root}")
    return resolved


def assert_repository_path(
    repository_root: Path,
    path: Path,
    label: str,
) -> Path:
    """Reject lexical escapes and every existing symlink below the repository."""

    repository_root = resolved_repository_root(repository_root)
    candidate = Path(os.path.abspath(os.fspath(path)))
    try:
        relative = candidate.relative_to(repository_root)
    except ValueError:
        fail(f"{label} path is outside the repository: {candidate}")

    current = repository_root
    for index, part in enumerate(relative.parts):
        current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            break
        except OSError as exc:
            fail(f"cannot inspect {label} path component {current}: {exc}")
        if stat.S_ISLNK(metadata.st_mode):
            fail(f"{label} path contains a symbolic-link component: {current}")
        if index < len(relative.parts) - 1 and not stat.S_ISDIR(metadata.st_mode):
            fail(f"{label} path ancestor is not a directory: {current}")
    return candidate


def read_regular_file_once(
    repository_root: Path,
    path: Path,
    label: str,
    *,
    expected_bytes: int | None = None,
) -> bytes:
    """Read a confined regular file through the same descriptor that is checked."""

    confined = assert_repository_path(repository_root, path, label)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(confined, flags)
    except OSError as exc:
        fail(f"cannot open {label} as a regular file: {confined}: {exc}")
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            fail(f"{label} must be a regular file: {confined}")
        if expected_bytes is not None and before.st_size != expected_bytes:
            fail(
                f"{label} byte count mismatch: expected={expected_bytes} "
                f"actual={before.st_size}"
            )
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            content = handle.read()
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            fail(f"{label} changed while it was being read: {confined}")
        if len(content) != before.st_size:
            fail(f"{label} read was incomplete: {confined}")
        path_metadata = os.lstat(confined)
        if (path_metadata.st_dev, path_metadata.st_ino) != (before.st_dev, before.st_ino):
            fail(f"{label} path changed while it was being read: {confined}")
        assert_repository_path(repository_root, confined, label)
        return content
    except OSError as exc:
        fail(f"cannot read {label}: {confined}: {exc}")
    finally:
        os.close(descriptor)


def read_stable_regular_path(path: Path, label: str) -> tuple[bytes, int]:
    """Read one non-symlink regular path and return bytes plus its mode."""

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        fail(f"cannot open {label}: {path}: {exc}")
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            fail(f"{label} is not a regular file: {path}")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            content = handle.read()
        after = os.fstat(descriptor)
        path_metadata = os.lstat(path)
        identity_before = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        )
        identity_after = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        )
        if identity_before != identity_after or (
            path_metadata.st_dev,
            path_metadata.st_ino,
        ) != (before.st_dev, before.st_ino):
            fail(f"{label} changed while it was being read: {path}")
        if len(content) != before.st_size:
            fail(f"{label} read was incomplete: {path}")
        return content, stat.S_IMODE(before.st_mode)
    except OSError as exc:
        fail(f"cannot read {label}: {path}: {exc}")
    finally:
        os.close(descriptor)


_ACTIVE_MUTATION_LOCKS: dict[str, tuple[int, int]] = {}


@contextmanager
def mutation_lock(repository_root: Path):
    """Serialize importer mutations without adding a worktree lock artifact."""

    repository_root = resolved_repository_root(repository_root)
    key = str(repository_root)
    active = _ACTIVE_MUTATION_LOCKS.get(key)
    if active is not None:
        descriptor, depth = active
        _ACTIVE_MUTATION_LOCKS[key] = (descriptor, depth + 1)
        try:
            yield repository_root
        finally:
            current_descriptor, current_depth = _ACTIVE_MUTATION_LOCKS[key]
            _ACTIVE_MUTATION_LOCKS[key] = (current_descriptor, current_depth - 1)
        return

    lock_digest = sha256_bytes(key.encode("utf-8"))[:24]
    lock_path = Path(tempfile.gettempdir()) / (
        f".elmos-database-bigdata-{lock_digest}.lock"
    )
    flags = (
        os.O_RDWR
        | os.O_CREAT
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(lock_path, flags, LOCK_FILE_MODE)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            fail(f"mutation lock is not a regular file: {lock_path}")
        if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
            fail(f"mutation lock is owned by another user: {lock_path}")
        os.fchmod(descriptor, LOCK_FILE_MODE)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail(f"another database/Big Data importer mutation is active: {repository_root}")
    except BaseException:
        if "descriptor" in locals():
            os.close(descriptor)
        raise

    _ACTIVE_MUTATION_LOCKS[key] = (descriptor, 1)
    try:
        yield repository_root
    finally:
        _ACTIVE_MUTATION_LOCKS.pop(key, None)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


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


def load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        fail(f"invalid {label}: {path}: {exc}")


def validate_relative_path(relative: str, label: str) -> PurePosixPath:
    if not relative or "\\" in relative or "\x00" in relative:
        fail(f"invalid {label} path: {relative!r}")
    path = PurePosixPath(relative)
    if (
        path.is_absolute()
        or str(path) != relative
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        fail(f"{label} path escapes or is not normalized: {relative}")
    return path


def assert_inside(root: Path, path: Path, label: str) -> None:
    try:
        path.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as exc:
        fail(f"{label} path escapes root: {path}: {exc}")


def source_files(source: Path) -> list[Path]:
    if not source.is_dir() or source.is_symlink():
        fail(f"canonical source must be a real directory: {source}")
    entries = list(source.rglob("*"))
    symlinks = [entry.relative_to(source).as_posix() for entry in entries if entry.is_symlink()]
    if symlinks:
        fail(f"canonical source may not contain symbolic links: {symlinks[:5]}")
    files: list[Path] = []
    for entry in entries:
        if entry.is_file():
            assert_inside(source, entry, "source file")
            files.append(entry)
        elif not entry.is_dir():
            fail(f"unsupported canonical source entry: {entry}")
    return sorted(files, key=lambda item: item.relative_to(source).as_posix())


def read_archive(
    archive: Path,
    repository_root: Path,
) -> tuple[dict[str, bytes], dict[str, int]]:
    repository_root = resolved_repository_root(repository_root)
    archive_bytes = read_regular_file_once(
        repository_root,
        archive,
        "source archive",
        expected_bytes=EXPECTED_ARCHIVE_BYTES,
    )
    actual_archive_digest = sha256_bytes(archive_bytes)
    if actual_archive_digest != EXPECTED_ARCHIVE_SHA256:
        fail(
            "archive SHA-256 mismatch: "
            f"expected={EXPECTED_ARCHIVE_SHA256} actual={actual_archive_digest}"
        )

    archive_files: dict[str, bytes] = {}
    archive_modes: dict[str, int] = {}
    seen: set[str] = set()
    seen_casefolded: set[str] = set()
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as handle:
            entries = handle.infolist()
            if len(entries) != EXPECTED_ARCHIVE_ENTRIES:
                fail(
                    f"archive must contain {EXPECTED_ARCHIVE_ENTRIES} entries; "
                    f"found {len(entries)}"
                )
            uncompressed_bytes = sum(info.file_size for info in entries)
            if uncompressed_bytes != EXPECTED_SOURCE_BYTES:
                fail(
                    "archive declared uncompressed byte count mismatch: "
                    f"expected={EXPECTED_SOURCE_BYTES} actual={uncompressed_bytes}"
                )
            if any(
                info.file_size < 0
                or info.file_size > EXPECTED_SOURCE_BYTES
                or info.compress_size < 0
                or info.compress_size > EXPECTED_ARCHIVE_BYTES
                for info in entries
            ):
                fail("archive entry size exceeds the pinned package bounds")

            validated_files: list[tuple[zipfile.ZipInfo, str, int]] = []
            for info in entries:
                name = info.filename
                if getattr(info, "orig_filename", name) != name:
                    fail(f"archive entry name was NUL-truncated or normalized: {name!r}")
                if name in seen:
                    fail(f"duplicate archive entry: {name}")
                seen.add(name)
                if info.flag_bits & 0x1:
                    fail(f"encrypted archive entries are not allowed: {name}")
                if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                    fail(f"archive entry uses an unsupported compression method: {name}")
                if name.endswith("/"):
                    normalized = name[:-1]
                    if not normalized:
                        fail("archive contains an empty directory name")
                else:
                    normalized = name
                path = validate_relative_path(normalized, "archive")
                if not path.parts or path.parts[0] != PACKAGE_DIRECTORY:
                    fail(f"archive entry is outside the package root: {name}")
                normalized_casefolded = normalized.casefold()
                if normalized_casefolded in seen_casefolded:
                    fail(f"case- or kind-colliding archive entry: {name}")
                seen_casefolded.add(normalized_casefolded)
                mode = info.external_attr >> 16
                file_type = stat.S_IFMT(mode)
                if info.is_dir():
                    if file_type not in {0, stat.S_IFDIR}:
                        fail(f"archive directory has an unsafe mode: {name}")
                    continue
                if file_type not in {0, stat.S_IFREG}:
                    fail(f"archive contains a non-regular file: {name}")
                relative = PurePosixPath(*path.parts[1:]).as_posix()
                if not relative:
                    fail(f"archive file has no package-relative path: {name}")
                validated_files.append((info, relative, stat.S_IMODE(mode)))

            for info, relative, file_mode in validated_files:
                content = handle.read(info)
                if len(content) != info.file_size:
                    fail(f"archive read was incomplete: {info.filename}")
                archive_files[relative] = content
                archive_modes[relative] = file_mode
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        fail(f"cannot validate source archive: {exc}")

    if len(archive_files) != EXPECTED_SOURCE_FILES:
        fail(
            f"archive must contain {EXPECTED_SOURCE_FILES} files; "
            f"found {len(archive_files)}"
        )
    actual_uncompressed_bytes = sum(len(content) for content in archive_files.values())
    if actual_uncompressed_bytes != EXPECTED_SOURCE_BYTES:
        fail(
            f"archive uncompressed byte count mismatch: expected={EXPECTED_SOURCE_BYTES} "
            f"actual={actual_uncompressed_bytes}"
        )

    mode_counts: dict[int, int] = {}
    for mode in archive_modes.values():
        mode_counts[mode] = mode_counts.get(mode, 0) + 1
    if mode_counts != {0o644: 92, 0o755: 6}:
        fail(f"archive file modes changed: {mode_counts}")
    return archive_files, archive_modes


def validate_archive(
    archive: Path,
    source: Path,
    repository_root: Path,
) -> list[dict[str, Any]]:
    repository_root = resolved_repository_root(repository_root)
    archive = assert_repository_path(repository_root, archive, "source archive")
    source = assert_repository_path(repository_root, source, "canonical source")
    archive_files, archive_modes = read_archive(archive, repository_root)
    return validate_extracted_tree(
        repository_root,
        source,
        archive_files,
        archive_modes,
    )


def validate_extracted_tree(
    repository_root: Path,
    source: Path,
    archive_files: Mapping[str, bytes],
    archive_modes: Mapping[str, int],
) -> list[dict[str, Any]]:
    repository_root = resolved_repository_root(repository_root)
    source = assert_repository_path(repository_root, source, "canonical source")
    extracted = source_files(source)
    extracted_names = {path.relative_to(source).as_posix() for path in extracted}
    if extracted_names != set(archive_files):
        fail(
            "canonical extraction differs from archive inventory: "
            f"missing={sorted(set(archive_files) - extracted_names)} "
            f"extra={sorted(extracted_names - set(archive_files))}"
        )
    inventory: list[dict[str, Any]] = []
    for relative in sorted(archive_files):
        extracted_path = source / relative
        extracted_bytes = read_regular_file_once(
            repository_root,
            extracted_path,
            f"canonical source file {relative}",
            expected_bytes=len(archive_files[relative]),
        )
        if extracted_bytes != archive_files[relative]:
            fail(f"canonical extraction differs from archive bytes: {relative}")
        extracted_mode = stat.S_IMODE(os.lstat(extracted_path).st_mode)
        if extracted_mode != archive_modes[relative]:
            fail(
                f"canonical extraction mode differs from archive: {relative}: "
                f"expected={archive_modes[relative]:04o} actual={extracted_mode:04o}"
            )
        inventory.append(
            {
                "path": relative,
                "bytes": len(extracted_bytes),
                "mode": f"{extracted_mode:04o}",
                "sha256": digest(extracted_bytes),
            }
        )
    return inventory


def extract_canonical_source(repository_root: Path = ROOT) -> Path:
    """Materialize the pinned ZIP into a new canonical source directory."""

    with mutation_lock(repository_root) as repository_root:
        archive = assert_repository_path(
            repository_root,
            repository_root / ARCHIVE_RELATIVE,
            "source archive",
        )
        source = assert_repository_path(
            repository_root,
            repository_root / SOURCE_RELATIVE,
            "canonical source",
        )
        if source.exists() or source.is_symlink():
            validate_archive(archive, source, repository_root)
            return source
        archive_files, archive_modes = read_archive(archive, repository_root)
        source.parent.mkdir(parents=True, mode=DIRECTORY_MODE, exist_ok=True)
        assert_repository_path(repository_root, source.parent, "canonical source parent")
        staged = assert_repository_path(
            repository_root,
            source.parent / f".{PACKAGE_DIRECTORY}.extract.{uuid.uuid4().hex}",
            "canonical source staging",
        )
        try:
            staged.mkdir(mode=DIRECTORY_MODE)
            staged.chmod(DIRECTORY_MODE)
            for relative in sorted(archive_files):
                validate_relative_path(relative, "extracted")
                target = staged / relative
                target.parent.mkdir(parents=True, mode=DIRECTORY_MODE, exist_ok=True)
                target.parent.chmod(DIRECTORY_MODE)
                target.write_bytes(archive_files[relative])
                target.chmod(archive_modes[relative])
            for directory in sorted(
                (path for path in staged.rglob("*") if path.is_dir()),
                key=lambda path: path.as_posix(),
            ):
                if directory.is_symlink():
                    fail(f"canonical source staging contains a symbolic link: {directory}")
                directory.chmod(DIRECTORY_MODE)
            validate_extracted_tree(
                repository_root,
                staged,
                archive_files,
                archive_modes,
            )
            assert_repository_path(repository_root, source, "canonical source")
            if source.exists() or source.is_symlink():
                fail(f"canonical source appeared during extraction: {source}")
            os.replace(staged, source)
            validate_extracted_tree(
                repository_root,
                source,
                archive_files,
                archive_modes,
            )
        except BaseException:
            if staged.is_dir() and not staged.is_symlink():
                shutil.rmtree(staged, ignore_errors=True)
            raise
        return source


def parse_source_skill(path: Path) -> tuple[dict[str, Any], str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        fail(f"cannot read source Skill {path}: {exc}")
    match = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.DOTALL)
    if match is None:
        fail(f"source Skill has invalid YAML frontmatter: {path}")
    try:
        metadata = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        fail(f"source Skill frontmatter is invalid: {path}: {exc}")
    if not isinstance(metadata, dict):
        fail(f"source Skill frontmatter is not an object: {path}")
    if set(metadata) != SOURCE_FRONTMATTER_KEYS:
        fail(
            f"source Skill frontmatter keys changed: {path}: "
            f"expected={sorted(SOURCE_FRONTMATTER_KEYS)} actual={sorted(metadata)}"
        )
    return metadata, match.group(2).lstrip("\n")


def directory_digest(path: Path) -> str:
    """Match the immutable package's manifest-owned directory hashing."""

    value = hashlib.sha256()
    for item in sorted(path.rglob("*"), key=lambda candidate: candidate.as_posix()):
        if item.is_symlink():
            fail(f"source Skill directory may not contain a symbolic link: {item}")
        if item.is_file() and "__pycache__" not in item.parts and item.suffix != ".pyc":
            relative = item.relative_to(path).as_posix().encode("utf-8")
            content = item.read_bytes()
            value.update(len(relative).to_bytes(8, "big"))
            value.update(relative)
            value.update(len(content).to_bytes(8, "big"))
            value.update(content)
    return value.hexdigest()


def topological_order(graph: Mapping[str, Sequence[str]]) -> list[str]:
    visiting: set[str] = set()
    visited: set[str] = set()
    ordered: list[str] = []

    def visit(name: str, trail: list[str]) -> None:
        if name in visited:
            return
        if name in visiting:
            fail("source Skill dependency cycle: " + " -> ".join(trail + [name]))
        visiting.add(name)
        for dependency in graph[name]:
            visit(dependency, trail + [name])
        visiting.remove(name)
        visited.add(name)
        ordered.append(name)

    for skill_name in graph:
        visit(skill_name, [])
    return ordered


def validate_skills(source: Path, manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    paths = sorted((source / "skills").glob("*/SKILL.md"))
    if len(paths) != EXPECTED_SKILLS:
        fail(f"expected {EXPECTED_SKILLS} source Skills; found {len(paths)}")
    unexpected_skill_files = sorted(
        path.relative_to(source / "skills").as_posix()
        for path in (source / "skills").rglob("*")
        if path.is_file() and path.name != "SKILL.md"
    )
    if unexpected_skill_files:
        fail(f"source Skill directories contain unexpected files: {unexpected_skill_files}")

    records: list[dict[str, Any]] = []
    graph: dict[str, list[str]] = {}
    task_locations: dict[str, str] = {}
    groups: dict[str, int] = {}
    for path in paths:
        directory = path.parent.name
        if SAFE_NAME.fullmatch(directory) is None:
            fail(f"unsafe source Skill name: {directory}")
        if len(directory) > skill_creator_tools.MAX_SKILL_NAME_LENGTH:
            fail(f"source Skill name exceeds Codex limit: {directory}")
        metadata, body = parse_source_skill(path)
        if metadata.get("name") != directory:
            fail(f"source Skill name mismatch: {path}")
        if metadata.get("version") != PACKAGE_VERSION:
            fail(f"source Skill version mismatch: {path}")
        description = metadata.get("description")
        group = metadata.get("group")
        dependencies = metadata.get("dependencies")
        triggers = metadata.get("triggers")
        outputs = metadata.get("outputs")
        if not isinstance(description, str) or not description.strip():
            fail(f"source Skill description is empty: {path}")
        if not isinstance(group, str) or group not in EXPECTED_GROUP_COUNTS:
            fail(f"source Skill group is invalid: {path}")
        for value, label, allow_empty in (
            (dependencies, "dependencies", True),
            (triggers, "triggers", False),
            (outputs, "outputs", False),
        ):
            if (
                not isinstance(value, list)
                or (not allow_empty and not value)
                or not all(isinstance(item, str) and item for item in value)
                or len(value) != len(set(value))
            ):
                fail(f"source Skill {label} are invalid: {path}")
        missing_sections = [section for section in REQUIRED_SKILL_SECTIONS if section not in body]
        if missing_sections:
            fail(f"source Skill is missing required sections: {path}: {missing_sections}")
        task_ids = TASK_ID.findall(body)
        if len(task_ids) < 6:
            fail(f"source Skill has too few stable task IDs: {path}")
        for task_id in task_ids:
            if task_id in task_locations:
                fail(
                    f"duplicate source task ID {task_id}: "
                    f"{task_locations[task_id]} and {path}"
                )
            task_locations[task_id] = path.relative_to(source).as_posix()
        groups[group] = groups.get(group, 0) + 1
        graph[directory] = list(dependencies)
        records.append(
            {
                "name": directory,
                "description": description.strip(),
                "group": group,
                "dependencies": list(dependencies),
                "triggers": list(triggers),
                "outputs": list(outputs),
                "source_path": path.relative_to(source).as_posix(),
                "source_sha256": digest(path.read_bytes()),
                "source_tree_sha256": "sha256:" + directory_digest(path.parent),
                "body": body.rstrip() + "\n",
            }
        )

    known = set(graph)
    for name, dependencies in graph.items():
        missing = sorted(set(dependencies) - known)
        if missing:
            fail(f"source Skill has missing dependencies: {name}: {missing}")
    order = topological_order(graph)
    if len(order) != EXPECTED_SKILLS:
        fail("source Skill dependency order is incomplete")
    if groups != EXPECTED_GROUP_COUNTS:
        fail(f"source Skill group counts changed: {groups}")
    if len(task_locations) != EXPECTED_TASK_IDS:
        fail(
            f"expected {EXPECTED_TASK_IDS} unique task IDs; found {len(task_locations)}"
        )

    manifest_skills = manifest.get("skills")
    if not isinstance(manifest_skills, list) or len(manifest_skills) != EXPECTED_SKILLS:
        fail("source manifest Skill inventory is invalid")
    manifest_by_name = {
        item.get("name"): item for item in manifest_skills if isinstance(item, dict)
    }
    if set(manifest_by_name) != known:
        fail("source manifest and Skill directory inventories differ")
    for record in records:
        item = manifest_by_name[record["name"]]
        expected_manifest = {
            "dependencies": record["dependencies"],
            "group": record["group"],
            "name": record["name"],
            "path": f"skills/{record['name']}",
            "sha256": record["source_tree_sha256"].removeprefix("sha256:"),
            "version": PACKAGE_VERSION,
        }
        if item != expected_manifest:
            fail(f"source manifest Skill record drifted: {record['name']}")
    return records


def expand_dependencies(requested: Iterable[str], graph: Mapping[str, Sequence[str]]) -> set[str]:
    expanded: set[str] = set()

    def visit(name: str) -> None:
        if name in expanded:
            return
        expanded.add(name)
        for dependency in graph[name]:
            visit(dependency)

    for name in requested:
        visit(name)
    return expanded


def validate_profiles(source: Path, skills: Sequence[Mapping[str, Any]], manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    graph = {str(item["name"]): list(item["dependencies"]) for item in skills}
    paths = sorted((source / "profiles").glob("*.json"))
    if len(paths) != EXPECTED_PROFILES:
        fail(f"expected {EXPECTED_PROFILES} profiles; found {len(paths)}")
    records: list[dict[str, Any]] = []
    for path in paths:
        profile = load_json(path, "profile")
        if not isinstance(profile, dict) or profile.get("profile") != path.stem:
            fail(f"profile identity mismatch: {path}")
        if profile.get("version") != PACKAGE_VERSION:
            fail(f"profile version mismatch: {path}")
        declared = profile.get("skills")
        if (
            not isinstance(declared, list)
            or not declared
            or not all(isinstance(item, str) for item in declared)
            or len(declared) != len(set(declared))
        ):
            fail(f"profile Skill inventory is invalid: {path}")
        unknown = sorted(set(declared) - set(graph))
        if unknown:
            fail(f"profile references unknown Skills: {path}: {unknown}")
        expanded = expand_dependencies(declared, graph)
        records.append(
            {
                "profile": path.stem,
                "source_path": path.relative_to(source).as_posix(),
                "declared_skills": list(declared),
                "expanded_skills": sorted(expanded),
            }
        )
    by_name = {item["profile"]: item for item in records}
    if set(by_name["full"]["declared_skills"]) != set(graph):
        fail("full profile does not declare all source Skills")
    manifest_profiles = manifest.get("profiles")
    if not isinstance(manifest_profiles, dict) or set(manifest_profiles) != set(by_name):
        fail("source manifest profile inventory is invalid")
    for name, item in by_name.items():
        expected = {
            "declared_skill_count": len(item["declared_skills"]),
            "path": item["source_path"],
        }
        if manifest_profiles[name] != expected:
            fail(f"source manifest profile record drifted: {name}")
    return records


def validate_catalogs(source: Path, skills: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    skill_names = {str(item["name"]) for item in skills}
    database = load_json(source / "catalog/database-capabilities.json", "technology catalog")
    technologies = database.get("technologies") if isinstance(database, dict) else None
    if not isinstance(technologies, list) or len(technologies) != EXPECTED_TECHNOLOGIES:
        fail("technology catalog count is invalid")
    technology_ids: list[str] = []
    for item in technologies:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            fail("technology catalog contains an invalid record")
        technology_ids.append(item["id"])
        if item.get("adapter_status") != "catalog-only":
            fail(f"technology is not catalog-only: {item['id']}")
    if len(technology_ids) != len(set(technology_ids)):
        fail("technology catalog IDs are not unique")

    architecture = load_json(source / "catalog/architecture-patterns.json", "architecture catalog")
    patterns = architecture.get("patterns") if isinstance(architecture, dict) else None
    if not isinstance(patterns, list) or len(patterns) != EXPECTED_PATTERNS:
        fail("architecture pattern count is invalid")
    pattern_ids = [item.get("id") for item in patterns if isinstance(item, dict)]
    if len(pattern_ids) != EXPECTED_PATTERNS or len(pattern_ids) != len(set(pattern_ids)):
        fail("architecture pattern IDs are invalid")

    templates = load_json(source / "catalog/project-templates.json", "project template catalog")
    template_items = templates.get("templates") if isinstance(templates, dict) else None
    if not isinstance(template_items, list) or len(template_items) != EXPECTED_TEMPLATES:
        fail("project template count is invalid")
    for item in template_items:
        if not isinstance(item, dict) or item.get("skill") not in skill_names:
            fail(f"project template references an unknown Skill: {item}")

    adapters = load_json(source / "catalog/technology-adapters.json", "adapter blueprints")
    adapter_items = adapters.get("adapters") if isinstance(adapters, dict) else None
    if not isinstance(adapter_items, list) or len(adapter_items) != EXPECTED_ADAPTER_BLUEPRINTS:
        fail("technology adapter blueprint count is invalid")
    roles = [item.get("role") for item in adapter_items if isinstance(item, dict)]
    if len(roles) != EXPECTED_ADAPTER_BLUEPRINTS or len(roles) != len(set(roles)):
        fail("technology adapter blueprint roles are invalid")

    rules = load_json(source / "catalog/selection-rules.json", "selection rules")
    if not isinstance(rules, dict) or not rules.get("hard_constraint_order"):
        fail("selection rules do not define hard-constraint order")
    return {
        "technologies": len(technologies),
        "patterns": len(patterns),
        "templates": len(template_items),
        "adapter_blueprints": len(adapter_items),
    }


def validate_schemas_and_examples(source: Path) -> dict[str, int]:
    schema_paths = sorted((source / "schemas").glob("*.schema.json"))
    if len(schema_paths) != EXPECTED_SCHEMAS:
        fail(f"expected {EXPECTED_SCHEMAS} JSON Schemas; found {len(schema_paths)}")
    schemas: dict[str, dict[str, Any]] = {}
    for path in schema_paths:
        schema = load_json(path, "JSON Schema")
        if not isinstance(schema, dict):
            fail(f"JSON Schema is not an object: {path}")
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as exc:
            fail(f"invalid Draft 2020-12 Schema {path}: {exc}")
        schemas[path.name] = schema

    mapping = {
        "requirements.json": "workload-requirements.schema.json",
        "database-decision.json": "database-decision.schema.json",
        "architecture-decision.json": "architecture-pattern-decision.schema.json",
        "cost-and-eta.json": "cost-and-eta.schema.json",
    }
    example_dirs = sorted(path for path in (source / "examples").iterdir() if path.is_dir())
    if len(example_dirs) != 3:
        fail(f"expected 3 source examples; found {len(example_dirs)}")
    validated = 0
    for directory in example_dirs:
        for filename, schema_name in mapping.items():
            instance = load_json(directory / filename, "example artifact")
            errors = sorted(
                Draft202012Validator(schemas[schema_name]).iter_errors(instance),
                key=lambda error: list(error.absolute_path),
            )
            if errors:
                fail(
                    f"example does not satisfy {schema_name}: "
                    f"{directory.name}/{filename}: {errors[0].message}"
                )
            validated += 1
    return {"schemas": len(schemas), "examples": len(example_dirs), "artifacts": validated}


def validate_reference_tool_contract(
    source: Path,
    skills: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    expected_paths = {
        "tools/database_selector.py",
        "tools/architecture_selector.py",
        "tools/plan_estimator.py",
    }
    configured_paths = {str(item["path"]) for item in REFERENCE_TOOLS.values()}
    if configured_paths != expected_paths or len(REFERENCE_TOOLS) != 3:
        fail("reference-tool mapping must own the exact three pinned tool paths")
    skill_names = {str(item["name"]) for item in skills}
    records: list[dict[str, Any]] = []
    for name, item in REFERENCE_TOOLS.items():
        if set(item) != {
            "path",
            "expected",
            "related_skills",
            "mapping_basis",
            "qualified_subcapability",
        }:
            fail(f"reference-tool mapping shape changed: {name}")
        tool_path = source / str(item["path"])
        if not tool_path.is_file() or tool_path.is_symlink():
            fail(f"reference tool must be a pinned regular file: {tool_path}")
        assert_inside(source, tool_path, "reference tool")
        try:
            syntax = ast.parse(tool_path.read_text(encoding="utf-8"), filename=str(tool_path))
        except (OSError, UnicodeError, SyntaxError) as exc:
            fail(f"reference tool cannot be parsed safely: {tool_path}: {exc}")
        banned_imports = {
            "http",
            "os",
            "requests",
            "shutil",
            "socket",
            "subprocess",
            "urllib",
        }
        for node in ast.walk(syntax):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".", 1)[0] for alias in node.names}
                if roots & banned_imports:
                    fail(f"reference tool imports a disallowed capability: {tool_path}")
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".", 1)[0]
                if root in banned_imports:
                    fail(f"reference tool imports a disallowed capability: {tool_path}")
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in {"compile", "eval", "exec", "__import__"}:
                    fail(f"reference tool uses dynamic execution: {tool_path}")
        related = item["related_skills"]
        if (
            not isinstance(related, list)
            or not related
            or not all(isinstance(value, str) for value in related)
            or len(related) != len(set(related))
            or not set(related).issubset(skill_names)
        ):
            fail(f"reference tool has invalid related Skills: {name}")
        if item["mapping_basis"] != "repository-inference":
            fail(f"reference tool mapping basis must remain explicit: {name}")
        if not isinstance(item["qualified_subcapability"], str) or not item[
            "qualified_subcapability"
        ]:
            fail(f"reference tool subcapability is empty: {name}")
        for example in sorted(path for path in (source / "examples").iterdir() if path.is_dir()):
            expected_output = example / str(item["expected"])
            if not expected_output.is_file() or expected_output.is_symlink():
                fail(f"reference tool expected artifact is missing: {name}/{example.name}")
        records.append(
            {
                "name": name,
                "path": str(item["path"]),
                "sha256": digest(tool_path.read_bytes()),
                "related_skills": list(related),
                "mapping_basis": item["mapping_basis"],
                "qualified_subcapability": item["qualified_subcapability"],
            }
        )
    return records


def source_tree_digest(inventory: Sequence[Mapping[str, Any]]) -> str:
    value = hashlib.sha256()
    for item in inventory:
        value.update(str(item["path"]).encode("utf-8"))
        value.update(b"\0")
        value.update(str(item["sha256"]).encode("ascii"))
        value.update(b"\0")
        value.update(str(item["bytes"]).encode("ascii"))
        value.update(b"\0")
        value.update(str(item["mode"]).encode("ascii"))
        value.update(b"\0")
    return "sha256:" + value.hexdigest()


def validate_source(repository_root: Path = ROOT) -> dict[str, Any]:
    repository_root = resolved_repository_root(repository_root)
    archive = assert_repository_path(
        repository_root,
        repository_root / ARCHIVE_RELATIVE,
        "source archive",
    )
    source = assert_repository_path(
        repository_root,
        repository_root / SOURCE_RELATIVE,
        "canonical source",
    )
    inventory = validate_archive(archive, source, repository_root)
    manifest_path = source / "MANIFEST.json"
    manifest_bytes = manifest_path.read_bytes()
    if sha256_bytes(manifest_bytes) != EXPECTED_MANIFEST_SHA256:
        fail("source MANIFEST.json trusted digest mismatch")
    manifest = load_json(manifest_path, "source manifest")
    if not isinstance(manifest, dict):
        fail("source manifest is not an object")
    if manifest.get("package") != PACKAGE_NAME or manifest.get("package_version") != PACKAGE_VERSION:
        fail("source package identity or version is invalid")
    if manifest.get("skill_count") != EXPECTED_SKILLS:
        fail("source manifest Skill count is invalid")
    if manifest.get("profile_count") != EXPECTED_PROFILES:
        fail("source manifest profile count is invalid")
    if manifest.get("group_counts") != EXPECTED_GROUP_COUNTS:
        fail("source manifest group counts are invalid")
    if manifest.get("checksum_exclusions") != EXPECTED_CHECKSUM_EXCLUSIONS:
        fail("source manifest checksum exclusions changed")
    trust_boundary = manifest.get("trust_boundary")
    if trust_boundary != {
        "catalog_entry_does_not_equal_verified_adapter": True,
        "catalog_is_seed_evidence": True,
        "production_requires_repository_specific_tests": True,
    }:
        fail("source manifest trust boundary changed")

    checksums = manifest.get("checksums_sha256")
    if not isinstance(checksums, dict) or len(checksums) != EXPECTED_CHECKSUM_ENTRIES:
        fail("source manifest checksum inventory is invalid")
    if list(checksums) != sorted(checksums):
        fail("source manifest checksums are not deterministically ordered")
    inventory_by_path = {str(item["path"]): item for item in inventory}
    expected_covered = set(inventory_by_path) - {"MANIFEST.json", "VALIDATION-REPORT.md"}
    if set(checksums) != expected_covered:
        fail("source manifest checksum coverage is not exact")
    for relative, expected_digest in checksums.items():
        if inventory_by_path[relative]["sha256"] != f"sha256:{expected_digest}":
            fail(f"source manifest checksum mismatch: {relative}")

    skills = validate_skills(source, manifest)
    profiles = validate_profiles(source, skills, manifest)
    catalogs = validate_catalogs(source, skills)
    validation = validate_schemas_and_examples(source)
    reference_tools = validate_reference_tool_contract(source, skills)
    return {
        "archive": archive,
        "source": source,
        "manifest": manifest,
        "inventory": inventory,
        "source_tree_sha256": source_tree_digest(inventory),
        "skills": skills,
        "profiles": profiles,
        "catalogs": catalogs,
        "validation": validation,
        "reference_tools": reference_tools,
    }


def expected_reference_runs(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = Path(summary["source"])
    runs: list[dict[str, Any]] = []
    example_dirs = sorted(path for path in (source / "examples").iterdir() if path.is_dir())
    for tool_name, tool in REFERENCE_TOOLS.items():
        for directory in example_dirs:
            input_path = directory / "requirements.json"
            expected_path = directory / str(tool["expected"])
            runs.append(
                {
                    "tool": tool_name,
                    "tool_path": str(tool["path"]),
                    "related_skills": list(tool["related_skills"]),
                    "mapping_basis": str(tool["mapping_basis"]),
                    "qualified_subcapability": str(tool["qualified_subcapability"]),
                    "example": directory.name,
                    "input_path": input_path.relative_to(source).as_posix(),
                    "input_sha256": digest(input_path.read_bytes()),
                    "expected_output_path": expected_path.relative_to(source).as_posix(),
                    "expected_output_sha256": digest(expected_path.read_bytes()),
                    "raw_stdout_path": (
                        f"{QUALIFICATION_EVIDENCE_DIRECTORY}/{tool_name}--"
                        f"{directory.name}.stdout.json"
                    ),
                    "raw_stderr_path": (
                        f"{QUALIFICATION_EVIDENCE_DIRECTORY}/{tool_name}--"
                        f"{directory.name}.stderr.txt"
                    ),
                }
            )
    return runs


def qualify_local(repository_root: Path = ROOT) -> dict[str, Any]:
    with mutation_lock(repository_root) as repository_root:
        extract_canonical_source(repository_root)
        summary = validate_source(repository_root)
        validate_qualification(repository_root, summary, required=False)
        return {
            "schema_version": "1.0",
            "package": PACKAGE_NAME,
            "package_version": PACKAGE_VERSION,
            "qualification_kind": "bounded-local-reference-tools",
            "status": "NOT_RUN",
            "reference_tool_state": "NOT_RUN",
            "skill_implementation_state": "DECLARED",
            "provider_runtime_evidence": "NOT_RUN",
            "external_evidence": "NOT_RUN",
            "production_certification": "NOT_CERTIFIED",
            "maximum_claim": "SOURCE_VALIDATED_NO_REFERENCE_TOOL_EXECUTION",
            "reason": (
                "local reference-tool execution is disabled because no supported "
                "default-deny filesystem-write and network sandbox is configured"
            ),
        }


def validate_qualification(
    repository_root: Path,
    summary: Mapping[str, Any],
    *,
    required: bool,
) -> None:
    """Reject persisted execution claims while no trusted sandbox exists."""

    del summary
    repository_root = resolved_repository_root(repository_root)
    receipt = assert_repository_path(
        repository_root,
        repository_root / DOC_RELATIVE / QUALIFICATION_NAME,
        "local reference-tool qualification",
    )
    evidence = assert_repository_path(
        repository_root,
        repository_root / DOC_RELATIVE / QUALIFICATION_EVIDENCE_DIRECTORY,
        "local reference-tool evidence",
    )
    if receipt.exists() or receipt.is_symlink() or evidence.exists() or evidence.is_symlink():
        fail(
            "persisted local reference-tool evidence is not accepted while "
            "sandboxed qualification execution is disabled"
        )
    if required:
        fail("local reference-tool qualification is disabled; state remains NOT_RUN")
    return None


def _validate_disabled_qualification_receipt(
    repository_root: Path,
    summary: Mapping[str, Any],
    *,
    required: bool,
) -> dict[str, Any] | None:
    repository_root = resolved_repository_root(repository_root)
    path = assert_repository_path(
        repository_root,
        repository_root / DOC_RELATIVE / QUALIFICATION_NAME,
        "local reference-tool qualification",
    )
    evidence_root = assert_repository_path(
        repository_root,
        repository_root / DOC_RELATIVE / QUALIFICATION_EVIDENCE_DIRECTORY,
        "local reference-tool evidence",
    )
    receipt_present = path.exists() or path.is_symlink()
    evidence_present = evidence_root.exists() or evidence_root.is_symlink()
    if not LOCAL_QUALIFICATION_EXECUTION_ENABLED:
        if receipt_present or evidence_present:
            fail(
                "persisted local reference-tool evidence is not accepted while "
                "sandboxed qualification execution is disabled"
            )
        if required:
            fail(
                "local reference-tool qualification is disabled; state remains NOT_RUN"
            )
        return None
    if not receipt_present:
        if required:
            fail(f"local reference-tool qualification is missing: {path}")
        return None
    if not path.is_file() or path.is_symlink():
        fail(f"local reference-tool qualification must be a regular file: {path}")
    receipt_bytes, receipt_mode = read_stable_regular_path(
        path,
        "local reference-tool qualification",
    )
    if receipt_mode != FILE_MODE:
        fail("local reference-tool qualification mode is unsafe")
    try:
        receipt = json.loads(receipt_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        fail(f"invalid local reference-tool qualification: {path}: {exc}")
    if not isinstance(receipt, dict):
        fail("local reference-tool qualification is not an object")
    required_values = {
        "schema_version": "1.0",
        "package": PACKAGE_NAME,
        "package_version": PACKAGE_VERSION,
        "qualification_kind": "bounded-local-reference-tools",
        "archive_path": ARCHIVE_RELATIVE.as_posix(),
        "archive_sha256": f"sha256:{EXPECTED_ARCHIVE_SHA256}",
        "source_path": SOURCE_RELATIVE.as_posix(),
        "source_tree_sha256": summary["source_tree_sha256"],
        "status": "PASS",
        "reference_tool_state": "LOCAL_EXECUTED_SELF_ATTESTED",
        "self_attested": True,
        "independent_verifier": False,
        "signature_status": "ABSENT",
        "skill_implementation_state": "DECLARED",
        "provider_runtime_evidence": "NOT_RUN",
        "external_evidence": "NOT_RUN",
        "production_certification": "NOT_CERTIFIED",
        "maximum_claim": "BOUNDED_REFERENCE_TOOLS_LOCAL_EXECUTED_SELF_ATTESTED",
    }
    receipt_keys = set(required_values) | {
        "observed_at",
        "qualification_driver_path",
        "qualification_driver_sha256",
        "python",
        "execution_environment",
        "raw_evidence_tree_sha256",
        "runs",
    }
    if set(receipt) != receipt_keys:
        fail(
            "local qualification fields are not exact: "
            f"missing={sorted(receipt_keys - set(receipt))} "
            f"extra={sorted(set(receipt) - receipt_keys)}"
        )
    for key, expected in required_values.items():
        if receipt.get(key) != expected:
            fail(f"local qualification field is invalid: {key}")
    observed_at = receipt.get("observed_at")
    try:
        parsed = datetime.fromisoformat(str(observed_at))
    except ValueError as exc:
        fail(f"local qualification observed_at is invalid: {exc}")
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        fail("local qualification observed_at must be UTC")
    driver_path = receipt.get("qualification_driver_path")
    if driver_path != "tooling/integrate_database_bigdata_skills.py":
        fail("local qualification driver path is invalid")
    driver_digest = receipt.get("qualification_driver_sha256")
    driver_file = assert_repository_path(
        repository_root,
        repository_root / str(driver_path),
        "local qualification driver",
    )
    driver_bytes, _ = read_stable_regular_path(driver_file, "local qualification driver")
    actual_driver_digest = digest(driver_bytes)
    if driver_digest != actual_driver_digest:
        fail("local qualification driver digest drifted")
    python_info = receipt.get("python")
    if not isinstance(python_info, dict) or set(python_info) != {
        "implementation",
        "version",
        "resolved_executable",
        "executable_bytes",
        "executable_sha256",
    }:
        fail("local qualification Python identity is invalid")
    if (
        not isinstance(python_info.get("implementation"), str)
        or not python_info["implementation"]
        or not isinstance(python_info.get("version"), str)
        or not python_info["version"]
        or not isinstance(python_info.get("resolved_executable"), str)
        or not Path(python_info["resolved_executable"]).is_absolute()
        or not isinstance(python_info.get("executable_bytes"), int)
        or python_info["executable_bytes"] <= 0
        or re.fullmatch(r"sha256:[0-9a-f]{64}", str(python_info.get("executable_sha256")))
        is None
    ):
        fail("local qualification Python evidence is invalid")
    recorded_executable = Path(str(python_info["resolved_executable"]))
    try:
        current_executable = Path(sys.executable).resolve(strict=True)
        recorded_resolved = recorded_executable.resolve(strict=True)
    except OSError as exc:
        fail(f"local qualification Python executable cannot be resolved: {exc}")
    if (
        recorded_resolved != current_executable
        or recorded_executable != recorded_resolved
        or not recorded_resolved.is_file()
        or recorded_resolved.is_symlink()
        or python_info["implementation"] != platform.python_implementation()
        or python_info["version"] != platform.python_version()
        or python_info["executable_bytes"] != recorded_resolved.stat().st_size
        or python_info["executable_sha256"]
        != "sha256:" + sha256_file(recorded_resolved)
    ):
        fail("local qualification Python executable or runtime drifted")
    expected_environment: dict[str, str] = {}
    if receipt.get("execution_environment") != expected_environment:
        fail("local qualification execution environment is invalid")

    expected_runs = expected_reference_runs(summary)
    actual_runs = receipt.get("runs")
    if not isinstance(actual_runs, list) or len(actual_runs) != len(expected_runs):
        fail("local qualification run inventory is invalid")
    last_finished: datetime | None = None
    for expected, actual in zip(expected_runs, actual_runs):
        if not isinstance(actual, dict):
            fail("local qualification run is not an object")
        run_keys = set(expected) | {
            "argv",
            "cwd",
            "started_at",
            "finished_at",
            "duration_ms",
            "exit_code",
            "stdout_bytes",
            "stdout_sha256",
            "stderr_bytes",
            "stderr_sha256",
            "semantic_match",
            "status",
        }
        if set(actual) != run_keys:
            fail(
                f"local qualification run fields are not exact: {expected['tool']}: "
                f"missing={sorted(run_keys - set(actual))} "
                f"extra={sorted(set(actual) - run_keys)}"
            )
        for key, value in expected.items():
            if actual.get(key) != value:
                fail(f"local qualification run field drifted: {expected['tool']}: {key}")
        expected_argv = [
            python_info["resolved_executable"],
            "-I",
            "-B",
            "-X",
            "utf8",
            expected["tool_path"],
            expected["input_path"],
        ]
        if actual.get("argv") != expected_argv:
            fail(f"local qualification argv drifted: {expected['tool']}")
        if actual.get("cwd") != SOURCE_RELATIVE.as_posix():
            fail(f"local qualification cwd drifted: {expected['tool']}")
        if (
            actual.get("exit_code") != 0
            or actual.get("semantic_match") is not True
            or actual.get("status") != "PASS"
        ):
            fail(f"local qualification run is not PASS: {expected['tool']}")
        parsed_times: dict[str, datetime] = {}
        for time_field in ("started_at", "finished_at"):
            try:
                value = datetime.fromisoformat(str(actual.get(time_field)))
            except ValueError as exc:
                fail(f"local qualification {time_field} is invalid: {expected['tool']}: {exc}")
            if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
                fail(f"local qualification {time_field} is not UTC: {expected['tool']}")
            parsed_times[time_field] = value
        if parsed_times["finished_at"] < parsed_times["started_at"]:
            fail(f"local qualification timestamps are reversed: {expected['tool']}")
        if last_finished is not None and parsed_times["started_at"] < last_finished:
            fail(f"local qualification runs overlap or are reordered: {expected['tool']}")
        last_finished = parsed_times["finished_at"]
        if not isinstance(actual.get("duration_ms"), int) or actual["duration_ms"] < 0:
            fail(f"local qualification duration is invalid: {expected['tool']}")
        for field in ("stdout_sha256", "stderr_sha256"):
            value = actual.get(field)
            if not isinstance(value, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
                fail(f"local qualification run has invalid {field}: {expected['tool']}")
        if actual["stdout_sha256"] != expected["expected_output_sha256"]:
            fail(f"local qualification stdout is not byte-bound: {expected['tool']}")
        if actual["stderr_sha256"] != digest(b""):
            fail(f"local qualification stderr is not empty: {expected['tool']}")
        stdout_path = repository_root / DOC_RELATIVE / str(expected["raw_stdout_path"])
        stderr_path = repository_root / DOC_RELATIVE / str(expected["raw_stderr_path"])
        for raw_path, label in ((stdout_path, "stdout"), (stderr_path, "stderr")):
            assert_repository_path(repository_root, raw_path, f"raw {label}")
            if not raw_path.is_file() or raw_path.is_symlink():
                fail(f"local qualification raw {label} is missing: {raw_path}")
            assert_inside(repository_root / DOC_RELATIVE, raw_path, f"raw {label}")
        stdout_bytes, stdout_mode = read_stable_regular_path(stdout_path, "raw stdout")
        stderr_bytes, stderr_mode = read_stable_regular_path(stderr_path, "raw stderr")
        if stdout_mode != FILE_MODE or stderr_mode != FILE_MODE:
            fail(f"local qualification raw evidence mode is unsafe: {expected['tool']}")
        if (
            actual.get("stdout_bytes") != len(stdout_bytes)
            or actual["stdout_sha256"] != digest(stdout_bytes)
            or stdout_bytes != (Path(summary["source"]) / expected["expected_output_path"]).read_bytes()
        ):
            fail(f"local qualification raw stdout drifted: {expected['tool']}")
        if (
            actual.get("stderr_bytes") != len(stderr_bytes)
            or actual["stderr_sha256"] != digest(stderr_bytes)
            or stderr_bytes
        ):
            fail(f"local qualification raw stderr drifted: {expected['tool']}")
    if last_finished is not None and parsed < last_finished:
        fail("local qualification observed_at predates the final run")
    if not evidence_root.is_dir() or evidence_root.is_symlink():
        fail("local qualification evidence directory is missing or unsafe")
    evidence_files, evidence_directories = read_tree_details(
        evidence_root,
        "local qualification evidence",
    )
    actual_evidence = {
        f"{QUALIFICATION_EVIDENCE_DIRECTORY}/{relative}": content
        for relative, content in evidence_files.items()
    }
    expected_evidence_paths = {
        str(item[key])
        for item in expected_runs
        for key in ("raw_stdout_path", "raw_stderr_path")
    }
    if set(actual_evidence) != expected_evidence_paths:
        fail("local qualification raw evidence inventory is not exact")
    expected_evidence_directories = {
        parent.as_posix()
        for relative in expected_evidence_paths
        for parent in PurePosixPath(relative).relative_to(
            QUALIFICATION_EVIDENCE_DIRECTORY
        ).parents
        if parent.as_posix() not in {"", "."}
    }
    if evidence_directories != expected_evidence_directories:
        fail("local qualification raw evidence directory inventory is not exact")
    if receipt.get("raw_evidence_tree_sha256") != tree_digest({"evidence": actual_evidence}):
        fail("local qualification raw evidence tree digest drifted")
    return receipt


def render_skill(skill: Mapping[str, Any]) -> bytes:
    name = str(skill["name"])
    description = (
        f"Use for ELMOS database or Big Data work covered by {name}. "
        f"Source purpose: {skill['description']} Preserve exact data, tenant, runtime, "
        "and evidence boundaries; catalog entries and generated plans are not production proof."
    )
    metadata_lines = [
        "metadata:",
        f"  source_package: {skill_creator_tools.yaml_quote(PACKAGE_NAME)}",
        f"  source_version: {skill_creator_tools.yaml_quote(PACKAGE_VERSION)}",
        f"  source_path: {skill_creator_tools.yaml_quote((SOURCE_RELATIVE / str(skill['source_path'])).as_posix())}",
        f"  source_sha256: {skill_creator_tools.yaml_quote(str(skill['source_sha256']))}",
        f"  source_group: {skill_creator_tools.yaml_quote(str(skill['group']))}",
        f"  normalized_namespace: {skill_creator_tools.yaml_quote(NAMESPACE)}",
        '  installation_state: "INSTALLED"',
        '  skill_implementation_state: "DECLARED"',
        '  reference_tool_state: "NOT_APPLICABLE_TO_WHOLE_SKILL"',
        '  provider_runtime_evidence: "NOT_RUN"',
        '  external_evidence_status: "NOT_RUN"',
        '  production_certification: "NOT_CERTIFIED"',
    ]
    frontmatter = "\n".join(
        [
            "---",
            f"name: {name}",
            f"description: {skill_creator_tools.yaml_quote(description)}",
            *metadata_lines,
            "---",
            "",
        ]
    )
    dependencies = json.dumps(skill["dependencies"], ensure_ascii=False)
    triggers = json.dumps(skill["triggers"], ensure_ascii=False)
    outputs = json.dumps(skill["outputs"], ensure_ascii=False)
    boundary_lines = [
        "",
        "## Repository Integration Boundary",
        "",
        f"- Provenance is pinned to `{PACKAGE_NAME}` `{PACKAGE_VERSION}`, source `{(SOURCE_RELATIVE / str(skill['source_path'])).as_posix()}`, and `{skill['source_sha256']}`.",
        f"- Source group: `{skill['group']}`. Dependencies: `{dependencies}`. Triggers: `{triggers}`. Declared outputs: `{outputs}`.",
        "- This normalized Skill is installed and invocable, but its implementation state remains `DECLARED`; the package contains no per-Skill runtime handler, provider adapter, or project-generation assets.",
        "- The source archive has no license, signature, SBOM, or provenance attestation. Its pinned digest proves byte identity only, not publisher identity, legal approval, or supply-chain certification.",
        "- All 29 technology entries are `catalog-only`. A catalog match, heuristic score, reference plan, or generated file is not proof of provider integration, engine behavior, performance, recovery, security, or production readiness.",
        "- Unknown requirements remain unknown; hard constraints must not be relaxed silently. Exact engine/provider/version/edition/region/runtime identities and representative evidence are required before a concrete recommendation or release claim.",
        "- Tenant, authorization, data residency, secrets, production writes, infrastructure changes, deployments, and destructive operations require their own explicit scope and least-privileged workflow.",
        "- Package-level reference-tool qualification, when present, is self-attested local engineering evidence for deterministic outputs from three checked-in synthetic examples. It does not change this whole-Skill state. Provider/runtime and external evidence remain `NOT_RUN`; production certification remains `NOT_CERTIFIED`.",
        "- Database migration or data-platform certification remains subject to the applicable Batch 31 implementation contract and conservative gate; static Skill/package validation cannot raise that status.",
    ]
    return (frontmatter + str(skill["body"]).rstrip() + "\n" + "\n".join(boundary_lines) + "\n").encode("utf-8")


def render_interface(name: str) -> bytes:
    display = skill_creator_tools.format_display_name(name).replace("Elmos", "ELMOS")
    short = "Run this database and Big Data Skill with evidence controls"
    prompt = (
        f"Use ${name} with the pinned ELMOS database and Big Data contracts; "
        "keep catalog and runtime evidence distinct and fail closed on unknowns."
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


def tree_digest(trees: Mapping[str, Mapping[str, bytes]]) -> str:
    value = hashlib.sha256()
    value.update(b"elmos-tree-digest-v2\0")

    def update_framed(content: bytes) -> None:
        value.update(len(content).to_bytes(8, "big"))
        value.update(content)

    value.update(len(trees).to_bytes(8, "big"))
    for name in sorted(trees):
        update_framed(name.encode("utf-8"))
        value.update(len(trees[name]).to_bytes(8, "big"))
        for relative in sorted(trees[name]):
            update_framed(relative.encode("utf-8"))
            update_framed(trees[name][relative])
    return "sha256:" + value.hexdigest()


def render_readme(qualification: Mapping[str, Any] | None) -> bytes:
    reference_state = "LOCAL_EXECUTED_SELF_ATTESTED" if qualification else "NOT_RUN"
    return f"""# Database and Big Data Skills Integration

This directory records the repository integration of `{PACKAGE_NAME}` version `{PACKAGE_VERSION}`.

- Trusted source archive: `{ARCHIVE_RELATIVE.as_posix()}` (`sha256:{EXPECTED_ARCHIVE_SHA256}`)
- Immutable extracted source: `{SOURCE_RELATIVE.as_posix()}/`
- Installed Skills: {EXPECTED_SKILLS} exact names under both `agent-skills/runtime/` and `.agents/skills/`
- Source profiles / schemas / technologies: {EXPECTED_PROFILES} / {EXPECTED_SCHEMAS} / {EXPECTED_TECHNOLOGIES}
- Skill implementation state: `DECLARED`
- Bounded reference-tool state: `{reference_state}`
- Provider/runtime and external evidence: `NOT_RUN`
- Production certification: `NOT_CERTIFIED`
- Source license / signature / SBOM / provenance attestation: `ABSENT`

The importer does not execute the source package installer, validator, or manifest builder. It independently pins the ZIP, compares every extracted byte, verifies exact checksum coverage, validates the 46-Skill DAG and 554 stable task IDs, checks profiles/catalogs/Schemas/examples, and generates Codex-compatible interfaces with provenance.

The source package includes three deterministic reference tools, but no per-Skill handlers, provider adapters, infrastructure templates, or generated-project assets. Local qualification of those three helpers against the three synthetic examples is self-attested engineering evidence only; it does not implement a whole Skill or validate any database, connector, engine, cloud, deployment, migration, benchmark, recovery path, or customer workload.

Run the repository-owned checks with:

```sh
make database-bigdata-skills
```
""".encode("utf-8")


def build_expected(repository_root: Path = ROOT) -> dict[str, Any]:
    repository_root = resolved_repository_root(repository_root)
    summary = validate_source(repository_root)
    qualification = validate_qualification(repository_root, summary, required=False)
    trees: dict[str, dict[str, bytes]] = {}
    records: list[dict[str, Any]] = []
    for skill in summary["skills"]:
        name = str(skill["name"])
        tree = {
            "SKILL.md": render_skill(skill),
            "agents/openai.yaml": render_interface(name),
        }
        trees[name] = tree
        related_tools = [
            item["name"]
            for item in summary["reference_tools"]
            if name in item["related_skills"]
        ]
        records.append(
            {
                "name": name,
                "source_group": skill["group"],
                "source_dependencies": skill["dependencies"],
                "source_path": (SOURCE_RELATIVE / str(skill["source_path"])).as_posix(),
                "source_sha256": skill["source_sha256"],
                "source_tree_sha256": skill["source_tree_sha256"],
                "runtime_skill_path": (RUNTIME_RELATIVE / name / "SKILL.md").as_posix(),
                "runtime_skill_sha256": digest(tree["SKILL.md"]),
                "runtime_interface_path": (RUNTIME_RELATIVE / name / "agents/openai.yaml").as_posix(),
                "runtime_interface_sha256": digest(tree["agents/openai.yaml"]),
                "workspace_skill_path": (WORKSPACE_RELATIVE / name / "SKILL.md").as_posix(),
                "workspace_skill_sha256": digest(tree["SKILL.md"]),
                "workspace_interface_path": (WORKSPACE_RELATIVE / name / "agents/openai.yaml").as_posix(),
                "workspace_interface_sha256": digest(tree["agents/openai.yaml"]),
                "installed_tree_sha256": tree_digest({name: tree}),
                "installation_state": "INSTALLED",
                "skill_implementation_state": "DECLARED",
                "related_reference_tools": related_tools,
                "reference_tool_mapping_basis": (
                    "repository-inference" if related_tools else "NOT_APPLICABLE"
                ),
                "reference_tool_state": "NOT_APPLICABLE_TO_WHOLE_SKILL",
                "provider_runtime_evidence": "NOT_RUN",
                "external_evidence_status": "NOT_RUN",
                "production_certification": "NOT_CERTIFIED",
            }
        )

    readme_bytes = render_readme(qualification)
    qualification_path = repository_root / DOC_RELATIVE / QUALIFICATION_NAME
    qualification_bytes = qualification_path.read_bytes() if qualification else None
    qualification_files: dict[str, bytes] = {}
    if qualification_bytes is not None:
        qualification_files[QUALIFICATION_NAME] = qualification_bytes
        for run in expected_reference_runs(summary):
            for key in ("raw_stdout_path", "raw_stderr_path"):
                relative = str(run[key])
                qualification_files[relative] = (repository_root / DOC_RELATIVE / relative).read_bytes()
    source_inventory = [
        {**item, "path": (SOURCE_RELATIVE / str(item["path"])).as_posix()}
        for item in summary["inventory"]
    ]
    manifest = {
        "schema_version": "1.0",
        "namespace": NAMESPACE,
        "source_package": PACKAGE_NAME,
        "source_version": PACKAGE_VERSION,
        "source_archive_path": ARCHIVE_RELATIVE.as_posix(),
        "source_archive_bytes": EXPECTED_ARCHIVE_BYTES,
        "source_archive_sha256": f"sha256:{EXPECTED_ARCHIVE_SHA256}",
        "canonical_source_path": SOURCE_RELATIVE.as_posix(),
        "canonical_source_file_count": EXPECTED_SOURCE_FILES,
        "canonical_source_tree_sha256": summary["source_tree_sha256"],
        "canonical_manifest_sha256": f"sha256:{EXPECTED_MANIFEST_SHA256}",
        "source_license_status": "ABSENT",
        "source_signature_status": "ABSENT",
        "source_sbom_status": "ABSENT",
        "source_provenance_attestation_status": "ABSENT",
        "source_checksum_entry_count": EXPECTED_CHECKSUM_ENTRIES,
        "source_checksum_coverage_exact": True,
        "source_files": source_inventory,
        "skill_count": EXPECTED_SKILLS,
        "profile_count": EXPECTED_PROFILES,
        "schema_count": EXPECTED_SCHEMAS,
        "technology_catalog_count": EXPECTED_TECHNOLOGIES,
        "technology_catalog_state": "CATALOG_ONLY",
        "adapter_blueprint_count": EXPECTED_ADAPTER_BLUEPRINTS,
        "provider_adapter_implementation_count": 0,
        "stable_task_id_count": EXPECTED_TASK_IDS,
        "runtime_root": RUNTIME_RELATIVE.as_posix(),
        "workspace_root": WORKSPACE_RELATIVE.as_posix(),
        "runtime_tree_sha256": tree_digest(trees),
        "workspace_tree_sha256": tree_digest(trees),
        "dual_root_byte_identical": True,
        "integration_readme_path": (DOC_RELATIVE / README_NAME).as_posix(),
        "integration_readme_sha256": digest(readme_bytes),
        "local_qualification_path": (
            (DOC_RELATIVE / QUALIFICATION_NAME).as_posix() if qualification else None
        ),
        "local_qualification_sha256": (
            digest(qualification_bytes) if qualification_bytes is not None else None
        ),
        "reference_tools": [
            {
                **item,
                "qualification_state": (
                    "LOCAL_EXECUTED_SELF_ATTESTED" if qualification else "NOT_RUN"
                ),
                "whole_skill_implementation_effect": "NONE",
            }
            for item in summary["reference_tools"]
        ],
        "reference_tool_state": (
            "LOCAL_EXECUTED_SELF_ATTESTED" if qualification else "NOT_RUN"
        ),
        "skill_implementation_state": "DECLARED",
        "provider_runtime_evidence": "NOT_RUN",
        "external_evidence_status": "NOT_RUN",
        "production_certification": "NOT_CERTIFIED",
        "maximum_local_claim": (
            "STRUCTURAL_SKILLS_INSTALLED_WITH_SELF_ATTESTED_REFERENCE_TOOL_EXECUTION"
            if qualification
            else "STRUCTURAL_SKILLS_INSTALLED"
        ),
        "skills": records,
        "profiles": summary["profiles"],
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return {
        "summary": summary,
        "qualification": qualification,
        "trees": trees,
        "readme_bytes": readme_bytes,
        "manifest": manifest,
        "manifest_bytes": manifest_bytes,
        "qualification_bytes": qualification_bytes,
        "qualification_files": qualification_files,
    }


def read_tree_details(
    root: Path,
    label: str = "installed tree",
) -> tuple[dict[str, bytes], set[str]]:
    try:
        root_metadata = root.lstat()
    except OSError as exc:
        fail(f"{label} is missing or unreadable: {root}: {exc}")
    if not stat.S_ISDIR(root_metadata.st_mode) or stat.S_ISLNK(root_metadata.st_mode):
        fail(f"{label} is missing or not a real directory: {root}")
    if stat.S_IMODE(root_metadata.st_mode) != DIRECTORY_MODE:
        fail(
            f"{label} directory mode is unsafe: {root}: "
            f"expected={DIRECTORY_MODE:04o} "
            f"actual={stat.S_IMODE(root_metadata.st_mode):04o}"
        )
    values: dict[str, bytes] = {}
    directories: set[str] = set()
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        try:
            metadata = path.lstat()
        except OSError as exc:
            fail(f"cannot inspect {label} entry {path}: {exc}")
        relative = path.relative_to(root).as_posix()
        if stat.S_ISLNK(metadata.st_mode):
            fail(f"{label} may not contain symbolic links: {path}")
        if stat.S_ISREG(metadata.st_mode):
            assert_inside(root, path, f"{label} file")
            content, file_mode = read_stable_regular_path(path, f"{label} file")
            if file_mode != FILE_MODE:
                fail(
                    f"{label} file mode is unsafe: {path}: "
                    f"expected={FILE_MODE:04o} actual={file_mode:04o}"
                )
            values[relative] = content
        elif stat.S_ISDIR(metadata.st_mode):
            directory_mode = stat.S_IMODE(metadata.st_mode)
            if directory_mode != DIRECTORY_MODE:
                fail(
                    f"{label} directory mode is unsafe: {path}: "
                    f"expected={DIRECTORY_MODE:04o} actual={directory_mode:04o}"
                )
            directories.add(relative)
        else:
            fail(f"{label} contains an unsupported special entry: {path}")
    return values, directories


def read_tree(root: Path) -> dict[str, bytes]:
    return read_tree_details(root)[0]


def validate_normalized_skills(repository_root: Path, expected: Mapping[str, Any]) -> None:
    for relative_root in (RUNTIME_RELATIVE, WORKSPACE_RELATIVE):
        for name in sorted(expected["trees"]):
            ok, message = skill_creator_tools.validate_skill(
                repository_root / relative_root / name
            )
            if not ok:
                fail(f"normalized Skill is invalid: {relative_root}/{name}: {message}")


def check_install(repository_root: Path = ROOT) -> dict[str, Any]:
    repository_root = resolved_repository_root(repository_root)
    expected = build_expected(repository_root)
    failures: list[str] = []
    for relative_root, label in (
        (RUNTIME_RELATIVE, "runtime"),
        (WORKSPACE_RELATIVE, "workspace"),
    ):
        root = assert_repository_path(
            repository_root,
            repository_root / relative_root,
            f"{label} Skill root",
        )
        for name, expected_tree in expected["trees"].items():
            destination = assert_repository_path(
                repository_root,
                root / name,
                f"{label} Skill",
            )
            try:
                actual_tree = read_tree(destination)
            except IntegrationError as exc:
                failures.append(f"{label}:{name}:{exc}")
                continue
            if actual_tree != expected_tree:
                missing = sorted(set(expected_tree) - set(actual_tree))
                extra = sorted(set(actual_tree) - set(expected_tree))
                changed = sorted(
                    path
                    for path in set(actual_tree) & set(expected_tree)
                    if actual_tree[path] != expected_tree[path]
                )
                failures.append(
                    f"{label}:{name}:missing={missing}:extra={extra}:changed={changed}"
                )

    doc_root = assert_repository_path(
        repository_root,
        repository_root / DOC_RELATIVE,
        "integration documentation",
    )
    expected_docs = {
        README_NAME: expected["readme_bytes"],
        INSTALL_MANIFEST_NAME: expected["manifest_bytes"],
    }
    expected_docs.update(expected["qualification_files"])
    if not doc_root.is_dir() or doc_root.is_symlink():
        failures.append("docs-root")
    else:
        try:
            actual_doc_files, actual_doc_dirs = read_tree_details(
                doc_root,
                "integration documentation",
            )
        except IntegrationError as exc:
            failures.append(f"docs-tree:{exc}")
            actual_doc_files = {}
            actual_doc_dirs = set()
        expected_doc_dirs = {
            parent.as_posix()
            for relative in expected_docs
            for parent in PurePosixPath(relative).parents
            if parent.as_posix() not in {"", "."}
        }
        if actual_doc_dirs != expected_doc_dirs:
            failures.append(
                f"docs-dirs:missing={sorted(expected_doc_dirs - actual_doc_dirs)}:"
                f"extra={sorted(actual_doc_dirs - expected_doc_dirs)}"
            )
        if actual_doc_files != expected_docs:
            missing = sorted(set(expected_docs) - set(actual_doc_files))
            extra = sorted(set(actual_doc_files) - set(expected_docs))
            changed = sorted(
                path
                for path in set(actual_doc_files) & set(expected_docs)
                if actual_doc_files[path] != expected_docs[path]
            )
            failures.append(f"docs:missing={missing}:extra={extra}:changed={changed}")
    if failures:
        fail(f"database/Big Data Skill installation drifted: {failures[:12]}")
    validate_normalized_skills(repository_root, expected)
    return expected


def load_previous_install(
    repository_root: Path,
    expected: Mapping[str, Any],
) -> dict[str, Any] | None:
    repository_root = resolved_repository_root(repository_root)
    manifest_path = assert_repository_path(
        repository_root,
        repository_root / DOC_RELATIVE / INSTALL_MANIFEST_NAME,
        "installed manifest",
    )
    if not (manifest_path.exists() or manifest_path.is_symlink()):
        return None
    if not manifest_path.is_file() or manifest_path.is_symlink():
        fail(f"installed manifest is not a regular file: {manifest_path}")
    manifest_bytes, manifest_mode = read_stable_regular_path(
        manifest_path,
        "previous installed manifest",
    )
    if manifest_mode != FILE_MODE:
        fail("previous installed manifest mode is unsafe")
    try:
        previous = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        fail(f"invalid previous installed manifest: {manifest_path}: {exc}")
    if not isinstance(previous, dict):
        fail("previous installed manifest is not an object")
    if previous != expected["manifest"] or manifest_bytes != expected["manifest_bytes"]:
        fail(
            "refusing to grant ownership from a manifest that is not the exact "
            "independently rendered installation manifest"
        )
    return previous


def validate_previous_owned_trees(
    repository_root: Path,
    previous: Mapping[str, Any],
    aliases: set[str],
) -> None:
    records = {
        item["name"]: item
        for item in previous["skills"]
        if isinstance(item, dict) and item.get("name") in aliases
    }
    for relative_root, label, skill_digest_key, interface_digest_key in (
        (
            RUNTIME_RELATIVE,
            "runtime",
            "runtime_skill_sha256",
            "runtime_interface_sha256",
        ),
        (
            WORKSPACE_RELATIVE,
            "workspace",
            "workspace_skill_sha256",
            "workspace_interface_sha256",
        ),
    ):
        for name in sorted(aliases):
            destination = assert_repository_path(
                repository_root,
                repository_root / relative_root / name,
                f"previous owned {label} Skill",
            )
            actual = read_tree(destination)
            if set(actual) != {"SKILL.md", "agents/openai.yaml"}:
                fail(f"previous owned {label} Skill file set drifted: {name}")
            record = records[name]
            if digest(actual["SKILL.md"]) != record.get(skill_digest_key):
                fail(f"previous owned {label} Skill content drifted: {name}")
            if digest(actual["agents/openai.yaml"]) != record.get(interface_digest_key):
                fail(f"previous owned {label} interface drifted: {name}")
            if tree_digest({name: actual}) != record.get("installed_tree_sha256"):
                fail(f"previous owned {label} Skill tree digest drifted: {name}")

    readme = assert_repository_path(
        repository_root,
        repository_root / DOC_RELATIVE / README_NAME,
        "previous owned integration README",
    )
    if not readme.is_file() or readme.is_symlink():
        fail("previous owned integration README drifted")
    readme_bytes, readme_mode = read_stable_regular_path(
        readme,
        "previous owned integration README",
    )
    if readme_mode != FILE_MODE or digest(readme_bytes) != previous.get(
        "integration_readme_sha256"
    ):
        fail("previous owned integration README drifted")


def write_tree(destination: Path, values: Mapping[str, bytes]) -> None:
    destination.mkdir(parents=True, mode=DIRECTORY_MODE, exist_ok=False)
    destination.chmod(DIRECTORY_MODE)
    for relative, content in sorted(values.items()):
        validate_relative_path(relative, "installed")
        path = destination / relative
        path.parent.mkdir(parents=True, mode=DIRECTORY_MODE, exist_ok=True)
        current = path.parent
        while current != destination.parent:
            current.chmod(DIRECTORY_MODE)
            if current == destination:
                break
            current = current.parent
        path.write_bytes(content)
        path.chmod(FILE_MODE)


def write_install(repository_root: Path = ROOT) -> dict[str, Any]:
    with mutation_lock(repository_root) as repository_root:
        extract_canonical_source(repository_root)
        expected = build_expected(repository_root)
        aliases = set(expected["trees"])
        previous = load_previous_install(repository_root, expected)
        owned = aliases if previous is not None else set()
        if previous is not None:
            validate_previous_owned_trees(repository_root, previous, aliases)

        doc_root = assert_repository_path(
            repository_root,
            repository_root / DOC_RELATIVE,
            "integration documentation",
        )
        allowed_existing_docs = set(expected["qualification_files"])
        if owned:
            allowed_existing_docs.update({README_NAME, INSTALL_MANIFEST_NAME})
        if doc_root.exists() or doc_root.is_symlink():
            if not doc_root.is_dir() or doc_root.is_symlink():
                fail(f"refusing to overwrite a non-directory documentation path: {doc_root}")
            existing_docs, existing_doc_dirs = read_tree_details(
                doc_root,
                "existing integration documentation",
            )
            allowed_doc_dirs = {
                parent.as_posix()
                for relative in allowed_existing_docs
                for parent in PurePosixPath(relative).parents
                if parent.as_posix() not in {"", "."}
            }
            if not set(existing_docs).issubset(allowed_existing_docs):
                fail(
                    "refusing to overwrite unowned documentation: "
                    f"{sorted(set(existing_docs) - allowed_existing_docs)}"
                )
            if not existing_doc_dirs.issubset(allowed_doc_dirs):
                fail(
                    "refusing to preserve unowned documentation directories: "
                    f"{sorted(existing_doc_dirs - allowed_doc_dirs)}"
                )

        for relative_root, label in (
            (RUNTIME_RELATIVE, "runtime"),
            (WORKSPACE_RELATIVE, "workspace"),
        ):
            install_root = assert_repository_path(
                repository_root,
                repository_root / relative_root,
                f"{label} Skill root",
            )
            for name in sorted(aliases):
                destination = assert_repository_path(
                    repository_root,
                    install_root / name,
                    f"{label} Skill",
                )
                if destination.exists() or destination.is_symlink():
                    if name not in owned:
                        fail(f"refusing to overwrite unowned {label} Skill: {destination}")
                    if destination.is_symlink() or not destination.is_dir():
                        fail(f"owned {label} Skill is not a real directory: {destination}")

        staged: list[dict[str, Any]] = []
        operations: list[dict[str, Any]] = []

        def present(path: Path) -> bool:
            return path.exists() or path.is_symlink()

        def read_operation_value(operation: Mapping[str, Any], path: Path) -> bytes | dict[str, bytes]:
            if operation["is_directory"]:
                return read_tree(path)
            content, mode = read_stable_regular_path(path, "installed documentation")
            if mode != FILE_MODE:
                fail(f"installed documentation mode is unsafe: {path}")
            return content

        try:
            for relative_root in (RUNTIME_RELATIVE, WORKSPACE_RELATIVE):
                install_root = assert_repository_path(
                    repository_root,
                    repository_root / relative_root,
                    "Skill installation root",
                )
                install_root.mkdir(parents=True, mode=DIRECTORY_MODE, exist_ok=True)
                assert_repository_path(repository_root, install_root, "Skill installation root")
                for name in sorted(aliases):
                    destination = assert_repository_path(
                        repository_root,
                        install_root / name,
                        "Skill destination",
                    )
                    stage = assert_repository_path(
                        repository_root,
                        install_root / f".{name}.stage.{uuid.uuid4().hex}",
                        "Skill staging",
                    )
                    staged_item = {
                        "destination": destination,
                        "stage": stage,
                        "is_directory": True,
                        "had_previous": name in owned,
                        "old_value": expected["trees"][name] if name in owned else None,
                        "new_value": expected["trees"][name],
                    }
                    staged.append(staged_item)
                    write_tree(stage, expected["trees"][name])
                    if read_tree(stage) != expected["trees"][name]:
                        fail(f"staged Skill bytes differ before install: {destination}")

            doc_root.mkdir(parents=True, mode=DIRECTORY_MODE, exist_ok=True)
            doc_root.chmod(DIRECTORY_MODE)
            assert_repository_path(repository_root, doc_root, "integration documentation")
            for filename, content in (
                (README_NAME, expected["readme_bytes"]),
                (INSTALL_MANIFEST_NAME, expected["manifest_bytes"]),
            ):
                destination = assert_repository_path(
                    repository_root,
                    doc_root / filename,
                    "documentation destination",
                )
                stage = assert_repository_path(
                    repository_root,
                    doc_root.parent
                    / f".database-bigdata-{filename}.stage.{uuid.uuid4().hex}",
                    "documentation staging",
                )
                staged_item = {
                    "destination": destination,
                    "stage": stage,
                    "is_directory": False,
                    "had_previous": previous is not None,
                    "old_value": content if previous is not None else None,
                    "new_value": content,
                }
                staged.append(staged_item)
                stage.write_bytes(content)
                stage.chmod(FILE_MODE)
                staged_content, staged_mode = read_stable_regular_path(
                    stage,
                    "staged documentation",
                )
                if staged_content != content or staged_mode != FILE_MODE:
                    fail(f"staged documentation differs before install: {destination}")

            for item in staged:
                destination = item["destination"]
                stage = item["stage"]
                assert_repository_path(repository_root, destination, "install destination")
                assert_repository_path(repository_root, stage, "install staging")
                if present(destination) != item["had_previous"]:
                    fail(f"install destination changed after preflight: {destination}")
                if item["had_previous"] and read_operation_value(item, destination) != item["old_value"]:
                    fail(f"owned install destination drifted before commit: {destination}")
                backup_parent = (
                    doc_root.parent
                    if destination.parent == doc_root
                    else destination.parent
                )
                backup = assert_repository_path(
                    repository_root,
                    backup_parent
                    / f".database-bigdata-{destination.name}.backup.{uuid.uuid4().hex}",
                    "install backup",
                )
                operation = {**item, "backup": backup, "backed_up": False, "published": False}
                operations.append(operation)
                if item["had_previous"]:
                    os.replace(destination, backup)
                    operation["backed_up"] = True
                    if read_operation_value(operation, backup) != item["old_value"]:
                        fail(f"install backup drifted during commit: {destination}")
                os.replace(stage, destination)
                operation["published"] = True
                if read_operation_value(operation, destination) != item["new_value"]:
                    fail(f"installed bytes drifted during commit: {destination}")

            checked = check_install(repository_root)
        except BaseException as exc:
            rollback_failures: list[str] = []
            discarded: list[Path] = []
            for operation in reversed(operations):
                destination = operation["destination"]
                backup = operation["backup"]
                try:
                    old_destination_is_intact = False
                    if present(destination):
                        current_value = read_operation_value(operation, destination)
                        backup_present = present(backup)
                        if (
                            operation["had_previous"]
                            and not backup_present
                            and current_value == operation["old_value"]
                        ):
                            old_destination_is_intact = True
                        elif current_value != operation["new_value"]:
                            fail(f"published destination drifted before rollback: {destination}")
                        else:
                            discard = assert_repository_path(
                                repository_root,
                                destination.parent
                                / f".database-bigdata-{destination.name}.discard.{uuid.uuid4().hex}",
                                "rollback discard",
                            )
                            os.replace(destination, discard)
                            discarded.append(discard)
                    if operation["had_previous"] and not old_destination_is_intact:
                        if not present(backup):
                            fail(f"install backup is unavailable during rollback: {destination}")
                        if read_operation_value(operation, backup) != operation["old_value"]:
                            fail(f"install backup drifted before rollback: {destination}")
                        os.replace(backup, destination)
                        if read_operation_value(operation, destination) != operation["old_value"]:
                            fail(f"restored install destination differs: {destination}")
                except BaseException as rollback_exc:
                    rollback_failures.append(f"{destination}: {rollback_exc}")

            for item in staged:
                stage = item["stage"]
                try:
                    if stage.is_dir() and not stage.is_symlink():
                        shutil.rmtree(stage)
                    elif present(stage):
                        stage.unlink()
                except OSError as cleanup_exc:
                    rollback_failures.append(f"staging cleanup {stage}: {cleanup_exc}")
            for discard in discarded:
                try:
                    if discard.is_dir() and not discard.is_symlink():
                        shutil.rmtree(discard)
                    elif present(discard):
                        discard.unlink()
                except OSError as cleanup_exc:
                    rollback_failures.append(f"discard cleanup {discard}: {cleanup_exc}")
            if rollback_failures:
                remaining_backups = [
                    str(operation["backup"])
                    for operation in operations
                    if present(operation["backup"])
                ]
                raise IntegrationError(
                    "installation failed and rollback was incomplete: "
                    f"original={exc}; rollback={rollback_failures}; "
                    f"preserved_backups={remaining_backups}"
                ) from exc
            raise

        for operation in operations:
            backup = operation["backup"]
            if backup.is_dir() and not backup.is_symlink():
                shutil.rmtree(backup, ignore_errors=True)
            elif present(backup):
                try:
                    backup.unlink()
                except OSError:
                    pass
        return checked


def result_payload(expected: Mapping[str, Any], mode: str) -> dict[str, Any]:
    manifest = expected["manifest"]
    if mode == "qualify-local":
        return {
            "status": "NOT_RUN",
            "mode": mode,
            "package": PACKAGE_NAME,
            "version": PACKAGE_VERSION,
            "source_files": manifest["canonical_source_file_count"],
            "reference_tools": manifest["reference_tool_state"],
            "skill_implementation": "DECLARED",
            "installation_state": "NOT_CHECKED",
            "runtime_skills": "NOT_CHECKED",
            "workspace_skills": "NOT_CHECKED",
            "provider_runtime": "NOT_RUN",
            "external_evidence": "NOT_RUN",
            "production_certification": "NOT_CERTIFIED",
            "maximum_local_claim": "SOURCE_VALIDATED_NO_REFERENCE_TOOL_EXECUTION",
            "reason": (
                "local execution is disabled without a default-deny "
                "filesystem-write and network sandbox"
            ),
        }
    if mode == "extract-source":
        return {
            "status": "PASS",
            "mode": mode,
            "package": PACKAGE_NAME,
            "version": PACKAGE_VERSION,
            "source_files": manifest["canonical_source_file_count"],
            "installation_state": "NOT_CHECKED",
            "runtime_skills": "NOT_CHECKED",
            "workspace_skills": "NOT_CHECKED",
            "provider_runtime": "NOT_RUN",
            "external_evidence": "NOT_RUN",
            "production_certification": "NOT_CERTIFIED",
            "maximum_local_claim": "CANONICAL_SOURCE_EXTRACTED",
        }
    return {
        "status": "PASS",
        "mode": mode,
        "package": PACKAGE_NAME,
        "version": PACKAGE_VERSION,
        "source_files": manifest["canonical_source_file_count"],
        "skills": manifest["skill_count"],
        "profiles": manifest["profile_count"],
        "schemas": manifest["schema_count"],
        "technologies": manifest["technology_catalog_count"],
        "runtime_skills": manifest["skill_count"],
        "workspace_skills": manifest["skill_count"],
        "reference_tools": manifest["reference_tool_state"],
        "skill_implementation": manifest["skill_implementation_state"],
        "provider_runtime": manifest["provider_runtime_evidence"],
        "external_evidence": manifest["external_evidence_status"],
        "production_certification": manifest["production_certification"],
        "maximum_local_claim": manifest["maximum_local_claim"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="install normalized Skills")
    mode.add_argument("--check", action="store_true", help="fail on source or installation drift")
    mode.add_argument(
        "--extract-source",
        action="store_true",
        help="safely materialize the pinned canonical source when it is absent",
    )
    mode.add_argument(
        "--qualify-local",
        action="store_true",
        help="validate source and report NOT_RUN while sandboxed execution is disabled",
    )
    args = parser.parse_args(argv)
    try:
        if args.qualify_local:
            qualify_local()
            expected = build_expected()
            selected_mode = "qualify-local"
        elif args.extract_source:
            extract_canonical_source()
            expected = build_expected()
            selected_mode = "extract-source"
        elif args.write:
            expected = write_install()
            selected_mode = "write"
        else:
            expected = check_install()
            selected_mode = "check"
    except IntegrationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result_payload(expected, selected_mode), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
