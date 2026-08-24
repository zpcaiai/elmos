#!/usr/bin/env python3
"""Safely integrate the pinned Elmos 7+1 commercial Skill archives.

The eight ZIP files are immutable, untrusted inputs.  This importer parses
their manifests and Skill frontmatter with the Python standard library, but it
never imports or executes archive scripts.  Repeated root contracts are merged
only when their bytes and modes are identical.  The canonical source is the
exact 252-file union; the 102nd installed Skill is a repository-owned router,
not content attributed to an archive.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import stat
import tempfile
import unicodedata
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_DIRECTORY_RELATIVE = Path("skills/subskills/archives")
SOURCE_RELATIVE = Path("skills/elmos-7plus1-commercial-skills-v1.0.0")
DOC_RELATIVE = Path("docs/elmos-7plus1-commercial-skills")
INSTALL_ROOTS = (Path(".agents/skills"), Path("agent-skills/runtime"))

PACKAGE_NAME = "elmos-7plus1-commercial-skills"
PACKAGE_VERSION = "1.0.0"
NAMESPACE = "elmos-7plus1-commercial-v1"
ROOT_SKILL_NAME = "elmos-7plus1-commercial-software-factory"
INSTALLED_NAME_OVERRIDES = {
    "elmos-incremental-analysis-cache": "elmos-7plus1-incremental-analysis-cache",
    "elmos-release-certification": "elmos-7plus1-release-certification",
}
INSTALLED_NAME_OVERRIDE_REASON = "PREEXISTING_REPOSITORY_SKILL_OWNERSHIP"

EXPECTED_PACKAGE_COUNT = 8
EXPECTED_ARCHIVE_ENTRY_COUNT = 469
EXPECTED_CANONICAL_FILE_COUNT = 252
EXPECTED_SHARED_FILE_COUNT = 31
EXPECTED_SOURCE_ROOT_SKILL_COUNT = 8
EXPECTED_SOURCE_CHILD_SKILL_COUNT = 93
EXPECTED_SOURCE_SKILL_COUNT = 101
EXPECTED_INSTALLED_SKILL_COUNT = 102
EXPECTED_PACKAGE_DEPENDENCY_EDGES = 24
EXPECTED_MERGED_DUPLICATES = 217

BLUEPRINT_IMPORTED = "BLUEPRINT_IMPORTED"
LOCAL_CONTRACT_IMPLEMENTED = "LOCAL_CONTRACT_IMPLEMENTED"
LOCAL_IMPLEMENTED_BOUNDED = "LOCAL_IMPLEMENTED_BOUNDED"
SOURCE_NOT_APPLICABLE = "NOT_APPLICABLE_REPOSITORY_OWNED"
RUNTIME_EVIDENCE_STATUS = "NOT_RUN"
EXTERNAL_EVIDENCE_STATUS = "NOT_RUN"
CERTIFICATION_STATUS = "NOT_CERTIFIED"
RUNTIME_MODULE = "elmos_software_factory"
RUNTIME_SKILL_REGISTRY = (
    "engines/software-factory-engine/src/elmos_software_factory/skill_registry.json"
)
RUNTIME_CAPABILITY_REGISTRY = (
    "engines/software-factory-engine/src/elmos_software_factory/capability_registry.json"
)
RUNTIME_PUBLIC_METHOD_REGISTRY = (
    "engines/software-factory-engine/src/elmos_software_factory/public_method_registry.json"
)
RUNTIME_REGISTRY = RUNTIME_SKILL_REGISTRY
RUNTIME_BINDING_STATE = "BOUND_NOT_EXECUTED"
RUNTIME_PYTHONPATH = "engines/software-factory-engine/src"
RUNTIME_ARTIFACTS = (
    "engines/software-factory-engine/src/elmos_software_factory/__init__.py",
    "engines/software-factory-engine/src/elmos_software_factory/__main__.py",
    "engines/software-factory-engine/src/elmos_software_factory/canonical.py",
    "engines/software-factory-engine/src/elmos_software_factory/capabilities.py",
    "engines/software-factory-engine/src/elmos_software_factory/cli.py",
    "engines/software-factory-engine/src/elmos_software_factory/handlers.py",
    "engines/software-factory-engine/src/elmos_software_factory/models.py",
    "engines/software-factory-engine/src/elmos_software_factory/public_methods.py",
    "engines/software-factory-engine/src/elmos_software_factory/registry.py",
    "engines/software-factory-engine/src/elmos_software_factory/runtime.py",
    RUNTIME_SKILL_REGISTRY,
    RUNTIME_CAPABILITY_REGISTRY,
    RUNTIME_PUBLIC_METHOD_REGISTRY,
)
EXPECTED_RUNTIME_REGISTRY_SHA256 = {
    RUNTIME_SKILL_REGISTRY: "sha256:c54404d806e3ced3f217c16f53bb2f36b5237d4aeb0558b3ea15c9d6dfa1d8f2",
    RUNTIME_CAPABILITY_REGISTRY: "sha256:a374f9b6d89b9e8c999f54b876f10b202576213a974190457cc8aaf1ad037ac7",
    RUNTIME_PUBLIC_METHOD_REGISTRY: "sha256:0171c8c6d4c5ee8b4cb1850ebd916ba485eead5f1984dd718386607be4fe029f",
}

NEUTRALIZED_SOURCE_PATHS = {
    "AGENTS.md": "_neutralized-instruction-data/AGENTS.md.source-data",
}
DIRECTORY_MODE = 0o755
RUNTIME_FILE_MODE = 0o644
MAX_RUNTIME_ARTIFACT_BYTES = 2 * 1024 * 1024

MAX_ARCHIVE_BYTES = 8 * 1024 * 1024
MAX_ARCHIVE_ENTRY_BYTES = 4 * 1024 * 1024
MAX_ARCHIVE_TOTAL_BYTES = 8 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200
MAX_PATH_BYTES = 1024

_SKILL_NAME_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_ACTION_NAME_RE = re.compile(r"[a-z][a-z0-9-]{0,127}")
_INPUT_NAME_RE = re.compile(r"[a-z][a-z0-9_]{0,127}")
_PUBLIC_METHOD_RE = re.compile(
    r"[A-Za-z][A-Za-z0-9]*(?:\.[A-Za-z][A-Za-z0-9]*)+"
)
_STABLE_ERROR_RE = re.compile(r"[A-Z][A-Z0-9_]{0,127}")
_FRONTMATTER_KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")
_WINDOWS_INVALID = frozenset('<>:"|?*')
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "CLOCK$",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


class IntegrationError(RuntimeError):
    """Raised when archive identity, safety, ownership, or drift fails closed."""


@dataclass(frozen=True)
class PackageSpec:
    ordinal: int
    package_id: str
    name: str
    phase: str
    archive_name: str
    archive_root: str
    archive_sha256: str
    archive_bytes: int
    entry_count: int
    uncompressed_bytes: int
    dependencies: tuple[str, ...]
    subskills: tuple[str, ...]


@dataclass(frozen=True)
class ArchiveRecord:
    relative: str
    size: int
    compressed_size: int
    mode: int
    sha256: str
    content: bytes


@dataclass(frozen=True)
class SourceSkill:
    ordinal: int
    package_id: str
    package_name: str
    role: str
    source_key: str
    source_name: str
    source_path: str
    source_sha256: str
    description: str
    body: str
    installed_dependencies: tuple[str, ...]
    source_archive: str


@dataclass(frozen=True)
class PackageSnapshot:
    spec: PackageSpec
    archive_sha256: str
    archive_bytes: int
    entry_count: int
    uncompressed_bytes: int
    files: Mapping[str, ArchiveRecord]
    manifest: Mapping[str, Any]
    manifest_sha256: str
    skills: tuple[SourceSkill, ...]


@dataclass(frozen=True)
class IntegrationSnapshot:
    packages: tuple[PackageSnapshot, ...]
    canonical_files: Mapping[str, ArchiveRecord]
    source_skills: tuple[SourceSkill, ...]
    package_topological_order: tuple[str, ...]


@dataclass(frozen=True)
class FilePayload:
    content: bytes
    mode: int = 0o644


@dataclass(frozen=True)
class ManagedAction:
    label: str
    destination: Path
    tree: Mapping[str, FilePayload]


@dataclass(frozen=True)
class RuntimeArtifactsSnapshot:
    skill_registry: Mapping[str, Any]
    capability_registry: Mapping[str, Any]
    public_method_registry: Mapping[str, Any]
    capability_by_skill: Mapping[str, Mapping[str, Any]]
    skill_to_package: Mapping[str, str]
    skill_to_operation: Mapping[str, str]
    artifact_digests: Mapping[str, str]
    aggregate_digest: str


SHARED_PATHS = (
    "AGENTS.md",
    "COMMERCIAL-GA-CHECKLIST.md",
    "DETAILED-PHASE-DELIVERY-PLAN.md",
    "ELMOS-REFERENCE-ARCHITECTURE.md",
    "KPI-AND-BENCHMARK-FRAMEWORK.md",
    "LICENSE-AND-ATTRIBUTION.md",
    "PHASE-MAP.md",
    "SOURCE-MANIFEST.md",
    "SOURCE-TO-CAPABILITY-MATRIX.md",
    "UPSTREAM-CAPABILITY-EXTRACTION.md",
    "VERSION",
    "examples/completion-gate.example.yaml",
    "examples/java-spring-to-rust.example.yaml",
    "examples/model-routing-policy.example.yaml",
    "examples/package-registry.example.yaml",
    "examples/requirement-ledger.example.json",
    "examples/saas-project-generation.example.yaml",
    "examples/source-capability-ledger.example.json",
    "schemas/benchmark-case.schema.json",
    "schemas/capability-ledger.schema.json",
    "schemas/event-envelope.schema.json",
    "schemas/evidence-bundle.schema.json",
    "schemas/model-route-decision.schema.json",
    "schemas/package-manifest.schema.json",
    "schemas/policy-decision.schema.json",
    "schemas/repair-trace.schema.json",
    "schemas/requirement-ledger.schema.json",
    "schemas/transformation-rule.schema.json",
    "schemas/workflow-contract.schema.json",
    "scripts/score_readiness.py",
    "scripts/validate_packages.py",
)

PACKAGE_FIXED_PATHS = (
    "ACCEPTANCE-GATES.md",
    "ARCHITECTURE.md",
    "BENCHMARKS-AND-EVALS.md",
    "DATA-AND-EVENT-MODEL.md",
    "FAILURE-MODES-AND-RECOVERY.md",
    "IMPLEMENTATION-BACKLOG.md",
    "INTERFACE-CONTRACTS.md",
    "OBSERVABILITY-AND-SLO.md",
    "PHASE-PLAN.md",
    "PRODUCT-CAPABILITY-SPEC.md",
    "README.md",
    "SECURITY-AND-GOVERNANCE.md",
    "SKILL.md",
    "examples/package-config.yaml",
    "manifest.json",
    "schemas/package-config.schema.json",
)


PACKAGE_SPECS = (
    PackageSpec(
        0,
        "P00",
        "elmos-software-factory-master",
        "全程 / Phase 0–4",
        "00-elmos-software-factory-master-v1.0.0.zip",
        "00-elmos-software-factory-master",
        "d3627374db28487e5f385986d762d267099e4107627a02358fddccb1352182b4",
        80_258,
        55,
        141_112,
        (),
        (
            "repository-system-of-record",
            "workflow-contract-compiler",
            "package-dependency-governor",
            "architecture-invariant-linter",
            "commercial-control-plane",
            "release-certification",
            "documentation-gardener",
            "upstream-change-monitor",
        ),
    ),
    PackageSpec(
        1,
        "P01",
        "elmos-harness-runtime-platform",
        "Phase 1（可信执行底座）",
        "01-elmos-harness-runtime-platform-v1.0.0.zip",
        "01-elmos-harness-runtime-platform",
        "1f26520d1146b22f872782d1dbb892690e45900997a4f3c0b72b96bc0f6f6295",
        89_168,
        60,
        157_157,
        ("P00",),
        (
            "harness-adapter-sdk",
            "event-sourced-session-runtime",
            "context-epoch-manager",
            "tool-runtime",
            "async-task-runtime",
            "continuable-subagent-manager",
            "permission-policy-engine",
            "approval-gate",
            "sandbox-runtime",
            "lsp-capability-seam",
            "compaction-and-resume",
            "headless-runtime-api",
            "readiness-dry-run",
        ),
    ),
    PackageSpec(
        2,
        "P02",
        "elmos-repository-intelligence-semantic-ir",
        "Phase 1（P0 核心护城河）",
        "02-elmos-repository-intelligence-semantic-ir-v1.0.0.zip",
        "02-elmos-repository-intelligence-semantic-ir",
        "5bbb33e3dcfe152dfe3075dd98a0600dab8da369f81ee7386180c4431c7330e4",
        87_739,
        59,
        154_012,
        ("P00", "P01"),
        (
            "repository-inventory-scanner",
            "language-framework-detector",
            "ast-symbol-indexer",
            "lsp-semantic-navigator",
            "program-graph-builder",
            "platform-graph-builder",
            "runtime-trace-ingestor",
            "semantic-ir-builder",
            "capability-discovery-ledger",
            "incremental-analysis-cache",
            "provenance-confidence-engine",
            "repository-query-service",
        ),
    ),
    PackageSpec(
        3,
        "P03",
        "elmos-project-generation-transformation-engine",
        "Phase 2（核心商业能力）",
        "03-elmos-project-generation-transformation-engine-v1.0.0.zip",
        "03-elmos-project-generation-transformation-engine",
        "e5950802a42970891536d3483d71c2680327da0525efd2a13be3299d1265103b",
        88_251,
        59,
        154_518,
        ("P00", "P01", "P02", "P05"),
        (
            "requirement-expander",
            "project-archetype-engine",
            "architecture-synthesizer",
            "implementation-dag-planner",
            "transformation-rule-engine",
            "mutation-exception-engine",
            "multi-language-emitter",
            "framework-platform-adapter",
            "data-integration-transformer",
            "frontend-miniapp-transformer",
            "infrastructure-operations-generator",
            "migration-controller",
        ),
    ),
    PackageSpec(
        4,
        "P04",
        "elmos-agent-orchestration-software-factory",
        "Phase 2（商业软件工厂）",
        "04-elmos-agent-orchestration-software-factory-v1.0.0.zip",
        "04-elmos-agent-orchestration-software-factory",
        "8ec202fa50b4087e1489f57c6601178b6584192077833d97367662b0ca246aea",
        88_426,
        59,
        154_757,
        ("P00", "P01", "P02", "P03", "P05", "P06"),
        (
            "workflow-tracker-adapter",
            "reconciliation-scheduler",
            "task-dag-orchestrator",
            "workspace-worktree-manager",
            "specialized-agent-registry",
            "continuable-collaboration-manager",
            "admission-concurrency-controller",
            "retry-stall-doomloop-controller",
            "workpad-progress-journal",
            "review-feedback-coordinator",
            "proof-of-work-assembler",
            "human-review-handoff",
        ),
    ),
    PackageSpec(
        5,
        "P05",
        "elmos-conversion-reliability-verification-harness",
        "Phase 1（P0 最高优先级）",
        "05-elmos-conversion-reliability-verification-harness-v1.0.0.zip",
        "05-elmos-conversion-reliability-verification-harness",
        "086a04bf4f6b741b5eb6d9f1e978f539a6a4d6e89fc7a72e72c95209246fd8fb",
        88_118,
        59,
        153_781,
        ("P00", "P01", "P02"),
        (
            "requirement-coverage-ledger",
            "capability-coverage-ledger",
            "mechanical-completion-gate",
            "verification-planner",
            "compiler-static-pipeline",
            "contract-integration-pipeline",
            "differential-runtime",
            "generative-testing",
            "ui-multimodal-verifier",
            "nonfunctional-verifier",
            "diagnosis-repair-loop",
            "evidence-certification-engine",
        ),
    ),
    PackageSpec(
        6,
        "P06",
        "elmos-intelligent-model-router",
        "Phase 2（质量/成本/隐私优化）",
        "06-elmos-intelligent-model-router-v1.0.0.zip",
        "06-elmos-intelligent-model-router",
        "1431512d09f180806c32f1df53d7d199fc21ea1b6ddda3f88870440d8830a28a",
        87_432,
        59,
        154_577,
        ("P00", "P01", "P05"),
        (
            "model-provider-catalog",
            "task-classifier",
            "route-constraint-engine",
            "benchmark-availability-gate",
            "historical-taskfit-scorer",
            "multi-objective-router",
            "fallback-circuitbreaker-hedging",
            "long-context-completeness-auditor",
            "multimodal-route",
            "cost-token-eta-engine",
            "privacy-data-policy-broker",
            "route-observability",
        ),
    ),
    PackageSpec(
        7,
        "P07",
        "elmos-transformation-learning-evolution",
        "Phase 3（长期复利护城河）",
        "07-elmos-transformation-learning-evolution-v1.0.0.zip",
        "07-elmos-transformation-learning-evolution",
        "ccef5c4a673c4ee8182304df327ec8b709d392ac1850c6a785bd79490990404d",
        87_690,
        59,
        154_181,
        ("P00", "P02", "P03", "P05", "P06"),
        (
            "transformation-knowledge-base",
            "project-archetype-knowledge-base",
            "failure-repair-corpus",
            "rule-promotion-governance",
            "benchmark-corpus",
            "evidence-corpus",
            "repair-retrieval-ranker",
            "drift-regression-detector",
            "active-learning-queue",
            "specialized-model-training",
            "tenant-ip-isolation",
            "knowledge-quality-auditor",
        ),
    ),
)

PACKAGE_BY_ID = {spec.package_id: spec for spec in PACKAGE_SPECS}

EXPECTED_RUNTIME_OPERATIONS = {
    "P00": "workflow",
    "P01": "runtime-plan",
    "P02": "repository-intelligence",
    "P03": "transformation-plan",
    "P04": "orchestration",
    "P05": "evidence-gate",
    "P06": "model-route",
    "P07": "knowledge",
}
EXPECTED_PUBLIC_METHOD_COUNTS = {
    "P00": 5,
    "P01": 8,
    "P02": 6,
    "P03": 6,
    "P04": 7,
    "P05": 6,
    "P06": 6,
    "P07": 6,
}


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest(value: bytes) -> str:
    return "sha256:" + _sha256(value)


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _decode_utf8(value: bytes, label: str) -> str:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise IntegrationError(f"{label} is not valid UTF-8") from exc


def _reject_json_constant(value: str) -> Any:
    raise IntegrationError(f"JSON contains a non-finite constant: {value}")


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise IntegrationError(f"JSON contains a duplicate key: {key}")
        result[key] = value
    return result


def _load_json(value: bytes, label: str) -> Any:
    try:
        return json.loads(
            _decode_utf8(value, label),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_json_constant,
        )
    except IntegrationError:
        raise
    except json.JSONDecodeError as exc:
        raise IntegrationError(f"invalid JSON in {label}: {exc}") from exc


def _validate_path_part(part: str, label: str) -> None:
    if not part or part in {".", ".."}:
        raise IntegrationError(f"{label} contains an ambiguous path segment")
    if part.endswith((" ", ".")):
        raise IntegrationError(f"{label} contains a trailing-dot/space segment: {part!r}")
    if any(character in _WINDOWS_INVALID for character in part):
        raise IntegrationError(f"{label} contains a reserved path character: {part!r}")
    if part.split(".", 1)[0].rstrip(" .").upper() in _WINDOWS_RESERVED:
        raise IntegrationError(f"{label} contains a reserved device name: {part!r}")


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


def _validate_member_metadata(info: zipfile.ZipInfo) -> int:
    if info.flag_bits & 0x1:
        raise IntegrationError(f"encrypted archive member is forbidden: {info.filename!r}")
    if info.is_dir() or info.filename.endswith("/"):
        raise IntegrationError(f"directory archive member is forbidden: {info.filename!r}")
    if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
        raise IntegrationError(
            f"unsupported archive compression method: {info.filename!r}"
        )
    unix_mode = (info.external_attr >> 16) & 0xFFFF
    file_type = stat.S_IFMT(unix_mode)
    if file_type not in {0, stat.S_IFREG}:
        raise IntegrationError(f"link or special archive member: {info.filename!r}")
    mode = stat.S_IMODE(unix_mode)
    if mode not in {0o644, 0o755}:
        raise IntegrationError(
            f"unsupported archive member mode {mode:#o}: {info.filename!r}"
        )
    if info.file_size < 0 or info.file_size > MAX_ARCHIVE_ENTRY_BYTES:
        raise IntegrationError(f"archive member size is unsafe: {info.filename!r}")
    if info.compress_size < 0:
        raise IntegrationError(
            f"archive compressed size is invalid: {info.filename!r}"
        )
    ratio = info.file_size / max(info.compress_size, 1)
    if ratio > MAX_COMPRESSION_RATIO:
        raise IntegrationError(
            f"archive compression ratio is unsafe: {info.filename!r}"
        )
    return mode


def inspect_archive(
    archive_path: Path,
    *,
    trusted_sha256: str | None = None,
    expected_archive_bytes: int | None = None,
    expected_entry_count: int | None = None,
    expected_total_bytes: int | None = None,
    expected_mode_counts: Mapping[int, int] | None = None,
) -> tuple[bytes, Mapping[str, ArchiveRecord]]:
    """Read a bounded ZIP snapshot without extracting or executing its content."""

    if not archive_path.is_file() or archive_path.is_symlink():
        raise IntegrationError(f"archive must be a regular file: {archive_path}")
    archive_bytes = archive_path.read_bytes()
    if len(archive_bytes) > MAX_ARCHIVE_BYTES:
        raise IntegrationError(f"archive exceeds the compressed-byte budget: {archive_path}")
    observed_sha256 = _sha256(archive_bytes)
    if trusted_sha256 is not None and observed_sha256 != trusted_sha256:
        raise IntegrationError(
            f"archive SHA-256 mismatch for {archive_path.name}: "
            f"expected={trusted_sha256} actual={observed_sha256}"
        )
    if expected_archive_bytes is not None and len(archive_bytes) != expected_archive_bytes:
        raise IntegrationError(
            f"archive byte count mismatch for {archive_path.name}: "
            f"expected={expected_archive_bytes} actual={len(archive_bytes)}"
        )
    try:
        handle = zipfile.ZipFile(io.BytesIO(archive_bytes), "r")
    except zipfile.BadZipFile as exc:
        raise IntegrationError(f"invalid ZIP archive: {archive_path}") from exc

    records: dict[str, ArchiveRecord] = {}
    raw_names: set[str] = set()
    folded_names: set[str] = set()
    mode_counts: dict[int, int] = {}
    total_bytes = 0
    try:
        with handle:
            infos = handle.infolist()
            if expected_entry_count is not None and len(infos) != expected_entry_count:
                raise IntegrationError(
                    f"archive entry count mismatch for {archive_path.name}: "
                    f"expected={expected_entry_count} actual={len(infos)}"
                )
            for info in infos:
                relative = _validated_relative_path(info.filename, "archive member").as_posix()
                if relative in raw_names:
                    raise IntegrationError(f"duplicate archive member: {relative!r}")
                raw_names.add(relative)
                folded = unicodedata.normalize("NFC", relative).casefold()
                if folded in folded_names:
                    raise IntegrationError(
                        f"case/Unicode archive path collision: {relative!r}"
                    )
                folded_names.add(folded)
                mode = _validate_member_metadata(info)
                total_bytes += info.file_size
                if total_bytes > MAX_ARCHIVE_TOTAL_BYTES:
                    raise IntegrationError("archive exceeds the expansion budget")
                chunks: list[bytes] = []
                observed_size = 0
                digest = hashlib.sha256()
                with handle.open(info, "r") as member:
                    while True:
                        chunk = member.read(64 * 1024)
                        if not chunk:
                            break
                        observed_size += len(chunk)
                        if (
                            observed_size > info.file_size
                            or observed_size > MAX_ARCHIVE_ENTRY_BYTES
                        ):
                            raise IntegrationError(
                                f"archive member exceeded its declared size: {relative}"
                            )
                        digest.update(chunk)
                        chunks.append(chunk)
                if observed_size != info.file_size:
                    raise IntegrationError(
                        f"archive member size mismatch: {relative}"
                    )
                records[relative] = ArchiveRecord(
                    relative=relative,
                    size=observed_size,
                    compressed_size=info.compress_size,
                    mode=mode,
                    sha256=digest.hexdigest(),
                    content=b"".join(chunks),
                )
                mode_counts[mode] = mode_counts.get(mode, 0) + 1
    except IntegrationError:
        raise
    except (OSError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise IntegrationError(f"cannot safely inspect archive {archive_path}: {exc}") from exc

    if expected_total_bytes is not None and total_bytes != expected_total_bytes:
        raise IntegrationError(
            f"archive uncompressed-byte mismatch for {archive_path.name}: "
            f"expected={expected_total_bytes} actual={total_bytes}"
        )
    if expected_mode_counts is not None and mode_counts != dict(expected_mode_counts):
        raise IntegrationError(
            f"archive mode distribution mismatch for {archive_path.name}: {mode_counts}"
        )
    return archive_bytes, dict(sorted(records.items()))


def _parse_frontmatter(value: bytes, label: str) -> tuple[Mapping[str, Any], str]:
    text = _decode_utf8(value, label)
    if "\r" in text:
        raise IntegrationError(f"Skill must use canonical LF newlines: {label}")
    match = re.match(r"^---\n(.*?)\n---(?:\n|\Z)", text, re.DOTALL)
    if match is None:
        raise IntegrationError(f"invalid Skill frontmatter envelope: {label}")
    document: dict[str, Any] = {}
    active_mapping: dict[str, str] | None = None
    for line_number, line in enumerate(match.group(1).splitlines(), 1):
        if not line.strip():
            continue
        if "\t" in line:
            raise IntegrationError(f"tabs are forbidden in Skill frontmatter: {label}")
        indentation = len(line) - len(line.lstrip(" "))
        stripped = line[indentation:]
        if ":" not in stripped:
            raise IntegrationError(
                f"invalid Skill frontmatter row {line_number}: {label}"
            )
        key, raw_value = stripped.split(":", 1)
        if _FRONTMATTER_KEY_RE.fullmatch(key) is None:
            raise IntegrationError(f"invalid Skill frontmatter key {key!r}: {label}")
        if indentation == 0:
            if key in document:
                raise IntegrationError(f"duplicate Skill frontmatter key {key}: {label}")
            if raw_value.strip():
                document[key] = _parse_frontmatter_scalar(raw_value.strip(), label)
                active_mapping = None
            else:
                nested: dict[str, str] = {}
                document[key] = nested
                active_mapping = nested
        elif indentation == 2 and active_mapping is not None:
            if key in active_mapping:
                raise IntegrationError(
                    f"duplicate nested Skill frontmatter key {key}: {label}"
                )
            if not raw_value.strip():
                raise IntegrationError(
                    f"nested Skill frontmatter value is empty: {label}: {key}"
                )
            active_mapping[key] = _parse_frontmatter_scalar(raw_value.strip(), label)
        else:
            raise IntegrationError(
                f"unsupported Skill frontmatter indentation at row {line_number}: {label}"
            )
    body = text[match.end() :].lstrip("\n")
    if not body.strip():
        raise IntegrationError(f"Skill body is empty: {label}")
    return document, body


def _parse_frontmatter_scalar(value: str, label: str) -> str:
    if value.startswith('"'):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise IntegrationError(
                f"invalid quoted Skill frontmatter scalar in {label}"
            ) from exc
        if not isinstance(parsed, str):
            raise IntegrationError(f"Skill frontmatter scalar is not text: {label}")
        return parsed
    if value.startswith("'"):
        if not value.endswith("'") or len(value) < 2:
            raise IntegrationError(f"invalid quoted Skill frontmatter scalar: {label}")
        return value[1:-1].replace("''", "'")
    if value[0] in "[{&*!>|%@`" or " #" in value:
        raise IntegrationError(f"unsupported Skill frontmatter scalar syntax: {label}")
    return value


def _validate_skill_name(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) > 64
        or _SKILL_NAME_RE.fullmatch(value) is None
    ):
        raise IntegrationError(f"invalid or overlong Skill name in {label}: {value!r}")
    return value


def _installed_skill_name(source_name: str) -> str:
    return INSTALLED_NAME_OVERRIDES.get(source_name, source_name)


def _installed_dependencies(source_dependencies: Sequence[str]) -> tuple[str, ...]:
    return tuple(_installed_skill_name(name) for name in source_dependencies)


def _expected_inventory(spec: PackageSpec) -> set[str]:
    package_paths = {
        f"{spec.archive_root}/{relative}" for relative in PACKAGE_FIXED_PATHS
    }
    child_paths = {
        f"{spec.archive_root}/skills/{subskill}/SKILL.md"
        for subskill in spec.subskills
    }
    return set(SHARED_PATHS) | package_paths | child_paths


def _validate_manifest(
    manifest: Any, spec: PackageSpec, label: str
) -> Mapping[str, Any]:
    if not isinstance(manifest, Mapping):
        raise IntegrationError(f"package manifest must be a JSON object: {label}")
    expected_keys = {
        "package_id",
        "name",
        "version",
        "phase",
        "dependencies",
        "capabilities",
        "source_pins",
        "subskills",
    }
    if set(manifest) != expected_keys:
        raise IntegrationError(f"package manifest keys are not exact: {label}")
    if (
        manifest.get("package_id") != spec.package_id
        or manifest.get("name") != spec.name
        or manifest.get("version") != PACKAGE_VERSION
        or manifest.get("phase") != spec.phase
    ):
        raise IntegrationError(f"package manifest identity/version mismatch: {label}")
    if manifest.get("dependencies") != list(spec.dependencies):
        raise IntegrationError(f"package dependency DAG mismatch: {spec.package_id}")
    if manifest.get("subskills") != list(spec.subskills):
        raise IntegrationError(f"package subskills are not the exact manifest inventory: {label}")

    capabilities = manifest.get("capabilities")
    expected_capability_count = 8 if spec.package_id == "P00" else 12
    if not isinstance(capabilities, list) or len(capabilities) != expected_capability_count:
        raise IntegrationError(f"package capability inventory mismatch: {label}")
    for number, capability in enumerate(capabilities, 1):
        if (
            not isinstance(capability, Mapping)
            or set(capability) != {"id", "name", "maturity"}
            or capability.get("id") != f"{spec.package_id}-C{number:02d}"
            or not isinstance(capability.get("name"), str)
            or not capability.get("name")
            or capability.get("maturity") != "design"
        ):
            raise IntegrationError(f"invalid package capability manifest row: {label}")
    source_pins = manifest.get("source_pins")
    if (
        not isinstance(source_pins, list)
        or not source_pins
        or any(not isinstance(item, str) or not item for item in source_pins)
        or len(set(source_pins)) != len(source_pins)
    ):
        raise IntegrationError(f"invalid package source_pins: {label}")
    return manifest


def _validate_source_frontmatter(
    frontmatter: Mapping[str, Any],
    *,
    spec: PackageSpec,
    expected_name: str,
    role: str,
    label: str,
) -> None:
    if set(frontmatter) != {
        "name",
        "description",
        "license",
        "compatibility",
        "metadata",
    }:
        raise IntegrationError(f"Skill frontmatter keys are not exact: {label}")
    if _validate_skill_name(frontmatter.get("name"), label) != expected_name:
        raise IntegrationError(f"Skill name does not match its manifest identity: {label}")
    description = frontmatter.get("description")
    if (
        not isinstance(description, str)
        or not description.strip()
        or len(description) > 1024
    ):
        raise IntegrationError(f"Skill description is invalid: {label}")
    if frontmatter.get("license") != "Proprietary":
        raise IntegrationError(f"Skill license identity mismatch: {label}")
    if not isinstance(frontmatter.get("compatibility"), str):
        raise IntegrationError(f"Skill compatibility is invalid: {label}")
    metadata = frontmatter.get("metadata")
    if not isinstance(metadata, Mapping):
        raise IntegrationError(f"Skill metadata must be a mapping: {label}")
    if role == "package-orchestrator":
        if set(metadata) != {
            "package_id",
            "version",
            "phase",
            "dependencies",
            "maturity",
        }:
            raise IntegrationError(f"package Skill metadata keys are not exact: {label}")
        expected_dependencies = (
            "none" if not spec.dependencies else ", ".join(item[1:] for item in spec.dependencies)
        )
        expected_metadata = {
            "package_id": spec.package_id,
            "version": PACKAGE_VERSION,
            "phase": spec.phase,
            "dependencies": expected_dependencies,
            "maturity": "commercial-product-blueprint",
        }
    else:
        if set(metadata) != {"parent_package", "version", "maturity"}:
            raise IntegrationError(f"child Skill metadata keys are not exact: {label}")
        expected_metadata = {
            "parent_package": spec.package_id,
            "version": PACKAGE_VERSION,
            "maturity": "commercial-product-blueprint",
        }
    if dict(metadata) != expected_metadata:
        raise IntegrationError(f"Skill metadata identity/version mismatch: {label}")


def _parse_source_skills(
    spec: PackageSpec, files: Mapping[str, ArchiveRecord]
) -> tuple[SourceSkill, ...]:
    records: list[SourceSkill] = []
    root_path = f"{spec.archive_root}/SKILL.md"
    root_record = files[root_path]
    root_frontmatter, root_body = _parse_frontmatter(root_record.content, root_path)
    _validate_source_frontmatter(
        root_frontmatter,
        spec=spec,
        expected_name=spec.name,
        role="package-orchestrator",
        label=root_path,
    )
    records.append(
        SourceSkill(
            ordinal=0,
            package_id=spec.package_id,
            package_name=spec.name,
            role="package-orchestrator",
            source_key=spec.package_id,
            source_name=spec.name,
            source_path=root_path,
            source_sha256=root_record.sha256,
            description=str(root_frontmatter["description"]),
            body=root_body,
            installed_dependencies=tuple(
                PACKAGE_BY_ID[dependency].name for dependency in spec.dependencies
            ),
            source_archive=spec.archive_name,
        )
    )
    for ordinal, subskill in enumerate(spec.subskills, 1):
        source_path = f"{spec.archive_root}/skills/{subskill}/SKILL.md"
        source_record = files[source_path]
        frontmatter, body = _parse_frontmatter(source_record.content, source_path)
        expected_name = f"elmos-{subskill}"
        _validate_source_frontmatter(
            frontmatter,
            spec=spec,
            expected_name=expected_name,
            role="child",
            label=source_path,
        )
        records.append(
            SourceSkill(
                ordinal=ordinal,
                package_id=spec.package_id,
                package_name=spec.name,
                role="child",
                source_key=f"{spec.package_id}:{subskill}",
                source_name=expected_name,
                source_path=source_path,
                source_sha256=source_record.sha256,
                description=str(frontmatter["description"]),
                body=body,
                installed_dependencies=(spec.name,),
                source_archive=spec.archive_name,
            )
        )
    return tuple(records)


def validate_archive(
    archive_path: Path,
    spec: PackageSpec,
    *,
    verify_archive_identity: bool = True,
) -> PackageSnapshot:
    archive_bytes, files = inspect_archive(
        archive_path,
        trusted_sha256=spec.archive_sha256 if verify_archive_identity else None,
        expected_archive_bytes=spec.archive_bytes if verify_archive_identity else None,
        expected_entry_count=spec.entry_count if verify_archive_identity else None,
        expected_total_bytes=spec.uncompressed_bytes if verify_archive_identity else None,
        expected_mode_counts=(
            {0o644: spec.entry_count - 2, 0o755: 2}
            if verify_archive_identity
            else None
        ),
    )
    expected_paths = _expected_inventory(spec)
    observed_paths = set(files)
    if observed_paths != expected_paths:
        missing = sorted(expected_paths - observed_paths)
        unknown = sorted(observed_paths - expected_paths)
        raise IntegrationError(
            f"archive inventory is not exact for {spec.package_id}: "
            f"missing={missing[:5]} unknown={unknown[:5]}"
        )
    manifest_path = f"{spec.archive_root}/manifest.json"
    manifest = _validate_manifest(
        _load_json(files[manifest_path].content, manifest_path), spec, manifest_path
    )
    if files["VERSION"].content != b"1.0.0\n":
        raise IntegrationError(f"shared VERSION mismatch in {spec.archive_name}")
    skills = _parse_source_skills(spec, files)
    expected_skill_count = 1 + len(spec.subskills)
    if len(skills) != expected_skill_count:
        raise IntegrationError(f"source Skill inventory mismatch for {spec.package_id}")
    return PackageSnapshot(
        spec=spec,
        archive_sha256=_sha256(archive_bytes),
        archive_bytes=len(archive_bytes),
        entry_count=len(files),
        uncompressed_bytes=sum(record.size for record in files.values()),
        files=files,
        manifest=manifest,
        manifest_sha256=files[manifest_path].sha256,
        skills=skills,
    )


def validate_package_graph(
    dependencies: Mapping[str, Sequence[str]],
    *,
    expected_ids: Sequence[str] | None = None,
) -> tuple[str, ...]:
    if expected_ids is not None and set(dependencies) != set(expected_ids):
        raise IntegrationError("package dependency DAG does not contain exact P00-P07 IDs")
    known = set(dependencies)
    for package_id, package_dependencies in dependencies.items():
        if len(set(package_dependencies)) != len(package_dependencies):
            raise IntegrationError(f"duplicate package dependency: {package_id}")
        if package_id in package_dependencies:
            raise IntegrationError(f"self package dependency: {package_id}")
        unknown = sorted(set(package_dependencies) - known)
        if unknown:
            raise IntegrationError(
                f"unknown package dependencies for {package_id}: {unknown}"
            )

    state: dict[str, int] = {}
    order: list[str] = []

    def visit(package_id: str, stack: tuple[str, ...]) -> None:
        observed = state.get(package_id, 0)
        if observed == 1:
            raise IntegrationError(
                "package dependency cycle: " + " -> ".join((*stack, package_id))
            )
        if observed == 2:
            return
        state[package_id] = 1
        for dependency in dependencies[package_id]:
            visit(dependency, (*stack, package_id))
        state[package_id] = 2
        order.append(package_id)

    traversal = expected_ids if expected_ids is not None else sorted(dependencies)
    for package_id in traversal:
        visit(package_id, ())
    return tuple(order)


def merge_source_trees(
    packages: Sequence[PackageSnapshot],
) -> Mapping[str, ArchiveRecord]:
    merged: dict[str, ArchiveRecord] = {}
    folded_paths: dict[str, str] = {}
    shared = set(SHARED_PATHS)
    for package in packages:
        for relative, record in package.files.items():
            folded = unicodedata.normalize("NFC", relative).casefold()
            prior_path = folded_paths.get(folded)
            if prior_path is not None and prior_path != relative:
                raise IntegrationError(
                    f"case/Unicode canonical-source collision: {prior_path!r} / {relative!r}"
                )
            folded_paths[folded] = relative
            prior = merged.get(relative)
            if prior is None:
                merged[relative] = record
                continue
            if relative not in shared:
                raise IntegrationError(f"non-shared archive path is duplicated: {relative}")
            if prior.content != record.content or prior.mode != record.mode:
                raise IntegrationError(
                    f"shared file mismatch across archives: {relative}"
                )
    return dict(sorted(merged.items()))


def validate_archives(
    archive_directory: Path,
    *,
    verify_archive_identity: bool = True,
) -> IntegrationSnapshot:
    if not archive_directory.is_dir() or archive_directory.is_symlink():
        raise IntegrationError(
            f"archive directory must be a real directory: {archive_directory}"
        )
    observed_names = sorted(
        path.name
        for path in archive_directory.iterdir()
        if path.is_file() and path.suffix.casefold() == ".zip"
    )
    expected_names = sorted(spec.archive_name for spec in PACKAGE_SPECS)
    if observed_names != expected_names:
        raise IntegrationError(
            f"archive directory must contain exactly the eight pinned ZIPs: "
            f"expected={expected_names} actual={observed_names}"
        )
    packages = tuple(
        validate_archive(
            archive_directory / spec.archive_name,
            spec,
            verify_archive_identity=verify_archive_identity,
        )
        for spec in PACKAGE_SPECS
    )
    dependency_map = {
        package.spec.package_id: tuple(package.manifest["dependencies"])
        for package in packages
    }
    package_order = validate_package_graph(
        dependency_map,
        expected_ids=tuple(spec.package_id for spec in PACKAGE_SPECS),
    )
    edge_count = sum(len(dependencies) for dependencies in dependency_map.values())
    if edge_count != EXPECTED_PACKAGE_DEPENDENCY_EDGES:
        raise IntegrationError(
            f"package dependency edge count mismatch: {edge_count}"
        )
    canonical_files = merge_source_trees(packages)
    source_skills = tuple(skill for package in packages for skill in package.skills)
    skill_names = [skill.source_name for skill in source_skills]
    if len(source_skills) != EXPECTED_SOURCE_SKILL_COUNT:
        raise IntegrationError(
            f"source Skill count mismatch: {len(source_skills)}"
        )
    if len(set(skill_names)) != len(skill_names):
        raise IntegrationError("source Skill names are not globally unique")
    if ROOT_SKILL_NAME in set(skill_names):
        raise IntegrationError("repo-owned root Skill collides with an archive Skill")
    unknown_overrides = sorted(set(INSTALLED_NAME_OVERRIDES) - set(skill_names))
    if unknown_overrides:
        raise IntegrationError(
            f"installed-name overrides reference unknown source Skills: {unknown_overrides}"
        )
    installed_names = [ROOT_SKILL_NAME]
    for skill in source_skills:
        installed_name = _validate_skill_name(
            _installed_skill_name(skill.source_name),
            f"installed name for {skill.source_name}",
        )
        if skill.source_name in INSTALLED_NAME_OVERRIDES and installed_name == skill.source_name:
            raise IntegrationError(f"installed-name override is ineffective: {skill.source_name}")
        installed_names.append(installed_name)
    folded_installed = [
        unicodedata.normalize("NFC", name).casefold() for name in installed_names
    ]
    if len(set(folded_installed)) != len(folded_installed):
        raise IntegrationError("resolved installed Skill names are not globally unique")
    if len(canonical_files) != EXPECTED_CANONICAL_FILE_COUNT:
        raise IntegrationError(
            f"canonical union file count mismatch: {len(canonical_files)}"
        )
    if sum(package.entry_count for package in packages) != EXPECTED_ARCHIVE_ENTRY_COUNT:
        raise IntegrationError("aggregate archive entry count mismatch")
    if len(source_skills) - EXPECTED_SOURCE_ROOT_SKILL_COUNT != EXPECTED_SOURCE_CHILD_SKILL_COUNT:
        raise IntegrationError("source child Skill count mismatch")
    return IntegrationSnapshot(
        packages=packages,
        canonical_files=canonical_files,
        source_skills=source_skills,
        package_topological_order=package_order,
    )


def _read_runtime_artifact(repository_root: Path, relative: str) -> bytes:
    root = repository_root.resolve(strict=True)
    path_value = _validated_relative_path(relative, "runtime artifact")
    current = root
    for part in path_value.parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise IntegrationError(f"runtime artifact traverses a symlink: {current}")
        if not current.is_dir():
            raise IntegrationError(f"runtime artifact parent is missing: {current}")
    path = root.joinpath(*path_value.parts)
    if path.is_symlink() or not path.is_file():
        raise IntegrationError(f"required runtime artifact is missing or unsafe: {relative}")
    observed_mode = stat.S_IMODE(path.stat().st_mode)
    if observed_mode != RUNTIME_FILE_MODE:
        raise IntegrationError(
            f"runtime artifact mode mismatch for {relative}: {observed_mode:#o}"
        )
    if path.stat().st_size > MAX_RUNTIME_ARTIFACT_BYTES:
        raise IntegrationError(f"runtime artifact exceeds byte budget: {relative}")
    value = path.read_bytes()
    if len(value) > MAX_RUNTIME_ARTIFACT_BYTES:
        raise IntegrationError(f"runtime artifact exceeded byte budget: {relative}")
    return value


def _string_array(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise IntegrationError(f"{label} must be an array")
    result = tuple(value)
    if any(not isinstance(item, str) or not item for item in result):
        raise IntegrationError(f"{label} must contain non-empty strings")
    if len(set(result)) != len(result):
        raise IntegrationError(f"{label} contains duplicates")
    return result


def _declared_public_methods(
    snapshot: IntegrationSnapshot,
) -> tuple[Mapping[str, Any], ...]:
    methods: list[Mapping[str, Any]] = []
    observed: set[str] = set()
    counts = {spec.package_id: 0 for spec in PACKAGE_SPECS}
    for package in snapshot.packages:
        relative = f"{package.spec.archive_root}/INTERFACE-CONTRACTS.md"
        text = _decode_utf8(package.files[relative].content, relative)
        for line in text.splitlines():
            if not line.startswith("|") or not line.endswith("|"):
                continue
            cells = tuple(cell.strip() for cell in line.strip("|").split("|"))
            if len(cells) != 4 or _PUBLIC_METHOD_RE.fullmatch(cells[0]) is None:
                continue
            stable_errors = tuple(item.strip() for item in cells[3].split("/"))
            if not stable_errors or any(
                _STABLE_ERROR_RE.fullmatch(item) is None for item in stable_errors
            ):
                raise IntegrationError(
                    f"archive public method has invalid stable errors: {relative}: {line}"
                )
            method = cells[0]
            if method in observed:
                raise IntegrationError(f"duplicate archive public method: {method}")
            observed.add(method)
            counts[package.spec.package_id] += 1
            methods.append(
                {
                    "method": method,
                    "package_id": package.spec.package_id,
                    "stable_errors": stable_errors,
                }
            )
    if len(methods) != 50 or counts != EXPECTED_PUBLIC_METHOD_COUNTS:
        raise IntegrationError(
            f"archive public-method inventory drifted: count={len(methods)} packages={counts}"
        )
    return tuple(methods)


def validate_runtime_artifacts(
    repository_root: Path,
    snapshot: IntegrationSnapshot,
) -> RuntimeArtifactsSnapshot:
    """Validate runtime registries and modules as inert, digest-bound data."""

    artifact_bytes = {
        relative: _read_runtime_artifact(repository_root, relative)
        for relative in RUNTIME_ARTIFACTS
    }
    artifact_digests = {
        relative: _digest(value) for relative, value in artifact_bytes.items()
    }
    skill_registry = _load_json(
        artifact_bytes[RUNTIME_SKILL_REGISTRY], RUNTIME_SKILL_REGISTRY
    )
    capability_registry = _load_json(
        artifact_bytes[RUNTIME_CAPABILITY_REGISTRY], RUNTIME_CAPABILITY_REGISTRY
    )
    public_method_registry = _load_json(
        artifact_bytes[RUNTIME_PUBLIC_METHOD_REGISTRY],
        RUNTIME_PUBLIC_METHOD_REGISTRY,
    )
    if not isinstance(skill_registry, Mapping) or set(skill_registry) != {
        "schema_version",
        "root_skill",
        "packages",
    }:
        raise IntegrationError("runtime Skill registry root fields are not exact")
    if skill_registry.get("schema_version") != "1.0":
        raise IntegrationError("runtime Skill registry schema version mismatch")
    root_binding = skill_registry.get("root_skill")
    if (
        not isinstance(root_binding, Mapping)
        or set(root_binding) != {"name", "operation"}
        or root_binding.get("name") != ROOT_SKILL_NAME
        or root_binding.get("operation") != "root-route"
    ):
        raise IntegrationError("runtime root Skill binding is not exact")

    package_rows = skill_registry.get("packages")
    if not isinstance(package_rows, list) or len(package_rows) != EXPECTED_PACKAGE_COUNT:
        raise IntegrationError("runtime Skill registry must contain exactly P00-P07")
    skill_to_package: dict[str, str] = {ROOT_SKILL_NAME: "ROOT"}
    skill_to_operation: dict[str, str] = {ROOT_SKILL_NAME: "root-route"}
    adapter_actions_by_package: dict[str, frozenset[str]] = {"ROOT": frozenset()}
    required_adapter_actions: dict[str, set[str]] = {
        spec.package_id: set() for spec in PACKAGE_SPECS
    }
    for index, (row, package) in enumerate(
        zip(package_rows, snapshot.packages, strict=True)
    ):
        label = f"runtime Skill registry packages[{index}]"
        if not isinstance(row, Mapping) or set(row) != {
            "package_id",
            "name",
            "dependencies",
            "operation",
            "adapter_actions",
            "skills",
        }:
            raise IntegrationError(f"{label} fields are not exact")
        expected_children = tuple(
            skill.source_name for skill in package.skills if skill.role == "child"
        )
        dependencies = _string_array(row.get("dependencies"), f"{label}.dependencies")
        adapter_actions = _string_array(
            row.get("adapter_actions"), f"{label}.adapter_actions"
        )
        children = _string_array(row.get("skills"), f"{label}.skills")
        if (
            row.get("package_id") != package.spec.package_id
            or row.get("name") != package.spec.name
            or dependencies != package.spec.dependencies
            or row.get("operation")
            != EXPECTED_RUNTIME_OPERATIONS[package.spec.package_id]
            or children != expected_children
        ):
            raise IntegrationError(f"{label} identity, DAG, operation, or Skills drifted")
        if tuple(sorted(adapter_actions)) != adapter_actions or any(
            _ACTION_NAME_RE.fullmatch(action) is None for action in adapter_actions
        ):
            raise IntegrationError(f"{label}.adapter_actions are not canonical")
        adapter_actions_by_package[package.spec.package_id] = frozenset(adapter_actions)
        for skill_name in (package.spec.name, *expected_children):
            if skill_name in skill_to_package:
                raise IntegrationError(f"duplicate runtime Skill binding: {skill_name}")
            skill_to_package[skill_name] = package.spec.package_id
            skill_to_operation[skill_name] = str(row["operation"])

    expected_names = (ROOT_SKILL_NAME, *(skill.source_name for skill in snapshot.source_skills))
    if tuple(skill_to_package) != expected_names:
        raise IntegrationError("runtime Skill registry does not bind the exact 102 Skills")

    if not isinstance(capability_registry, Mapping) or set(capability_registry) != {
        "schema_version",
        "capabilities",
    }:
        raise IntegrationError("runtime capability registry root fields are not exact")
    if capability_registry.get("schema_version") != "1.0":
        raise IntegrationError("runtime capability registry schema version mismatch")
    capability_rows = capability_registry.get("capabilities")
    if not isinstance(capability_rows, list) or len(capability_rows) != len(expected_names):
        raise IntegrationError("runtime capability registry must contain exactly 102 rows")
    capability_by_skill: dict[str, Mapping[str, Any]] = {}
    observed_order: list[str] = []
    for index, row in enumerate(capability_rows):
        label = f"runtime capability registry capabilities[{index}]"
        if not isinstance(row, Mapping) or set(row) != {
            "skill_name",
            "action",
            "mode",
            "required_inputs",
        }:
            raise IntegrationError(f"{label} fields are not exact")
        skill_name = row.get("skill_name")
        action = row.get("action")
        mode = row.get("mode")
        required_inputs = _string_array(
            row.get("required_inputs"), f"{label}.required_inputs"
        )
        if (
            not isinstance(skill_name, str)
            or skill_name not in skill_to_package
            or skill_name in capability_by_skill
        ):
            raise IntegrationError(f"{label}.skill_name is unknown or duplicated")
        if not isinstance(action, str) or _ACTION_NAME_RE.fullmatch(action) is None:
            raise IntegrationError(f"{label}.action is invalid")
        if mode not in {"local", "requires_adapter"}:
            raise IntegrationError(f"{label}.mode is invalid")
        if not required_inputs or any(
            _INPUT_NAME_RE.fullmatch(item) is None for item in required_inputs
        ):
            raise IntegrationError(f"{label}.required_inputs are invalid")
        package_id = skill_to_package[skill_name]
        expected_adapter_mode = action in adapter_actions_by_package[package_id]
        if (mode == "requires_adapter") != expected_adapter_mode:
            raise IntegrationError(
                f"{label} action/mode is incoherent with package {package_id} adapter boundary"
            )
        if mode == "requires_adapter":
            required_adapter_actions[package_id].add(action)
        normalized = {
            "skill_name": skill_name,
            "package_id": package_id,
            "operation": skill_to_operation[skill_name],
            "action": action,
            "mode": mode,
            "required_inputs": list(required_inputs),
        }
        capability_by_skill[skill_name] = normalized
        observed_order.append(skill_name)
    if tuple(observed_order) != expected_names or set(capability_by_skill) != set(expected_names):
        raise IntegrationError("runtime capability registry does not bind the exact 102 Skills")

    if not isinstance(public_method_registry, Mapping) or set(public_method_registry) != {
        "schema_version",
        "methods",
    }:
        raise IntegrationError("runtime public-method registry root fields are not exact")
    if public_method_registry.get("schema_version") != "1.0":
        raise IntegrationError("runtime public-method registry schema version mismatch")
    method_rows = public_method_registry.get("methods")
    if not isinstance(method_rows, list) or len(method_rows) != 50:
        raise IntegrationError("runtime public-method registry must contain exactly 50 rows")
    observed_methods: set[str] = set()
    method_counts = {spec.package_id: 0 for spec in PACKAGE_SPECS}
    prior_package_ordinal = -1
    package_ordinals = {spec.package_id: spec.ordinal for spec in PACKAGE_SPECS}
    declared_methods = _declared_public_methods(snapshot)
    for index, (row, declared) in enumerate(
        zip(method_rows, declared_methods, strict=True)
    ):
        label = f"runtime public-method registry methods[{index}]"
        if not isinstance(row, Mapping) or set(row) != {
            "method",
            "package_id",
            "action",
            "execution_mode",
            "required_inputs",
            "domain_errors",
            "platform_errors",
        }:
            raise IntegrationError(f"{label} fields are not exact")
        method = row.get("method")
        package_id = row.get("package_id")
        action = row.get("action")
        mode = row.get("execution_mode")
        required_inputs = _string_array(
            row.get("required_inputs"), f"{label}.required_inputs"
        )
        domain_errors = _string_array(
            row.get("domain_errors"), f"{label}.domain_errors"
        )
        platform_errors = _string_array(
            row.get("platform_errors"), f"{label}.platform_errors"
        )
        if (
            not isinstance(method, str)
            or _PUBLIC_METHOD_RE.fullmatch(method) is None
            or method in observed_methods
        ):
            raise IntegrationError(f"{label}.method is invalid or duplicated")
        if not isinstance(package_id, str) or package_id not in package_ordinals:
            raise IntegrationError(f"{label}.package_id is invalid")
        if package_ordinals[package_id] < prior_package_ordinal:
            raise IntegrationError("runtime public-method registry package order drifted")
        prior_package_ordinal = package_ordinals[package_id]
        if not isinstance(action, str) or _ACTION_NAME_RE.fullmatch(action) is None:
            raise IntegrationError(f"{label}.action is invalid")
        if mode not in {"local", "requires_adapter"}:
            raise IntegrationError(f"{label}.execution_mode is invalid")
        if not required_inputs or any(
            _INPUT_NAME_RE.fullmatch(item) is None for item in required_inputs
        ):
            raise IntegrationError(f"{label}.required_inputs are invalid")
        if not domain_errors or any(
            _STABLE_ERROR_RE.fullmatch(item) is None for item in domain_errors
        ):
            raise IntegrationError(f"{label}.domain_errors are invalid")
        if not platform_errors or any(
            _STABLE_ERROR_RE.fullmatch(item) is None for item in platform_errors
        ):
            raise IntegrationError(f"{label}.platform_errors are invalid")
        if (
            method != declared["method"]
            or package_id != declared["package_id"]
            or domain_errors != declared["stable_errors"]
        ):
            raise IntegrationError(
                f"{label} does not match the archive public-method identity/errors contract"
            )
        expected_adapter_mode = action in adapter_actions_by_package[package_id]
        if (mode == "requires_adapter") != expected_adapter_mode:
            raise IntegrationError(
                f"{label} action/mode is incoherent with package {package_id} adapter boundary"
            )
        if mode == "requires_adapter":
            required_adapter_actions[package_id].add(action)
        observed_methods.add(method)
        method_counts[package_id] += 1
    if method_counts != EXPECTED_PUBLIC_METHOD_COUNTS:
        raise IntegrationError(
            f"runtime public-method package counts drifted: {method_counts}"
        )
    for package_id, observed_actions in adapter_actions_by_package.items():
        if package_id == "ROOT":
            continue
        expected_actions = frozenset(required_adapter_actions[package_id])
        if observed_actions != expected_actions:
            raise IntegrationError(
                f"runtime package {package_id} adapter_actions are not the exact "
                "capability/public-method requires_adapter union"
            )
    for relative, expected_digest in EXPECTED_RUNTIME_REGISTRY_SHA256.items():
        if artifact_digests[relative] != expected_digest:
            raise IntegrationError(
                f"runtime registry pinned digest mismatch for {relative}: "
                f"expected={expected_digest} actual={artifact_digests[relative]}"
            )

    aggregate = hashlib.sha256()
    for relative, digest in sorted(artifact_digests.items()):
        aggregate.update(relative.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(f"{RUNTIME_FILE_MODE:04o}".encode("ascii"))
        aggregate.update(b"\0")
        aggregate.update(digest.encode("ascii"))
        aggregate.update(b"\0")
    return RuntimeArtifactsSnapshot(
        skill_registry=skill_registry,
        capability_registry=capability_registry,
        public_method_registry=public_method_registry,
        capability_by_skill=dict(sorted(capability_by_skill.items())),
        skill_to_package=dict(skill_to_package),
        skill_to_operation=dict(skill_to_operation),
        artifact_digests=dict(sorted(artifact_digests.items())),
        aggregate_digest="sha256:" + aggregate.hexdigest(),
    )


def _yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _materialized_source_path(logical_path: str) -> str:
    explicit = NEUTRALIZED_SOURCE_PATHS.get(logical_path)
    if explicit is not None:
        return explicit
    if PurePosixPath(logical_path).name == "SKILL.md":
        return logical_path + ".source-data"
    return logical_path


def _source_skill_metadata(skill: SourceSkill) -> Mapping[str, str]:
    materialized_path = _materialized_source_path(skill.source_path)
    installed_name = _installed_skill_name(skill.source_name)
    return {
        "source_package": PACKAGE_NAME,
        "source_package_id": skill.package_id,
        "source_package_name": skill.package_name,
        "source_archive": skill.source_archive,
        "source_role": skill.role,
        "source_key": skill.source_key,
        "source_name": skill.source_name,
        "installed_name": installed_name,
        "source_logical_path": skill.source_path,
        "source_path": (SOURCE_RELATIVE / materialized_path).as_posix(),
        "source_materialized_path": materialized_path,
        "source_sha256": "sha256:" + skill.source_sha256,
        "source_version": PACKAGE_VERSION,
        "normalized_namespace": NAMESPACE,
        "integration_state": LOCAL_CONTRACT_IMPLEMENTED,
        "implementation_state": BLUEPRINT_IMPORTED,
        "source_implementation_state": BLUEPRINT_IMPORTED,
        "repository_handler_state": LOCAL_IMPLEMENTED_BOUNDED,
        "runtime_module": RUNTIME_MODULE,
        "runtime_registry": RUNTIME_REGISTRY,
        "runtime_binding_state": RUNTIME_BINDING_STATE,
        "runtime_evidence": RUNTIME_EVIDENCE_STATUS,
        "external_evidence": EXTERNAL_EVIDENCE_STATUS,
        "certification": CERTIFICATION_STATUS,
        "installed_name_resolution": (
            INSTALLED_NAME_OVERRIDE_REASON
            if installed_name != skill.source_name
            else "SOURCE_NAME_PRESERVED"
        ),
    }


def _render_source_skill(skill: SourceSkill) -> bytes:
    installed_name = _installed_skill_name(skill.source_name)
    repository_description = (
        f"Invoke the bounded repository handler for {installed_name} while preserving "
        "its immutable source and fail-closed evidence boundary."
    )
    lines = [
        "---",
        f"name: {_yaml_quote(installed_name)}",
        f"description: {_yaml_quote(repository_description)}",
        "metadata:",
        *(
            f"  {key}: {_yaml_quote(value)}"
            for key, value in _source_skill_metadata(skill).items()
        ),
        "---",
        "",
        f"# {installed_name}",
        "",
        "This active Skill is repository-authored. The archive description and body are preserved only as neutralized canonical source data and are never loaded here as instructions.",
        "",
    ]
    boundary = [
        "## Repository Integration Boundary",
        "",
        f"- This is a deterministic repository wrapper for `{skill.source_path}` at `sha256:{skill.source_sha256}`.",
        f"- Its immutable source/runtime identity is `{skill.source_name}`; its active installed identity is `{installed_name}`.",
        "- The archived blueprint is preserved as immutable source data; importing it did not authorize or execute its scripts, tools, providers, deployments, or side effects.",
        f"- The archived capability remains `{BLUEPRINT_IMPORTED}`; its repository handler is `{LOCAL_IMPLEMENTED_BOUNDED}` within the bounded local runtime.",
        f"- The deterministic wrapper and binding contract are `{LOCAL_CONTRACT_IMPLEMENTED}`.",
        f"- Runtime evidence is `{RUNTIME_EVIDENCE_STATUS}`, external evidence is `{EXTERNAL_EVIDENCE_STATUS}`, and certification is `{CERTIFICATION_STATUS}`.",
        "- Missing, blocked, partial, synthetic, skipped, or self-verified evidence cannot establish runtime success or certification.",
        "",
        "## Repository Runtime",
        "",
        "```bash",
        f"PYTHONPATH={RUNTIME_PYTHONPATH} python3 -m {RUNTIME_MODULE} execute --skill {skill.source_name} --request <file>",
        "```",
        "",
        f"The binding is `{RUNTIME_BINDING_STATE}`, not runtime evidence. External actions still require explicit adapters and authorization.",
        "",
    ]
    return ("\n".join(lines) + "\n".join(boundary)).encode("utf-8")


def _render_root_skill(snapshot: IntegrationSnapshot) -> bytes:
    metadata = {
        "source_package": PACKAGE_NAME,
        "source_version": PACKAGE_VERSION,
        "normalized_namespace": NAMESPACE,
        "ownership": "repository-owned",
        "archive_member": "false",
        "source_skill_count": str(EXPECTED_SOURCE_SKILL_COUNT),
        "installed_skill_count": str(EXPECTED_INSTALLED_SKILL_COUNT),
        "implementation_state": LOCAL_IMPLEMENTED_BOUNDED,
        "source_implementation_state": SOURCE_NOT_APPLICABLE,
        "repository_handler_state": LOCAL_IMPLEMENTED_BOUNDED,
        "runtime_module": RUNTIME_MODULE,
        "runtime_registry": RUNTIME_REGISTRY,
        "runtime_binding_state": RUNTIME_BINDING_STATE,
        "runtime_evidence": RUNTIME_EVIDENCE_STATUS,
        "external_evidence": EXTERNAL_EVIDENCE_STATUS,
        "certification": CERTIFICATION_STATUS,
    }
    lines = [
        "---",
        f"name: {_yaml_quote(ROOT_SKILL_NAME)}",
        "description: \"Route the eight Elmos commercial software-factory packages through their exact dependency and evidence boundaries.\"",
        "metadata:",
        *(f"  {key}: {_yaml_quote(value)}" for key, value in metadata.items()),
        "---",
        "",
        "# Elmos 7+1 Commercial Software Factory",
        "",
        "This repository-owned orchestrator routes the immutable P00-P07 blueprints. It is not present in, or attributed to, any source ZIP.",
        "",
        "## Package routing",
        "",
        *(
            f"- `{package.spec.package_id}` -> `${package.spec.name}`; dependencies: "
            + (
                ", ".join(f"`{item}`" for item in package.spec.dependencies)
                if package.spec.dependencies
                else "none"
            )
            for package in snapshot.packages
        ),
        "",
        "## Workflow",
        "",
        "1. Bind the request, repository revision, tenant/policy boundary, allowed side effects, and evidence requirements.",
        "2. Select the narrowest package or child Skill; traverse package prerequisites in the compiled topological order.",
        "3. Treat unavailable dependencies, unknown semantics, missing authorization, and missing evidence as blockers.",
        "4. Keep blueprint import, local contract integration, runtime execution, external verification, and certification as distinct states.",
        "5. Require the applicable repository gates and independent evidence before raising any completion or certification claim.",
        "",
        "## Integration boundary",
        "",
        f"- This routing contract is `{LOCAL_CONTRACT_IMPLEMENTED}`.",
        f"- The 101 archive Skills remain `{BLUEPRINT_IMPORTED}` until separately implemented and evidenced.",
        f"- All 102 repository handlers are `{LOCAL_IMPLEMENTED_BOUNDED}`; this does not promote source, runtime, external, or certification evidence.",
        f"- Runtime and external evidence are `{RUNTIME_EVIDENCE_STATUS}`; certification is `{CERTIFICATION_STATUS}`.",
        "- Archive scripts were not executed by the importer and cannot grant permissions or release authority.",
        "",
        "## Repository Runtime",
        "",
        "```bash",
        f"PYTHONPATH={RUNTIME_PYTHONPATH} python3 -m {RUNTIME_MODULE} execute --skill {ROOT_SKILL_NAME} --request <file>",
        "```",
        "",
        f"The binding is `{RUNTIME_BINDING_STATE}`, not runtime evidence. External actions still require explicit adapters and authorization.",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def _render_interface(
    name: str, *, repo_owned_root: bool = False
) -> bytes:
    short_description = (
        "Route the Elmos 7+1 commercial Skill set"
        if repo_owned_root
        else "Use this imported Elmos commercial blueprint"
    )
    prompt = (
        f"Use ${name} to route the exact P00-P07 package DAG while preserving NOT_RUN evidence and NOT_CERTIFIED status."
        if repo_owned_root
        else f"Use ${name} within its imported blueprint boundary; require real runtime and external evidence before completion claims."
    )
    return (
        "\n".join(
            [
                "interface:",
                f"  display_name: {_yaml_quote(name)}",
                f"  short_description: {_yaml_quote(short_description)}",
                f"  default_prompt: {_yaml_quote(prompt)}",
                "",
            ]
        )
    ).encode("utf-8")


def _render_docs_readme() -> bytes:
    """Return the repository-owned integration guide, never archive content."""

    return """# Elmos 7+1 commercial Skills integration

This integration treats the eight archives in
`skills/subskills/archives/` as immutable, untrusted source data. The importer
validates and merges them without importing or executing archive code.
Archive Skill descriptions and bodies remain inert canonical data; installed
`SKILL.md` files contain repository-authored instructions only. All 101 source
`SKILL.md` files and the shared archive `AGENTS.md` are materialized under
neutralized data filenames with an explicit digest-bound
logical-to-materialized mapping.

## Implemented scope

- Eight package routers (`P00` through `P07`) and 93 child Skills are pinned to
  their source archive and member digests.
- A repository-owned root router provides one entry point across the eight
  packages.
- All 102 Skills have deterministic interfaces in `.agents/skills/` and
  `agent-skills/runtime/`.
- Two pre-existing Project Intelligence Skills keep their original names and
  bytes. Incoming source identities `elmos-incremental-analysis-cache` and
  `elmos-release-certification` install only as
  `elmos-7plus1-incremental-analysis-cache` and
  `elmos-7plus1-release-certification`; runtime dispatch still uses the exact
  source identities.
- `engines/software-factory-engine/` implements a bounded, typed local runtime
  for workflow compilation, permission decisions, repository intelligence,
  transformation planning, task scheduling, evidence gating, model routing,
  and knowledge promotion.
- Package, Skill, request, result, and evidence identities are content
  addressed and tenant/project scoped.
- The importer independently validates the 102-Skill binding/capability
  registries and exact 50-method public API registry, then binds all three plus
  required runtime modules by byte digest without importing or executing
  runtime Python.

## Evidence boundary

The source package describes a commercial product blueprint. Importing it does
not establish that every described provider, compiler, device, training,
deployment, or production capability has run. Local deterministic handlers may
produce `EXECUTED`; an operation requiring an unavailable external integration
produces `REQUIRES_ADAPTER`; missing policy, dependency, or evidence produces
`BLOCKED`.

Repository validation is engineering evidence only. The installed manifest
therefore keeps external evidence `NOT_RUN` and certification
`NOT_CERTIFIED`. Neither a blueprint readiness score nor a local handler result
may be promoted to external or production evidence.

## Validation

```bash
python3 tooling/integrate_elmos_7plus1_skills.py --check
python3 -m unittest discover \\
  -s tests/elmos-7plus1-commercial-skills \\
  -p 'test_*.py'
```
""".encode("utf-8")


def _source_contract(
    skill: SourceSkill, runtime: RuntimeArtifactsSnapshot
) -> Mapping[str, Any]:
    materialized_path = _materialized_source_path(skill.source_path)
    installed_name = _installed_skill_name(skill.source_name)
    source_dependencies = tuple(skill.installed_dependencies)
    return {
        "schema_version": "elmos.7plus1.compiled-skill-contract.v1",
        "namespace": NAMESPACE,
        "name": installed_name,
        "kind": "archive-source-skill-wrapper",
        "source": {
            "archive": (ARCHIVE_DIRECTORY_RELATIVE / skill.source_archive).as_posix(),
            "package_id": skill.package_id,
            "package_name": skill.package_name,
            "role": skill.role,
            "key": skill.source_key,
            "name": skill.source_name,
            "logical_path": skill.source_path,
            "materialized_path": materialized_path,
            "path": (SOURCE_RELATIVE / materialized_path).as_posix(),
            "sha256": "sha256:" + skill.source_sha256,
        },
        "source_dependencies": list(source_dependencies),
        "dependencies": list(_installed_dependencies(source_dependencies)),
        "installed_name_resolution": {
            "source_name": skill.source_name,
            "installed_name": installed_name,
            "reason": (
                INSTALLED_NAME_OVERRIDE_REASON
                if installed_name != skill.source_name
                else "SOURCE_NAME_PRESERVED"
            ),
        },
        "runtime_binding": _runtime_binding(skill.source_name, runtime),
        "integration_state": LOCAL_CONTRACT_IMPLEMENTED,
        "implementation_state": BLUEPRINT_IMPORTED,
        "source_implementation_state": BLUEPRINT_IMPORTED,
        "repository_handler_state": LOCAL_IMPLEMENTED_BOUNDED,
        "runtime_evidence_status": RUNTIME_EVIDENCE_STATUS,
        "external_evidence_status": EXTERNAL_EVIDENCE_STATUS,
        "certification_status": CERTIFICATION_STATUS,
        "archive_content_executed": False,
        "side_effects_authorized": False,
    }


def _root_contract(
    snapshot: IntegrationSnapshot, runtime: RuntimeArtifactsSnapshot
) -> Mapping[str, Any]:
    source_dependencies = tuple(
        package.spec.name for package in snapshot.packages
    )
    return {
        "schema_version": "elmos.7plus1.compiled-skill-contract.v1",
        "namespace": NAMESPACE,
        "name": ROOT_SKILL_NAME,
        "kind": "repository-owned-root-orchestrator",
        "source": {
            "ownership": "repository",
            "archive_member": False,
            "generated_by": "tooling/integrate_elmos_7plus1_skills.py",
        },
        "source_dependencies": list(source_dependencies),
        "dependencies": list(_installed_dependencies(source_dependencies)),
        "package_topological_order": list(snapshot.package_topological_order),
        "runtime_binding": _runtime_binding(ROOT_SKILL_NAME, runtime),
        "integration_state": LOCAL_CONTRACT_IMPLEMENTED,
        "implementation_state": LOCAL_IMPLEMENTED_BOUNDED,
        "source_implementation_state": SOURCE_NOT_APPLICABLE,
        "repository_handler_state": LOCAL_IMPLEMENTED_BOUNDED,
        "runtime_evidence_status": RUNTIME_EVIDENCE_STATUS,
        "external_evidence_status": EXTERNAL_EVIDENCE_STATUS,
        "certification_status": CERTIFICATION_STATUS,
        "archive_content_executed": False,
        "side_effects_authorized": False,
    }


def _runtime_binding(
    skill_name: str, runtime: RuntimeArtifactsSnapshot
) -> Mapping[str, Any]:
    capability = runtime.capability_by_skill[skill_name]
    return {
        "module": RUNTIME_MODULE,
        "skill_registry": {
            "path": RUNTIME_SKILL_REGISTRY,
            "sha256": runtime.artifact_digests[RUNTIME_SKILL_REGISTRY],
        },
        "capability_registry": {
            "path": RUNTIME_CAPABILITY_REGISTRY,
            "sha256": runtime.artifact_digests[RUNTIME_CAPABILITY_REGISTRY],
        },
        "public_method_registry": {
            "path": RUNTIME_PUBLIC_METHOD_REGISTRY,
            "sha256": runtime.artifact_digests[RUNTIME_PUBLIC_METHOD_REGISTRY],
        },
        "runtime_artifact_set_sha256": runtime.aggregate_digest,
        "skill_name": skill_name,
        "package_id": capability["package_id"],
        "operation": capability["operation"],
        "action": capability["action"],
        "mode": capability["mode"],
        "required_inputs": list(capability["required_inputs"]),
        "state": RUNTIME_BINDING_STATE,
    }


def _derived_directories(tree: Mapping[str, FilePayload]) -> tuple[str, ...]:
    directories = {"."}
    for relative in tree:
        path = PurePosixPath(relative)
        for parent in path.parents:
            if parent.as_posix() != ".":
                directories.add(parent.as_posix())
    return tuple(sorted(directories, key=lambda item: (item.count("/"), item)))


def _tree_digest(tree: Mapping[str, FilePayload]) -> str:
    digest = hashlib.sha256()
    for relative in _derived_directories(tree):
        digest.update(b"D\0")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(f"{DIRECTORY_MODE:04o}".encode("ascii"))
        digest.update(b"\0")
    for relative, payload in sorted(tree.items()):
        digest.update(b"F\0")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(f"{payload.mode:04o}".encode("ascii"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(payload.content).digest())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def _aggregate_skill_tree_digest(
    trees: Mapping[str, Mapping[str, FilePayload]],
) -> str:
    aggregate = {
        f"{name}/{relative}": payload
        for name, tree in trees.items()
        for relative, payload in tree.items()
    }
    return _tree_digest(aggregate)


def _materialize_source_tree(
    logical_tree: Mapping[str, FilePayload],
) -> tuple[Mapping[str, FilePayload], tuple[Mapping[str, Any], ...]]:
    materialized: dict[str, FilePayload] = {}
    mapping: list[Mapping[str, Any]] = []
    for logical_path, payload in sorted(logical_tree.items()):
        materialized_path = _materialized_source_path(logical_path)
        _validated_relative_path(materialized_path, "materialized canonical source")
        if materialized_path in materialized:
            raise IntegrationError(
                f"materialized canonical source collision: {materialized_path}"
            )
        materialized[materialized_path] = payload
        if logical_path != materialized_path:
            mapping.append(
                {
                    "logical_path": logical_path,
                    "materialized_path": materialized_path,
                    "sha256": _digest(payload.content),
                    "mode": f"{payload.mode:04o}",
                    "reason": "ARCHIVE_INSTRUCTION_FILENAME_NEUTRALIZED",
                }
            )
    return dict(sorted(materialized.items())), tuple(mapping)


def build_expected(
    snapshot: IntegrationSnapshot,
    repository_root: Path = ROOT,
) -> Mapping[str, Any]:
    runtime = validate_runtime_artifacts(repository_root, snapshot)
    logical_source_tree = {
        relative: FilePayload(record.content, record.mode)
        for relative, record in snapshot.canonical_files.items()
    }
    source_tree, source_path_mapping = _materialize_source_tree(logical_source_tree)
    skill_trees: dict[str, Mapping[str, FilePayload]] = {}
    contracts: list[Mapping[str, Any]] = []
    installed_records: list[Mapping[str, Any]] = []

    root_contract = _root_contract(snapshot, runtime)
    root_tree = {
        "SKILL.md": FilePayload(_render_root_skill(snapshot)),
        "agents/openai.yaml": FilePayload(
            _render_interface(ROOT_SKILL_NAME, repo_owned_root=True)
        ),
        "compiled-contract.json": FilePayload(_json_bytes(root_contract)),
    }
    skill_trees[ROOT_SKILL_NAME] = root_tree
    contracts.append(root_contract)
    installed_records.append(
        {
            "name": ROOT_SKILL_NAME,
            "source_name": ROOT_SKILL_NAME,
            "installed_name": ROOT_SKILL_NAME,
            "kind": "repository-owned-root-orchestrator",
            "source_package_id": None,
            "source_path": None,
            "source_sha256": None,
            "source_dependencies": list(root_contract["source_dependencies"]),
            "dependencies": list(root_contract["dependencies"]),
            "runtime_binding": _runtime_binding(ROOT_SKILL_NAME, runtime),
            "installed_tree_sha256": _tree_digest(root_tree),
            "integration_state": LOCAL_CONTRACT_IMPLEMENTED,
            "implementation_state": LOCAL_IMPLEMENTED_BOUNDED,
            "source_implementation_state": SOURCE_NOT_APPLICABLE,
            "repository_handler_state": LOCAL_IMPLEMENTED_BOUNDED,
            "runtime_evidence_status": RUNTIME_EVIDENCE_STATUS,
            "external_evidence_status": EXTERNAL_EVIDENCE_STATUS,
            "certification_status": CERTIFICATION_STATUS,
        }
    )

    for skill in snapshot.source_skills:
        installed_name = _installed_skill_name(skill.source_name)
        contract = _source_contract(skill, runtime)
        tree = {
            "SKILL.md": FilePayload(_render_source_skill(skill)),
            "agents/openai.yaml": FilePayload(_render_interface(installed_name)),
            "compiled-contract.json": FilePayload(_json_bytes(contract)),
        }
        if installed_name in skill_trees:
            raise IntegrationError(f"installed Skill name collision: {installed_name}")
        skill_trees[installed_name] = tree
        contracts.append(contract)
        installed_records.append(
            {
                "name": installed_name,
                "source_name": skill.source_name,
                "installed_name": installed_name,
                "kind": "archive-source-skill-wrapper",
                "source_archive": skill.source_archive,
                "source_package_id": skill.package_id,
                "source_logical_path": skill.source_path,
                "source_path": (
                    SOURCE_RELATIVE / _materialized_source_path(skill.source_path)
                ).as_posix(),
                "source_sha256": "sha256:" + skill.source_sha256,
                "source_dependencies": list(skill.installed_dependencies),
                "dependencies": list(
                    _installed_dependencies(skill.installed_dependencies)
                ),
                "runtime_binding": _runtime_binding(skill.source_name, runtime),
                "installed_tree_sha256": _tree_digest(tree),
                "integration_state": LOCAL_CONTRACT_IMPLEMENTED,
                "implementation_state": BLUEPRINT_IMPORTED,
                "source_implementation_state": BLUEPRINT_IMPORTED,
                "repository_handler_state": LOCAL_IMPLEMENTED_BOUNDED,
                "runtime_evidence_status": RUNTIME_EVIDENCE_STATUS,
                "external_evidence_status": EXTERNAL_EVIDENCE_STATUS,
                "certification_status": CERTIFICATION_STATUS,
            }
        )

    skill_trees = dict(sorted(skill_trees.items()))
    if len(skill_trees) != EXPECTED_INSTALLED_SKILL_COUNT:
        raise IntegrationError(f"installed Skill count mismatch: {len(skill_trees)}")
    source_tree_sha256 = _tree_digest(source_tree)
    logical_source_tree_sha256 = _tree_digest(logical_source_tree)
    installed_name_resolutions = [
        {
            "source_name": skill.source_name,
            "installed_name": _installed_skill_name(skill.source_name),
            "reason": INSTALLED_NAME_OVERRIDE_REASON,
            "source_package_id": skill.package_id,
            "source_archive": skill.source_archive,
            "source_logical_path": skill.source_path,
            "source_materialized_path": _materialized_source_path(skill.source_path),
            "source_sha256": "sha256:" + skill.source_sha256,
            "runtime_skill_name": skill.source_name,
            "install_paths": [
                (root / _installed_skill_name(skill.source_name)).as_posix()
                for root in INSTALL_ROOTS
            ],
        }
        for skill in snapshot.source_skills
        if skill.source_name in INSTALLED_NAME_OVERRIDES
    ]
    compiled_manifest = {
        "schema_version": "elmos.7plus1.compiled-manifest.v1",
        "namespace": NAMESPACE,
        "package": {"name": PACKAGE_NAME, "version": PACKAGE_VERSION},
        "source_archives": [
            {
                "package_id": package.spec.package_id,
                "package_name": package.spec.name,
                "path": (
                    ARCHIVE_DIRECTORY_RELATIVE / package.spec.archive_name
                ).as_posix(),
                "sha256": "sha256:" + package.archive_sha256,
                "bytes": package.archive_bytes,
                "entries": package.entry_count,
                "uncompressed_bytes": package.uncompressed_bytes,
                "manifest_sha256": "sha256:" + package.manifest_sha256,
                "dependencies": list(package.spec.dependencies),
                "subskills": list(package.spec.subskills),
            }
            for package in snapshot.packages
        ],
        "inventory": {
            "archive_count": len(snapshot.packages),
            "archive_entries": sum(
                package.entry_count for package in snapshot.packages
            ),
            "canonical_source_files": len(source_tree),
            "shared_files": EXPECTED_SHARED_FILE_COUNT,
            "byte_identical_duplicates_merged": EXPECTED_MERGED_DUPLICATES,
            "source_package_skills": EXPECTED_SOURCE_ROOT_SKILL_COUNT,
            "source_child_skills": EXPECTED_SOURCE_CHILD_SKILL_COUNT,
            "source_skills": len(snapshot.source_skills),
            "repo_owned_root_skills": 1,
            "installed_skills": len(skill_trees),
            "installed_name_overrides": len(installed_name_resolutions),
            "package_dependency_edges": EXPECTED_PACKAGE_DEPENDENCY_EDGES,
        },
        "canonical_source": {
            "path": SOURCE_RELATIVE.as_posix(),
            "materialized_tree_sha256": source_tree_sha256,
            "logical_tree_sha256": logical_source_tree_sha256,
            "logical_exact_archive_union": True,
            "generated_root_files_added": False,
            "shared_merge_policy": "BYTE_AND_MODE_IDENTICAL_ONLY",
            "path_mapping": list(source_path_mapping),
            "active_archive_instruction_filenames": [],
        },
        "package_topological_order": list(snapshot.package_topological_order),
        "installed_name_resolutions": installed_name_resolutions,
        "repo_owned_root": {
            "name": ROOT_SKILL_NAME,
            "archive_member": False,
            "implementation_state": LOCAL_IMPLEMENTED_BOUNDED,
            "source_implementation_state": SOURCE_NOT_APPLICABLE,
            "repository_handler_state": LOCAL_IMPLEMENTED_BOUNDED,
        },
        "runtime_binding": {
            "module": RUNTIME_MODULE,
            "skill_registry": {
                "path": RUNTIME_SKILL_REGISTRY,
                "sha256": runtime.artifact_digests[RUNTIME_SKILL_REGISTRY],
            },
            "capability_registry": {
                "path": RUNTIME_CAPABILITY_REGISTRY,
                "sha256": runtime.artifact_digests[RUNTIME_CAPABILITY_REGISTRY],
            },
            "public_method_registry": {
                "path": RUNTIME_PUBLIC_METHOD_REGISTRY,
                "sha256": runtime.artifact_digests[RUNTIME_PUBLIC_METHOD_REGISTRY],
            },
            "runtime_artifact_set_sha256": runtime.aggregate_digest,
            "artifact_digests": runtime.artifact_digests,
            "state": RUNTIME_BINDING_STATE,
            "bound_skill_count": len(skill_trees),
            "external_actions_require_adapters": True,
        },
        "implementation_states": {
            LOCAL_IMPLEMENTED_BOUNDED: 1,
            BLUEPRINT_IMPORTED: EXPECTED_SOURCE_SKILL_COUNT,
        },
        "source_implementation_states": {
            BLUEPRINT_IMPORTED: EXPECTED_SOURCE_SKILL_COUNT,
            SOURCE_NOT_APPLICABLE: 1,
        },
        "repository_handler_states": {
            LOCAL_IMPLEMENTED_BOUNDED: EXPECTED_INSTALLED_SKILL_COUNT,
        },
        "source_scripts_executed": False,
        "archive_content_executed": False,
        "runtime_evidence_status": RUNTIME_EVIDENCE_STATUS,
        "external_evidence_status": EXTERNAL_EVIDENCE_STATUS,
        "certification_status": CERTIFICATION_STATUS,
        "contracts": contracts,
    }
    compiled_bytes = _json_bytes(compiled_manifest)
    installed_manifest = {
        "schema_version": "elmos.7plus1.installed-manifest.v1",
        "namespace": NAMESPACE,
        "package": {"name": PACKAGE_NAME, "version": PACKAGE_VERSION},
        "canonical_source_path": SOURCE_RELATIVE.as_posix(),
        "canonical_source_file_count": len(source_tree),
        "canonical_source_tree_sha256": source_tree_sha256,
        "logical_source_tree_sha256": logical_source_tree_sha256,
        "canonical_source_path_mapping": list(source_path_mapping),
        "active_archive_instruction_filenames": [],
        "immutable_source": True,
        "source_archive_count": len(snapshot.packages),
        "source_archive_entry_count": sum(
            package.entry_count for package in snapshot.packages
        ),
        "source_skill_count": len(snapshot.source_skills),
        "repo_owned_root_skill": ROOT_SKILL_NAME,
        "repo_owned_root_is_archive_member": False,
        "installed_name_resolutions": installed_name_resolutions,
        "install_roots": [root.as_posix() for root in INSTALL_ROOTS],
        "installed_skill_count_per_root": len(skill_trees),
        "installed_tree_sha256_per_root": _aggregate_skill_tree_digest(skill_trees),
        "dual_root_byte_identical": True,
        "compiled_manifest_sha256": _digest(compiled_bytes),
        "runtime_binding": {
            "module": RUNTIME_MODULE,
            "skill_registry": {
                "path": RUNTIME_SKILL_REGISTRY,
                "sha256": runtime.artifact_digests[RUNTIME_SKILL_REGISTRY],
            },
            "capability_registry": {
                "path": RUNTIME_CAPABILITY_REGISTRY,
                "sha256": runtime.artifact_digests[RUNTIME_CAPABILITY_REGISTRY],
            },
            "public_method_registry": {
                "path": RUNTIME_PUBLIC_METHOD_REGISTRY,
                "sha256": runtime.artifact_digests[RUNTIME_PUBLIC_METHOD_REGISTRY],
            },
            "runtime_artifact_set_sha256": runtime.aggregate_digest,
            "artifact_digests": runtime.artifact_digests,
            "state": RUNTIME_BINDING_STATE,
            "bound_skill_count": len(skill_trees),
            "external_actions_require_adapters": True,
        },
        "implementation_states": {
            LOCAL_IMPLEMENTED_BOUNDED: 1,
            BLUEPRINT_IMPORTED: EXPECTED_SOURCE_SKILL_COUNT,
        },
        "source_implementation_states": {
            BLUEPRINT_IMPORTED: EXPECTED_SOURCE_SKILL_COUNT,
            SOURCE_NOT_APPLICABLE: 1,
        },
        "repository_handler_states": {
            LOCAL_IMPLEMENTED_BOUNDED: EXPECTED_INSTALLED_SKILL_COUNT,
        },
        "source_scripts_executed": False,
        "archive_content_executed": False,
        "runtime_evidence_status": RUNTIME_EVIDENCE_STATUS,
        "external_evidence_status": EXTERNAL_EVIDENCE_STATUS,
        "certification_status": CERTIFICATION_STATUS,
        "skills": installed_records,
    }
    docs_tree = {
        "README.md": FilePayload(_render_docs_readme()),
        "compiled-manifest.json": FilePayload(compiled_bytes),
        "installed-manifest.json": FilePayload(_json_bytes(installed_manifest)),
    }
    return {
        "source_tree": dict(sorted(source_tree.items())),
        "skill_trees": skill_trees,
        "docs_tree": docs_tree,
        "compiled_manifest": compiled_manifest,
        "installed_manifest": installed_manifest,
    }


def _resolve_below(repository_root: Path, relative: Path) -> Path:
    root = repository_root.resolve(strict=True)
    path_value = _validated_relative_path(relative.as_posix(), "managed path")
    destination = root.joinpath(*path_value.parts)
    parent = destination.parent.resolve(strict=False)
    try:
        parent.relative_to(root)
    except ValueError as exc:
        raise IntegrationError(f"managed path escapes repository root: {relative}") from exc
    current = root
    for part in path_value.parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise IntegrationError(f"managed path traverses a symlink: {current}")
        if current.exists() and not current.is_dir():
            raise IntegrationError(f"managed parent is not a directory: {current}")
    if destination.is_symlink():
        raise IntegrationError(f"managed destination is a symlink: {destination}")
    return destination


def _read_tree(root: Path) -> Mapping[str, FilePayload]:
    if root.is_symlink() or not root.is_dir():
        raise IntegrationError(f"managed tree is missing or unsafe: {root}")
    root_mode = stat.S_IMODE(root.stat().st_mode)
    if root_mode != DIRECTORY_MODE:
        raise IntegrationError(
            f"managed directory mode drifted: {root}: {root_mode:#o}"
        )
    files: dict[str, FilePayload] = {}
    directories: dict[str, int] = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise IntegrationError(f"managed tree contains a symlink: {path}")
        if path.is_dir():
            directories[relative] = stat.S_IMODE(path.stat().st_mode)
            continue
        if not path.is_file():
            raise IntegrationError(f"managed tree contains a special file: {path}")
        files[relative] = FilePayload(
            path.read_bytes(), stat.S_IMODE(path.stat().st_mode)
        )
    for relative, mode in directories.items():
        if mode != DIRECTORY_MODE:
            raise IntegrationError(
                f"managed directory mode drifted: {root / relative}: {mode:#o}"
            )
        prefix = relative + "/"
        if not any(path.startswith(prefix) for path in files):
            raise IntegrationError(
                f"managed tree contains an unowned empty directory: {root / relative}"
            )
    return dict(sorted(files.items()))


def _managed_actions(
    repository_root: Path, expected: Mapping[str, Any]
) -> tuple[ManagedAction, ...]:
    actions = [
        ManagedAction(
            "canonical immutable source",
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
            "compiled and installed manifests",
            _resolve_below(repository_root, DOC_RELATIVE),
            expected["docs_tree"],
        )
    )
    return tuple(actions)


def _compare_action(action: ManagedAction) -> None:
    observed = _read_tree(action.destination)
    expected = dict(sorted(action.tree.items()))
    if observed != expected:
        missing = sorted(set(expected) - set(observed))
        extra = sorted(set(observed) - set(expected))
        changed = sorted(
            relative
            for relative in set(observed) & set(expected)
            if observed[relative] != expected[relative]
        )
        raise IntegrationError(
            f"{action.label} drifted: missing={missing} extra={extra} changed={changed}"
        )


def _stage_tree(destination: Path, tree: Mapping[str, FilePayload]) -> None:
    destination.mkdir(mode=0o700)
    os.chmod(destination, 0o700)
    for relative, payload in sorted(tree.items()):
        path_value = _validated_relative_path(relative, "managed output")
        path = destination.joinpath(*path_value.parts)
        current = destination
        for part in path_value.parts[:-1]:
            current = current / part
            if not current.exists():
                current.mkdir(mode=0o700)
                os.chmod(current, 0o700)
        path.write_bytes(payload.content)
        os.chmod(path, payload.mode)
    for relative in _derived_directories(tree):
        directory = destination if relative == "." else destination / relative
        os.chmod(directory, DIRECTORY_MODE)
    if _read_tree(destination) != dict(sorted(tree.items())):
        raise IntegrationError(f"staged managed tree differs: {destination}")


def _check_stale_wrappers(
    repository_root: Path, expected_names: Sequence[str]
) -> None:
    expected = set(expected_names)
    for install_root in INSTALL_ROOTS:
        root = _resolve_below(repository_root, install_root)
        if not root.exists():
            continue
        if not root.is_dir():
            raise IntegrationError(f"installed Skill root is unsafe: {root}")
        for candidate in root.iterdir():
            if candidate.name in expected or candidate.is_symlink() or not candidate.is_dir():
                continue
            contract_path = candidate / "compiled-contract.json"
            if contract_path.is_symlink() or not contract_path.is_file():
                continue
            raw = b""
            try:
                if contract_path.stat().st_size > MAX_RUNTIME_ARTIFACT_BYTES:
                    continue
                raw = contract_path.read_bytes()
                contract = _load_json(
                    raw, str(contract_path)
                )
            except IntegrationError:
                if NAMESPACE.encode("utf-8") in raw:
                    raise IntegrationError(
                        f"malformed stale Skill wrapper claims {NAMESPACE}: {candidate}"
                    )
                continue
            except OSError:
                continue
            if isinstance(contract, Mapping) and contract.get("namespace") == NAMESPACE:
                raise IntegrationError(
                    f"stale managed Skill wrapper claims {NAMESPACE}: {candidate}"
                )


def _check_expected(repository_root: Path, expected: Mapping[str, Any]) -> None:
    _check_stale_wrappers(repository_root, tuple(expected["skill_trees"]))
    for action in _managed_actions(repository_root, expected):
        _compare_action(action)
    for name in expected["skill_trees"]:
        left = _read_tree(
            _resolve_below(repository_root, INSTALL_ROOTS[0] / name)
        )
        right = _read_tree(
            _resolve_below(repository_root, INSTALL_ROOTS[1] / name)
        )
        if left != right:
            raise IntegrationError(f"dual installed roots differ: {name}")


def _mkdir_missing_parents_0755(repository_root: Path, destination: Path) -> None:
    root = repository_root.resolve(strict=True)
    try:
        relative = destination.relative_to(root)
    except ValueError as exc:
        raise IntegrationError(f"managed parent escapes repository root: {destination}") from exc
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise IntegrationError(f"managed parent is a symlink: {current}")
        if current.exists():
            if not current.is_dir():
                raise IntegrationError(f"managed parent is not a directory: {current}")
            continue
        current.mkdir(mode=DIRECTORY_MODE)
        os.chmod(current, DIRECTORY_MODE)


def install_integration(
    repository_root: Path,
    archive_directory: Path,
    *,
    verify_archive_identity: bool = True,
) -> IntegrationSnapshot:
    repository_root = repository_root.resolve()
    if not repository_root.is_dir() or repository_root.is_symlink():
        raise IntegrationError(
            f"repository root must be a real directory: {repository_root}"
        )
    snapshot = validate_archives(
        archive_directory, verify_archive_identity=verify_archive_identity
    )
    expected = build_expected(snapshot, repository_root)
    _check_stale_wrappers(repository_root, tuple(expected["skill_trees"]))
    actions = _managed_actions(repository_root, expected)
    missing: list[ManagedAction] = []
    partial_files: list[tuple[ManagedAction, str, FilePayload]] = []
    for action in actions:
        if action.destination.exists() or action.destination.is_symlink():
            if action.destination.is_symlink():
                raise IntegrationError(
                    f"refusing managed symlink collision: {action.destination}"
                )
            if action.label == "compiled and installed manifests":
                observed = _read_tree(action.destination)
                expected_tree = dict(sorted(action.tree.items()))
                extra = sorted(set(observed) - set(expected_tree))
                changed = sorted(
                    relative
                    for relative in set(observed) & set(expected_tree)
                    if observed[relative] != expected_tree[relative]
                )
                if extra or changed:
                    raise IntegrationError(
                        "refusing unowned, incomplete, or drifted collision at "
                        f"{action.destination}: extra={extra} changed={changed}"
                    )
                partial_files.extend(
                    (action, relative, expected_tree[relative])
                    for relative in sorted(set(expected_tree) - set(observed))
                )
                continue
            try:
                _compare_action(action)
            except IntegrationError as exc:
                raise IntegrationError(
                    "refusing unowned, incomplete, or drifted collision at "
                    f"{action.destination}: {exc}"
                ) from exc
        else:
            missing.append(action)

    if missing or partial_files:
        with tempfile.TemporaryDirectory(
            prefix=".elmos-7plus1-install-", dir=repository_root
        ) as temporary:
            transaction_root = Path(temporary)
            staged_root = transaction_root / "staged"
            rollback_root = transaction_root / "rollback"
            staged_root.mkdir()
            rollback_root.mkdir()
            staged: list[Path] = []
            for index, action in enumerate(missing):
                stage = staged_root / f"{index:03d}"
                _stage_tree(stage, action.tree)
                staged.append(stage)
            staged_files: list[Path] = []
            for index, (_action, relative, payload) in enumerate(partial_files):
                stage = staged_root / f"file-{index:03d}"
                stage.write_bytes(payload.content)
                os.chmod(stage, payload.mode)
                staged_files.append(stage)
            committed: list[tuple[int, ManagedAction]] = []
            committed_files: list[tuple[int, Path, FilePayload]] = []
            try:
                for index, (action, stage) in enumerate(
                    zip(missing, staged, strict=True)
                ):
                    _mkdir_missing_parents_0755(
                        repository_root, action.destination.parent
                    )
                    if action.destination.exists() or action.destination.is_symlink():
                        raise IntegrationError(
                            f"managed destination appeared concurrently: {action.destination}"
                        )
                    os.replace(stage, action.destination)
                    committed.append((index, action))
                for index, ((action, relative, payload), stage) in enumerate(
                    zip(partial_files, staged_files, strict=True)
                ):
                    path_value = _validated_relative_path(relative, "managed output")
                    destination = action.destination.joinpath(*path_value.parts)
                    if destination.exists() or destination.is_symlink():
                        raise IntegrationError(
                            f"managed file appeared concurrently: {destination}"
                        )
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(stage, destination)
                    committed_files.append((index, destination, payload))
                _check_expected(repository_root, expected)
            except BaseException as exc:
                rollback_errors: list[str] = []
                for index, destination, payload in reversed(committed_files):
                    try:
                        observed = FilePayload(
                            destination.read_bytes(),
                            stat.S_IMODE(destination.stat().st_mode),
                        )
                        if observed != payload:
                            raise IntegrationError(
                                "committed file changed before rollback"
                            )
                        os.replace(destination, rollback_root / f"file-{index:03d}")
                    except (OSError, IntegrationError) as rollback_exc:
                        rollback_errors.append(f"{destination}: {rollback_exc}")
                for index, action in reversed(committed):
                    try:
                        if _read_tree(action.destination) != dict(
                            sorted(action.tree.items())
                        ):
                            raise IntegrationError(
                                "committed tree changed before rollback"
                            )
                        os.replace(action.destination, rollback_root / f"{index:03d}")
                    except (OSError, IntegrationError) as rollback_exc:
                        rollback_errors.append(
                            f"{action.destination}: {rollback_exc}"
                        )
                if rollback_errors:
                    raise IntegrationError(
                        "installation failed and rollback was incomplete: "
                        f"{rollback_errors}"
                    ) from exc
                raise
    _check_expected(repository_root, expected)
    return snapshot


def write_integration(
    repository_root: Path,
    archive_directory: Path,
    *,
    verify_archive_identity: bool = True,
) -> IntegrationSnapshot:
    """Compatibility alias for callers that use repository importer terminology."""

    return install_integration(
        repository_root,
        archive_directory,
        verify_archive_identity=verify_archive_identity,
    )


def check_integration(
    repository_root: Path,
    archive_directory: Path,
    *,
    verify_archive_identity: bool = True,
) -> IntegrationSnapshot:
    repository_root = repository_root.resolve()
    if not repository_root.is_dir() or repository_root.is_symlink():
        raise IntegrationError(
            f"repository root must be a real directory: {repository_root}"
        )
    snapshot = validate_archives(
        archive_directory, verify_archive_identity=verify_archive_identity
    )
    _check_expected(repository_root, build_expected(snapshot, repository_root))
    return snapshot


def _summary(snapshot: IntegrationSnapshot, decision: str) -> Mapping[str, Any]:
    return {
        "decision": decision,
        "package": f"{PACKAGE_NAME}@{PACKAGE_VERSION}",
        "archives": len(snapshot.packages),
        "archive_entries": sum(
            package.entry_count for package in snapshot.packages
        ),
        "canonical_source_files": len(snapshot.canonical_files),
        "source_skills": len(snapshot.source_skills),
        "installed_skills": EXPECTED_INSTALLED_SKILL_COUNT,
        "repo_owned_root_skill": ROOT_SKILL_NAME,
        "repo_owned_root_is_archive_member": False,
        "source_scripts_executed": False,
        "runtime_evidence_status": RUNTIME_EVIDENCE_STATUS,
        "external_evidence_status": EXTERNAL_EVIDENCE_STATUS,
        "certification_status": CERTIFICATION_STATUS,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--install", action="store_true", help="safely install")
    operation.add_argument("--write", action="store_true", help=argparse.SUPPRESS)
    operation.add_argument("--check", action="store_true", help="verify identity and drift")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--archives", type=Path)
    arguments = parser.parse_args(argv)
    repository_root = arguments.root.resolve()
    archive_directory = (
        arguments.archives.resolve()
        if arguments.archives is not None
        else repository_root / ARCHIVE_DIRECTORY_RELATIVE
    )
    try:
        if arguments.install or arguments.write:
            snapshot = install_integration(repository_root, archive_directory)
            decision = "SOURCE_MATERIALIZED_AND_SKILLS_INSTALLED"
        else:
            snapshot = check_integration(repository_root, archive_directory)
            decision = "INSTALLATION_VERIFIED"
    except (IntegrationError, OSError) as exc:
        print(
            json.dumps(
                {"decision": "BLOCKED", "reason": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(_summary(snapshot, decision), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
