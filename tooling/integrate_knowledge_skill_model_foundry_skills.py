#!/usr/bin/env python3
"""Audit and compile the pinned Knowledge-Skill-Model Foundry package.

The ZIP is untrusted declarative input. This module never extracts, imports,
compiles, or executes bundled Python, SQL, Rego, pipelines, prompts, or Skill
instructions. ``--check`` is read-only. ``--write`` emits only deterministic
repository-owned catalog assets.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from types import MappingProxyType
from typing import Any, Mapping, Sequence
import unicodedata
import zipfile

try:
    import yaml
    from jsonschema import Draft202012Validator
except ModuleNotFoundError as exc:  # pragma: no cover - Makefile supplies pins
    raise SystemExit(
        "PyYAML and jsonschema are required; use "
        "`make knowledge-skill-model-foundry-skills`"
    ) from exc


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIRECTORY = "elmos-knowledge-skill-model-foundry-v3.0.0"
PACKAGE_ID = PACKAGE_DIRECTORY
PACKAGE_NAME = "elmos-knowledge-skill-model-foundry"
PACKAGE_VERSION = "3.0.0"
PACKAGE_PREFIX = f"{PACKAGE_DIRECTORY}/"

PRIMARY_ARCHIVE_RELATIVE = Path("skills/subskills") / f"{PACKAGE_DIRECTORY}.zip"
FALLBACK_ARCHIVE_RELATIVE = Path("skills/subskills/sub") / f"{PACKAGE_DIRECTORY}.zip"
ENGINE_RELATIVE = Path("engines/knowledge-skill-model-foundry-engine")
CATALOG_RELATIVE = ENGINE_RELATIVE / "catalog"

EXPECTED_ARCHIVE_SHA256 = (
    "e29673a598756deff422e8dd7f36b2826e9c1aaff6df22db2c0699b0857ee0e4"
)
EXPECTED_ARCHIVE_BYTES = 16_668_810
EXPECTED_ENTRY_COUNT = 16_007
EXPECTED_FILE_COUNT = 9_317
EXPECTED_DIRECTORY_COUNT = 6_690
EXPECTED_CONTROLLED_FILE_COUNT = 9_316
EXPECTED_TOTAL_UNCOMPRESSED_BYTES = 23_561_976
EXPECTED_TOTAL_COMPRESSED_MEMBER_BYTES = 10_276_814

EXPECTED_ATOMIC_SKILLS = 1_310
EXPECTED_META_SKILLS = 41
EXPECTED_PACKS = 41
EXPECTED_EVALUATION_CASES = 31_440
EXPECTED_DEPENDENCY_EDGES = 9_090
EXPECTED_POSTGRES_TABLE_COUNT = 38

MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
MAX_ENTRY_COUNT = 20_000
MAX_ENTRY_UNCOMPRESSED_BYTES = 8 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 32 * 1024 * 1024
MAX_MEMBER_COMPRESSION_RATIO = 20.0
MAX_TOTAL_COMPRESSION_RATIO = 4.0
MAX_PATH_UTF8_BYTES = 512
READ_CHUNK_BYTES = 1024 * 1024

EXPECTED_PRIORITY_COUNTS = MappingProxyType({"P0": 916, "P1": 368, "P2": 26})
EXPECTED_RISK_COUNTS = MappingProxyType(
    {"critical": 112, "high": 871, "medium": 307, "research": 20}
)
EXPECTED_PACK_COUNTS = MappingProxyType(
    {
        "00-foundation-contracts": 14,
        "01-knowledge-ingestion-governance": 20,
        "02-repository-semantic-intelligence": 24,
        "03-retrieval-context-engineering": 20,
        "04-memory-experience-flywheel": 20,
        "05-skill-foundry-runtime": 29,
        "06-dataset-foundry": 30,
        "07-private-model-foundry": 34,
        "08-agentic-training-rl": 28,
        "09-evaluation-proof-certification": 36,
        "10-serving-routing-inference": 28,
        "11-security-privacy-compliance": 36,
        "12-observability-lineage-finops": 28,
        "13-commercial-multitenant-platform": 24,
        "14-human-governance-operations": 20,
        "15-domain-engineering-packs": 37,
        "16-self-evolution-release-engineering": 30,
        "17-repository-execution-os": 34,
        "18-java-spring-enterprise-modernization": 48,
        "19-cross-language-semantic-conversion": 52,
        "20-sql-database-modernization": 50,
        "21-project-generation-product-engineering": 44,
        "22-frontend-mobile-miniapp-modernization": 44,
        "23-repository-refactoring-technical-debt": 32,
        "24-api-event-integration-modernization": 32,
        "25-data-engineering-lakehouse-analytics": 40,
        "26-cloud-native-devops-platform-engineering": 38,
        "27-test-quality-assurance-factory": 44,
        "28-security-compliance-supply-chain": 40,
        "29-performance-reliability-cost-engineering": 32,
        "30-architecture-documentation-ide": 32,
        "31-ai-agent-rag-ml-engineering": 46,
        "32-legacy-mainframe-enterprise-modernization": 40,
        "33-industrial-iot-edge-robotics": 32,
        "34-language-runtime-adapters": 36,
        "35-database-engine-adapters": 24,
        "36-framework-runtime-adapters": 36,
        "37-cloud-platform-adapters": 16,
        "38-golden-route-customer-delivery": 24,
        "39-product-commercialization-marketplace": 16,
        "40-regulated-industry-assurance": 20,
    }
)

ATOMIC_SKILL_FILES = frozenset(
    {
        "SKILL.md",
        "skill.yaml",
        "evals/contract.yaml",
        "evals/cases.yaml",
        "policies/execution.yaml",
        "references/implementation-notes.md",
        "tests/conformance.yaml",
    }
)
META_SKILL_FILES = frozenset({"SKILL.md", "evals/activation.json"})
EXPECTED_SCHEMA_PATHS = frozenset(
    {
        "schemas/adapter-profile.schema.json",
        "schemas/business-line.schema.json",
        "schemas/customer-acceptance.schema.json",
        "schemas/dataset-item.schema.json",
        "schemas/evidence-bundle.schema.json",
        "schemas/experience-episode.schema.json",
        "schemas/golden-route.schema.json",
        "schemas/model-release.schema.json",
        "schemas/repository-execution.schema.json",
        "schemas/skill-contract-v3.schema.json",
        "schemas/skill-contract.schema.json",
        "schemas/transformation-contract.schema.json",
        "schemas/verification-obligation.schema.json",
    }
)
EXPECTED_POLICY_PATHS = frozenset(
    {
        "policies/adapter-compatibility.rego",
        "policies/business-line-admission.rego",
        "policies/cross-tenant-training-deny.rego",
        "policies/evidence-invalidation.rego",
        "policies/golden-route-promotion.rego",
        "policies/high-risk-transformation.rego",
        "policies/model-promotion.rego",
        "policies/skill-execution.rego",
        "policies/training-eligibility.rego",
    }
)
EXPECTED_PIPELINE_PATHS = frozenset(
    {
        "pipelines/ai-agent-rag-golden-route.yaml",
        "pipelines/capability-gap-to-skill.yaml",
        "pipelines/cross-language-golden-route.yaml",
        "pipelines/customer-delivery-lifecycle.yaml",
        "pipelines/customer-private-adapter.yaml",
        "pipelines/data-platform-golden-route.yaml",
        "pipelines/database-zero-downtime-golden-route.yaml",
        "pipelines/experience-to-dataset.yaml",
        "pipelines/frontend-miniapp-golden-route.yaml",
        "pipelines/knowledge-to-skill.yaml",
        "pipelines/project-generation-golden-route.yaml",
        "pipelines/repository-task-intake-to-certify.yaml",
        "pipelines/spring-modernization-golden-route.yaml",
        "pipelines/train-certify-deploy.yaml",
    }
)
EXPECTED_EXECUTABLE_PATHS = frozenset(
    {
        "tools/coverage_audit.py",
        "tools/deep_quality_audit.py",
        "tools/new_skill.py",
        "tools/package_diff.py",
        "tools/validate_package.py",
    }
)

SKILL_ID_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
CHECKSUM_LINE_PATTERN = re.compile(r"([0-9a-f]{64})  ([^\r\n]+)\Z")
LOCAL_CAPABILITY_ALLOWLIST: frozenset[str] = frozenset(
    {
        "artifact-identity-and-hashing",
        "typed-skill-contract",
        "package-conformance-validator",
        "capability-dependency-graph",
        "hierarchical-skill-registry",
        "progressive-skill-disclosure",
        "skill-activation-router",
        "skill-dependency-resolver",
        "environment-owned-authority",
        "least-privilege-tool-authorization",
        "workspace-attachment-ownership-fencing",
        "tamper-evident-audit-log",
        "artifact-normalization",
        "provenance-and-lineage-capture",
        "sensitive-data-and-secret-detection",
        "experience-episode-capture",
        "tenant-memory-isolation-and-replay",
        "dataset-contract-and-schema",
        "dataset-quarantine-management",
        "task-canonicalization-and-normalization",
        "evidence-aggregation-and-completeness",
        "uncertainty-and-abstention-evaluation",
        "health-warmup-and-readiness",
        "complexity-risk-cost-latency-routing",
        "model-version-pinning-determinism",
        "tool-call-schema-and-policy-check",
    }
)

UNBOUND = "UNBOUND"
BASIC_PACKS = frozenset(tuple(EXPECTED_PACK_COUNTS)[:17])
ENHANCED_PACKS = frozenset(tuple(EXPECTED_PACK_COUNTS)[17:])
BOOTSTRAP_DEPENDENCY_SKILLS = frozenset(
    {
        "typed-skill-contract",
        "evidence-contract",
        "policy-contract",
        "skill-transaction-and-rollback",
        "tenant-policy-aware-retrieval",
    }
)
SKILL_ROOT_KEYS = frozenset({"apiVersion", "kind", "metadata", "spec"})
SKILL_METADATA_KEYS = frozenset({"name", "version", "pack", "priority", "owner"})
SKILL_SPEC_KEYS = frozenset(
    {
        "description", "kernel", "riskClass", "exposure", "preconditions", "inputs",
        "outputs", "workflow", "tools", "evidence", "rollback", "learning", "telemetry",
        "businessLines", "capabilityTags", "triggers", "negativeTriggers", "dependencies",
        "invariants", "failureModes", "execution", "compatibility", "maturity", "support",
    }
)
BASIC_PRECONDITIONS = (
    "tenant.authorized == true",
    "task.contract != null",
    "release.versionPinned == true",
)
ENHANCED_PRECONDITIONS = BASIC_PRECONDITIONS + (
    "baseline.snapshotAvailable == true",
    "evidence.serviceAvailable == true",
)
BASIC_POLICY = {
    "default": "deny",
    "allowWhen": ["tenant-authorized", "version-compatible", "required-evidence-service-available"],
    "approvalWhen": ["production-write", "data-export", "training-global", "security-policy-change"],
    "denyWhen": ["revoked-skill", "unsigned-dependency", "quarantined-data", "cross-tenant-access"],
}
ENHANCED_POLICY = {
    "default": "deny",
    "allowWhen": [
        "tenant-authorized", "version-compatible", "baseline-and-rollback-available",
        "required-evidence-service-available", "tool-authority-owned-by-environment",
    ],
    "approvalWhen": [
        "production-write", "irreversible-data-change", "data-export",
        "training-or-adapter-update", "security-policy-change",
    ],
    "denyWhen": [
        "revoked-skill", "unsigned-dependency", "quarantined-data", "cross-tenant-access",
        "missing-version-pin", "hard-gate-bypass-requested",
    ],
}
CONFORMANCE_CHECKS = (
    "schema-valid", "frontmatter-valid", "id-unique-and-length-valid",
    "owner-and-business-line-assigned", "dependencies-resolvable-and-acyclic",
    "tools-default-deny", "eight-positive-eight-negative-four-ambiguous-four-adversarial-evals",
    "evidence-gates-nonempty", "rollback-required", "learning-policy-explicit",
    "telemetry-wall-clock-and-cost-enabled", "unsupported-version-never-presented-as-supported",
    "no-placeholder-or-empty-required-artifact",
)
BASIC_FAILURE_MODES = (
    "unsupported-version-or-environment", "insufficient-semantic-coverage",
    "deterministic-verification-failure", "authorization-or-data-rights-failure",
    "rollback-target-unavailable",
)
ENHANCED_FAILURE_MODES = (
    "unsupported-source-or-target-version", "insufficient-semantic-or-contract-coverage",
    "deterministic-verification-failure", "security-privacy-or-license-policy-failure",
    "performance-or-capacity-regression", "rollback-or-recovery-evidence-missing",
)


class IntegrationError(RuntimeError):
    """Raised for a fail-closed archive or generated-asset violation."""


@dataclass(frozen=True)
class ArchiveIdentity:
    sha256: str
    byte_count: int
    entry_count: int = EXPECTED_ENTRY_COUNT
    file_count: int = EXPECTED_FILE_COUNT
    directory_count: int = EXPECTED_DIRECTORY_COUNT


PINNED_ARCHIVE_IDENTITY = ArchiveIdentity(
    sha256=EXPECTED_ARCHIVE_SHA256,
    byte_count=EXPECTED_ARCHIVE_BYTES,
)


@dataclass(frozen=True)
class ArchiveMetrics:
    entries: int
    files: int
    directories: int
    controlled_files: int
    compressed_member_bytes: int
    uncompressed_bytes: int
    maximum_member_compression_ratio: float
    executable_files: tuple[str, ...]


@dataclass(frozen=True)
class AuditResult:
    archive_path: Path
    archive_sha256: str
    archive_bytes: int
    archive_metrics: ArchiveMetrics
    compiled_catalog: Mapping[str, Any]
    package_report: Mapping[str, Any]


class _UniqueKeySafeLoader(getattr(yaml, "CSafeLoader", yaml.SafeLoader)):
    pass


def _construct_unique_mapping(
    loader: _UniqueKeySafeLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in result
        except TypeError as exc:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found unhashable mapping key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def fail(message: str) -> None:
    raise IntegrationError(message)


def _require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(READ_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def load_json(data: bytes, label: str) -> Any:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                fail(f"{label}: invalid JSON: duplicate key {key!r}")
            result[key] = value
        return result

    def reject_non_finite(value: str) -> Any:
        fail(f"{label}: invalid JSON: non-finite number {value!r}")

    try:
        return json.loads(
            data.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_non_finite,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"{label}: invalid JSON: {exc}")


def load_yaml(data: bytes, label: str) -> Any:
    try:
        value = yaml.load(data.decode("utf-8"), Loader=_UniqueKeySafeLoader)
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        fail(f"{label}: invalid YAML: {exc}")
    return value


def _mapping(value: Any, label: str) -> dict[str, Any]:
    _require(isinstance(value, dict), f"{label}: expected mapping")
    return value


def _list(value: Any, label: str) -> list[Any]:
    _require(isinstance(value, list), f"{label}: expected list")
    return value


def _string(value: Any, label: str) -> str:
    _require(isinstance(value, str) and bool(value), f"{label}: expected non-empty string")
    return value


def resolve_archive(root: Path = ROOT) -> Path:
    primary = root / PRIMARY_ARCHIVE_RELATIVE
    if primary.is_file():
        return primary
    fallback = root / FALLBACK_ARCHIVE_RELATIVE
    if fallback.is_file():
        return fallback
    fail(
        f"pinned archive missing at {PRIMARY_ARCHIVE_RELATIVE} "
        f"and {FALLBACK_ARCHIVE_RELATIVE}"
    )


def verify_archive(
    path: Path, identity: ArchiveIdentity = PINNED_ARCHIVE_IDENTITY
) -> str:
    _require(path.is_file(), f"archive missing: {path}")
    byte_count = path.stat().st_size
    _require(byte_count <= MAX_ARCHIVE_BYTES, f"archive exceeds safety cap: {byte_count}")
    _require(
        byte_count == identity.byte_count,
        f"archive byte count mismatch: expected {identity.byte_count}, got {byte_count}",
    )
    digest = digest_file(path)
    _require(
        digest == identity.sha256,
        f"archive digest mismatch: expected {identity.sha256}, got {digest}",
    )
    return digest


def _relative_member_path(name: str) -> str:
    _require("\x00" not in name, "archive member contains NUL")
    _require("\\" not in name, f"archive member uses backslash: {name!r}")
    _require(not name.startswith("/"), f"archive member is absolute: {name!r}")
    _require(not re.match(r"^[A-Za-z]:", name), f"archive member has drive prefix: {name!r}")
    _require(
        len(name.encode("utf-8")) <= MAX_PATH_UTF8_BYTES,
        f"archive member path exceeds cap: {name!r}",
    )
    _require(
        unicodedata.normalize("NFC", name) == name,
        f"archive member path is not NFC-normalized: {name!r}",
    )
    path = PurePosixPath(name)
    _require(
        all(part not in {"", ".", ".."} for part in path.parts),
        f"archive member contains unsafe component: {name!r}",
    )
    _require(
        name == PACKAGE_DIRECTORY or name.startswith(PACKAGE_PREFIX),
        f"archive member escapes required package root: {name!r}",
    )
    if name in {PACKAGE_DIRECTORY, PACKAGE_PREFIX}:
        return ""
    return name[len(PACKAGE_PREFIX) :].rstrip("/")


def inspect_archive_structure(
    infos: Sequence[zipfile.ZipInfo],
    identity: ArchiveIdentity = PINNED_ARCHIVE_IDENTITY,
) -> ArchiveMetrics:
    _require(len(infos) <= MAX_ENTRY_COUNT, f"archive has too many entries: {len(infos)}")
    exact_names: set[str] = set()
    nfc_names: dict[str, str] = {}
    casefold_names: dict[str, str] = {}
    files = 0
    directories = 0
    total_uncompressed = 0
    total_compressed = 0
    maximum_ratio = 0.0
    executables: list[str] = []

    for info in infos:
        name = info.filename
        relative = _relative_member_path(name)
        _require(name not in exact_names, f"duplicate archive member: {name!r}")
        exact_names.add(name)
        normalized = unicodedata.normalize("NFC", name.rstrip("/"))
        previous_nfc = nfc_names.setdefault(normalized, name)
        _require(
            previous_nfc == name,
            f"NFC-normalized archive collision: {previous_nfc!r} vs {name!r}",
        )
        folded = normalized.casefold()
        previous_case = casefold_names.setdefault(folded, name)
        _require(
            previous_case == name,
            f"casefold archive collision: {previous_case!r} vs {name!r}",
        )
        _require(not (info.flag_bits & 0x1), f"encrypted archive member: {name!r}")
        _require(
            info.compress_type in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED},
            f"unsupported compression method for {name!r}: {info.compress_type}",
        )
        _require(
            info.file_size <= MAX_ENTRY_UNCOMPRESSED_BYTES,
            f"archive member exceeds size cap: {name!r} ({info.file_size})",
        )
        mode = (info.external_attr >> 16) & 0xFFFF
        file_type = stat.S_IFMT(mode)
        if info.is_dir():
            directories += 1
            _require(name.endswith("/"), f"directory lacks trailing slash: {name!r}")
            _require(file_type == stat.S_IFDIR, f"directory has unsafe mode {oct(mode)}: {name!r}")
            # The pinned producer encoded setgid on every directory. We never
            # extract these entries; the exact mode is accepted as archive
            # identity metadata and is never reproduced in generated assets.
            _require(stat.S_IMODE(mode) == 0o2755, f"directory permission drift {oct(mode)}: {name!r}")
            _require(info.file_size == 0, f"directory has payload: {name!r}")
        else:
            files += 1
            _require(
                file_type == stat.S_IFREG,
                f"symlink or special archive member {oct(mode)}: {name!r}",
            )
            permission = stat.S_IMODE(mode)
            _require(permission in {0o644, 0o755}, f"unsafe file permission {oct(mode)}: {name!r}")
            if permission & 0o111:
                executables.append(relative)
        ratio = info.file_size / max(info.compress_size, 1) if info.file_size else 0.0
        _require(
            ratio <= MAX_MEMBER_COMPRESSION_RATIO,
            f"archive member compression ratio exceeds cap: {name!r} ({ratio:.2f})",
        )
        maximum_ratio = max(maximum_ratio, ratio)
        total_uncompressed += info.file_size
        total_compressed += info.compress_size

    _require(
        len(infos) == identity.entry_count,
        f"archive entry count mismatch: expected {identity.entry_count}, got {len(infos)}",
    )
    _require(files == identity.file_count, f"archive file count mismatch: expected {identity.file_count}, got {files}")
    _require(
        directories == identity.directory_count,
        f"archive directory count mismatch: expected {identity.directory_count}, got {directories}",
    )
    _require(
        total_uncompressed <= MAX_TOTAL_UNCOMPRESSED_BYTES,
        f"archive total uncompressed size exceeds cap: {total_uncompressed}",
    )
    total_ratio = total_uncompressed / max(total_compressed, 1)
    _require(
        total_ratio <= MAX_TOTAL_COMPRESSION_RATIO,
        f"archive total compression ratio exceeds cap: {total_ratio:.2f}",
    )
    if identity == PINNED_ARCHIVE_IDENTITY:
        _require(
            total_uncompressed == EXPECTED_TOTAL_UNCOMPRESSED_BYTES,
            f"archive uncompressed byte count drift: {total_uncompressed}",
        )
        _require(
            total_compressed == EXPECTED_TOTAL_COMPRESSED_MEMBER_BYTES,
            f"archive compressed member byte count drift: {total_compressed}",
        )
        _require(
            frozenset(executables) == EXPECTED_EXECUTABLE_PATHS,
            f"archive executable inventory drift: {sorted(executables)}",
        )
    return ArchiveMetrics(
        entries=len(infos),
        files=files,
        directories=directories,
        controlled_files=0,
        compressed_member_bytes=total_compressed,
        uncompressed_bytes=total_uncompressed,
        maximum_member_compression_ratio=maximum_ratio,
        executable_files=tuple(sorted(executables)),
    )


def _read_member(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    _require(not info.is_dir(), f"attempted to read directory member: {info.filename}")
    with zf.open(info, "r") as stream:
        chunks: list[bytes] = []
        total = 0
        while chunk := stream.read(READ_CHUNK_BYTES):
            total += len(chunk)
            _require(total <= MAX_ENTRY_UNCOMPRESSED_BYTES, f"member exceeded read cap: {info.filename}")
            chunks.append(chunk)
    _require(total == info.file_size, f"member size changed during read: {info.filename}")
    return b"".join(chunks)


def _relative_file_index(infos: Sequence[zipfile.ZipInfo]) -> dict[str, zipfile.ZipInfo]:
    return {
        _relative_member_path(info.filename): info
        for info in infos
        if not info.is_dir()
    }


def verify_controlled_files(
    zf: zipfile.ZipFile, files: Mapping[str, zipfile.ZipInfo]
) -> dict[str, str]:
    checksum_info = files.get("SHA256SUMS")
    _require(checksum_info is not None, "missing SHA256SUMS")
    try:
        text = _read_member(zf, checksum_info).decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(f"SHA256SUMS is not UTF-8: {exc}")
    _require(text.endswith("\n"), "SHA256SUMS must end with a newline")
    lines = text.splitlines()
    _require(
        len(lines) == EXPECTED_CONTROLLED_FILE_COUNT,
        f"SHA256SUMS line count mismatch: expected {EXPECTED_CONTROLLED_FILE_COUNT}, got {len(lines)}",
    )
    declared: dict[str, str] = {}
    for line_number, line in enumerate(lines, 1):
        match = CHECKSUM_LINE_PATTERN.fullmatch(line)
        _require(match is not None, f"malformed SHA256SUMS line {line_number}")
        expected, relative = match.groups()
        _require(relative != "SHA256SUMS", "SHA256SUMS must not self-reference")
        _require(relative not in declared, f"duplicate SHA256SUMS path: {relative}")
        _require(
            _relative_member_path(PACKAGE_PREFIX + relative) == relative,
            f"unsafe SHA256SUMS path: {relative!r}",
        )
        declared[relative] = expected
    expected_paths = set(files) - {"SHA256SUMS"}
    _require(
        set(declared) == expected_paths,
        "SHA256SUMS coverage mismatch: "
        f"missing={sorted(expected_paths - set(declared))[:10]}, "
        f"extra={sorted(set(declared) - expected_paths)[:10]}",
    )
    for relative in sorted(declared):
        actual = digest_bytes(_read_member(zf, files[relative]))
        _require(actual == declared[relative], f"SHA256SUMS mismatch for {relative}")
    return declared


def _parse_frontmatter(data: bytes, label: str) -> dict[str, Any]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(f"{label}: invalid UTF-8: {exc}")
    _require(text.startswith("---\n"), f"{label}: missing YAML frontmatter")
    end = text.find("\n---\n", 4)
    _require(end >= 0, f"{label}: unterminated YAML frontmatter")
    return _mapping(load_yaml(text[4:end].encode(), label), label)


def _validate_skill_id(value: Any, label: str) -> str:
    name = _string(value, label)
    _require(len(name) <= 64, f"{label}: Skill ID exceeds 64 characters")
    _require(SKILL_ID_PATTERN.fullmatch(name) is not None, f"{label}: invalid Skill ID")
    return name


def _string_list(value: Any, label: str, *, nonempty: bool = True) -> list[str]:
    rows = _list(value, label)
    if nonempty:
        _require(bool(rows), f"{label}: must not be empty")
    result = [_string(row, f"{label}[{index}]") for index, row in enumerate(rows)]
    _require(len(result) == len(set(result)), f"{label}: duplicate values")
    return result


def _named_contract_values(value: Any, label: str) -> list[str]:
    rows = _list(value, label)
    result = [
        _string(_mapping(row, f"{label}[{index}]").get("name"), f"{label}[{index}].name")
        for index, row in enumerate(rows)
    ]
    _require(result and len(result) == len(set(result)), f"{label}: invalid names")
    return result


def _exact_keys(value: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    actual = frozenset(value)
    _require(
        actual == expected,
        f"{label}: closed shape mismatch; missing={sorted(expected - actual)}, "
        f"extra={sorted(actual - expected)}",
    )


def _typed_contracts(
    value: Any,
    label: str,
    *,
    flag_name: str,
    compiled_flag_name: str,
) -> tuple[list[str], list[dict[str, Any]]]:
    rows = _list(value, label)
    names: list[str] = []
    compiled: list[dict[str, Any]] = []
    for index, raw_row in enumerate(rows):
        row_label = f"{label}[{index}]"
        row = _mapping(raw_row, row_label)
        _exact_keys(row, frozenset({"name", flag_name}), row_label)
        name = _string(row.get("name"), f"{row_label}.name")
        _require(row.get(flag_name) is True, f"{row_label}.{flag_name} must be true")
        names.append(name)
        compiled.append(
            {
                "name": name,
                compiled_flag_name: True,
                "schema_binding": UNBOUND,
            }
        )
    _require(names and len(names) == len(set(names)), f"{label}: invalid names")
    return names, compiled


def _closed_string_list(value: Any, label: str, expected: Sequence[str] | None = None) -> list[str]:
    result = _string_list(value, label)
    if expected is not None:
        _require(result == list(expected), f"{label}: exact values drift")
    return result


def _validate_contract_shape(
    skill_contract: Mapping[str, Any],
    *,
    name: str,
    pack: str,
    skill_path: str,
) -> dict[str, Any]:
    """Strictly validate the two source generations and normalize without invention."""

    _exact_keys(skill_contract, SKILL_ROOT_KEYS, skill_path)
    _require(skill_contract.get("apiVersion") == "elmos.ai/v1", f"{name}: apiVersion drift")
    _require(skill_contract.get("kind") == "ProofCarryingSkill", f"{name}: kind drift")
    metadata = _mapping(skill_contract.get("metadata"), f"{skill_path}.metadata")
    _exact_keys(metadata, SKILL_METADATA_KEYS, f"{skill_path}.metadata")
    spec = _mapping(skill_contract.get("spec"), f"{skill_path}.spec")
    expected_spec_keys = SKILL_SPEC_KEYS | (
        frozenset({"dependencySemantics"}) if name in BOOTSTRAP_DEPENDENCY_SKILLS else frozenset()
    )
    _exact_keys(spec, expected_spec_keys, f"{skill_path}.spec")
    enhanced = pack in ENHANCED_PACKS
    _require(enhanced or pack in BASIC_PACKS, f"{name}: unknown contract generation")

    description = _string(spec.get("description"), f"{skill_path}.description")
    kernel = _string(spec.get("kernel"), f"{skill_path}.kernel")
    _require(spec.get("exposure") == "atomic-registry-only", f"{name}: exposure drift")
    preconditions = _closed_string_list(
        spec.get("preconditions"),
        f"{skill_path}.preconditions",
        ENHANCED_PRECONDITIONS if enhanced else BASIC_PRECONDITIONS,
    )
    inputs, input_contracts = _typed_contracts(
        spec.get("inputs"),
        f"{skill_path}.inputs",
        flag_name="required",
        compiled_flag_name="required",
    )
    outputs, output_contracts = _typed_contracts(
        spec.get("outputs"),
        f"{skill_path}.outputs",
        flag_name="contentAddressed",
        compiled_flag_name="content_addressed",
    )
    workflow = _closed_string_list(spec.get("workflow"), f"{skill_path}.workflow")
    _require(len(workflow) == 7, f"{name}: workflow must contain exactly seven steps")

    tools = _mapping(spec.get("tools"), f"{skill_path}.tools")
    expected_tool_keys = frozenset(
        {"allowed", "defaultDeny", "environmentOwnedAuthority", "parameterValidationRequired"}
        if enhanced
        else {"allowed", "defaultDeny"}
    )
    _exact_keys(tools, expected_tool_keys, f"{skill_path}.tools")
    allowed_tools = _closed_string_list(tools.get("allowed"), f"{skill_path}.tools.allowed")
    _require(tools.get("defaultDeny") is True, f"{name}: tools must default deny")
    if enhanced:
        _require(
            tools.get("environmentOwnedAuthority") is True
            and tools.get("parameterValidationRequired") is True,
            f"{name}: enhanced tool authority boundary drift",
        )

    evidence = _mapping(spec.get("evidence"), f"{skill_path}.evidence")
    expected_evidence_keys = frozenset(
        {"requiredGates", "minimumLevel", "independentReplayRequired", "sourceBindingRequired"}
        if enhanced
        else {"requiredGates", "minimumLevel"}
    )
    _exact_keys(evidence, expected_evidence_keys, f"{skill_path}.evidence")
    gates = _closed_string_list(
        evidence.get("requiredGates"), f"{skill_path}.evidence.requiredGates"
    )
    minimum_level = _string(evidence.get("minimumLevel"), f"{skill_path}.evidence.minimumLevel")
    _require(minimum_level in {"E1", "E2", "E3"}, f"{name}: unsupported evidence level")
    if enhanced:
        _require(
            evidence.get("independentReplayRequired") is (minimum_level == "E3")
            and evidence.get("sourceBindingRequired") is True,
            f"{name}: enhanced evidence boundary drift",
        )

    rollback = _mapping(spec.get("rollback"), f"{skill_path}.rollback")
    expected_rollback_keys = frozenset(
        {"required", "strategy", "rehearsalRequired"} if enhanced else {"required", "strategy"}
    )
    _exact_keys(rollback, expected_rollback_keys, f"{skill_path}.rollback")
    _require(rollback.get("required") is True, f"{name}: rollback must be required")
    expected_strategy = (
        "restore-versioned-checkpoint-and-compensate-side-effects"
        if enhanced
        else "restore-checkpoint-and-compensate-side-effects"
    )
    _require(rollback.get("strategy") == expected_strategy, f"{name}: rollback strategy drift")

    execution = _mapping(spec.get("execution"), f"{skill_path}.execution")
    expected_execution_keys = frozenset(
        {
            "class", "idempotencyRequired", "checkpointRequired",
            "independentVerificationRequired", "productionWriteApprovalRequired",
            "maxUnverifiedSideEffects",
        }
        if enhanced
        else {
            "class", "idempotencyRequired", "checkpointRequired",
            "independentVerificationRequired", "productionWriteApprovalRequired",
        }
    )
    _exact_keys(execution, expected_execution_keys, f"{skill_path}.execution")
    _require(
        execution.get("class") == "durable-replayable"
        and execution.get("idempotencyRequired") is True
        and execution.get("checkpointRequired") is True
        and execution.get("independentVerificationRequired") is True
        and execution.get("productionWriteApprovalRequired") is True,
        f"{name}: fail-closed execution contract drift",
    )
    if enhanced:
        _require(execution.get("maxUnverifiedSideEffects") == 0, f"{name}: side-effect bound drift")

    compatibility = _mapping(spec.get("compatibility"), f"{skill_path}.compatibility")
    _exact_keys(
        compatibility,
        frozenset({"packageVersion", "runtime", "versionPinned", "matrixRequired"}),
        f"{skill_path}.compatibility",
    )
    _require(
        compatibility
        == {
            "packageVersion": PACKAGE_VERSION,
            "runtime": "Elmos Proof-Driven Agentic Harness v3+",
            "versionPinned": True,
            "matrixRequired": True,
        },
        f"{name}: compatibility contract drift",
    )
    maturity = _mapping(spec.get("maturity"), f"{skill_path}.maturity")
    _exact_keys(
        maturity,
        frozenset({"status", "runtimeImplementation", "certificationTarget"}),
        f"{skill_path}.maturity",
    )
    _require(
        maturity
        == {
            "status": "specification-ready",
            "runtimeImplementation": "required",
            "certificationTarget": minimum_level,
        },
        f"{name}: maturity/evidence mismatch",
    )

    learning = _mapping(spec.get("learning"), f"{skill_path}.learning")
    expected_learning_keys = frozenset(
        {
            "captureTrajectory", "globalTrainingEligible", "tenantAdapterEligible",
            "humanAcceptanceRequired", "minimumDatasetTier",
        }
        if enhanced
        else {"captureTrajectory", "globalTrainingEligible", "tenantAdapterEligible"}
    )
    _exact_keys(learning, expected_learning_keys, f"{skill_path}.learning")
    _require(
        learning.get("captureTrajectory") is True
        and learning.get("globalTrainingEligible") is False
        and learning.get("tenantAdapterEligible") == "explicit-opt-in",
        f"{name}: learning boundary drift",
    )
    risk_class = _string(spec.get("riskClass"), f"{skill_path}.riskClass")
    if enhanced:
        _require(learning.get("minimumDatasetTier") == "Gold", f"{name}: dataset tier drift")
        _require(
            learning.get("humanAcceptanceRequired") is (risk_class == "critical"),
            f"{name}: critical human acceptance mismatch",
        )
        _require(
            rollback.get("rehearsalRequired") is (risk_class == "critical"),
            f"{name}: critical rollback rehearsal mismatch",
        )

    telemetry = _mapping(spec.get("telemetry"), f"{skill_path}.telemetry")
    expected_telemetry_keys = frozenset(
        {
            "emitTrace", "emitCost", "emitWallClock", "emitEvidenceLineage",
            "emitProgress", "sensitiveContentDefault",
        }
        if enhanced
        else {"emitTrace", "emitCost", "emitWallClock"}
    )
    _exact_keys(telemetry, expected_telemetry_keys, f"{skill_path}.telemetry")
    _require(
        telemetry.get("emitTrace") is True
        and telemetry.get("emitCost") is True
        and telemetry.get("emitWallClock") is True,
        f"{name}: base telemetry drift",
    )
    if enhanced:
        _require(
            telemetry.get("emitEvidenceLineage") is True
            and telemetry.get("emitProgress") is True
            and telemetry.get("sensitiveContentDefault") == "redacted",
            f"{name}: enhanced telemetry drift",
        )

    support = _mapping(spec.get("support"), f"{skill_path}.support")
    _exact_keys(
        support,
        frozenset({"supportTier", "deprecationPolicyRequired"}),
        f"{skill_path}.support",
    )
    _require(support.get("deprecationPolicyRequired") is True, f"{name}: support boundary drift")
    _require(support.get("supportTier") in {"standard", "LTS-candidate"}, f"{name}: support tier drift")

    business_lines = _closed_string_list(spec.get("businessLines"), f"{skill_path}.businessLines")
    capability_tags = _closed_string_list(spec.get("capabilityTags"), f"{skill_path}.capabilityTags")
    triggers = _closed_string_list(spec.get("triggers"), f"{skill_path}.triggers")
    negative_triggers = _closed_string_list(
        spec.get("negativeTriggers"), f"{skill_path}.negativeTriggers"
    )
    dependencies = _string_list(
        spec.get("dependencies"), f"{skill_path}.dependencies", nonempty=False
    )
    invariants = _closed_string_list(spec.get("invariants"), f"{skill_path}.invariants")
    expected_tail = (
        [
            "tenant-boundary-preserved", "source-and-target-traceable",
            "no-hidden-test-weakening", "no-evidence-fabrication", "machine-wall-clock-recorded",
        ]
        if enhanced
        else ["tenant-boundary-preserved", "no-evidence-fabrication", "hard-gates-not-weakened"]
    )
    _require(invariants == gates + expected_tail, f"{name}: gate/invariant alignment drift")
    failure_modes = _closed_string_list(
        spec.get("failureModes"),
        f"{skill_path}.failureModes",
        ENHANCED_FAILURE_MODES if enhanced else BASIC_FAILURE_MODES,
    )
    dependency_semantics = spec.get("dependencySemantics", UNBOUND)
    if name in BOOTSTRAP_DEPENDENCY_SKILLS:
        _require(dependency_semantics == "bootstrap-dag", f"{name}: bootstrap semantics drift")
    else:
        _require(dependency_semantics == UNBOUND, f"{name}: undeclared dependency semantics")

    return {
        "description": description,
        "kernel": kernel,
        "exposure": "atomic-registry-only",
        "risk_class": risk_class,
        "preconditions": preconditions,
        "inputs": inputs,
        "input_contracts": input_contracts,
        "outputs": outputs,
        "output_contracts": output_contracts,
        "workflow": workflow,
        "allowed_tools": allowed_tools,
        "tool_contract": {
            "allowed": allowed_tools,
            "default_deny": True,
            "environment_owned_authority": (
                True if enhanced else UNBOUND
            ),
            "parameter_validation_required": True if enhanced else UNBOUND,
            "parameter_schemas": UNBOUND,
        },
        "required_gates": gates,
        "evidence_contract": {
            "required_gates": gates,
            "minimum_level": minimum_level,
            "independent_replay_required": (
                minimum_level == "E3" if enhanced else UNBOUND
            ),
            "source_binding_required": True if enhanced else UNBOUND,
        },
        "rollback_contract": {
            "required": True,
            "strategy": expected_strategy,
            "rehearsal_required": rollback.get("rehearsalRequired", UNBOUND),
        },
        "execution_contract": {
            "class": "durable-replayable",
            "idempotency_required": True,
            "checkpoint_required": True,
            "independent_verification_required": True,
            "production_write_approval_required": True,
            "max_unverified_side_effects": execution.get("maxUnverifiedSideEffects", UNBOUND),
        },
        "compatibility_contract": {
            "package_version": PACKAGE_VERSION,
            "runtime": compatibility["runtime"],
            "version_pinned": True,
            "matrix_required": True,
            "exact_runtime_tuple": UNBOUND,
        },
        "maturity_contract": {
            "status": "specification-ready",
            "runtime_implementation": "required",
            "certification_target": minimum_level,
        },
        "learning_contract": dict(learning),
        "telemetry_contract": dict(telemetry),
        "support_contract": dict(support),
        "business_lines": business_lines,
        "capability_tags": capability_tags,
        "triggers": triggers,
        "negative_triggers": negative_triggers,
        "dependencies": dependencies,
        "dependency_semantics": dependency_semantics,
        "invariants": invariants,
        "failure_modes": failure_modes,
        "contract_generation": "ENHANCED" if enhanced else "BASIC",
    }


def _check_dag(nodes: set[str], edges: Mapping[str, Sequence[str]]) -> None:
    unresolved = sorted(
        (node, dependency)
        for node, dependencies in edges.items()
        for dependency in dependencies
        if dependency not in nodes
    )
    _require(not unresolved, f"Skill DAG has unresolved dependencies: {unresolved[:10]}")
    self_dependencies = sorted(node for node, dependencies in edges.items() if node in dependencies)
    _require(not self_dependencies, f"Skill DAG has self dependencies: {self_dependencies}")
    indegree = {node: 0 for node in nodes}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for node, dependencies in edges.items():
        for dependency in dependencies:
            indegree[node] += 1
            outgoing[dependency].append(node)
    queue = deque(sorted(node for node, degree in indegree.items() if degree == 0))
    visited = 0
    while queue:
        node = queue.popleft()
        visited += 1
        for successor in sorted(outgoing[node]):
            indegree[successor] -= 1
            if indegree[successor] == 0:
                queue.append(successor)
    _require(
        visited == len(nodes),
        "Skill DAG cycle detected among "
        f"{sorted(node for node, degree in indegree.items() if degree > 0)[:20]}",
    )


def _handler_id(pack: str) -> str:
    return "pack." + pack.replace("-", "_")


def _capability_state(skill_name: str) -> str:
    return "LOCAL" if skill_name in LOCAL_CAPABILITY_ALLOWLIST else "PREPARE_ONLY"


def _files_below(files: Mapping[str, zipfile.ZipInfo], prefix: str) -> set[str]:
    return {path[len(prefix) :] for path in files if path.startswith(prefix)}


def _validate_manifest(manifest: Mapping[str, Any]) -> tuple[list[str], str, str, str]:
    _require(manifest.get("apiVersion") == "elmos.ai/v1", "manifest apiVersion mismatch")
    _require(manifest.get("kind") == "KnowledgeSkillModelFoundryPackage", "manifest kind mismatch")
    metadata = _mapping(manifest.get("metadata"), "manifest.metadata")
    _require(metadata.get("name") == PACKAGE_NAME, "manifest package name mismatch")
    _require(metadata.get("version") == PACKAGE_VERSION, "manifest version mismatch")
    exact_metadata = {
        "atomicSkillCount": EXPECTED_ATOMIC_SKILLS,
        "metaSkillCount": EXPECTED_META_SKILLS,
        "packCount": EXPECTED_PACKS,
        "evaluationCaseCount": EXPECTED_EVALUATION_CASES,
        "conformanceManifestCount": EXPECTED_ATOMIC_SKILLS,
        "dependencyCycleCount": 0,
        "unresolvedDependencyCount": 0,
        "validationStatus": "package-integrity-passed",
        "runtimeStatus": "specification-ready",
    }
    for key, expected in exact_metadata.items():
        _require(metadata.get(key) == expected, f"manifest metadata drift for {key}")
    _require(metadata.get("priorityCounts") == dict(EXPECTED_PRIORITY_COUNTS), "manifest priority counts mismatch")
    spec = _mapping(manifest.get("spec"), "manifest.spec")
    packs = _string_list(spec.get("packs"), "manifest.spec.packs")
    _require(packs == list(EXPECTED_PACK_COUNTS), "manifest pack order or identity mismatch")
    catalog_path = _string(spec.get("atomicRegistry"), "manifest.spec.atomicRegistry")
    business_path = _string(spec.get("businessLineRegistry"), "manifest.spec.businessLineRegistry")
    technology_path = _string(spec.get("technologySupportMatrix"), "manifest.spec.technologySupportMatrix")
    for label, path in (
        ("catalog", catalog_path),
        ("business line registry", business_path),
        ("technology matrix", technology_path),
    ):
        _require(
            _relative_member_path(PACKAGE_PREFIX + path) == path,
            f"manifest {label} path is unsafe",
        )
    _require(catalog_path.endswith(".yaml"), "authoritative catalog must be YAML")
    return packs, catalog_path, business_path, technology_path


def _validate_policy_contract(
    value: Any,
    *,
    enhanced: bool,
    label: str,
) -> dict[str, Any]:
    policy = _mapping(value, label)
    _exact_keys(policy, frozenset({"default", "allowWhen", "approvalWhen", "denyWhen"}), label)
    expected = ENHANCED_POLICY if enhanced else BASIC_POLICY
    _require(policy == expected, f"{label}: exact default-deny policy drift")
    return {
        "default": "deny",
        "allow_when": list(expected["allowWhen"]),
        "approval_when": list(expected["approvalWhen"]),
        "deny_when": list(expected["denyWhen"]),
    }


def _validate_eval_contract(
    value: Any,
    *,
    enhanced: bool,
    gates: Sequence[str],
    label: str,
) -> dict[str, Any]:
    contract = _mapping(value, label)
    _exact_keys(
        contract,
        frozenset({"activation", "outcome", "process", "efficiency", "security", "learning"}),
        label,
    )
    activation = _mapping(contract.get("activation"), f"{label}.activation")
    _exact_keys(
        activation,
        frozenset(
            {
                "positiveRequired", "negativeRequired", "split",
                "ambiguousRequired", "adversarialRequired",
            }
        ),
        f"{label}.activation",
    )
    expected_activation = {
        "positiveRequired": 8,
        "negativeRequired": 8,
        "split": "repo-org-time-disjoint",
        "ambiguousRequired": 4,
        "adversarialRequired": 4,
    }
    _require(activation == expected_activation, f"{label}: activation contract drift")
    outcomes = _list(contract.get("outcome"), f"{label}.outcome")
    compiled_outcomes: list[dict[str, str]] = []
    for index, value_row in enumerate(outcomes):
        row_label = f"{label}.outcome[{index}]"
        row = _mapping(value_row, row_label)
        _exact_keys(row, frozenset({"gate", "type"}), row_label)
        gate = _string(row.get("gate"), f"{row_label}.gate")
        _require(row.get("type") == "deterministic-first", f"{row_label}: type drift")
        compiled_outcomes.append({"gate": gate, "type": "deterministic-first"})
    _require(
        [row["gate"] for row in compiled_outcomes] == list(gates),
        f"{label}: outcome/evidence gate mismatch",
    )
    expected_process = (
        [
            "authorized-tools-only", "environment-owned-authority", "checkpoint-created",
            "source-target-lineage", "independent-verification", "rollback-on-hard-failure",
        ]
        if enhanced
        else [
            "authorized-tools-only", "checkpoint-created", "independent-verification",
            "rollback-on-hard-failure",
        ]
    )
    expected_efficiency = (
        [
            "wall_clock_ms", "queue_ms", "input_tokens", "output_tokens", "tool_calls",
            "build_minutes", "cost",
        ]
        if enhanced
        else ["wall_clock_ms", "input_tokens", "output_tokens", "tool_calls", "cost"]
    )
    process = _closed_string_list(contract.get("process"), f"{label}.process", expected_process)
    efficiency = _closed_string_list(
        contract.get("efficiency"), f"{label}.efficiency", expected_efficiency
    )
    expected_security = ["tenant-isolation", "prompt-injection", "secret-leakage", "artifact-integrity"]
    if enhanced:
        expected_security.append("supply-chain")
    security = _closed_string_list(
        contract.get("security"), f"{label}.security", expected_security
    )
    learning = _closed_string_list(
        contract.get("learning"),
        f"{label}.learning",
        ["training-rights", "dataset-tier", "eval-leakage", "human-acceptance"],
    )
    return {
        "positive_required": 8,
        "negative_required": 8,
        "ambiguous_required": 4,
        "adversarial_required": 4,
        "split": "repo-org-time-disjoint",
        "outcome": compiled_outcomes,
        "process": process,
        "efficiency": efficiency,
        "security": security,
        "learning": learning,
        "corpus_embedded": False,
    }


def _validate_eval_cases(value: Any, *, label: str, name: str) -> None:
    cases = _mapping(value, label)
    _exact_keys(cases, frozenset({"positive", "negative", "ambiguous", "adversarial"}), label)
    for kind, expected_count in {
        "positive": 8,
        "negative": 8,
        "ambiguous": 4,
        "adversarial": 4,
    }.items():
        rows = _list(cases.get(kind), f"{label}.{kind}")
        _require(len(rows) == expected_count, f"{name}: {kind} case count mismatch")
        expected_keys = (
            frozenset({"query", "shouldTrigger"})
            if kind in {"positive", "negative"}
            else frozenset({"query", "expected"})
        )
        for case_index, raw_case in enumerate(rows):
            case_label = f"{label}.{kind}[{case_index}]"
            case = _mapping(raw_case, case_label)
            _exact_keys(case, expected_keys, case_label)
            _string(case.get("query"), f"{case_label}.query")
            if kind == "positive":
                _require(case.get("shouldTrigger") is True, f"{name}: malformed positive case")
            elif kind == "negative":
                _require(case.get("shouldTrigger") is False, f"{name}: malformed negative case")
            else:
                _string(case.get("expected"), f"{case_label}.expected")


def _validate_conformance_contract(value: Any, *, label: str, name: str) -> dict[str, Any]:
    conformance = _mapping(value, label)
    _exact_keys(
        conformance,
        frozenset({"skill", "packageVersion", "requiredChecks", "runtimeStatus"}),
        label,
    )
    _require(conformance.get("skill") == name, f"{name}: conformance identity mismatch")
    _require(conformance.get("packageVersion") == PACKAGE_VERSION, f"{name}: conformance version drift")
    checks = _closed_string_list(
        conformance.get("requiredChecks"), f"{label}.requiredChecks", CONFORMANCE_CHECKS
    )
    runtime_status = "not-implemented-by-this-specification-package"
    _require(conformance.get("runtimeStatus") == runtime_status, f"{name}: runtime boundary mismatch")
    return {
        "package_version": PACKAGE_VERSION,
        "required_checks": checks,
        "runtime_status": runtime_status,
    }


def _validate_atomic_skills(
    zf: zipfile.ZipFile,
    files: Mapping[str, zipfile.ZipInfo],
    controlled_hashes: Mapping[str, str],
    catalog_items: Sequence[Any],
    schema: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, list[str]], Counter[str], Counter[str], Counter[str]]:
    validator = Draft202012Validator(schema)
    compiled: list[dict[str, Any]] = []
    dependencies: dict[str, list[str]] = {}
    pack_counts: Counter[str] = Counter()
    priority_counts: Counter[str] = Counter()
    risk_counts: Counter[str] = Counter()
    seen: set[str] = set()
    all_expected_skill_files: set[str] = set()
    for index, raw_item in enumerate(catalog_items):
        item = _mapping(raw_item, f"catalog.skills[{index}]")
        name = _validate_skill_id(item.get("id"), f"catalog.skills[{index}].id")
        _require(name not in seen, f"duplicate catalog Skill ID: {name}")
        seen.add(name)
        pack = _string(item.get("pack"), f"catalog.{name}.pack")
        _require(pack in EXPECTED_PACK_COUNTS, f"catalog.{name}: unknown pack {pack}")
        expected_source = f"skills/atomic/{pack}/{name}/SKILL.md"
        source_path = _string(item.get("path"), f"catalog.{name}.path")
        _require(source_path == expected_source, f"catalog.{name}: source path mismatch")
        prefix = f"skills/atomic/{pack}/{name}/"
        inventory = _files_below(files, prefix)
        _require(
            inventory == ATOMIC_SKILL_FILES,
            f"atomic Skill {pack}/{name}: file inventory mismatch: "
            f"missing={sorted(ATOMIC_SKILL_FILES - inventory)}, "
            f"extra={sorted(inventory - ATOMIC_SKILL_FILES)}",
        )
        all_expected_skill_files.update(prefix + relative for relative in ATOMIC_SKILL_FILES)
        skill_path = prefix + "skill.yaml"
        skill_contract = _mapping(load_yaml(_read_member(zf, files[skill_path]), skill_path), skill_path)
        schema_errors = sorted(validator.iter_errors(skill_contract), key=lambda error: list(error.path))
        _require(
            not schema_errors,
            f"{skill_path}: Schema validation failed: "
            + "; ".join(error.message for error in schema_errors[:5]),
        )
        normalized = _validate_contract_shape(
            skill_contract,
            name=name,
            pack=pack,
            skill_path=skill_path,
        )
        metadata = _mapping(skill_contract.get("metadata"), f"{skill_path}.metadata")
        priority = _string(metadata.get("priority"), f"{skill_path}.priority")
        risk_class = str(normalized["risk_class"])
        maturity_status = str(normalized["maturity_contract"]["status"])
        version = _string(metadata.get("version"), f"{skill_path}.metadata.version")
        gates = list(normalized["required_gates"])
        allowed_tools = list(normalized["allowed_tools"])
        inputs = list(normalized["inputs"])
        outputs = list(normalized["outputs"])
        deps = list(normalized["dependencies"])
        exact_pairs = (
            (metadata.get("name"), name, "metadata.name"),
            (metadata.get("pack"), pack, "metadata.pack"),
            (version, item.get("version"), "version"),
            (priority, item.get("priority"), "priority"),
            (metadata.get("owner"), item.get("owner"), "owner"),
            (risk_class, item.get("riskClass"), "riskClass"),
            (maturity_status, item.get("maturity"), "maturity"),
            (inputs, item.get("inputs"), "inputs"),
            (outputs, item.get("outputs"), "outputs"),
            (allowed_tools, item.get("tools"), "tools"),
            (gates, item.get("mustPassGates"), "required gates"),
        )
        for actual, expected, label in exact_pairs:
            _require(actual == expected, f"catalog/skill.yaml mismatch for {name}: {label}")
        # The authoritative catalog intentionally omits inherited dependency
        # lists for the carried-forward v2 records. The exact per-Skill
        # contract remains checksum-bound and is the dependency authority;
        # whenever the catalog spells dependencies out, parity is mandatory.
        if "dependencies" in item:
            _require(
                deps == item["dependencies"],
                f"catalog/skill.yaml mismatch for {name}: dependencies",
            )
        _require(version == PACKAGE_VERSION, f"{name}: package version mismatch")
        _require(maturity_status == "specification-ready", f"{name}: maturity overclaim")
        frontmatter = _parse_frontmatter(_read_member(zf, files[source_path]), source_path)
        _require(frontmatter.get("name") == name, f"{name}: SKILL.md name mismatch")
        fm_metadata = _mapping(frontmatter.get("metadata"), f"{source_path}.metadata")
        _require(fm_metadata.get("version") == version, f"{name}: frontmatter version mismatch")
        _require(fm_metadata.get("pack") == pack, f"{name}: frontmatter pack mismatch")
        _require(fm_metadata.get("priority") == priority, f"{name}: frontmatter priority mismatch")
        eval_contract_path = prefix + "evals/contract.yaml"
        eval_contract = _validate_eval_contract(
            load_yaml(_read_member(zf, files[eval_contract_path]), eval_contract_path),
            enhanced=pack in ENHANCED_PACKS,
            gates=gates,
            label=eval_contract_path,
        )
        cases_path = prefix + "evals/cases.yaml"
        _validate_eval_cases(
            load_yaml(_read_member(zf, files[cases_path]), cases_path),
            label=cases_path,
            name=name,
        )
        policy_path = prefix + "policies/execution.yaml"
        policy = _validate_policy_contract(
            load_yaml(_read_member(zf, files[policy_path]), policy_path),
            enhanced=pack in ENHANCED_PACKS,
            label=policy_path,
        )
        conformance_path = prefix + "tests/conformance.yaml"
        conformance = _validate_conformance_contract(
            load_yaml(_read_member(zf, files[conformance_path]), conformance_path),
            label=conformance_path,
            name=name,
        )
        notes_path = prefix + "references/implementation-notes.md"
        _require(bool(_read_member(zf, files[notes_path]).strip()), f"{name}: implementation notes empty")
        dependencies[name] = deps
        pack_counts[pack] += 1
        priority_counts[priority] += 1
        risk_counts[risk_class] += 1
        source_bindings = {
            "skill_markdown": {"path": source_path, "sha256": controlled_hashes[source_path]},
            "skill_contract": {"path": skill_path, "sha256": controlled_hashes[skill_path]},
            "execution_policy": {"path": policy_path, "sha256": controlled_hashes[policy_path]},
            "conformance": {
                "path": conformance_path,
                "sha256": controlled_hashes[conformance_path],
            },
            "eval_contract": {
                "path": eval_contract_path,
                "sha256": controlled_hashes[eval_contract_path],
            },
            "eval_cases": {"path": cases_path, "sha256": controlled_hashes[cases_path]},
        }
        compiled.append(
            {
                "name": name,
                "pack": pack,
                "version": version,
                "priority": priority,
                "risk_class": risk_class,
                "maturity": maturity_status,
                "owner": metadata["owner"],
                "description": normalized["description"],
                "kernel": normalized["kernel"],
                "exposure": normalized["exposure"],
                "source_path": source_path,
                "source_sha256": controlled_hashes[source_path],
                "source_bindings": source_bindings,
                "dependencies": deps,
                "dependency_semantics": normalized["dependency_semantics"],
                "inputs": inputs,
                "input_contracts": normalized["input_contracts"],
                "outputs": outputs,
                "output_contracts": normalized["output_contracts"],
                "preconditions": normalized["preconditions"],
                "workflow": normalized["workflow"],
                "allowed_tools": allowed_tools,
                "tool_contract": normalized["tool_contract"],
                "required_gates": gates,
                "evidence_contract": normalized["evidence_contract"],
                "rollback_contract": normalized["rollback_contract"],
                "execution_contract": normalized["execution_contract"],
                "compatibility_contract": normalized["compatibility_contract"],
                "maturity_contract": normalized["maturity_contract"],
                "learning_contract": normalized["learning_contract"],
                "telemetry_contract": normalized["telemetry_contract"],
                "support_contract": normalized["support_contract"],
                "business_lines": normalized["business_lines"],
                "capability_tags": normalized["capability_tags"],
                "triggers": normalized["triggers"],
                "negative_triggers": normalized["negative_triggers"],
                "invariants": normalized["invariants"],
                "failure_modes": normalized["failure_modes"],
                "contract_generation": normalized["contract_generation"],
                "policy_contract": policy,
                "conformance_contract": conformance,
                "activation_contract": eval_contract,
                "handler_id": _handler_id(pack),
                "semantic_handler_binding": (
                    f"local.{name}"
                    if name in LOCAL_CAPABILITY_ALLOWLIST
                    else UNBOUND
                ),
                "capability_state": _capability_state(name),
                "external_evidence_status": "NOT_RUN",
                "certification_status": "NOT_CERTIFIED",
            }
        )
    source_atomic_files = {path for path in files if path.startswith("skills/atomic/")}
    _require(
        source_atomic_files == all_expected_skill_files,
        f"atomic source inventory has unregistered files: {sorted(source_atomic_files - all_expected_skill_files)[:20]}",
    )
    return compiled, dependencies, pack_counts, priority_counts, risk_counts


def _validate_meta_skills(
    zf: zipfile.ZipFile,
    files: Mapping[str, zipfile.ZipInfo],
    controlled_hashes: Mapping[str, str],
    packs: Sequence[str],
    candidates_by_pack: Mapping[str, Sequence[str]],
) -> tuple[list[dict[str, Any]], Counter[str], int]:
    compiled: list[dict[str, Any]] = []
    version_counts: Counter[str] = Counter()
    activation_cases = 0
    expected_meta_files: set[str] = set()
    for pack in packs:
        prefix = f"skills/meta/{pack}/"
        inventory = _files_below(files, prefix)
        _require(inventory == META_SKILL_FILES, f"meta Skill {pack}: file inventory mismatch: {sorted(inventory)}")
        expected_meta_files.update(prefix + relative for relative in META_SKILL_FILES)
        source_path = prefix + "SKILL.md"
        frontmatter = _parse_frontmatter(_read_member(zf, files[source_path]), source_path)
        name = f"elmos-{pack}"
        _require(frontmatter.get("name") == name, f"meta Skill name mismatch for {pack}")
        metadata = _mapping(frontmatter.get("metadata"), f"{source_path}.metadata")
        _require(metadata.get("pack") == pack, f"meta Skill pack mismatch for {pack}")
        _require(metadata.get("exposure") == "meta", f"meta Skill exposure mismatch for {pack}")
        version = _string(metadata.get("version"), f"{source_path}.metadata.version")
        expected_version = "2.0.0" if int(pack[:2]) <= 16 else PACKAGE_VERSION
        _require(version == expected_version, f"meta Skill source-version drift for {pack}")
        version_counts[version] += 1
        activation_path = prefix + "evals/activation.json"
        rows = _list(load_json(_read_member(zf, files[activation_path]), activation_path), activation_path)
        expected_count = 4 if int(pack[:2]) <= 16 else 5
        _require(len(rows) == expected_count, f"meta activation count mismatch for {pack}")
        actual_true = 0
        for index, raw_row in enumerate(rows):
            row = _mapping(raw_row, f"{activation_path}[{index}]")
            _string(row.get("query"), f"{activation_path}[{index}].query")
            _require(isinstance(row.get("should_trigger"), bool), f"{activation_path}[{index}]: should_trigger must be boolean")
            actual_true += int(row["should_trigger"])
        _require(actual_true == 2, f"meta activation polarity mismatch for {pack}")
        activation_cases += len(rows)
        candidates = sorted(candidates_by_pack[pack])
        _require(len(candidates) == EXPECTED_PACK_COUNTS[pack], f"meta candidate count mismatch for {pack}")
        compiled.append(
            {
                "name": name,
                "pack": pack,
                "source_path": source_path,
                "source_sha256": controlled_hashes[source_path],
                "candidates": candidates,
            }
        )
    source_meta_files = {path for path in files if path.startswith("skills/meta/")}
    _require(source_meta_files == expected_meta_files, "meta source inventory drift")
    _require(
        version_counts == Counter({"2.0.0": 17, "3.0.0": 24}),
        f"meta source version distribution mismatch: {dict(version_counts)}",
    )
    return compiled, version_counts, activation_cases


def _validate_supporting_surfaces(
    zf: zipfile.ZipFile,
    files: Mapping[str, zipfile.ZipInfo],
    controlled_hashes: Mapping[str, str],
    catalog_items: Sequence[Mapping[str, Any]],
    packs: Sequence[str],
    business_path: str,
    technology_path: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    schema_paths = frozenset(path for path in files if path.startswith("schemas/") and path.endswith(".json"))
    _require(schema_paths == EXPECTED_SCHEMA_PATHS, "Schema inventory mismatch")
    for path in sorted(schema_paths):
        schema = _mapping(load_json(_read_member(zf, files[path]), path), path)
        _require(schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", f"{path}: draft mismatch")
        Draft202012Validator.check_schema(schema)
    policy_paths = frozenset(path for path in files if path.startswith("policies/") and path.endswith(".rego"))
    _require(policy_paths == EXPECTED_POLICY_PATHS, "policy inventory mismatch")
    for path in sorted(policy_paths):
        try:
            text = _read_member(zf, files[path]).decode("utf-8")
        except UnicodeDecodeError as exc:
            fail(f"{path}: invalid UTF-8: {exc}")
        _require(re.search(r"(?m)^package\s+elmos\.", text) is not None, f"{path}: package declaration missing")
        _require(re.search(r"(?m)^default\s+", text) is not None, f"{path}: default decision missing")
    pipeline_paths = frozenset(path for path in files if path.startswith("pipelines/") and path.endswith(".yaml"))
    _require(pipeline_paths == EXPECTED_PIPELINE_PATHS, "pipeline inventory mismatch")
    compiled_pipelines: list[dict[str, Any]] = []
    pipeline_names: set[str] = set()
    pipeline_step_count = 0
    pipeline_kind_counts: Counter[str] = Counter()
    for path in sorted(pipeline_paths):
        pipeline = _mapping(load_yaml(_read_member(zf, files[path]), path), path)
        _require(pipeline.get("apiVersion") == "elmos.ai/v1", f"{path}: apiVersion mismatch")
        kind = _string(pipeline.get("kind"), f"{path}.kind")
        _require(kind in {"Pipeline", "DurablePipeline"}, f"{path}: unsupported kind")
        metadata = _mapping(pipeline.get("metadata"), f"{path}.metadata")
        name = _validate_skill_id(metadata.get("name"), f"{path}.metadata.name")
        _require(name not in pipeline_names, f"duplicate pipeline name: {name}")
        pipeline_names.add(name)
        spec = _mapping(pipeline.get("spec"), f"{path}.spec")
        steps = _list(spec.get("steps"), f"{path}.spec.steps")
        _require(bool(steps), f"{path}: pipeline steps empty")
        pipeline_step_count += len(steps)
        pipeline_kind_counts[kind] += 1
        compiled_pipelines.append(
            {
                "name": name,
                "kind": kind,
                "source_path": path,
                "source_sha256": controlled_hashes[path],
                "execution_mode": "PREPARE_ONLY",
            }
        )
    _require(pipeline_step_count == 127, f"pipeline step count mismatch: {pipeline_step_count}")
    _require(
        pipeline_kind_counts == Counter({"DurablePipeline": 10, "Pipeline": 4}),
        f"pipeline kind distribution mismatch: {dict(pipeline_kind_counts)}",
    )
    technology = _mapping(load_yaml(_read_member(zf, files[technology_path]), technology_path), technology_path)
    technology_spec = _mapping(technology.get("spec"), f"{technology_path}.spec")
    profile_counts = {
        "languages_and_builds": len(_list(technology_spec.get("languagesAndBuilds"), "technology.languagesAndBuilds")),
        "database_engines": len(_list(technology_spec.get("databaseEngines"), "technology.databaseEngines")),
        "frameworks_and_runtimes": len(_list(technology_spec.get("frameworksAndRuntimes"), "technology.frameworksAndRuntimes")),
        "cloud_platforms": len(_list(technology_spec.get("cloudPlatforms"), "technology.cloudPlatforms")),
    }
    _require(
        profile_counts == {
            "languages_and_builds": 36,
            "database_engines": 24,
            "frameworks_and_runtimes": 36,
            "cloud_platforms": 16,
        },
        f"technology support matrix count mismatch: {profile_counts}",
    )
    support_levels = _mapping(technology_spec.get("supportLevels"), "technology.supportLevels")
    _require(
        set(support_levels) == {"specification-ready", "implemented", "production-certified"},
        "technology support levels drift",
    )
    business = _mapping(load_yaml(_read_member(zf, files[business_path]), business_path), business_path)
    business_lines = _list(
        _mapping(business.get("spec"), f"{business_path}.spec").get("businessLines"),
        f"{business_path}.spec.businessLines",
    )
    _require(len(business_lines) == 24, "business-line count mismatch")
    catalog_pack_counts = Counter(str(item["pack"]) for item in catalog_items)
    golden_route_null = 0
    observed_business_packs: list[str] = []
    for index, raw_line in enumerate(business_lines):
        line = _mapping(raw_line, f"businessLines[{index}]")
        pack = _string(line.get("pack"), f"businessLines[{index}].pack")
        observed_business_packs.append(pack)
        _require(
            line.get("atomicSkillCount") == catalog_pack_counts[pack],
            f"business-line Skill count mismatch for {pack}",
        )
        _require(line.get("status") == "specification-ready", f"business-line status overclaim for {pack}")
        golden_route_null += int(line.get("goldenRouteSkill") is None)
    _require(observed_business_packs == list(packs)[17:], "business-line pack identity mismatch")
    _require(golden_route_null == 7, "business-line null Golden Route count mismatch")
    graph_path = "registry/pack-dependency-graph.yaml"
    graph = _mapping(load_yaml(_read_member(zf, files[graph_path]), graph_path), graph_path)
    graph_spec = _mapping(graph.get("spec"), f"{graph_path}.spec")
    common_dependencies = _string_list(graph_spec.get("commonDependencies"), f"{graph_path}.commonDependencies")
    _require(len(common_dependencies) == 5, "pack graph common dependency count mismatch")
    graph_packs = _list(graph_spec.get("packs"), f"{graph_path}.packs")
    _require(len(graph_packs) == 24, "pack dependency graph pack count mismatch")
    atomic_ids = {str(item["id"]) for item in catalog_items}
    graph_references: list[str] = []
    for index, raw_pack in enumerate(graph_packs):
        graph_pack = _mapping(raw_pack, f"packGraph.packs[{index}]")
        graph_references.extend(
            _string_list(graph_pack.get("dependsOnSkills"), f"packGraph.packs[{index}].dependsOnSkills")
        )
    _require(len(graph_references) == 72, "pack dependency graph reference count mismatch")
    _require(set(graph_references) <= atomic_ids, "pack dependency graph has unresolved references")
    sql_path = "database/postgresql-schema.sql"
    try:
        sql = _read_member(zf, files[sql_path]).decode("utf-8")
    except UnicodeDecodeError as exc:
        fail(f"{sql_path}: invalid UTF-8: {exc}")
    table_count = len(re.findall(r"(?mi)^CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+", sql))
    _require(table_count == EXPECTED_POSTGRES_TABLE_COUNT, f"PostgreSQL table count mismatch: {table_count}")
    rls_enabled = re.search(r"(?i)ENABLE\s+ROW\s+LEVEL\s+SECURITY", sql) is not None
    rls_policies = len(re.findall(r"(?mi)^CREATE\s+POLICY\s+", sql))
    _require(not rls_enabled and rls_policies == 0, "pinned RLS gap unexpectedly changed")
    license_text = _read_member(zf, files["LICENSE"]).decode("utf-8")
    license_placeholder = "Replace with company-approved legal text before distribution." in license_text
    _require(license_placeholder, "pinned placeholder license gap unexpectedly changed")
    return compiled_pipelines, {
        "profiles": profile_counts,
        "pipeline_steps": pipeline_step_count,
        "business_lines": len(business_lines),
        "golden_route_skill_null": golden_route_null,
        "postgresql_tables": table_count,
        "postgresql_rls_enabled": rls_enabled,
        "postgresql_rls_policy_count": rls_policies,
        "license_placeholder": license_placeholder,
        "schema_count": len(schema_paths),
        "policy_count": len(policy_paths),
        "pipeline_count": len(pipeline_paths),
        "pack_graph_references": len(graph_references),
        "pack_graph_unique_references": len(set(graph_references)),
    }


def _validate_auxiliary_json_catalog(
    zf: zipfile.ZipFile,
    files: Mapping[str, zipfile.ZipInfo],
    authoritative_ids: Sequence[str],
) -> dict[str, Any]:
    path = "registry/skill-catalog.json"
    auxiliary = _mapping(load_json(_read_member(zf, files[path]), path), path)
    metadata = _mapping(auxiliary.get("metadata"), f"{path}.metadata")
    items = _list(_mapping(auxiliary.get("spec"), f"{path}.spec").get("skills"), f"{path}.spec.skills")
    ids = [
        _validate_skill_id(_mapping(item, f"{path}.skills").get("id"), f"{path}.skill.id")
        for item in items
    ]
    _require(metadata.get("version") == "2.0.0", "auxiliary JSON catalog version drift")
    _require(len(ids) == 458 and len(set(ids)) == 458, "auxiliary JSON catalog count drift")
    authoritative_set = set(authoritative_ids)
    _require(set(ids) <= authoritative_set, "auxiliary JSON catalog has non-authoritative IDs")
    _require(len(authoritative_set - set(ids)) == 852, "auxiliary JSON catalog stale delta mismatch")
    return {
        "status": "STALE_NON_AUTHORITATIVE",
        "version": "2.0.0",
        "skill_count": 458,
        "missing_from_authoritative": 852,
        "extra_vs_authoritative": 0,
    }


def _gap(code: str, status: str, detail: str) -> dict[str, str]:
    return {"code": code, "status": status, "detail": detail}


def audit_archive(
    archive_path: Path, identity: ArchiveIdentity = PINNED_ARCHIVE_IDENTITY
) -> AuditResult:
    """Validate the package directly from ZIP and return normalized assets."""
    archive_path = archive_path.resolve()
    archive_sha256 = verify_archive(archive_path, identity)
    with zipfile.ZipFile(archive_path, "r") as zf:
        _require(zf.comment == b"", "archive comment is not allowed")
        infos = zf.infolist()
        archive_metrics = inspect_archive_structure(infos, identity)
        _require(zf.testzip() is None, "archive CRC failure")
        files = _relative_file_index(infos)
        controlled_hashes = verify_controlled_files(zf, files)
        archive_metrics = ArchiveMetrics(
            entries=archive_metrics.entries,
            files=archive_metrics.files,
            directories=archive_metrics.directories,
            controlled_files=len(controlled_hashes),
            compressed_member_bytes=archive_metrics.compressed_member_bytes,
            uncompressed_bytes=archive_metrics.uncompressed_bytes,
            maximum_member_compression_ratio=archive_metrics.maximum_member_compression_ratio,
            executable_files=archive_metrics.executable_files,
        )
        manifest_path = "manifest.yaml"
        manifest = _mapping(load_yaml(_read_member(zf, files[manifest_path]), manifest_path), manifest_path)
        packs, catalog_path, business_path, technology_path = _validate_manifest(manifest)
        _require(catalog_path in controlled_hashes, "manifest catalog is not checksum-controlled")
        catalog = _mapping(load_yaml(_read_member(zf, files[catalog_path]), catalog_path), catalog_path)
        _require(catalog.get("apiVersion") == "elmos.ai/v1", "catalog apiVersion mismatch")
        _require(catalog.get("kind") == "SkillCatalog", "catalog kind mismatch")
        catalog_metadata = _mapping(catalog.get("metadata"), f"{catalog_path}.metadata")
        _require(catalog_metadata.get("version") == PACKAGE_VERSION, "catalog version mismatch")
        _require(catalog_metadata.get("atomicSkillCount") == EXPECTED_ATOMIC_SKILLS, "catalog declared Skill count mismatch")
        _require(catalog_metadata.get("packCount") == EXPECTED_PACKS, "catalog declared pack count mismatch")
        catalog_spec = _mapping(catalog.get("spec"), f"{catalog_path}.spec")
        discovery_source = _mapping(catalog_spec.get("discovery"), f"{catalog_path}.discovery")
        discovery = {
            "startup": discovery_source.get("startup"),
            "candidate_limit": discovery_source.get("maxCandidates"),
            "activation_limit": discovery_source.get("maxActivated"),
        }
        _require(
            discovery == {"startup": "meta-only", "candidate_limit": 16, "activation_limit": 8},
            f"catalog discovery contract mismatch: {discovery}",
        )
        discovery_policy_path = "registry/discovery-policy.yaml"
        discovery_policy = _mapping(
            load_yaml(_read_member(zf, files[discovery_policy_path]), discovery_policy_path),
            discovery_policy_path,
        )
        discovery_policy_spec = _mapping(discovery_policy.get("spec"), f"{discovery_policy_path}.spec")
        _require(
            discovery_policy_spec.get("startupExposure") == ["skills/meta"]
            and discovery_policy_spec.get("candidateLimit") == discovery["candidate_limit"]
            and discovery_policy_spec.get("activationLimit") == discovery["activation_limit"],
            "discovery policy/catalog mismatch",
        )
        catalog_items = _list(catalog_spec.get("skills"), f"{catalog_path}.skills")
        _require(len(catalog_items) == EXPECTED_ATOMIC_SKILLS, "authoritative catalog count mismatch")
        skill_schema_path = "schemas/skill-contract-v3.schema.json"
        skill_schema = _mapping(
            load_json(_read_member(zf, files[skill_schema_path]), skill_schema_path), skill_schema_path
        )
        atomic_skills, dependency_graph, pack_counts, priority_counts, risk_counts = _validate_atomic_skills(
            zf, files, controlled_hashes, catalog_items, skill_schema
        )
        _require(len(atomic_skills) == EXPECTED_ATOMIC_SKILLS, "atomic Skill count mismatch")
        _require(dict(pack_counts) == dict(EXPECTED_PACK_COUNTS), f"pack counts mismatch: {dict(pack_counts)}")
        _require(dict(priority_counts) == dict(EXPECTED_PRIORITY_COUNTS), f"priority counts mismatch: {dict(priority_counts)}")
        _require(dict(risk_counts) == dict(EXPECTED_RISK_COUNTS), f"risk counts mismatch: {dict(risk_counts)}")
        dependency_edges = sum(len(deps) for deps in dependency_graph.values())
        _require(dependency_edges == EXPECTED_DEPENDENCY_EDGES, f"dependency edge count mismatch: {dependency_edges}")
        _check_dag(set(dependency_graph), dependency_graph)
        candidates_by_pack: dict[str, list[str]] = defaultdict(list)
        for skill in atomic_skills:
            candidates_by_pack[str(skill["pack"])].append(str(skill["name"]))
        meta_skills, meta_version_counts, meta_activation_cases = _validate_meta_skills(
            zf, files, controlled_hashes, packs, candidates_by_pack
        )
        _require(len(meta_skills) == EXPECTED_META_SKILLS, "meta Skill count mismatch")
        compiled_pipelines, supporting = _validate_supporting_surfaces(
            zf,
            files,
            controlled_hashes,
            catalog_items,
            packs,
            business_path,
            technology_path,
        )
        auxiliary = _validate_auxiliary_json_catalog(
            zf, files, [str(skill["name"]) for skill in atomic_skills]
        )
        duplicate_schema = (
            controlled_hashes["schemas/skill-contract.schema.json"]
            == controlled_hashes["schemas/skill-contract-v3.schema.json"]
        )
        _require(duplicate_schema, "pinned duplicate Schema gap unexpectedly changed")
    package = {
        "id": PACKAGE_ID,
        "name": PACKAGE_NAME,
        "version": PACKAGE_VERSION,
        "archive_sha256": archive_sha256,
        "archive_bytes": identity.byte_count,
    }
    compiled_catalog: dict[str, Any] = {
        "schema_version": "elmos.knowledge-skill-model-foundry.compiled-catalog.v2",
        "package": package,
        "authority": {
            "catalog_path": catalog_path,
            "catalog_sha256": controlled_hashes[catalog_path],
            "auxiliary_json_status": "STALE_NON_AUTHORITATIVE",
        },
        "discovery": discovery,
        "atomic_skills": sorted(atomic_skills, key=lambda item: str(item["name"])),
        "meta_skills": sorted(meta_skills, key=lambda item: str(item["pack"])),
        "pipelines": sorted(compiled_pipelines, key=lambda item: str(item["name"])),
    }
    gaps = [
        _gap("AUXILIARY_JSON_CATALOG_STALE", "STALE_NON_AUTHORITATIVE", "registry/skill-catalog.json is v2.0.0 with 458 Skills and omits 852 authoritative YAML Skills."),
        _gap("DUPLICATE_SKILL_CONTRACT_SCHEMA", "DECLARED_GAP", "skill-contract.schema.json and skill-contract-v3.schema.json are byte-identical."),
        _gap("POSTGRESQL_RLS_NOT_IMPLEMENTED", "DECLARED_GAP", "The SQL design has no ENABLE ROW LEVEL SECURITY or CREATE POLICY statements."),
        _gap("LICENSE_TEXT_PLACEHOLDER", "BLOCKS_DISTRIBUTION", "LICENSE requires company-approved replacement legal text."),
        _gap("PACKAGE_SIGNATURE_MISSING", "NOT_PROVIDED", "No package-level detached signature or trusted signing bundle is present."),
        _gap("SBOM_MISSING", "NOT_PROVIDED", "No package-level SPDX or CycloneDX SBOM is present."),
        _gap("PROVENANCE_ATTESTATION_MISSING", "NOT_PROVIDED", "No package-level provenance attestation is present."),
        _gap(
            "SOURCE_PACKAGE_RUNTIME_IMPLEMENTATION_ABSENT",
            "SOURCE_DECLARED_ABSENT",
            "All 1,310 conformance manifests state that the source package itself has no runtime implementation; repository-owned exact handlers are tracked separately by capability_states.",
        ),
        _gap("TECHNOLOGY_MATRIX_VERSION_TUPLES_ABSENT", "CATALOG_ONLY", "The matrix has adapter names but no exact version or execution-evidence tuples."),
    ]
    package_report: dict[str, Any] = {
        "schema_version": "elmos.knowledge-skill-model-foundry.package-report.v1",
        "package": package,
        "validation_state": "STRUCTURAL_VALIDATED_WITH_DECLARED_GAPS",
        "source_execution": "NEVER_EXECUTED",
        "authority": compiled_catalog["authority"],
        "archive": {
            "entries": archive_metrics.entries,
            "files": archive_metrics.files,
            "directories": archive_metrics.directories,
            "controlled_files": archive_metrics.controlled_files,
            "compressed_member_bytes": archive_metrics.compressed_member_bytes,
            "uncompressed_bytes": archive_metrics.uncompressed_bytes,
            "maximum_member_compression_ratio": round(archive_metrics.maximum_member_compression_ratio, 6),
            "crc_status": "PASS",
            "executable_files": list(archive_metrics.executable_files),
        },
        "counts": {
            "atomic_skills": len(atomic_skills),
            "meta_skills": len(meta_skills),
            "packs": len(packs),
            "schemas": supporting["schema_count"],
            "policies": supporting["policy_count"],
            "pipelines": supporting["pipeline_count"],
            "pipeline_steps": supporting["pipeline_steps"],
            "dependency_edges": dependency_edges,
            "business_lines": supporting["business_lines"],
            "postgresql_tables": supporting["postgresql_tables"],
            "meta_activation_cases": meta_activation_cases,
        },
        "priority_counts": dict(sorted(priority_counts.items())),
        "risk_counts": dict(sorted(risk_counts.items())),
        "pack_counts": dict(sorted(pack_counts.items())),
        "evaluation_counts": {
            "positive": 10_480,
            "negative": 10_480,
            "ambiguous": 5_240,
            "adversarial": 5_240,
            "total": EXPECTED_EVALUATION_CASES,
        },
        "dependency_graph": {
            "unresolved": 0,
            "self_dependencies": 0,
            "cycles": 0,
            "edges": dependency_edges,
            "pack_graph_references": supporting["pack_graph_references"],
            "pack_graph_unique_references": supporting["pack_graph_unique_references"],
        },
        "profiles": supporting["profiles"],
        "meta_source_version_counts": dict(sorted(meta_version_counts.items())),
        "capability_states": {
            "PREPARE_ONLY": sum(skill["capability_state"] == "PREPARE_ONLY" for skill in atomic_skills),
            "LOCAL": sum(skill["capability_state"] == "LOCAL" for skill in atomic_skills),
        },
        "auxiliary_json_catalog": auxiliary,
        "external_evidence_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
        "gaps": gaps,
    }
    return AuditResult(
        archive_path=archive_path,
        archive_sha256=archive_sha256,
        archive_bytes=identity.byte_count,
        archive_metrics=archive_metrics,
        compiled_catalog=compiled_catalog,
        package_report=package_report,
    )


def _safe_wrapper_bytes(meta: Mapping[str, Any]) -> bytes:
    name = str(meta["name"])
    pack = str(meta["pack"])
    count = len(meta["candidates"])
    source_sha256 = str(meta["source_sha256"])
    return f"""---
name: {name}
description: Route the {pack} capability pack through the repository-owned compiled catalog using fail-closed PREPARE_ONLY bindings.
license: Proprietary-Elmos-Commercial
metadata:
  version: {PACKAGE_VERSION}
  pack: {pack}
  capability-state: PREPARE_ONLY
  external-evidence-status: NOT_RUN
  certification-status: NOT_CERTIFIED
  source-sha256: {source_sha256}
---

# {name}

This repository-owned wrapper exposes {count} catalog candidates. It contains
no copied source instructions and grants no provider, repository mutation,
production, signing, training, deployment, or certification authority.
""".encode("utf-8")


def generated_asset_bytes(
    result: AuditResult, *, include_meta_wrappers: bool = False
) -> dict[Path, bytes]:
    assets = {
        Path("compiled-catalog.json"): canonical_json_bytes(result.compiled_catalog),
        Path("package-report.json"): canonical_json_bytes(result.package_report),
    }
    if include_meta_wrappers:
        for meta in result.compiled_catalog["meta_skills"]:
            assets[Path("meta-skills") / str(meta["name"]) / "SKILL.md"] = _safe_wrapper_bytes(meta)
    return assets


def _catalog_directory(output_root: Path) -> tuple[Path, Path]:
    _require(not output_root.is_symlink(), f"output root must not be a symlink: {output_root}")
    resolved_root = output_root.resolve()
    catalog_dir = resolved_root / CATALOG_RELATIVE
    _require(catalog_dir.is_relative_to(resolved_root), f"generated catalog escapes output root: {catalog_dir}")
    if catalog_dir.exists() or catalog_dir.is_symlink():
        _require(
            catalog_dir.is_dir() and not catalog_dir.is_symlink(),
            f"generated catalog directory collision: {catalog_dir}",
        )
    return resolved_root, catalog_dir


def _preflight_generated_targets(
    catalog_dir: Path, assets: Mapping[Path, bytes]
) -> tuple[int, int]:
    new_count = 0
    identical_count = 0
    for relative, expected in sorted(assets.items(), key=lambda item: item[0].as_posix()):
        _require(not relative.is_absolute() and ".." not in relative.parts, f"unsafe generated path: {relative}")
        target = catalog_dir / relative
        current = catalog_dir
        for part in relative.parts[:-1]:
            current = current / part
            if current.exists() or current.is_symlink():
                _require(current.is_dir() and not current.is_symlink(), f"generated directory collision: {current}")
        if target.exists() or target.is_symlink():
            _require(target.is_file() and not target.is_symlink(), f"generated target collision: {target}")
            _require(target.read_bytes() == expected, f"refusing to overwrite changed generated asset: {target}")
            identical_count += 1
        else:
            new_count += 1
    return new_count, identical_count


def write_generated_assets(
    result: AuditResult,
    output_root: Path,
    *,
    include_meta_wrappers: bool = False,
) -> dict[str, Any]:
    """Create deterministic assets without overwriting or removing anything."""
    resolved_root, catalog_dir = _catalog_directory(output_root)
    assets = generated_asset_bytes(result, include_meta_wrappers=include_meta_wrappers)
    new_count, identical_count = _preflight_generated_targets(catalog_dir, assets)
    resolved_root.mkdir(parents=True, exist_ok=True)
    catalog_dir.mkdir(parents=True, exist_ok=True)
    for relative, data in sorted(assets.items(), key=lambda item: item[0].as_posix()):
        target = catalog_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            continue
        try:
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            fail(f"generated target appeared after preflight: {target}")
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    return {
        "status": "GENERATED" if new_count else "ALREADY_IDENTICAL",
        "catalog_directory": catalog_dir.as_posix(),
        "created": new_count,
        "existing_identical": identical_count,
        "assets": sorted(path.as_posix() for path in assets),
    }


def verify_generated_assets(result: AuditResult, output_root: Path) -> dict[str, Any]:
    """Read-only verification of generated assets when any are present."""
    _, catalog_dir = _catalog_directory(output_root)
    compiled_path = catalog_dir / "compiled-catalog.json"
    report_path = catalog_dir / "package-report.json"
    wrappers_dir = catalog_dir / "meta-skills"
    any_present = any(path.exists() or path.is_symlink() for path in (compiled_path, report_path, wrappers_dir))
    if not any_present:
        return {"status": "ABSENT", "verified": 0}
    _require(compiled_path.is_file() and not compiled_path.is_symlink(), "compiled-catalog.json missing or unsafe")
    _require(report_path.is_file() and not report_path.is_symlink(), "package-report.json missing or unsafe")
    expected_base = generated_asset_bytes(result)
    _require(compiled_path.read_bytes() == expected_base[Path("compiled-catalog.json")], "compiled-catalog.json drift")
    _require(report_path.read_bytes() == expected_base[Path("package-report.json")], "package-report.json drift")
    verified = 2
    wrapper_status = "ABSENT"
    if wrappers_dir.exists() or wrappers_dir.is_symlink():
        _require(wrappers_dir.is_dir() and not wrappers_dir.is_symlink(), "meta-skills wrapper path is unsafe")
        expected_wrappers = {
            relative: data
            for relative, data in generated_asset_bytes(result, include_meta_wrappers=True).items()
            if relative.parts[0] == "meta-skills"
        }
        observed_files = {
            path.relative_to(catalog_dir)
            for path in wrappers_dir.rglob("*")
            if path.is_file()
        }
        _require(observed_files == set(expected_wrappers), "meta wrapper inventory drift")
        for relative, expected in expected_wrappers.items():
            path = catalog_dir / relative
            _require(not path.is_symlink() and path.read_bytes() == expected, f"meta wrapper drift: {relative}")
        verified += len(expected_wrappers)
        wrapper_status = "VERIFIED"
    return {"status": "VERIFIED", "verified": verified, "meta_wrappers": wrapper_status}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="read-only direct ZIP validation")
    mode.add_argument("--write", action="store_true", help="write deterministic compiled assets only")
    parser.add_argument("--archive", type=Path, help="archive path; defaults to the pinned repository path")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT,
        help="repository or staging root under which engines/.../catalog is addressed",
    )
    parser.add_argument(
        "--include-meta-wrappers",
        action="store_true",
        help="also generate 41 normalized PREPARE_ONLY meta wrappers",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        archive = args.archive.resolve() if args.archive else resolve_archive()
        result = audit_archive(archive)
        write_result: Mapping[str, Any] | None = None
        if args.write:
            write_result = write_generated_assets(
                result, args.output_root, include_meta_wrappers=args.include_meta_wrappers
            )
            generated = verify_generated_assets(result, args.output_root)
        else:
            generated = verify_generated_assets(result, args.output_root)
        response: dict[str, Any] = {
            "status": "PASS",
            "mode": "CHECK" if args.check else "WRITE",
            "package": PACKAGE_ID,
            "archive_sha256": result.archive_sha256,
            "atomic_skills": len(result.compiled_catalog["atomic_skills"]),
            "meta_skills": len(result.compiled_catalog["meta_skills"]),
            "source_execution": "NEVER_EXECUTED",
            "generated_assets": generated,
            "external_evidence_status": "NOT_RUN",
            "certification_status": "NOT_CERTIFIED",
        }
        if write_result is not None:
            response["write"] = write_result
        print(json.dumps(response, ensure_ascii=False, sort_keys=True))
        return 0
    except (IntegrationError, zipfile.BadZipFile, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
