#!/usr/bin/env python3
"""Safely import the repository task-decomposition and model-router Skills.

The pinned ZIP is untrusted input.  This module reads every member as bounded
data and never imports or executes the package's Python, tests, prompts,
AGENTS.md, CLAUDE.md, or workflow.  It preserves an immutable source tree and
separately emits Codex-compatible, provenance-bound repository Skills.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import os
import re
import stat
import tempfile
import unicodedata
import zipfile
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "elmos-repository-task-decomposition-cost-router-skills"
PACKAGE_VERSION = "1.1.0"
PACKAGE_ID = "elmos.repository-task-router-skills"
NAMESPACE = "repository-task-router-v1"
ARCHIVE_ROOT = "elmos_repo_orchestrator_skills"
ARCHIVE_RELATIVE = Path("skills/subskills") / f"{PACKAGE_NAME}-v{PACKAGE_VERSION}.zip"
SOURCE_RELATIVE = Path("skills") / f"{PACKAGE_NAME}-v{PACKAGE_VERSION}"
DOC_RELATIVE = Path("docs/repository-task-router-skills")
INSTALL_ROOTS = (Path("agent-skills/runtime"), Path(".agents/skills"))

EXPECTED_ARCHIVE_SHA256 = "c5842c93d268f2ebc7126d743a2fce6fba9f92071ea7e6556c11349d4896337a"
EXPECTED_ARCHIVE_BYTES = 72_565
EXPECTED_ENTRY_COUNT = 108
EXPECTED_FILE_COUNT = 63
EXPECTED_DIRECTORY_COUNT = 45
EXPECTED_UNCOMPRESSED_BYTES = 101_831
EXPECTED_SOURCE_MODE_COUNTS = {"file:0644": 63, "directory:2755": 45}
EXPECTED_CATEGORY_COUNTS = {
    "(root)": 5,
    "config": 5,
    "docs": 4,
    "examples": 3,
    "schemas": 5,
    "scripts": 2,
    "skills": 37,
    "tests": 2,
}
MAX_ARCHIVE_ENTRY_BYTES = 128 * 1024
MAX_ARCHIVE_TOTAL_BYTES = 1024 * 1024
MAX_COMPRESSION_RATIO = 100
MAX_PATH_BYTES = 1024

EXPECTED_ALLOWLIST = (
    "gpt-5.6-sol-max",
    "claude-opus-5-max",
    "claude-fable-5",
    "grok-4.6",
    "kimi-k3-max",
    "glm-5.3-max",
    "qwen3.8-max",
    "deepseek-v4-pro-0813",
    "gemini-3.7-flash-high",
    "claude-sonnet-5",
)

EXPECTED_SKILLS = (
    "elmos-repository-orchestrator",
    "elmos-requirement-normalizer",
    "elmos-repo-intake",
    "elmos-architecture-indexer",
    "elmos-change-impact-analyzer",
    "elmos-task-decomposer",
    "elmos-atomicity-validator",
    "elmos-task-dag-builder",
    "elmos-contract-boundary-generator",
    "elmos-complexity-estimator",
    "elmos-risk-classifier",
    "elmos-context-slicer",
    "elmos-model-registry-guard",
    "elmos-model-capability-profiler",
    "elmos-cost-performance-router",
    "elmos-budget-planner",
    "elmos-eta-estimator",
    "elmos-wave-scheduler",
    "elmos-worktree-manager",
    "elmos-worker-prompt-builder",
    "elmos-worker-executor",
    "elmos-deterministic-validator",
    "elmos-failure-classifier",
    "elmos-retry-escalation-controller",
    "elmos-patch-reviewer",
    "elmos-security-auth-gate",
    "elmos-data-migration-gate",
    "elmos-concurrency-idempotency-gate",
    "elmos-integration-manager",
    "elmos-conflict-resolver",
    "elmos-incremental-regression-gate",
    "elmos-repository-certifier",
    "elmos-rollback-recovery",
    "elmos-run-state-journal",
    "elmos-telemetry-learner",
    "elmos-routing-policy-optimizer",
    "elmos-model-selection-controller",
)

EXPECTED_V11_SKILLS = frozenset(
    {
        "elmos-repository-orchestrator",
        "elmos-model-registry-guard",
        "elmos-cost-performance-router",
        "elmos-worker-executor",
        "elmos-retry-escalation-controller",
        "elmos-model-selection-controller",
    }
)

# This repository-owned graph is deliberately explicit because the source
# package contains only a nested example workflow, not a dependency manifest.
# Conditional nodes reach a terminal skipped state when their trigger is false.
DAG_DEPENDENCIES: Mapping[str, tuple[str, ...]] = {
    "elmos-repository-orchestrator": (),
    "elmos-run-state-journal": ("elmos-repository-orchestrator",),
    "elmos-model-selection-controller": (
        "elmos-repository-orchestrator",
        "elmos-run-state-journal",
    ),
    "elmos-requirement-normalizer": (
        "elmos-repository-orchestrator",
        "elmos-run-state-journal",
        "elmos-model-selection-controller",
    ),
    "elmos-repo-intake": ("elmos-requirement-normalizer",),
    "elmos-architecture-indexer": ("elmos-repo-intake",),
    "elmos-change-impact-analyzer": (
        "elmos-requirement-normalizer",
        "elmos-architecture-indexer",
    ),
    "elmos-task-decomposer": ("elmos-change-impact-analyzer",),
    "elmos-atomicity-validator": ("elmos-task-decomposer",),
    "elmos-task-dag-builder": ("elmos-atomicity-validator",),
    "elmos-contract-boundary-generator": ("elmos-task-dag-builder",),
    "elmos-complexity-estimator": ("elmos-contract-boundary-generator",),
    "elmos-risk-classifier": ("elmos-contract-boundary-generator",),
    "elmos-context-slicer": ("elmos-contract-boundary-generator",),
    "elmos-model-registry-guard": (
        "elmos-run-state-journal",
        "elmos-model-selection-controller",
    ),
    "elmos-model-capability-profiler": ("elmos-model-registry-guard",),
    "elmos-cost-performance-router": (
        "elmos-complexity-estimator",
        "elmos-risk-classifier",
        "elmos-context-slicer",
        "elmos-model-registry-guard",
        "elmos-model-capability-profiler",
        "elmos-model-selection-controller",
    ),
    "elmos-budget-planner": (
        "elmos-task-dag-builder",
        "elmos-cost-performance-router",
    ),
    "elmos-eta-estimator": (
        "elmos-task-dag-builder",
        "elmos-budget-planner",
    ),
    "elmos-wave-scheduler": (
        "elmos-task-dag-builder",
        "elmos-budget-planner",
        "elmos-eta-estimator",
        "elmos-run-state-journal",
    ),
    "elmos-worktree-manager": ("elmos-wave-scheduler",),
    "elmos-worker-prompt-builder": (
        "elmos-contract-boundary-generator",
        "elmos-context-slicer",
        "elmos-worktree-manager",
    ),
    "elmos-worker-executor": (
        "elmos-model-registry-guard",
        "elmos-cost-performance-router",
        "elmos-worktree-manager",
        "elmos-worker-prompt-builder",
        "elmos-model-selection-controller",
    ),
    "elmos-deterministic-validator": (
        "elmos-risk-classifier",
        "elmos-worker-executor",
    ),
    "elmos-failure-classifier": (
        "elmos-worker-executor",
        "elmos-deterministic-validator",
    ),
    "elmos-retry-escalation-controller": (
        "elmos-model-registry-guard",
        "elmos-cost-performance-router",
        "elmos-failure-classifier",
        "elmos-model-selection-controller",
    ),
    "elmos-patch-reviewer": (
        "elmos-risk-classifier",
        "elmos-model-registry-guard",
        "elmos-deterministic-validator",
    ),
    "elmos-security-auth-gate": (
        "elmos-risk-classifier",
        "elmos-deterministic-validator",
    ),
    "elmos-data-migration-gate": (
        "elmos-risk-classifier",
        "elmos-deterministic-validator",
    ),
    "elmos-concurrency-idempotency-gate": (
        "elmos-risk-classifier",
        "elmos-deterministic-validator",
    ),
    "elmos-integration-manager": (
        "elmos-deterministic-validator",
        "elmos-patch-reviewer",
        "elmos-security-auth-gate",
        "elmos-data-migration-gate",
        "elmos-concurrency-idempotency-gate",
        "elmos-run-state-journal",
    ),
    "elmos-conflict-resolver": ("elmos-integration-manager",),
    "elmos-incremental-regression-gate": (
        "elmos-integration-manager",
        "elmos-conflict-resolver",
    ),
    "elmos-repository-certifier": (
        "elmos-model-registry-guard",
        "elmos-security-auth-gate",
        "elmos-data-migration-gate",
        "elmos-concurrency-idempotency-gate",
        "elmos-incremental-regression-gate",
    ),
    "elmos-rollback-recovery": (
        "elmos-repository-orchestrator",
        "elmos-worktree-manager",
        "elmos-worker-executor",
        "elmos-integration-manager",
        "elmos-run-state-journal",
    ),
    "elmos-telemetry-learner": (
        "elmos-repository-certifier",
        "elmos-run-state-journal",
    ),
    "elmos-routing-policy-optimizer": (
        "elmos-model-registry-guard",
        "elmos-cost-performance-router",
        "elmos-telemetry-learner",
    ),
}

CONDITIONAL_SKILLS = frozenset(
    {
        "elmos-contract-boundary-generator",
        "elmos-failure-classifier",
        "elmos-retry-escalation-controller",
        "elmos-patch-reviewer",
        "elmos-security-auth-gate",
        "elmos-data-migration-gate",
        "elmos-concurrency-idempotency-gate",
        "elmos-conflict-resolver",
    }
)
CONTROL_SKILLS = frozenset(
    {
        "elmos-model-registry-guard",
        "elmos-run-state-journal",
        "elmos-model-selection-controller",
    }
)
EXCEPTION_SKILLS = frozenset({"elmos-rollback-recovery"})
OFFLINE_SKILLS = frozenset({"elmos-routing-policy-optimizer"})

RUNTIME_REGISTRY_RELATIVE = Path(
    "packages/repository-orchestrator/config/handler-registry.json"
)
RUNTIME_MODULE = "elmos_repository_orchestrator.runtime"
RUNTIME_CALLABLE = "dispatch"
EXTERNAL_EVIDENCE_STATUS = "NOT_RUN"
CERTIFICATION_STATUS = "NOT_CERTIFIED"

# One exact, locally generated documentation tree existed before the managed
# output receipt was introduced.  This digest is the only receipt-less tree
# that may be refreshed; arbitrary or partially modified trees still fail.
LEGACY_MANAGED_DOC_TREE_SHA256S = frozenset(
    {"sha256:d348470108610f66cc4e7d6638ae1fdf9a674ab6c2bc0a75b62aab02407dc0bf"}
)

SOURCE_ABSENCE_FACTS = {
    "checksums_inventory": False,
    "cryptographic_signature": False,
    "license": False,
    "sbom": False,
    "provenance_attestation": False,
}

_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "CLOCK$",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}
_WINDOWS_INVALID = frozenset('<>:"|?*')
_SKILL_NAME_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

YamlLoader = Callable[[str], Any]


class IntegrationError(RuntimeError):
    """Fail-closed source, safety, ownership, or drift error."""


@dataclass(frozen=True)
class ArchiveRecord:
    archive_name: str
    relative: str
    kind: str
    size: int
    compressed_size: int
    source_mode: int
    sha256: str | None
    content: bytes | None


@dataclass(frozen=True)
class SourceSkill:
    ordinal: int
    name: str
    version: str
    description: str
    source_path: str
    source_sha256: str
    body: str
    sections: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True)
class RuntimeRegistry:
    present: bool
    path: str
    sha256: str | None
    names: tuple[str, ...]
    handlers: Mapping[str, str]
    canonical_owners: Mapping[str, str]
    adapter_requirements: Mapping[str, str | None]


@dataclass(frozen=True)
class PackageSnapshot:
    archive_sha256: str
    archive_bytes: int
    entry_count: int
    uncompressed_bytes: int
    files: Mapping[str, ArchiveRecord]
    directories: tuple[str, ...]
    skills: tuple[SourceSkill, ...]
    source_findings: tuple[Mapping[str, Any], ...]
    workflow_names: tuple[str, ...]
    topological_order: tuple[str, ...]


@dataclass(frozen=True)
class FilePayload:
    content: bytes
    mode: int = 0o644


@dataclass(frozen=True)
class TreeSpec:
    files: Mapping[str, FilePayload]
    directories: tuple[str, ...]


@dataclass(frozen=True)
class ManagedAction:
    label: str
    destination: Path
    tree: TreeSpec


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _decode_utf8(value: bytes, label: str) -> str:
    try:
        text = value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise IntegrationError(f"{label} is not valid UTF-8") from exc
    if "\x00" in text or "\r\n" in text:
        raise IntegrationError(f"{label} must be NUL-free UTF-8 with LF endings")
    return text


def _default_yaml_loader(value: str) -> Any:
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise IntegrationError("PyYAML 6.0.2 is required for source validation") from exc
    try:
        return yaml.safe_load(value)
    except yaml.YAMLError as exc:
        raise IntegrationError(f"source YAML is invalid: {exc}") from exc


def _validate_path_part(part: str, label: str) -> None:
    if not part or part in {".", ".."}:
        raise IntegrationError(f"{label} contains an ambiguous path segment")
    if part.endswith((" ", ".")):
        raise IntegrationError(f"{label} has a trailing-dot/space segment: {part!r}")
    if any(character in _WINDOWS_INVALID for character in part):
        raise IntegrationError(f"{label} has a reserved path character: {part!r}")
    if part.split(".", 1)[0].rstrip(" .").upper() in _WINDOWS_RESERVED:
        raise IntegrationError(f"{label} has a reserved device name: {part!r}")


def _validated_relative_path(value: str, label: str) -> PurePosixPath:
    if (
        not value
        or "\\" in value
        or "\x00" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise IntegrationError(f"unsafe {label} path: {value!r}")
    if unicodedata.normalize("NFC", value) != value:
        raise IntegrationError(f"{label} path is not NFC-normalized: {value!r}")
    if len(value.encode("utf-8")) > MAX_PATH_BYTES:
        raise IntegrationError(f"{label} path is too long: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value:
        raise IntegrationError(f"{label} path is absolute or non-canonical: {value!r}")
    for part in path.parts:
        _validate_path_part(part, label)
    return path


def _archive_relative(name: str, is_directory: bool) -> str:
    if is_directory != name.endswith("/"):
        raise IntegrationError(f"archive member directory marker is inconsistent: {name!r}")
    canonical = name[:-1] if is_directory else name
    path = _validated_relative_path(canonical, "archive member")
    if not path.parts or path.parts[0] != ARCHIVE_ROOT:
        raise IntegrationError(f"archive member escapes the pinned root: {name!r}")
    if len(path.parts) == 1:
        if not is_directory:
            raise IntegrationError("archive root must be a directory")
        return ""
    return PurePosixPath(*path.parts[1:]).as_posix()


def _member_kind_and_mode(info: zipfile.ZipInfo) -> tuple[str, int]:
    if info.create_system != 3:
        raise IntegrationError(f"archive member is not Unix-authored: {info.filename!r}")
    if info.flag_bits != 0:
        if info.flag_bits & 0x1:
            raise IntegrationError(f"encrypted archive member is forbidden: {info.filename!r}")
        raise IntegrationError(f"unsupported ZIP flags on member: {info.filename!r}")
    unix_mode = (info.external_attr >> 16) & 0xFFFF
    file_type = stat.S_IFMT(unix_mode)
    permission = stat.S_IMODE(unix_mode)
    if info.is_dir():
        if file_type != stat.S_IFDIR or permission != 0o2755:
            raise IntegrationError(f"unexpected source directory mode: {info.filename!r}")
        if info.compress_type != zipfile.ZIP_STORED or info.file_size != 0:
            raise IntegrationError(f"source directory entry must be empty/stored: {info.filename!r}")
        return "directory", permission
    if file_type != stat.S_IFREG or permission != 0o644:
        raise IntegrationError(f"link, special, or wrong-mode file: {info.filename!r}")
    if info.compress_type != zipfile.ZIP_DEFLATED:
        raise IntegrationError(f"unsupported file compression: {info.filename!r}")
    if info.file_size < 0 or info.file_size > MAX_ARCHIVE_ENTRY_BYTES:
        raise IntegrationError(f"archive member size is unsafe: {info.filename!r}")
    if info.compress_size < 0:
        raise IntegrationError(f"archive compressed size is invalid: {info.filename!r}")
    if info.file_size / max(info.compress_size, 1) > MAX_COMPRESSION_RATIO:
        raise IntegrationError(f"archive compression ratio is unsafe: {info.filename!r}")
    return "file", permission


def inspect_archive(
    archive_path: Path,
    *,
    trusted_sha256: str | None = EXPECTED_ARCHIVE_SHA256,
    expected_archive_bytes: int | None = EXPECTED_ARCHIVE_BYTES,
    expected_entry_count: int | None = EXPECTED_ENTRY_COUNT,
    expected_total_bytes: int | None = EXPECTED_UNCOMPRESSED_BYTES,
    expected_mode_counts: Mapping[str, int] | None = EXPECTED_SOURCE_MODE_COUNTS,
) -> tuple[bytes, Mapping[str, ArchiveRecord]]:
    """Read every bounded member without extracting or executing package content."""

    if not archive_path.is_file() or archive_path.is_symlink():
        raise IntegrationError(f"source archive must be a regular file: {archive_path}")
    archive_bytes = archive_path.read_bytes()
    if expected_archive_bytes is not None and len(archive_bytes) != expected_archive_bytes:
        raise IntegrationError(
            f"archive byte count mismatch: {len(archive_bytes)} != {expected_archive_bytes}"
        )
    archive_sha256 = _sha256(archive_bytes)
    if trusted_sha256 is not None and archive_sha256 != trusted_sha256:
        raise IntegrationError(
            f"archive SHA-256 mismatch: expected {trusted_sha256}, got {archive_sha256}"
        )
    try:
        handle = zipfile.ZipFile(io.BytesIO(archive_bytes), "r")
    except zipfile.BadZipFile as exc:
        raise IntegrationError("pinned source is not a valid ZIP") from exc

    records: dict[str, ArchiveRecord] = {}
    raw_names: set[str] = set()
    folded_names: set[str] = set()
    total_bytes = 0
    mode_counts: Counter[str] = Counter()
    try:
        with handle:
            if handle.comment:
                raise IntegrationError("archive comment is not allowed")
            infos = handle.infolist()
            if expected_entry_count is not None and len(infos) != expected_entry_count:
                raise IntegrationError(
                    f"archive entry count mismatch: {len(infos)} != {expected_entry_count}"
                )
            for info in infos:
                if info.filename in raw_names:
                    raise IntegrationError(f"duplicate archive member: {info.filename!r}")
                raw_names.add(info.filename)
                kind, source_mode = _member_kind_and_mode(info)
                relative = _archive_relative(info.filename, kind == "directory")
                collision_key = unicodedata.normalize("NFC", relative).casefold()
                if collision_key in folded_names:
                    raise IntegrationError(f"case/Unicode archive path collision: {info.filename!r}")
                folded_names.add(collision_key)
                total_bytes += info.file_size
                if total_bytes > MAX_ARCHIVE_TOTAL_BYTES:
                    raise IntegrationError("archive exceeds bounded expansion budget")
                content: bytes | None = None
                digest: str | None = None
                if kind == "file":
                    chunks: list[bytes] = []
                    observed = 0
                    hasher = hashlib.sha256()
                    with handle.open(info, "r") as member:
                        while True:
                            chunk = member.read(64 * 1024)
                            if not chunk:
                                break
                            observed += len(chunk)
                            if observed > info.file_size or observed > MAX_ARCHIVE_ENTRY_BYTES:
                                raise IntegrationError(
                                    f"archive member exceeded declared size: {info.filename!r}"
                                )
                            hasher.update(chunk)
                            chunks.append(chunk)
                    if observed != info.file_size:
                        raise IntegrationError(f"archive member size mismatch: {info.filename!r}")
                    content = b"".join(chunks)
                    digest = hasher.hexdigest()
                    _decode_utf8(content, relative)
                records[relative] = ArchiveRecord(
                    archive_name=info.filename,
                    relative=relative,
                    kind=kind,
                    size=info.file_size,
                    compressed_size=info.compress_size,
                    source_mode=source_mode,
                    sha256=digest,
                    content=content,
                )
                mode_counts[f"{kind}:{source_mode:04o}"] += 1
    except (OSError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        if isinstance(exc, IntegrationError):
            raise
        raise IntegrationError(f"cannot safely inspect source archive: {exc}") from exc

    if expected_total_bytes is not None and total_bytes != expected_total_bytes:
        raise IntegrationError(
            f"archive uncompressed-byte mismatch: {total_bytes} != {expected_total_bytes}"
        )
    if expected_mode_counts is not None and mode_counts != Counter(expected_mode_counts):
        raise IntegrationError(f"archive mode distribution mismatch: {dict(mode_counts)!r}")
    return archive_bytes, records


def _split_frontmatter(
    value: bytes, label: str, yaml_loader: YamlLoader
) -> tuple[Mapping[str, Any], str]:
    text = _decode_utf8(value, label)
    match = re.match(r"^---\n(.*?)\n---\n?", text, re.DOTALL)
    if match is None:
        raise IntegrationError(f"invalid Skill frontmatter envelope: {label}")
    try:
        frontmatter = yaml_loader(match.group(1))
    except Exception as exc:
        raise IntegrationError(f"invalid Skill frontmatter YAML: {label}: {exc}") from exc
    if not isinstance(frontmatter, Mapping):
        raise IntegrationError(f"Skill frontmatter must be a mapping: {label}")
    return frontmatter, text[match.end() :].lstrip("\n")


def _section_items(body: str, heading: str) -> tuple[str, ...]:
    match = re.search(
        rf"^## {re.escape(heading)}\s*$\n(.*?)(?=^## |\Z)",
        body,
        re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise IntegrationError(f"source Skill is missing section: {heading}")
    items = []
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            # Preserve Markdown verbatim.  Stripping backticks from both ends
            # corrupts a leading inline-code span when explanatory prose
            # follows it (for example, ``model_selection` (Smart ...)``).
            items.append(stripped[2:].strip())
    return tuple(items)


def _parse_source_skills(
    files: Mapping[str, ArchiveRecord], yaml_loader: YamlLoader
) -> tuple[SourceSkill, ...]:
    paths = sorted(
        relative
        for relative, record in files.items()
        if record.kind == "file" and re.fullmatch(r"skills/[0-9]{2}-[^/]+/SKILL\.md", relative)
    )
    if len(paths) != len(EXPECTED_SKILLS):
        raise IntegrationError(f"source Skill count mismatch: {len(paths)}")
    skills: list[SourceSkill] = []
    for ordinal, (path, expected_name) in enumerate(zip(paths, EXPECTED_SKILLS, strict=True)):
        if not path.startswith(f"skills/{ordinal:02d}-"):
            raise IntegrationError(f"source Skill ordinal/path mismatch: {path}")
        record = files[path]
        assert record.content is not None and record.sha256 is not None
        frontmatter, body = _split_frontmatter(record.content, path, yaml_loader)
        if set(frontmatter) != {"name", "version", "description"}:
            raise IntegrationError(f"source Skill frontmatter keys drifted: {path}")
        name = frontmatter.get("name")
        version = str(frontmatter.get("version"))
        description = frontmatter.get("description")
        expected_version = "1.1.0" if expected_name in EXPECTED_V11_SKILLS else "1.0.0"
        if (
            name != expected_name
            or version != expected_version
            or not isinstance(description, str)
            or not description.strip()
            or _SKILL_NAME_RE.fullmatch(expected_name) is None
            or len(expected_name) > 64
        ):
            raise IntegrationError(f"source Skill identity mismatch: {path}")
        required_sections = (
            "Trigger conditions",
            "Inputs",
            "Outputs",
            "Procedure",
            "Guardrails",
            "Acceptance criteria",
            "Integration contract",
        )
        sections = {section: _section_items(body, section) for section in required_sections}
        skills.append(
            SourceSkill(
                ordinal=ordinal,
                name=expected_name,
                version=version,
                description=description.strip(),
                source_path=path,
                source_sha256=record.sha256,
                body=body,
                sections=sections,
            )
        )
    if tuple(skill.name for skill in skills) != EXPECTED_SKILLS:
        raise IntegrationError("source Skill order differs from the pinned inventory")
    return tuple(skills)


def _load_json_record(files: Mapping[str, ArchiveRecord], path: str) -> Any:
    record = files.get(path)
    if record is None or record.kind != "file" or record.content is None:
        raise IntegrationError(f"source JSON file is missing: {path}")
    try:
        return json.loads(_decode_utf8(record.content, path))
    except json.JSONDecodeError as exc:
        raise IntegrationError(f"source JSON is invalid: {path}") from exc


def _load_yaml_record(
    files: Mapping[str, ArchiveRecord], path: str, yaml_loader: YamlLoader
) -> Any:
    record = files.get(path)
    if record is None or record.kind != "file" or record.content is None:
        raise IntegrationError(f"source YAML file is missing: {path}")
    try:
        return yaml_loader(_decode_utf8(record.content, path))
    except IntegrationError:
        raise
    except Exception as exc:
        raise IntegrationError(f"source YAML is invalid: {path}: {exc}") from exc


def _literal_string_set(source: str, assignment: str, label: str) -> set[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise IntegrationError(f"source Python is not parseable data: {label}") from exc
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == assignment for target in targets):
                value = node.value
                try:
                    parsed = ast.literal_eval(value)
                except (ValueError, TypeError) as exc:
                    raise IntegrationError(f"{label} {assignment} is not literal data") from exc
                if not isinstance(parsed, (set, frozenset, list, tuple)) or not all(
                    isinstance(item, str) for item in parsed
                ):
                    raise IntegrationError(f"{label} {assignment} is not a string collection")
                return set(parsed)
    raise IntegrationError(f"{label} is missing literal assignment {assignment}")


def _compiled_schemas() -> Mapping[str, Mapping[str, Any]]:
    aliases = list(EXPECTED_ALLOWLIST)
    relative_path = {
        "type": "string",
        "minLength": 1,
        "pattern": r"^(?!/)(?!.*(?:^|/)\.\.(?:/|$))(?!.*\\).+$",
    }
    model_selection_request_properties = {
        "mode": {"enum": ["smart", "manual"]},
        "selected_model": {"enum": [*aliases, None]},
        "optimization_profile": {
            "enum": ["cost_performance", "lowest_cost", "max_quality", "fastest"]
        },
        "fallback_policy": {"enum": ["strict", "smart_within_allowlist"]},
        "verification_policy": {
            "enum": ["system_required_verifiers", "selected_model_only"]
        },
    }
    model_selection_request = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://elmos.dev/schemas/repository-task-router/model-selection-request.v1.json",
        "description": (
            "Caller-controlled model-selection request. Server-derived lock, source, "
            "resolution time, and registry provenance fields are forbidden."
        ),
        "type": "object",
        "additionalProperties": False,
        "required": ["mode"],
        "properties": model_selection_request_properties,
        "allOf": [
            {
                "if": {"properties": {"mode": {"const": "manual"}}, "required": ["mode"]},
                "then": {
                    "required": ["selected_model"],
                    "properties": {
                        "selected_model": {"type": "string", "enum": aliases},
                    }
                },
                "else": {
                    "properties": {
                        "selected_model": {"type": "null"},
                    }
                },
            }
        ],
    }
    model_selection_resolved = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://elmos.dev/schemas/repository-task-router/model-selection-resolved.v1.json",
        "description": (
            "Server-resolved, registry-bound selection record. A NOT_CONFIGURED result "
            "with absent registry provenance is not a resolved record."
        ),
        "type": "object",
        "additionalProperties": False,
        "required": [
            "mode",
            "selected_model",
            "optimization_profile",
            "fallback_policy",
            "verification_policy",
            "selection_source",
            "locked_by_user",
            "resolved_at",
            "registry_digest",
        ],
        "properties": {
            **model_selection_request_properties,
            "selection_source": {"enum": ["ui", "api", "cli", "resume"]},
            "locked_by_user": {"type": "boolean"},
            "resolved_at": {"type": "string", "format": "date-time"},
            "registry_digest": {
                "type": "string",
                "pattern": r"^sha256:[0-9a-f]{64}$",
            },
        },
        "allOf": [
            {
                "if": {"properties": {"mode": {"const": "manual"}}, "required": ["mode"]},
                "then": {
                    "properties": {
                        "selected_model": {"type": "string", "enum": aliases},
                        "locked_by_user": {"const": True},
                    }
                },
                "else": {
                    "properties": {
                        "selected_model": {"type": "null"},
                        "locked_by_user": {"const": False},
                    }
                },
            }
        ],
    }
    task = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://elmos.dev/schemas/repository-task-router/task.v1.json",
        "description": (
            "Atomic planning input. Complexity and status are optional stage-owned "
            "annotations added by the estimator and journal after decomposition."
        ),
        "type": "object",
        "additionalProperties": False,
        "required": ["id", "title", "objective", "acceptance"],
        "properties": {
            "id": {"type": "string", "pattern": r"^[A-Za-z0-9][A-Za-z0-9._-]*$"},
            "title": {"type": "string", "minLength": 1},
            "objective": {"type": "string", "minLength": 1},
            "task_class": {"type": "string", "minLength": 1},
            "owned_paths": {"type": "array", "uniqueItems": True, "items": relative_path},
            "read_paths": {"type": "array", "uniqueItems": True, "items": relative_path},
            "forbidden_paths": {"type": "array", "uniqueItems": True, "items": relative_path},
            "dependencies": {
                "type": "array", "uniqueItems": True,
                "items": {"type": "string", "pattern": r"^[A-Za-z0-9][A-Za-z0-9._-]*$"},
            },
            "acceptance": {
                "type": "array", "minItems": 1, "uniqueItems": True,
                "items": {"type": "string", "minLength": 1},
            },
            "complexity": {"type": "object"},
            "risk": {"type": "object"},
            "read_only": {"type": "boolean"},
            "context_pack": {"type": "object"},
            "routing": {"type": "object"},
            "status": {"enum": ["planned", "ready", "running", "blocked", "failed", "passed", "waived"]},
        },
        "allOf": [
            {
                "anyOf": [
                    {
                        "required": ["owned_paths"],
                        "properties": {"owned_paths": {"minItems": 1}},
                    },
                    {
                        "required": ["read_only"],
                        "properties": {"read_only": {"const": True}},
                    },
                ]
            }
        ],
    }
    dag = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://elmos.dev/schemas/repository-task-router/dag.v1.json",
        "type": "object",
        "additionalProperties": False,
        "required": ["run_id", "tasks", "waves"],
        "properties": {
            "run_id": {"type": "string", "minLength": 1},
            "tasks": {"type": "array", "minItems": 1, "items": task},
            "waves": {
                "type": "array", "minItems": 1,
                "items": {"type": "array", "minItems": 1, "uniqueItems": True, "items": {"type": "string"}},
            },
            "critical_path": {"type": "array", "uniqueItems": True, "items": {"type": "string"}},
            "path_locks": {"type": "object"},
        },
    }
    evidence = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://elmos.dev/schemas/repository-task-router/evidence.v1.json",
        "type": "object",
        "additionalProperties": False,
        "required": ["kind", "command_or_check", "status", "sha256", "bytes", "executor"],
        "properties": {
            "kind": {"type": "string", "minLength": 1},
            "command_or_check": {"type": "string", "minLength": 1},
            "status": {"enum": ["PASS", "FAIL", "NOT_RUN", "BLOCKED", "INCONCLUSIVE"]},
            "artifact": {"oneOf": [relative_path, {"type": "null"}]},
            "sha256": {"type": "string", "pattern": r"^sha256:[0-9a-f]{64}$"},
            "bytes": {"type": "integer", "minimum": 0},
            "timestamp": {"type": "string", "format": "date-time"},
            "executor": {"type": "string", "minLength": 1},
            "verifier": {"type": ["string", "null"]},
        },
    }
    execution = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://elmos.dev/schemas/repository-task-router/execution-record.v1.json",
        "type": "object",
        "additionalProperties": False,
        "required": ["task_id", "model_alias", "attempt", "started_at", "result"],
        "properties": {
            "task_id": {"type": "string", "minLength": 1},
            "model_alias": {"type": "string", "enum": aliases},
            "attempt": {"type": "integer", "minimum": 1},
            "prompt_tokens": {"type": ["integer", "null"], "minimum": 0},
            "output_tokens": {"type": ["integer", "null"], "minimum": 0},
            "cost_amount": {
                "type": "string",
                "pattern": r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$",
            },
            "cost_currency": {"type": "string", "pattern": r"^[A-Z]{3}$"},
            "pricing_effective_at": {"type": "string", "format": "date-time"},
            "pricing_registry_digest": {
                "type": "string",
                "pattern": r"^sha256:[0-9a-f]{64}$",
            },
            "started_at": {"type": "string", "format": "date-time"},
            "ended_at": {"type": ["string", "null"], "format": "date-time"},
            "result": {"type": "string", "minLength": 1},
            "failure_class": {"type": ["string", "null"]},
            "evidence": {"type": "array", "items": evidence},
            "selection_mode": {"enum": ["smart", "manual", None]},
            "selection_provenance": {
                "enum": ["system_smart", "user_selected", "fallback", "required_verifier", None]
            },
            "user_selected_model": {"enum": [*aliases, None]},
            "fallback_from_model": {"enum": [*aliases, None]},
            "routing_reason": {"type": ["string", "null"]},
        },
        "dependentRequired": {
            "cost_amount": [
                "cost_currency",
                "pricing_effective_at",
                "pricing_registry_digest",
            ],
            "cost_currency": [
                "cost_amount",
                "pricing_effective_at",
                "pricing_registry_digest",
            ],
            "pricing_effective_at": [
                "cost_amount",
                "cost_currency",
                "pricing_registry_digest",
            ],
            "pricing_registry_digest": [
                "cost_amount",
                "cost_currency",
                "pricing_effective_at",
            ],
        },
    }
    return {
        "dag.schema.json": dag,
        "evidence.schema.json": evidence,
        "execution-record.schema.json": execution,
        "model-selection-request.schema.json": model_selection_request,
        "model-selection-resolved.schema.json": model_selection_resolved,
        "task.schema.json": task,
    }


def _validator(schema: Mapping[str, Any]) -> Any:
    try:
        from jsonschema import Draft202012Validator
    except ModuleNotFoundError as exc:
        raise IntegrationError("jsonschema 4.25.1 is required for contract validation") from exc
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        raise IntegrationError(f"JSON Schema is invalid: {exc}") from exc
    return Draft202012Validator(schema)


def _validate_dag() -> tuple[str, ...]:
    if set(DAG_DEPENDENCIES) != set(EXPECTED_SKILLS):
        raise IntegrationError("repository DAG does not contain exactly all 37 Skills")
    state: dict[str, int] = {}
    order: list[str] = []

    def visit(name: str, stack: tuple[str, ...]) -> None:
        observed = state.get(name, 0)
        if observed == 1:
            raise IntegrationError("repository Skill DAG cycle: " + " -> ".join((*stack, name)))
        if observed == 2:
            return
        state[name] = 1
        dependencies = DAG_DEPENDENCIES[name]
        if len(set(dependencies)) != len(dependencies):
            raise IntegrationError(f"repository Skill DAG has duplicate dependency: {name}")
        for dependency in dependencies:
            if dependency not in DAG_DEPENDENCIES:
                raise IntegrationError(f"repository Skill DAG has unknown dependency: {dependency}")
            visit(dependency, (*stack, name))
        state[name] = 2
        order.append(name)

    for skill in EXPECTED_SKILLS:
        visit(skill, ())
    return tuple(order)


def _validate_source_contracts(
    files: Mapping[str, ArchiveRecord], yaml_loader: YamlLoader
) -> tuple[tuple[Mapping[str, Any], ...], tuple[str, ...]]:
    manifest = _load_json_record(files, "manifest.json")
    if (
        not isinstance(manifest, Mapping)
        or manifest.get("package") != PACKAGE_NAME
        or manifest.get("version") != PACKAGE_VERSION
        or manifest.get("skills_count") != len(EXPECTED_SKILLS)
        or manifest.get("entry_skill") != "skills/00-repository-orchestrator/SKILL.md"
        or tuple(manifest.get("hard_model_allowlist", ())) != EXPECTED_ALLOWLIST
    ):
        raise IntegrationError("source manifest identity or inventory mismatch")

    registry = _load_yaml_record(files, "config/model-registry.yaml", yaml_loader)
    selection_policy = _load_yaml_record(files, "config/model-selection-policy.yaml", yaml_loader)
    router_policy = _load_yaml_record(files, "config/router-policy.yaml", yaml_loader)
    workflow = _load_yaml_record(files, "examples/full-repository-workflow.yaml", yaml_loader)
    if not isinstance(registry, Mapping) or tuple((registry.get("aliases") or {}).keys()) != EXPECTED_ALLOWLIST:
        raise IntegrationError("source model registry differs from the exact allowlist")
    if (
        not isinstance(selection_policy, Mapping)
        or selection_policy.get("default_mode") != "smart"
        or set((selection_policy.get("modes") or {}).keys()) != {"smart", "manual"}
    ):
        raise IntegrationError("source model-selection policy drifted")

    router_refs: set[str] = set()
    if not isinstance(router_policy, Mapping):
        raise IntegrationError("source router policy must be a mapping")
    for section in ("tiers", "task_class_preferences"):
        for candidates in (router_policy.get(section) or {}).values():
            if not isinstance(candidates, list):
                raise IntegrationError(f"source router policy {section} is malformed")
            router_refs.update(item for item in candidates if isinstance(item, str))
    router_refs.update((router_policy.get("review_policy") or {}).get("reviewer_candidates") or [])
    if not router_refs or not router_refs <= set(EXPECTED_ALLOWLIST):
        raise IntegrationError("source router policy references a non-allowlisted model")

    selection_schema = _load_json_record(files, "schemas/model-selection.schema.json")
    execution_schema = _load_json_record(files, "schemas/execution-record.schema.json")
    for schema_path in (
        "schemas/model-selection.schema.json",
        "schemas/task.schema.json",
        "schemas/execution-record.schema.json",
        "schemas/dag.schema.json",
        "schemas/evidence.schema.json",
    ):
        _validator(_load_json_record(files, schema_path))
    selected = selection_schema["properties"]["selected_model"]["enum"]
    if tuple(item for item in selected if item is not None) != EXPECTED_ALLOWLIST:
        raise IntegrationError("source model-selection Schema allowlist drifted")
    for field in ("user_selected_model", "fallback_from_model"):
        values = execution_schema["properties"][field]["enum"]
        if tuple(item for item in values if item is not None) != EXPECTED_ALLOWLIST:
            raise IntegrationError(f"source execution Schema allowlist drifted: {field}")

    for script_path, variable in (
        ("scripts/validate_package.py", "ALLOWED"),
        ("tests/test_allowlist.py", "EXPECTED"),
        ("tests/test_model_selection.py", "EXPECTED"),
    ):
        record = files[script_path]
        assert record.content is not None
        observed = _literal_string_set(_decode_utf8(record.content, script_path), variable, script_path)
        if observed != set(EXPECTED_ALLOWLIST):
            raise IntegrationError(f"source Python allowlist drifted: {script_path}")

    workflow_names: list[str] = []

    def collect_skills(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if key == "skill" and isinstance(child, str):
                    workflow_names.append(child)
                else:
                    collect_skills(child)
        elif isinstance(value, list):
            for child in value:
                collect_skills(child)

    collect_skills(workflow)
    if len(workflow_names) != 27 or len(set(workflow_names)) != 27:
        raise IntegrationError("source example workflow must reference exactly 27 unique Skills")
    if not set(workflow_names) <= set(EXPECTED_SKILLS):
        raise IntegrationError("source example workflow references an unknown Skill")

    findings: list[Mapping[str, Any]] = []
    source_task_schema = _load_json_record(files, "schemas/task.schema.json")
    task_plan = _load_json_record(files, "examples/example-task-plan.json")
    task_validator = _validator(source_task_schema)
    expected_missing = {"objective", "acceptance", "complexity", "status"}
    for task in task_plan.get("tasks", []):
        missing = set(source_task_schema["required"]) - set(task)
        if missing != expected_missing or not list(task_validator.iter_errors(task)):
            raise IntegrationError("pinned invalid task example shape drifted")
    findings.append(
        {
            "code": "SOURCE_TASK_EXAMPLE_SCHEMA_MISMATCH",
            "paths": ["examples/example-task-plan.json", "schemas/task.schema.json"],
            "affected_tasks": len(task_plan.get("tasks", [])),
            "missing_fields_per_task": sorted(expected_missing),
            "immutable_source_rewritten": False,
            "compiled_contract_repaired": True,
        }
    )

    # Source manual/null is deliberately recorded as a defect and rejected by
    # the compiled model-selection contract.
    source_selection_validator = _validator(selection_schema)
    manual_null = {
        "mode": "manual",
        "selected_model": None,
        "fallback_policy": "strict",
        "verification_policy": "system_required_verifiers",
        "locked_by_user": True,
    }
    if list(source_selection_validator.iter_errors(manual_null)):
        raise IntegrationError("pinned manual-null source Schema defect unexpectedly changed")
    compiled = _compiled_schemas()
    request_manual_null = {
        key: value
        for key, value in manual_null.items()
        if key not in {"locked_by_user", "selection_source"}
    }
    if not list(
        _validator(compiled["model-selection-request.schema.json"]).iter_errors(
            request_manual_null
        )
    ):
        raise IntegrationError("compiled model-selection Schema still accepts manual/null")
    findings.append(
        {
            "code": "SOURCE_MANUAL_NULL_MODEL_ACCEPTED",
            "path": "schemas/model-selection.schema.json",
            "immutable_source_rewritten": False,
            "compiled_contract_repaired": True,
        }
    )
    if "enum" in execution_schema["properties"]["model_alias"]:
        raise IntegrationError("pinned unconstrained execution model_alias defect changed")
    findings.append(
        {
            "code": "SOURCE_EXECUTION_MODEL_ALIAS_UNCONSTRAINED",
            "path": "schemas/execution-record.schema.json",
            "immutable_source_rewritten": False,
            "compiled_contract_repaired": True,
        }
    )
    for schema in compiled.values():
        _validator(schema)
    examples = _load_json_record(files, "examples/model-selection-examples.json")
    compiled_request_validator = _validator(
        compiled["model-selection-request.schema.json"]
    )
    compiled_resolved_validator = _validator(
        compiled["model-selection-resolved.schema.json"]
    )
    request_fields = set(
        compiled["model-selection-request.schema.json"]["properties"]
    )
    for label, example in examples.items():
        request = {key: value for key, value in example.items() if key in request_fields}
        request_errors = list(compiled_request_validator.iter_errors(request))
        if request_errors:
            raise IntegrationError(
                f"source positive model-selection request projection is invalid: {label}"
            )
        if not list(compiled_request_validator.iter_errors(example)):
            raise IntegrationError(
                f"compiled request Schema accepts server-derived source fields: {label}"
            )
        resolved = {
            **example,
            "resolved_at": "2026-01-01T00:00:00Z",
            "registry_digest": "sha256:" + "0" * 64,
        }
        if list(compiled_resolved_validator.iter_errors(resolved)):
            raise IntegrationError(
                f"compiled resolved model-selection projection is invalid: {label}"
            )
    _validate_dag()
    findings.append(
        {
            "code": "SOURCE_MANIFEST_HAS_NO_DEPENDENCY_DAG",
            "path": "manifest.json",
            "source_workflow_skill_count": len(workflow_names),
            "compiled_dag_skill_count": len(DAG_DEPENDENCIES),
            "immutable_source_rewritten": False,
            "compiled_contract_repaired": True,
        }
    )
    return tuple(findings), tuple(workflow_names)


def validate_archive(
    archive_path: Path, *, yaml_loader: YamlLoader | None = None
) -> PackageSnapshot:
    yaml_loader = yaml_loader or _default_yaml_loader
    archive_bytes, records = inspect_archive(archive_path)
    files = {path: record for path, record in records.items() if record.kind == "file"}
    directories = tuple(sorted(path for path, record in records.items() if record.kind == "directory"))
    if len(files) != EXPECTED_FILE_COUNT or len(directories) != EXPECTED_DIRECTORY_COUNT:
        raise IntegrationError("archive file/directory inventory count mismatch")
    category_counts: Counter[str] = Counter()
    for path in files:
        category_counts[path.split("/", 1)[0] if "/" in path else "(root)"] += 1
    if category_counts != Counter(EXPECTED_CATEGORY_COUNTS):
        raise IntegrationError(f"source category inventory mismatch: {dict(category_counts)!r}")
    skills = _parse_source_skills(files, yaml_loader)
    findings, workflow_names = _validate_source_contracts(files, yaml_loader)
    source_names = set(files) | set(directories)
    prohibited = {
        path for path in source_names
        if PurePosixPath(path).name.lower() in {
            "checksums.sha256", "license", "license.md", "license.txt", "sbom.json",
            "provenance.json", "signature", "signature.sig",
        }
    }
    if prohibited:
        raise IntegrationError(f"pinned source absence facts changed: {sorted(prohibited)}")
    return PackageSnapshot(
        archive_sha256=_sha256(archive_bytes),
        archive_bytes=len(archive_bytes),
        entry_count=len(records),
        uncompressed_bytes=sum(record.size for record in records.values()),
        files=dict(sorted(files.items())),
        directories=directories,
        skills=skills,
        source_findings=findings,
        workflow_names=workflow_names,
        topological_order=_validate_dag(),
    )


def load_runtime_registry(repository_root: Path) -> RuntimeRegistry:
    path = repository_root / RUNTIME_REGISTRY_RELATIVE
    relative = RUNTIME_REGISTRY_RELATIVE.as_posix()
    if not path.exists() and not path.is_symlink():
        return RuntimeRegistry(False, relative, None, (), {}, {}, {})
    if path.is_symlink() or not path.is_file():
        raise IntegrationError(f"runtime registry must be a regular file: {relative}")
    content = path.read_bytes()
    try:
        document = json.loads(_decode_utf8(content, relative))
    except json.JSONDecodeError as exc:
        raise IntegrationError("runtime handler registry is invalid JSON") from exc
    if not isinstance(document, Mapping):
        raise IntegrationError("runtime handler registry must be an object")
    if (
        document.get("schema_version") != "elmos.repository-orchestrator.handler-registry.v1"
        or document.get("package") != PACKAGE_NAME
        or document.get("runtime_module") != RUNTIME_MODULE
        or document.get("runtime_callable") != RUNTIME_CALLABLE
    ):
        raise IntegrationError("runtime handler registry identity/binding mismatch")
    entries = document.get("skills")
    if not isinstance(entries, list) or len(entries) != len(EXPECTED_SKILLS):
        raise IntegrationError("runtime handler registry must contain exactly 37 entries")
    names: list[str] = []
    handlers: dict[str, str] = {}
    canonical_owners: dict[str, str] = {}
    adapter_requirements: dict[str, str | None] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise IntegrationError("runtime handler registry entry must be an object")
        name = entry.get("name")
        handler = entry.get("handler")
        canonical_owner = entry.get("canonical_owner")
        adapter_requirement = entry.get("adapter_requirement")
        if (
            not isinstance(name, str)
            or not isinstance(handler, str)
            or not handler
            or not isinstance(canonical_owner, str)
            or not canonical_owner
            or (adapter_requirement is not None and not isinstance(adapter_requirement, str))
        ):
            raise IntegrationError("runtime handler registry entry identity is invalid")
        if name in handlers:
            raise IntegrationError(f"runtime handler registry duplicates Skill: {name}")
        names.append(name)
        handlers[name] = handler
        canonical_owners[name] = canonical_owner
        adapter_requirements[name] = adapter_requirement
    if tuple(names) != EXPECTED_SKILLS:
        raise IntegrationError("runtime handler registry differs from source Skill order")
    return RuntimeRegistry(
        True,
        relative,
        _sha256(content),
        tuple(names),
        handlers,
        canonical_owners,
        adapter_requirements,
    )


def _yaml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def _display_name(name: str) -> str:
    acronyms = {"api": "API", "eta": "ETA", "idempotency": "Idempotency"}
    return " ".join(acronyms.get(word, word.capitalize()) for word in name.split("-"))


def _implementation_state(skill: SourceSkill, registry: RuntimeRegistry) -> str:
    """A static registry proves a binding exists, not that it was executed."""

    return "IMPLEMENTED" if skill.name in registry.handlers else "DECLARED"


def _local_evidence_state(_skill: SourceSkill, _registry: RuntimeRegistry) -> str:
    return "NOT_RUN"


def _activation(name: str) -> str:
    if name in CONDITIONAL_SKILLS:
        return "conditional"
    if name in CONTROL_SKILLS:
        return "control"
    if name in EXCEPTION_SKILLS:
        return "exception"
    if name in OFFLINE_SKILLS:
        return "offline"
    return "required"


def _render_skill(skill: SourceSkill, registry: RuntimeRegistry) -> bytes:
    implementation_state = _implementation_state(skill, registry)
    local_evidence_state = _local_evidence_state(skill, registry)
    metadata = {
        "package": PACKAGE_NAME,
        "package_version": PACKAGE_VERSION,
        "source_version": skill.version,
        "source_path": (SOURCE_RELATIVE / skill.source_path).as_posix(),
        "source_sha256": "sha256:" + skill.source_sha256,
        "namespace": NAMESPACE,
        "runtime_module": RUNTIME_MODULE,
        "runtime_callable": RUNTIME_CALLABLE,
        "runtime_handler": registry.handlers.get(skill.name, "UNDECLARED"),
        "canonical_owner": registry.canonical_owners.get(
            skill.name, "packages/repository-orchestrator:UNDECLARED"
        ),
        "implementation_state": implementation_state,
        "local_evidence": local_evidence_state,
        "external_evidence": EXTERNAL_EVIDENCE_STATUS,
        "certification": CERTIFICATION_STATUS,
    }
    frontmatter = [
        "---",
        f"name: {_yaml_quote(skill.name)}",
        f"description: {_yaml_quote(skill.description)}",
        "metadata:",
        *(f"  {key}: {_yaml_quote(value)}" for key, value in metadata.items()),
        "---",
        "",
    ]
    boundary = [
        "## Repository runtime binding",
        "",
        f"- Immutable package source: `{metadata['source_path']}` (`{metadata['source_sha256']}`).",
        f"- Shared source policy and schemas: `{SOURCE_RELATIVE.as_posix()}/config/` and `{SOURCE_RELATIVE.as_posix()}/schemas/`.",
        f"- Repository-corrected contracts and the exact 37-node DAG: `{DOC_RELATIVE.as_posix()}/compiled-schemas/` and `{DOC_RELATIVE.as_posix()}/dependency-dag.json`.",
        f"- Bounded dispatch binding: `{RUNTIME_MODULE}:{RUNTIME_CALLABLE}`; implementation state is `{implementation_state}` and local execution evidence is `{local_evidence_state}`.",
        "- Package-authored instructions below describe the capability; they do not authorize provider, SCM, worktree, network, secret, merge, deployment, or certification side effects.",
        f"- Provider/SCM/worktree external evidence remains `{EXTERNAL_EVIDENCE_STATUS}` and certification remains `{CERTIFICATION_STATUS}`.",
        "- Missing, blocked, partial, skipped, synthetic, or self-verified evidence never passes a required gate.",
        "",
        "## Immutable package guidance",
        "",
    ]
    return ("\n".join(frontmatter + boundary) + skill.body.rstrip() + "\n").encode("utf-8")


def _render_interface(skill: SourceSkill) -> bytes:
    short_description = "Run repository task routing with bounded evidence"
    default_prompt = (
        f"Use ${skill.name} to perform its bounded repository workflow with provenance and fail-closed evidence."
    )
    return (
        "\n".join(
            [
                "interface:",
                f"  display_name: {_yaml_quote(_display_name(skill.name))}",
                f"  short_description: {_yaml_quote(short_description)}",
                f"  default_prompt: {_yaml_quote(default_prompt)}",
                "",
            ]
        )
    ).encode("utf-8")


def _compiled_contract(skill: SourceSkill, registry: RuntimeRegistry) -> Mapping[str, Any]:
    return {
        "schema_version": "elmos.repository-task-router.compiled-skill.v1",
        "namespace": NAMESPACE,
        "package": {"id": PACKAGE_ID, "name": PACKAGE_NAME, "version": PACKAGE_VERSION},
        "source": {
            "ordinal": skill.ordinal,
            "name": skill.name,
            "version": skill.version,
            "path": (SOURCE_RELATIVE / skill.source_path).as_posix(),
            "sha256": "sha256:" + skill.source_sha256,
        },
        "dag": {
            "dependencies": list(DAG_DEPENDENCIES[skill.name]),
            "activation": _activation(skill.name),
        },
        "contract": {
            "triggers": list(skill.sections["Trigger conditions"]),
            "inputs": list(skill.sections["Inputs"]),
            "outputs": list(skill.sections["Outputs"]),
            "guardrails": list(skill.sections["Guardrails"]),
            "acceptance": list(skill.sections["Acceptance criteria"]),
        },
        "runtime_binding": {
            "module": RUNTIME_MODULE,
            "callable": RUNTIME_CALLABLE,
            "handler": registry.handlers.get(skill.name),
            "canonical_owner": registry.canonical_owners.get(skill.name),
            "adapter_requirement": registry.adapter_requirements.get(skill.name),
            "registry_path": registry.path,
            "registry_sha256": "sha256:" + registry.sha256 if registry.sha256 else None,
            "implementation_state": _implementation_state(skill, registry),
            "local_evidence_status": _local_evidence_state(skill, registry),
        },
        "external_evidence_status": EXTERNAL_EVIDENCE_STATUS,
        "certification_status": CERTIFICATION_STATUS,
    }


def _tree_digest(tree: TreeSpec) -> str:
    digest = hashlib.sha256()
    for directory in sorted(tree.directories):
        digest.update(b"D\0")
        digest.update(directory.encode("utf-8"))
        digest.update(b"\0000755\0")
    for relative, payload in sorted(tree.files.items()):
        digest.update(b"F\0")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(f"{payload.mode:04o}".encode("ascii"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(payload.content).digest())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def _aggregate_skill_digest(trees: Mapping[str, TreeSpec]) -> str:
    files: dict[str, FilePayload] = {}
    directories: list[str] = []
    for name, tree in sorted(trees.items()):
        directories.append(name)
        directories.extend(f"{name}/{directory}" for directory in tree.directories)
        files.update({f"{name}/{path}": payload for path, payload in tree.files.items()})
    return _tree_digest(TreeSpec(files, tuple(directories)))


def _dependency_document(snapshot: PackageSnapshot) -> Mapping[str, Any]:
    nodes = []
    for name in snapshot.topological_order:
        nodes.append(
            {
                "name": name,
                "source_ordinal": EXPECTED_SKILLS.index(name),
                "activation": _activation(name),
                "depends_on": list(DAG_DEPENDENCIES[name]),
            }
        )
    return {
        "schema_version": "elmos.repository-task-router.dependency-dag.v1",
        "package": PACKAGE_NAME,
        "package_version": PACKAGE_VERSION,
        "authority": "repository-compiled-contract",
        "source_manifest_declared_dag": False,
        "node_count": len(nodes),
        "edge_count": sum(len(item) for item in DAG_DEPENDENCIES.values()),
        "acyclic": True,
        "topological_order": list(snapshot.topological_order),
        "nodes": nodes,
    }


def _readme(snapshot: PackageSnapshot, registry: RuntimeRegistry) -> bytes:
    implemented_count = sum(
        _implementation_state(skill, registry) == "IMPLEMENTED"
        for skill in snapshot.skills
    )
    return f"""# Repository task-router Skills integration

This repository-owned integration treats `{ARCHIVE_RELATIVE.as_posix()}` as untrusted input. The importer reads every member as bounded data, never executes package scripts/tests/instructions, and preserves exact source bytes under `{SOURCE_RELATIVE.as_posix()}`.

The 37 normalized Skills are installed byte-identically under `{INSTALL_ROOTS[0].as_posix()}` and `{INSTALL_ROOTS[1].as_posix()}`. Unsupported source `version` frontmatter is retained as `metadata.source_version`; each installed folder matches its exact Skill name and includes quoted `agents/openai.yaml` metadata.

The source package has no manifest-owned dependency DAG, checksum inventory, signature, license, SBOM, or provenance attestation. `dependency-dag.json` is the authoritative repository-compiled 37-node graph. Corrected schemas live under `compiled-schemas/`; immutable source defects are recorded rather than rewritten.

The compiled model-selection contracts separate caller input from a server-resolved, registry-bound record: request payloads cannot forge `selection_source`, `locked_by_user`, `resolved_at`, or `registry_digest`. Atomic tasks may omit stage-owned `complexity` and `status` until their estimator/journal stages. Execution cost is optional; when recorded it is an exact decimal string and must include currency, effective pricing time, and a pricing-registry digest.

- Bounded implementation bindings: `{implemented_count}/37` (`IMPLEMENTED` only when declared by `{registry.path}`)
- Local execution evidence: `NOT_RUN`
- Provider, SCM, and worktree evidence: `{EXTERNAL_EVIDENCE_STATUS}`
- Certification: `{CERTIFICATION_STATUS}`
- Source package code executed by importer: `false`

`IMPLEMENTED` means a bounded repository handler is statically bound; it does not mean the handler was executed or passed. It is not proof of provider availability, model identity, price freshness, worktree isolation, SCM mutation, merge, deployment, customer acceptance, or certification.
""".encode("utf-8")


def build_expected(snapshot: PackageSnapshot, repository_root: Path = ROOT) -> Mapping[str, Any]:
    registry = load_runtime_registry(repository_root)
    source_files = {
        path: FilePayload(record.content or b"", 0o644)
        for path, record in snapshot.files.items()
    }
    source_directories = tuple(path for path in snapshot.directories if path)
    source_tree = TreeSpec(source_files, source_directories)

    skill_trees: dict[str, TreeSpec] = {}
    skill_records: list[Mapping[str, Any]] = []
    for skill in snapshot.skills:
        contract = _compiled_contract(skill, registry)
        tree = TreeSpec(
            {
                "SKILL.md": FilePayload(_render_skill(skill, registry)),
                "agents/openai.yaml": FilePayload(_render_interface(skill)),
                "compiled-contract.json": FilePayload(_json_bytes(contract)),
            },
            ("agents",),
        )
        skill_trees[skill.name] = tree
        skill_records.append(
            {
                "ordinal": skill.ordinal,
                "name": skill.name,
                "source_version": skill.version,
                "source_path": (SOURCE_RELATIVE / skill.source_path).as_posix(),
                "source_sha256": "sha256:" + skill.source_sha256,
                "activation": _activation(skill.name),
                "depends_on": list(DAG_DEPENDENCIES[skill.name]),
                "installed_tree_sha256": _tree_digest(tree),
                "installed_files": [
                    {
                        "path": path,
                        "bytes": len(payload.content),
                        "sha256": "sha256:" + _sha256(payload.content),
                        "mode": f"{payload.mode:04o}",
                    }
                    for path, payload in sorted(tree.files.items())
                ],
                "runtime_handler": registry.handlers.get(skill.name),
                "canonical_owner": registry.canonical_owners.get(skill.name),
                "adapter_requirement": registry.adapter_requirements.get(skill.name),
                "implementation_state": _implementation_state(skill, registry),
                "local_evidence_status": _local_evidence_state(skill, registry),
                "external_evidence_status": EXTERNAL_EVIDENCE_STATUS,
                "certification_status": CERTIFICATION_STATUS,
            }
        )

    compiled_schemas = _compiled_schemas()
    dag = _dependency_document(snapshot)
    dag_bytes = _json_bytes(dag)
    schema_files = {
        f"compiled-schemas/{name}": FilePayload(_json_bytes(schema))
        for name, schema in compiled_schemas.items()
    }
    source_inventory = [
        {
            "path": path,
            "bytes": record.size,
            "compressed_bytes": record.compressed_size,
            "sha256": "sha256:" + str(record.sha256),
            "source_mode": f"{record.source_mode:04o}",
            "installed_mode": "0644",
        }
        for path, record in snapshot.files.items()
    ]
    source_directory_inventory = [
        {
            "path": path or ".",
            "source_mode": "2755",
            "installed_mode": "0755",
        }
        for path in snapshot.directories
    ]
    aggregate_digest = _aggregate_skill_digest(skill_trees)
    installed_manifest = {
        "schema_version": "elmos.repository-task-router.installed-manifest.v1",
        "namespace": NAMESPACE,
        "package": {"id": PACKAGE_ID, "name": PACKAGE_NAME, "version": PACKAGE_VERSION},
        "archive": {
            "path": ARCHIVE_RELATIVE.as_posix(),
            "sha256": "sha256:" + snapshot.archive_sha256,
            "bytes": snapshot.archive_bytes,
            "entries": snapshot.entry_count,
            "files": len(snapshot.files),
            "directories": len(snapshot.directories),
            "uncompressed_bytes": snapshot.uncompressed_bytes,
            "single_root": ARCHIVE_ROOT,
        },
        "canonical_source": {
            "path": SOURCE_RELATIVE.as_posix(),
            "immutable": True,
            "tree_sha256": _tree_digest(source_tree),
            "files": source_inventory,
            "directories": source_directory_inventory,
        },
        "source_absence_facts": SOURCE_ABSENCE_FACTS,
        "source_content_executed": False,
        "source_instructions_promoted_to_repository_authority": False,
        "source_findings": list(snapshot.source_findings),
        "dependency_dag": {
            "path": (DOC_RELATIVE / "dependency-dag.json").as_posix(),
            "sha256": "sha256:" + _sha256(dag_bytes),
            "nodes": len(DAG_DEPENDENCIES),
            "edges": sum(len(item) for item in DAG_DEPENDENCIES.values()),
            "acyclic": True,
            "authority": "repository-compiled-contract",
        },
        "runtime_registry": {
            "present": registry.present,
            "path": registry.path,
            "sha256": "sha256:" + registry.sha256 if registry.sha256 else None,
            "declared_handlers": len(registry.names),
            "module": RUNTIME_MODULE,
            "callable": RUNTIME_CALLABLE,
        },
        "install_roots": [path.as_posix() for path in INSTALL_ROOTS],
        "installed_skill_count_per_root": len(skill_trees),
        "installed_tree_sha256_per_root": aggregate_digest,
        "dual_root_byte_identical": True,
        "implementation_states": {
            "IMPLEMENTED": sum(record["implementation_state"] == "IMPLEMENTED" for record in skill_records),
            "DECLARED": sum(record["implementation_state"] == "DECLARED" for record in skill_records),
        },
        "local_evidence_status": "NOT_RUN",
        "external_evidence_status": EXTERNAL_EVIDENCE_STATUS,
        "certification_status": CERTIFICATION_STATUS,
        "skills": skill_records,
    }
    docs_base_files: dict[str, FilePayload] = {
        **schema_files,
        "dependency-dag.json": FilePayload(dag_bytes),
        "README.md": FilePayload(_readme(snapshot, registry)),
    }
    installed_manifest["managed_output"] = {
        "schema_version": "elmos.repository-task-router.generated-tree.v1",
        "generator": "tooling/integrate_repository_task_router_skills.py",
        "root": DOC_RELATIVE.as_posix(),
        "archive_sha256": "sha256:" + snapshot.archive_sha256,
        "directories": ["compiled-schemas"],
        "files_excluding_manifest": [
            {
                "path": path,
                "bytes": len(payload.content),
                "sha256": "sha256:" + _sha256(payload.content),
                "mode": f"{payload.mode:04o}",
            }
            for path, payload in sorted(docs_base_files.items())
        ],
    }
    docs_files: dict[str, FilePayload] = {
        **docs_base_files,
        "installed-manifest.json": FilePayload(_json_bytes(installed_manifest)),
    }
    return {
        "source_tree": source_tree,
        "skill_trees": dict(sorted(skill_trees.items())),
        "docs_tree": TreeSpec(docs_files, ("compiled-schemas",)),
        "installed_manifest": installed_manifest,
        "runtime_registry": registry,
    }


def _resolve_below(repository_root: Path, relative: Path) -> Path:
    root = repository_root.resolve()
    destination = (root / relative).resolve(strict=False)
    try:
        destination.relative_to(root)
    except ValueError as exc:
        raise IntegrationError(f"managed path escapes repository root: {relative}") from exc
    current = root
    for part in relative.parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise IntegrationError(f"managed path traverses a symlink: {current}")
        if current.exists() and not current.is_dir():
            raise IntegrationError(f"managed parent is not a directory: {current}")
    return destination


def _read_tree(root: Path) -> TreeSpec:
    if root.is_symlink() or not root.is_dir():
        raise IntegrationError(f"managed tree is missing or unsafe: {root}")
    if stat.S_IMODE(root.stat().st_mode) != 0o755:
        raise IntegrationError(f"managed root directory mode is not 0755: {root}")
    files: dict[str, FilePayload] = {}
    directories: list[str] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise IntegrationError(f"managed tree contains a symlink: {path}")
        if path.is_dir():
            if stat.S_IMODE(path.stat().st_mode) != 0o755:
                raise IntegrationError(f"managed directory mode is not 0755: {path}")
            directories.append(relative)
        elif path.is_file():
            files[relative] = FilePayload(path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
        else:
            raise IntegrationError(f"managed tree contains a special file: {path}")
    return TreeSpec(dict(sorted(files.items())), tuple(sorted(directories)))


def _managed_actions(repository_root: Path, expected: Mapping[str, Any]) -> tuple[ManagedAction, ...]:
    actions = [
        ManagedAction(
            "immutable source",
            _resolve_below(repository_root, SOURCE_RELATIVE),
            expected["source_tree"],
        )
    ]
    for install_root in INSTALL_ROOTS:
        for name, tree in expected["skill_trees"].items():
            actions.append(
                ManagedAction(
                    f"{install_root.as_posix()} Skill {name}",
                    _resolve_below(repository_root, install_root / name),
                    tree,
                )
            )
    actions.append(
        ManagedAction(
            "integration documentation",
            _resolve_below(repository_root, DOC_RELATIVE),
            expected["docs_tree"],
        )
    )
    return tuple(actions)


def _compare_action(action: ManagedAction) -> None:
    observed = _read_tree(action.destination)
    if observed != action.tree:
        missing = sorted(set(action.tree.files) - set(observed.files))
        extra = sorted(set(observed.files) - set(action.tree.files))
        changed = sorted(
            path for path in set(observed.files) & set(action.tree.files)
            if observed.files[path] != action.tree.files[path]
        )
        raise IntegrationError(
            f"{action.label} drifted: missing={missing}, extra={extra}, changed={changed}, "
            f"directory_drift={observed.directories != action.tree.directories}"
        )


def _verify_managed_documentation(
    destination: Path,
    snapshot: PackageSnapshot,
) -> TreeSpec:
    """Accept only an exact legacy digest or a self-inventoried prior output."""

    observed = _read_tree(destination)
    if _tree_digest(observed) in LEGACY_MANAGED_DOC_TREE_SHA256S:
        return observed
    manifest_payload = observed.files.get("installed-manifest.json")
    if manifest_payload is None or manifest_payload.mode != 0o644:
        raise IntegrationError("documentation tree has no safe installed-manifest receipt")
    try:
        manifest = json.loads(
            _decode_utf8(manifest_payload.content, "installed-manifest.json")
        )
    except json.JSONDecodeError as exc:
        raise IntegrationError("documentation ownership receipt is invalid JSON") from exc
    if not isinstance(manifest, Mapping):
        raise IntegrationError("documentation ownership receipt must be an object")
    package = manifest.get("package")
    archive = manifest.get("archive")
    receipt = manifest.get("managed_output")
    if (
        manifest.get("schema_version")
        != "elmos.repository-task-router.installed-manifest.v1"
        or package
        != {"id": PACKAGE_ID, "name": PACKAGE_NAME, "version": PACKAGE_VERSION}
        or not isinstance(archive, Mapping)
        or archive.get("sha256") != "sha256:" + snapshot.archive_sha256
        or manifest.get("source_content_executed") is not False
        or manifest.get("source_instructions_promoted_to_repository_authority") is not False
        or not isinstance(receipt, Mapping)
        or receipt.get("schema_version")
        != "elmos.repository-task-router.generated-tree.v1"
        or receipt.get("generator")
        != "tooling/integrate_repository_task_router_skills.py"
        or receipt.get("root") != DOC_RELATIVE.as_posix()
        or receipt.get("archive_sha256") != "sha256:" + snapshot.archive_sha256
    ):
        raise IntegrationError("documentation ownership receipt identity mismatch")
    directories = receipt.get("directories")
    if not isinstance(directories, list) or not all(
        isinstance(item, str) for item in directories
    ):
        raise IntegrationError("documentation ownership directory inventory is malformed")
    if tuple(directories) != observed.directories:
        raise IntegrationError("documentation ownership directory inventory drifted")
    inventory = receipt.get("files_excluding_manifest")
    if not isinstance(inventory, list):
        raise IntegrationError("documentation ownership file inventory is malformed")
    expected_paths = set(observed.files) - {"installed-manifest.json"}
    recorded_paths: set[str] = set()
    for record in inventory:
        if not isinstance(record, Mapping) or set(record) != {
            "path",
            "bytes",
            "sha256",
            "mode",
        }:
            raise IntegrationError("documentation ownership file record is malformed")
        path = record.get("path")
        if not isinstance(path, str) or path == "installed-manifest.json":
            raise IntegrationError("documentation ownership file path is malformed")
        _validated_relative_path(path, "managed documentation receipt")
        folded = unicodedata.normalize("NFC", path).casefold()
        if folded in {item.casefold() for item in recorded_paths}:
            raise IntegrationError("documentation ownership file inventory has a collision")
        recorded_paths.add(path)
        payload = observed.files.get(path)
        if (
            payload is None
            or record.get("bytes") != len(payload.content)
            or record.get("sha256") != "sha256:" + _sha256(payload.content)
            or record.get("mode") != f"{payload.mode:04o}"
        ):
            raise IntegrationError(f"documentation ownership file drifted: {path}")
    if recorded_paths != expected_paths:
        raise IntegrationError("documentation ownership file inventory is incomplete")
    return observed


def _managed_skill_receipts(
    repository_root: Path,
    snapshot: PackageSnapshot,
) -> Mapping[str, Mapping[str, Any]]:
    documentation = _resolve_below(repository_root, DOC_RELATIVE)
    observed = _verify_managed_documentation(documentation, snapshot)
    try:
        manifest = json.loads(
            _decode_utf8(
                observed.files["installed-manifest.json"].content,
                "installed-manifest.json",
            )
        )
    except (KeyError, json.JSONDecodeError) as exc:
        raise IntegrationError("installed Skill ownership manifest is invalid") from exc
    records = manifest.get("skills") if isinstance(manifest, Mapping) else None
    if not isinstance(records, list) or tuple(
        record.get("name") if isinstance(record, Mapping) else None
        for record in records
    ) != EXPECTED_SKILLS:
        raise IntegrationError("installed Skill ownership manifest identity drifted")
    by_source_name = {skill.name: skill for skill in snapshot.skills}
    receipts: dict[str, Mapping[str, Any]] = {}
    for record in records:
        assert isinstance(record, Mapping)
        name = str(record["name"])
        source = by_source_name[name]
        if (
            record.get("source_path")
            != (SOURCE_RELATIVE / source.source_path).as_posix()
            or record.get("source_sha256") != "sha256:" + source.source_sha256
            or record.get("installed_tree_sha256") is None
            or not isinstance(record.get("installed_files"), list)
        ):
            raise IntegrationError(f"installed Skill ownership receipt drifted: {name}")
        receipts[name] = record
    return receipts


def _verify_managed_skill(
    destination: Path,
    name: str,
    receipt: Mapping[str, Any],
) -> TreeSpec:
    observed = _read_tree(destination)
    if observed.directories != ("agents",):
        raise IntegrationError(f"installed Skill directory inventory drifted: {name}")
    if receipt.get("installed_tree_sha256") != _tree_digest(observed):
        raise IntegrationError(f"installed Skill tree digest drifted: {name}")
    inventory = receipt.get("installed_files")
    if not isinstance(inventory, list):
        raise IntegrationError(f"installed Skill file inventory is malformed: {name}")
    recorded_paths: set[str] = set()
    for record in inventory:
        if not isinstance(record, Mapping) or set(record) != {
            "path",
            "bytes",
            "sha256",
            "mode",
        }:
            raise IntegrationError(f"installed Skill file receipt is malformed: {name}")
        path = record.get("path")
        if not isinstance(path, str):
            raise IntegrationError(f"installed Skill file path is malformed: {name}")
        _validated_relative_path(path, "installed Skill receipt")
        folded = path.casefold()
        if folded in {item.casefold() for item in recorded_paths}:
            raise IntegrationError(f"installed Skill receipt has a collision: {name}")
        recorded_paths.add(path)
        payload = observed.files.get(path)
        if (
            payload is None
            or record.get("bytes") != len(payload.content)
            or record.get("sha256") != "sha256:" + _sha256(payload.content)
            or record.get("mode") != f"{payload.mode:04o}"
        ):
            raise IntegrationError(f"installed Skill file drifted: {name}/{path}")
    if recorded_paths != set(observed.files):
        raise IntegrationError(f"installed Skill file inventory is incomplete: {name}")
    return observed


def _stage_tree(destination: Path, tree: TreeSpec) -> None:
    destination.mkdir()
    os.chmod(destination, 0o755)
    for directory in sorted(tree.directories, key=lambda item: (item.count("/"), item)):
        relative = _validated_relative_path(directory, "managed directory")
        path = destination.joinpath(*relative.parts)
        path.mkdir(parents=True, exist_ok=False)
        os.chmod(path, 0o755)
    for relative_value, payload in sorted(tree.files.items()):
        relative = _validated_relative_path(relative_value, "managed file")
        path = destination.joinpath(*relative.parts)
        if not path.parent.is_dir() or path.exists() or path.is_symlink():
            raise IntegrationError(f"unsafe staged file destination: {path}")
        path.write_bytes(payload.content)
        os.chmod(path, payload.mode)
    if _read_tree(destination) != tree:
        raise IntegrationError(f"staged managed tree differs: {destination}")


def _check_expected(repository_root: Path, expected: Mapping[str, Any]) -> None:
    for action in _managed_actions(repository_root, expected):
        _compare_action(action)
    left_root, right_root = INSTALL_ROOTS
    for name in EXPECTED_SKILLS:
        left = _read_tree(_resolve_below(repository_root, left_root / name))
        right = _read_tree(_resolve_below(repository_root, right_root / name))
        if left != right:
            raise IntegrationError(f"dual installed roots differ: {name}")


def write_integration(
    repository_root: Path,
    archive_path: Path,
    *,
    yaml_loader: YamlLoader | None = None,
) -> PackageSnapshot:
    repository_root = repository_root.resolve()
    if repository_root.is_symlink() or not repository_root.is_dir():
        raise IntegrationError(f"repository root must be a real directory: {repository_root}")
    snapshot = validate_archive(archive_path, yaml_loader=yaml_loader)
    expected = build_expected(snapshot, repository_root)
    actions = _managed_actions(repository_root, expected)
    skill_destinations = {
        _resolve_below(repository_root, install_root / name): name
        for install_root in INSTALL_ROOTS
        for name in EXPECTED_SKILLS
    }
    skill_receipts: Mapping[str, Mapping[str, Any]] | None = None
    missing: list[ManagedAction] = []
    refresh: list[tuple[ManagedAction, TreeSpec]] = []
    for action in actions:
        if action.destination.exists() or action.destination.is_symlink():
            if action.destination.is_symlink():
                raise IntegrationError(f"refusing managed symlink collision: {action.destination}")
            try:
                _compare_action(action)
            except IntegrationError as exc:
                if action.destination == _resolve_below(repository_root, DOC_RELATIVE):
                    try:
                        previous = _verify_managed_documentation(
                            action.destination,
                            snapshot,
                        )
                    except IntegrationError as ownership_exc:
                        raise IntegrationError(
                            "refusing unowned, incomplete, or drifted collision: "
                            f"{action.destination}: {ownership_exc}"
                        ) from ownership_exc
                    refresh.append((action, previous))
                elif action.destination in skill_destinations:
                    name = skill_destinations[action.destination]
                    try:
                        if skill_receipts is None:
                            skill_receipts = _managed_skill_receipts(
                                repository_root,
                                snapshot,
                            )
                        previous = _verify_managed_skill(
                            action.destination,
                            name,
                            skill_receipts[name],
                        )
                    except (KeyError, IntegrationError) as ownership_exc:
                        raise IntegrationError(
                            "refusing unowned, incomplete, or drifted collision: "
                            f"{action.destination}: {ownership_exc}"
                        ) from ownership_exc
                    refresh.append((action, previous))
                else:
                    raise IntegrationError(
                        "refusing unowned, incomplete, or drifted collision: "
                        f"{action.destination}: {exc}"
                    ) from exc
        else:
            missing.append(action)

    changes = [
        (action, None) for action in missing
    ] + refresh
    if changes:
        with tempfile.TemporaryDirectory(prefix=".repository-task-router-install-", dir=repository_root) as temporary:
            transaction_root = Path(temporary)
            staged_root = transaction_root / "staged"
            rollback_root = transaction_root / "rollback"
            discard_root = transaction_root / "discard"
            staged_root.mkdir()
            rollback_root.mkdir()
            discard_root.mkdir()
            staged: list[Path] = []
            for index, (action, _previous) in enumerate(changes):
                stage = staged_root / f"{index:03d}"
                _stage_tree(stage, action.tree)
                staged.append(stage)
            committed: list[tuple[int, ManagedAction, Path | None]] = []
            try:
                for index, ((action, previous), stage) in enumerate(
                    zip(changes, staged, strict=True)
                ):
                    action.destination.parent.mkdir(parents=True, exist_ok=True)
                    previous_path: Path | None = None
                    if previous is None:
                        if action.destination.exists() or action.destination.is_symlink():
                            raise IntegrationError(
                                f"managed destination appeared concurrently: {action.destination}"
                            )
                    else:
                        if _read_tree(action.destination) != previous:
                            raise IntegrationError(
                                f"managed documentation changed before refresh: {action.destination}"
                            )
                        previous_path = rollback_root / f"{index:03d}.previous"
                        os.replace(action.destination, previous_path)
                    try:
                        if action.destination.exists() or action.destination.is_symlink():
                            raise IntegrationError(
                                f"managed destination reappeared concurrently: {action.destination}"
                            )
                        os.replace(stage, action.destination)
                    except BaseException as replace_exc:
                        if previous_path is not None:
                            if action.destination.exists() or action.destination.is_symlink():
                                raise IntegrationError(
                                    "refresh failed and a concurrent collision prevents "
                                    f"restoring {action.destination}"
                                ) from replace_exc
                            os.replace(previous_path, action.destination)
                        raise
                    committed.append((index, action, previous_path))
                _check_expected(repository_root, expected)
            except BaseException as exc:
                rollback_errors: list[str] = []
                for index, action, previous_path in reversed(committed):
                    try:
                        if _read_tree(action.destination) != action.tree:
                            raise IntegrationError("committed tree changed before rollback")
                        os.replace(action.destination, discard_root / f"{index:03d}.new")
                        if previous_path is not None:
                            if not previous_path.is_dir() or action.destination.exists():
                                raise IntegrationError(
                                    "previous documentation tree cannot be restored"
                                )
                            os.replace(previous_path, action.destination)
                    except (OSError, IntegrationError) as rollback_exc:
                        rollback_errors.append(f"{action.destination}: {rollback_exc}")
                if rollback_errors:
                    raise IntegrationError(
                        f"installation failed and rollback was incomplete: {rollback_errors}"
                    ) from exc
                raise
    _check_expected(repository_root, expected)
    return snapshot


def check_integration(
    repository_root: Path,
    archive_path: Path,
    *,
    yaml_loader: YamlLoader | None = None,
) -> PackageSnapshot:
    repository_root = repository_root.resolve()
    snapshot = validate_archive(archive_path, yaml_loader=yaml_loader)
    expected = build_expected(snapshot, repository_root)
    _check_expected(repository_root, expected)
    return snapshot


def _summary(snapshot: PackageSnapshot, repository_root: Path, decision: str) -> Mapping[str, Any]:
    registry = load_runtime_registry(repository_root)
    return {
        "decision": decision,
        "package": f"{PACKAGE_NAME}@{PACKAGE_VERSION}",
        "archive_sha256": "sha256:" + snapshot.archive_sha256,
        "archive_bytes": snapshot.archive_bytes,
        "entries": snapshot.entry_count,
        "files": len(snapshot.files),
        "directories": len(snapshot.directories),
        "uncompressed_bytes": snapshot.uncompressed_bytes,
        "skills": len(snapshot.skills),
        "dag_edges": sum(len(item) for item in DAG_DEPENDENCIES.values()),
        "source_findings": len(snapshot.source_findings),
        "source_content_executed": False,
        "local_handlers": len(registry.names),
        "external_evidence_status": EXTERNAL_EVIDENCE_STATUS,
        "certification_status": CERTIFICATION_STATUS,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--write", action="store_true", help="safely extract and install")
    operation.add_argument("--check", action="store_true", help="verify source identity and drift")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--archive", type=Path)
    arguments = parser.parse_args(argv)
    repository_root = arguments.root.resolve()
    archive_path = arguments.archive.resolve() if arguments.archive else repository_root / ARCHIVE_RELATIVE
    try:
        if arguments.write:
            snapshot = write_integration(repository_root, archive_path)
            decision = "SOURCE_EXTRACTED_AND_SKILLS_INSTALLED"
        else:
            snapshot = check_integration(repository_root, archive_path)
            decision = "INSTALLATION_VERIFIED"
    except IntegrationError as exc:
        print(json.dumps({"decision": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(_summary(snapshot, repository_root, decision), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
