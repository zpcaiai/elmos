#!/usr/bin/env python3
"""Safely import the pinned build-cache staging and parity Skill package.

The attached ZIP is immutable, untrusted input.  This importer never imports or
executes package code.  It independently validates the archive, its complete
checksum inventory, manifest, dependency DAG, and Skill interfaces before it
extracts the package or updates repository Skill roots.

The v1.2 upgrade is deliberately narrow.  Existing v1.1 Skills may be replaced
only when their complete installed tree is byte-identical to the pinned v1.1
source and the v1.2 change is limited to the package/version frontmatter.  New
Skills may be created only at absent destinations.  Equal v1.2 trees are a
no-op; every other collision fails closed.
"""

from __future__ import annotations

import argparse
import hashlib
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
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

ARCHIVE_DIRECTORY = "elmos-build-cache-staging-codex-claude-parity-skills-v1.2.0"
ARCHIVE_RELATIVE = Path("skills/subskills") / f"{ARCHIVE_DIRECTORY}.zip"
SOURCE_RELATIVE = Path("agent-skills/packages/elmos-build-cache-staging-codex-claude-parity")
V11_SOURCE_RELATIVE = Path("agent-skills/packages/elmos-build-cache-staging-sota")
DOC_RELATIVE = Path("docs/build-cache-staging-parity")

PACKAGE_ID = "elmos-build-cache-staging-codex-claude-parity"
PACKAGE_VERSION = "1.2.0"
ENTRY_SKILL = "elmos-codex-claude-cache-parity-rollout"
EXPECTED_ARCHIVE_SHA256 = "dde312b55a95cbc7af6753ec88f07833e93ffa296b782ddcf3ef1a6470b73cb7"
EXPECTED_ARCHIVE_ENTRY_COUNT = 210
EXPECTED_ARCHIVE_FILE_COUNT = 146
EXPECTED_ARCHIVE_DIRECTORY_COUNT = 64
EXPECTED_ARCHIVE_UNCOMPRESSED_BYTES = 640_930
EXPECTED_ARCHIVE_MODE_COUNTS = {0o644: 140, 0o755: 6}
EXPECTED_CHECKSUM_ENTRY_COUNT = 145
EXPECTED_CHECKSUMS_SHA256 = "08977fdf302f36181eef8e05bdb74605b10eddc8ed68a43d6e3daaf0d0731d54"

V11_PACKAGE_ID = "elmos-build-cache-staging-sota"
V11_PACKAGE_VERSION = "1.1.0"
EXPECTED_V11_MANIFEST_SHA256 = "307edba86664c8428a57bdbb923af50cd05f8c52360fe30635b41828bc2a117f"
EXPECTED_V11_CHECKSUMS_SHA256 = "fb58fdd9d063644cdc9d0616ff01b8da9e7daf98da7e88ebe90f65baf8e8e3a7"

INSTALL_ROOTS = (
    Path("agent-skills/runtime"),
    Path(".agents/skills"),
    Path(".codex/skills"),
    Path(".claude/skills"),
)

V11_SKILLS = (
    "elmos-cache-system-architecture",
    "elmos-cache-metadata-database",
    "elmos-cache-api-cli-contracts",
    "elmos-project-snapshot-merkle",
    "elmos-content-addressable-storage",
    "elmos-cache-key-fingerprinting",
    "elmos-action-cache",
    "elmos-project-generation-file-staging",
    "elmos-atomic-file-write-promotion",
    "elmos-sandbox-overlay-workspaces",
    "elmos-intermediate-artifact-manifest",
    "elmos-stage-contract-registry",
    "elmos-semantic-interface-hashing",
    "elmos-incremental-conversion-dag",
    "elmos-run-journal-state-machine",
    "elmos-checkpoint-resume",
    "elmos-generation-conflict-merge",
    "elmos-remote-shared-cache",
    "elmos-native-build-cache-adapters",
    "elmos-cache-security-provenance",
    "elmos-cache-retention-gc",
    "elmos-cache-observability-performance",
    "elmos-cache-chaos-certification",
    "elmos-cache-trace-replay-simulator",
    "elmos-sota-cache-policy-portfolio",
    "elmos-dag-aware-cache-prefetch",
    "elmos-cost-aware-cache-admission",
    "elmos-adaptive-cache-policy-orchestrator",
    "elmos-learning-augmented-cache-control",
    "elmos-cache-autotuning-certification",
    "elmos-cache-rollout-end-to-end",
)

NEW_V12_SKILLS = (
    "elmos-provider-prompt-cache-adapters",
    "elmos-canonical-prompt-prefix-layout",
    "elmos-append-only-repository-context-ledger",
    "elmos-cache-preserving-context-compaction",
    "elmos-environment-snapshot-cache",
    "elmos-cache-affinity-routing",
    "elmos-multi-layer-cache-coordinator",
    "elmos-cache-miss-diagnostics",
    "elmos-codex-claude-parity-benchmark",
    "elmos-cache-hit-slo-autotuning",
    "elmos-codex-claude-cache-parity-rollout",
)

EXPECTED_SKILLS = V11_SKILLS + NEW_V12_SKILLS

REQUIRED_SKILL_SECTIONS = (
    "## Outcome",
    "## Use this skill when",
    "## Required inputs",
    "## Produced artifacts",
    "## Non-negotiable invariants",
    "## Execution workflow",
    "## Implementation tasks",
    "## Acceptance criteria",
    "## Evidence required",
    "## Anti-patterns",
    "## Done condition",
)

MAX_ARCHIVE_ENTRY_BYTES = 128 * 1024
MAX_ARCHIVE_TOTAL_BYTES = 2 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100


class IntegrationError(RuntimeError):
    """A pinned-source, lineage, collision, or installation validation error."""


@dataclass(frozen=True)
class FilePayload:
    content: bytes
    mode: int = 0o644


@dataclass(frozen=True)
class ArchiveSummary:
    files: dict[str, FilePayload]
    directories: tuple[str, ...]
    manifest: dict[str, Any]
    dependencies: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class InstallAction:
    destination: Path
    expected: dict[str, FilePayload]
    operation: str
    target_kind: str = "tree"


def fail(message: str) -> None:
    raise IntegrationError(message)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_relative_path(relative: str, label: str) -> PurePosixPath:
    if not relative or "\\" in relative or "\x00" in relative:
        fail(f"invalid {label} path: {relative!r}")
    if unicodedata.normalize("NFC", relative) != relative:
        fail(f"{label} path is not NFC-normalized: {relative!r}")
    path = PurePosixPath(relative)
    if path.is_absolute() or str(path) != relative or any(part in {"", ".", ".."} for part in path.parts):
        fail(f"{label} path escapes or is not normalized: {relative!r}")
    return path


def _load_json_bytes(value: bytes, label: str) -> Any:
    try:
        return json.loads(value.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        fail(f"invalid {label}: {exc}")


def _parse_frontmatter(value: bytes, label: str) -> dict[str, str]:
    try:
        text = value.decode("utf-8")
    except UnicodeError as exc:
        fail(f"{label} is not UTF-8: {exc}")
    if not text.startswith("---\n"):
        fail(f"{label} lacks YAML frontmatter")
    end = text.find("\n---\n", 4)
    if end < 0:
        fail(f"{label} has unclosed YAML frontmatter")
    result: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            fail(f"{label} has an invalid frontmatter line: {line!r}")
        key, raw = line.split(":", 1)
        key = key.strip()
        if key in result:
            fail(f"{label} has duplicate frontmatter field: {key}")
        result[key] = raw.strip()
    for section in REQUIRED_SKILL_SECTIONS:
        if section not in text:
            fail(f"{label} is missing required section: {section}")
    return result


def _parse_dependency_list(value: str, label: str) -> tuple[str, ...]:
    if value == "[]":
        return ()
    if not value.startswith("[") or not value.endswith("]"):
        fail(f"{label} dependencies are not a simple YAML list")
    dependencies = tuple(part.strip() for part in value[1:-1].split(","))
    if not dependencies or any(not item for item in dependencies):
        fail(f"{label} dependencies contain an empty item")
    return dependencies


def _validate_checksums(files: dict[str, FilePayload]) -> None:
    checksum = files.get("checksums.sha256")
    if checksum is None:
        fail("checksums.sha256 is missing")
    if sha256_bytes(checksum.content) != EXPECTED_CHECKSUMS_SHA256:
        fail("checksums.sha256 trusted digest mismatch")
    try:
        lines = checksum.content.decode("utf-8").splitlines()
    except UnicodeError as exc:
        fail(f"checksums.sha256 is not UTF-8: {exc}")
    if len(lines) != EXPECTED_CHECKSUM_ENTRY_COUNT:
        fail(
            f"checksums.sha256 must have {EXPECTED_CHECKSUM_ENTRY_COUNT} entries; "
            f"found {len(lines)}"
        )
    covered: dict[str, str] = {}
    for number, line in enumerate(lines, 1):
        match = re.fullmatch(r"([0-9a-f]{64})  (\S(?:.*\S)?)", line)
        if match is None:
            fail(f"invalid checksums.sha256 line {number}")
        expected_digest, relative = match.groups()
        _validate_relative_path(relative, "checksum")
        if relative == "checksums.sha256" or relative in covered:
            fail(f"duplicate or self-referential checksum path: {relative}")
        payload = files.get(relative)
        if payload is None:
            fail(f"checksummed file is missing: {relative}")
        if sha256_bytes(payload.content) != expected_digest:
            fail(f"checksum mismatch for {relative}")
        covered[relative] = expected_digest
    expected_coverage = set(files) - {"checksums.sha256"}
    if set(covered) != expected_coverage:
        fail(
            "checksum inventory is not complete: "
            f"missing={sorted(expected_coverage - set(covered))[:8]} "
            f"extra={sorted(set(covered) - expected_coverage)[:8]}"
        )


def _validate_manifest_and_skills(files: dict[str, FilePayload]) -> ArchiveSummary:
    manifest_payload = files.get("manifest.json")
    if manifest_payload is None:
        fail("manifest.json is missing")
    manifest = _load_json_bytes(manifest_payload.content, "manifest.json")
    if not isinstance(manifest, dict):
        fail("manifest.json must contain an object")
    if manifest.get("schema_version") != PACKAGE_VERSION:
        fail("manifest schema_version mismatch")
    if manifest.get("package_id") != PACKAGE_ID or manifest.get("package_version") != PACKAGE_VERSION:
        fail("manifest package identity mismatch")
    if manifest.get("entry_skill") != ENTRY_SKILL:
        fail("manifest entry Skill mismatch")
    records = manifest.get("skills")
    order = manifest.get("topological_order")
    if not isinstance(records, list) or not isinstance(order, list):
        fail("manifest Skills or topological_order is not a list")
    names = tuple(record.get("id") for record in records if isinstance(record, dict))
    if len(records) != len(EXPECTED_SKILLS) or names != EXPECTED_SKILLS:
        fail(f"manifest must contain the exact ordered {len(EXPECTED_SKILLS)}-Skill inventory")
    if tuple(order) != EXPECTED_SKILLS:
        fail("manifest topological_order is not the pinned 42-Skill order")
    if len(set(names)) != len(names):
        fail("manifest contains duplicate Skill IDs")

    dependencies: dict[str, tuple[str, ...]] = {}
    seen: set[str] = set()
    for record in records:
        name = record["id"]
        if re.fullmatch(r"[a-z0-9-]+", name) is None or len(name) > 64:
            fail(f"invalid Skill name: {name}")
        expected_path = f"agent-skills/runtime/{name}/SKILL.md"
        if record.get("path") != expected_path:
            fail(f"manifest Skill path mismatch for {name}")
        raw_dependencies = record.get("dependencies")
        if not isinstance(raw_dependencies, list) or any(not isinstance(item, str) for item in raw_dependencies):
            fail(f"manifest dependencies are invalid for {name}")
        dependency_tuple = tuple(raw_dependencies)
        unknown = set(dependency_tuple) - set(EXPECTED_SKILLS)
        if unknown:
            fail(f"{name} has unknown dependencies: {sorted(unknown)}")
        not_prior = set(dependency_tuple) - seen
        if not_prior:
            fail(f"{name} dependency order is not topological: {sorted(not_prior)}")
        dependencies[name] = dependency_tuple
        seen.add(name)

        payload = files.get(expected_path)
        if payload is None:
            fail(f"Skill file is missing: {expected_path}")
        frontmatter = _parse_frontmatter(payload.content, expected_path)
        required_fields = {"name", "description", "version", "package", "phase", "dependencies"}
        missing_fields = required_fields - set(frontmatter)
        if missing_fields:
            fail(f"{name} is missing frontmatter fields: {sorted(missing_fields)}")
        if frontmatter["name"] != name:
            fail(f"Skill frontmatter name mismatch: {name}")
        if frontmatter["version"] != PACKAGE_VERSION or frontmatter["package"] != PACKAGE_ID:
            fail(f"Skill package identity mismatch: {name}")
        if _parse_dependency_list(frontmatter["dependencies"], name) != dependency_tuple:
            fail(f"Skill dependency frontmatter mismatch: {name}")

    claim_policy = manifest.get("claim_policy")
    if not isinstance(claim_policy, dict) or claim_policy.get("mode") != "measured_only":
        fail("manifest must retain the measured-only parity claim boundary")
    return ArchiveSummary(files=files, directories=(), manifest=manifest, dependencies=dependencies)


def inspect_archive(
    archive: Path,
    *,
    trusted_sha256: str | None = EXPECTED_ARCHIVE_SHA256,
    enforce_pinned_shape: bool = True,
) -> ArchiveSummary:
    if not archive.is_file() or archive.is_symlink():
        fail(f"archive must be a regular file: {archive}")
    if trusted_sha256 is not None and sha256_file(archive) != trusted_sha256:
        fail("archive trusted SHA-256 mismatch")
    try:
        handle = zipfile.ZipFile(archive)
    except (OSError, zipfile.BadZipFile) as exc:
        fail(f"invalid ZIP archive: {exc}")
    with handle:
        infos = handle.infolist()
        if enforce_pinned_shape and len(infos) != EXPECTED_ARCHIVE_ENTRY_COUNT:
            fail(f"archive entry count mismatch: {len(infos)}")
        names: set[str] = set()
        folded: dict[str, str] = {}
        files: dict[str, FilePayload] = {}
        directories: list[str] = []
        total_bytes = 0
        mode_counts: Counter[int] = Counter()
        for info in infos:
            name = info.filename
            if name in names:
                fail(f"duplicate archive entry: {name}")
            names.add(name)
            if info.flag_bits & 0x1:
                fail(f"encrypted archive entry is forbidden: {name}")
            if info.create_system != 3:
                fail(f"archive entry lacks Unix type metadata: {name}")
            if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                fail(f"unsupported compression method for: {name}")
            if not name.startswith(f"{ARCHIVE_DIRECTORY}/"):
                fail(f"archive entry is outside the pinned root: {name}")
            relative_with_slash = name[len(ARCHIVE_DIRECTORY) + 1 :]
            if not relative_with_slash:
                if not info.is_dir():
                    fail("archive root entry is not a directory")
                continue
            is_directory = info.is_dir()
            relative = relative_with_slash[:-1] if is_directory else relative_with_slash
            _validate_relative_path(relative, "archive")
            folded_name = unicodedata.normalize("NFC", relative).casefold()
            previous = folded.get(folded_name)
            if previous is not None and previous != relative:
                fail(f"case-insensitive archive collision: {previous!r} and {relative!r}")
            folded[folded_name] = relative
            raw_mode = info.external_attr >> 16
            entry_type = stat.S_IFMT(raw_mode)
            permissions = stat.S_IMODE(raw_mode)
            if is_directory:
                # The source ZIP was created below a setgid workspace, so its
                # directory entries retain 02755.  Extraction deliberately
                # normalizes those directories to 0755; no executable file or
                # installed Skill inherits the setgid bit.
                if entry_type != stat.S_IFDIR or permissions not in {0o755, 0o2755}:
                    fail(f"unsafe archive directory type or mode: {name}")
                directories.append(relative)
                continue
            if entry_type != stat.S_IFREG or permissions not in {0o644, 0o755}:
                fail(f"unsafe archive file type or mode: {name}")
            if info.file_size > MAX_ARCHIVE_ENTRY_BYTES:
                fail(f"archive entry exceeds size limit: {name}")
            if info.file_size / max(1, info.compress_size) > MAX_COMPRESSION_RATIO:
                fail(f"archive entry exceeds compression-ratio limit: {name}")
            total_bytes += info.file_size
            if total_bytes > MAX_ARCHIVE_TOTAL_BYTES:
                fail("archive exceeds total uncompressed size limit")
            content = handle.read(info)
            if len(content) != info.file_size:
                fail(f"archive entry size changed while reading: {name}")
            files[relative] = FilePayload(content=content, mode=permissions)
            mode_counts[permissions] += 1
        if enforce_pinned_shape:
            if len(files) != EXPECTED_ARCHIVE_FILE_COUNT or len(directories) != EXPECTED_ARCHIVE_DIRECTORY_COUNT - 1:
                fail(
                    "archive file/directory inventory mismatch: "
                    f"files={len(files)} directories={len(directories) + 1}"
                )
            if total_bytes != EXPECTED_ARCHIVE_UNCOMPRESSED_BYTES:
                fail(f"archive uncompressed byte count mismatch: {total_bytes}")
            if dict(mode_counts) != EXPECTED_ARCHIVE_MODE_COUNTS:
                fail(f"archive file mode inventory mismatch: {dict(mode_counts)}")
        _validate_checksums(files)
        summary = _validate_manifest_and_skills(files)
        return ArchiveSummary(
            files=summary.files,
            directories=tuple(sorted(directories)),
            manifest=summary.manifest,
            dependencies=summary.dependencies,
        )


def _read_tree(root: Path) -> dict[str, FilePayload]:
    if not root.is_dir() or root.is_symlink():
        fail(f"tree is missing, not a directory, or a symlink: {root}")
    result: dict[str, FilePayload] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            fail(f"tree contains a symbolic link: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            fail(f"tree contains an unsupported entry: {path}")
        relative = path.relative_to(root).as_posix()
        _validate_relative_path(relative, "tree")
        result[relative] = FilePayload(path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
    return result


def _validate_source(source: Path, archive: Path) -> ArchiveSummary:
    summary = inspect_archive(archive)
    actual = _read_tree(source)
    if actual != summary.files:
        missing = sorted(set(summary.files) - set(actual))
        extra = sorted(set(actual) - set(summary.files))
        changed = sorted(
            name for name in set(actual) & set(summary.files) if actual[name] != summary.files[name]
        )
        fail(
            "immutable extracted source differs from the pinned archive: "
            f"missing={missing[:8]} extra={extra[:8]} changed={changed[:8]}"
        )
    return summary


def extract_source(repository_root: Path = ROOT) -> ArchiveSummary:
    repository_root = repository_root.resolve()
    archive = repository_root / ARCHIVE_RELATIVE
    destination = repository_root / SOURCE_RELATIVE
    summary = inspect_archive(archive)
    if destination.exists() or destination.is_symlink():
        return _validate_source(destination, archive)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{destination.name}-extract-", dir=destination.parent) as temporary:
        staging = Path(temporary) / destination.name
        staging.mkdir(mode=0o755)
        for relative in summary.directories:
            path = staging / PurePosixPath(relative)
            path.mkdir(parents=True, exist_ok=True)
            os.chmod(path, 0o755)
        for relative, payload in sorted(summary.files.items()):
            path = staging / PurePosixPath(relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload.content)
            os.chmod(path, payload.mode)
        if _read_tree(staging) != summary.files:
            fail("staged immutable source differs before publication")
        if destination.exists() or destination.is_symlink():
            fail(f"source destination appeared concurrently: {destination}")
        os.replace(staging, destination)
    return _validate_source(destination, archive)


def _parse_v11_checksums(source: Path) -> dict[str, str]:
    checksum_path = source / "checksums.sha256"
    if not checksum_path.is_file() or checksum_path.is_symlink():
        fail("pinned v1.1 checksums.sha256 is missing or unsafe")
    value = checksum_path.read_bytes()
    if sha256_bytes(value) != EXPECTED_V11_CHECKSUMS_SHA256:
        fail("pinned v1.1 checksums.sha256 digest mismatch")
    result: dict[str, str] = {}
    for number, line in enumerate(value.decode("utf-8").splitlines(), 1):
        match = re.fullmatch(r"([0-9a-f]{64})  (\S(?:.*\S)?)", line)
        if match is None:
            fail(f"invalid pinned v1.1 checksum line {number}")
        digest, legacy_relative = match.groups()
        # The already-committed v1.1 package wrote checksum paths with one
        # leading "./".  Its checksum file is itself pinned above, so accept
        # only that exact legacy spelling and normalize it before resolution.
        relative = legacy_relative[2:] if legacy_relative.startswith("./") else legacy_relative
        _validate_relative_path(relative, "v1.1 checksum")
        if relative in result:
            fail(f"duplicate pinned v1.1 checksum path: {relative}")
        path = source / PurePosixPath(relative)
        if not path.is_file() or path.is_symlink() or sha256_file(path) != digest:
            fail(f"pinned v1.1 checksum mismatch: {relative}")
        result[relative] = digest
    return result


def _load_v11_skills(repository_root: Path) -> dict[str, bytes]:
    source = repository_root / V11_SOURCE_RELATIVE
    manifest_path = source / "manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        fail("pinned v1.1 manifest is missing or unsafe")
    manifest_bytes = manifest_path.read_bytes()
    if sha256_bytes(manifest_bytes) != EXPECTED_V11_MANIFEST_SHA256:
        fail("pinned v1.1 manifest digest mismatch")
    checksums = _parse_v11_checksums(source)
    manifest = _load_json_bytes(manifest_bytes, "pinned v1.1 manifest")
    if manifest.get("package_id") != V11_PACKAGE_ID or manifest.get("package_version") != V11_PACKAGE_VERSION:
        fail("pinned v1.1 package identity mismatch")
    records = manifest.get("skills")
    if not isinstance(records, list) or tuple(record.get("id") for record in records) != V11_SKILLS:
        fail("pinned v1.1 Skill inventory mismatch")
    result: dict[str, bytes] = {}
    for record in records:
        name = record["id"]
        relative = record.get("path")
        expected_relative = f"agent-skills/runtime/{name}/SKILL.md"
        if relative != expected_relative or checksums.get(relative) is None:
            fail(f"pinned v1.1 Skill path is not checksum-bound: {name}")
        result[name] = (source / PurePosixPath(relative)).read_bytes()
    return result


def _assert_frontmatter_only_upgrade(name: str, old: bytes, new: bytes) -> None:
    old_version = b"version: 1.1.0"
    old_package = b"package: elmos-build-cache-staging-sota"
    if old.count(old_version) != 1 or old.count(old_package) != 1:
        fail(f"pinned v1.1 frontmatter identity is ambiguous: {name}")
    upgraded = old.replace(old_version, b"version: 1.2.0", 1).replace(
        old_package,
        b"package: elmos-build-cache-staging-codex-claude-parity",
        1,
    )
    if upgraded != new:
        fail(f"v1.2 changed more than package/version frontmatter for completed Skill: {name}")


def _expected_skill_trees(
    summary: ArchiveSummary,
    v11: dict[str, bytes],
) -> tuple[dict[str, dict[str, FilePayload]], dict[str, dict[str, FilePayload]]]:
    expected: dict[str, dict[str, FilePayload]] = {}
    prior: dict[str, dict[str, FilePayload]] = {}
    for name in EXPECTED_SKILLS:
        payload = summary.files[f"agent-skills/runtime/{name}/SKILL.md"]
        expected[name] = {"SKILL.md": payload}
        if name in v11:
            _assert_frontmatter_only_upgrade(name, v11[name], payload.content)
            prior[name] = {"SKILL.md": FilePayload(v11[name], payload.mode)}
    return expected, prior


def _package_tree_digest(files: dict[str, FilePayload]) -> str:
    digest = hashlib.sha256()
    for relative, payload in sorted(files.items()):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(f"{payload.mode:04o}".encode("ascii"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256_bytes(payload.content)))
    return "sha256:" + digest.hexdigest()


def _build_install_manifest(
    summary: ArchiveSummary,
    v11: dict[str, bytes],
) -> dict[str, FilePayload]:
    records = []
    for name in EXPECTED_SKILLS:
        content = summary.files[f"agent-skills/runtime/{name}/SKILL.md"].content
        record: dict[str, Any] = {
            "name": name,
            "source_sha256": "sha256:" + sha256_bytes(content),
            "migration": "v1.1-frontmatter-only" if name in v11 else "new-v1.2",
            "implementation_claim": "UNCHANGED" if name in v11 else "NOT_RUN",
        }
        if name in v11:
            record["prior_v1_1_sha256"] = "sha256:" + sha256_bytes(v11[name])
        records.append(record)
    manifest = {
        "schema_version": "elmos.build-cache-staging-parity.install.v1",
        "package_id": PACKAGE_ID,
        "package_version": PACKAGE_VERSION,
        "source_archive": ARCHIVE_RELATIVE.as_posix(),
        "source_archive_sha256": "sha256:" + EXPECTED_ARCHIVE_SHA256,
        "source_root": SOURCE_RELATIVE.as_posix(),
        "source_tree_sha256": _package_tree_digest(summary.files),
        "entry_skill": ENTRY_SKILL,
        "skill_count": len(EXPECTED_SKILLS),
        "retained_v1_1_skill_count": len(V11_SKILLS),
        "new_v1_2_skill_count": len(NEW_V12_SKILLS),
        "install_roots": [path.as_posix() for path in INSTALL_ROOTS],
        "four_root_byte_identical": True,
        "package_scripts_executed": False,
        "external_evidence_status": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
        "skills": records,
    }
    content = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return {"installed-manifest.json": FilePayload(content)}


def _classify_destination(
    destination: Path,
    expected: dict[str, FilePayload],
    prior: dict[str, FilePayload] | None,
) -> str:
    if not destination.exists() and not destination.is_symlink():
        return "create"
    actual = _read_tree(destination)
    if actual == expected:
        return "noop"
    if prior is not None and set(actual) == set(prior):
        # Seven v1.1 SOTA Skills were committed with 0644 in Git but are 0600
        # in this macOS worktree (core.filemode does not report that drift).
        # The authorized lineage is byte-based: accept only the exact pinned
        # v1.1 content with a non-executable 0600/0644 mode, then normalize the
        # v1.2 installation to the package-owned 0644 mode.
        if all(
            actual[path].content == prior[path].content
            and actual[path].mode in {0o600, prior[path].mode}
            for path in prior
        ):
            return "upgrade"
    fail(f"refusing unowned, incomplete, or drifted collision: {destination}")


def _write_staged_tree(destination: Path, tree: dict[str, FilePayload]) -> None:
    destination.mkdir(mode=0o755)
    for relative, payload in sorted(tree.items()):
        path = destination / PurePosixPath(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload.content)
        os.chmod(path, payload.mode)
    if _read_tree(destination) != tree:
        fail(f"staged installation differs from expected: {destination}")


def _classify_managed_file(destination: Path, expected: FilePayload) -> str:
    """Classify one importer-owned file without claiming its sibling directory."""

    if not destination.exists() and not destination.is_symlink():
        return "create"
    if destination.is_symlink() or not destination.is_file():
        fail(f"refusing unowned or unsafe managed-file collision: {destination}")
    actual = FilePayload(destination.read_bytes(), stat.S_IMODE(destination.stat().st_mode))
    if actual == expected:
        return "noop"
    fail(f"refusing drifted managed-file collision: {destination}")


def _write_staged_file(destination: Path, payload: FilePayload) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload.content)
    os.chmod(destination, payload.mode)
    actual = FilePayload(destination.read_bytes(), stat.S_IMODE(destination.stat().st_mode))
    if actual != payload:
        fail(f"staged installation differs from expected: {destination}")


def _prepare_actions(
    repository_root: Path,
    expected: dict[str, dict[str, FilePayload]],
    prior: dict[str, dict[str, FilePayload]],
    docs: dict[str, FilePayload],
) -> list[InstallAction]:
    actions: list[InstallAction] = []
    for relative_root in INSTALL_ROOTS:
        for name in EXPECTED_SKILLS:
            destination = repository_root / relative_root / name
            operation = _classify_destination(destination, expected[name], prior.get(name))
            if operation != "noop":
                actions.append(InstallAction(destination, expected[name], operation))
    manifest_name = "installed-manifest.json"
    doc_destination = repository_root / DOC_RELATIVE / manifest_name
    operation = _classify_managed_file(doc_destination, docs[manifest_name])
    if operation != "noop":
        actions.append(InstallAction(doc_destination, docs, operation, "file"))
    return actions


def _commit_actions(repository_root: Path, actions: list[InstallAction]) -> None:
    if not actions:
        return
    with tempfile.TemporaryDirectory(prefix=".build-cache-parity-install-", dir=repository_root) as temporary:
        temporary_root = Path(temporary)
        staged: list[Path] = []
        for index, action in enumerate(actions):
            stage = temporary_root / "staged" / str(index)
            if action.target_kind == "tree":
                stage.parent.mkdir(parents=True, exist_ok=True)
                _write_staged_tree(stage, action.expected)
            elif action.target_kind == "file":
                if set(action.expected) != {action.destination.name}:
                    fail(f"managed-file action has an invalid payload: {action.destination}")
                _write_staged_file(stage, action.expected[action.destination.name])
            else:
                fail(f"unknown install target kind: {action.target_kind}")
            staged.append(stage)

        committed: list[tuple[InstallAction, Path | None]] = []
        try:
            for index, (action, stage) in enumerate(zip(actions, staged, strict=True)):
                action.destination.parent.mkdir(parents=True, exist_ok=True)
                backup: Path | None = None
                if action.operation == "upgrade":
                    backup = temporary_root / "backups" / str(index)
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(action.destination, backup)
                elif action.operation != "create":
                    fail(f"unknown install action: {action.operation}")
                os.replace(stage, action.destination)
                committed.append((action, backup))
        except BaseException:
            rollback_errors: list[str] = []
            for action, backup in reversed(committed):
                try:
                    if action.destination.exists() or action.destination.is_symlink():
                        rollback_target = temporary_root / "rollback" / str(len(rollback_errors))
                        rollback_target.parent.mkdir(parents=True, exist_ok=True)
                        os.replace(action.destination, rollback_target)
                    if backup is not None and backup.exists():
                        os.replace(backup, action.destination)
                except OSError as exc:
                    rollback_errors.append(f"{action.destination}: {exc}")
            if rollback_errors:
                fail(f"installation failed and rollback was incomplete: {rollback_errors}")
            raise


def _expected_install(
    repository_root: Path,
) -> tuple[ArchiveSummary, dict[str, dict[str, FilePayload]], dict[str, dict[str, FilePayload]], dict[str, FilePayload]]:
    archive = repository_root / ARCHIVE_RELATIVE
    source = repository_root / SOURCE_RELATIVE
    summary = _validate_source(source, archive)
    v11 = _load_v11_skills(repository_root)
    expected, prior = _expected_skill_trees(summary, v11)
    docs = _build_install_manifest(summary, v11)
    return summary, expected, prior, docs


def check_install(repository_root: Path = ROOT) -> ArchiveSummary:
    repository_root = repository_root.resolve()
    summary, expected, _prior, docs = _expected_install(repository_root)
    failures: list[str] = []
    for relative_root in INSTALL_ROOTS:
        for name in EXPECTED_SKILLS:
            destination = repository_root / relative_root / name
            try:
                actual = _read_tree(destination)
            except IntegrationError as exc:
                failures.append(str(exc))
                continue
            if actual != expected[name]:
                failures.append(f"installation drifted: {destination}")
    manifest_name = "installed-manifest.json"
    doc_destination = repository_root / DOC_RELATIVE / manifest_name
    try:
        operation = _classify_managed_file(doc_destination, docs[manifest_name])
    except IntegrationError as exc:
        failures.append(str(exc))
    else:
        if operation != "noop":
            failures.append(f"installation missing: {doc_destination}")
    if failures:
        fail(f"build-cache parity installation is incomplete or drifted: {failures[:12]}")

    for name in EXPECTED_SKILLS:
        trees = [_read_tree(repository_root / relative_root / name) for relative_root in INSTALL_ROOTS]
        if any(tree != trees[0] for tree in trees[1:]):
            fail(f"Skill roots are not byte-identical: {name}")
    return summary


def install(repository_root: Path = ROOT) -> tuple[ArchiveSummary, list[InstallAction]]:
    repository_root = repository_root.resolve()
    summary, expected, prior, docs = _expected_install(repository_root)
    actions = _prepare_actions(repository_root, expected, prior, docs)
    _commit_actions(repository_root, actions)
    check_install(repository_root)
    return summary, actions


def main() -> int:
    parser = argparse.ArgumentParser(description="Import the pinned ELMOS build-cache parity Skill package")
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--extract", action="store_true", help="safely extract the immutable source package")
    operation.add_argument("--check", action="store_true", help="verify source and all installed roots without writing")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    repository_root = args.root.resolve()
    try:
        if args.extract:
            summary = extract_source(repository_root)
            decision = "SOURCE_EXTRACTED_AND_VERIFIED"
            action_counts: Counter[str] = Counter()
        elif args.check:
            summary = check_install(repository_root)
            decision = "INSTALLATION_VERIFIED"
            action_counts = Counter()
        else:
            summary, actions = install(repository_root)
            decision = "INSTALLED_OR_UPGRADED"
            action_counts = Counter(action.operation for action in actions)
    except IntegrationError as exc:
        print(json.dumps({"decision": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 1
    print(
        json.dumps(
            {
                "decision": decision,
                "package_id": PACKAGE_ID,
                "package_version": PACKAGE_VERSION,
                "source_archive_sha256": "sha256:" + EXPECTED_ARCHIVE_SHA256,
                "skills": len(EXPECTED_SKILLS),
                "retained_v1_1_skills": len(V11_SKILLS),
                "new_v1_2_skills": len(NEW_V12_SKILLS),
                "dependency_edges": sum(len(value) for value in summary.dependencies.values()),
                "actions": dict(sorted(action_counts.items())),
                "external_evidence_status": "NOT_RUN",
                "certification": "NOT_CERTIFIED",
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
