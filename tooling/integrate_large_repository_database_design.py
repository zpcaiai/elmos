#!/usr/bin/env python3
"""Safely install the pinned large-repository database design Skill package.

The ZIP is an immutable, untrusted source input.  This repository-owned
importer validates its complete inventory and checksums without importing or
executing package code, materializes an exact canonical source tree, and
normalizes the single source Skill for the two repository Skill roots.

Only structural/static integration is established here.  PostgreSQL engine,
concurrency, RLS, failover, upgrade, restore, external-verifier, and
certification evidence remain explicitly fail-closed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import unicodedata
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

try:
    import yaml
except ModuleNotFoundError as exc:  # pragma: no cover - dependency diagnostic
    raise SystemExit("PyYAML is required by the repository Skill validator") from exc

import skill_creator_tools


ROOT = Path(__file__).resolve().parents[1]

PACKAGE_DIRECTORY = "elmos-large-repository-database-design-v1.0.0"
PACKAGE_NAME = "elmos-large-repository-database-design"
PACKAGE_VERSION = "1.0.0"
NAMESPACE = "elmos-large-repository-database-design-v1"
SKILL_NAME = "large-repository-run-persistence"

ARCHIVE_RELATIVE = Path("skills/subskills") / f"{PACKAGE_DIRECTORY}.zip"
SOURCE_RELATIVE = Path("skills") / PACKAGE_DIRECTORY
SOURCE_SKILL_RELATIVE = Path("skills/large-repository-run-persistence/SKILL.md")
RUNTIME_RELATIVE = Path("agent-skills/runtime")
WORKSPACE_RELATIVE = Path(".agents/skills")
DOC_RELATIVE = Path("docs/large-repository-database-design")
INSTALL_MANIFEST_NAME = "installed-manifest.json"

EXPECTED_ARCHIVE_SHA256 = (
    "624de461a0a7a3a295b6c3ebcd1ffd6e3a45f80bdf33aad0d7e3cb0d8c430e88"
)
ALLOWED_PREVIOUS_INSTALL_MANIFEST_SHA256 = frozenset(
    {
        # Repository-owned v1 manifest before the claim_ready_task ambiguity
        # was recorded. This permits one exact, auditable metadata migration;
        # arbitrary or user-owned manifest drift still fails closed.
        "fbe49b8f20dff983656eb5ebd1d1357fa2197d552d0ddead25a0d63825d0c872",
    }
)
EXPECTED_ARCHIVE_BYTES = 158_461
EXPECTED_ARCHIVE_ENTRIES = 59
EXPECTED_SOURCE_FILES = 42
EXPECTED_SOURCE_DIRECTORIES = 17
EXPECTED_SOURCE_BYTES = 489_986
EXPECTED_CHECKSUM_SHA256 = (
    "6bf7c561ccc3e31ed296717d20bc9f3915d149896a1d2b1dd9a3c7094a9fc07a"
)
EXPECTED_CHECKSUM_ENTRIES = 41
EXPECTED_ARCHIVE_DIRECTORY_MODE = 0o2755
CANONICAL_DIRECTORY_MODE = 0o755
INSTALLED_DIRECTORY_MODE = 0o755
INSTALLED_FILE_MODE = 0o644
EXPECTED_EXECUTABLES = {"scripts/validate_database_design.py"}

CHECKSUM_PATH = "CHECKSUMS.sha256"
PACKAGE_MANIFEST_PATH = "PACKAGE-MANIFEST.json"
VALIDATION_REPORT_PATH = "VALIDATION-REPORT.md"
WORKFLOW_PATH = ".github/workflows/database-ci.yml"
BROKEN_WORKFLOW_REFERENCE = "scripts/validate_bundle.py"

SOURCE_FRONTMATTER_KEYS = {
    "name",
    "description",
    "license",
    "compatibility",
    "metadata",
}
SOURCE_METADATA_KEYS = {"product", "package", "phase", "version"}
CHECKSUM_LINE = re.compile(r"^([0-9a-f]{64})  (.+)$")
WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:")


class IntegrationError(RuntimeError):
    """A fail-closed archive, source, or installation error."""


def fail(message: str) -> None:
    raise IntegrationError(message)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest(value: bytes) -> str:
    return f"sha256:{sha256_bytes(value)}"


def sha256_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def load_json_bytes(value: bytes, label: str) -> Any:
    try:
        return json.loads(value.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        fail(f"invalid {label}: {exc}")


def validate_relative_path(value: str, label: str) -> PurePosixPath:
    """Require one normalized, platform-neutral, relative path."""

    if not value or "\\" in value or "\x00" in value:
        fail(f"unsafe {label} path: {value!r}")
    if unicodedata.normalize("NFC", value) != value:
        fail(f"non-normal Unicode {label} path: {value!r}")
    if WINDOWS_ABSOLUTE.match(value):
        fail(f"absolute {label} path: {value!r}")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        fail(f"non-normal, absolute, or traversal {label} path: {value!r}")
    return path


def validate_repository_directory(
    repository_root: Path,
    directory: Path,
    label: str,
) -> None:
    """Reject writes through symlinked or non-directory repository ancestors."""

    root = Path(os.path.abspath(repository_root))
    target = Path(os.path.abspath(directory))
    if not root.is_dir() or root.is_symlink():
        fail(f"repository root must be a real directory: {root}")
    try:
        relative = target.relative_to(root)
    except ValueError:
        fail(f"{label} directory escapes repository root: {target}")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            fail(f"{label} directory has a symbolic-link ancestor: {current}")
        if current.exists() and not current.is_dir():
            fail(f"{label} ancestor is not a directory: {current}")


def expected_file_mode(relative: str) -> int:
    return 0o755 if relative in EXPECTED_EXECUTABLES else 0o644


def required_directory_paths(file_paths: Sequence[str]) -> set[str]:
    required = {""}
    for relative in file_paths:
        for parent in PurePosixPath(relative).parents:
            value = parent.as_posix()
            required.add("" if value == "." else value)
    return required


@dataclass(frozen=True)
class ArchiveSnapshot:
    files: dict[str, bytes]
    file_modes: dict[str, int]
    directories: dict[str, int]
    checksums: dict[str, str]

    @property
    def uncompressed_bytes(self) -> int:
        return sum(len(value) for value in self.files.values())


def parse_checksums(value: bytes) -> dict[str, str]:
    if sha256_bytes(value) != EXPECTED_CHECKSUM_SHA256:
        fail("CHECKSUMS.sha256 digest mismatch")
    try:
        text = value.decode("utf-8")
    except UnicodeError as exc:
        fail(f"CHECKSUMS.sha256 is not UTF-8: {exc}")
    if not text.endswith("\n"):
        fail("CHECKSUMS.sha256 must end with a newline")

    checksums: dict[str, str] = {}
    casefolded: set[str] = set()
    for line_number, line in enumerate(text.splitlines(), 1):
        match = CHECKSUM_LINE.fullmatch(line)
        if match is None:
            fail(f"invalid CHECKSUMS.sha256 line {line_number}")
        relative = validate_relative_path(match.group(2), "checksum")
        name = relative.as_posix()
        folded = name.casefold()
        if name in checksums or folded in casefolded:
            fail(f"duplicate or case-colliding checksum path: {name}")
        checksums[name] = match.group(1)
        casefolded.add(folded)
    if len(checksums) != EXPECTED_CHECKSUM_ENTRIES:
        fail(
            "CHECKSUMS.sha256 entry count mismatch: "
            f"expected={EXPECTED_CHECKSUM_ENTRIES} actual={len(checksums)}"
        )
    return checksums


def read_archive(
    archive: Path,
    *,
    enforce_identity: bool = True,
) -> ArchiveSnapshot:
    """Validate and read the package without extracting or executing it.

    ``enforce_identity=False`` exists only so unit tests can exercise individual
    fail-closed ZIP checks against deliberately corrupted fixtures.  All public
    write/check paths use the default pinned-identity enforcement.
    """

    if not archive.is_file() or archive.is_symlink():
        fail(f"source archive must be a regular file: {archive}")
    if enforce_identity:
        actual_size = archive.stat().st_size
        if actual_size != EXPECTED_ARCHIVE_BYTES:
            fail(
                "archive byte count mismatch: "
                f"expected={EXPECTED_ARCHIVE_BYTES} actual={actual_size}"
            )
        actual_digest = sha256_file(archive)
        if actual_digest != EXPECTED_ARCHIVE_SHA256:
            fail(
                "archive SHA-256 mismatch: "
                f"expected={EXPECTED_ARCHIVE_SHA256} actual={actual_digest}"
            )

    files: dict[str, bytes] = {}
    file_modes: dict[str, int] = {}
    directories: dict[str, int] = {}
    seen_paths: set[str] = set()
    seen_casefolded: set[str] = set()
    try:
        with zipfile.ZipFile(archive) as handle:
            entries = handle.infolist()
            if len(entries) != EXPECTED_ARCHIVE_ENTRIES:
                fail(
                    "archive entry count mismatch: "
                    f"expected={EXPECTED_ARCHIVE_ENTRIES} actual={len(entries)}"
                )
            for info in entries:
                raw_name = info.filename
                is_directory = raw_name.endswith("/")
                normalized_name = raw_name[:-1] if is_directory else raw_name
                path = validate_relative_path(normalized_name, "archive")
                if not path.parts or path.parts[0] != PACKAGE_DIRECTORY:
                    fail(f"archive entry is outside the package root: {raw_name!r}")

                normalized_key = path.as_posix()
                folded = normalized_key.casefold()
                if normalized_key in seen_paths or folded in seen_casefolded:
                    fail(f"duplicate or casefold-colliding archive entry: {raw_name}")
                seen_paths.add(normalized_key)
                seen_casefolded.add(folded)

                if info.flag_bits & 0x1:
                    fail(f"encrypted archive entry is forbidden: {raw_name}")
                if info.create_system != 3:
                    fail(f"archive entry lacks trusted Unix mode metadata: {raw_name}")

                mode = info.external_attr >> 16
                kind = stat.S_IFMT(mode)
                permissions = stat.S_IMODE(mode)
                relative_parts = path.parts[1:]
                relative = PurePosixPath(*relative_parts).as_posix() if relative_parts else ""

                if is_directory:
                    if not info.is_dir() or info.compress_type != zipfile.ZIP_STORED:
                        fail(f"unsupported archive directory encoding: {raw_name}")
                    if kind != stat.S_IFDIR or permissions != EXPECTED_ARCHIVE_DIRECTORY_MODE:
                        fail(
                            f"unsupported archive directory mode: {raw_name}: "
                            f"{permissions:04o}"
                        )
                    directories[relative] = permissions
                    continue

                if info.is_dir() or kind == stat.S_IFLNK:
                    fail(f"archive contains a symbolic link: {raw_name}")
                if kind != stat.S_IFREG:
                    fail(f"archive contains a non-regular file: {raw_name}")
                if not relative:
                    fail("archive package root cannot be a file")
                if info.compress_type != zipfile.ZIP_DEFLATED:
                    fail(f"unsupported archive file compression: {raw_name}")
                required_mode = expected_file_mode(relative)
                if permissions != required_mode:
                    fail(
                        f"unsupported archive file mode: {raw_name}: "
                        f"expected={required_mode:04o} actual={permissions:04o}"
                    )
                content = handle.read(info)
                if len(content) != info.file_size:
                    fail(f"incomplete archive read: {raw_name}")
                files[relative] = content
                file_modes[relative] = permissions
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        fail(f"cannot validate source archive: {exc}")

    if len(files) != EXPECTED_SOURCE_FILES:
        fail(
            "archive file count mismatch: "
            f"expected={EXPECTED_SOURCE_FILES} actual={len(files)}"
        )
    if len(directories) != EXPECTED_SOURCE_DIRECTORIES:
        fail(
            "archive directory count mismatch: "
            f"expected={EXPECTED_SOURCE_DIRECTORIES} actual={len(directories)}"
        )
    uncompressed_bytes = sum(len(value) for value in files.values())
    if uncompressed_bytes != EXPECTED_SOURCE_BYTES:
        fail(
            "archive uncompressed byte count mismatch: "
            f"expected={EXPECTED_SOURCE_BYTES} actual={uncompressed_bytes}"
        )
    required_directories = required_directory_paths(list(files))
    if set(directories) != required_directories:
        fail(
            "archive directory inventory is not exact: "
            f"missing={sorted(required_directories - set(directories))} "
            f"extra={sorted(set(directories) - required_directories)}"
        )

    if CHECKSUM_PATH not in files:
        fail("archive is missing CHECKSUMS.sha256")
    checksums = parse_checksums(files[CHECKSUM_PATH])
    expected_checked_files = set(files) - {CHECKSUM_PATH}
    if set(checksums) != expected_checked_files:
        fail(
            "checksum coverage has extra or unchecked paths: "
            f"unchecked={sorted(expected_checked_files - set(checksums))} "
            f"extra={sorted(set(checksums) - expected_checked_files)}"
        )
    for relative, expected_digest in checksums.items():
        actual_digest = sha256_bytes(files[relative])
        if actual_digest != expected_digest:
            fail(
                f"checksum mismatch for {relative}: "
                f"expected={expected_digest} actual={actual_digest}"
            )

    return ArchiveSnapshot(files, file_modes, directories, checksums)


def tree_digest(
    files: Mapping[str, bytes],
    file_modes: Mapping[str, int],
    directories: Mapping[str, int],
) -> str:
    value = hashlib.sha256()
    for relative in sorted(directories):
        value.update(b"directory\0")
        value.update(relative.encode("utf-8"))
        value.update(b"\0")
        value.update(f"{directories[relative]:04o}".encode("ascii"))
        value.update(b"\0")
    for relative in sorted(files):
        content = files[relative]
        value.update(b"file\0")
        value.update(relative.encode("utf-8"))
        value.update(b"\0")
        value.update(f"{file_modes[relative]:04o}".encode("ascii"))
        value.update(b"\0")
        value.update(len(content).to_bytes(8, "big"))
        value.update(content)
    return f"sha256:{value.hexdigest()}"


def canonical_directory_modes(snapshot: ArchiveSnapshot) -> dict[str, int]:
    return {relative: CANONICAL_DIRECTORY_MODE for relative in snapshot.directories}


def walk_source(source: Path) -> tuple[dict[str, bytes], dict[str, int], dict[str, int]]:
    if not source.is_dir() or source.is_symlink():
        fail(f"canonical source must be a real directory: {source}")

    files: dict[str, bytes] = {}
    file_modes: dict[str, int] = {}
    directories: dict[str, int] = {"": stat.S_IMODE(source.stat().st_mode)}

    def visit(directory: Path, relative_directory: PurePosixPath | None) -> None:
        try:
            children = sorted(directory.iterdir(), key=lambda item: item.name)
        except OSError as exc:
            fail(f"cannot read canonical source directory {directory}: {exc}")
        for child in children:
            relative = (
                PurePosixPath(child.name)
                if relative_directory is None
                else relative_directory / child.name
            )
            relative_text = relative.as_posix()
            validate_relative_path(relative_text, "canonical source")
            if child.is_symlink():
                fail(f"canonical source contains a symbolic link: {relative_text}")
            if child.is_dir():
                directories[relative_text] = stat.S_IMODE(child.stat().st_mode)
                visit(child, relative)
            elif child.is_file():
                files[relative_text] = child.read_bytes()
                file_modes[relative_text] = stat.S_IMODE(child.stat().st_mode)
            else:
                fail(f"canonical source contains an unsupported entry: {relative_text}")

    visit(source, None)
    return files, file_modes, directories


def validate_source_tree(source: Path, snapshot: ArchiveSnapshot) -> dict[str, Any]:
    files, modes, directories = walk_source(source)
    if set(files) != set(snapshot.files):
        fail(
            "canonical source inventory differs from archive: "
            f"missing={sorted(set(snapshot.files) - set(files))} "
            f"extra={sorted(set(files) - set(snapshot.files))}"
        )
    expected_directories = canonical_directory_modes(snapshot)
    if directories != expected_directories:
        fail(
            "canonical source directory mode or inventory drift: "
            f"expected={expected_directories} actual={directories}"
        )
    inventory: list[dict[str, Any]] = []
    for relative in sorted(snapshot.files):
        if files[relative] != snapshot.files[relative]:
            fail(f"canonical source bytes differ from archive: {relative}")
        if modes[relative] != snapshot.file_modes[relative]:
            fail(
                f"canonical source file mode differs from archive: {relative}: "
                f"expected={snapshot.file_modes[relative]:04o} actual={modes[relative]:04o}"
            )
        inventory.append(
            {
                "path": relative,
                "bytes": len(files[relative]),
                "mode": f"{modes[relative]:04o}",
                "sha256": digest(files[relative]),
            }
        )
    return {
        "files": files,
        "file_modes": modes,
        "directories": directories,
        "inventory": inventory,
        "tree_sha256": tree_digest(files, modes, directories),
    }


def extract_canonical_source(repository_root: Path = ROOT) -> Path:
    """Materialize the pinned source once, without ZipFile.extract()."""

    archive = repository_root / ARCHIVE_RELATIVE
    source = repository_root / SOURCE_RELATIVE
    validate_repository_directory(repository_root, archive.parent, "archive")
    validate_repository_directory(repository_root, source.parent, "canonical source")
    snapshot = read_archive(archive)
    if source.exists() or source.is_symlink():
        validate_source_tree(source, snapshot)
        return source

    source.parent.mkdir(parents=True, exist_ok=True)
    staged = source.parent / f".{PACKAGE_DIRECTORY}.extract.{uuid.uuid4().hex}"
    try:
        staged.mkdir(mode=CANONICAL_DIRECTORY_MODE)
        staged.chmod(CANONICAL_DIRECTORY_MODE)
        for relative in sorted(
            (item for item in snapshot.directories if item),
            key=lambda item: (len(PurePosixPath(item).parts), item),
        ):
            validate_relative_path(relative, "extracted directory")
            target = staged.joinpath(*PurePosixPath(relative).parts)
            target.mkdir(mode=CANONICAL_DIRECTORY_MODE)
            target.chmod(CANONICAL_DIRECTORY_MODE)
        for relative in sorted(snapshot.files):
            validate_relative_path(relative, "extracted file")
            target = staged.joinpath(*PurePosixPath(relative).parts)
            target.write_bytes(snapshot.files[relative])
            target.chmod(snapshot.file_modes[relative])
        validate_source_tree(staged, snapshot)
        if source.exists() or source.is_symlink():
            fail(f"canonical source appeared during extraction: {source}")
        os.replace(staged, source)
    except Exception:
        shutil.rmtree(staged, ignore_errors=True)
        raise
    return source


def parse_source_skill(value: bytes) -> tuple[dict[str, Any], str]:
    try:
        text = value.decode("utf-8")
    except UnicodeError as exc:
        fail(f"source Skill is not UTF-8: {exc}")
    match = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.DOTALL)
    if match is None:
        fail("source Skill has invalid YAML frontmatter")
    try:
        metadata = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        fail(f"source Skill frontmatter is invalid: {exc}")
    if not isinstance(metadata, dict) or set(metadata) != SOURCE_FRONTMATTER_KEYS:
        actual = sorted(metadata) if isinstance(metadata, dict) else type(metadata).__name__
        fail(
            "source Skill frontmatter keys changed: "
            f"expected={sorted(SOURCE_FRONTMATTER_KEYS)} actual={actual}"
        )
    nested = metadata.get("metadata")
    if not isinstance(nested, dict) or set(nested) != SOURCE_METADATA_KEYS:
        fail("source Skill nested metadata changed")
    if metadata.get("name") != SKILL_NAME:
        fail(f"source Skill name changed: {metadata.get('name')!r}")
    if not isinstance(metadata.get("description"), str) or not metadata["description"].strip():
        fail("source Skill description is missing")
    if metadata.get("license") != "Proprietary":
        fail("source Skill license changed")
    if not isinstance(metadata.get("compatibility"), str):
        fail("source Skill compatibility declaration changed")
    if nested != {
        "product": "elmos",
        "package": "deployment-and-data-plane",
        "phase": "DB-1-DB-4",
        "version": "1.0.0",
    }:
        fail("source Skill metadata values changed")
    body = match.group(2).lstrip("\n")
    if not body.startswith("# Elmos Large Repository Run Persistence\n"):
        fail("source Skill body heading changed")
    return metadata, body


def validate_source_contract(snapshot: ArchiveSnapshot) -> dict[str, Any]:
    required = {
        CHECKSUM_PATH,
        PACKAGE_MANIFEST_PATH,
        VALIDATION_REPORT_PATH,
        WORKFLOW_PATH,
        SOURCE_SKILL_RELATIVE.as_posix(),
    }
    if not required.issubset(snapshot.files):
        fail(f"source package is missing contract files: {sorted(required - set(snapshot.files))}")

    package_manifest = load_json_bytes(
        snapshot.files[PACKAGE_MANIFEST_PATH], PACKAGE_MANIFEST_PATH
    )
    if not isinstance(package_manifest, dict):
        fail("PACKAGE-MANIFEST.json must be an object")
    if package_manifest.get("name") != PACKAGE_NAME:
        fail("PACKAGE-MANIFEST.json package name changed")
    if package_manifest.get("version") != PACKAGE_VERSION:
        fail("PACKAGE-MANIFEST.json version changed")
    if package_manifest.get("database") != "PostgreSQL 16+":
        fail("PACKAGE-MANIFEST.json database profile changed")

    report = snapshot.files[VALIDATION_REPORT_PATH].decode("utf-8")
    report_heading = "# Elmos v1.1.0 交付校验报告"
    if not report.startswith(report_heading + "\n"):
        fail("expected source 1.0/1.1 validation-report drift marker changed")

    workflow = snapshot.files[WORKFLOW_PATH].decode("utf-8")
    reference = f"python3 {BROKEN_WORKFLOW_REFERENCE}"
    if reference not in workflow:
        fail("expected broken source workflow reference changed")
    if BROKEN_WORKFLOW_REFERENCE in snapshot.files:
        fail("broken source workflow reference unexpectedly resolved in the pinned archive")

    skill_metadata, skill_body = parse_source_skill(
        snapshot.files[SOURCE_SKILL_RELATIVE.as_posix()]
    )
    return {
        "package_manifest": package_manifest,
        "skill_metadata": skill_metadata,
        "skill_body": skill_body,
        "source_version_drift": {
            "state": "PRESERVED_SOURCE_DRIFT",
            "package_manifest_version": PACKAGE_VERSION,
            "validation_report_heading_version": "1.1.0",
            "resolution": "CANONICAL_SOURCE_NOT_REWRITTEN",
        },
        "broken_source_workflow_reference": {
            "state": "PRESENT_BROKEN_REFERENCE",
            "workflow_path": (SOURCE_RELATIVE / WORKFLOW_PATH).as_posix(),
            "referenced_path": BROKEN_WORKFLOW_REFERENCE,
            "referenced_path_present_in_archive": False,
            "importer_executes_workflow": False,
        },
    }


def validate_source(repository_root: Path = ROOT) -> dict[str, Any]:
    validate_repository_directory(
        repository_root,
        (repository_root / ARCHIVE_RELATIVE).parent,
        "archive",
    )
    validate_repository_directory(
        repository_root,
        (repository_root / SOURCE_RELATIVE).parent,
        "canonical source",
    )
    snapshot = read_archive(repository_root / ARCHIVE_RELATIVE)
    source = validate_source_tree(repository_root / SOURCE_RELATIVE, snapshot)
    contract = validate_source_contract(snapshot)
    return {"snapshot": snapshot, "source": source, "contract": contract}


def render_skill(summary: Mapping[str, Any]) -> bytes:
    snapshot: ArchiveSnapshot = summary["snapshot"]
    source_metadata = summary["contract"]["skill_metadata"]
    nested = source_metadata["metadata"]
    description = (
        str(source_metadata["description"]).strip()
        + " Use the pinned repository integration boundary and keep all engine and "
        "external evidence fail-closed."
    )
    if len(description) > 1024:
        fail("normalized Skill description exceeds the Codex limit")
    source_skill = snapshot.files[SOURCE_SKILL_RELATIVE.as_posix()]
    lines = [
        "---",
        f"name: {SKILL_NAME}",
        f"description: {skill_creator_tools.yaml_quote(description)}",
        f"license: {skill_creator_tools.yaml_quote(str(source_metadata['license']))}",
        "metadata:",
        f"  source_package: {skill_creator_tools.yaml_quote(PACKAGE_NAME)}",
        f"  source_version: {skill_creator_tools.yaml_quote(PACKAGE_VERSION)}",
        f"  source_path: {skill_creator_tools.yaml_quote((SOURCE_RELATIVE / SOURCE_SKILL_RELATIVE).as_posix())}",
        f"  source_sha256: {skill_creator_tools.yaml_quote(digest(source_skill))}",
        f"  source_compatibility: {skill_creator_tools.yaml_quote(str(source_metadata['compatibility']))}",
        f"  source_product: {skill_creator_tools.yaml_quote(str(nested['product']))}",
        f"  source_package_group: {skill_creator_tools.yaml_quote(str(nested['package']))}",
        f"  source_phase: {skill_creator_tools.yaml_quote(str(nested['phase']))}",
        f"  source_declared_version: {skill_creator_tools.yaml_quote(str(nested['version']))}",
        f"  normalized_namespace: {skill_creator_tools.yaml_quote(NAMESPACE)}",
        '  installation_state: "INSTALLED"',
        '  implementation_state: "STATIC_VALIDATED"',
        '  postgresql_runtime_evidence: "NOT_RUN"',
        '  concurrency_evidence: "NOT_RUN"',
        '  rls_evidence: "NOT_RUN"',
        '  failover_evidence: "NOT_RUN"',
        '  upgrade_evidence: "NOT_RUN"',
        '  restore_evidence: "NOT_RUN"',
        '  external_evidence: "NOT_RUN"',
        '  certification: "NOT_CERTIFIED"',
        "---",
        "",
    ]
    boundary = """

## Repository Integration and Evidence Boundary

- The canonical package remains byte-identical to the pinned ZIP. Its source `compatibility` declaration is retained as provenance metadata because `compatibility` is not a repository-supported top-level Skill frontmatter key.
- The package declares version `1.0.0`, while `VALIDATION-REPORT.md` labels itself `v1.1.0`; this drift is preserved and explicit rather than silently corrected.
- The source workflow invokes missing `scripts/validate_bundle.py`. The importer never runs that workflow, the package validator, SQL, Flyway, Docker, or any other source executable.
- `STATIC_VALIDATED` means only that archive safety, complete checksums, static source contracts, normalized Skill shape, provenance, and installation drift were checked by repository-owned code.
- PostgreSQL 16/17 migration execution, real concurrency and stale-fence behavior, cross-tenant RLS, failover, previous-version upgrade, backup/PITR restore, representative workloads, and independent external evidence remain `NOT_RUN`.
- Apply the exact directional Batch 31 database implementation contract and conservative gate before raising any support or readiness status. Unknown or missing evidence fails closed; certification remains `NOT_CERTIFIED`.
"""
    body = str(summary["contract"]["skill_body"]).rstrip()
    return ("\n".join(lines) + "\n" + body + boundary).encode("utf-8")


def render_interface() -> bytes:
    return (
        "\n".join(
            [
                "interface:",
                '  display_name: "Large Repository Run Persistence"',
                '  short_description: "Apply the pinned ELMOS PostgreSQL persistence contract"',
                (
                    '  default_prompt: "Use $large-repository-run-persistence with '
                    'the pinned database design; keep runtime and certification evidence fail-closed."'
                ),
                "",
            ]
        )
    ).encode("utf-8")


def installed_tree_digest(tree: Mapping[str, bytes]) -> str:
    value = hashlib.sha256()
    for relative in sorted(required_directory_paths(list(tree))):
        value.update(b"directory\0")
        value.update(relative.encode("utf-8"))
        value.update(b"\0")
        value.update(f"{INSTALLED_DIRECTORY_MODE:04o}".encode("ascii"))
        value.update(b"\0")
    for relative in sorted(tree):
        validate_relative_path(relative, "installed tree")
        content = tree[relative]
        value.update(b"file\0")
        value.update(relative.encode("utf-8"))
        value.update(b"\0")
        value.update(f"{INSTALLED_FILE_MODE:04o}".encode("ascii"))
        value.update(b"\0")
        value.update(len(content).to_bytes(8, "big"))
        value.update(content)
    return f"sha256:{value.hexdigest()}"


def build_expected(repository_root: Path = ROOT) -> dict[str, Any]:
    summary = validate_source(repository_root)
    snapshot: ArchiveSnapshot = summary["snapshot"]
    skill_bytes = render_skill(summary)
    interface_bytes = render_interface()
    tree = {"SKILL.md": skill_bytes, "agents/openai.yaml": interface_bytes}
    tree_sha256 = installed_tree_digest(tree)
    source = summary["source"]
    archive_tree_sha256 = tree_digest(
        snapshot.files, snapshot.file_modes, snapshot.directories
    )
    canonical_tree_sha256 = source["tree_sha256"]
    evidence = {
        "maximum_local_status": "STATIC_VALIDATED",
        "source_scripts_executed_by_importer": False,
        "postgresql_16_runtime_evidence": "NOT_RUN",
        "postgresql_17_runtime_evidence": "NOT_RUN",
        "migration_execution_evidence": "NOT_RUN",
        "concurrency_evidence": "NOT_RUN",
        "rls_evidence": "NOT_RUN",
        "failover_evidence": "NOT_RUN",
        "upgrade_evidence": "NOT_RUN",
        "restore_evidence": "NOT_RUN",
        "external_evidence": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
    }
    record = {
        "name": SKILL_NAME,
        "source_path": (SOURCE_RELATIVE / SOURCE_SKILL_RELATIVE).as_posix(),
        "source_sha256": digest(snapshot.files[SOURCE_SKILL_RELATIVE.as_posix()]),
        "source_frontmatter_normalization": {
            "state": "NORMALIZED_WITHOUT_CANONICAL_SOURCE_MUTATION",
            "source_compatibility_moved_to_metadata": True,
            "repository_frontmatter_validated": True,
        },
        "runtime_skill_path": (RUNTIME_RELATIVE / SKILL_NAME / "SKILL.md").as_posix(),
        "runtime_skill_sha256": digest(skill_bytes),
        "runtime_interface_path": (
            RUNTIME_RELATIVE / SKILL_NAME / "agents/openai.yaml"
        ).as_posix(),
        "runtime_interface_sha256": digest(interface_bytes),
        "workspace_skill_path": (WORKSPACE_RELATIVE / SKILL_NAME / "SKILL.md").as_posix(),
        "workspace_skill_sha256": digest(skill_bytes),
        "workspace_interface_path": (
            WORKSPACE_RELATIVE / SKILL_NAME / "agents/openai.yaml"
        ).as_posix(),
        "workspace_interface_sha256": digest(interface_bytes),
        "installed_tree_sha256": tree_sha256,
        "implementation_state": "STATIC_VALIDATED",
        "postgresql_runtime_evidence": "NOT_RUN",
        "external_evidence": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
    }
    manifest = {
        "schema_version": "1.0",
        "namespace": NAMESPACE,
        "source_package": PACKAGE_NAME,
        "source_version": PACKAGE_VERSION,
        "archive": {
            "path": ARCHIVE_RELATIVE.as_posix(),
            "bytes": EXPECTED_ARCHIVE_BYTES,
            "sha256": f"sha256:{EXPECTED_ARCHIVE_SHA256}",
            "entry_count": EXPECTED_ARCHIVE_ENTRIES,
            "file_count": EXPECTED_SOURCE_FILES,
            "directory_count": EXPECTED_SOURCE_DIRECTORIES,
            "uncompressed_bytes": EXPECTED_SOURCE_BYTES,
            "tree_sha256": archive_tree_sha256,
            "directory_mode": "2755",
        },
        "checksums": {
            "path": (SOURCE_RELATIVE / CHECKSUM_PATH).as_posix(),
            "sha256": f"sha256:{EXPECTED_CHECKSUM_SHA256}",
            "entry_count": EXPECTED_CHECKSUM_ENTRIES,
            "coverage": "EXACT_ALL_FILES_EXCEPT_CHECKSUMS_SELF",
        },
        "canonical_source": {
            "path": SOURCE_RELATIVE.as_posix(),
            "file_count": EXPECTED_SOURCE_FILES,
            "directory_count": EXPECTED_SOURCE_DIRECTORIES,
            "bytes": EXPECTED_SOURCE_BYTES,
            "tree_sha256": canonical_tree_sha256,
            "directory_mode_normalization": "ARCHIVE_2755_TO_CANONICAL_0755",
            "files": [
                {**item, "path": (SOURCE_RELATIVE / item["path"]).as_posix()}
                for item in source["inventory"]
            ],
        },
        "source_version_drift": summary["contract"]["source_version_drift"],
        "broken_source_workflow_reference": summary["contract"]
        ["broken_source_workflow_reference"],
        "postgresql_partition_constraint_defect": {
            "state": "PRESERVED_CANONICAL_SOURCE_REQUIRES_COMPATIBILITY_OVERLAY",
            "source_migration": (
                SOURCE_RELATIVE
                / "database/migrations/V020__runs_tasks_sessions_and_recovery.sql"
            ).as_posix(),
            "source_sha256": (
                "sha256:1d9b6641ed8f2f423938ff067de56a33b86dc754220832d423a078b81ac5bc6e"
            ),
            "affected_tables": ["exec.run_event", "exec.session_event"],
            "source_partition_keys": ["run_id", "session_id"],
            "declared_unique_key": ["tenant_id", "event_id"],
            "postgresql_requirement": (
                "every unique key on a partitioned table must include every "
                "partition-key column"
            ),
            "canonical_source_mutated": False,
            "production_resolution": "NOT_APPROVED",
        },
        "postgresql_account_slot_uniqueness_defect": {
            "state": "PRESERVED_CANONICAL_SOURCE_REQUIRES_COMPATIBILITY_OVERLAY",
            "source_migration": (
                SOURCE_RELATIVE
                / "database/migrations/V010__tenancy_projects_jobs_and_admission.sql"
            ).as_posix(),
            "source_sha256": (
                "sha256:ca02afa6f4df7881ad85b1139faf137732a0146dbcf247abf4e40205bca53829"
            ),
            "affected_table": "core.account_task_slot",
            "source_constraint": (
                "UNIQUE NULLS NOT DISTINCT (tenant_id, claimed_by_run_id)"
            ),
            "runtime_requirement": (
                "three unclaimed slots per account and at most one claimed slot "
                "per tenant and run"
            ),
            "compatibility_overlay": (
                "UNIQUE (tenant_id, claimed_by_run_id)"
            ),
            "canonical_source_mutated": False,
            "production_resolution": "NOT_APPROVED",
        },
        "postgresql_temporal_identity_uniqueness_defect": {
            "state": "PRESERVED_CANONICAL_SOURCE_REQUIRES_COMPATIBILITY_OVERLAY",
            "source_migration": (
                SOURCE_RELATIVE
                / "database/migrations/V020__runs_tasks_sessions_and_recovery.sql"
            ).as_posix(),
            "source_sha256": (
                "sha256:1d9b6641ed8f2f423938ff067de56a33b86dc754220832d423a078b81ac5bc6e"
            ),
            "affected_table": "exec.run",
            "source_constraint": (
                "UNIQUE NULLS NOT DISTINCT "
                "(tenant_id, temporal_namespace, temporal_workflow_id, temporal_run_id)"
            ),
            "runtime_requirement": (
                "multiple non-Temporal runs per tenant while preserving uniqueness "
                "when a complete Temporal identity is present"
            ),
            "compatibility_overlay": (
                "UNIQUE (tenant_id, temporal_namespace, temporal_workflow_id, temporal_run_id)"
            ),
            "canonical_source_mutated": False,
            "production_resolution": "NOT_APPROVED",
        },
        "postgresql_claim_ready_task_ambiguity_defect": {
            "state": "PRESERVED_CANONICAL_SOURCE_REQUIRES_COMPATIBILITY_OVERLAY",
            "source_migration": (
                SOURCE_RELATIVE
                / "database/migrations/V090__transactional_runtime_functions.sql"
            ).as_posix(),
            "source_sha256": (
                "sha256:8eb1646c5c0200a81769edc542b26fd6beb3d515bf122b570b140a6c797a6ddf"
            ),
            "affected_function": "exec.claim_ready_task",
            "source_query": (
                "unqualified run_attempt id, tenant_id, run_id, status, and attempt_no "
                "inside a RETURNS TABLE function"
            ),
            "runtime_requirement": (
                "claim one ready task while preserving tenant, run-attempt, lease, "
                "and fencing-token identities"
            ),
            "compatibility_overlay": (
                "qualify the run_attempt relation as ra and every referenced column"
            ),
            "canonical_source_mutated": False,
            "production_resolution": "NOT_APPROVED",
        },
        "installation": {
            "runtime_root": RUNTIME_RELATIVE.as_posix(),
            "workspace_root": WORKSPACE_RELATIVE.as_posix(),
            "runtime_tree_sha256": tree_sha256,
            "workspace_tree_sha256": tree_sha256,
            "dual_root_byte_identical": True,
            "interface_sha256": digest(interface_bytes),
        },
        "skill_count": 1,
        "skills": [record],
        "evidence": evidence,
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )
    return {
        "summary": summary,
        "tree": tree,
        "manifest": manifest,
        "manifest_bytes": manifest_bytes,
    }


def read_installed_tree(root: Path) -> dict[str, bytes]:
    if not root.is_dir() or root.is_symlink():
        fail(f"installed Skill must be a real directory: {root}")
    values: dict[str, bytes] = {}
    directories: set[str] = {""}
    if stat.S_IMODE(root.stat().st_mode) != INSTALLED_DIRECTORY_MODE:
        fail(f"installed Skill root mode drift: {root}")
    for child in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if child.is_symlink():
            fail(f"installed Skill contains a symbolic link: {child}")
        if child.is_file():
            if stat.S_IMODE(child.stat().st_mode) != INSTALLED_FILE_MODE:
                fail(f"installed Skill file mode drift: {child}")
            values[child.relative_to(root).as_posix()] = child.read_bytes()
        elif child.is_dir():
            if stat.S_IMODE(child.stat().st_mode) != INSTALLED_DIRECTORY_MODE:
                fail(f"installed Skill directory mode drift: {child}")
            directories.add(child.relative_to(root).as_posix())
        else:
            fail(f"installed Skill contains an unsupported entry: {child}")
    expected_directories = required_directory_paths(list(values))
    if directories != expected_directories:
        fail(
            "installed Skill directory inventory drift: "
            f"missing={sorted(expected_directories - directories)} "
            f"extra={sorted(directories - expected_directories)}"
        )
    return values


def validate_skill_root(skill_root: Path) -> None:
    valid, message = skill_creator_tools.validate_skill(skill_root)
    if not valid:
        fail(f"normalized Skill is invalid at {skill_root}: {message}")
    interface_path = skill_root / "agents/openai.yaml"
    try:
        interface = yaml.safe_load(interface_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        fail(f"normalized Skill interface is invalid at {interface_path}: {exc}")
    if not isinstance(interface, dict) or set(interface) != {"interface"}:
        fail(f"normalized Skill interface shape changed at {interface_path}")
    fields = interface.get("interface")
    if not isinstance(fields, dict) or set(fields) != {
        "display_name",
        "short_description",
        "default_prompt",
    }:
        fail(f"normalized Skill interface fields changed at {interface_path}")


def validate_installed_skill(repository_root: Path, relative_root: Path) -> None:
    validate_skill_root(repository_root / relative_root / SKILL_NAME)


def check_install(repository_root: Path = ROOT) -> dict[str, Any]:
    expected = build_expected(repository_root)
    failures: list[str] = []
    for relative_root, label in (
        (RUNTIME_RELATIVE, "runtime"),
        (WORKSPACE_RELATIVE, "workspace"),
    ):
        destination = repository_root / relative_root / SKILL_NAME
        validate_repository_directory(
            repository_root,
            destination.parent,
            f"{label} installation",
        )
        try:
            actual = read_installed_tree(destination)
        except IntegrationError as exc:
            failures.append(f"{label}: {exc}")
            continue
        if actual != expected["tree"]:
            missing = sorted(set(expected["tree"]) - set(actual))
            extra = sorted(set(actual) - set(expected["tree"]))
            changed = sorted(
                relative
                for relative in set(actual) & set(expected["tree"])
                if actual[relative] != expected["tree"][relative]
            )
            failures.append(
                f"{label} installed drift: missing={missing} extra={extra} changed={changed}"
            )

    manifest_path = repository_root / DOC_RELATIVE / INSTALL_MANIFEST_NAME
    validate_repository_directory(
        repository_root,
        manifest_path.parent,
        "installed manifest",
    )
    if not manifest_path.is_file() or manifest_path.is_symlink():
        failures.append(f"installed manifest is missing or unsafe: {manifest_path}")
    elif stat.S_IMODE(manifest_path.stat().st_mode) != INSTALLED_FILE_MODE:
        failures.append("installed manifest mode drift")
    elif manifest_path.read_bytes() != expected["manifest_bytes"]:
        failures.append("installed manifest drift")
    if failures:
        fail(f"large-repository database design installation drifted: {failures}")

    for relative_root in (RUNTIME_RELATIVE, WORKSPACE_RELATIVE):
        validate_installed_skill(repository_root, relative_root)
    return expected


def write_tree(destination: Path, values: Mapping[str, bytes]) -> None:
    destination.mkdir(parents=True, exist_ok=False, mode=INSTALLED_DIRECTORY_MODE)
    destination.chmod(INSTALLED_DIRECTORY_MODE)
    for relative, content in sorted(values.items()):
        path = validate_relative_path(relative, "installed")
        target = destination.joinpath(*path.parts)
        target.parent.mkdir(
            parents=True,
            exist_ok=True,
            mode=INSTALLED_DIRECTORY_MODE,
        )
        current = target.parent
        while current != destination.parent:
            current.chmod(INSTALLED_DIRECTORY_MODE)
            if current == destination:
                break
            current = current.parent
        target.write_bytes(content)
        target.chmod(INSTALLED_FILE_MODE)


def previous_manifest_owned(path: Path) -> bool:
    if not path.exists() and not path.is_symlink():
        return False
    if not path.is_file() or path.is_symlink():
        fail(f"installed manifest is not a regular file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        fail(f"installed manifest is invalid: {path}: {exc}")
    if not isinstance(value, dict):
        fail("installed manifest must be an object")
    archive_record = value.get("archive")
    if (
        value.get("namespace") != NAMESPACE
        or value.get("source_package") != PACKAGE_NAME
        or value.get("source_version") != PACKAGE_VERSION
        or not isinstance(archive_record, dict)
        or archive_record.get("sha256")
        != f"sha256:{EXPECTED_ARCHIVE_SHA256}"
    ):
        fail("refusing to overwrite a foreign installed manifest")
    return True


def write_install(repository_root: Path = ROOT) -> dict[str, Any]:
    extract_canonical_source(repository_root)
    expected = build_expected(repository_root)
    manifest_path = repository_root / DOC_RELATIVE / INSTALL_MANIFEST_NAME
    owned = previous_manifest_owned(manifest_path)

    destinations = [
        repository_root / RUNTIME_RELATIVE / SKILL_NAME,
        repository_root / WORKSPACE_RELATIVE / SKILL_NAME,
    ]
    for destination in destinations:
        validate_repository_directory(
            repository_root,
            destination.parent,
            "Skill installation",
        )
    validate_repository_directory(
        repository_root,
        manifest_path.parent,
        "installed manifest",
    )
    if owned:
        # Installed Skill bytes remain immutable. Permit only an explicitly
        # pinned predecessor manifest to migrate to the current deterministic
        # schema; any other drift remains a hard failure.
        current_manifest = manifest_path.read_bytes()
        if current_manifest == expected["manifest_bytes"]:
            return check_install(repository_root)
        current_manifest_sha256 = digest(current_manifest).removeprefix("sha256:")
        if current_manifest_sha256 not in ALLOWED_PREVIOUS_INSTALL_MANIFEST_SHA256:
            fail(
                "refusing to migrate an unrecognized installed manifest: "
                f"sha256:{current_manifest_sha256}"
            )
        for destination in destinations:
            if read_installed_tree(destination) != expected["tree"]:
                fail(
                    "refusing manifest migration while installed Skill bytes drifted: "
                    f"{destination}"
                )
            validate_skill_root(destination)
        manifest_stage = manifest_path.parent / (
            f".{INSTALL_MANIFEST_NAME}.stage.{uuid.uuid4().hex}"
        )
        try:
            manifest_stage.write_bytes(expected["manifest_bytes"])
            manifest_stage.chmod(INSTALLED_FILE_MODE)
            if manifest_stage.read_bytes() != expected["manifest_bytes"]:
                fail("staged installed manifest bytes differ")
            os.replace(manifest_stage, manifest_path)
        finally:
            if manifest_stage.exists() or manifest_stage.is_symlink():
                manifest_stage.unlink()
        return check_install(repository_root)

    for destination in destinations:
        if destination.exists() or destination.is_symlink():
            fail(f"refusing to overwrite an unowned installed Skill: {destination}")
    if manifest_path.exists() or manifest_path.is_symlink():
        fail(f"refusing to overwrite an unowned installed manifest: {manifest_path}")

    staged: list[Path] = []
    installed: list[Path] = []
    try:
        for destination in destinations:
            destination.parent.mkdir(parents=True, exist_ok=True)
            stage = destination.parent / f".{SKILL_NAME}.stage.{uuid.uuid4().hex}"
            write_tree(stage, expected["tree"])
            staged.append(stage)
            if read_installed_tree(stage) != expected["tree"]:
                fail(f"staged installed Skill bytes differ: {stage}")
            validate_skill_root(stage)

        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_stage = manifest_path.parent / (
            f".{INSTALL_MANIFEST_NAME}.stage.{uuid.uuid4().hex}"
        )
        manifest_stage.write_bytes(expected["manifest_bytes"])
        manifest_stage.chmod(INSTALLED_FILE_MODE)
        staged.append(manifest_stage)
        if manifest_stage.read_bytes() != expected["manifest_bytes"]:
            fail("staged installed manifest bytes differ")

        for stage, destination in zip(staged[:2], destinations, strict=True):
            os.replace(stage, destination)
            installed.append(destination)
        os.replace(manifest_stage, manifest_path)
        installed.append(manifest_path)
        result = check_install(repository_root)
    except Exception:
        for path in reversed(installed):
            if path == manifest_path:
                path.unlink(missing_ok=True)
            else:
                shutil.rmtree(path, ignore_errors=True)
        raise
    finally:
        for stage in staged:
            if stage.is_dir() and not stage.is_symlink():
                shutil.rmtree(stage, ignore_errors=True)
            elif stage.exists() or stage.is_symlink():
                stage.unlink(missing_ok=True)

    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="install the pinned package")
    mode.add_argument("--check", action="store_true", help="verify source and installation")
    args = parser.parse_args(argv)
    try:
        result = write_install(ROOT) if args.write else check_install(ROOT)
    except IntegrationError as exc:
        print(f"large-repository database design integration failed: {exc}", file=sys.stderr)
        return 1
    manifest = result["manifest"]
    print(
        "large-repository database design integration passed: "
        f"mode={'write' if args.write else 'check'} "
        f"skills={manifest['skill_count']} "
        f"status={manifest['evidence']['maximum_local_status']} "
        f"certification={manifest['evidence']['certification']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
