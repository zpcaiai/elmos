#!/usr/bin/env python3
"""Safely integrate the pinned Elmos pricing and billing Skill package.

The supplied ZIP is immutable, untrusted input.  This importer reads it with
the Python standard library, validates the complete archive and package
contracts, and never imports or executes any code from the package.

Generated source files preserve the archive byte-for-byte.  Installed Skill
copies are repository-owned normalizations: their Codex frontmatter, package
namespace, provenance, evidence boundaries, and UI metadata are deterministic.
"""

from __future__ import annotations

import argparse
import csv
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
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]

PACKAGE_ID = "elmos-pricing-billing-skills"
PACKAGE_VERSION = "1.0.0"
ARCHIVE_ROOT = f"{PACKAGE_ID}-v{PACKAGE_VERSION}"
ARCHIVE_RELATIVE = Path("skills/subskills") / f"{ARCHIVE_ROOT}.zip"
ARCHIVE_SHA256 = "9f7440b69a82a52172a1f62da915d96cfa4e0326dc04a305603c76001c8e88bc"
ARCHIVE_BYTES = 246_184
EXPECTED_ENTRY_COUNT = 130
EXPECTED_UNCOMPRESSED_BYTES = 513_164
EXPECTED_INTERNAL_CHECKSUMS = 129
EXPECTED_CONTROLLED_FILES = 128
EXPECTED_MODE_COUNTS = {0o644: 122, 0o755: 8}
EXPECTED_SKILL_COUNT = 18
EXPECTED_BATCH_COUNT = 54
EXPECTED_REQUIREMENT_COUNT = 180
EXPECTED_SCENARIO_COUNT = 50
EXPECTED_EXECUTABLE_REFERENCE_TESTS = 4
MAX_ENTRY_BYTES = 128 * 1024
MAX_COMPRESSION_RATIO = 100
MAX_SKILL_NAME_LENGTH = 64

PACKAGE_NAMESPACE = "elmos.pricing-billing.v1"
SOURCE_RELATIVE = Path("skills") / ARCHIVE_ROOT
DOC_RELATIVE = Path("docs/pricing-billing-skills")
SUPPORT_RELATIVE = Path(".elmos-billing-kit")
INSTALL_ROOTS = (Path(".agents/skills"), Path("agent-skills/runtime"))

SUPPORT_SOURCE_DIRECTORIES = (
    "docs",
    "schemas",
    "policies",
    "manifests",
    "tests",
    "templates",
    "examples",
    "tools",
)
SUPPORT_SOURCE_FILES = (
    "README.md",
    "SKILL_INDEX.md",
    "BATCH_INDEX.md",
    "IMPLEMENTATION_CHECKLIST.md",
    "CODEX_IMPLEMENTATION_PROMPT.md",
    "CLAUDE_CODE_IMPLEMENTATION_PROMPT.md",
    "PACKAGE_MANIFEST.json",
    "VALIDATION_REPORT.md",
    "VERSION",
)

INSTALL_STATE = "INSTALLED"
GUIDANCE_STATE = "GUIDANCE_IMPORTED"
RUNTIME_IMPLEMENTATION_STATE = "LOCAL_REFERENCE_BOUND"
RUNTIME_EVIDENCE_STATE = "NOT_RUN"
EXTERNAL_EVIDENCE_STATE = "NOT_RUN"
CERTIFICATION_STATE = "NOT_CERTIFIED"
MAXIMUM_LOCAL_CLAIM = "BOUNDED_LOCAL_REFERENCE_IMPLEMENTATION"
RUNTIME_BINDING_RELATIVE = (
    Path("verification-packs") / "pricing-billing-local-v1" / "runtime-binding.json"
)
ARCHIVE_DIGEST_SCOPE = "BYTE_IDENTITY_ONLY"
SOURCE_ATTESTATION_STATE = "NOT_PROVIDED"
ARCHIVE_IDENTITY_NOTICE = (
    "The user-supplied pinned SHA-256 proves byte identity only; it does not "
    "establish authorship, signature, SBOM, or provenance attestation."
)

EXPECTED_SKILL_NAMES = (
    "elmos-billing-orchestrator",
    "elmos-pricing-product-model",
    "elmos-plan-catalog-entitlements",
    "elmos-credit-wallet-ledger",
    "elmos-usage-metering",
    "elmos-task-cost-estimation",
    "elmos-quote-budget-guard",
    "elmos-project-pricing-contracts",
    "elmos-subscription-invoicing",
    "elmos-payments-reconciliation",
    "elmos-refunds-disputes",
    "elmos-enterprise-byok",
    "elmos-cost-margin-analytics",
    "elmos-billing-admin-ux",
    "elmos-security-compliance",
    "elmos-billing-observability-ops",
    "elmos-billing-testing-certification",
    "elmos-rollout-migration",
)

TRACEABILITY_HEADER = (
    "requirement_id",
    "priority",
    "skill",
    "batch",
    "statement",
    "status",
    "source_files",
    "symbols",
    "tests",
    "runtime_evidence",
    "commit",
    "owner",
    "notes",
)

REQUIRED_SKILL_SECTIONS = (
    "## Objective",
    "## Trigger boundaries",
    "## Inputs",
    "## Outputs",
    "## Workflow",
    "## Hard invariants",
    "## Required tests",
    "## Evidence contract",
    "## Definition of Done",
    "## Stop and escalate",
    "## Completion report",
    "## Assigned batches",
)


class IntegrationError(RuntimeError):
    """A pinned-source, safety, identity, collision, or drift check failed."""


@dataclass(frozen=True)
class FilePayload:
    content: bytes
    mode: int = 0o644


@dataclass(frozen=True)
class SkillRecord:
    name: str
    title: str
    description: str
    depends_on: tuple[str, ...]
    batches: tuple[str, ...]
    requirement_ids: tuple[str, ...]
    source_skill_sha256: str
    source_tree_sha256: str


@dataclass(frozen=True)
class BatchRecord:
    source_id: str
    title: str
    skill: str
    depends_on: tuple[str, ...]
    requirement_ids: tuple[str, ...]


@dataclass(frozen=True)
class PackageSnapshot:
    archive_bytes: bytes
    archive_sha256: str
    files: Mapping[str, FilePayload]
    file_sha256: Mapping[str, str]
    skills: tuple[SkillRecord, ...]
    batches: tuple[BatchRecord, ...]
    requirement_priority_counts: Mapping[str, int]
    requirement_status_counts: Mapping[str, int]
    scenario_priority_counts: Mapping[str, int]
    internal_checksum_count: int
    controlled_file_count: int
    executable_reference_tests: int


@dataclass(frozen=True)
class ManagedTree:
    relative_root: Path
    files: Mapping[str, FilePayload]


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _decode_utf8(value: bytes, label: str) -> str:
    try:
        result = value.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise IntegrationError(f"{label}: not strict UTF-8") from exc
    if "\x00" in result:
        raise IntegrationError(f"{label}: contains NUL")
    return result


def _strict_json(value: bytes, label: str) -> Any:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise IntegrationError(f"{label}: duplicate JSON key {key!r}")
            result[key] = item
        return result

    def reject_constant(token: str) -> None:
        raise IntegrationError(f"{label}: non-finite JSON number {token!r}")

    try:
        return json.loads(
            _decode_utf8(value, label),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise IntegrationError(f"{label}: invalid JSON") from exc


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _safe_relative_name(value: str, label: str) -> PurePosixPath:
    if (
        not value
        or "\x00" in value
        or "\\" in value
        or any(ord(character) < 32 for character in value)
    ):
        raise IntegrationError(f"{label}: unsafe path {value!r}")
    if unicodedata.normalize("NFC", value) != value:
        raise IntegrationError(f"{label}: path is not NFC-normalized: {value!r}")
    if value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        raise IntegrationError(f"{label}: absolute or drive-like path {value!r}")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise IntegrationError(f"{label}: ambiguous path {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute():
        raise IntegrationError(f"{label}: absolute path {value!r}")
    return path


def _safe_archive_name(value: str) -> PurePosixPath:
    path = _safe_relative_name(value, "archive member")
    if not path.parts or path.parts[0] != ARCHIVE_ROOT or len(path.parts) == 1:
        raise IntegrationError(f"archive member escapes expected root: {value!r}")
    return path


def _read_archive(
    archive_path: Path,
    *,
    expected_sha256: str | None,
    expected_archive_bytes: int | None,
) -> bytes:
    try:
        size = archive_path.stat().st_size
    except FileNotFoundError as exc:
        raise IntegrationError(f"source archive is missing: {archive_path}") from exc
    if not archive_path.is_file() or archive_path.is_symlink():
        raise IntegrationError(f"source archive must be a regular file: {archive_path}")
    if expected_archive_bytes is not None and size != expected_archive_bytes:
        raise IntegrationError(
            f"archive byte count mismatch: expected {expected_archive_bytes}, got {size}"
        )
    if size > 2 * 1024 * 1024:
        raise IntegrationError(f"archive exceeds hard safety bound: {size} bytes")
    value = archive_path.read_bytes()
    observed = _sha256(value)
    if expected_sha256 is not None and observed != expected_sha256:
        raise IntegrationError(
            f"archive SHA-256 mismatch: expected {expected_sha256}, got {observed}"
        )
    return value


def _validate_central_directory(
    archive: zipfile.ZipFile,
    *,
    expected_entries: int = EXPECTED_ENTRY_COUNT,
    expected_uncompressed_bytes: int = EXPECTED_UNCOMPRESSED_BYTES,
) -> tuple[zipfile.ZipInfo, ...]:
    infos = tuple(archive.infolist())
    names = [item.filename for item in infos]
    duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
    if duplicates:
        raise IntegrationError(f"duplicate archive members: {duplicates}")

    collision_names: dict[str, str] = {}
    total = 0
    mode_counts: Counter[int] = Counter()
    for info in infos:
        path = _safe_archive_name(info.filename)
        collision_key = unicodedata.normalize("NFC", path.as_posix()).casefold()
        prior = collision_names.get(collision_key)
        if prior is not None:
            raise IntegrationError(
                f"case/Unicode archive path collision: {prior!r}, {info.filename!r}"
            )
        collision_names[collision_key] = info.filename
        if info.flag_bits & 0x1:
            raise IntegrationError(f"encrypted archive entry: {info.filename!r}")
        if info.is_dir():
            raise IntegrationError(f"unexpected directory entry: {info.filename!r}")
        unix_mode = (info.external_attr >> 16) & 0xFFFF
        file_type = stat.S_IFMT(unix_mode)
        if file_type == stat.S_IFLNK:
            raise IntegrationError(f"symbolic link archive entry: {info.filename!r}")
        if file_type not in (0, stat.S_IFREG):
            raise IntegrationError(f"special archive entry: {info.filename!r}")
        mode = stat.S_IMODE(unix_mode) or 0o644
        if mode not in {0o644, 0o755}:
            raise IntegrationError(
                f"unexpected archive member mode {mode:o}: {info.filename!r}"
            )
        mode_counts[mode] += 1
        if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
            raise IntegrationError(f"unsupported compression: {info.filename!r}")
        if info.file_size < 0 or info.compress_size < 0:
            raise IntegrationError(f"negative archive size: {info.filename!r}")
        if info.file_size > MAX_ENTRY_BYTES:
            raise IntegrationError(f"archive member exceeds byte bound: {info.filename!r}")
        if info.file_size and not info.compress_size:
            raise IntegrationError(f"invalid zero compressed size: {info.filename!r}")
        if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
            raise IntegrationError(f"compression ratio exceeds bound: {info.filename!r}")
        total += info.file_size

    if len(infos) != expected_entries:
        raise IntegrationError(
            f"archive entry count mismatch: expected {expected_entries}, got {len(infos)}"
        )
    if total != expected_uncompressed_bytes:
        raise IntegrationError(
            "archive uncompressed-byte mismatch: "
            f"expected {expected_uncompressed_bytes}, got {total}"
        )
    if dict(mode_counts) != EXPECTED_MODE_COUNTS:
        raise IntegrationError(
            f"archive mode inventory mismatch: expected {EXPECTED_MODE_COUNTS}, "
            f"got {dict(mode_counts)}"
        )
    return infos


def _read_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    observed = 0
    chunks: list[bytes] = []
    with archive.open(info, "r") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            observed += len(chunk)
            if observed > info.file_size:
                raise IntegrationError(f"member exceeds declared size: {info.filename!r}")
            chunks.append(chunk)
    if observed != info.file_size:
        raise IntegrationError(
            f"member size mismatch for {info.filename!r}: {observed} != {info.file_size}"
        )
    return b"".join(chunks)


def _parse_checksums(
    files: Mapping[str, FilePayload],
) -> tuple[dict[str, str], int]:
    checksum_name = "CHECKSUMS.sha256"
    payload = files.get(checksum_name)
    if payload is None:
        raise IntegrationError("archive is missing CHECKSUMS.sha256")
    rows: dict[str, str] = {}
    pattern = re.compile(r"^([0-9a-f]{64})  (.+)$")
    for line_number, line in enumerate(
        _decode_utf8(payload.content, checksum_name).splitlines(), 1
    ):
        match = pattern.fullmatch(line)
        if match is None:
            raise IntegrationError(f"{checksum_name}:{line_number}: malformed row")
        expected, relative = match.groups()
        _safe_relative_name(relative, f"{checksum_name}:{line_number}")
        if relative in rows:
            raise IntegrationError(f"{checksum_name}: duplicate path {relative!r}")
        rows[relative] = expected
    expected_paths = set(files) - {checksum_name}
    if len(rows) != EXPECTED_INTERNAL_CHECKSUMS or set(rows) != expected_paths:
        raise IntegrationError(
            "internal checksum coverage mismatch: "
            f"count={len(rows)} missing={sorted(expected_paths - set(rows))} "
            f"extra={sorted(set(rows) - expected_paths)}"
        )
    for relative, expected in rows.items():
        observed = _sha256(files[relative].content)
        if observed != expected:
            raise IntegrationError(f"internal checksum mismatch: {relative}")
    return rows, len(rows)


def _validate_controlled_files(files: Mapping[str, FilePayload]) -> int:
    relative = "manifests/controlled-files.json"
    value = _strict_json(files[relative].content, relative)
    if not isinstance(value, dict):
        raise IntegrationError(f"{relative}: root must be an object")
    rows = value.get("files")
    if (
        value.get("schema_version") != "1.0"
        or value.get("package") != ARCHIVE_ROOT
        or not isinstance(rows, list)
        or len(rows) != EXPECTED_CONTROLLED_FILES
    ):
        raise IntegrationError(f"{relative}: package identity or count mismatch")
    observed_paths: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {"path", "sha256", "size"}:
            raise IntegrationError(f"{relative}: invalid row {index}")
        path = row.get("path")
        digest = row.get("sha256")
        size = row.get("size")
        if not isinstance(path, str):
            raise IntegrationError(f"{relative}: non-string path at row {index}")
        _safe_relative_name(path, f"{relative}:{index}")
        if path in observed_paths:
            raise IntegrationError(f"{relative}: duplicate path {path!r}")
        observed_paths.add(path)
        payload = files.get(path)
        if payload is None:
            raise IntegrationError(f"{relative}: missing controlled file {path!r}")
        if (
            not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or digest != _sha256(payload.content)
            or size != len(payload.content)
        ):
            raise IntegrationError(f"{relative}: digest/size mismatch for {path!r}")
    expected = set(files) - {"CHECKSUMS.sha256", relative}
    if observed_paths != expected:
        raise IntegrationError(
            f"{relative}: coverage mismatch missing={sorted(expected - observed_paths)} "
            f"extra={sorted(observed_paths - expected)}"
        )
    return len(rows)


def _parse_frontmatter(value: bytes, label: str) -> tuple[dict[str, str], str]:
    text = _decode_utf8(value, label)
    match = re.match(r"\A---\r?\n(.*?)\r?\n---\r?\n", text, re.DOTALL)
    if match is None:
        raise IntegrationError(f"{label}: missing or malformed frontmatter")
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line or line.startswith(" ") or ":" not in line:
            continue
        key, raw = line.split(":", 1)
        if key in fields:
            raise IntegrationError(f"{label}: duplicate frontmatter key {key!r}")
        value_text = raw.strip()
        if value_text.startswith('"'):
            try:
                scalar = json.loads(value_text)
            except json.JSONDecodeError as exc:
                raise IntegrationError(f"{label}: invalid quoted frontmatter") from exc
            if not isinstance(scalar, str):
                raise IntegrationError(f"{label}: frontmatter scalar is not a string")
            fields[key] = scalar
        else:
            fields[key] = value_text
    return fields, text[match.end() :]


def _validate_dag(graph: Mapping[str, Sequence[str]], label: str) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str, trail: tuple[str, ...]) -> None:
        if node in visited:
            return
        if node in visiting:
            raise IntegrationError(f"cycle in {label} DAG: {' -> '.join((*trail, node))}")
        visiting.add(node)
        for dependency in graph[node]:
            if dependency not in graph:
                raise IntegrationError(
                    f"unknown {label} dependency {dependency!r} referenced by {node!r}"
                )
            visit(dependency, (*trail, node))
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node, ())


def _tree_digest(files: Mapping[str, FilePayload]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(files):
        payload = files[relative]
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(f"{payload.mode:o}".encode("ascii"))
        digest.update(b"\0")
        digest.update(str(len(payload.content)).encode("ascii"))
        digest.update(b"\0")
        digest.update(_sha256(payload.content).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _validate_package_contracts(
    files: Mapping[str, FilePayload],
) -> tuple[
    tuple[SkillRecord, ...],
    tuple[BatchRecord, ...],
    Mapping[str, int],
    Mapping[str, int],
    Mapping[str, int],
    int,
]:
    manifest = _strict_json(files["MANIFEST.json"].content, "MANIFEST.json")
    package_manifest = _strict_json(
        files["PACKAGE_MANIFEST.json"].content, "PACKAGE_MANIFEST.json"
    )
    if manifest != package_manifest:
        raise IntegrationError("MANIFEST.json and PACKAGE_MANIFEST.json differ")
    expected_counts = {
        "skills": EXPECTED_SKILL_COUNT,
        "batches": EXPECTED_BATCH_COUNT,
        "requirements": EXPECTED_REQUIREMENT_COUNT,
        "test_scenarios": EXPECTED_SCENARIO_COUNT,
    }
    if (
        not isinstance(manifest, dict)
        or manifest.get("name") != PACKAGE_ID
        or manifest.get("version") != PACKAGE_VERSION
        or manifest.get("counts") != expected_counts
        or manifest.get("entry_skill") != "elmos-billing-orchestrator"
    ):
        raise IntegrationError("package manifest identity or declared counts differ")
    if _decode_utf8(files["VERSION"].content, "VERSION").strip() != PACKAGE_VERSION:
        raise IntegrationError("VERSION differs from the package manifest")

    skills_value = _strict_json(
        files["manifests/skills.manifest.json"].content,
        "manifests/skills.manifest.json",
    )
    if (
        not isinstance(skills_value, dict)
        or skills_value.get("package") != PACKAGE_ID
        or skills_value.get("version") != PACKAGE_VERSION
        or skills_value.get("schema_version") != "1.0"
        or not isinstance(skills_value.get("skills"), list)
    ):
        raise IntegrationError("skills manifest identity is invalid")
    raw_skills = skills_value["skills"]
    names = tuple(item.get("name") for item in raw_skills if isinstance(item, dict))
    if names != EXPECTED_SKILL_NAMES:
        raise IntegrationError(f"Skill name/order drift: {names!r}")

    expected_skill_files = {
        relative
        for name in EXPECTED_SKILL_NAMES
        for relative in (
            f"skills/{name}/SKILL.md",
            f"skills/{name}/references/REQUIREMENTS.md",
            f"skills/{name}/assets/COMPLETION-REPORT.md",
        )
    }
    observed_skill_files = {path for path in files if path.startswith("skills/")}
    if observed_skill_files != expected_skill_files:
        raise IntegrationError(
            "Skill payload shape mismatch: "
            f"missing={sorted(expected_skill_files - observed_skill_files)} "
            f"extra={sorted(observed_skill_files - expected_skill_files)}"
        )

    batches_value = _strict_json(
        files["manifests/batches.manifest.json"].content,
        "manifests/batches.manifest.json",
    )
    if (
        not isinstance(batches_value, dict)
        or batches_value.get("package") != PACKAGE_ID
        or batches_value.get("version") != PACKAGE_VERSION
        or batches_value.get("schema_version") != "1.0"
        or not isinstance(batches_value.get("batches"), list)
    ):
        raise IntegrationError("batches manifest identity is invalid")
    raw_batches = batches_value["batches"]
    expected_batch_ids = tuple(f"B{index:02d}" for index in range(EXPECTED_BATCH_COUNT))
    observed_batch_ids = tuple(
        item.get("id") for item in raw_batches if isinstance(item, dict)
    )
    if observed_batch_ids != expected_batch_ids:
        raise IntegrationError("batch IDs must be exactly ordered B00-B53")

    trace_text = _decode_utf8(
        files["manifests/requirements.traceability.csv"].content,
        "manifests/requirements.traceability.csv",
    )
    reader = csv.DictReader(io.StringIO(trace_text, newline=""))
    if tuple(reader.fieldnames or ()) != TRACEABILITY_HEADER:
        raise IntegrationError("traceability CSV header differs")
    trace_rows = list(reader)
    if len(trace_rows) != EXPECTED_REQUIREMENT_COUNT:
        raise IntegrationError("traceability requirement count differs")
    requirement_ids = [row["requirement_id"] for row in trace_rows]
    if len(set(requirement_ids)) != EXPECTED_REQUIREMENT_COUNT:
        raise IntegrationError("traceability requirement IDs are not unique")
    priority_counts = Counter(row["priority"] for row in trace_rows)
    status_counts = Counter(row["status"] for row in trace_rows)
    if dict(priority_counts) != {"P0": 108, "P1": 72}:
        raise IntegrationError(f"requirement priority counts differ: {priority_counts}")
    if dict(status_counts) != {"MISSING": EXPECTED_REQUIREMENT_COUNT}:
        raise IntegrationError(f"initial requirement statuses differ: {status_counts}")

    skill_graph: dict[str, tuple[str, ...]] = {}
    manifest_requirement_ids: set[str] = set()
    manifest_batch_ids: set[str] = set()
    skills: list[SkillRecord] = []
    for raw in raw_skills:
        if not isinstance(raw, dict):
            raise IntegrationError("skills manifest contains a non-object entry")
        name = raw.get("name")
        title = raw.get("title")
        description = raw.get("description")
        depends_on = raw.get("depends_on")
        batches = raw.get("batches")
        assigned_requirements = raw.get("requirement_ids")
        if (
            not isinstance(name, str)
            or re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) is None
            or len(name) > MAX_SKILL_NAME_LENGTH
            or not isinstance(title, str)
            or not isinstance(description, str)
            or not 1 <= len(description) <= 1024
            or not isinstance(depends_on, list)
            or not all(isinstance(item, str) for item in depends_on)
            or not isinstance(batches, list)
            or not all(isinstance(item, str) for item in batches)
            or not isinstance(assigned_requirements, list)
            or not all(isinstance(item, str) for item in assigned_requirements)
            or raw.get("path") != f"skills/{name}/SKILL.md"
        ):
            raise IntegrationError(f"invalid Skill manifest entry: {name!r}")
        if len(batches) != 3 or len(assigned_requirements) != 10:
            raise IntegrationError(f"{name}: batch/requirement cardinality differs")

        skill_relative = f"skills/{name}/SKILL.md"
        frontmatter, body = _parse_frontmatter(files[skill_relative].content, skill_relative)
        if frontmatter.get("name") != name or frontmatter.get("description") != description:
            raise IntegrationError(f"{name}: frontmatter and manifest identity differ")
        if len(body.splitlines()) > 500:
            raise IntegrationError(f"{name}: SKILL.md exceeds 500 lines")
        for section in REQUIRED_SKILL_SECTIONS:
            if section not in body:
                raise IntegrationError(f"{name}: missing required section {section}")
        for relative_link in re.findall(r"\]\(([^)]+)\)", body):
            if relative_link.startswith(("http://", "https://", "#")):
                continue
            link = _safe_relative_name(relative_link, f"{name} relative link")
            target = PurePosixPath("skills", name).joinpath(link)
            if target.as_posix() not in files:
                raise IntegrationError(f"{name}: broken relative link {relative_link!r}")

        requirement_doc = _decode_utf8(
            files[f"skills/{name}/references/REQUIREMENTS.md"].content,
            f"skills/{name}/references/REQUIREMENTS.md",
        )
        documented_ids = tuple(
            re.findall(r"^\| (EB-\d{2}-\d{3}) \|", requirement_doc, re.MULTILINE)
        )
        trace_for_skill = tuple(
            row["requirement_id"] for row in trace_rows if row["skill"] == name
        )
        if documented_ids != tuple(assigned_requirements) or trace_for_skill != tuple(
            assigned_requirements
        ):
            raise IntegrationError(f"{name}: requirement manifests differ")

        source_tree = {
            relative.removeprefix(f"skills/{name}/"): files[relative]
            for relative in expected_skill_files
            if relative.startswith(f"skills/{name}/")
        }
        skill_graph[name] = tuple(depends_on)
        manifest_requirement_ids.update(assigned_requirements)
        manifest_batch_ids.update(batches)
        skills.append(
            SkillRecord(
                name=name,
                title=title,
                description=description,
                depends_on=tuple(depends_on),
                batches=tuple(batches),
                requirement_ids=tuple(assigned_requirements),
                source_skill_sha256=_sha256(files[skill_relative].content),
                source_tree_sha256=_tree_digest(source_tree),
            )
        )

    _validate_dag(skill_graph, "Skill")
    if manifest_requirement_ids != set(requirement_ids):
        raise IntegrationError("Skill manifest and traceability requirements differ")
    if manifest_batch_ids != set(expected_batch_ids):
        raise IntegrationError("Skill manifest and batch IDs differ")

    batch_graph: dict[str, tuple[str, ...]] = {}
    batch_requirement_ids: set[str] = set()
    batches: list[BatchRecord] = []
    skill_by_name = {item.name: item for item in skills}
    for raw in raw_batches:
        if not isinstance(raw, dict):
            raise IntegrationError("batches manifest contains a non-object entry")
        source_id = raw.get("id")
        title = raw.get("title")
        skill_name = raw.get("skill")
        depends_on = raw.get("depends_on")
        assigned_requirements = raw.get("requirement_ids")
        if (
            not isinstance(source_id, str)
            or not isinstance(title, str)
            or skill_name not in skill_by_name
            or not isinstance(depends_on, list)
            or not all(isinstance(item, str) for item in depends_on)
            or not isinstance(assigned_requirements, list)
            or not all(isinstance(item, str) for item in assigned_requirements)
        ):
            raise IntegrationError(f"invalid batch manifest entry: {source_id!r}")
        if source_id not in skill_by_name[skill_name].batches:
            raise IntegrationError(f"{source_id}: owner Skill does not claim batch")
        trace_for_batch = {
            row["requirement_id"] for row in trace_rows if row["batch"] == source_id
        }
        if trace_for_batch != set(assigned_requirements):
            raise IntegrationError(f"{source_id}: requirement traceability differs")
        batch_graph[source_id] = tuple(depends_on)
        batch_requirement_ids.update(assigned_requirements)
        batches.append(
            BatchRecord(
                source_id=source_id,
                title=title,
                skill=skill_name,
                depends_on=tuple(depends_on),
                requirement_ids=tuple(assigned_requirements),
            )
        )
    _validate_dag(batch_graph, "batch")
    if batch_requirement_ids != set(requirement_ids):
        raise IntegrationError("batch and traceability requirements differ")

    scenario_text = _decode_utf8(
        files["tests/SCENARIO-MATRIX.md"].content, "tests/SCENARIO-MATRIX.md"
    )
    scenario_rows = re.findall(
        r"^\| (S\d{3}) \| (P[0-2]) \|", scenario_text, re.MULTILINE
    )
    expected_scenarios = [f"S{index:03d}" for index in range(1, 51)]
    if [row[0] for row in scenario_rows] != expected_scenarios:
        raise IntegrationError("scenario IDs must be exactly ordered S001-S050")
    scenario_priorities = Counter(row[1] for row in scenario_rows)
    if dict(scenario_priorities) != {"P0": 44, "P1": 6}:
        raise IntegrationError("scenario priority counts differ")

    reference_tests = _decode_utf8(
        files["tests/test_quote_reference.py"].content,
        "tests/test_quote_reference.py",
    )
    executable_reference_tests = len(
        re.findall(r"^    def test_[a-zA-Z0-9_]+\(", reference_tests, re.MULTILINE)
    )
    if executable_reference_tests != EXPECTED_EXECUTABLE_REFERENCE_TESTS:
        raise IntegrationError("executable reference test count differs")

    return (
        tuple(skills),
        tuple(batches),
        dict(priority_counts),
        dict(status_counts),
        dict(scenario_priorities),
        executable_reference_tests,
    )


def validate_archive(
    archive_path: Path,
    *,
    expected_sha256: str | None = ARCHIVE_SHA256,
    expected_archive_bytes: int | None = ARCHIVE_BYTES,
) -> PackageSnapshot:
    archive_bytes = _read_archive(
        archive_path,
        expected_sha256=expected_sha256,
        expected_archive_bytes=expected_archive_bytes,
    )
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes), "r")
    except zipfile.BadZipFile as exc:
        raise IntegrationError("source archive is not a valid ZIP") from exc

    with archive:
        infos = _validate_central_directory(archive)
        files: dict[str, FilePayload] = {}
        for info in infos:
            path = _safe_archive_name(info.filename)
            relative = PurePosixPath(*path.parts[1:]).as_posix()
            unix_mode = (info.external_attr >> 16) & 0xFFFF
            mode = stat.S_IMODE(unix_mode) or 0o644
            files[relative] = FilePayload(_read_member(archive, info), mode)

    checksum_rows, checksum_count = _parse_checksums(files)
    del checksum_rows
    controlled_count = _validate_controlled_files(files)
    (
        skills,
        batches,
        priority_counts,
        status_counts,
        scenario_priorities,
        executable_reference_tests,
    ) = _validate_package_contracts(files)
    return PackageSnapshot(
        archive_bytes=archive_bytes,
        archive_sha256=_sha256(archive_bytes),
        files=files,
        file_sha256={relative: _sha256(payload.content) for relative, payload in files.items()},
        skills=skills,
        batches=batches,
        requirement_priority_counts=priority_counts,
        requirement_status_counts=status_counts,
        scenario_priority_counts=scenario_priorities,
        internal_checksum_count=checksum_count,
        controlled_file_count=controlled_count,
        executable_reference_tests=executable_reference_tests,
    )


def _normalized_skill(snapshot: PackageSnapshot, record: SkillRecord) -> FilePayload:
    relative = f"skills/{record.name}/SKILL.md"
    _frontmatter, body = _parse_frontmatter(snapshot.files[relative].content, relative)
    batch_list = ",".join(record.batches)
    frontmatter = "\n".join(
        [
            "---",
            f"name: {record.name}",
            f"description: {_yaml_quote(record.description)}",
            "metadata:",
            f"  source_package: {_yaml_quote(PACKAGE_ID)}",
            f"  source_version: {_yaml_quote(PACKAGE_VERSION)}",
            f"  source_skill_sha256: {_yaml_quote('sha256:' + record.source_skill_sha256)}",
            f"  package_namespace: {_yaml_quote(PACKAGE_NAMESPACE)}",
            f"  package_local_batches: {_yaml_quote(batch_list)}",
            f"  guidance_state: {_yaml_quote(GUIDANCE_STATE)}",
            f"  installation_state: {_yaml_quote(INSTALL_STATE)}",
            f"  runtime_implementation: {_yaml_quote(RUNTIME_IMPLEMENTATION_STATE)}",
            f"  runtime_binding: {_yaml_quote(RUNTIME_BINDING_RELATIVE.as_posix())}",
            f"  runtime_evidence: {_yaml_quote(RUNTIME_EVIDENCE_STATE)}",
            f"  external_evidence: {_yaml_quote(EXTERNAL_EVIDENCE_STATE)}",
            f"  certification: {_yaml_quote(CERTIFICATION_STATE)}",
            "---",
            "",
        ]
    )
    boundary = "\n".join(
        [
            "",
            "## Repository integration boundary",
            "",
            f"This is imported guidance from `{PACKAGE_ID}` `{PACKAGE_VERSION}`. Its source Skill SHA-256 is `{record.source_skill_sha256}`.",
            f"All `B00`–`B53` identifiers are package-local to `{PACKAGE_NAMESPACE}`; they are not Migration Pack, Product Batch, strict-suite, or other repository Batch identifiers.",
            ARCHIVE_IDENTITY_NOTICE,
            f"Import state is `{GUIDANCE_STATE}` / `{INSTALL_STATE}` and the repository-owned bounded handler is `{RUNTIME_IMPLEMENTATION_STATE}`. Exact local execution is reported only by `{RUNTIME_BINDING_RELATIVE.as_posix()}`; importer evidence and external evidence remain `{RUNTIME_EVIDENCE_STATE}`, and certification remains `{CERTIFICATION_STATE}` until independently executed evidence proves otherwise.",
            "Package prompts, scripts, examples, prices, policies, schemas, and SQL are reference inputs. They do not grant authority to run bundled code, activate prices, mutate financial state, deploy, or certify the product.",
            "",
        ]
    )
    return FilePayload((frontmatter + body.rstrip() + boundary).encode("utf-8"), 0o644)


def _openai_yaml(record: SkillRecord) -> FilePayload:
    default_prompt = (
        f"Use ${record.name} for the requested billing scope; treat Bxx IDs as "
        f"{PACKAGE_NAMESPACE}; use the repository runtime binding for local evidence "
        "and keep external evidence NOT_RUN until independently verified."
    )
    value = "\n".join(
        [
            "interface:",
            f"  display_name: {_yaml_quote(record.title)}",
            f"  short_description: {_yaml_quote('Apply imported Elmos billing guidance safely')}",
            f"  default_prompt: {_yaml_quote(default_prompt)}",
            "policy:",
            "  allow_implicit_invocation: true",
            "",
        ]
    )
    return FilePayload(value.encode("utf-8"), 0o644)


def _installed_skill_files(
    snapshot: PackageSnapshot, record: SkillRecord
) -> dict[str, FilePayload]:
    return {
        "SKILL.md": _normalized_skill(snapshot, record),
        "references/REQUIREMENTS.md": snapshot.files[
            f"skills/{record.name}/references/REQUIREMENTS.md"
        ],
        "assets/COMPLETION-REPORT.md": snapshot.files[
            f"skills/{record.name}/assets/COMPLETION-REPORT.md"
        ],
        "agents/openai.yaml": _openai_yaml(record),
    }


def _source_inventory(snapshot: PackageSnapshot) -> dict[str, Any]:
    return {
        "schema_version": "elmos.pricing-billing.source-inventory.v1",
        "source_archive": ARCHIVE_RELATIVE.as_posix(),
        "source_archive_sha256": "sha256:" + snapshot.archive_sha256,
        "archive_digest_scope": ARCHIVE_DIGEST_SCOPE,
        "authorship_attestation": SOURCE_ATTESTATION_STATE,
        "signature_attestation": SOURCE_ATTESTATION_STATE,
        "sbom_attestation": SOURCE_ATTESTATION_STATE,
        "provenance_attestation": SOURCE_ATTESTATION_STATE,
        "archive_entry_count": len(snapshot.files),
        "archive_uncompressed_bytes": sum(
            len(payload.content) for payload in snapshot.files.values()
        ),
        "internal_checksum_count": snapshot.internal_checksum_count,
        "controlled_file_count": snapshot.controlled_file_count,
        "files": [
            {
                "path": relative,
                "bytes": len(snapshot.files[relative].content),
                "mode": f"{snapshot.files[relative].mode:o}",
                "sha256": "sha256:" + snapshot.file_sha256[relative],
            }
            for relative in sorted(snapshot.files)
        ],
    }


def _support_files(snapshot: PackageSnapshot) -> dict[str, FilePayload]:
    """Build the deterministic repository-local support tree.

    The upstream installer copies these directories and root files into
    ``.elmos-billing-kit``.  We reproduce that data layout without executing
    the installer, without timestamps or absolute paths, and with every source
    helper normalized to a non-executable mode.
    """

    selected: dict[str, FilePayload] = {}
    for relative, payload in snapshot.files.items():
        top = PurePosixPath(relative).parts[0]
        if top in SUPPORT_SOURCE_DIRECTORIES or relative in SUPPORT_SOURCE_FILES:
            selected[relative] = FilePayload(payload.content, 0o644)

    missing_directories = [
        directory
        for directory in SUPPORT_SOURCE_DIRECTORIES
        if not any(
            PurePosixPath(relative).parts[0] == directory for relative in selected
        )
    ]
    missing_files = [relative for relative in SUPPORT_SOURCE_FILES if relative not in selected]
    if missing_directories or missing_files:
        raise IntegrationError(
            "shared support source is incomplete: "
            f"directories={missing_directories} files={missing_files}"
        )

    selected_digest = _tree_digest(selected)
    selected["INTEGRATION_BOUNDARY.md"] = FilePayload(
        (
            "# Repository Integration Boundary\n\n"
            f"This support tree is generated from `{ARCHIVE_RELATIVE.as_posix()}` "
            f"at SHA-256 `{snapshot.archive_sha256}`.\n\n"
            "All content is imported guidance or reference data. Bundled Python, shell, "
            "SQL, CI, quote, installer, uninstaller, validator, and test files are not "
            "executed by the repository importer and are installed non-executable.\n\n"
            f"{ARCHIVE_IDENTITY_NOTICE}\n\n"
            f"Source `B00`-`B53` identifiers are package-local to `{PACKAGE_NAMESPACE}`. "
            f"Guidance is `{GUIDANCE_STATE}` and installed; the bounded repository handler "
            f"is `{RUNTIME_IMPLEMENTATION_STATE}` and is evidenced separately by "
            f"`{RUNTIME_BINDING_RELATIVE.as_posix()}`. External evidence remains "
            f"`{EXTERNAL_EVIDENCE_STATE}`, and production certification remains "
            f"`{CERTIFICATION_STATE}`.\n"
        ).encode("utf-8")
    )
    selected["install-manifest.json"] = FilePayload(
        _json_bytes(
            {
                "schema_version": "elmos.pricing-billing.support-install.v1",
                "package": PACKAGE_ID,
                "version": PACKAGE_VERSION,
                "source_archive": ARCHIVE_RELATIVE.as_posix(),
                "source_archive_sha256": snapshot.archive_sha256,
                "archive_digest_scope": ARCHIVE_DIGEST_SCOPE,
                "authorship_attestation": SOURCE_ATTESTATION_STATE,
                "signature_attestation": SOURCE_ATTESTATION_STATE,
                "sbom_attestation": SOURCE_ATTESTATION_STATE,
                "provenance_attestation": SOURCE_ATTESTATION_STATE,
                "shared_source_tree_sha256": "sha256:" + selected_digest,
                "support_root": SUPPORT_RELATIVE.as_posix(),
                "install_roots": [root.as_posix() for root in INSTALL_ROOTS],
                "skills": [record.name for record in snapshot.skills],
                "source_helpers_executed": False,
                "source_helpers_mode": "0644_NON_EXECUTABLE",
                "guidance_state": GUIDANCE_STATE,
                "installation_state": INSTALL_STATE,
                "runtime_implementation": RUNTIME_IMPLEMENTATION_STATE,
                "runtime_binding": RUNTIME_BINDING_RELATIVE.as_posix(),
                "runtime_evidence": RUNTIME_EVIDENCE_STATE,
                "external_evidence": EXTERNAL_EVIDENCE_STATE,
                "production_certification": CERTIFICATION_STATE,
            }
        )
    )
    return selected


def _overlap_map() -> dict[str, Any]:
    """Record semantic owners without merging any Batch namespace."""

    return {
        "schema_version": "elmos.pricing-billing.overlap-map.v1",
        "source_namespace": PACKAGE_NAMESPACE,
        "source_batch_range": "B00-B53",
        "resolution_policy": "REUSE_EXISTING_AUTHORITIES_AND_AVOID_PARALLEL_SYSTEMS",
        "activation_default": "guidance-only",
        "external_evidence_status": EXTERNAL_EVIDENCE_STATE,
        "production_certification": CERTIFICATION_STATE,
        "relationships": [
            {
                "authority_id": "product-b39-finance",
                "authority_namespace": "Product Batch B39 Finance",
                "authority_path": "docs/product-batches39-complete/skill-source-manifest.json",
                "authority_entry": "financial-billing-commercial-operations-orchestrator",
                "relationship": "semantic-overlap-reuse-authority",
                "overlapping_source_skills": list(EXPECTED_SKILL_NAMES),
                "boundary": (
                    "Product B39 remains the repository authority for financial, billing, "
                    "commercial, payment, reconciliation, finance analytics, and unit-economics "
                    "contracts. The imported package-local Bxx guidance must not supersede it."
                ),
            },
            {
                "authority_id": "product-b44-finops-economics",
                "authority_namespace": "Product Batch B44 FinOps and migration economics",
                "authority_path": "docs/batch44/AUTHORITY.md",
                "authority_entry": "Skills 1455-1474",
                "relationship": "semantic-overlap-reuse-authority",
                "overlapping_source_skills": [
                    "elmos-pricing-product-model",
                    "elmos-usage-metering",
                    "elmos-task-cost-estimation",
                    "elmos-quote-budget-guard",
                    "elmos-project-pricing-contracts",
                    "elmos-cost-margin-analytics",
                ],
                "boundary": (
                    "Product B44 remains authoritative for migration FinOps, metering, cost "
                    "allocation, pricing, quoting, margin, budget, ROI, TCO, and economics. "
                    "This identifier is not Precision Migration B44 or another B44 namespace."
                ),
            },
            {
                "authority_id": "product-batch56-reviewed-guidance",
                "authority_namespace": "Product Batch 56 reviewed-guidance overlay",
                "authority_path": "docs/product-closure-batch56/overlap-map.json",
                "authority_entry": (
                    "b56-commercial-product-edition-metering-billing-support-7d81f20f"
                ),
                "readiness_authority": (
                    "scripts/product-closure-batch56a/run_product_closure_gate.py"
                ),
                "relationship": "semantic-overlap-supplementary-guidance",
                "overlapping_source_skills": [
                    "elmos-plan-catalog-entitlements",
                    "elmos-usage-metering",
                    "elmos-subscription-invoicing",
                    "elmos-billing-observability-ops",
                    "elmos-rollout-migration",
                ],
                "boundary": (
                    "Product Batch 56 remains inactive supplementary guidance and Product 56A "
                    "remains readiness authority; this package cannot certify closure or GA."
                ),
            },
            {
                "authority_id": "current-commercial-billing-runtime",
                "authority_namespace": "ELMOS commercial implementation",
                "authority_paths": [
                    "modules/commercial-operations/src/main/java/io/elmos/commercial/PricingPlanCatalog.java",
                    "apps/commercial-api/src/main/java/io/elmos/commercialapi/SelfServiceBillingController.java",
                    "modules/persistence/src/main/resources/db/migration/V49__self_service_billing_and_usage.sql",
                    "modules/persistence/src/test/java/io/elmos/persistence/SelfServiceBillingMigrationContractTest.java",
                    "docs/tasks/self-service-billing/ARCHITECTURE.md",
                ],
                "relationship": "implementation-overlap-extend-in-place",
                "overlapping_source_skills": list(EXPECTED_SKILL_NAMES),
                "boundary": (
                    "Extend and validate the existing catalog, subscription, usage, payment, "
                    "reconciliation, tenant, and persistence contracts in place. Do not create "
                    "parallel ledgers, tenant authorities, payment state machines, or migration "
                    "histories, and never rewrite applied V49 migration history."
                ),
            },
        ],
    }


def _installed_manifest(
    snapshot: PackageSnapshot,
    installed_by_skill: Mapping[str, Mapping[str, FilePayload]],
    support_files: Mapping[str, FilePayload],
) -> dict[str, Any]:
    batch_rows = [
        {
            "source_id": batch.source_id,
            "qualified_id": f"{PACKAGE_NAMESPACE}/{batch.source_id}",
            "title": batch.title,
            "owner_skill": batch.skill,
            "source_dependencies": list(batch.depends_on),
            "qualified_dependencies": [
                f"{PACKAGE_NAMESPACE}/{dependency}" for dependency in batch.depends_on
            ],
            "requirement_ids": list(batch.requirement_ids),
        }
        for batch in snapshot.batches
    ]
    skill_rows: list[dict[str, Any]] = []
    for record in snapshot.skills:
        installed_files = installed_by_skill[record.name]
        skill_rows.append(
            {
                "source_name": record.name,
                "installed_name": record.name,
                "title": record.title,
                "source_path": f"{SOURCE_RELATIVE.as_posix()}/skills/{record.name}/SKILL.md",
                "source_skill_sha256": "sha256:" + record.source_skill_sha256,
                "source_tree_sha256": "sha256:" + record.source_tree_sha256,
                "installed_skill_sha256": "sha256:"
                + _sha256(installed_files["SKILL.md"].content),
                "installed_interface_sha256": "sha256:"
                + _sha256(installed_files["agents/openai.yaml"].content),
                "installed_tree_sha256": "sha256:" + _tree_digest(installed_files),
                "installed_paths": [
                    f"{root.as_posix()}/{record.name}" for root in INSTALL_ROOTS
                ],
                "source_dependencies": list(record.depends_on),
                "source_batches": list(record.batches),
                "qualified_batches": [
                    f"{PACKAGE_NAMESPACE}/{batch}" for batch in record.batches
                ],
                "requirement_ids": list(record.requirement_ids),
                "guidance_state": GUIDANCE_STATE,
                "installation_state": INSTALL_STATE,
                "runtime_implementation": RUNTIME_IMPLEMENTATION_STATE,
                "runtime_binding": RUNTIME_BINDING_RELATIVE.as_posix(),
                "runtime_evidence": RUNTIME_EVIDENCE_STATE,
                "external_evidence": EXTERNAL_EVIDENCE_STATE,
                "certification": CERTIFICATION_STATE,
            }
        )
    return {
        "schema_version": "elmos.pricing-billing.installed-manifest.v1",
        "source_archive_sha256": snapshot.archive_sha256,
        "skill_count": len(snapshot.skills),
        "requirement_count": sum(snapshot.requirement_priority_counts.values()),
        "external_evidence_status": EXTERNAL_EVIDENCE_STATE,
        "production_certification": CERTIFICATION_STATE,
        "package": {
            "source_name": PACKAGE_ID,
            "source_version": PACKAGE_VERSION,
            "source_archive": ARCHIVE_RELATIVE.as_posix(),
            "source_archive_sha256": "sha256:" + snapshot.archive_sha256,
            "archive_digest_scope": ARCHIVE_DIGEST_SCOPE,
            "authorship_attestation": SOURCE_ATTESTATION_STATE,
            "signature_attestation": SOURCE_ATTESTATION_STATE,
            "sbom_attestation": SOURCE_ATTESTATION_STATE,
            "provenance_attestation": SOURCE_ATTESTATION_STATE,
            "source_tree": SOURCE_RELATIVE.as_posix(),
            "source_tree_sha256": "sha256:" + _tree_digest(snapshot.files),
            "archive_entry_count": len(snapshot.files),
            "archive_uncompressed_bytes": sum(
                len(payload.content) for payload in snapshot.files.values()
            ),
            "internal_checksum_count": snapshot.internal_checksum_count,
            "controlled_file_count": snapshot.controlled_file_count,
        },
        "namespace": {
            "name": PACKAGE_NAMESPACE,
            "source_batch_range": "B00-B53",
            "collision_boundary": (
                "Package-local pricing/billing Bxx identifiers are never equivalent to "
                "Migration Packs, Product Batches, strict suites, or other repository namespaces."
            ),
        },
        "status": {
            "guidance": GUIDANCE_STATE,
            "installation": INSTALL_STATE,
            "runtime_implementation": RUNTIME_IMPLEMENTATION_STATE,
            "runtime_binding": RUNTIME_BINDING_RELATIVE.as_posix(),
            "runtime_evidence": RUNTIME_EVIDENCE_STATE,
            "external_evidence": EXTERNAL_EVIDENCE_STATE,
            "certification": CERTIFICATION_STATE,
            "production_ready": False,
            "maximum_local_claim": MAXIMUM_LOCAL_CLAIM,
        },
        "counts": {
            "skills": len(snapshot.skills),
            "batches": len(snapshot.batches),
            "requirements": sum(snapshot.requirement_priority_counts.values()),
            "requirement_priorities": dict(snapshot.requirement_priority_counts),
            "initial_requirement_statuses": dict(snapshot.requirement_status_counts),
            "documented_scenarios": sum(snapshot.scenario_priority_counts.values()),
            "scenario_priorities": dict(snapshot.scenario_priority_counts),
            "executable_reference_tests": snapshot.executable_reference_tests,
        },
        "install_roots": [root.as_posix() for root in INSTALL_ROOTS],
        "support_root": SUPPORT_RELATIVE.as_posix(),
        "support_tree_sha256": "sha256:" + _tree_digest(support_files),
        "dual_root_parity": "BYTE_AND_MODE_IDENTICAL",
        "source_scripts_executed_by_importer": False,
        "batches": batch_rows,
        "skills": skill_rows,
        "explicit_non_claims": [
            ARCHIVE_IDENTITY_NOTICE,
            "Source package validation was not used as runtime implementation evidence.",
            "No bundled install, uninstall, validate, quote, test, CI, or SQL code was executed.",
            "Draft prices, policies, schemas, and reference SQL were not activated.",
            "No payment, accounting, tax, legal, privacy, production, customer, or certification evidence was run.",
        ],
    }


def _repository_readme(snapshot: PackageSnapshot) -> bytes:
    names = "\n".join(f"- `${record.name}`" for record in snapshot.skills)
    value = f"""# Pricing and Billing Skill Integration

This directory records the repository-owned, fail-closed integration of
`{PACKAGE_ID}` `{PACKAGE_VERSION}`.

## Pinned source

- Archive: `{ARCHIVE_RELATIVE.as_posix()}`
- SHA-256: `{snapshot.archive_sha256}`
- Immutable extracted tree: `{SOURCE_RELATIVE.as_posix()}/`
- Inventory: `{EXPECTED_ENTRY_COUNT}` files and `{EXPECTED_UNCOMPRESSED_BYTES}` uncompressed bytes

{ARCHIVE_IDENTITY_NOTICE}

The importer treats the ZIP as untrusted data. It does not import or execute
the bundled shell, Python, test, CI, installer, uninstaller, validator, quote,
or SQL files.

## Installed state

- Guidance: `{GUIDANCE_STATE}`
- Installation: `{INSTALL_STATE}`
- Runtime implementation: `{RUNTIME_IMPLEMENTATION_STATE}`
- Runtime binding: `{RUNTIME_BINDING_RELATIVE.as_posix()}`
- Importer runtime evidence: `{RUNTIME_EVIDENCE_STATE}`
- External evidence: `{EXTERNAL_EVIDENCE_STATE}`
- Certification: `{CERTIFICATION_STATE}`
- Maximum local claim: `{MAXIMUM_LOCAL_CLAIM}`

All source `B00`–`B53` identifiers are qualified as
`{PACKAGE_NAMESPACE}/Bxx`. They do not name or update any other repository
Batch, Migration Pack, Product Batch, or test-suite result.

## Installed Skills

{names}

Each Skill is byte-and-mode identical in `.agents/skills/` and
`agent-skills/runtime/`. Installed `SKILL.md` files retain the source body but
use repository-compatible frontmatter and an explicit provenance/evidence
boundary. `agents/openai.yaml` provides deterministic UI metadata. The shared
support material referenced by those Skills is generated at
`.elmos-billing-kit/`; bundled helper files are present as non-executable data.

Semantic overlap and precedence for Product B39 Finance, Product B44 FinOps,
Product Batch 56, and the current commercial billing implementation are
recorded in `overlap-map.json`.

## Validation

```bash
python3 tooling/integrate_pricing_billing_skills.py --check
python3 tooling/validate_pricing_billing_installed.py
python3 -m unittest discover -s tests/pricing-billing-skills -p 'test_*.py' -v
```

`--write` is conflict-safe: an absent managed tree may be created and an exact
tree is a no-op, but a differing existing tree is never overwritten.
"""
    return value.encode("utf-8")


def build_managed_trees(snapshot: PackageSnapshot) -> tuple[ManagedTree, ...]:
    installed_by_skill = {
        record.name: _installed_skill_files(snapshot, record)
        for record in snapshot.skills
    }
    support_files = _support_files(snapshot)
    manifest = _installed_manifest(snapshot, installed_by_skill, support_files)
    docs = {
        "README.md": FilePayload(_repository_readme(snapshot)),
        "source-inventory.json": FilePayload(_json_bytes(_source_inventory(snapshot))),
        "installed-manifest.json": FilePayload(_json_bytes(manifest)),
        "overlap-map.json": FilePayload(_json_bytes(_overlap_map())),
    }
    trees: list[ManagedTree] = [ManagedTree(SOURCE_RELATIVE, snapshot.files)]
    for root in INSTALL_ROOTS:
        for record in snapshot.skills:
            trees.append(
                ManagedTree(root / record.name, installed_by_skill[record.name])
            )
    trees.append(ManagedTree(SUPPORT_RELATIVE, support_files))
    trees.append(ManagedTree(DOC_RELATIVE, docs))
    return tuple(trees)


def _expected_directories(files: Mapping[str, FilePayload]) -> set[str]:
    result: set[str] = set()
    for relative in files:
        parent = PurePosixPath(relative).parent
        while parent != PurePosixPath("."):
            result.add(parent.as_posix())
            parent = parent.parent
    return result


def _resolve_repository_root(repo_root: Path) -> Path:
    """Reject a lexical root symlink before resolving the real directory."""

    if repo_root.is_symlink():
        raise IntegrationError(f"repository root must not be a symlink: {repo_root}")
    root = repo_root.resolve()
    if not root.is_dir():
        raise IntegrationError(f"repository root must be a real directory: {repo_root}")
    return root


def _safe_output_root(repo_root: Path, relative: Path) -> Path:
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise IntegrationError(f"unsafe managed output path: {relative}")
    root = repo_root.resolve()
    candidate = root / relative
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise IntegrationError(f"managed output path contains symlink: {current}")
        if current.exists() and not current.is_dir() and current != candidate:
            raise IntegrationError(f"managed output parent is not a directory: {current}")
    try:
        candidate.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise IntegrationError(f"managed output escapes repository root: {relative}") from exc
    return candidate


def _check_tree(root: Path, files: Mapping[str, FilePayload]) -> None:
    if root.is_symlink() or not root.is_dir():
        raise IntegrationError(f"managed tree is missing or not a real directory: {root}")
    observed_files: dict[str, Path] = {}
    observed_directories: set[str] = set()
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise IntegrationError(f"symlink in managed tree: {path}")
        if path.is_dir():
            observed_directories.add(relative)
        elif path.is_file():
            observed_files[relative] = path
        else:
            raise IntegrationError(f"special file in managed tree: {path}")
    expected_files = set(files)
    if set(observed_files) != expected_files:
        raise IntegrationError(
            f"managed tree file drift at {root}: "
            f"missing={sorted(expected_files - set(observed_files))} "
            f"extra={sorted(set(observed_files) - expected_files)}"
        )
    expected_directories = _expected_directories(files)
    if observed_directories != expected_directories:
        raise IntegrationError(
            f"managed tree directory drift at {root}: "
            f"missing={sorted(expected_directories - observed_directories)} "
            f"extra={sorted(observed_directories - expected_directories)}"
        )
    for relative, expected in files.items():
        path = observed_files[relative]
        if path.read_bytes() != expected.content:
            raise IntegrationError(f"managed file content drift: {path}")
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode != expected.mode:
            raise IntegrationError(
                f"managed file mode drift: {path} expected={expected.mode:o} got={mode:o}"
            )


def check_outputs(repo_root: Path, snapshot: PackageSnapshot) -> dict[str, Any]:
    repo_root = _resolve_repository_root(repo_root)
    for tree in build_managed_trees(snapshot):
        root = _safe_output_root(repo_root, tree.relative_root)
        _check_tree(root, tree.files)
    return integration_report(snapshot, "check")


def _write_staged_tree(root: Path, files: Mapping[str, FilePayload]) -> None:
    root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{root.name}.staging-", dir=root.parent))
    try:
        for relative, payload in files.items():
            path = staging.joinpath(*PurePosixPath(relative).parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(path, flags, payload.mode)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(payload.content)
                    handle.flush()
                    os.fsync(handle.fileno())
            except BaseException:
                path.unlink(missing_ok=True)
                raise
            path.chmod(payload.mode)
        _check_tree(staging, files)
        if root.exists() or root.is_symlink():
            raise IntegrationError(f"managed output appeared during write: {root}")
        os.replace(staging, root)
    finally:
        if staging.exists():
            for path in sorted(
                staging.rglob("*"),
                key=lambda item: (len(item.relative_to(staging).parts), item.as_posix()),
                reverse=True,
            ):
                if path.is_file() or path.is_symlink():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            staging.rmdir()


def write_outputs(repo_root: Path, snapshot: PackageSnapshot) -> dict[str, Any]:
    repo_root = _resolve_repository_root(repo_root)
    trees = build_managed_trees(snapshot)
    states: list[tuple[ManagedTree, Path, bool]] = []
    # Full preflight happens before the first write, so any collision is a no-op.
    for tree in trees:
        root = _safe_output_root(repo_root, tree.relative_root)
        exists = root.exists() or root.is_symlink()
        if exists:
            _check_tree(root, tree.files)
        states.append((tree, root, exists))
    for tree, root, exists in states:
        if not exists:
            _write_staged_tree(root, tree.files)
    check_outputs(repo_root, snapshot)
    return integration_report(snapshot, "write")


def integration_report(snapshot: PackageSnapshot, mode: str) -> dict[str, Any]:
    return {
        "mode": mode,
        "package": PACKAGE_ID,
        "version": PACKAGE_VERSION,
        "namespace": PACKAGE_NAMESPACE,
        "archive_sha256": snapshot.archive_sha256,
        "archive_entries": len(snapshot.files),
        "archive_uncompressed_bytes": sum(
            len(payload.content) for payload in snapshot.files.values()
        ),
        "skills": len(snapshot.skills),
        "batches": len(snapshot.batches),
        "requirements": sum(snapshot.requirement_priority_counts.values()),
        "documented_scenarios": sum(snapshot.scenario_priority_counts.values()),
        "executable_reference_tests": snapshot.executable_reference_tests,
        "install_roots": [root.as_posix() for root in INSTALL_ROOTS],
        "dual_root_parity": "BYTE_AND_MODE_IDENTICAL",
        "guidance_state": GUIDANCE_STATE,
        "installation_state": INSTALL_STATE,
        "runtime_implementation": RUNTIME_IMPLEMENTATION_STATE,
        "runtime_binding": RUNTIME_BINDING_RELATIVE.as_posix(),
        "runtime_evidence": RUNTIME_EVIDENCE_STATE,
        "external_evidence": EXTERNAL_EVIDENCE_STATE,
        "certification": CERTIFICATION_STATE,
        "source_scripts_executed": False,
    }


def _resolve_archive(repo_root: Path, archive: Path | None) -> Path:
    candidate = repo_root / ARCHIVE_RELATIVE if archive is None else archive
    if candidate.is_symlink():
        raise IntegrationError(f"source archive must not be a symlink: {candidate}")
    return candidate.resolve()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="Create absent exact outputs")
    mode.add_argument("--check", action="store_true", help="Verify all generated outputs")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument(
        "--archive",
        type=Path,
        help="Test-only archive override; provenance remains bound to the canonical path",
    )
    args = parser.parse_args(argv)
    try:
        repo_root = _resolve_repository_root(args.repo_root)
        archive_path = _resolve_archive(repo_root, args.archive)
        snapshot = validate_archive(archive_path)
        report = (
            write_outputs(repo_root, snapshot)
            if args.write
            else check_outputs(repo_root, snapshot)
        )
    except IntegrationError as exc:
        parser.exit(1, f"ERROR: {exc}\n")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
