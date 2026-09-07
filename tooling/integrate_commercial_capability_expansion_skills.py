#!/usr/bin/env python3
"""Securely compile the pinned Commercial Capability Expansion Skill package.

The ZIP is untrusted declarative input. This importer never imports or runs
package Python, Rego, prompts, workflows, or Skill instructions. It validates
the complete archive in memory before any write, preserves an immutable source
mirror, and installs repository-owned bounded wrappers rather than source
instructions.
"""

from __future__ import annotations

import argparse
import binascii
from collections import Counter, defaultdict, deque
from contextlib import contextmanager
import ctypes
from dataclasses import dataclass
from datetime import datetime, timezone
import errno
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
from typing import Any, Iterable, Iterator, Mapping, Sequence
import unicodedata
import zipfile

try:
    import yaml
    from jsonschema import Draft202012Validator
except ModuleNotFoundError as exc:  # pragma: no cover - dependency bootstrap
    raise SystemExit(
        "PyYAML and jsonschema are required; use "
        "`make commercial-capability-expansion-skills`"
    ) from exc


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIRECTORY = "elmos-commercial-capability-expansion-skills-v2.0.0"
PACKAGE_ID = PACKAGE_DIRECTORY
PACKAGE_NAME = "elmos-commercial-capability-expansion-skills"
PACKAGE_VERSION = "2.0.0"
PACKAGE_GENERATED = "2026-08-29"

PRIMARY_ARCHIVE_RELATIVE = Path("skills/subskills") / f"{PACKAGE_DIRECTORY}.zip"
FALLBACK_ARCHIVE_RELATIVE = (
    Path("skills/subskills/sub") / f"{PACKAGE_DIRECTORY}.zip"
)
SOURCE_RELATIVE = Path("skills") / PACKAGE_DIRECTORY
WORKSPACE_SKILLS_RELATIVE = Path(".agents/skills")
RUNTIME_SKILLS_RELATIVE = Path("agent-skills/runtime")
CATALOG_RELATIVE = Path(
    "docs/commercial-capability-expansion/COMPILED_SKILL_CATALOG.json"
)
RECEIPT_RELATIVE = Path(
    "docs/commercial-capability-expansion/QUALIFICATION_RECEIPT.json"
)
COMPILER_RELATIVE = "tooling/integrate_commercial_capability_expansion_skills.py"
MASTER_SKILL_NAME = "elmos-commercial-capability-expansion"

EXPECTED_ARCHIVE_SHA256 = (
    "7a73cf924f4ebab3eddba327ba4feeb64b8575e39f2baf03fc53315cbc868380"
)
EXPECTED_ARCHIVE_BYTES = 161_254
EXPECTED_MEMBER_COUNT = 105
EXPECTED_UNCOMPRESSED_BYTES = 294_029

# Defensive parser bounds; they are not capability or certification claims.
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024
MAX_MEMBER_BYTES = 512 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 8 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100.0
READ_CHUNK_BYTES = 64 * 1024
MAX_MANAGED_OUTPUT_BYTES = 2 * 1024 * 1024
MAX_MANAGED_TREE_FILES = 512
MAX_MANAGED_TREE_BYTES = 8 * 1024 * 1024

EXPECTED_SKILLS_BY_KERNEL: dict[str, tuple[str, ...]] = {
    "K1-skill-runtime": (
        "universal-agent-skill-runtime",
        "progressive-skill-disclosure",
        "context-aware-skill-source",
        "skill-registry-ingestion",
        "skill-sandbox-runner",
        "skill-version-provenance",
        "model-tool-skill-router",
        "human-approval-message-injection",
        "durable-agent-workflow",
        "task-checkpoint-time-travel",
    ),
    "K2-repository-intelligence": (
        "polyglot-syntax-front-end",
        "semantic-symbol-index",
        "repository-semantic-code-graph",
        "cross-repository-impact-analysis",
        "dependency-build-graph-discovery",
        "runtime-evidence-graph",
        "repository-slicing-context-pack",
        "affected-test-selection",
        "software-catalog-ownership-graph",
        "change-risk-classifier",
    ),
    "K3-transformation": (
        "multi-engine-rewrite-router",
        "compiler-api-rewrite",
        "semantic-ir-lift-lower",
        "behavioral-equivalence-migration",
        "framework-modernization-router",
        "api-contract-preserving-transform",
        "concurrency-semantics-transform",
        "build-system-migration",
        "configuration-iac-migration",
        "transformation-explainability-ledger",
    ),
    "K4-build-execution": (
        "hermetic-build-environment",
        "untrusted-code-microvm-sandbox",
        "reproducible-build-verifier",
        "remote-execution-cache-planner",
        "resource-quota-budget-enforcer",
        "deterministic-toolchain-lock",
        "environment-capture-replay",
        "native-runtime-lab",
        "fault-injection-chaos-execution",
    ),
    "K5-verification": (
        "compiler-grade-certification-gate",
        "differential-runtime-verification",
        "continuous-fuzz-certification",
        "property-based-test-generation",
        "api-schema-fuzz-testing",
        "contract-compatibility-verification",
        "browser-e2e-trace-verification",
        "static-dataflow-assurance",
        "formal-proof-router",
        "metamorphic-equivalence-testing",
        "mutation-strength-certification",
        "performance-regression-certification",
        "golden-route-corpus-manager",
        "evidence-gate-orchestrator",
    ),
    "K6-security-governance": (
        "policy-as-code-kernel",
        "fine-grained-authorization-engine",
        "secret-egress-control",
        "prompt-injection-tool-boundary",
        "sbom-vulnerability-attestation",
        "slsa-in-toto-provenance",
        "artifact-signing-verification",
        "license-compliance-scanner",
        "multi-tenant-isolation-certifier",
        "kubernetes-policy-certification",
    ),
    "K7-database-data": (
        "database-semantic-compiler",
        "schema-metadata-discovery",
        "sql-dialect-transpiler",
        "stored-routine-migration",
        "transaction-semantic-equivalence",
        "query-plan-performance-equivalence",
        "data-lineage-impact-analysis",
        "data-migration-reconciliation",
        "cdc-shadow-compare",
        "database-security-policy-migration",
    ),
    "K8-observability-evolution": (
        "otel-agent-execution-tracing",
        "agent-evidence-evaluation",
        "trajectory-dataset-versioning",
        "failure-attribution-learning",
        "self-evolving-skill-factory",
        "automatic-task-corpus-generation",
        "skill-promotion-canary",
        "software-catalog-production-scorecard",
        "feature-flag-progressive-rollout",
        "incident-replay-root-cause",
        "cost-latency-quality-optimizer",
        "platform-template-generator",
    ),
}
EXPECTED_SKILL_NAMES = tuple(
    name for names in EXPECTED_SKILLS_BY_KERNEL.values() for name in names
)
EXPECTED_SKILL_COUNT = 85
EXPECTED_KERNEL_COUNTS = {
    kernel: len(names) for kernel, names in EXPECTED_SKILLS_BY_KERNEL.items()
}
EXPECTED_PRIORITY_COUNTS = {"P0": 68, "P1": 17, "P2": 0}

EXPECTED_MARKDOWN_HEADINGS = {
    "README.md": "# Elmos Commercial Capability Expansion Skills v2.0.0",
    "ROADMAP.md": "# Delivery Roadmap",
    "INVENTORY.md": "# Inventory",
    "MERGE_GUIDE.md": "# Merge Guide",
    "architecture/KERNEL_INTEGRATION.md": "# Kernel Integration",
    "architecture/PROOF_CARRYING_TRANSFORMATION.md": (
        "# Proof-Carrying Transformation Bundle"
    ),
    "architecture/REPOSITORY_SEMANTIC_GRAPH.md": "# Repository Semantic Graph",
    "architecture/SKILL_LIFECYCLE.md": "# Production Skill Lifecycle",
    "evals/E0-E5_MATRIX.md": "# E0-E5 Evidence Matrix",
    "evals/PROMOTION_POLICY.md": "# Rule / Skill / Model Promotion Policy",
    "policies/POLICY_MODEL.md": "# Policy Model",
    "references/SOURCES.md": "# Upstream Inspiration Map",
}
EXPECTED_SCHEMA_FILES = {
    "schemas/certification-result.schema.json",
    "schemas/evidence-bundle.schema.json",
    "schemas/skill-manifest.schema.json",
}
EXPECTED_NON_SKILL_FILES = {
    "SKILL.md",
    "manifest.json",
    "SHA256SUMS.txt",
    "policies/example_policy.rego",
    "scripts/validate_package.py",
    *EXPECTED_MARKDOWN_HEADINGS,
    *EXPECTED_SCHEMA_FILES,
}
EXPECTED_MASTER_SECTIONS = (
    "## Trigger",
    "## Mandatory orchestration",
    "## Global invariants",
)
EXPECTED_SKILL_SECTIONS = (
    "## Objective",
    "## Inspirations",
    "## Activation conditions",
    "## Required inputs",
    "## Workflow",
    "## Required outputs",
    "## Production invariants",
    "## Integration contracts",
    "## Certification",
)

SOURCE_DEPENDENCY_FIELDS = frozenset(
    {"dependencies", "dependency_graph", "dependencyGraph", "dag", "edges"}
)
RUNTIME_BINDING = {
    "module": "elmos_commercial_expansion",
    "service": "CommercialCapabilityExpansionService",
    "entrypoint": "CommercialCapabilityExpansionService.execute",
    "preparation_module": "elmos_commercial_expansion.runtime",
    "preparation_entrypoint": "CommercialCapabilityRuntime.prepare_invocation",
    "input_contract_catalog_entrypoint": "list_capability_kernels",
    "input_contract_policy": "EXACT_REQUIRED_OPTIONAL_FAIL_CLOSED",
    "authentication_required": True,
}
IMPLEMENTATION_STATUS = "RUNTIME_BOUND_NOT_EXECUTED"
DEPENDENCY_ORIGIN = "REPOSITORY_OWNED_NORMALIZATION"

KERNEL_PRIMARY_ANCHOR = {
    "K1-skill-runtime": "universal-agent-skill-runtime",
    "K2-repository-intelligence": "repository-semantic-code-graph",
    "K3-transformation": "multi-engine-rewrite-router",
    "K4-build-execution": "hermetic-build-environment",
    "K5-verification": "evidence-gate-orchestrator",
    "K6-security-governance": "policy-as-code-kernel",
    "K7-database-data": "database-semantic-compiler",
    "K8-observability-evolution": "otel-agent-execution-tracing",
}
LIFECYCLE_ANCHORS = frozenset(
    {
        *KERNEL_PRIMARY_ANCHOR.values(),
        "fine-grained-authorization-engine",
        "prompt-injection-tool-boundary",
        "change-risk-classifier",
        "differential-runtime-verification",
        "continuous-fuzz-certification",
        "contract-compatibility-verification",
        "static-dataflow-assurance",
        "slsa-in-toto-provenance",
        "trajectory-dataset-versioning",
    }
)


class IntegrationError(RuntimeError):
    """The package or installed projection violates the integration contract."""


class _RenameIdentityMismatch(IntegrationError):
    """A no-replace rename moved an inode other than the captured source."""

    def __init__(self, message: str, actual: os.stat_result) -> None:
        super().__init__(message)
        self.actual = actual


@dataclass(frozen=True)
class FilePayload:
    content: bytes
    mode: int = 0o644


@dataclass(frozen=True)
class ArchiveSnapshot:
    archive_sha256: str
    archive_bytes: int
    member_count: int
    uncompressed_bytes: int
    files: Mapping[str, FilePayload]


@dataclass(frozen=True)
class ValidatedPackage:
    snapshot: ArchiveSnapshot
    manifest: Mapping[str, Any]
    source_skills: tuple[Mapping[str, Any], ...]
    repository_graph: Mapping[str, Any]


@dataclass(frozen=True)
class CompiledProjection:
    catalog_bytes: bytes
    wrapper_trees: Mapping[str, Mapping[str, FilePayload]]
    receipt_bytes: bytes
    receipt: Mapping[str, Any]


@dataclass
class _TrustedRootLock:
    """Held advisory lock bound to one trusted-root directory inode."""

    root: Path
    device: int
    inode: int
    fd: int
    exclusive: bool
    active: bool = True


@dataclass(frozen=True)
class _TemporaryPathCapability:
    """Identity-bound authority for one importer-created temporary path."""

    path: Path
    parent: Path
    basename: str
    prefix: str
    kind: str
    device: int
    inode: int
    parent_device: int
    parent_inode: int
    trusted_root: Path
    trusted_root_device: int
    trusted_root_inode: int
    root_lock: _TrustedRootLock


@dataclass(frozen=True)
class _ManagedFileCAS:
    """Prevalidation snapshot used to reject concurrent managed-file drift."""

    exists: bool
    device: int | None = None
    inode: int | None = None
    size: int | None = None
    mtime_ns: int | None = None
    sha256: str | None = None


def fail(message: str) -> None:
    raise IntegrationError(message)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )


def _decode_utf8(data: bytes, label: str) -> str:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(f"{label}: invalid UTF-8: {exc}")
    if "\x00" in text:
        fail(f"{label}: NUL is forbidden")
    if "\r" in text:
        fail(f"{label}: only canonical LF line endings are accepted")
    return text


def _reject_duplicate_json_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise IntegrationError(f"JSON contains duplicate key: {key!r}")
        result[key] = value
    return result


def load_json(data: bytes, label: str) -> Any:
    text = _decode_utf8(data, label)
    try:
        return json.loads(text, object_pairs_hook=_reject_duplicate_json_keys)
    except json.JSONDecodeError as exc:
        fail(f"{label}: invalid JSON: {exc}")


class _StrictSafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _StrictSafeLoader, node: yaml.nodes.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_StrictSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def load_yaml(data: bytes, label: str) -> Any:
    text = _decode_utf8(data, label)
    try:
        return yaml.load(text, Loader=_StrictSafeLoader)
    except yaml.YAMLError as exc:
        fail(f"{label}: invalid YAML: {exc}")


def _read_stable_pinned_archive(path: Path) -> bytes:
    """Read one regular, non-symlink archive inode and verify pinned identity."""

    try:
        before = path.lstat()
    except OSError as exc:
        fail(f"cannot stat archive {path}: {exc}")
    if not stat.S_ISREG(before.st_mode):
        fail(f"archive must be a regular non-symlink file: {path}")
    if before.st_size != EXPECTED_ARCHIVE_BYTES:
        fail(
            "archive byte size mismatch: "
            f"expected {EXPECTED_ARCHIVE_BYTES}, got {before.st_size}"
        )
    if before.st_size > MAX_ARCHIVE_BYTES:
        fail("archive exceeds the importer compressed-size safety bound")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        fail(f"cannot securely open archive {path}: {exc}")
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
            fail("opened archive inode is not a regular file")
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            fail("archive inode changed between lstat and open")
        chunks: list[bytes] = []
        count = 0
        while True:
            chunk = os.read(fd, READ_CHUNK_BYTES)
            if not chunk:
                break
            count += len(chunk)
            if count > MAX_ARCHIVE_BYTES:
                fail("archive grew beyond the compressed-size safety bound while reading")
            chunks.append(chunk)
        after_fd = os.fstat(fd)
    finally:
        os.close(fd)

    data = b"".join(chunks)
    try:
        after_path = path.lstat()
    except OSError as exc:
        fail(f"archive disappeared or changed while reading: {exc}")
    stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    if any(getattr(before, field) != getattr(after_fd, field) for field in stable_fields):
        fail("archive inode changed while reading")
    if any(getattr(before, field) != getattr(after_path, field) for field in stable_fields):
        fail("archive path changed while reading")
    if len(data) != EXPECTED_ARCHIVE_BYTES:
        fail(
            "archive byte size mismatch after stable read: "
            f"expected {EXPECTED_ARCHIVE_BYTES}, got {len(data)}"
        )
    actual_digest = sha256_bytes(data)
    if actual_digest != EXPECTED_ARCHIVE_SHA256:
        fail(
            "archive digest mismatch: "
            f"expected {EXPECTED_ARCHIVE_SHA256}, got {actual_digest}"
        )
    return data


def resolve_archive() -> Path:
    candidates = [ROOT / PRIMARY_ARCHIVE_RELATIVE, ROOT / FALLBACK_ARCHIVE_RELATIVE]
    existing = [candidate for candidate in candidates if candidate.exists()]
    if not existing:
        fail(
            "commercial capability expansion archive not found in candidates: "
            + ", ".join(str(candidate) for candidate in candidates)
        )
    if len(existing) == 2:
        first = _read_stable_pinned_archive(existing[0])
        second = _read_stable_pinned_archive(existing[1])
        if first != second:  # pragma: no cover - digest checks catch this first
            fail("primary and fallback archives are not byte-identical")
    return existing[0]


def _validate_archive_name(raw_name: str) -> tuple[str, PurePosixPath]:
    if not raw_name or "\x00" in raw_name or "\\" in raw_name:
        fail(f"unsafe archive member path: {raw_name!r}")
    if any(ord(char) < 32 or ord(char) == 127 for char in raw_name):
        fail(f"archive member path contains a control character: {raw_name!r}")
    if unicodedata.normalize("NFC", raw_name) != raw_name:
        fail(f"archive member path is not Unicode NFC-normalized: {raw_name!r}")
    path = PurePosixPath(raw_name)
    if path.is_absolute() or raw_name.startswith("/"):
        fail(f"absolute archive member path is forbidden: {raw_name!r}")
    if path.as_posix() != raw_name:
        fail(f"non-canonical archive member path is forbidden: {raw_name!r}")
    if not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        fail(f"traversal archive member path is forbidden: {raw_name!r}")
    if path.parts[0] != PACKAGE_DIRECTORY or len(path.parts) < 2:
        fail(
            f"archive member must be a file below {PACKAGE_DIRECTORY!r}: {raw_name!r}"
        )
    relative = PurePosixPath(*path.parts[1:]).as_posix()
    return relative, path


def _validate_zip_info(info: zipfile.ZipInfo) -> tuple[str, int]:
    relative, _ = _validate_archive_name(info.filename)
    if info.flag_bits & 0x1:
        fail(f"encrypted archive member is forbidden: {info.filename!r}")
    if info.create_system != 3:
        fail(f"archive member lacks Unix regular-file metadata: {info.filename!r}")
    raw_mode = (info.external_attr >> 16) & 0xFFFF
    if not stat.S_ISREG(raw_mode):
        fail(f"symlink, directory, or special archive member is forbidden: {info.filename!r}")
    mode = stat.S_IMODE(raw_mode)
    expected_mode = 0o755 if relative == "scripts/validate_package.py" else 0o644
    if mode != expected_mode:
        fail(
            f"archive member mode mismatch for {relative}: "
            f"expected {oct(expected_mode)}, got {oct(mode)}"
        )
    if info.compress_type != zipfile.ZIP_DEFLATED:
        fail(f"unsupported archive compression method: {info.filename!r}")
    if info.file_size < 0 or info.compress_size < 0:
        fail(f"archive member has an invalid declared size: {info.filename!r}")
    if info.file_size > MAX_MEMBER_BYTES:
        fail(f"archive member exceeds the uncompressed-size bound: {info.filename!r}")
    if info.file_size and info.compress_size == 0:
        fail(f"archive member has an unbounded compression ratio: {info.filename!r}")
    if info.file_size / max(info.compress_size, 1) > MAX_COMPRESSION_RATIO:
        fail(f"archive member exceeds the compression-ratio bound: {info.filename!r}")
    return relative, mode


def scan_archive_bytes(
    archive_bytes: bytes,
    *,
    expected_member_count: int | None = None,
    expected_uncompressed_bytes: int | None = None,
) -> ArchiveSnapshot:
    """Validate ZIP structure and read all regular members with CRC enforcement.

    The production entrypoint calls this only after `_read_stable_pinned_archive`.
    Tests may call it directly to exercise malicious-ZIP rejection.
    """

    if len(archive_bytes) > MAX_ARCHIVE_BYTES:
        fail("archive exceeds the compressed-size safety bound")
    files: dict[str, FilePayload] = {}
    seen_raw: set[str] = set()
    seen_folded: dict[str, str] = {}
    total_declared = 0
    total_compressed = 0
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as archive:
            infos = archive.infolist()
            if expected_member_count is not None and len(infos) != expected_member_count:
                fail(
                    "archive member count mismatch: "
                    f"expected {expected_member_count}, got {len(infos)}"
                )
            for info in infos:
                relative, mode = _validate_zip_info(info)
                if info.filename in seen_raw:
                    fail(f"duplicate archive member name: {info.filename!r}")
                seen_raw.add(info.filename)
                folded = unicodedata.normalize("NFC", info.filename).casefold()
                previous = seen_folded.get(folded)
                if previous is not None:
                    fail(
                        "Unicode NFC/casefold archive path collision: "
                        f"{previous!r} and {info.filename!r}"
                    )
                seen_folded[folded] = info.filename
                total_declared += info.file_size
                total_compressed += info.compress_size
                if total_declared > MAX_TOTAL_UNCOMPRESSED_BYTES:
                    fail("archive exceeds the total uncompressed-size bound")
                if total_declared / max(total_compressed, 1) > MAX_COMPRESSION_RATIO:
                    fail("archive exceeds the total compression-ratio bound")

                content_parts: list[bytes] = []
                actual_size = 0
                crc = 0
                with archive.open(info, "r") as member:
                    while True:
                        chunk = member.read(READ_CHUNK_BYTES)
                        if not chunk:
                            break
                        actual_size += len(chunk)
                        if actual_size > info.file_size or actual_size > MAX_MEMBER_BYTES:
                            fail(
                                "archive member expanded beyond its declared bound: "
                                f"{info.filename!r}"
                            )
                        crc = binascii.crc32(chunk, crc)
                        content_parts.append(chunk)
                if actual_size != info.file_size:
                    fail(
                        f"archive member size mismatch for {info.filename!r}: "
                        f"declared {info.file_size}, read {actual_size}"
                    )
                if (crc & 0xFFFFFFFF) != info.CRC:
                    fail(f"archive member CRC mismatch: {info.filename!r}")
                files[relative] = FilePayload(b"".join(content_parts), mode)
    except IntegrationError:
        raise
    except (zipfile.BadZipFile, RuntimeError, OSError, EOFError) as exc:
        fail(f"invalid or unreadable ZIP archive: {exc}")

    relative_paths = sorted(files)
    relative_set = set(relative_paths)
    for relative in relative_paths:
        parts = PurePosixPath(relative).parts
        for index in range(1, len(parts)):
            prefix = PurePosixPath(*parts[:index]).as_posix()
            if prefix in relative_set:
                fail(f"archive file/directory prefix collision: {prefix!r} and {relative!r}")
    if expected_uncompressed_bytes is not None and total_declared != expected_uncompressed_bytes:
        fail(
            "archive uncompressed-byte mismatch: "
            f"expected {expected_uncompressed_bytes}, got {total_declared}"
        )
    return ArchiveSnapshot(
        archive_sha256=sha256_bytes(archive_bytes),
        archive_bytes=len(archive_bytes),
        member_count=len(files),
        uncompressed_bytes=total_declared,
        files=files,
    )


def read_pinned_archive(path: Path) -> ArchiveSnapshot:
    data = _read_stable_pinned_archive(path)
    snapshot = scan_archive_bytes(
        data,
        expected_member_count=EXPECTED_MEMBER_COUNT,
        expected_uncompressed_bytes=EXPECTED_UNCOMPRESSED_BYTES,
    )
    if snapshot.archive_sha256 != EXPECTED_ARCHIVE_SHA256:
        fail("internal error: archive snapshot lost its pinned digest")
    return snapshot


def _validate_sha256sums(files: Mapping[str, FilePayload]) -> None:
    checksum_name = "SHA256SUMS.txt"
    payload = files.get(checksum_name)
    if payload is None:
        fail("SHA256SUMS.txt is missing")
    text = _decode_utf8(payload.content, checksum_name)
    if not text.endswith("\n"):
        fail("SHA256SUMS.txt must end with a newline")
    expected_paths = set(files) - {checksum_name}
    declared: dict[str, str] = {}
    folded_paths: set[str] = set()
    line_pattern = re.compile(r"^([0-9a-f]{64})  ([^\n]+)$")
    for line_number, line in enumerate(text.splitlines(), 1):
        match = line_pattern.fullmatch(line)
        if match is None:
            fail(f"SHA256SUMS.txt:{line_number}: malformed checksum line")
        digest, relative = match.groups()
        normalized, path = _validate_archive_name(f"{PACKAGE_DIRECTORY}/{relative}")
        if normalized != relative or path.parts[0] != PACKAGE_DIRECTORY:
            fail(f"SHA256SUMS.txt:{line_number}: non-canonical path {relative!r}")
        if relative == checksum_name:
            fail("SHA256SUMS.txt must not include a self-checksum")
        folded = unicodedata.normalize("NFC", relative).casefold()
        if folded in folded_paths:
            fail(f"SHA256SUMS.txt contains a duplicate/colliding path: {relative!r}")
        folded_paths.add(folded)
        declared[relative] = digest
    if set(declared) != expected_paths:
        missing = sorted(expected_paths - set(declared))
        extra = sorted(set(declared) - expected_paths)
        fail(
            "SHA256SUMS.txt must cover every archive member except itself; "
            f"missing={missing}, extra={extra}"
        )
    for relative, expected_digest in declared.items():
        actual_digest = sha256_bytes(files[relative].content)
        if actual_digest != expected_digest:
            fail(
                f"SHA256SUMS digest mismatch for {relative}: "
                f"expected {expected_digest}, got {actual_digest}"
            )


def _parse_frontmatter(payload: FilePayload, label: str) -> tuple[Mapping[str, Any], str]:
    text = _decode_utf8(payload.content, label)
    lines = text.splitlines(keepends=True)
    if not lines or lines[0] != "---\n":
        fail(f"{label}: missing opening YAML frontmatter delimiter")
    try:
        close_index = lines.index("---\n", 1)
    except ValueError:
        fail(f"{label}: missing closing YAML frontmatter delimiter")
    if close_index < 2:
        fail(f"{label}: empty YAML frontmatter")
    frontmatter_bytes = "".join(lines[1:close_index]).encode("utf-8")
    frontmatter = load_yaml(frontmatter_bytes, f"{label} frontmatter")
    if not isinstance(frontmatter, dict) or any(
        not isinstance(key, str) for key in frontmatter
    ):
        fail(f"{label}: frontmatter must be a string-keyed mapping")
    body = "".join(lines[close_index + 1 :])
    if not body.startswith("\n# ") or not body.endswith("\n"):
        fail(f"{label}: body must have a canonical top-level heading and final newline")
    return frontmatter, body


def _validate_master_skill(files: Mapping[str, FilePayload]) -> None:
    frontmatter, body = _parse_frontmatter(files["SKILL.md"], "SKILL.md")
    expected = {
        "name": MASTER_SKILL_NAME,
        "version": PACKAGE_VERSION,
        "priority": "P0",
        "kind": "meta-skill",
    }
    if frontmatter != expected:
        fail(f"SKILL.md: master frontmatter mismatch: expected {expected}, got {frontmatter}")
    if not body.startswith("\n# Elmos Commercial Capability Expansion\n"):
        fail("SKILL.md: master heading mismatch")
    for section in EXPECTED_MASTER_SECTIONS:
        if body.count(section) != 1:
            fail(f"SKILL.md: required section must appear exactly once: {section}")


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        fail(
            f"{label}: key mismatch; missing={sorted(expected-actual)}, "
            f"extra={sorted(actual-expected)}"
        )


def _validate_manifest_and_skills(
    files: Mapping[str, FilePayload]
) -> tuple[Mapping[str, Any], tuple[Mapping[str, Any], ...]]:
    manifest_value = load_json(files["manifest.json"].content, "manifest.json")
    if not isinstance(manifest_value, dict):
        fail("manifest.json must be an object")
    _require_exact_keys(
        manifest_value, {"package", "version", "generated", "skills"}, "manifest.json"
    )
    if manifest_value["package"] != PACKAGE_NAME:
        fail("manifest.json package identity mismatch")
    if manifest_value["version"] != PACKAGE_VERSION:
        fail("manifest.json version mismatch")
    if manifest_value["generated"] != PACKAGE_GENERATED:
        fail("manifest.json generated date mismatch")
    if set(manifest_value).intersection(SOURCE_DEPENDENCY_FIELDS):
        fail("source manifest unexpectedly acquired dependency/DAG fields")
    raw_skills = manifest_value["skills"]
    if not isinstance(raw_skills, list) or len(raw_skills) != EXPECTED_SKILL_COUNT:
        fail(f"manifest.json must contain exactly {EXPECTED_SKILL_COUNT} skills")

    validated: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    actual_by_kernel: dict[str, list[str]] = defaultdict(list)
    priorities: Counter[str] = Counter()
    skill_paths: set[str] = set()
    id_pattern = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    for index, raw_skill in enumerate(raw_skills):
        label = f"manifest.json skills[{index}]"
        if not isinstance(raw_skill, dict):
            fail(f"{label} must be an object")
        _require_exact_keys(
            raw_skill,
            {"id", "kernel", "priority", "objective", "inspirations", "path"},
            label,
        )
        if set(raw_skill).intersection(SOURCE_DEPENDENCY_FIELDS):
            fail(f"{label} unexpectedly declares source dependency semantics")
        skill_id = raw_skill["id"]
        kernel = raw_skill["kernel"]
        priority = raw_skill["priority"]
        objective = raw_skill["objective"]
        inspirations = raw_skill["inspirations"]
        member_path = raw_skill["path"]
        if not isinstance(skill_id, str) or id_pattern.fullmatch(skill_id) is None:
            fail(f"{label}.id is not a canonical Skill name")
        if skill_id in seen:
            fail(f"manifest.json contains duplicate Skill name: {skill_id}")
        seen.add(skill_id)
        if kernel not in EXPECTED_SKILLS_BY_KERNEL:
            fail(f"{label}.kernel is unknown: {kernel!r}")
        if priority not in {"P0", "P1", "P2"}:
            fail(f"{label}.priority is invalid: {priority!r}")
        if not isinstance(objective, str) or not (20 <= len(objective) <= 1_000):
            fail(f"{label}.objective must be a bounded non-empty string")
        if (
            not isinstance(inspirations, list)
            or not inspirations
            or any(not isinstance(item, str) or not item.strip() for item in inspirations)
            or len(set(inspirations)) != len(inspirations)
        ):
            fail(f"{label}.inspirations must be a non-empty unique string list")
        expected_path = f"skills/{kernel}/{skill_id}/SKILL.md"
        if member_path != expected_path:
            fail(
                f"{label}.path mismatch: expected {expected_path!r}, got {member_path!r}"
            )
        if member_path in skill_paths or member_path not in files:
            fail(f"{label}.path is duplicate or absent: {member_path!r}")
        skill_paths.add(member_path)

        frontmatter, body = _parse_frontmatter(files[member_path], member_path)
        expected_frontmatter = {
            "name": skill_id,
            "version": "1.0.0",
            "priority": priority,
            "kernel": kernel,
            "kind": "production-skill",
        }
        if frontmatter != expected_frontmatter:
            fail(
                f"{member_path}: frontmatter mismatch: "
                f"expected {expected_frontmatter}, got {frontmatter}"
            )
        if not body.startswith(f"\n# {skill_id}\n"):
            fail(f"{member_path}: top-level heading does not match Skill name")
        for section in EXPECTED_SKILL_SECTIONS:
            if body.count(section) != 1:
                fail(
                    f"{member_path}: required section must appear exactly once: {section}"
                )
        if f"## Objective\n{objective}\n" not in body:
            fail(f"{member_path}: Objective text does not match manifest.json")

        actual_by_kernel[kernel].append(skill_id)
        priorities[priority] += 1
        validated.append(dict(raw_skill))

    if tuple(skill["id"] for skill in validated) != EXPECTED_SKILL_NAMES:
        fail("manifest.json Skill names/order do not match the pinned exact catalog")
    for kernel, expected_names in EXPECTED_SKILLS_BY_KERNEL.items():
        if tuple(actual_by_kernel[kernel]) != expected_names:
            fail(f"manifest.json exact names/order mismatch for kernel {kernel}")
    actual_priorities = {name: priorities.get(name, 0) for name in EXPECTED_PRIORITY_COUNTS}
    if actual_priorities != EXPECTED_PRIORITY_COUNTS:
        fail(
            f"manifest.json priority counts mismatch: "
            f"expected {EXPECTED_PRIORITY_COUNTS}, got {actual_priorities}"
        )
    expected_file_set = EXPECTED_NON_SKILL_FILES | skill_paths
    if set(files) != expected_file_set:
        fail(
            "archive exact member inventory mismatch; "
            f"missing={sorted(expected_file_set-set(files))}, "
            f"extra={sorted(set(files)-expected_file_set)}"
        )
    return manifest_value, tuple(validated)


def _validate_documents(files: Mapping[str, FilePayload]) -> None:
    for relative, heading in EXPECTED_MARKDOWN_HEADINGS.items():
        text = _decode_utf8(files[relative].content, relative)
        if not text.startswith(heading + "\n") or not text.endswith("\n"):
            fail(f"{relative}: heading or final newline mismatch")
        if len(text) < len(heading) + 20:
            fail(f"{relative}: document is unexpectedly empty")
    policy = _decode_utf8(
        files["policies/example_policy.rego"].content,
        "policies/example_policy.rego",
    )
    if not policy.startswith("package elmos.execution\n") or not policy.endswith("\n"):
        fail("policies/example_policy.rego: inert policy document shape mismatch")
    script = _decode_utf8(
        files["scripts/validate_package.py"].content,
        "scripts/validate_package.py",
    )
    if not script.startswith("#!/usr/bin/env python3\n") or not script.endswith("\n"):
        fail("scripts/validate_package.py: inert script document shape mismatch")


def _walk_schema(value: Any, label: str) -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_label = f"{label}/{key}"
            yield child_label, child
            yield from _walk_schema(child, child_label)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_label = f"{label}/{index}"
            yield child_label, child
            yield from _walk_schema(child, child_label)


def _validate_schemas(files: Mapping[str, FilePayload]) -> None:
    actual = {path for path in files if path.startswith("schemas/")}
    if actual != EXPECTED_SCHEMA_FILES:
        fail(
            f"schema inventory mismatch: missing={sorted(EXPECTED_SCHEMA_FILES-actual)}, "
            f"extra={sorted(actual-EXPECTED_SCHEMA_FILES)}"
        )
    for relative in sorted(EXPECTED_SCHEMA_FILES):
        schema = load_json(files[relative].content, relative)
        if not isinstance(schema, dict):
            fail(f"{relative}: schema document must be an object")
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            fail(f"{relative}: must explicitly declare JSON Schema draft 2020-12")
        if schema.get("type") != "object":
            fail(f"{relative}: root schema type must be object")
        required = schema.get("required")
        properties = schema.get("properties")
        if (
            not isinstance(required, list)
            or not required
            or any(not isinstance(item, str) for item in required)
            or len(set(required)) != len(required)
            or not isinstance(properties, dict)
            or not set(required).issubset(properties)
        ):
            fail(f"{relative}: required/properties contract is malformed")
        for pointer, value in _walk_schema(schema, relative):
            if pointer.endswith("/$ref") and isinstance(value, str):
                if "://" in value or value.startswith("//"):
                    fail(f"{relative}: remote JSON Schema references are forbidden: {value}")
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as exc:
            fail(f"{relative}: invalid draft 2020-12 schema: {exc}")


def _add_edge(
    edges: dict[tuple[str, str], dict[str, str]],
    source: str,
    target: str,
    reason: str,
) -> None:
    if source == target:
        fail(f"repository-owned dependency graph contains a self-edge: {source}")
    key = (source, target)
    edge = {
        "from": source,
        "to": target,
        "origin": DEPENDENCY_ORIGIN,
        "reason": reason,
    }
    prior = edges.get(key)
    if prior is not None and prior != edge:
        fail(f"repository-owned dependency edge has conflicting reasons: {key}")
    edges[key] = edge


def _assert_acyclic(nodes: Sequence[str], edges: Sequence[Mapping[str, str]]) -> list[str]:
    node_set = set(nodes)
    if len(node_set) != len(nodes):
        fail("dependency graph contains duplicate nodes")
    adjacency: dict[str, list[str]] = defaultdict(list)
    indegree = {node: 0 for node in nodes}
    for edge in edges:
        source = edge["from"]
        target = edge["to"]
        if source not in node_set or target not in node_set:
            fail(f"dependency graph edge references an unknown node: {source}->{target}")
        adjacency[source].append(target)
        indegree[target] += 1
    order_index = {name: index for index, name in enumerate(nodes)}
    queue = deque(sorted((n for n in nodes if indegree[n] == 0), key=order_index.get))
    result: list[str] = []
    while queue:
        node = queue.popleft()
        result.append(node)
        for target in sorted(adjacency[node], key=order_index.get):
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    if len(result) != len(nodes):
        fail("repository-owned dependency graph contains a cycle")
    return result


def build_repository_owned_graph(
    skills: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    """Compile documented lifecycle anchors plus bounded kernel grouping.

    The source manifest has no dependency graph. These edges are repository
    normalization, never source-owned dependency claims.
    """

    nodes = [skill["id"] for skill in skills]
    if tuple(nodes) != EXPECTED_SKILL_NAMES:
        fail("cannot compile dependency graph for a non-exact Skill catalog")
    edges: dict[tuple[str, str], dict[str, str]] = {}
    explicit_edges = (
        ("policy-as-code-kernel", "fine-grained-authorization-engine", "policy before authorization"),
        ("policy-as-code-kernel", "prompt-injection-tool-boundary", "policy before tool boundary"),
        ("policy-as-code-kernel", "universal-agent-skill-runtime", "mandatory Task to Policy to Runtime flow"),
        ("fine-grained-authorization-engine", "universal-agent-skill-runtime", "authorized runtime entry"),
        ("prompt-injection-tool-boundary", "universal-agent-skill-runtime", "bounded runtime entry"),
        ("universal-agent-skill-runtime", "repository-semantic-code-graph", "runtime to repository graph"),
        ("repository-semantic-code-graph", "change-risk-classifier", "repository graph to risk and evidence plan"),
        ("change-risk-classifier", "multi-engine-rewrite-router", "risk plan before transformation"),
        ("multi-engine-rewrite-router", "hermetic-build-environment", "transformation before sandboxed build"),
        ("hermetic-build-environment", "differential-runtime-verification", "real build before differential verification"),
        ("hermetic-build-environment", "continuous-fuzz-certification", "real build before fuzz verification"),
        ("hermetic-build-environment", "contract-compatibility-verification", "real build before contract verification"),
        ("hermetic-build-environment", "static-dataflow-assurance", "build context before static assurance"),
        ("differential-runtime-verification", "evidence-gate-orchestrator", "verification producer to evidence gate"),
        ("continuous-fuzz-certification", "evidence-gate-orchestrator", "verification producer to evidence gate"),
        ("contract-compatibility-verification", "evidence-gate-orchestrator", "verification producer to evidence gate"),
        ("static-dataflow-assurance", "evidence-gate-orchestrator", "verification producer to evidence gate"),
        ("policy-as-code-kernel", "slsa-in-toto-provenance", "policy-bound provenance"),
        ("evidence-gate-orchestrator", "slsa-in-toto-provenance", "E0-E5 decision before artifact provenance"),
        ("slsa-in-toto-provenance", "otel-agent-execution-tracing", "artifact provenance before trajectory capture"),
        ("otel-agent-execution-tracing", "trajectory-dataset-versioning", "trace to versioned trajectory dataset"),
    )
    for source, target, reason in explicit_edges:
        _add_edge(edges, source, target, reason)

    for skill in skills:
        skill_id = skill["id"]
        anchor = KERNEL_PRIMARY_ANCHOR[skill["kernel"]]
        if skill_id not in LIFECYCLE_ANCHORS:
            _add_edge(
                edges,
                anchor,
                skill_id,
                f"repository-owned {skill['kernel']} capability anchor",
            )

    ordered_edges = [edges[key] for key in sorted(edges)]
    topological_order = _assert_acyclic(nodes, ordered_edges)
    incoming: dict[str, list[str]] = defaultdict(list)
    for edge in ordered_edges:
        incoming[edge["to"]].append(edge["from"])
    return {
        "origin": DEPENDENCY_ORIGIN,
        "source_dependency_gap": True,
        "source_owned_dag_claimed": False,
        "node_count": len(nodes),
        "edge_count": len(ordered_edges),
        "nodes": nodes,
        "edges": ordered_edges,
        "kernel_anchors": KERNEL_PRIMARY_ANCHOR,
        "dependencies_by_skill": {
            name: sorted(incoming.get(name, [])) for name in nodes
        },
        "acyclic": True,
        "topological_order": topological_order,
    }


def validate_package(snapshot: ArchiveSnapshot) -> ValidatedPackage:
    files = snapshot.files
    _validate_sha256sums(files)
    _validate_master_skill(files)
    manifest, skills = _validate_manifest_and_skills(files)
    _validate_documents(files)
    _validate_schemas(files)
    repository_graph = build_repository_owned_graph(skills)
    return ValidatedPackage(snapshot, manifest, skills, repository_graph)


def _tree_digest(files: Mapping[str, FilePayload]) -> str:
    digest = hashlib.sha256()
    digest.update(b"elmos-tree-sha256-v1\0")
    for relative in sorted(files):
        encoded = relative.encode("utf-8")
        content = files[relative].content
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _aggregate_wrapper_payloads(
    trees: Mapping[str, Mapping[str, FilePayload]]
) -> dict[str, FilePayload]:
    return {
        f"{skill_name}/{relative}": payload
        for skill_name, tree in trees.items()
        for relative, payload in tree.items()
    }


def _display_name(skill_name: str) -> str:
    return " ".join(word.capitalize() for word in skill_name.split("-"))


def _compiled_contract(
    package: ValidatedPackage,
    skill: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    is_master = skill is None
    if is_master:
        name = MASTER_SKILL_NAME
        kernel = "K0-commercial-orchestration"
        priority = "P0"
        objective = (
            "Orchestrate the repository-owned eight-kernel commercial capability "
            "lifecycle with fail-closed evidence boundaries."
        )
        source_member = "SKILL.md"
        dependencies = [
            "policy-as-code-kernel",
            "universal-agent-skill-runtime",
            "repository-semantic-code-graph",
            "change-risk-classifier",
            "multi-engine-rewrite-router",
            "hermetic-build-environment",
            "evidence-gate-orchestrator",
            "slsa-in-toto-provenance",
            "otel-agent-execution-tracing",
            "trajectory-dataset-versioning",
        ]
        binding_mode = "GUIDANCE_ONLY_NOT_EXECUTABLE"
    else:
        name = skill["id"]
        kernel = skill["kernel"]
        priority = skill["priority"]
        objective = skill["objective"]
        source_member = skill["path"]
        dependencies = package.repository_graph["dependencies_by_skill"][name]
        binding_mode = "AUTHENTICATED_EXACT_EXECUTION"
    source_payload = package.snapshot.files[source_member]
    runtime = {
        **RUNTIME_BINDING,
        "binding_mode": binding_mode,
        "scope_fields": [
            "tenant_id",
            "project_id",
            "actor_id",
            "revision",
            "environment_id",
        ],
        "preparation_fields": [
            "scope",
            "skill_id",
            "action",
            "inputs",
            "idempotency_key",
            "ttl",
        ],
        "execute_fields": [
            "invocation",
            "inputs",
            "decision",
            "lease",
            "authority_proof",
        ],
    }
    if is_master:
        runtime.update(
            {
                "module": None,
                "service": None,
                "entrypoint": None,
                "preparation_module": None,
                "preparation_entrypoint": None,
                "input_contract_catalog_entrypoint": None,
                "input_contract_policy": None,
                "authentication_required": None,
                "scope_fields": [],
                "preparation_fields": [],
                "execute_fields": [],
            }
        )
        runtime["orchestrates_exact_skill_count"] = EXPECTED_SKILL_COUNT
    return {
        "schema_version": "2.0.0",
        "kind": "elmos.commercial-capability-expansion.compiled-skill-contract",
        "package": {"name": PACKAGE_NAME, "version": PACKAGE_VERSION},
        "skill": {
            "name": name,
            "kernel": kernel,
            "priority": priority,
            "objective": objective,
            "dependencies": dependencies,
            "dependency_origin": DEPENDENCY_ORIGIN,
            "source_dependency_gap": True,
        },
        "source": {
            "archive_path": PRIMARY_ARCHIVE_RELATIVE.as_posix(),
            "archive_sha256": EXPECTED_ARCHIVE_SHA256,
            "archive_bytes": EXPECTED_ARCHIVE_BYTES,
            "member": source_member,
            "member_sha256": sha256_bytes(source_payload.content),
            "source_dependency_declarations_present": False,
            "source_content_executed": False,
            "source_instructions_installed": False,
        },
        "provenance": {
            "compiler": COMPILER_RELATIVE,
            "wrapper_ownership": "REPOSITORY_OWNED",
            "archive_scripts_executed": False,
            "archive_rego_executed": False,
            "dual_roots_required_byte_identical": [
                WORKSPACE_SKILLS_RELATIVE.as_posix(),
                RUNTIME_SKILLS_RELATIVE.as_posix(),
            ],
        },
        "runtime": runtime,
        "status": {
            "implementation": (
                "GUIDANCE_ONLY_NOT_EXECUTABLE"
                if is_master
                else IMPLEMENTATION_STATUS
            ),
            "local_execution_evidence": "NOT_RUN",
            "external_runtime_evidence": "NOT_RUN",
            "independent_verification": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        },
        "gates": {
            "unknown_is_success": False,
            "self_certification_allowed": False,
            "independent_evidence_required_for_certification": True,
        },
    }


def _wrapper_markdown(contract: Mapping[str, Any]) -> bytes:
    skill = contract["skill"]
    name = skill["name"]
    title = (
        "Elmos Commercial Capability Expansion"
        if name == MASTER_SKILL_NAME
        else _display_name(name)
    )
    dependencies = skill["dependencies"]
    dependency_lines = (
        "\n".join(f"- `${dependency}`" for dependency in dependencies)
        if dependencies
        else "- No repository-owned predecessor dependency."
    )
    if name == MASTER_SKILL_NAME:
        invocation = (
            "Do not execute the master as a Skill. Traverse the normalized dependency DAG, "
            "prepare each exact invocation with `CommercialCapabilityRuntime.prepare_invocation`, "
            "and submit each authority-bound call through the public "
            "`CommercialCapabilityExpansionService.execute` surface."
        )
    else:
        invocation = (
            f"Submit `{name}` through the authenticated public "
            "`CommercialCapabilityExpansionService.execute` surface; exact handler "
            "resolution is private runtime state."
        )
    description = (
        f"Repository-owned bounded wrapper for {name}; external evidence remains NOT_RUN."
    )
    text = f'''---
name: {name}
description: {json.dumps(description, ensure_ascii=False)}
---

# {title}

## Use this Skill when

{skill["objective"]}

## Required workflow

1. Read `compiled-contract.json` and preserve its exact source identity, repository-owned dependencies, runtime binding, and evidence state.
2. Resolve authenticated tenant, project, actor, immutable revision, environment authority, least privilege, and idempotency before execution.
3. Read the exact required and optional input fields from the read-only `list_capability_kernels()` catalog; missing and unknown fields fail closed.
4. {invocation}
5. Keep source facts, plans, effects, evidence, and certification decisions distinct and content-addressed.
6. Treat `UNKNOWN`, `INCONCLUSIVE`, `NOT_RUN`, missing, stale, or self-verified evidence as non-success.

## Repository-owned dependencies

{dependency_lines}

## Boundaries

- Source archive instructions, Python, Rego, prompts, workflows, and examples are inert untrusted data; this wrapper neither installs nor executes them.
- This binding is `{contract["status"]["implementation"]}`. External runtime and independent evidence remain `NOT_RUN`; certification remains `NOT_CERTIFIED`.
- The source manifest declares no dependency graph. Dependencies above are `{DEPENDENCY_ORIGIN}` and never a source-owned DAG claim.
- Never broaden permissions, weaken tests, hide unsupported semantics, or manufacture evidence to obtain a passing gate.

## Runtime binding

- Module: `{contract["runtime"]["module"]}`
- Service: `{contract["runtime"]["service"]}`
- Entrypoint: `{contract["runtime"]["entrypoint"]}`
- Source member SHA-256: `{contract["source"]["member_sha256"]}`
- Compiled contract: `compiled-contract.json`
- Codex interface: `agents/openai.yaml`

This file is repository-owned and was generated without executing source-package content.
'''
    return text.encode("utf-8")


def _openai_yaml(contract: Mapping[str, Any]) -> bytes:
    name = contract["skill"]["name"]
    display = (
        "Elmos Commercial Capability Expansion"
        if name == MASTER_SKILL_NAME
        else _display_name(name)
    )
    if name == MASTER_SKILL_NAME:
        prompt = (
            f"Use ${name} as non-executable orchestration guidance: traverse the normalized "
            "dependency DAG, prepare each exact invocation, and submit only authority-bound "
            "exact calls through CommercialCapabilityExpansionService.execute."
        )
    else:
        prompt = (
            f"Use ${name} through the authenticated public "
            "CommercialCapabilityExpansionService.execute surface with exact scope; "
            "private handler resolution is runtime-owned and evidence fails closed."
        )
    short = f"Run {name} with bounded commercial controls"
    text = (
        "interface:\n"
        f"  display_name: {json.dumps(display, ensure_ascii=False)}\n"
        f"  short_description: {json.dumps(short, ensure_ascii=False)}\n"
        f"  default_prompt: {json.dumps(prompt, ensure_ascii=False)}\n"
        "policy:\n"
        "  allow_implicit_invocation: true\n"
    )
    parsed = load_yaml(text.encode("utf-8"), f"generated {name}/agents/openai.yaml")
    if not isinstance(parsed, dict) or set(parsed) != {"interface", "policy"}:
        fail(f"generated Codex interface is malformed for {name}")
    return text.encode("utf-8")


def _build_wrapper_trees(
    package: ValidatedPackage,
) -> Mapping[str, Mapping[str, FilePayload]]:
    trees: dict[str, Mapping[str, FilePayload]] = {}
    items: list[Mapping[str, Any] | None] = [None, *package.source_skills]
    for source_skill in items:
        contract = _compiled_contract(package, source_skill)
        name = contract["skill"]["name"]
        tree = {
            "SKILL.md": FilePayload(_wrapper_markdown(contract)),
            "compiled-contract.json": FilePayload(canonical_json(contract)),
            "agents/openai.yaml": FilePayload(_openai_yaml(contract)),
        }
        if name in trees:
            fail(f"generated duplicate wrapper tree: {name}")
        trees[name] = tree
    if set(trees) != {MASTER_SKILL_NAME, *EXPECTED_SKILL_NAMES}:
        fail("generated wrapper tree names do not match master plus 85 exact Skills")
    return trees


def _build_catalog(
    package: ValidatedPackage,
    wrapper_trees: Mapping[str, Mapping[str, FilePayload]],
) -> Mapping[str, Any]:
    skills: list[dict[str, Any]] = []
    for source_skill in package.source_skills:
        name = source_skill["id"]
        contract = load_json(
            wrapper_trees[name]["compiled-contract.json"].content,
            f"generated {name}/compiled-contract.json",
        )
        skills.append(
            {
                "name": name,
                "kernel": source_skill["kernel"],
                "priority": source_skill["priority"],
                "objective": source_skill["objective"],
                "source_member": source_skill["path"],
                "source_member_sha256": contract["source"]["member_sha256"],
                "repository_owned_dependencies": contract["skill"]["dependencies"],
                "dependency_origin": DEPENDENCY_ORIGIN,
                "implementation": IMPLEMENTATION_STATUS,
            }
        )
    return {
        "schema_version": "2.0.0",
        "kind": "elmos.commercial-capability-expansion.compiled-catalog",
        "origin": "REPOSITORY_OWNED_COMPILED",
        "package": {
            "id": PACKAGE_ID,
            "name": PACKAGE_NAME,
            "version": PACKAGE_VERSION,
            "archive_sha256": EXPECTED_ARCHIVE_SHA256,
        },
        "source_manifest": {
            "member": "manifest.json",
            "member_sha256": sha256_bytes(
                package.snapshot.files["manifest.json"].content
            ),
            "dependency_fields_present": [],
            "source_dependency_gap": True,
            "source_owned_dag_claimed": False,
        },
        "source_graph": {
            "origin": "SOURCE_MANIFEST_INVENTORY_ONLY",
            "node_count": EXPECTED_SKILL_COUNT,
            "edge_count": 0,
            "nodes": list(EXPECTED_SKILL_NAMES),
            "edges": [],
            "source_dependency_gap": True,
            "source_owned_dag_claimed": False,
        },
        "repository_owned_lifecycle_graph": package.repository_graph,
        "runtime_binding": RUNTIME_BINDING,
        "skill_count": EXPECTED_SKILL_COUNT,
        "kernel_counts": EXPECTED_KERNEL_COUNTS,
        "skills": skills,
    }


def _path_label(path: Path) -> str:
    absolute = path.absolute()
    try:
        return absolute.relative_to(ROOT).as_posix()
    except ValueError:
        return absolute.as_posix()


def _receipt_without_time(
    package: ValidatedPackage,
    catalog_bytes: bytes,
    wrapper_trees: Mapping[str, Mapping[str, FilePayload]],
    *,
    archive_path: Path,
    source_path: Path,
    catalog_path: Path,
    workspace_root: Path,
    runtime_root: Path,
) -> Mapping[str, Any]:
    source_digest = _tree_digest(package.snapshot.files)
    catalog_tree_digest = _tree_digest({catalog_path.name: FilePayload(catalog_bytes)})
    wrappers_digest = _tree_digest(_aggregate_wrapper_payloads(wrapper_trees))
    return {
        "schema_version": "2.0.0",
        "package_id": PACKAGE_ID,
        "qualification_level": "LOCAL_STRUCTURAL_SELF_ATTESTED",
        "source_archive": {
            "path": _path_label(archive_path),
            "sha256": package.snapshot.archive_sha256,
            "bytes": package.snapshot.archive_bytes,
            "member_count": package.snapshot.member_count,
            "uncompressed_bytes": package.snapshot.uncompressed_bytes,
            "scripts_executed": False,
            "rego_executed": False,
        },
        "immutable_extraction": {
            "path": _path_label(source_path),
            "file_count": len(package.snapshot.files),
            "tree_digest_schema": "elmos-tree-sha256-v1-path-and-bytes",
            "tree_sha256": source_digest,
            "status": "BYTE_IDENTICAL_IMMUTABLE",
        },
        "compiled_catalog": {
            "path": _path_label(catalog_path),
            "sha256": sha256_bytes(catalog_bytes),
            "tree_sha256": catalog_tree_digest,
            "origin": "REPOSITORY_OWNED_COMPILED",
        },
        "installed_wrappers": {
            "master_count": 1,
            "skill_count": EXPECTED_SKILL_COUNT,
            "files_per_wrapper": 3,
            "workspace_root": _path_label(workspace_root),
            "runtime_root": _path_label(runtime_root),
            "tree_sha256": wrappers_digest,
            "dual_roots_byte_identical": True,
            "source_instructions_installed": False,
        },
        "dependency_model": {
            "source_graph_node_count": EXPECTED_SKILL_COUNT,
            "source_graph_edge_count": 0,
            "source_dependency_gap": True,
            "source_owned_dag_claimed": False,
            "repository_graph_origin": DEPENDENCY_ORIGIN,
            "repository_graph_node_count": package.repository_graph["node_count"],
            "repository_graph_edge_count": package.repository_graph["edge_count"],
            "repository_graph_acyclic": True,
        },
        "runtime_binding": RUNTIME_BINDING,
        "evidence": {
            "local_runtime": "NOT_RUN",
            "external_runtime": "NOT_RUN",
            "provider_database_stream_lakehouse": "NOT_RUN",
            "independent_verification": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        },
        "security": {
            "archive_identity_pinned": True,
            "all_members_prevalidated_before_write": True,
            "sha256sums_complete": True,
            "crc_validated": True,
            "source_executables_treated_as_inert_data": True,
        },
    }


def _valid_qualified_at(value: Any) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _bounded_stable_read_file(path: Path, *, max_bytes: int, label: str) -> bytes:
    """Read one stable regular inode without following links or exceeding a bound."""

    try:
        before = path.lstat()
    except OSError as exc:
        fail(f"cannot stat {label} {path}: {exc}")
    if not stat.S_ISREG(before.st_mode):
        fail(f"{label} must be a regular non-symlink file: {path}")
    if before.st_size > max_bytes:
        fail(f"{label} exceeds the {max_bytes}-byte read bound: {path}")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        fail(f"cannot securely open {label} {path}: {exc}")
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or not _same_inode(opened, before):
            fail(f"{label} inode changed while opening: {path}")
        chunks: list[bytes] = []
        count = 0
        while True:
            chunk = os.read(descriptor, min(READ_CHUNK_BYTES, max_bytes + 1 - count))
            if not chunk:
                break
            count += len(chunk)
            if count > max_bytes:
                fail(f"{label} exceeds the {max_bytes}-byte read bound: {path}")
            chunks.append(chunk)
        after_fd = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    try:
        after_path = path.lstat()
    except OSError as exc:
        fail(f"{label} path changed while reading {path}: {exc}")
    stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    if any(getattr(opened, field) != getattr(after_fd, field) for field in stable_fields):
        fail(f"{label} inode changed while reading: {path}")
    if any(getattr(opened, field) != getattr(after_path, field) for field in stable_fields):
        fail(f"{label} path changed while reading: {path}")
    content = b"".join(chunks)
    if len(content) != opened.st_size:
        fail(f"{label} size changed while reading: {path}")
    return content


def _existing_receipt_time(path: Path, expected_without_time: Mapping[str, Any]) -> str | None:
    if not path.is_file() or path.is_symlink():
        return None
    try:
        value = load_json(
            _bounded_stable_read_file(
                path, max_bytes=MAX_MANAGED_OUTPUT_BYTES, label="existing receipt"
            ),
            str(path),
        )
    except (IntegrationError, OSError):
        return None
    if not isinstance(value, dict) or not _valid_qualified_at(value.get("qualified_at")):
        return None
    without_time = dict(value)
    qualified_at = without_time.pop("qualified_at")
    if without_time == expected_without_time:
        return qualified_at
    return None


def compile_projection(
    package: ValidatedPackage,
    *,
    archive_path: Path,
    source_path: Path,
    catalog_path: Path,
    receipt_path: Path,
    workspace_root: Path,
    runtime_root: Path,
) -> CompiledProjection:
    wrapper_trees = _build_wrapper_trees(package)
    catalog = _build_catalog(package, wrapper_trees)
    catalog_bytes = canonical_json(catalog)
    receipt_base = _receipt_without_time(
        package,
        catalog_bytes,
        wrapper_trees,
        archive_path=archive_path,
        source_path=source_path,
        catalog_path=catalog_path,
        workspace_root=workspace_root,
        runtime_root=runtime_root,
    )
    qualified_at = _existing_receipt_time(receipt_path, receipt_base)
    if qualified_at is None:
        qualified_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        )
    receipt = dict(receipt_base)
    receipt["qualified_at"] = qualified_at
    return CompiledProjection(
        catalog_bytes=catalog_bytes,
        wrapper_trees=wrapper_trees,
        receipt_bytes=canonical_json(receipt),
        receipt=receipt,
    )


def _read_regular_tree(
    root: Path, candidates: Sequence[Mapping[str, FilePayload]]
) -> dict[str, FilePayload]:
    """Read only a bounded candidate inventory via stable fd-relative opens."""

    if not candidates:
        fail("managed tree candidate inventory is required")
    candidate_sets = [set(candidate) for candidate in candidates]
    allowed_paths = set().union(*candidate_sets)
    if len(allowed_paths) > MAX_MANAGED_TREE_FILES:
        fail("managed tree expected inventory exceeds the file-count bound")
    allowed_sizes: dict[str, set[int]] = defaultdict(set)
    for candidate in candidates:
        if sum(len(payload.content) for payload in candidate.values()) > MAX_MANAGED_TREE_BYTES:
            fail("managed tree expected inventory exceeds the aggregate byte bound")
        for relative, payload in candidate.items():
            path = PurePosixPath(relative)
            if (
                not relative
                or path.is_absolute()
                or path.as_posix() != relative
                or any(part in {"", ".", ".."} for part in path.parts)
            ):
                fail(f"unsafe managed tree expected path: {relative!r}")
            allowed_sizes[relative].add(len(payload.content))
    expected_directories = {
        PurePosixPath(*PurePosixPath(relative).parts[:index]).as_posix()
        for relative in allowed_paths
        for index in range(1, len(PurePosixPath(relative).parts))
    }
    try:
        root_before = root.lstat()
    except OSError as exc:
        fail(f"cannot stat managed tree {root}: {exc}")
    if not stat.S_ISDIR(root_before.st_mode):
        fail(f"managed tree must be a real directory: {root}")
    root_fd = _open_bound_directory(
        root,
        device=root_before.st_dev,
        inode=root_before.st_ino,
        label="managed tree",
    )
    result: dict[str, FilePayload] = {}
    aggregate = 0

    def walk(directory_fd: int, prefix: str, opened_state: os.stat_result) -> None:
        nonlocal aggregate
        expected_children = {
            relative[len(prefix) + 1 :].split("/", 1)[0]
            if prefix
            else relative.split("/", 1)[0]
            for relative in allowed_paths | expected_directories
            if (relative.startswith(prefix + "/") if prefix else True)
        }
        seen: set[str] = set()
        with os.scandir(directory_fd) as entries:
            for entry in entries:
                if entry.name in seen:
                    fail(f"managed tree contains duplicate directory entry: {entry.name!r}")
                seen.add(entry.name)
                relative = f"{prefix}/{entry.name}" if prefix else entry.name
                try:
                    state = entry.stat(follow_symlinks=False)
                except OSError as exc:
                    fail(f"cannot stat managed tree entry {relative}: {exc}")
                if relative not in allowed_paths and relative not in expected_directories:
                    kind = (
                        "directory"
                        if stat.S_ISDIR(state.st_mode)
                        else "file"
                        if stat.S_ISREG(state.st_mode)
                        else "special"
                    )
                    fail(
                        f"managed tree extra entry: {relative!r} "
                        f"type={kind} size={state.st_size}"
                    )
                if stat.S_ISLNK(state.st_mode):
                    fail(f"symlink is forbidden in managed tree: {relative}")
                if stat.S_ISDIR(state.st_mode):
                    child_fd = _open_bound_child(
                        directory_fd,
                        entry.name,
                        expected=state,
                        directory=True,
                        label=f"managed tree directory {relative}",
                    )
                    try:
                        walk(child_fd, relative, state)
                        after = os.fstat(child_fd)
                        current = os.stat(
                            entry.name, dir_fd=directory_fd, follow_symlinks=False
                        )
                        stable_directory_fields = (
                            "st_dev",
                            "st_ino",
                            "st_mtime_ns",
                            "st_ctime_ns",
                        )
                        if any(
                            getattr(after, field) != getattr(state, field)
                            or getattr(current, field) != getattr(state, field)
                            for field in stable_directory_fields
                        ):
                            fail(f"managed tree directory changed while walking: {relative}")
                    finally:
                        os.close(child_fd)
                    continue
                if not stat.S_ISREG(state.st_mode):
                    fail(f"special file is forbidden in managed tree: {relative}")
                if state.st_size not in allowed_sizes[relative]:
                    fail(f"managed tree byte drift (file size): {relative}")
                if aggregate + state.st_size > MAX_MANAGED_TREE_BYTES:
                    fail("managed tree exceeds the aggregate byte read bound")
                file_fd = _open_bound_child(
                    directory_fd,
                    entry.name,
                    expected=state,
                    directory=False,
                    label=f"managed tree file {relative}",
                )
                try:
                    chunks: list[bytes] = []
                    count = 0
                    while count <= state.st_size:
                        chunk = os.read(
                            file_fd,
                            min(READ_CHUNK_BYTES, state.st_size + 1 - count),
                        )
                        if not chunk:
                            break
                        count += len(chunk)
                        if count > state.st_size:
                            fail(f"managed tree file grew while reading: {relative}")
                        chunks.append(chunk)
                    after = os.fstat(file_fd)
                    current = os.stat(
                        entry.name, dir_fd=directory_fd, follow_symlinks=False
                    )
                finally:
                    os.close(file_fd)
                stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
                if any(getattr(state, field) != getattr(after, field) for field in stable_fields):
                    fail(f"managed tree file changed while reading: {relative}")
                if any(getattr(state, field) != getattr(current, field) for field in stable_fields):
                    fail(f"managed tree file path changed while reading: {relative}")
                content = b"".join(chunks)
                if len(content) != state.st_size:
                    fail(f"managed tree file size changed while reading: {relative}")
                aggregate += len(content)
                result[relative] = FilePayload(content, stat.S_IMODE(state.st_mode))
        if not seen.issubset(expected_children):  # pragma: no cover - handled above
            fail("managed tree inventory changed while walking")
        after_directory = os.fstat(directory_fd)
        if any(
            getattr(after_directory, field) != getattr(opened_state, field)
            for field in ("st_dev", "st_ino", "st_mtime_ns", "st_ctime_ns")
        ):
            fail(f"managed tree directory changed while walking: {prefix or '.'}")

    try:
        walk(root_fd, "", root_before)
        root_after_fd = os.fstat(root_fd)
    finally:
        os.close(root_fd)
    try:
        root_after_path = root.lstat()
    except OSError as exc:
        fail(f"managed tree root changed while walking {root}: {exc}")
    if any(
        getattr(root_after_fd, field) != getattr(root_before, field)
        or getattr(root_after_path, field) != getattr(root_before, field)
        for field in ("st_dev", "st_ino", "st_mtime_ns", "st_ctime_ns")
    ):
        fail(f"managed tree root inode changed while walking: {root}")
    if set(result) not in candidate_sets:
        fail(
            f"managed tree file inventory drift: actual_count={len(result)} "
            f"expected_counts={sorted({len(paths) for paths in candidate_sets})}"
        )
    return result


def _assert_tree_bytes(
    root: Path, expected: Mapping[str, FilePayload], label: str
) -> None:
    actual = _read_regular_tree(root, [expected])
    if set(actual) != set(expected):
        fail(
            f"{label} file inventory drift: "
            f"missing={sorted(set(expected)-set(actual))}, "
            f"extra={sorted(set(actual)-set(expected))}"
        )
    for relative, payload in expected.items():
        if actual[relative].content != payload.content:
            fail(f"{label} byte drift: {relative}")


def _assert_immutable_extraction(
    source_path: Path, expected: Mapping[str, FilePayload]
) -> None:
    if not source_path.exists():
        fail(f"immutable extraction is missing: {source_path}")
    _assert_tree_bytes(source_path, expected, "immutable extraction")


def _legacy_wrapper_tree(
    package: ValidatedPackage, name: str
) -> Mapping[str, FilePayload]:
    if name == MASTER_SKILL_NAME:
        member = "SKILL.md"
    else:
        by_name = {skill["id"]: skill for skill in package.source_skills}
        member = by_name[name]["path"]
    return {"SKILL.md": FilePayload(package.snapshot.files[member].content)}


def _previous_managed_wrapper_tree(
    expected: Mapping[str, FilePayload],
) -> Mapping[str, FilePayload]:
    """Reconstruct the one supported repository-owned v2 projection predecessor.

    Upgrades are accepted only when every existing byte matches this exact
    predecessor.  Foreign or partially modified managed trees still fail
    closed; this is not a permissive overwrite path.
    """

    contract = load_json(
        expected["compiled-contract.json"].content,
        "generated predecessor compiled-contract.json",
    )
    if not isinstance(contract, dict) or not isinstance(contract.get("runtime"), dict):
        fail("generated predecessor contract is malformed")
    contract["runtime"].pop("input_contract_catalog_entrypoint", None)
    contract["runtime"].pop("input_contract_policy", None)

    markdown = expected["SKILL.md"].content.decode("utf-8")
    discovery_step = (
        "3. Read the exact required and optional input fields from the read-only "
        "`list_capability_kernels()` catalog; missing and unknown fields fail closed.\n"
    )
    if markdown.count(discovery_step) != 1:
        fail("generated predecessor workflow marker is missing or ambiguous")
    markdown = markdown.replace(discovery_step, "", 1)
    if "\n4. " not in markdown:
        fail("generated predecessor invocation step is missing")
    markdown = markdown.replace("\n4. ", "\n3. ", 1)
    markdown = markdown.replace(
        "\n5. Keep source facts, plans, effects, evidence, and certification decisions ",
        "\n4. Keep source facts, plans, effects, evidence, and certification decisions ",
        1,
    )
    markdown = markdown.replace(
        "\n6. Treat `UNKNOWN`, `INCONCLUSIVE`, `NOT_RUN`, missing, stale, or self-verified ",
        "\n5. Treat `UNKNOWN`, `INCONCLUSIVE`, `NOT_RUN`, missing, stale, or self-verified ",
        1,
    )
    return {
        "SKILL.md": FilePayload(markdown.encode("utf-8"), expected["SKILL.md"].mode),
        "compiled-contract.json": FilePayload(
            canonical_json(contract),
            expected["compiled-contract.json"].mode,
        ),
        "agents/openai.yaml": expected["agents/openai.yaml"],
    }


def _classify_wrapper_destination(
    destination: Path,
    expected: Mapping[str, FilePayload],
    legacy: Mapping[str, FilePayload],
) -> str:
    if not destination.exists() and not destination.is_symlink():
        return "CREATE"
    previous_managed = (
        _previous_managed_wrapper_tree(expected)
        if set(expected) == {"SKILL.md", "compiled-contract.json", "agents/openai.yaml"}
        else None
    )
    variants = [expected, legacy]
    if previous_managed is not None:
        variants.append(previous_managed)
    actual = _read_regular_tree(destination, variants)
    actual_bytes = {name: payload.content for name, payload in actual.items()}
    expected_bytes = {name: payload.content for name, payload in expected.items()}
    legacy_bytes = {name: payload.content for name, payload in legacy.items()}
    previous_managed_bytes = (
        {name: payload.content for name, payload in previous_managed.items()}
        if previous_managed is not None
        else None
    )
    if actual_bytes == expected_bytes:
        return "KEEP"
    if actual_bytes == legacy_bytes:
        return "MIGRATE_LEGACY_SOURCE_COPY"
    if previous_managed_bytes is not None and actual_bytes == previous_managed_bytes:
        return "MIGRATE_REPOSITORY_V2_INPUT_CONTRACT_DISCOVERY"
    fail(f"managed wrapper drift or foreign ownership at {destination}")


def _canonical_absolute_path(path: Path, label: str) -> Path:
    if not path.is_absolute():
        fail(f"{label} must be absolute: {path}")
    normalized = Path(os.path.normpath(os.fspath(path)))
    if normalized != path:
        fail(f"{label} must be lexically canonical: {path}")
    return path


def _lstat_or_none(path: Path, label: str) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        fail(f"cannot lstat {label} {path}: {exc}")


def _same_inode(first: os.stat_result, second: os.stat_result) -> bool:
    return (first.st_dev, first.st_ino) == (second.st_dev, second.st_ino)


def _trusted_root_state(trusted_root: Path) -> os.stat_result:
    root = _canonical_absolute_path(trusted_root, "trusted root")
    state = _lstat_or_none(root, "trusted root")
    if state is None or stat.S_ISLNK(state.st_mode) or not stat.S_ISDIR(state.st_mode):
        fail(f"trusted root must be an existing real directory: {root}")
    return state


def _validate_root_lock(
    root_lock: _TrustedRootLock,
    trusted_root: Path,
    *,
    require_exclusive: bool,
) -> None:
    root = _canonical_absolute_path(trusted_root, "trusted root")
    if not root_lock.active or root_lock.root != root:
        fail(f"trusted-root lock is inactive or bound to another root: {root}")
    if require_exclusive and not root_lock.exclusive:
        fail(f"an exclusive trusted-root lock is required: {root}")
    try:
        descriptor_state = os.fstat(root_lock.fd)
    except OSError as exc:
        fail(f"trusted-root lock descriptor is invalid: {exc}")
    path_state = _trusted_root_state(root)
    expected = (root_lock.device, root_lock.inode)
    if (descriptor_state.st_dev, descriptor_state.st_ino) != expected:
        fail(f"trusted-root lock descriptor inode drifted: {root}")
    if (path_state.st_dev, path_state.st_ino) != expected:
        fail(f"trusted-root path inode drifted while locked: {root}")
    if not stat.S_ISDIR(descriptor_state.st_mode):
        fail(f"trusted-root lock descriptor is not a directory: {root}")


@contextmanager
def _trusted_root_lock(
    trusted_root: Path, *, exclusive: bool
) -> Iterator[_TrustedRootLock]:
    root = _canonical_absolute_path(trusted_root, "trusted root")
    before = _trusted_root_state(root)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(root, flags)
    except OSError as exc:
        fail(f"cannot open trusted root for locking {root}: {exc}")
    lock: _TrustedRootLock | None = None
    acquired = False
    try:
        descriptor_state = os.fstat(fd)
        if not _same_inode(descriptor_state, before):
            fail(f"trusted-root inode changed while opening lock: {root}")
        fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        acquired = True
        lock = _TrustedRootLock(
            root=root,
            device=descriptor_state.st_dev,
            inode=descriptor_state.st_ino,
            fd=fd,
            exclusive=exclusive,
        )
        _validate_root_lock(lock, root, require_exclusive=exclusive)
        yield lock
        _validate_root_lock(lock, root, require_exclusive=exclusive)
    finally:
        if lock is not None:
            lock.active = False
        try:
            if acquired:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _validate_owned_path(
    path: Path,
    trusted_root: Path,
    label: str,
    *,
    allow_trusted_root: bool = False,
    reject_protected_target: bool = True,
    reject_hardlinked_file: bool = False,
) -> os.stat_result | None:
    """Validate lexical ownership and every existing inode without resolving links."""

    root = _canonical_absolute_path(trusted_root, "trusted root")
    root_state = _trusted_root_state(root)
    candidate = _canonical_absolute_path(path, label)
    try:
        relative = candidate.relative_to(root)
    except ValueError:
        fail(f"{label} escapes trusted root {root}: {candidate}")
    if candidate == root and not allow_trusted_root:
        fail(f"{label} must not be the trusted repository/test root: {candidate}")

    current = root
    candidate_state = root_state if candidate == root else None
    for index, part in enumerate(relative.parts):
        current = current / part
        state = _lstat_or_none(current, label)
        if state is None:
            break
        if stat.S_ISLNK(state.st_mode):
            fail(f"{label} has symlink ancestry: {current}")
        if index < len(relative.parts) - 1 and not stat.S_ISDIR(state.st_mode):
            fail(f"{label} has a non-directory ancestor: {current}")
        if current != root and _same_inode(state, root_state):
            fail(f"{label} aliases the trusted root inode: {current}")
        if current == candidate:
            candidate_state = state

    if reject_hardlinked_file and candidate_state is not None:
        if stat.S_ISREG(candidate_state.st_mode) and candidate_state.st_nlink != 1:
            fail(f"{label} is a hard-linked managed file: {candidate}")

    if reject_protected_target:
        protected = (
            ("current working directory", _canonical_absolute_path(Path.cwd(), "cwd")),
            ("repository root", ROOT),
        )
        for protected_label, protected_path in protected:
            protected_state = _lstat_or_none(protected_path, protected_label)
            if candidate == protected_path or (
                candidate_state is not None
                and protected_state is not None
                and _same_inode(candidate_state, protected_state)
            ):
                fail(f"{label} must not target the {protected_label}: {candidate}")
    return candidate_state


def _validate_managed_layout(
    *,
    trusted_root: Path,
    source_path: Path,
    catalog_path: Path,
    receipt_path: Path,
    workspace_root: Path,
    runtime_root: Path,
) -> None:
    managed = {
        "immutable extraction": source_path,
        "compiled catalog": catalog_path,
        "qualification receipt": receipt_path,
        "workspace wrapper root": workspace_root,
        "runtime wrapper root": runtime_root,
    }
    states: dict[str, os.stat_result | None] = {}
    for label, path in managed.items():
        states[label] = _validate_owned_path(
            path,
            trusted_root,
            label,
            reject_hardlinked_file=label
            in {"compiled catalog", "qualification receipt"},
        )

    directory_labels = {
        "immutable extraction",
        "workspace wrapper root",
        "runtime wrapper root",
    }
    for label, state in states.items():
        if state is None:
            continue
        if label in directory_labels and not stat.S_ISDIR(state.st_mode):
            fail(f"{label} must be a real directory: {managed[label]}")
        if label not in directory_labels and not stat.S_ISREG(state.st_mode):
            fail(f"{label} must be a regular file: {managed[label]}")

    entries = list(managed.items())
    for index, (first_label, first) in enumerate(entries):
        for second_label, second in entries[index + 1 :]:
            if first == second or first in second.parents or second in first.parents:
                fail(
                    "managed output paths must not overlap: "
                    f"{first_label}={first}, {second_label}={second}"
                )
            first_state = states[first_label]
            second_state = states[second_label]
            if (
                first_state is not None
                and second_state is not None
                and _same_inode(first_state, second_state)
            ):
                fail(
                    "managed output paths share an inode: "
                    f"{first_label}={first}, {second_label}={second}"
                )


def _validate_cli_managed_paths(
    *,
    source_path: Path,
    catalog_path: Path,
    receipt_path: Path,
    workspace_root: Path,
    runtime_root: Path,
) -> None:
    actual = {
        "--target-dir": source_path,
        "--catalog-output": catalog_path,
        "--receipt-output": receipt_path,
        "--workspace-root": workspace_root,
        "--runtime-root": runtime_root,
    }
    expected = {
        "--target-dir": ROOT / SOURCE_RELATIVE,
        "--catalog-output": ROOT / CATALOG_RELATIVE,
        "--receipt-output": ROOT / RECEIPT_RELATIVE,
        "--workspace-root": ROOT / WORKSPACE_SKILLS_RELATIVE,
        "--runtime-root": ROOT / RUNTIME_SKILLS_RELATIVE,
    }
    for option, expected_path in expected.items():
        if actual[option] != expected_path:
            fail(
                f"{option} is repository-owned and must equal {expected_path}; "
                f"got {actual[option]}"
            )
    _validate_managed_layout(
        trusted_root=ROOT,
        source_path=source_path,
        catalog_path=catalog_path,
        receipt_path=receipt_path,
        workspace_root=workspace_root,
        runtime_root=runtime_root,
    )


def _validate_temporary_prefix(prefix: str) -> None:
    if (
        not prefix
        or Path(prefix).name != prefix
        or "\\" in prefix
        or not prefix.startswith(".")
        or not (
            prefix.endswith(".stage-")
            or prefix.endswith(".backup-container-")
            or prefix.endswith(".quarantine-container-")
        )
    ):
        fail(f"unsafe temporary-path prefix: {prefix!r}")


def _capture_temporary_path(
    path: Path,
    *,
    parent: Path,
    prefix: str,
    kind: str,
    trusted_root: Path,
    root_lock: _TrustedRootLock,
) -> _TemporaryPathCapability:
    _validate_root_lock(root_lock, trusted_root, require_exclusive=True)
    _validate_temporary_prefix(prefix)
    parent_state = _validate_owned_path(
        parent,
        trusted_root,
        "temporary parent",
        allow_trusted_root=True,
        reject_protected_target=False,
    )
    if parent_state is None or not stat.S_ISDIR(parent_state.st_mode):
        fail(f"temporary parent must be an existing real directory: {parent}")
    state = _validate_owned_path(path, trusted_root, "temporary cleanup target")
    if path.parent != parent:
        fail(f"temporary path is not a direct child of its expected parent: {path}")
    if path.name == prefix or not path.name.startswith(prefix):
        fail(f"temporary path basename does not match its expected prefix: {path}")
    if state is None or stat.S_ISLNK(state.st_mode):
        fail(f"temporary path must exist and must not be a symlink: {path}")
    if kind == "directory" and not stat.S_ISDIR(state.st_mode):
        fail(f"temporary directory capability targets a non-directory: {path}")
    if kind == "file" and not stat.S_ISREG(state.st_mode):
        fail(f"temporary file capability targets a non-file: {path}")
    if kind not in {"directory", "file"}:
        fail(f"unsupported temporary path capability kind: {kind}")
    root_state = _trusted_root_state(trusted_root)
    return _TemporaryPathCapability(
        path=path,
        parent=parent,
        basename=path.name,
        prefix=prefix,
        kind=kind,
        device=state.st_dev,
        inode=state.st_ino,
        parent_device=parent_state.st_dev,
        parent_inode=parent_state.st_ino,
        trusted_root=trusted_root,
        trusted_root_device=root_state.st_dev,
        trusted_root_inode=root_state.st_ino,
        root_lock=root_lock,
    )


def _validate_temporary_path(capability: _TemporaryPathCapability) -> None:
    path = _canonical_absolute_path(capability.path, "temporary cleanup target")
    parent = _canonical_absolute_path(capability.parent, "temporary parent")
    trusted_root = _canonical_absolute_path(capability.trusted_root, "trusted root")
    _validate_root_lock(
        capability.root_lock, trusted_root, require_exclusive=True
    )
    _validate_temporary_prefix(capability.prefix)
    if path.parent != parent or path.name != capability.basename:
        fail(f"temporary cleanup capability path binding drifted: {path}")
    if path.name == capability.prefix or not path.name.startswith(capability.prefix):
        fail(f"temporary cleanup capability prefix binding drifted: {path}")

    root_state = _trusted_root_state(trusted_root)
    if (root_state.st_dev, root_state.st_ino) != (
        capability.trusted_root_device,
        capability.trusted_root_inode,
    ):
        fail(f"trusted root inode changed before temporary cleanup: {trusted_root}")
    parent_state = _validate_owned_path(
        parent,
        trusted_root,
        "temporary parent",
        allow_trusted_root=True,
        reject_protected_target=False,
    )
    if parent_state is None or (parent_state.st_dev, parent_state.st_ino) != (
        capability.parent_device,
        capability.parent_inode,
    ):
        fail(f"temporary parent inode changed before cleanup: {parent}")
    if not stat.S_ISDIR(parent_state.st_mode):
        fail(f"temporary parent is no longer a directory: {parent}")

    state = _validate_owned_path(path, trusted_root, "temporary cleanup target")
    if state is None or (state.st_dev, state.st_ino) != (
        capability.device,
        capability.inode,
    ):
        fail(f"temporary cleanup target inode changed or disappeared: {path}")
    if stat.S_ISLNK(state.st_mode):
        fail(f"temporary cleanup target became a symlink: {path}")
    if capability.kind == "directory" and not stat.S_ISDIR(state.st_mode):
        fail(f"temporary cleanup target is no longer a directory: {path}")
    if capability.kind == "file" and not stat.S_ISREG(state.st_mode):
        fail(f"temporary cleanup target is no longer a regular file: {path}")


def _validate_relocated_temporary_path(
    path: Path, capability: _TemporaryPathCapability, label: str
) -> None:
    """Verify that a renamed temporary inode is still the importer-owned inode."""

    state = _validate_owned_path(path, capability.trusted_root, label)
    if state is None or (state.st_dev, state.st_ino) != (
        capability.device,
        capability.inode,
    ):
        fail(f"{label} no longer has the importer-created inode: {path}")
    if capability.kind == "directory" and not stat.S_ISDIR(state.st_mode):
        fail(f"{label} is no longer a directory: {path}")
    if capability.kind == "file" and not stat.S_ISREG(state.st_mode):
        fail(f"{label} is no longer a regular file: {path}")


def _open_bound_directory(
    path: Path, *, device: int, inode: int, label: str
) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        fail(f"cannot open {label} {path}: {exc}")
    try:
        state = os.fstat(descriptor)
        if (state.st_dev, state.st_ino) != (device, inode):
            fail(f"{label} inode changed while opening: {path}")
        if not stat.S_ISDIR(state.st_mode):
            fail(f"{label} is not a directory: {path}")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _open_bound_child(
    parent_fd: int,
    name: str,
    *,
    expected: os.stat_result,
    directory: bool,
    label: str,
) -> int:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    if directory:
        flags |= getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=parent_fd)
    except OSError as exc:
        fail(f"cannot open bound {label} {name!r}: {exc}")
    try:
        state = os.fstat(descriptor)
        if not _same_inode(state, expected):
            fail(f"bound {label} inode changed while opening: {name!r}")
        if directory and not stat.S_ISDIR(state.st_mode):
            fail(f"bound {label} is no longer a directory: {name!r}")
        if not directory and not stat.S_ISREG(state.st_mode):
            fail(f"bound {label} is no longer a regular file: {name!r}")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _rename_noreplace_syscall(
    source_fd: int,
    source_name: str,
    destination_fd: int,
    destination_name: str,
) -> None:
    """Use the host's atomic no-replace rename primitive; never emulate it."""

    for name in (source_name, destination_name):
        if not name or Path(name).name != name or name in {".", ".."}:
            fail(f"unsafe no-replace rename basename: {name!r}")
    libc = ctypes.CDLL(None, use_errno=True)
    source_bytes = os.fsencode(source_name)
    destination_bytes = os.fsencode(destination_name)
    if sys.platform == "darwin":
        renameatx_np = libc.renameatx_np
        renameatx_np.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameatx_np.restype = ctypes.c_int
        result = renameatx_np(
            source_fd,
            source_bytes,
            destination_fd,
            destination_bytes,
            0x00000004,  # RENAME_EXCL
        )
    elif sys.platform.startswith("linux"):
        try:
            renameat2 = libc.renameat2
        except AttributeError:
            fail("host lacks an atomic no-replace directory rename primitive")
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        result = renameat2(
            source_fd,
            source_bytes,
            destination_fd,
            destination_bytes,
            0x00000001,  # RENAME_NOREPLACE
        )
    else:
        fail("host lacks an atomic no-replace directory rename primitive")
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(error_number, os.strerror(error_number), destination_name)
    raise OSError(error_number, os.strerror(error_number), destination_name)


def _rename_bound_noreplace(
    source_fd: int,
    source_name: str,
    destination_fd: int,
    destination_name: str,
    *,
    expected_device: int,
    expected_inode: int,
    directory: bool,
    label: str,
) -> os.stat_result:
    """Atomically publish one captured inode and verify what actually moved."""

    source = os.stat(source_name, dir_fd=source_fd, follow_symlinks=False)
    if (source.st_dev, source.st_ino) != (expected_device, expected_inode):
        fail(f"{label} source inode changed before no-replace rename")
    if directory and not stat.S_ISDIR(source.st_mode):
        fail(f"{label} source is no longer a directory")
    if not directory and not stat.S_ISREG(source.st_mode):
        fail(f"{label} source is no longer a regular file")
    _rename_noreplace_syscall(
        source_fd,
        source_name,
        destination_fd,
        destination_name,
    )
    moved = os.stat(destination_name, dir_fd=destination_fd, follow_symlinks=False)
    if (moved.st_dev, moved.st_ino) != (expected_device, expected_inode):
        raise _RenameIdentityMismatch(
            f"{label} moved an unexpected inode during no-replace rename",
            moved,
        )
    try:
        os.stat(source_name, dir_fd=source_fd, follow_symlinks=False)
    except FileNotFoundError:
        pass
    else:
        fail(f"{label} source basename was recreated after no-replace rename")
    return moved


def _retain_unknown_tree(
    *,
    parent_fd: int,
    parent: Path,
    name: str,
    actual: os.stat_result,
    destination_name: str,
    trusted_root: Path,
    root_lock: _TrustedRootLock,
) -> Path:
    """Move a concurrently substituted tree into a retained recovery container."""

    quarantine = _create_temporary_directory(
        parent,
        f".{destination_name}.quarantine-container-",
        trusted_root=trusted_root,
        root_lock=root_lock,
    )
    quarantine_fd = _open_bound_directory(
        quarantine.path,
        device=quarantine.device,
        inode=quarantine.inode,
        label="retained tree quarantine",
    )
    try:
        _rename_bound_noreplace(
            parent_fd,
            name,
            quarantine_fd,
            "payload",
            expected_device=actual.st_dev,
            expected_inode=actual.st_ino,
            directory=True,
            label="unknown concurrent tree quarantine",
        )
    except BaseException:
        # Both the unknown source and the random recovery container are retained.
        raise
    finally:
        os.close(quarantine_fd)
    return quarantine.path


def _delete_directory_contents_fd(directory_fd: int, label: str) -> None:
    """Delete only entries reachable below one already-open directory inode."""

    for name in sorted(os.listdir(directory_fd)):
        if name in {"", ".", ".."}:
            fail(f"unsafe entry in {label}: {name!r}")
        state = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if stat.S_ISLNK(state.st_mode):
            fail(f"symlink appeared inside {label}: {name!r}")
        if stat.S_ISDIR(state.st_mode):
            child_fd = _open_bound_child(
                directory_fd,
                name,
                expected=state,
                directory=True,
                label=label,
            )
            try:
                _delete_directory_contents_fd(child_fd, f"{label}/{name}")
                if os.listdir(child_fd):
                    fail(f"bound directory was repopulated during cleanup: {label}/{name}")
                current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                if not _same_inode(current, state) or not stat.S_ISDIR(current.st_mode):
                    fail(f"bound directory inode changed before rmdir: {label}/{name}")
                os.rmdir(name, dir_fd=directory_fd)
            finally:
                os.close(child_fd)
        elif stat.S_ISREG(state.st_mode):
            child_fd = _open_bound_child(
                directory_fd,
                name,
                expected=state,
                directory=False,
                label=label,
            )
            try:
                current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                if not _same_inode(current, state) or not stat.S_ISREG(current.st_mode):
                    fail(f"bound file inode changed before unlink: {label}/{name}")
                os.unlink(name, dir_fd=directory_fd)
            finally:
                os.close(child_fd)
        else:
            fail(f"special file appeared inside {label}: {name!r}")


def _delete_quarantined_payload(
    quarantine_fd: int,
    capability: _TemporaryPathCapability,
) -> None:
    payload_state = os.stat("payload", dir_fd=quarantine_fd, follow_symlinks=False)
    if (payload_state.st_dev, payload_state.st_ino) != (
        capability.device,
        capability.inode,
    ):
        fail("quarantined cleanup payload inode changed before deletion")
    if capability.kind == "directory":
        payload_fd = _open_bound_child(
            quarantine_fd,
            "payload",
            expected=payload_state,
            directory=True,
            label="quarantined payload",
        )
        try:
            _delete_directory_contents_fd(payload_fd, "quarantined payload")
            if os.listdir(payload_fd):
                fail("quarantined payload directory was repopulated")
            current = os.stat(
                "payload", dir_fd=quarantine_fd, follow_symlinks=False
            )
            if not _same_inode(current, payload_state) or not stat.S_ISDIR(
                current.st_mode
            ):
                fail("quarantined payload directory inode changed before rmdir")
            os.rmdir("payload", dir_fd=quarantine_fd)
        finally:
            os.close(payload_fd)
    elif capability.kind == "file":
        payload_fd = _open_bound_child(
            quarantine_fd,
            "payload",
            expected=payload_state,
            directory=False,
            label="quarantined payload",
        )
        try:
            current = os.stat(
                "payload", dir_fd=quarantine_fd, follow_symlinks=False
            )
            if not _same_inode(current, payload_state) or not stat.S_ISREG(
                current.st_mode
            ):
                fail("quarantined payload file inode changed before unlink")
            os.unlink("payload", dir_fd=quarantine_fd)
        finally:
            os.close(payload_fd)
    else:  # pragma: no cover - capability validation rejects this
        fail(f"unsupported quarantined payload kind: {capability.kind}")


def _cleanup_temporary_path(capability: _TemporaryPathCapability) -> None:
    """Quarantine a bound inode under its held parent, then delete only quarantine."""

    _validate_temporary_path(capability)
    root_lock = capability.root_lock
    quarantine = _create_temporary_directory(
        capability.parent,
        f".{PACKAGE_NAME}.quarantine-container-",
        trusted_root=capability.trusted_root,
        root_lock=root_lock,
    )
    parent_fd = _open_bound_directory(
        capability.parent,
        device=capability.parent_device,
        inode=capability.parent_inode,
        label="temporary parent",
    )
    quarantine_fd: int | None = None
    moved = False
    try:
        _validate_root_lock(
            root_lock, capability.trusted_root, require_exclusive=True
        )
        _validate_temporary_path(capability)
        _validate_temporary_path(quarantine)
        quarantine_fd = _open_bound_directory(
            quarantine.path,
            device=quarantine.device,
            inode=quarantine.inode,
            label="cleanup quarantine",
        )
        source_state = os.stat(
            capability.basename, dir_fd=parent_fd, follow_symlinks=False
        )
        if (source_state.st_dev, source_state.st_ino) != (
            capability.device,
            capability.inode,
        ):
            fail(f"temporary source inode changed before quarantine: {capability.path}")
        try:
            _rename_bound_noreplace(
                parent_fd,
                capability.basename,
                quarantine_fd,
                "payload",
                expected_device=capability.device,
                expected_inode=capability.inode,
                directory=capability.kind == "directory",
                label="temporary cleanup quarantine",
            )
        except FileExistsError:
            fail(
                "cleanup quarantine payload appeared concurrently; "
                f"source and container retained: {quarantine.path}"
            )
        except _RenameIdentityMismatch:
            moved = True
            fail(
                "cleanup quarantine moved an unexpected inode; "
                f"container retained: {quarantine.path}"
            )
        moved = True
        if os.listdir(quarantine_fd) != ["payload"]:
            fail(f"cleanup quarantine contains unexpected entries: {quarantine.path}")
        try:
            os.stat(capability.basename, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            fail(f"temporary source name was recreated during quarantine: {capability.path}")

        _validate_root_lock(
            root_lock, capability.trusted_root, require_exclusive=True
        )
        _validate_temporary_path(quarantine)
        quarantine_state = os.stat(
            quarantine.basename, dir_fd=parent_fd, follow_symlinks=False
        )
        if (quarantine_state.st_dev, quarantine_state.st_ino) != (
            quarantine.device,
            quarantine.inode,
        ):
            fail(f"cleanup quarantine inode changed before removal: {quarantine.path}")
        _delete_quarantined_payload(quarantine_fd, capability)
        if os.listdir(quarantine_fd):
            fail(f"cleanup quarantine was repopulated: {quarantine.path}")
        quarantine_state = os.stat(
            quarantine.basename, dir_fd=parent_fd, follow_symlinks=False
        )
        if (quarantine_state.st_dev, quarantine_state.st_ino) != (
            quarantine.device,
            quarantine.inode,
        ) or not stat.S_ISDIR(quarantine_state.st_mode):
            fail(f"cleanup quarantine inode changed before final rmdir: {quarantine.path}")
        os.rmdir(quarantine.basename, dir_fd=parent_fd)
    except BaseException:
        # If the source was moved, retain the random quarantine for recovery.
        # If it was not moved, remove only the independently bound empty container.
        if not moved:
            try:
                _validate_temporary_path(quarantine)
            except IntegrationError:
                pass
            else:
                if quarantine_fd is None:
                    quarantine_fd = _open_bound_directory(
                        quarantine.path,
                        device=quarantine.device,
                        inode=quarantine.inode,
                        label="cleanup quarantine",
                    )
                quarantine_state = os.stat(
                    quarantine.basename, dir_fd=parent_fd, follow_symlinks=False
                )
                if (quarantine_state.st_dev, quarantine_state.st_ino) == (
                    quarantine.device,
                    quarantine.inode,
                ) and not os.listdir(quarantine_fd):
                    os.rmdir(quarantine.basename, dir_fd=parent_fd)
        raise
    finally:
        if quarantine_fd is not None:
            os.close(quarantine_fd)
        os.close(parent_fd)


def _create_temporary_directory(
    parent: Path,
    prefix: str,
    *,
    trusted_root: Path,
    root_lock: _TrustedRootLock,
) -> _TemporaryPathCapability:
    _validate_root_lock(root_lock, trusted_root, require_exclusive=True)
    _validate_temporary_prefix(prefix)
    _validate_owned_path(
        parent,
        trusted_root,
        "temporary parent",
        allow_trusted_root=True,
        reject_protected_target=False,
    )
    parent.mkdir(parents=True, exist_ok=True)
    _validate_owned_path(
        parent,
        trusted_root,
        "temporary parent",
        allow_trusted_root=True,
        reject_protected_target=False,
    )
    path = Path(tempfile.mkdtemp(prefix=prefix, dir=parent))
    return _capture_temporary_path(
        path,
        parent=parent,
        prefix=prefix,
        kind="directory",
        trusted_root=trusted_root,
        root_lock=root_lock,
    )


def _write_staged_tree(
    parent: Path,
    tree: Mapping[str, FilePayload],
    prefix: str,
    *,
    trusted_root: Path,
    root_lock: _TrustedRootLock,
) -> _TemporaryPathCapability:
    capability = _create_temporary_directory(
        parent,
        prefix,
        trusted_root=trusted_root,
        root_lock=root_lock,
    )
    stage = capability.path
    try:
        os.chmod(stage, 0o755)
        for relative, payload in tree.items():
            if (
                not isinstance(relative, str)
                or not relative
                or "\\" in relative
                or unicodedata.normalize("NFC", relative) != relative
            ):
                fail(f"unsafe generated tree member path: {relative!r}")
            relative_path = PurePosixPath(relative)
            if (
                relative_path.is_absolute()
                or relative_path.as_posix() != relative
                or any(part in {"", ".", ".."} for part in relative_path.parts)
            ):
                fail(f"unsafe generated tree member path: {relative!r}")
            path = stage.joinpath(*relative_path.parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload.content)
            os.chmod(path, payload.mode)
        _assert_tree_bytes(stage, tree, f"staged tree {stage}")
        _validate_temporary_path(capability)
        return capability
    except BaseException:
        _cleanup_temporary_path(capability)
        raise


def _publish_immutable_extraction(
    source_path: Path,
    tree: Mapping[str, FilePayload],
    *,
    trusted_root: Path,
    _root_lock: _TrustedRootLock | None = None,
) -> bool:
    if _root_lock is None:
        with _trusted_root_lock(trusted_root, exclusive=True) as held_lock:
            return _publish_immutable_extraction(
                source_path,
                tree,
                trusted_root=trusted_root,
                _root_lock=held_lock,
            )
    _validate_root_lock(_root_lock, trusted_root, require_exclusive=True)
    _validate_owned_path(source_path, trusted_root, "immutable extraction")
    if source_path.exists() or source_path.is_symlink():
        _assert_tree_bytes(source_path, tree, "immutable extraction")
        return False
    stage_capability = _write_staged_tree(
        source_path.parent,
        tree,
        f".{source_path.name}.stage-",
        trusted_root=trusted_root,
        root_lock=_root_lock,
    )
    stage: Path | None = stage_capability.path
    parent_fd = _open_bound_directory(
        source_path.parent,
        device=stage_capability.parent_device,
        inode=stage_capability.parent_inode,
        label="immutable extraction parent",
    )
    try:
        _validate_temporary_path(stage_capability)
        try:
            _rename_bound_noreplace(
                parent_fd,
                stage_capability.basename,
                parent_fd,
                source_path.name,
                expected_device=stage_capability.device,
                expected_inode=stage_capability.inode,
                directory=True,
                label="immutable extraction publish",
            )
        except FileExistsError:
            _assert_tree_bytes(source_path, tree, "concurrent immutable extraction")
            return False
        except _RenameIdentityMismatch as exc:
            recovery = _retain_unknown_tree(
                parent_fd=parent_fd,
                parent=source_path.parent,
                name=source_path.name,
                actual=exc.actual,
                destination_name=source_path.name,
                trusted_root=trusted_root,
                root_lock=_root_lock,
            )
            stage = None
            fail(
                "immutable extraction publish moved an unexpected inode; "
                f"quarantine retained at {recovery}"
            )
        stage = None
        _assert_tree_bytes(source_path, tree, "published immutable extraction")
        return True
    finally:
        os.close(parent_fd)
        if stage is not None:
            if stage != stage_capability.path:
                fail("immutable extraction stage binding drifted before cleanup")
            _cleanup_temporary_path(stage_capability)


def _atomic_replace_tree(
    destination: Path,
    tree: Mapping[str, FilePayload],
    *,
    trusted_root: Path,
    expected_existing: Mapping[str, FilePayload] | None = None,
    _root_lock: _TrustedRootLock | None = None,
) -> None:
    if _root_lock is None:
        with _trusted_root_lock(trusted_root, exclusive=True) as held_lock:
            _atomic_replace_tree(
                destination,
                tree,
                trusted_root=trusted_root,
                expected_existing=expected_existing,
                _root_lock=held_lock,
            )
            return
    _validate_root_lock(_root_lock, trusted_root, require_exclusive=True)
    original_state = _validate_owned_path(
        destination, trusted_root, "managed tree destination"
    )
    if original_state is not None and not stat.S_ISDIR(original_state.st_mode):
        fail(f"managed tree destination must be a real directory: {destination}")
    if original_state is None and expected_existing is not None:
        fail(f"expected managed tree is missing before replacement: {destination}")
    if original_state is not None and expected_existing is None:
        fail(f"unexpected managed tree exists before replacement: {destination}")
    if expected_existing is not None:
        _assert_tree_bytes(
            destination, expected_existing, "prevalidated managed tree"
        )
    stage_capability = _write_staged_tree(
        destination.parent,
        tree,
        f".{destination.name}.stage-",
        trusted_root=trusted_root,
        root_lock=_root_lock,
    )
    stage: Path | None = stage_capability.path
    backup_capability: _TemporaryPathCapability | None = None
    backup: Path | None = None
    parent_fd = _open_bound_directory(
        destination.parent,
        device=stage_capability.parent_device,
        inode=stage_capability.parent_inode,
        label="managed tree parent",
    )
    backup_fd: int | None = None
    preserve_backup = False
    published = False
    published_verified = False
    try:
        if original_state is not None:
            if expected_existing is None:  # pragma: no cover - guarded above
                fail(f"missing expected-existing tree contract: {destination}")
            _assert_tree_bytes(
                destination, expected_existing, "managed tree before backup"
            )
            current_state = _validate_owned_path(
                destination, trusted_root, "managed tree destination"
            )
            if current_state is None or not _same_inode(current_state, original_state):
                fail(f"managed tree destination inode changed before backup: {destination}")
            backup_capability = _create_temporary_directory(
                destination.parent,
                f".{destination.name}.backup-container-",
                trusted_root=trusted_root,
                root_lock=_root_lock,
            )
            backup = backup_capability.path
            _validate_temporary_path(backup_capability)
            backup_fd = _open_bound_directory(
                backup,
                device=backup_capability.device,
                inode=backup_capability.inode,
                label="managed tree backup",
            )
            try:
                _rename_bound_noreplace(
                    parent_fd,
                    destination.name,
                    backup_fd,
                    "previous",
                    expected_device=original_state.st_dev,
                    expected_inode=original_state.st_ino,
                    directory=True,
                    label="managed tree backup",
                )
            except FileExistsError:
                preserve_backup = True
                fail(f"managed tree backup destination appeared concurrently: {backup}")
            _assert_tree_bytes(
                backup / "previous",
                expected_existing,
                "backed-up managed tree",
            )
        elif destination.exists() or destination.is_symlink():
            fail(f"managed tree destination appeared concurrently: {destination}")

        if destination.exists() or destination.is_symlink():
            preserve_backup = backup is not None
            fail(f"managed tree destination appeared before publish: {destination}")
        _validate_temporary_path(stage_capability)
        try:
            _rename_bound_noreplace(
                parent_fd,
                stage_capability.basename,
                parent_fd,
                destination.name,
                expected_device=stage_capability.device,
                expected_inode=stage_capability.inode,
                directory=True,
                label="managed tree publish",
            )
        except FileExistsError:
            preserve_backup = backup is not None
            fail(f"managed tree destination appeared during no-replace publish: {destination}")
        except _RenameIdentityMismatch as exc:
            recovery = _retain_unknown_tree(
                parent_fd=parent_fd,
                parent=destination.parent,
                name=destination.name,
                actual=exc.actual,
                destination_name=destination.name,
                trusted_root=trusted_root,
                root_lock=_root_lock,
            )
            stage = None
            preserve_backup = backup is not None
            fail(
                "managed tree publish moved an unexpected inode; "
                f"quarantine retained at {recovery}"
            )
        stage = None
        published = True
        _validate_relocated_temporary_path(
            destination, stage_capability, "published managed tree"
        )
        _assert_tree_bytes(destination, tree, f"published wrapper {destination}")
        published_verified = True
        if backup is not None and backup_capability is not None:
            if backup != backup_capability.path:
                fail("wrapper backup binding drifted before cleanup")
            if backup_fd is not None:
                os.close(backup_fd)
                backup_fd = None
            _cleanup_temporary_path(backup_capability)
            backup = None
            backup_capability = None
    except BaseException:
        if published_verified:
            preserve_backup = backup is not None
            raise
        if backup is not None and backup_capability is not None:
            if backup != backup_capability.path:
                fail("wrapper backup binding drifted during rollback")
            _validate_temporary_path(backup_capability)
        if backup is not None and backup_capability is not None:
            try:
                if backup_fd is None:
                    backup_fd = _open_bound_directory(
                        backup,
                        device=backup_capability.device,
                        inode=backup_capability.inode,
                        label="managed tree backup",
                    )
                if published:
                    try:
                        _rename_bound_noreplace(
                            parent_fd,
                            destination.name,
                            backup_fd,
                            "failed-new",
                            expected_device=stage_capability.device,
                            expected_inode=stage_capability.inode,
                            directory=True,
                            label="failed managed tree quarantine",
                        )
                    except _RenameIdentityMismatch as exc:
                        recovery = _retain_unknown_tree(
                            parent_fd=parent_fd,
                            parent=destination.parent,
                            name=destination.name,
                            actual=exc.actual,
                            destination_name=destination.name,
                            trusted_root=trusted_root,
                            root_lock=_root_lock,
                        )
                        preserve_backup = True
                        fail(
                            "failed published tree changed before rollback; "
                            f"quarantine retained at {recovery}"
                        )
                else:
                    try:
                        os.stat(
                            destination.name,
                            dir_fd=parent_fd,
                            follow_symlinks=False,
                        )
                    except FileNotFoundError:
                        pass
                    else:
                        preserve_backup = True
                        fail(
                            "concurrent destination blocks safe rollback; "
                            f"backup retained at {backup}"
                        )
                moved_state = os.stat(
                    "previous", dir_fd=backup_fd, follow_symlinks=False
                )
                if original_state is None or not _same_inode(
                    moved_state, original_state
                ):
                    preserve_backup = True
                    fail(f"backed-up managed tree inode drifted before restore: {backup}")
                try:
                    _rename_bound_noreplace(
                        backup_fd,
                        "previous",
                        parent_fd,
                        destination.name,
                        expected_device=original_state.st_dev,
                        expected_inode=original_state.st_ino,
                        directory=True,
                        label="managed tree restore",
                    )
                except FileExistsError:
                    preserve_backup = True
                    fail(
                        "concurrent destination blocks no-replace restore; "
                        f"backup retained at {backup}"
                    )
                except _RenameIdentityMismatch as exc:
                    recovery = _retain_unknown_tree(
                        parent_fd=parent_fd,
                        parent=destination.parent,
                        name=destination.name,
                        actual=exc.actual,
                        destination_name=destination.name,
                        trusted_root=trusted_root,
                        root_lock=_root_lock,
                    )
                    preserve_backup = True
                    fail(
                        "managed tree restore moved an unexpected inode; "
                        f"quarantine retained at {recovery}"
                    )
                restored_state = _validate_owned_path(
                    destination, trusted_root, "restored managed tree"
                )
                if restored_state is None or not _same_inode(
                    restored_state, original_state
                ):
                    preserve_backup = True
                    fail(f"restored managed tree inode mismatch: {destination}")
            except BaseException:
                preserve_backup = True
                raise
        raise
    finally:
        if backup_fd is not None:
            os.close(backup_fd)
        os.close(parent_fd)
        if stage is not None:
            if stage != stage_capability.path:
                fail("wrapper stage binding drifted before cleanup")
            _cleanup_temporary_path(stage_capability)
        if (
            backup is not None
            and backup_capability is not None
            and not preserve_backup
        ):
            if backup != backup_capability.path:
                fail("wrapper backup binding drifted before final cleanup")
            _cleanup_temporary_path(backup_capability)


def _snapshot_managed_file(
    path: Path, *, trusted_root: Path, label: str
) -> _ManagedFileCAS:
    state = _validate_owned_path(
        path,
        trusted_root,
        label,
        reject_hardlinked_file=True,
    )
    if state is None:
        return _ManagedFileCAS(exists=False)
    if not stat.S_ISREG(state.st_mode):
        fail(f"{label} must be a regular file: {path}")
    if state.st_size > MAX_MANAGED_OUTPUT_BYTES:
        fail(f"{label} exceeds the managed-file size bound: {path}")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        fail(f"cannot open {label} {path}: {exc}")
    try:
        before = os.fstat(descriptor)
        if not _same_inode(before, state) or not stat.S_ISREG(before.st_mode):
            fail(f"{label} inode changed while opening: {path}")
        digest = hashlib.sha256()
        total = 0
        while True:
            chunk = os.read(descriptor, READ_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_MANAGED_OUTPUT_BYTES:
                fail(f"{label} expanded beyond the managed-file bound: {path}")
            digest.update(chunk)
        after = os.fstat(descriptor)
        if not _same_inode(before, after) or (
            before.st_size,
            before.st_mtime_ns,
            total,
        ) != (after.st_size, after.st_mtime_ns, after.st_size):
            fail(f"{label} changed while hashing: {path}")
        return _ManagedFileCAS(
            exists=True,
            device=after.st_dev,
            inode=after.st_ino,
            size=after.st_size,
            mtime_ns=after.st_mtime_ns,
            sha256=digest.hexdigest(),
        )
    finally:
        os.close(descriptor)


def _assert_managed_file_cas(
    path: Path,
    expected: _ManagedFileCAS,
    *,
    trusted_root: Path,
    label: str,
) -> None:
    actual = _snapshot_managed_file(path, trusted_root=trusted_root, label=label)
    if actual != expected:
        fail(f"{label} changed after prevalidation: {path}")


def _atomic_write_file(
    path: Path,
    content: bytes,
    *,
    trusted_root: Path,
    expected_previous: _ManagedFileCAS,
    _root_lock: _TrustedRootLock | None = None,
) -> None:
    if _root_lock is None:
        with _trusted_root_lock(trusted_root, exclusive=True) as held_lock:
            _atomic_write_file(
                path,
                content,
                trusted_root=trusted_root,
                expected_previous=expected_previous,
                _root_lock=held_lock,
            )
            return
    if len(content) > MAX_MANAGED_OUTPUT_BYTES:
        fail(f"managed output content exceeds the size bound: {path}")
    _validate_root_lock(_root_lock, trusted_root, require_exclusive=True)
    _assert_managed_file_cas(
        path,
        expected_previous,
        trusted_root=trusted_root,
        label="managed output file",
    )
    parent_state = _validate_owned_path(
        path.parent,
        trusted_root,
        "managed output parent",
        allow_trusted_root=True,
        reject_protected_target=False,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    parent_state = _validate_owned_path(
        path.parent,
        trusted_root,
        "managed output parent",
        allow_trusted_root=True,
        reject_protected_target=False,
    )
    if parent_state is None or not stat.S_ISDIR(parent_state.st_mode):
        fail(f"managed output parent is not a real directory: {path.parent}")
    prefix = f".{path.name}.stage-"
    fd, temp_name = tempfile.mkstemp(prefix=prefix, dir=path.parent)
    try:
        temp_capability = _capture_temporary_path(
            Path(temp_name),
            parent=path.parent,
            prefix=prefix,
            kind="file",
            trusted_root=trusted_root,
            root_lock=_root_lock,
        )
    except BaseException:
        os.close(fd)
        raise
    temp_path: Path | None = temp_capability.path
    parent_fd: int | None = None
    backup_capability: _TemporaryPathCapability | None = None
    backup_fd: int | None = None
    old_moved = False
    published = False
    preserve_backup = False
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, 0o644)
        _validate_temporary_path(temp_capability)
        staged = _snapshot_managed_file(
            temp_path,
            trusted_root=trusted_root,
            label="staged managed output file",
        )
        if (
            not staged.exists
            or (staged.device, staged.inode)
            != (temp_capability.device, temp_capability.inode)
            or staged.size != len(content)
            or staged.sha256 != sha256_bytes(content)
        ):
            fail(f"staged managed output bytes/inode mismatch: {temp_path}")
        _assert_managed_file_cas(
            path,
            expected_previous,
            trusted_root=trusted_root,
            label="managed output file",
        )
        parent_fd = _open_bound_directory(
            path.parent,
            device=parent_state.st_dev,
            inode=parent_state.st_ino,
            label="managed output parent",
        )
        if expected_previous.exists:
            backup_capability = _create_temporary_directory(
                path.parent,
                f".{path.name}.backup-container-",
                trusted_root=trusted_root,
                root_lock=_root_lock,
            )
            backup_fd = _open_bound_directory(
                backup_capability.path,
                device=backup_capability.device,
                inode=backup_capability.inode,
                label="managed output backup",
            )
            _assert_managed_file_cas(
                path,
                expected_previous,
                trusted_root=trusted_root,
                label="managed output file",
            )
            current = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != (
                expected_previous.device,
                expected_previous.inode,
            ) or not stat.S_ISREG(current.st_mode):
                fail(f"managed output inode changed before quarantine: {path}")
            try:
                _rename_bound_noreplace(
                    parent_fd,
                    path.name,
                    backup_fd,
                    "previous",
                    expected_device=expected_previous.device,
                    expected_inode=expected_previous.inode,
                    directory=False,
                    label="managed output backup",
                )
            except FileExistsError:
                preserve_backup = True
                fail(
                    "managed output backup appeared concurrently; "
                    f"source and backup retained: {backup_capability.path}"
                )
            except _RenameIdentityMismatch:
                old_moved = True
                preserve_backup = True
                fail(
                    "managed output backup moved an unexpected inode; "
                    f"backup retained: {backup_capability.path}"
                )
            old_moved = True
            _assert_managed_file_cas(
                backup_capability.path / "previous",
                expected_previous,
                trusted_root=trusted_root,
                label="quarantined managed output file",
            )
        else:
            try:
                os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                fail(f"managed output file appeared concurrently: {path}")

        _validate_temporary_path(temp_capability)
        staged_inode = os.stat(
            temp_capability.basename,
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
        if (staged_inode.st_dev, staged_inode.st_ino) != (
            temp_capability.device,
            temp_capability.inode,
        ):
            fail(f"managed output stage inode changed before publish: {temp_path}")
        try:
            os.link(
                temp_capability.basename,
                path.name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
                follow_symlinks=False,
            )
        except FileExistsError:
            preserve_backup = old_moved
            fail(f"managed output destination appeared during no-replace publish: {path}")
        published = True
        _validate_relocated_temporary_path(
            path, temp_capability, "published managed output file"
        )
        current_stage = os.stat(
            temp_capability.basename,
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
        if (current_stage.st_dev, current_stage.st_ino) != (
            temp_capability.device,
            temp_capability.inode,
        ):
            fail(f"managed output stage inode changed before unlink: {temp_path}")
        os.unlink(temp_capability.basename, dir_fd=parent_fd)
        temp_path = None
        final = _snapshot_managed_file(
            path,
            trusted_root=trusted_root,
            label="published managed output file",
        )
        if (
            not final.exists
            or (final.device, final.inode)
            != (temp_capability.device, temp_capability.inode)
            or final.size != len(content)
            or final.sha256 != sha256_bytes(content)
        ):
            fail(f"published managed output bytes/inode mismatch: {path}")
        if backup_fd is not None:
            os.close(backup_fd)
            backup_fd = None
        if backup_capability is not None:
            _cleanup_temporary_path(backup_capability)
            backup_capability = None
            old_moved = False
    except BaseException:
        if (
            old_moved
            and not published
            and not preserve_backup
            and backup_capability is not None
        ):
            if backup_fd is None:
                backup_fd = _open_bound_directory(
                    backup_capability.path,
                    device=backup_capability.device,
                    inode=backup_capability.inode,
                    label="managed output backup",
                )
            if parent_fd is None:
                parent_fd = _open_bound_directory(
                    path.parent,
                    device=parent_state.st_dev,
                    inode=parent_state.st_ino,
                    label="managed output parent",
                )
            try:
                os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                previous = os.stat(
                    "previous", dir_fd=backup_fd, follow_symlinks=False
                )
                os.link(
                    "previous",
                    path.name,
                    src_dir_fd=backup_fd,
                    dst_dir_fd=parent_fd,
                    follow_symlinks=False,
                )
                restored = os.stat(
                    path.name, dir_fd=parent_fd, follow_symlinks=False
                )
                if not _same_inode(restored, previous):
                    preserve_backup = True
                    fail(f"managed output restore inode mismatch: {path}")
                os.unlink("previous", dir_fd=backup_fd)
                old_moved = False
                os.close(backup_fd)
                backup_fd = None
                _cleanup_temporary_path(backup_capability)
                backup_capability = None
            else:
                preserve_backup = True
        elif published:
            preserve_backup = backup_capability is not None
        raise
    finally:
        if backup_fd is not None:
            os.close(backup_fd)
        if parent_fd is not None:
            os.close(parent_fd)
        if temp_path is not None:
            if temp_path != temp_capability.path:
                fail("managed output stage binding drifted before cleanup")
            _cleanup_temporary_path(temp_capability)
        if backup_capability is not None and not preserve_backup and not old_moved:
            _cleanup_temporary_path(backup_capability)


def _prevalidate_destinations(
    package: ValidatedPackage,
    projection: CompiledProjection,
    *,
    trusted_root: Path,
    source_path: Path,
    catalog_path: Path,
    receipt_path: Path,
    workspace_root: Path,
    runtime_root: Path,
) -> tuple[Mapping[Path, str], Mapping[Path, _ManagedFileCAS]]:
    _validate_managed_layout(
        trusted_root=trusted_root,
        source_path=source_path,
        catalog_path=catalog_path,
        receipt_path=receipt_path,
        workspace_root=workspace_root,
        runtime_root=runtime_root,
    )
    if source_path.exists() or source_path.is_symlink():
        _assert_tree_bytes(source_path, package.snapshot.files, "immutable extraction")
    actions: dict[Path, str] = {}
    for root in (workspace_root, runtime_root):
        if root.exists() and (root.is_symlink() or not root.is_dir()):
            fail(f"wrapper root must be a real directory: {root}")
        for name, tree in projection.wrapper_trees.items():
            actions[root / name] = _classify_wrapper_destination(
                root / name,
                tree,
                _legacy_wrapper_tree(package, name),
            )
    for managed_file in (catalog_path, receipt_path):
        if managed_file.exists() and (
            managed_file.is_symlink() or not managed_file.is_file()
        ):
            fail(f"managed output must be a regular non-symlink file: {managed_file}")
    file_cas = {
        path: _snapshot_managed_file(
            path,
            trusted_root=trusted_root,
            label=f"prevalidated managed output {path.name}",
        )
        for path in (catalog_path, receipt_path)
    }
    return actions, file_cas


def install_projection(
    package: ValidatedPackage,
    projection: CompiledProjection,
    *,
    trusted_root: Path,
    source_path: Path,
    catalog_path: Path,
    receipt_path: Path,
    workspace_root: Path,
    runtime_root: Path,
) -> None:
    with _trusted_root_lock(trusted_root, exclusive=True) as root_lock:
        _install_projection_locked(
            package,
            projection,
            trusted_root=trusted_root,
            root_lock=root_lock,
            source_path=source_path,
            catalog_path=catalog_path,
            receipt_path=receipt_path,
            workspace_root=workspace_root,
            runtime_root=runtime_root,
        )


def _install_projection_locked(
    package: ValidatedPackage,
    projection: CompiledProjection,
    *,
    trusted_root: Path,
    root_lock: _TrustedRootLock,
    source_path: Path,
    catalog_path: Path,
    receipt_path: Path,
    workspace_root: Path,
    runtime_root: Path,
) -> None:
    _validate_root_lock(root_lock, trusted_root, require_exclusive=True)
    # Every archive byte, checksum, manifest record, frontmatter, document,
    # schema, graph, generated wrapper, and existing destination is validated
    # before the first write below.
    actions, file_cas = _prevalidate_destinations(
        package,
        projection,
        trusted_root=trusted_root,
        source_path=source_path,
        catalog_path=catalog_path,
        receipt_path=receipt_path,
        workspace_root=workspace_root,
        runtime_root=runtime_root,
    )
    _publish_immutable_extraction(
        source_path,
        package.snapshot.files,
        trusted_root=trusted_root,
        _root_lock=root_lock,
    )
    for destination, action in actions.items():
        if action == "KEEP":
            continue
        tree = projection.wrapper_trees[destination.name]
        if action == "MIGRATE_LEGACY_SOURCE_COPY":
            expected_existing = _legacy_wrapper_tree(package, destination.name)
        elif action == "MIGRATE_REPOSITORY_V2_INPUT_CONTRACT_DISCOVERY":
            expected_existing = _previous_managed_wrapper_tree(tree)
        else:
            expected_existing = None
        _atomic_replace_tree(
            destination,
            tree,
            trusted_root=trusted_root,
            expected_existing=expected_existing,
            _root_lock=root_lock,
        )
    _validate_root_lock(root_lock, trusted_root, require_exclusive=True)
    _assert_tree_bytes(
        source_path, package.snapshot.files, "pre-receipt immutable extraction"
    )
    for root in (workspace_root, runtime_root):
        for name, expected_tree in projection.wrapper_trees.items():
            _assert_tree_bytes(
                root / name,
                expected_tree,
                f"pre-receipt managed wrapper {root / name}",
            )
    _atomic_write_file(
        catalog_path,
        projection.catalog_bytes,
        trusted_root=trusted_root,
        expected_previous=file_cas[catalog_path],
        _root_lock=root_lock,
    )
    _validate_root_lock(root_lock, trusted_root, require_exclusive=True)
    _atomic_write_file(
        receipt_path,
        projection.receipt_bytes,
        trusted_root=trusted_root,
        expected_previous=file_cas[receipt_path],
        _root_lock=root_lock,
    )
    _validate_root_lock(root_lock, trusted_root, require_exclusive=True)


def _check_receipt(path: Path, expected: Mapping[str, Any]) -> None:
    if path.is_symlink() or not path.is_file():
        fail(f"qualification receipt is missing or unsafe: {path}")
    actual = load_json(
        _bounded_stable_read_file(
            path, max_bytes=MAX_MANAGED_OUTPUT_BYTES, label="qualification receipt"
        ),
        str(path),
    )
    if not isinstance(actual, dict):
        fail("qualification receipt must be an object")
    if not _valid_qualified_at(actual.get("qualified_at")):
        fail("qualification receipt qualified_at is not canonical RFC3339 UTC")
    expected_without_time = dict(expected)
    expected_without_time.pop("qualified_at", None)
    actual_without_time = dict(actual)
    actual_without_time.pop("qualified_at", None)
    if actual_without_time != expected_without_time:
        fail("qualification receipt content/digest bindings drifted")


def check_projection(
    package: ValidatedPackage,
    projection: CompiledProjection,
    *,
    trusted_root: Path,
    source_path: Path,
    catalog_path: Path,
    receipt_path: Path,
    workspace_root: Path,
    runtime_root: Path,
) -> None:
    with _trusted_root_lock(trusted_root, exclusive=False) as root_lock:
        _check_projection_locked(
            package,
            projection,
            trusted_root=trusted_root,
            root_lock=root_lock,
            source_path=source_path,
            catalog_path=catalog_path,
            receipt_path=receipt_path,
            workspace_root=workspace_root,
            runtime_root=runtime_root,
        )


def _check_projection_locked(
    package: ValidatedPackage,
    projection: CompiledProjection,
    *,
    trusted_root: Path,
    root_lock: _TrustedRootLock,
    source_path: Path,
    catalog_path: Path,
    receipt_path: Path,
    workspace_root: Path,
    runtime_root: Path,
) -> None:
    """Replay every binding without creating, replacing, or touching a file."""

    _validate_root_lock(root_lock, trusted_root, require_exclusive=False)
    _validate_managed_layout(
        trusted_root=trusted_root,
        source_path=source_path,
        catalog_path=catalog_path,
        receipt_path=receipt_path,
        workspace_root=workspace_root,
        runtime_root=runtime_root,
    )
    _assert_immutable_extraction(source_path, package.snapshot.files)
    if catalog_path.is_symlink() or not catalog_path.is_file():
        fail(f"compiled catalog is missing or unsafe: {catalog_path}")
    if _bounded_stable_read_file(
        catalog_path,
        max_bytes=MAX_MANAGED_OUTPUT_BYTES,
        label="compiled catalog",
    ) != projection.catalog_bytes:
        fail("compiled catalog byte drift")
    for root in (workspace_root, runtime_root):
        if root.is_symlink() or not root.is_dir():
            fail(f"wrapper root is missing or unsafe: {root}")
        for name, tree in projection.wrapper_trees.items():
            _assert_tree_bytes(root / name, tree, f"installed wrapper {root/name}")
    workspace_payloads = {
        f"{name}/{relative}": payload
        for name in projection.wrapper_trees
        for relative, payload in _read_regular_tree(
            workspace_root / name, [projection.wrapper_trees[name]]
        ).items()
    }
    runtime_payloads = {
        f"{name}/{relative}": payload
        for name in projection.wrapper_trees
        for relative, payload in _read_regular_tree(
            runtime_root / name, [projection.wrapper_trees[name]]
        ).items()
    }
    if {key: value.content for key, value in workspace_payloads.items()} != {
        key: value.content for key, value in runtime_payloads.items()
    }:
        fail("workspace/runtime wrapper roots are not byte-identical")
    if _tree_digest(workspace_payloads) != projection.receipt["installed_wrappers"][
        "tree_sha256"
    ]:
        fail("installed wrapper tree digest does not match qualification receipt")
    _check_receipt(receipt_path, projection.receipt)


def _absolute_without_resolving(path: Path) -> Path:
    return path if path.is_absolute() else Path.cwd() / path


def run(args: argparse.Namespace) -> None:
    source_path = _absolute_without_resolving(args.target_dir)
    catalog_path = _absolute_without_resolving(args.catalog_output)
    receipt_path = _absolute_without_resolving(args.receipt_output)
    workspace_root = _absolute_without_resolving(args.workspace_root)
    runtime_root = _absolute_without_resolving(args.runtime_root)

    _validate_cli_managed_paths(
        source_path=source_path,
        catalog_path=catalog_path,
        receipt_path=receipt_path,
        workspace_root=workspace_root,
        runtime_root=runtime_root,
    )
    archive_path = (
        _absolute_without_resolving(args.archive) if args.archive else resolve_archive()
    )
    snapshot = read_pinned_archive(archive_path)
    package = validate_package(snapshot)
    projection = compile_projection(
        package,
        archive_path=archive_path,
        source_path=source_path,
        catalog_path=catalog_path,
        receipt_path=receipt_path,
        workspace_root=workspace_root,
        runtime_root=runtime_root,
    )
    if args.check:
        check_projection(
            package,
            projection,
            trusted_root=ROOT,
            source_path=source_path,
            catalog_path=catalog_path,
            receipt_path=receipt_path,
            workspace_root=workspace_root,
            runtime_root=runtime_root,
        )
        print(
            "CHECK OK: pinned archive, immutable extraction, 85-name catalog, "
            "repository-owned acyclic lifecycle graph, 86 wrapper trees, dual roots, "
            "and fail-closed receipt verified read-only"
        )
        return
    install_projection(
        package,
        projection,
        trusted_root=ROOT,
        source_path=source_path,
        catalog_path=catalog_path,
        receipt_path=receipt_path,
        workspace_root=workspace_root,
        runtime_root=runtime_root,
    )
    print(
        "INSTALLED: immutable pinned source data plus repository-owned master + 85 "
        "bounded wrappers; source scripts/Rego were not executed; external evidence "
        "is NOT_RUN and certification is NOT_CERTIFIED"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Securely compile the pinned Commercial Capability Expansion v2.0.0 package"
        )
    )
    parser.add_argument("--archive", type=Path, help="pinned archive path override")
    parser.add_argument("--target-dir", type=Path, default=ROOT / SOURCE_RELATIVE)
    parser.add_argument("--catalog-output", type=Path, default=ROOT / CATALOG_RELATIVE)
    parser.add_argument("--receipt-output", type=Path, default=ROOT / RECEIPT_RELATIVE)
    parser.add_argument(
        "--workspace-root", type=Path, default=ROOT / WORKSPACE_SKILLS_RELATIVE
    )
    parser.add_argument(
        "--runtime-root", type=Path, default=ROOT / RUNTIME_SKILLS_RELATIVE
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="replay every archive/extraction/catalog/wrapper/receipt check without writes",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        run(parser.parse_args(argv))
    except IntegrationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
