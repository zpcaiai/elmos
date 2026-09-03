#!/usr/bin/env python3
"""Publish the bounded Batch 35 composite proof-harness verification pack.

The base and runtime-assurance-delta qualification receipts are untrusted
evidence inputs. This publisher recomputes every receipt binding from
repository bytes before it constructs a limited, self-attested pack. It never
runs source-package content, promotes external evidence, requests
certification, or treats a successful local gate process as certification.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import stat
import tempfile
from typing import AbstractSet, Any, Iterator, Mapping, Sequence
import zipfile


PACKAGE_NAME = "elmos-proof-driven-agentic-harness-repository-semantic-compiler"
PACKAGE_VERSION = "3.0.0"
COMPOSITE_VERSION = "3.1.0"
ARCHIVE_SHA256 = "552268611c3edc55f58c6d4d488adaaeda8a549212cc5dc52c06e4333e0c3e07"
ARCHIVE_BYTES = 5_601_254
ARCHIVE_RELATIVE = Path(
    "skills/subskills/"
    "elmos-proof-driven-agentic-harness-repository-semantic-compiler-v3.0.0.zip"
)
ENGINE_ROOT = Path("engines/proof-driven-harness-engine")
QUALIFIER_RELATIVE = ENGINE_ROOT / "tools/qualify_local.py"
STRUCTURED_RUNNER_RELATIVE = ENGINE_ROOT / "tools/run_structured_unittest.py"
PUBLISHER_RELATIVE = ENGINE_ROOT / "tools/publish_verification_pack.py"
PUBLISHER_TEST_RELATIVE = ENGINE_ROOT / "tests/test_publish_verification_pack.py"
IMPORTER_RELATIVE = Path("tooling/integrate_proof_driven_harness_v3.py")
IMPORTER_TEST_RELATIVE = Path("tests/proof-driven-harness-v3/test_integration.py")
POSTGRES_TEST_RELATIVE = ENGINE_ROOT / "tests/postgres17_integration.py"
RECEIPT_RELATIVE = ENGINE_ROOT / "qualification/local-qualification.json"
DELTA_PACKAGE_NAME = "elmos-v3-harness-runtime-assurance-delta"
DELTA_PACKAGE_VERSION = "3.1.0"
DELTA_ARCHIVE_ROOT = f"{DELTA_PACKAGE_NAME}-v{DELTA_PACKAGE_VERSION}"
DELTA_ARCHIVE_SHA256 = (
    "13ba6f089d3c367affe3e03999418029873d842e07a8c80cfaeeffb4308a7a37"
)
DELTA_ARCHIVE_BYTES = 173_228
DELTA_ARCHIVE_RELATIVE = Path(
    "skills/subskills/elmos-v3-harness-runtime-assurance-delta-v3.1.0.zip"
)
DELTA_QUALIFIER_RELATIVE = ENGINE_ROOT / "tools/qualify_delta.py"
DELTA_IMPORTER_RELATIVE = Path("tooling/integrate_harness_runtime_assurance_delta.py")
DELTA_ACCEPTANCE_BINDINGS_RELATIVE = (
    ENGINE_ROOT / "supply-chain/delta-v3.1-acceptance-bindings.json"
)
DELTA_ENGINE_TEST_PATTERN = "test_delta_*.py"
DELTA_REQUIRED_ENGINE_TESTS = (
    ENGINE_ROOT / "tests/test_delta_contract_closure.py",
    ENGINE_ROOT / "tests/test_delta_migration.py",
    ENGINE_ROOT / "tests/test_delta_qualification.py",
    ENGINE_ROOT / "tests/test_delta_skills.py",
)
DELTA_OPTIONAL_ENGINE_TESTS = (
    ENGINE_ROOT / "tests/test_delta_control_plane.py",
    ENGINE_ROOT / "tests/test_delta_storage.py",
)
DELTA_IMPORTER_TEST_RELATIVE = Path(
    "tests/proof-driven-harness-v3/test_delta_integration.py"
)
DELTA_RECEIPT_RELATIVE = (
    ENGINE_ROOT / "qualification/delta-v3.1/local-qualification.json"
)
DELTA_ACCEPTANCE_SKILLS = (
    ("ELMOS-V3D-001", "elmos-tool-result-interception-commit", "P0"),
    ("ELMOS-V3D-002", "elmos-step-finalized-execution-plan", "P0"),
    ("ELMOS-V3D-003", "elmos-lossless-permission-replay", "P0"),
    ("ELMOS-V3D-004", "elmos-invocation-scoped-capability-lease", "P0"),
    ("ELMOS-V3D-005", "elmos-host-minted-security-context", "P0"),
    ("ELMOS-V3D-006", "elmos-environment-attachment-authority", "P0"),
    ("ELMOS-V3D-007", "elmos-executor-generation-fencing", "P0"),
    ("ELMOS-V3D-008", "elmos-workspace-ownership-lease", "P0"),
    ("ELMOS-V3D-009", "elmos-harness-transport-version-negotiation", "P0"),
    ("ELMOS-V3D-010", "elmos-skill-trust-domain-provenance", "P0"),
    ("ELMOS-V3D-011", "elmos-registered-durable-plugin-events", "P1"),
    ("ELMOS-V3D-012", "elmos-typed-external-ingress", "P1"),
    ("ELMOS-V3D-013", "elmos-subagent-model-execution-spec", "P1"),
)
DELTA_ACCEPTANCE_CASE_SUFFIXES = (
    "A01",
    "A02",
    "A03",
    "A04",
    "A05",
    "NEG-STALE",
    "NEG-REPLAY",
    "RECOVERY",
)
DELTA_ACCEPTANCE_SCENARIOS_PER_SKILL = 8
DELTA_ACCEPTANCE_SCENARIO_COUNT = 104
_DELTA_TEST_SELECTOR_PATTERN = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*){2,}")
PACK_KEY = "proof-driven-harness-v3-local"
PACK_RELATIVE = Path("verification-packs") / PACK_KEY
MAX_RECEIPT_BYTES = 1024 * 1024
MAX_LOG_BYTES = 32 * 1024 * 1024
MAX_REPOSITORY_FILE_BYTES = 128 * 1024 * 1024
GATE_OUTPUTS = frozenset(
    {Path("certification/gate-result.json"), Path("certification/gate-report.md")}
)
EXCLUDED_DIRECTORIES = frozenset(
    {
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "build",
        "dist",
    }
)
SKILL_NAMES = tuple(
    sorted(
        (
            "elmos-goal-specification-kernel",
            "elmos-repository-intelligence-kernel",
            "elmos-repository-semantic-compiler-kernel",
            "elmos-agentic-reasoning-kernel",
            "elmos-transformation-kernel",
            "elmos-proof-verification-kernel",
            "elmos-harness-runtime-kernel",
            "elmos-certification-kernel",
            "elmos-domain-spring-legacy-modernization",
            "elmos-domain-cross-language-conversion",
            "elmos-domain-multi-language-project-generation",
            "elmos-domain-sql-dialect-routine-conversion",
            "elmos-domain-repository-refactoring",
            "elmos-evaluation-trust-gate",
            "elmos-self-improvement-governance",
            "elmos-commercial-operations-finops",
        )
    )
)
COMPONENT_IDS = tuple(
    f"K{kernel}-C{component:02d}"
    for kernel in range(1, 9)
    for component in range(1, 13)
)
RAW_LOG_COMMANDS: Mapping[str, tuple[str, ...]] = {
    "qualification/raw/engine-tests.json": (
        STRUCTURED_RUNNER_RELATIVE.as_posix(),
        "--repo-root",
        ".",
        "--start-directory",
        "engines/proof-driven-harness-engine/tests",
        "--pattern",
        "test_*.py",
    ),
    "qualification/raw/package-integration-tests.json": (
        STRUCTURED_RUNNER_RELATIVE.as_posix(),
        "--repo-root",
        ".",
        "--start-directory",
        "tests/proof-driven-harness-v3",
        "--pattern",
        "test_*.py",
    ),
    "qualification/raw/archive-installation-check.json": (
        "tooling/integrate_proof_driven_harness_v3.py",
        "--check",
        "--qualification-phase",
    ),
}
DELTA_RAW_LOG_COMMANDS: Mapping[str, tuple[str, ...]] = {
    "qualification/delta-v3.1/raw/delta-engine-tests.json": (
        STRUCTURED_RUNNER_RELATIVE.as_posix(),
        "--repo-root",
        ".",
        "--start-directory",
        (ENGINE_ROOT / "tests").as_posix(),
        "--pattern",
        DELTA_ENGINE_TEST_PATTERN,
    ),
    "qualification/delta-v3.1/raw/delta-importer-tests.json": (
        STRUCTURED_RUNNER_RELATIVE.as_posix(),
        "--repo-root",
        ".",
        "--start-directory",
        "tests/proof-driven-harness-v3",
        "--pattern",
        "test_delta_integration.py",
    ),
    "qualification/delta-v3.1/raw/delta-installation-check.json": (
        DELTA_IMPORTER_RELATIVE.as_posix(),
        "--repo-root",
        ".",
        "--check",
    ),
}
POSTGRES_RAW_LOG = "qualification/raw/postgres17-integration.json"
POSTGRES_RAW_COMMAND = (
    STRUCTURED_RUNNER_RELATIVE.as_posix(),
    "--repo-root",
    ".",
    "--start-directory",
    "engines/proof-driven-harness-engine/tests",
    "--pattern",
    "postgres17_integration.py",
)
POSTGRES_VERSION_OUTPUT_PATTERN = re.compile(
    r"initdb \(PostgreSQL\) 17\.5(?:[ \t]+\([^()\r\n]+\))?"
)
POSTGRES_TOOL_VERSION_OUTPUT_PATTERNS = {
    name: re.compile(
        rf"{re.escape(name)} \(PostgreSQL\) 17\.5(?:[ \t]+\([^()\r\n]+\))?"
    )
    for name in ("initdb", "pg_ctl", "psql", "postgres")
}
STRUCTURED_RAW_LOGS = frozenset(
    {
        "qualification/raw/engine-tests.json",
        "qualification/raw/package-integration-tests.json",
        POSTGRES_RAW_LOG,
    }
)
TEST_TOTAL_KEYS = frozenset(
    {
        "selected",
        "passed",
        "failed",
        "errors",
        "skipped",
        "expected_failures",
        "unexpected_successes",
    }
)


class VerificationPackError(RuntimeError):
    """Raised when evidence or output state fails closed."""


@dataclass(frozen=True)
class FileIdentity:
    device: int
    inode: int
    mode: int
    size: int
    mtime_ns: int
    ctime_ns: int


@dataclass(frozen=True)
class FileSnapshot:
    payload: bytes
    identity: FileIdentity


@dataclass(frozen=True)
class ValidatedQualification:
    receipt_payload: bytes
    receipt: Mapping[str, Any]
    receipt_sha256: str
    engine_records: tuple[Mapping[str, Any], ...]
    engine_tree_sha256: str
    archive: FileSnapshot
    qualifier: FileSnapshot
    raw_logs: Mapping[str, FileSnapshot]
    raw_records: Mapping[str, Mapping[str, Any]]
    structured_results: Mapping[str, Mapping[str, Any]]
    delta_receipt_payload: bytes
    delta_receipt: Mapping[str, Any]
    delta_receipt_sha256: str
    delta_archive: FileSnapshot
    delta_qualifier: FileSnapshot
    delta_raw_logs: Mapping[str, FileSnapshot]
    delta_raw_records: Mapping[str, Mapping[str, Any]]
    delta_structured_results: Mapping[str, Mapping[str, Any]]
    observed_files: Mapping[Path, FileIdentity]

    @property
    def test_count(self) -> int:
        return int(self.receipt["tests"]["passed"]) + int(
            self.delta_receipt["tests"]["passed"]
        )


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def digest(payload: bytes) -> str:
    return "sha256:" + sha256_hex(payload)


def _identity(metadata: os.stat_result) -> FileIdentity:
    return FileIdentity(
        device=metadata.st_dev,
        inode=metadata.st_ino,
        mode=metadata.st_mode,
        size=metadata.st_size,
        mtime_ns=metadata.st_mtime_ns,
        ctime_ns=metadata.st_ctime_ns,
    )


def _directory_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _relative_parts(relative: Path) -> tuple[str, ...]:
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise VerificationPackError(f"unsafe repository-relative path: {relative}")
    parts = tuple(relative.parts)
    if any(part in {"", ".", ".."} or "/" in part or "\x00" in part for part in parts):
        raise VerificationPackError(f"unsafe repository-relative path: {relative}")
    return parts


@contextmanager
def repository_anchor(
    repository_root: Path,
) -> Iterator[tuple[Path, int, FileIdentity]]:
    absolute = Path(os.path.abspath(os.fspath(repository_root)))
    try:
        descriptor = os.open(absolute, _directory_flags())
    except OSError as exc:
        raise VerificationPackError(
            f"cannot safely open repository root {absolute}: {exc}"
        ) from exc
    try:
        identity = _identity(os.fstat(descriptor))
        pathname = _identity(os.stat(absolute, follow_symlinks=False))
        if (
            not stat.S_ISDIR(identity.mode)
            or not stat.S_ISDIR(pathname.mode)
            or (identity.device, identity.inode) != (pathname.device, pathname.inode)
        ):
            raise VerificationPackError(
                f"repository root is not a stable real directory: {absolute}"
            )
        yield absolute, descriptor, identity
    finally:
        os.close(descriptor)


def assert_repository_anchor(absolute: Path, expected: FileIdentity) -> None:
    try:
        current = _identity(os.stat(absolute, follow_symlinks=False))
    except OSError as exc:
        raise VerificationPackError(
            f"repository root pathname cannot be revalidated: {absolute}: {exc}"
        ) from exc
    if not stat.S_ISDIR(current.mode) or (current.device, current.inode) != (
        expected.device,
        expected.inode,
    ):
        raise VerificationPackError(
            f"repository root pathname identity changed: {absolute}"
        )


def _open_directory_at(
    root_fd: int,
    relative: Path,
    *,
    missing_ok: bool = False,
    create: bool = False,
    mode: int = 0o755,
) -> int | None:
    parts = _relative_parts(relative)
    current = os.dup(root_fd)
    try:
        for part in parts:
            if create:
                try:
                    os.mkdir(part, mode, dir_fd=current)
                except FileExistsError:
                    pass
                except OSError as exc:
                    raise VerificationPackError(
                        f"cannot create anchored directory {relative}: {exc}"
                    ) from exc
            try:
                following = os.open(part, _directory_flags(), dir_fd=current)
            except FileNotFoundError:
                if missing_ok and not create:
                    os.close(current)
                    return None
                raise VerificationPackError(f"missing anchored directory: {relative}")
            except OSError as exc:
                raise VerificationPackError(
                    f"unsafe anchored directory component {part!r} in {relative}: {exc}"
                ) from exc
            opened = os.fstat(following)
            if not stat.S_ISDIR(opened.st_mode):
                os.close(following)
                raise VerificationPackError(
                    f"anchored path is not a directory: {relative}"
                )
            os.close(current)
            current = following
        return current
    except BaseException:
        try:
            os.close(current)
        except OSError:
            pass
        raise


def _open_parent_at(
    root_fd: int,
    relative: Path,
    *,
    missing_ok: bool = False,
) -> tuple[int, str] | None:
    parts = _relative_parts(relative)
    if len(parts) == 1:
        return os.dup(root_fd), parts[0]
    parent = _open_directory_at(
        root_fd,
        Path(*parts[:-1]),
        missing_ok=missing_ok,
    )
    if parent is None:
        return None
    return parent, parts[-1]


def _read_descriptor(descriptor: int, limit: int, label: str) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(descriptor, min(1024 * 1024, limit + 1 - total))
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise VerificationPackError(f"file exceeds byte limit: {label}")
        chunks.append(chunk)
    return b"".join(chunks)


def read_file_at(
    root_fd: int,
    relative: Path,
    *,
    limit: int,
    missing_ok: bool = False,
) -> FileSnapshot | None:
    parent = _open_parent_at(root_fd, relative, missing_ok=missing_ok)
    if parent is None:
        return None
    parent_fd, name = parent
    descriptor = -1
    try:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(name, flags, dir_fd=parent_fd)
        except FileNotFoundError:
            if missing_ok:
                return None
            raise VerificationPackError(f"missing anchored file: {relative}")
        except OSError as exc:
            raise VerificationPackError(
                f"cannot safely open anchored file {relative}: {exc}"
            ) from exc
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise VerificationPackError(f"not a regular file: {relative}")
        if before.st_size > limit:
            raise VerificationPackError(f"file exceeds byte limit: {relative}")
        payload = _read_descriptor(descriptor, limit, str(relative))
        after = os.fstat(descriptor)
        if _identity(before) != _identity(after) or len(payload) != before.st_size:
            raise VerificationPackError(f"file changed while reading: {relative}")
        return FileSnapshot(payload=payload, identity=_identity(before))
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent_fd)


def lstat_at(root_fd: int, relative: Path) -> os.stat_result | None:
    parent = _open_parent_at(root_fd, relative, missing_ok=True)
    if parent is None:
        return None
    parent_fd, name = parent
    try:
        try:
            return os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            return None
    finally:
        os.close(parent_fd)


def revalidate_file_at(
    root_fd: int,
    relative: Path,
    expected: FileIdentity,
) -> None:
    current = lstat_at(root_fd, relative)
    if (
        current is None
        or _identity(current) != expected
        or not stat.S_ISREG(current.st_mode)
    ):
        raise VerificationPackError(f"file pathname identity changed: {relative}")


def _load_json(payload: bytes, label: str) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise VerificationPackError(f"duplicate JSON key in {label}: {key}")
            result[key] = value
        return result

    try:
        return json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda value: (_ for _ in ()).throw(
                VerificationPackError(f"non-finite JSON value in {label}: {value}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationPackError(f"invalid JSON in {label}: {exc}") from exc


def _exact_mapping(value: Any, keys: AbstractSet[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise VerificationPackError(f"{label} fields do not match the fixed contract")
    return value


def _nonnegative_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise VerificationPackError(f"{label} must be a non-negative integer")
    return int(value)


def _engine_excluded(relative: PurePosixPath) -> bool:
    if not relative.parts or relative.parts[0] == "qualification":
        return True
    if any(
        part in EXCLUDED_DIRECTORIES or part.endswith(".egg-info")
        for part in relative.parts
    ):
        return True
    return (
        relative.name.endswith(".pyc")
        or relative.name == ".coverage"
        or relative.name.startswith(".coverage.")
        or relative.name == "coverage.xml"
    )


def _walk_engine(
    directory_fd: int,
    prefix: tuple[str, ...],
    records: list[dict[str, Any]],
) -> None:
    before = _identity(os.fstat(directory_fd))
    for name in sorted(os.listdir(directory_fd)):
        if name in {"", ".", ".."} or "/" in name or "\x00" in name:
            raise VerificationPackError(f"unsafe engine member name: {name!r}")
        parts = (*prefix, name)
        relative = PurePosixPath(*parts)
        if _engine_excluded(relative):
            continue
        metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if stat.S_ISDIR(metadata.st_mode):
            child_fd = os.open(name, _directory_flags(), dir_fd=directory_fd)
            try:
                opened = os.fstat(child_fd)
                if (opened.st_dev, opened.st_ino) != (
                    metadata.st_dev,
                    metadata.st_ino,
                ):
                    raise VerificationPackError(
                        f"engine directory raced open: {relative}"
                    )
                _walk_engine(child_fd, parts, records)
            finally:
                os.close(child_fd)
        elif stat.S_ISREG(metadata.st_mode):
            flags = (
                os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
            )
            descriptor = os.open(name, flags, dir_fd=directory_fd)
            try:
                opened = os.fstat(descriptor)
                if (opened.st_dev, opened.st_ino) != (
                    metadata.st_dev,
                    metadata.st_ino,
                ):
                    raise VerificationPackError(f"engine file raced open: {relative}")
                payload = _read_descriptor(
                    descriptor,
                    MAX_REPOSITORY_FILE_BYTES,
                    relative.as_posix(),
                )
                after = os.fstat(descriptor)
                if (
                    _identity(opened) != _identity(after)
                    or len(payload) != opened.st_size
                ):
                    raise VerificationPackError(
                        f"engine file changed while reading: {relative}"
                    )
            finally:
                os.close(descriptor)
            records.append(
                {
                    "path": relative.as_posix(),
                    "sha256": sha256_hex(payload),
                    "bytes": len(payload),
                    "mode": format(stat.S_IMODE(opened.st_mode), "04o"),
                }
            )
        else:
            raise VerificationPackError(
                f"special or linked engine member is forbidden: {relative}"
            )
    if before != _identity(os.fstat(directory_fd)):
        raise VerificationPackError(
            f"engine directory changed while reading: {'/'.join(prefix) or '.'}"
        )


def engine_inventory_at(root_fd: int) -> tuple[Mapping[str, Any], ...]:
    engine_fd = _open_directory_at(root_fd, ENGINE_ROOT)
    assert engine_fd is not None
    root_identity = _identity(os.fstat(engine_fd))
    try:
        records: list[dict[str, Any]] = []
        _walk_engine(engine_fd, (), records)
    finally:
        os.close(engine_fd)
    records.sort(key=lambda item: item["path"])
    if not records:
        raise VerificationPackError("engine tree is empty")
    current = lstat_at(root_fd, ENGINE_ROOT)
    if current is None or (
        current.st_dev,
        current.st_ino,
    ) != (root_identity.device, root_identity.inode):
        raise VerificationPackError("engine root identity changed")
    return tuple(records)


def _validate_execution_environment(
    root_fd: int,
    value: Any,
    *,
    expected_tool: Path,
    label: str,
) -> Mapping[str, Any]:
    environment = _exact_mapping(
        value,
        {
            "schema_version",
            "os",
            "python",
            "tool",
            "packages",
            "postgresql",
            "evidence_boundary",
        },
        f"execution environment {label}",
    )
    os_record = _exact_mapping(
        environment["os"],
        {"system", "release", "version", "machine"},
        f"operating system {label}",
    )
    python = _exact_mapping(
        environment["python"],
        {
            "implementation",
            "version",
            "cache_tag",
            "executable",
            "executable_sha256",
        },
        f"python environment {label}",
    )
    tool = _exact_mapping(
        environment["tool"],
        {"path", "version", "sha256"},
        f"tool environment {label}",
    )
    boundary = _exact_mapping(
        environment["evidence_boundary"],
        {
            "classification",
            "external_evidence",
            "independent_verification",
            "certification",
        },
        f"environment evidence boundary {label}",
    )
    if (
        environment["schema_version"] != "1.0.0"
        or any(not isinstance(item, str) or not item for item in os_record.values())
        or any(
            not isinstance(python[key], str) or not python[key]
            for key in ("implementation", "version", "cache_tag", "executable")
        )
        or not Path(python["executable"]).is_absolute()
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", str(python["executable_sha256"]))
        or tool["path"] != expected_tool.as_posix()
        or tool["version"] != PACKAGE_VERSION
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", str(tool["sha256"]))
        or boundary
        != {
            "classification": "LOCAL_EXECUTED_SELF_ATTESTED",
            "external_evidence": "NOT_RUN",
            "independent_verification": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }
    ):
        raise VerificationPackError(
            f"execution environment identity is invalid: {label}"
        )
    packages = environment["packages"]
    if (
        not isinstance(packages, dict)
        or any(
            not isinstance(key, str)
            or not key
            or not isinstance(package_version, str)
            or not package_version
            for key, package_version in packages.items()
        )
        or "psycopg" not in packages
        or "psycopg-binary" not in packages
    ):
        raise VerificationPackError(
            f"execution dependency versions are invalid: {label}"
        )
    if not isinstance(environment["postgresql"], dict):
        raise VerificationPackError(f"PostgreSQL environment is invalid: {label}")
    tool_snapshot = read_file_at(
        root_fd,
        expected_tool,
        limit=MAX_REPOSITORY_FILE_BYTES,
    )
    assert tool_snapshot is not None
    if tool["sha256"] != digest(tool_snapshot.payload):
        raise VerificationPackError(f"qualification tool digest drift: {label}")
    return environment


def _validate_structured_results(
    root_fd: int,
    stdout: str,
    *,
    path: str,
    commands: Mapping[str, tuple[str, ...]] | None = None,
) -> tuple[Mapping[str, Any], int]:
    result = _exact_mapping(
        _load_json(stdout.encode("utf-8"), f"structured stdout {path}"),
        {
            "schema_version",
            "kind",
            "status",
            "discovery",
            "totals",
            "outcomes",
            "runner_output",
            "captured_stdout",
            "captured_stderr",
            "evidence_boundary",
        },
        f"structured test results {path}",
    )
    discovery = _exact_mapping(
        result["discovery"],
        {"start_directory", "pattern"},
        f"test discovery {path}",
    )
    if commands is not None:
        command = commands[path]
    else:
        command = (
            POSTGRES_RAW_COMMAND if path == POSTGRES_RAW_LOG else RAW_LOG_COMMANDS[path]
        )
    expected_discovery = {
        "start_directory": command[4],
        "pattern": command[6],
    }
    totals = _exact_mapping(result["totals"], TEST_TOTAL_KEYS, f"test totals {path}")
    normalized_totals = {
        key: _nonnegative_integer(totals[key], f"{path} {key}")
        for key in TEST_TOTAL_KEYS
    }
    outcomes = result["outcomes"]
    boundary = _exact_mapping(
        result["evidence_boundary"],
        {
            "classification",
            "external_evidence",
            "independent_verification",
            "certification",
        },
        f"structured result boundary {path}",
    )
    if (
        result["schema_version"] != "1.0.0"
        or result["kind"] != "elmos.proof-harness.structured-unittest-results"
        or result["status"] != "PASS"
        or discovery != expected_discovery
        or not isinstance(outcomes, list)
        or len(outcomes) != normalized_totals["selected"]
        or normalized_totals["selected"] <= 0
        or normalized_totals["passed"] != normalized_totals["selected"]
        or any(
            normalized_totals[key] != 0
            for key in TEST_TOTAL_KEYS.difference({"selected", "passed"})
        )
        or not isinstance(result["runner_output"], str)
        or not isinstance(result["captured_stdout"], str)
        or not isinstance(result["captured_stderr"], str)
        or boundary
        != {
            "classification": "LOCAL_EXECUTED_SELF_ATTESTED",
            "external_evidence": "NOT_RUN",
            "independent_verification": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }
    ):
        raise VerificationPackError(f"structured test result contract failed: {path}")
    permitted_root = Path(expected_discovery["start_directory"])
    selectors: set[str] = set()
    for index, raw_outcome in enumerate(outcomes):
        if not isinstance(raw_outcome, dict):
            raise VerificationPackError(
                f"structured outcome is not an object: {path}#{index}"
            )
        required = {
            "selector",
            "source_path",
            "source_sha256",
            "selector_source_binding_sha256",
            "status",
            "duration_milliseconds",
        }
        actual_fields = set(raw_outcome)
        if actual_fields != required and actual_fields != required | {"detail"}:
            raise VerificationPackError(
                f"structured outcome fields are not exact: {path}#{index}"
            )
        selector = raw_outcome["selector"]
        source_path = raw_outcome["source_path"]
        if (
            not isinstance(selector, str)
            or not selector
            or selector in selectors
            or not isinstance(source_path, str)
            or not source_path
            or raw_outcome["status"] != "PASSED"
            or not re.fullmatch(
                r"sha256:[0-9a-f]{64}", str(raw_outcome["source_sha256"])
            )
            or not re.fullmatch(
                r"sha256:[0-9a-f]{64}",
                str(raw_outcome["selector_source_binding_sha256"]),
            )
        ):
            raise VerificationPackError(
                f"structured outcome identity is invalid: {path}#{index}"
            )
        _nonnegative_integer(
            raw_outcome["duration_milliseconds"],
            f"structured outcome duration {path}#{index}",
        )
        source_relative = Path(*PurePosixPath(source_path).parts)
        try:
            source_relative.relative_to(permitted_root)
        except ValueError as exc:
            raise VerificationPackError(
                f"structured test source escapes discovery root: {source_path}"
            ) from exc
        source_snapshot = read_file_at(
            root_fd,
            source_relative,
            limit=MAX_REPOSITORY_FILE_BYTES,
        )
        assert source_snapshot is not None
        binding = {
            "selector": selector,
            "source_path": source_path,
            "source_sha256": digest(source_snapshot.payload),
        }
        if (
            raw_outcome["source_sha256"] != binding["source_sha256"]
            or raw_outcome["selector_source_binding_sha256"]
            != digest(canonical_bytes(binding))
            or not selector.startswith(source_relative.stem + ".")
        ):
            raise VerificationPackError(
                f"structured selector/source binding drift: {selector}"
            )
        selectors.add(selector)
    return result, normalized_totals["passed"]


def _validate_raw_log(
    root_fd: int,
    reference: Any,
    *,
    allowed_commands: Mapping[str, tuple[str, ...]],
) -> tuple[
    str,
    FileSnapshot,
    Mapping[str, Any],
    Mapping[str, Any] | None,
    int,
    Path,
]:
    ref = _exact_mapping(reference, {"path", "sha256", "bytes"}, "raw log reference")
    path = ref["path"]
    if path not in allowed_commands:
        raise VerificationPackError(f"unexpected qualification raw log: {path!r}")
    if not isinstance(ref["sha256"], str) or not re.fullmatch(
        r"[0-9a-f]{64}", ref["sha256"]
    ):
        raise VerificationPackError(f"invalid raw log digest: {path}")
    byte_count = _nonnegative_integer(ref["bytes"], f"raw log bytes {path}")
    repository_path = ENGINE_ROOT / Path(*PurePosixPath(path).parts)
    snapshot = read_file_at(root_fd, repository_path, limit=MAX_LOG_BYTES)
    assert snapshot is not None
    if (
        len(snapshot.payload) != byte_count
        or sha256_hex(snapshot.payload) != ref["sha256"]
    ):
        raise VerificationPackError(f"raw log digest mismatch: {path}")
    record = _exact_mapping(
        _load_json(snapshot.payload, path),
        {
            "schema_version",
            "name",
            "argv",
            "cwd",
            "returncode",
            "timed_out",
            "wall_clock_milliseconds",
            "stdout",
            "stderr",
            "execution_environment",
        },
        f"raw log {path}",
    )
    argv = record["argv"]
    if (
        record["schema_version"] != "1.0.0"
        or record["name"] != PurePosixPath(path).stem
        or record["cwd"] != "."
        or not isinstance(argv, list)
        or not argv
        or any(not isinstance(item, str) or not item for item in argv)
        or tuple(argv[1:]) != allowed_commands[path]
        or record["returncode"] != 0
        or isinstance(record["returncode"], bool)
        or record["timed_out"] is not False
        or not isinstance(record["stdout"], str)
        or not isinstance(record["stderr"], str)
    ):
        raise VerificationPackError(f"raw log execution contract failed: {path}")
    _nonnegative_integer(record["wall_clock_milliseconds"], f"duration {path}")
    expected_tool = (
        STRUCTURED_RUNNER_RELATIVE if path in STRUCTURED_RAW_LOGS else IMPORTER_RELATIVE
    )
    validated_environment = _validate_execution_environment(
        root_fd,
        record["execution_environment"],
        expected_tool=expected_tool,
        label=path,
    )
    if argv[0] != validated_environment["python"]["executable"]:
        raise VerificationPackError(
            f"raw log Python executable binding failed: {path}"
        )
    structured: Mapping[str, Any] | None = None
    passed = 0
    if path in STRUCTURED_RAW_LOGS:
        structured, passed = _validate_structured_results(
            root_fd,
            record["stdout"],
            path=path,
        )
    return path, snapshot, record, structured, passed, repository_path


def _delta_acceptance_source_scenarios(
    payload: bytes,
    *,
    skill_id: str,
    priority: str,
) -> list[tuple[str, str]]:
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise VerificationPackError("delta acceptance source is not UTF-8") from exc
    if "\x00" in text or "\r" in text:
        raise VerificationPackError("delta acceptance source line content is invalid")
    scenarios: list[tuple[str, str]] = []
    current: str | None = None
    for line in text.splitlines():
        identifier = re.fullmatch(
            r"\s*- id: (ELMOS-V3D-\d{3}-(?:A0[1-5]|NEG-STALE|NEG-REPLAY|RECOVERY))\s*",
            line,
        )
        if identifier is not None:
            if current is not None:
                raise VerificationPackError(
                    "delta acceptance scenario lacks an exact priority"
                )
            current = identifier.group(1)
            continue
        source_priority = re.fullmatch(r"\s+priority: (P0|P1)\s*", line)
        if current is not None and source_priority is not None:
            scenarios.append((current, source_priority.group(1)))
            current = None
    expected_ids = [f"{skill_id}-{suffix}" for suffix in DELTA_ACCEPTANCE_CASE_SUFFIXES]
    if current is not None or [item[0] for item in scenarios] != expected_ids:
        raise VerificationPackError(
            f"delta acceptance source scenario inventory drifted: {skill_id}"
        )
    return scenarios


def _validate_delta_acceptance_bindings(
    payload: bytes,
    archive_payload: bytes,
) -> Mapping[str, Any]:
    value = _exact_mapping(
        _load_json(payload, DELTA_ACCEPTANCE_BINDINGS_RELATIVE.as_posix()),
        {
            "schema_version",
            "kind",
            "package",
            "source_archive",
            "binding_semantics",
            "expected_skill_count",
            "expected_scenarios_per_skill",
            "expected_scenario_count",
            "skills",
        },
        "delta acceptance bindings",
    )
    if (
        value["schema_version"] != "1.0.0"
        or value["kind"] != "elmos.harness-runtime-assurance-delta.acceptance-bindings"
        or value["package"] != f"{DELTA_PACKAGE_NAME}@{DELTA_PACKAGE_VERSION}"
        or value["source_archive"]
        != {
            "path": DELTA_ARCHIVE_RELATIVE.as_posix(),
            "sha256": "sha256:" + DELTA_ARCHIVE_SHA256,
            "bytes": DELTA_ARCHIVE_BYTES,
            "executed": False,
        }
        or value["binding_semantics"]
        != {
            "classification": "STATIC_TRACEABILITY_ONLY",
            "successful_local_result_boundary": "LOCAL_EXECUTED_SELF_ATTESTED",
            "target_environment": "NOT_RUN",
            "independent_verification": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
            "static_mapping_is_execution_evidence": False,
        }
        or value["expected_skill_count"] != len(DELTA_ACCEPTANCE_SKILLS)
        or value["expected_scenarios_per_skill"] != DELTA_ACCEPTANCE_SCENARIOS_PER_SKILL
        or value["expected_scenario_count"] != DELTA_ACCEPTANCE_SCENARIO_COUNT
    ):
        raise VerificationPackError("delta acceptance binding header drifted")
    skills = value["skills"]
    if not isinstance(skills, list) or len(skills) != len(DELTA_ACCEPTANCE_SKILLS):
        raise VerificationPackError("delta acceptance skill inventory drifted")
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_payload), "r")
    except zipfile.BadZipFile as exc:
        raise VerificationPackError("delta acceptance source ZIP is invalid") from exc
    cases: list[dict[str, Any]] = []
    observed_ids: set[str] = set()
    with archive:
        members = archive.infolist()
        member_names = [member.filename for member in members]
        for raw_skill, (skill_id, skill, priority) in zip(
            skills, DELTA_ACCEPTANCE_SKILLS, strict=True
        ):
            skill_record = _exact_mapping(
                raw_skill,
                {"skill", "priority", "source_acceptance", "cases"},
                "delta acceptance skill binding",
            )
            expected_member = (
                f"{DELTA_ARCHIVE_ROOT}/payload/skills/extensions/"
                f"{priority}/{skill}/acceptance.yaml"
            )
            if member_names.count(expected_member) != 1:
                raise VerificationPackError(
                    f"delta acceptance source is missing or duplicated: {skill}"
                )
            info = archive.getinfo(expected_member)
            source_payload = archive.read(info)
            expected_source = {
                "archive_member": expected_member,
                "sha256": digest(source_payload),
                "bytes": len(source_payload),
                "executed": False,
            }
            source = _exact_mapping(
                skill_record["source_acceptance"],
                {"archive_member", "sha256", "bytes", "executed"},
                "delta acceptance source binding",
            )
            if (
                skill_record["skill"] != skill
                or skill_record["priority"] != priority
                or source != expected_source
            ):
                raise VerificationPackError(
                    f"delta acceptance source binding drifted: {skill}"
                )
            source_scenarios = _delta_acceptance_source_scenarios(
                source_payload,
                skill_id=skill_id,
                priority=priority,
            )
            raw_cases = skill_record["cases"]
            if (
                not isinstance(raw_cases, list)
                or len(raw_cases) != DELTA_ACCEPTANCE_SCENARIOS_PER_SKILL
            ):
                raise VerificationPackError(
                    f"delta acceptance cases are incomplete: {skill}"
                )
            for raw_case, (acceptance_id, source_priority) in zip(
                raw_cases, source_scenarios, strict=True
            ):
                case = _exact_mapping(
                    raw_case,
                    {
                        "acceptance_id",
                        "priority",
                        "repository_test_selectors",
                        "local_evidence_boundary",
                        "target_environment",
                        "certification",
                    },
                    "delta acceptance case binding",
                )
                selectors = case["repository_test_selectors"]
                if (
                    case["acceptance_id"] != acceptance_id
                    or acceptance_id in observed_ids
                    or case["priority"] != source_priority
                    or not isinstance(selectors, list)
                    or not 1 <= len(selectors) <= 8
                    or any(
                        not isinstance(selector, str)
                        or len(selector) > 1024
                        or _DELTA_TEST_SELECTOR_PATTERN.fullmatch(selector) is None
                        for selector in selectors
                    )
                    or len(set(selectors)) != len(selectors)
                    or case["local_evidence_boundary"] != "LOCAL_EXECUTED_SELF_ATTESTED"
                    or case["target_environment"] != "NOT_RUN"
                    or case["certification"] != "NOT_CERTIFIED"
                ):
                    raise VerificationPackError(
                        f"delta acceptance case binding drifted: {acceptance_id}"
                    )
                observed_ids.add(acceptance_id)
                cases.append(
                    {
                        "acceptance_id": acceptance_id,
                        "priority": source_priority,
                        "skill": skill,
                        "source_acceptance_sha256": expected_source["sha256"],
                        "repository_test_selectors": list(selectors),
                    }
                )
    if len(cases) != DELTA_ACCEPTANCE_SCENARIO_COUNT:
        raise VerificationPackError("delta acceptance binding is not exactly 13x8")
    return {
        "path": DELTA_ACCEPTANCE_BINDINGS_RELATIVE.as_posix(),
        "sha256": digest(payload),
        "skills": len(DELTA_ACCEPTANCE_SKILLS),
        "scenarios_per_skill": DELTA_ACCEPTANCE_SCENARIOS_PER_SKILL,
        "scenarios": DELTA_ACCEPTANCE_SCENARIO_COUNT,
        "mapping_classification": "STATIC_TRACEABILITY_ONLY",
        "static_mapping_is_execution_evidence": False,
        "cases": cases,
    }


def _expected_delta_acceptance_receipt(
    bindings: Mapping[str, Any],
    outcomes: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    by_selector: dict[str, Mapping[str, Any]] = {}
    for outcome in outcomes:
        selector = outcome.get("selector")
        if not isinstance(selector, str) or selector in by_selector:
            raise VerificationPackError("delta acceptance outcomes contain duplicates")
        by_selector[selector] = outcome
    raw_cases = bindings["cases"]
    assert isinstance(raw_cases, list)
    expected_results: list[dict[str, Any]] = []
    priorities = {"P0": 0, "P1": 0}
    for case in raw_cases:
        assert isinstance(case, Mapping)
        priority = str(case["priority"])
        priorities[priority] += 1
        selectors = case["repository_test_selectors"]
        assert isinstance(selectors, list)
        evidence: list[dict[str, str]] = []
        for selector in selectors:
            bound_outcome = by_selector.get(str(selector))
            if bound_outcome is None or bound_outcome.get("status") != "PASSED":
                raise VerificationPackError(
                    f"delta acceptance selector did not pass: {case['acceptance_id']}:{selector}"
                )
            evidence.append(
                {
                    "selector": str(selector),
                    "source_path": str(bound_outcome["source_path"]),
                    "source_sha256": str(bound_outcome["source_sha256"]),
                }
            )
        expected_results.append(
            {
                "acceptance_id": case["acceptance_id"],
                "skill": case["skill"],
                "priority": priority,
                "source_acceptance_sha256": case["source_acceptance_sha256"],
                "repository_test_selectors": list(selectors),
                "repository_test_evidence": evidence,
                "local_result": "PASSED",
                "local_evidence_boundary": "LOCAL_EXECUTED_SELF_ATTESTED",
                "target_environment": "NOT_RUN",
                "certification": "NOT_CERTIFIED",
            }
        )
    return {
        "binding_path": bindings["path"],
        "binding_sha256": bindings["sha256"],
        "mapping_classification": "STATIC_TRACEABILITY_ONLY",
        "static_mapping_is_execution_evidence": False,
        "skills": len(DELTA_ACCEPTANCE_SKILLS),
        "scenarios_per_skill": DELTA_ACCEPTANCE_SCENARIOS_PER_SKILL,
        "scenarios": DELTA_ACCEPTANCE_SCENARIO_COUNT,
        "local_cases": {
            "passed": DELTA_ACCEPTANCE_SCENARIO_COUNT,
            "failed": 0,
            "p0_passed": priorities["P0"],
            "p1_passed": priorities["P1"],
            "evidence_boundary": "LOCAL_EXECUTED_SELF_ATTESTED",
        },
        "target_environment": "NOT_RUN",
        "independent_verification": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
        "case_results": expected_results,
    }


def _validate_delta_acceptance_receipt(
    value: Any,
    bindings: Mapping[str, Any],
    outcomes: Sequence[Mapping[str, Any]],
) -> None:
    if value != _expected_delta_acceptance_receipt(bindings, outcomes):
        raise VerificationPackError("delta acceptance receipt evidence drifted")


def _validate_delta_qualification(
    root_fd: int,
    records: tuple[Mapping[str, Any], ...],
) -> tuple[
    FileSnapshot,
    Mapping[str, Any],
    FileSnapshot,
    FileSnapshot,
    Mapping[str, FileSnapshot],
    Mapping[str, Mapping[str, Any]],
    Mapping[str, Mapping[str, Any]],
    Mapping[Path, FileIdentity],
]:
    receipt_snapshot = read_file_at(
        root_fd, DELTA_RECEIPT_RELATIVE, limit=MAX_RECEIPT_BYTES
    )
    assert receipt_snapshot is not None
    receipt = _exact_mapping(
        _load_json(receipt_snapshot.payload, DELTA_RECEIPT_RELATIVE.as_posix()),
        {
            "schema_version",
            "kind",
            "package",
            "base_package_version",
            "composite_version",
            "archive_sha256",
            "archive_bytes",
            "engine",
            "inputs",
            "raw_logs",
            "tests",
            "acceptance",
            "install_roundtrip",
            "adapter_profile_negotiation",
            "postgresql17",
            "opa",
            "provider_runtime",
            "remote_executor",
            "target_environment_conformance",
            "independent_verification",
            "certification",
            "implementation_status",
            "status",
        },
        "delta qualification receipt",
    )
    if receipt_snapshot.payload != json_bytes(receipt):
        raise VerificationPackError("delta qualification receipt is not canonical JSON")
    if (
        receipt["schema_version"] != "1.0.0"
        or receipt["kind"]
        != "elmos.harness-runtime-assurance-delta.local-qualification"
        or receipt["package"] != f"{DELTA_PACKAGE_NAME}@{DELTA_PACKAGE_VERSION}"
        or receipt["base_package_version"] != PACKAGE_VERSION
        or receipt["composite_version"] != COMPOSITE_VERSION
        or receipt["archive_sha256"] != DELTA_ARCHIVE_SHA256
        or receipt["archive_bytes"] != DELTA_ARCHIVE_BYTES
        or receipt["status"] != "PASS"
        or receipt["implementation_status"] != "LOCAL_EXECUTED_SELF_ATTESTED"
        or receipt["install_roundtrip"] != "PASS"
        or receipt["adapter_profile_negotiation"] != "PASS"
        or any(
            receipt[key] != "NOT_RUN"
            for key in (
                "postgresql17",
                "opa",
                "provider_runtime",
                "remote_executor",
                "target_environment_conformance",
                "independent_verification",
            )
        )
        or receipt["certification"] != "NOT_CERTIFIED"
    ):
        raise VerificationPackError("delta qualification identity/boundary is invalid")

    archive = read_file_at(root_fd, DELTA_ARCHIVE_RELATIVE, limit=DELTA_ARCHIVE_BYTES)
    assert archive is not None
    if (
        len(archive.payload) != DELTA_ARCHIVE_BYTES
        or sha256_hex(archive.payload) != DELTA_ARCHIVE_SHA256
    ):
        raise VerificationPackError("delta source archive identity is invalid")

    acceptance_snapshot = read_file_at(
        root_fd,
        DELTA_ACCEPTANCE_BINDINGS_RELATIVE,
        limit=2 * 1024 * 1024,
    )
    assert acceptance_snapshot is not None
    acceptance_bindings = _validate_delta_acceptance_bindings(
        acceptance_snapshot.payload,
        archive.payload,
    )

    delta_records = [
        item
        for item in records
        if not any(
            part in {"build", "dist"} or part.endswith(".egg-info")
            for part in PurePosixPath(str(item["path"])).parts
        )
    ]
    normalized_records = [
        {
            "path": item["path"],
            "bytes": item["bytes"],
            "sha256": "sha256:" + str(item["sha256"]),
        }
        for item in delta_records
    ]
    engine = _exact_mapping(
        receipt["engine"], {"files", "tree_sha256", "inventory"}, "delta engine"
    )
    delta_tree_sha256 = digest(canonical_bytes(normalized_records))
    if (
        engine["files"] != len(normalized_records)
        or engine["inventory"] != normalized_records
        or engine["tree_sha256"] != delta_tree_sha256
    ):
        raise VerificationPackError("delta qualification engine binding is invalid")

    discovered_engine_tests = {
        ENGINE_ROOT / Path(*PurePosixPath(str(item["path"])).parts)
        for item in delta_records
        if PurePosixPath(str(item["path"])).parent == PurePosixPath("tests")
        and PurePosixPath(str(item["path"])).match(DELTA_ENGINE_TEST_PATTERN)
    }
    required_engine_tests = set(DELTA_REQUIRED_ENGINE_TESTS)
    allowed_engine_tests = required_engine_tests | set(DELTA_OPTIONAL_ENGINE_TESTS)
    missing_engine_tests = required_engine_tests.difference(discovered_engine_tests)
    unexpected_engine_tests = discovered_engine_tests.difference(allowed_engine_tests)
    if missing_engine_tests or unexpected_engine_tests:
        raise VerificationPackError(
            "delta qualification test inventory is invalid: "
            f"missing={sorted(map(str, missing_engine_tests))}, "
            f"unexpected={sorted(map(str, unexpected_engine_tests))}"
        )
    expected_inputs = (
        DELTA_QUALIFIER_RELATIVE,
        STRUCTURED_RUNNER_RELATIVE,
        DELTA_IMPORTER_RELATIVE,
        DELTA_ACCEPTANCE_BINDINGS_RELATIVE,
        *tuple(sorted(discovered_engine_tests)),
        DELTA_IMPORTER_TEST_RELATIVE,
    )
    inputs = receipt["inputs"]
    if not isinstance(inputs, dict) or set(inputs) != {
        path.as_posix() for path in expected_inputs
    }:
        raise VerificationPackError("delta fixed input set is invalid")
    observed: dict[Path, FileIdentity] = {
        DELTA_RECEIPT_RELATIVE: receipt_snapshot.identity,
        DELTA_ARCHIVE_RELATIVE: archive.identity,
        DELTA_ACCEPTANCE_BINDINGS_RELATIVE: acceptance_snapshot.identity,
    }
    qualifier: FileSnapshot | None = None
    for relative in expected_inputs:
        snapshot = read_file_at(root_fd, relative, limit=MAX_REPOSITORY_FILE_BYTES)
        assert snapshot is not None
        contract = _exact_mapping(
            inputs[relative.as_posix()], {"bytes", "sha256"}, f"delta input {relative}"
        )
        if contract != {
            "bytes": len(snapshot.payload),
            "sha256": digest(snapshot.payload),
        }:
            raise VerificationPackError(f"delta fixed input digest drift: {relative}")
        observed[relative] = snapshot.identity
        if relative == DELTA_QUALIFIER_RELATIVE:
            qualifier = snapshot
    assert qualifier is not None

    tests = _exact_mapping(receipt["tests"], TEST_TOTAL_KEYS, "delta test totals")
    expected_totals = {
        key: _nonnegative_integer(tests[key], f"delta tests {key}")
        for key in TEST_TOTAL_KEYS
    }
    if (
        expected_totals["selected"] < 25
        or expected_totals["passed"] != expected_totals["selected"]
        or any(
            expected_totals[key] != 0
            for key in TEST_TOTAL_KEYS.difference({"selected", "passed"})
        )
    ):
        raise VerificationPackError("delta test totals are not fully passing")

    raw_refs = receipt["raw_logs"]
    if not isinstance(raw_refs, list) or len(raw_refs) != len(DELTA_RAW_LOG_COMMANDS):
        raise VerificationPackError("delta raw log set is incomplete")
    raw_logs: dict[str, FileSnapshot] = {}
    raw_records: dict[str, Mapping[str, Any]] = {}
    structured_results: dict[str, Mapping[str, Any]] = {}
    observed_totals = {key: 0 for key in TEST_TOTAL_KEYS}
    adapter_selectors: set[str] = set()
    for raw_ref in raw_refs:
        reference = _exact_mapping(
            raw_ref,
            {"name", "path", "sha256", "returncode"},
            "delta raw log reference",
        )
        path = reference["path"]
        if path not in DELTA_RAW_LOG_COMMANDS or path in raw_logs:
            raise VerificationPackError(
                f"unexpected or duplicate delta raw log: {path!r}"
            )
        if (
            reference["name"] != PurePosixPath(path).stem
            or reference["returncode"] != 0
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", str(reference["sha256"]))
        ):
            raise VerificationPackError(f"delta raw log reference is invalid: {path}")
        repository_path = ENGINE_ROOT / Path(*PurePosixPath(path).parts)
        snapshot = read_file_at(root_fd, repository_path, limit=MAX_LOG_BYTES)
        assert snapshot is not None
        if reference["sha256"] != digest(snapshot.payload):
            raise VerificationPackError(f"delta raw log digest mismatch: {path}")
        record = _exact_mapping(
            _load_json(snapshot.payload, path),
            {
                "schema_version",
                "name",
                "argv",
                "cwd",
                "returncode",
                "timed_out",
                "wall_clock_milliseconds",
                "stdout",
                "stderr",
                "execution_environment",
            },
            f"delta raw log {path}",
        )
        environment = _exact_mapping(
            record["execution_environment"],
            {
                "python",
                "os",
                "network",
                "external_evidence",
                "independent_verification",
                "certification",
            },
            f"delta execution environment {path}",
        )
        python_record = _exact_mapping(
            environment["python"],
            {"implementation", "version", "executable"},
            f"delta Python environment {path}",
        )
        os_record = _exact_mapping(
            environment["os"],
            {"system", "release", "machine"},
            f"delta OS environment {path}",
        )
        argv = record["argv"]
        if (
            snapshot.payload != json_bytes(record)
            or record["schema_version"] != "1.0.0"
            or record["name"] != reference["name"]
            or record["cwd"] != "."
            or not isinstance(argv, list)
            or not argv
            or any(not isinstance(item, str) or not item for item in argv)
            or tuple(argv[1:]) != DELTA_RAW_LOG_COMMANDS[path]
            or argv[0] != python_record["executable"]
            or record["returncode"] != 0
            or record["timed_out"] is not False
            or not isinstance(record["stdout"], str)
            or not isinstance(record["stderr"], str)
            or environment["network"] != "LOOPBACK_PROXY_DENY"
            or environment["external_evidence"] != "NOT_RUN"
            or environment["independent_verification"] != "NOT_RUN"
            or environment["certification"] != "NOT_CERTIFIED"
            or any(
                not isinstance(value, str) or not value
                for value in python_record.values()
            )
            or any(
                not isinstance(value, str) or not value for value in os_record.values()
            )
        ):
            raise VerificationPackError(f"delta raw log contract failed: {path}")
        _nonnegative_integer(
            record["wall_clock_milliseconds"], f"delta duration {path}"
        )
        if path.endswith("-tests.json"):
            structured, _ = _validate_structured_results(
                root_fd,
                record["stdout"],
                path=path,
                commands=DELTA_RAW_LOG_COMMANDS,
            )
            structured_results[path] = structured
            for key in TEST_TOTAL_KEYS:
                observed_totals[key] += int(structured["totals"][key])
            if path.endswith("delta-engine-tests.json"):
                observed_sources = {
                    str(outcome["source_path"]) for outcome in structured["outcomes"]
                }
                expected_sources = {
                    relative.as_posix() for relative in discovered_engine_tests
                }
                if observed_sources != expected_sources:
                    raise VerificationPackError(
                        "delta engine test evidence omitted a fixed test source"
                    )
                adapter_selectors.update(
                    outcome["selector"]
                    for outcome in structured["outcomes"]
                    if any(
                        token in outcome["selector"].lower()
                        for token in ("protocol", "adapter", "permission")
                    )
                )
            elif {
                str(outcome["source_path"]) for outcome in structured["outcomes"]
            } != {DELTA_IMPORTER_TEST_RELATIVE.as_posix()}:
                raise VerificationPackError(
                    "delta importer test evidence source binding is invalid"
                )
        else:
            installation = _load_json(
                record["stdout"].encode("utf-8"), "delta installation stdout"
            )
            if (
                not isinstance(installation, dict)
                or installation.get("action") != "check"
                or installation.get("package")
                != f"{DELTA_PACKAGE_NAME}@{DELTA_PACKAGE_VERSION}"
                or not isinstance(installation.get("archive"), dict)
                or installation["archive"].get("sha256") != DELTA_ARCHIVE_SHA256
                or installation["archive"].get("bytes") != DELTA_ARCHIVE_BYTES
                or installation.get("implementation_status")
                not in {
                    "DECLARED_RUNTIME_UNQUALIFIED",
                    "LOCAL_EXECUTED_SELF_ATTESTED",
                }
                or installation.get("external_runtime_status") != "NOT_RUN"
                or installation.get("certification_status") != "NOT_CERTIFIED"
                or not isinstance(installation.get("installation"), dict)
                or installation["installation"].get("status") != "PASS"
            ):
                raise VerificationPackError("delta installation check is invalid")
        raw_logs[path] = snapshot
        raw_records[path] = record
        observed[repository_path] = snapshot.identity
    if (
        set(raw_logs) != set(DELTA_RAW_LOG_COMMANDS)
        or observed_totals != expected_totals
        or len(adapter_selectors) < 3
    ):
        raise VerificationPackError("delta raw evidence does not match its receipt")
    engine_results = structured_results.get(
        "qualification/delta-v3.1/raw/delta-engine-tests.json"
    )
    if engine_results is None:
        raise VerificationPackError("delta acceptance engine outcomes are unavailable")
    _validate_delta_acceptance_receipt(
        receipt["acceptance"],
        acceptance_bindings,
        engine_results["outcomes"],
    )
    return (
        receipt_snapshot,
        receipt,
        archive,
        qualifier,
        raw_logs,
        raw_records,
        structured_results,
        observed,
    )


def validate_qualification(repository_root: Path) -> ValidatedQualification:
    """Completely revalidate the fixed receipt against current repository bytes."""

    with repository_anchor(repository_root) as (absolute, root_fd, root_identity):
        receipt_snapshot = read_file_at(
            root_fd,
            RECEIPT_RELATIVE,
            limit=MAX_RECEIPT_BYTES,
        )
        assert receipt_snapshot is not None
        receipt = _exact_mapping(
            _load_json(receipt_snapshot.payload, RECEIPT_RELATIVE.as_posix()),
            {
                "schema_version",
                "kind",
                "status",
                "package",
                "engine",
                "tests",
                "postgresql17",
                "qualifier",
            },
            "qualification receipt",
        )
        if receipt_snapshot.payload != canonical_bytes(receipt) + b"\n":
            raise VerificationPackError("qualification receipt is not canonical JSON")
        if (
            receipt["schema_version"] != "1.1.0"
            or receipt["kind"] != "elmos.proof-driven-harness-v3.local-qualification"
            or receipt["status"] != "PASS"
        ):
            raise VerificationPackError(
                "qualification receipt identity/status is invalid"
            )
        package = _exact_mapping(
            receipt["package"],
            {"name", "version", "archive_sha256"},
            "qualification package",
        )
        if package != {
            "name": PACKAGE_NAME,
            "version": PACKAGE_VERSION,
            "archive_sha256": ARCHIVE_SHA256,
        }:
            raise VerificationPackError("qualification package binding is invalid")

        archive = read_file_at(
            root_fd,
            ARCHIVE_RELATIVE,
            limit=ARCHIVE_BYTES,
        )
        assert archive is not None
        if (
            len(archive.payload) != ARCHIVE_BYTES
            or sha256_hex(archive.payload) != ARCHIVE_SHA256
        ):
            raise VerificationPackError("source archive identity is invalid")

        engine = _exact_mapping(
            receipt["engine"],
            {
                "root",
                "tree_sha256",
                "files",
                "skill_count",
                "skill_names_sha256",
                "component_count",
                "component_ids_sha256",
            },
            "qualification engine",
        )
        records = engine_inventory_at(root_fd)
        tree_sha256 = sha256_hex(canonical_bytes(list(records)))
        if (
            engine["root"] != ENGINE_ROOT.as_posix()
            or engine["files"] != list(records)
            or engine["tree_sha256"] != tree_sha256
            or engine["skill_count"] != len(SKILL_NAMES)
            or engine["skill_names_sha256"]
            != sha256_hex(canonical_bytes(list(SKILL_NAMES)))
            or engine["component_count"] != len(COMPONENT_IDS)
            or engine["component_ids_sha256"]
            != sha256_hex(canonical_bytes(list(COMPONENT_IDS)))
        ):
            raise VerificationPackError(
                "qualification engine/registry binding is invalid"
            )

        qualifier = read_file_at(
            root_fd,
            QUALIFIER_RELATIVE,
            limit=MAX_RECEIPT_BYTES,
        )
        assert qualifier is not None
        qualifier_contract = _exact_mapping(
            receipt["qualifier"], {"path", "sha256"}, "qualification producer"
        )
        if qualifier_contract != {
            "path": QUALIFIER_RELATIVE.as_posix(),
            "sha256": sha256_hex(qualifier.payload),
        }:
            raise VerificationPackError("qualification producer digest is invalid")

        tests = _exact_mapping(
            receipt["tests"],
            {"status", *TEST_TOTAL_KEYS, "raw_logs"},
            "qualification tests",
        )
        postgres = receipt["postgresql17"]
        if not isinstance(postgres, dict):
            raise VerificationPackError("qualification PostgreSQL record is invalid")
        postgres_status = postgres.get("status")
        if postgres_status == "NOT_RUN":
            postgres = _exact_mapping(
                postgres,
                {
                    "status",
                    "required_postgresql_version",
                    "required_psycopg_version",
                    "raw_log",
                    "reason",
                },
                "qualification PostgreSQL not-run record",
            )
            if (
                postgres["required_postgresql_version"] != "17.5"
                or postgres["required_psycopg_version"] != "3.2.13"
                or postgres["raw_log"] is not None
                or not isinstance(postgres["reason"], str)
                or not postgres["reason"]
            ):
                raise VerificationPackError(
                    "qualification PostgreSQL NOT_RUN record is invalid"
                )
            allowed_commands = dict(RAW_LOG_COMMANDS)
        elif postgres_status == "LOCAL_EXECUTED_SELF_ATTESTED":
            postgres = _exact_mapping(
                postgres,
                {
                    "status",
                    "required_postgresql_version",
                    "required_psycopg_version",
                    "environment",
                    "tests",
                    "raw_log",
                    "external_evidence",
                    "independent_verification",
                    "certification",
                },
                "qualification PostgreSQL execution record",
            )
            environment = _exact_mapping(
                postgres["environment"],
                {
                    "status",
                    "required_version",
                    "observed_version",
                    "version_output",
                    "psycopg_version",
                    "psycopg_binary_version",
                    "tools",
                },
                "qualification PostgreSQL environment",
            )
            if (
                postgres["required_postgresql_version"] != "17.5"
                or postgres["required_psycopg_version"] != "3.2.13"
                or environment["status"] != "AVAILABLE_EXACT"
                or environment["required_version"] != "17.5"
                or environment["observed_version"] != "17.5"
                or not isinstance(environment["version_output"], str)
                or POSTGRES_VERSION_OUTPUT_PATTERN.fullmatch(
                    environment["version_output"]
                )
                is None
                or environment["psycopg_version"] != "3.2.13"
                or environment["psycopg_binary_version"] != "3.2.13"
                or postgres["external_evidence"] != "NOT_RUN"
                or postgres["independent_verification"] != "NOT_RUN"
                or postgres["certification"] != "NOT_CERTIFIED"
            ):
                raise VerificationPackError(
                    "qualification PostgreSQL exact environment is invalid"
                )
            tools = environment["tools"]
            if (
                not isinstance(tools, list)
                or len(tools) != 4
                or [item.get("name") for item in tools if isinstance(item, dict)]
                != ["initdb", "pg_ctl", "psql", "postgres"]
                or any(
                    not isinstance(item, dict)
                    or set(item)
                    != {
                        "name",
                        "path",
                        "sha256",
                        "observed_version",
                        "version_output",
                    }
                    or not isinstance(item["path"], str)
                    or not Path(item["path"]).is_absolute()
                    or item["observed_version"] != "17.5"
                    or not isinstance(item["version_output"], str)
                    or POSTGRES_TOOL_VERSION_OUTPUT_PATTERNS.get(
                        str(item["name"]), re.compile(r"(?!)")
                    ).fullmatch(item["version_output"])
                    is None
                    or not re.fullmatch(r"sha256:[0-9a-f]{64}", str(item["sha256"]))
                    for item in tools
                )
            ):
                raise VerificationPackError(
                    "qualification PostgreSQL tool identities are invalid"
                )
            allowed_commands = {
                **RAW_LOG_COMMANDS,
                POSTGRES_RAW_LOG: POSTGRES_RAW_COMMAND,
            }
        else:
            raise VerificationPackError("qualification PostgreSQL status is invalid")
        raw_refs = tests["raw_logs"]
        if not isinstance(raw_refs, list) or len(raw_refs) != len(allowed_commands):
            raise VerificationPackError("qualification raw log set is incomplete")
        raw_logs: dict[str, FileSnapshot] = {}
        raw_records: dict[str, Mapping[str, Any]] = {}
        structured_results: dict[str, Mapping[str, Any]] = {}
        observed: dict[Path, FileIdentity] = {
            RECEIPT_RELATIVE: receipt_snapshot.identity,
            ARCHIVE_RELATIVE: archive.identity,
            QUALIFIER_RELATIVE: qualifier.identity,
        }
        observed_totals = {key: 0 for key in TEST_TOTAL_KEYS}
        for raw_ref in raw_refs:
            path, snapshot, record, structured, passed, repository_path = (
                _validate_raw_log(
                    root_fd,
                    raw_ref,
                    allowed_commands=allowed_commands,
                )
            )
            if path in raw_logs:
                raise VerificationPackError(f"duplicate raw log: {path}")
            raw_logs[path] = snapshot
            raw_records[path] = record
            if structured is not None:
                structured_results[path] = structured
                for key in TEST_TOTAL_KEYS:
                    observed_totals[key] += int(structured["totals"][key])
            observed[repository_path] = snapshot.identity
            if structured is not None and passed != int(structured["totals"]["passed"]):
                raise VerificationPackError(f"structured test count mismatch: {path}")
        if set(raw_logs) != set(allowed_commands):
            raise VerificationPackError(
                "qualification raw log identities are incomplete"
            )
        receipt_totals = {
            key: _nonnegative_integer(tests[key], f"qualification {key}")
            for key in TEST_TOTAL_KEYS
        }
        if (
            tests["status"] != "PASS"
            or receipt_totals["selected"] <= 0
            or receipt_totals["passed"] != receipt_totals["selected"]
            or any(
                receipt_totals[key] != 0
                for key in TEST_TOTAL_KEYS.difference({"selected", "passed"})
            )
            or receipt_totals != observed_totals
        ):
            raise VerificationPackError("qualification totals do not match raw logs")
        if postgres_status == "LOCAL_EXECUTED_SELF_ATTESTED":
            if (
                postgres["raw_log"]
                != next(ref for ref in raw_refs if ref["path"] == POSTGRES_RAW_LOG)
                or postgres["tests"] != structured_results[POSTGRES_RAW_LOG]["totals"]
                or raw_records[POSTGRES_RAW_LOG]["execution_environment"]["postgresql"]
                != postgres["environment"]
            ):
                raise VerificationPackError(
                    "qualification PostgreSQL receipt binding is invalid"
                )

        (
            delta_receipt_snapshot,
            delta_receipt,
            delta_archive,
            delta_qualifier,
            delta_raw_logs,
            delta_raw_records,
            delta_structured_results,
            delta_observed,
        ) = _validate_delta_qualification(root_fd, records)
        observed.update(delta_observed)

        if engine_inventory_at(root_fd) != records:
            raise VerificationPackError("engine tree changed during receipt validation")
        for observed_path, identity in observed.items():
            revalidate_file_at(root_fd, observed_path, identity)
        assert_repository_anchor(absolute, root_identity)
        return ValidatedQualification(
            receipt_payload=receipt_snapshot.payload,
            receipt=receipt,
            receipt_sha256=sha256_hex(receipt_snapshot.payload),
            engine_records=records,
            engine_tree_sha256=tree_sha256,
            archive=archive,
            qualifier=qualifier,
            raw_logs=raw_logs,
            raw_records=raw_records,
            structured_results=structured_results,
            delta_receipt_payload=delta_receipt_snapshot.payload,
            delta_receipt=delta_receipt,
            delta_receipt_sha256=sha256_hex(delta_receipt_snapshot.payload),
            delta_archive=delta_archive,
            delta_qualifier=delta_qualifier,
            delta_raw_logs=delta_raw_logs,
            delta_raw_records=delta_raw_records,
            delta_structured_results=delta_structured_results,
            observed_files=observed,
        )


def _negative_cases(qualification: ValidatedQualification) -> dict[str, Any]:
    declarations = [
        {
            "case_id": "NEG-ARCHIVE-SNAPSHOT-SWAP",
            "selector": (
                "test_integration.ProofDrivenHarnessArchiveTests."
                "test_archive_audit_uses_one_in_memory_snapshot_and_detects_path_swap"
            ),
            "expected": "archive audit rejects pathname replacement after its pinned snapshot",
            "evidence_raw_log": "qualification/raw/package-integration-tests.json",
        },
        {
            "case_id": "NEG-ARCHIVE-PATH-TRAVERSAL",
            "selector": (
                "test_integration.ProofDrivenHarnessArchiveTests."
                "test_traversal_member_fails_closed"
            ),
            "expected": "unsafe archive member path is rejected",
            "evidence_raw_log": "qualification/raw/package-integration-tests.json",
        },
        {
            "case_id": "NEG-ARCHIVE-UNICODE-COLLISION",
            "selector": (
                "test_integration.ProofDrivenHarnessArchiveTests."
                "test_unicode_casefold_collision_fails_closed"
            ),
            "expected": "Unicode and casefold archive collision is rejected",
            "evidence_raw_log": "qualification/raw/package-integration-tests.json",
        },
        {
            "case_id": "NEG-ARCHIVE-LINK-ENCRYPTION-RATIO",
            "selector": (
                "test_integration.ProofDrivenHarnessArchiveTests."
                "test_symlink_encryption_and_ratio_fail_closed"
            ),
            "expected": "linked, encrypted, or over-ratio archive member is rejected",
            "evidence_raw_log": "qualification/raw/package-integration-tests.json",
        },
        {
            "case_id": "NEG-PUBLISH-SYMLINK-PARENT",
            "selector": (
                "test_integration.ProofDrivenHarnessInstallationTests."
                "test_dirfd_publication_rejects_symlink_parent"
            ),
            "expected": "publication never traverses a symlink parent",
            "evidence_raw_log": "qualification/raw/package-integration-tests.json",
        },
        {
            "case_id": "NEG-PUBLISH-PARENT-SWAP",
            "selector": (
                "test_integration.ProofDrivenHarnessInstallationTests."
                "test_dirfd_publication_detects_parent_swap_during_rename"
            ),
            "expected": "publication detects parent replacement during rename",
            "evidence_raw_log": "qualification/raw/package-integration-tests.json",
        },
        {
            "case_id": "NEG-QUALIFICATION-TAMPER",
            "selector": (
                "test_integration.ProofDrivenHarnessQualificationTests."
                "test_only_exact_digest_bound_receipt_promotes_status"
            ),
            "expected": "engine or receipt drift prevents local status promotion",
            "evidence_raw_log": "qualification/raw/package-integration-tests.json",
        },
        {
            "case_id": "NEG-PACK-RECEIPT-TAMPER",
            "selector": (
                "test_publish_verification_pack."
                "ProofDrivenHarnessVerificationPackPublisherTests."
                "test_tampered_receipt_fails_closed"
            ),
            "expected": "verification pack publisher rejects a tampered receipt",
            "evidence_raw_log": "qualification/raw/engine-tests.json",
        },
        {
            "case_id": "NEG-PACK-SYMLINK-OUTPUT",
            "selector": (
                "test_publish_verification_pack."
                "ProofDrivenHarnessVerificationPackPublisherTests."
                "test_symlink_output_fails_closed_without_escape"
            ),
            "expected": "verification pack publisher rejects a linked output",
            "evidence_raw_log": "qualification/raw/engine-tests.json",
        },
        {
            "case_id": "NEG-DELTA-ACCEPTANCE-BINDING-TAMPER-OMISSION",
            "selector": (
                "test_publish_verification_pack."
                "ProofDrivenHarnessVerificationPackPublisherTests."
                "test_delta_acceptance_binding_tamper_and_omission_fail_closed"
            ),
            "expected": "delta acceptance source tamper or case omission is rejected",
            "evidence_raw_log": "qualification/raw/engine-tests.json",
        },
        {
            "case_id": "NEG-DELTA-ACCEPTANCE-RECEIPT-SELECTOR-DRIFT",
            "selector": (
                "test_publish_verification_pack."
                "ProofDrivenHarnessVerificationPackPublisherTests."
                "test_delta_acceptance_receipt_selector_drift_fails_closed"
            ),
            "expected": "delta acceptance receipt selector drift is rejected",
            "evidence_raw_log": "qualification/raw/engine-tests.json",
        },
    ]
    cases: list[dict[str, Any]] = []
    for declaration in declarations:
        raw_path = declaration["evidence_raw_log"]
        structured = qualification.structured_results.get(raw_path)
        if structured is None:
            raise VerificationPackError(
                f"negative case has no structured raw results: {declaration['case_id']}"
            )
        matching = [
            outcome
            for outcome in structured["outcomes"]
            if outcome["selector"] == declaration["selector"]
        ]
        if len(matching) != 1 or matching[0]["status"] != "PASSED":
            raise VerificationPackError(
                f"negative selector did not pass exactly once: {declaration['selector']}"
            )
        outcome = matching[0]
        cases.append(
            {
                **declaration,
                "status": "PASSED",
                "outcome_binding": {
                    "selector": outcome["selector"],
                    "source_path": outcome["source_path"],
                    "source_sha256": outcome["source_sha256"],
                    "selector_source_binding_sha256": outcome[
                        "selector_source_binding_sha256"
                    ],
                    "outcome_sha256": digest(canonical_bytes(outcome)),
                    "raw_log_sha256": digest(qualification.raw_logs[raw_path].payload),
                },
            }
        )
    return {
        "schema_version": 1,
        "kind": "elmos.proof-driven-harness-v3.local-negative-corpus",
        "execution": "LOCAL_EXECUTED_SELF_ATTESTED",
        "discovery_commands": [
            list(RAW_LOG_COMMANDS["qualification/raw/engine-tests.json"]),
            list(RAW_LOG_COMMANDS["qualification/raw/package-integration-tests.json"]),
        ],
        "cases": cases,
        "limitations": [
            "Each listed negative control is bound to one PASSED selector, its exact source digest, and the containing raw-log digest; evidence remains self-attested and local.",
            "No independent adversarial corpus or external verifier executed these cases.",
        ],
    }


def _environment_record(qualification: ValidatedQualification) -> dict[str, Any]:
    commands = []
    all_records = {
        **qualification.raw_records,
        **qualification.delta_raw_records,
    }
    all_logs = {**qualification.raw_logs, **qualification.delta_raw_logs}
    all_structured = {
        **qualification.structured_results,
        **qualification.delta_structured_results,
    }
    for path in sorted(all_records):
        record = all_records[path]
        commands.append(
            {
                "name": record["name"],
                "argv": record["argv"],
                "cwd": record["cwd"],
                "raw_log_sha256": digest(all_logs[path].payload),
                "raw_log_bytes": len(all_logs[path].payload),
                "returncode": record["returncode"],
                "timed_out": record["timed_out"],
                "execution_environment": record["execution_environment"],
                "structured_results_sha256": (
                    digest(canonical_bytes(all_structured[path]))
                    if path in all_structured
                    else None
                ),
            }
        )
    return {
        "schema_version": 1,
        "kind": "elmos.proof-driven-harness-v3.content-addressed-local-environment",
        "scope": "FIXED_LOCAL_SELF_ATTESTED_QUALIFICATION",
        "receipt_sha256": digest(qualification.receipt_payload),
        "qualifier_sha256": digest(qualification.qualifier.payload),
        "delta_receipt_sha256": digest(qualification.delta_receipt_payload),
        "delta_qualifier_sha256": digest(qualification.delta_qualifier.payload),
        "postgresql17": qualification.receipt["postgresql17"],
        "delta_external_runtime": {
            "postgresql17": "NOT_RUN",
            "opa": "NOT_RUN",
            "provider_runtime": "NOT_RUN",
            "remote_executor": "NOT_RUN",
            "target_environment_conformance": "NOT_RUN",
        },
        "commands": commands,
        "captured_boundaries": {
            "repository_root": ".",
            "source_archive_executed": False,
            "external_network_evidence": "NOT_RUN",
            "external_provider_evidence": "NOT_RUN",
            "independent_verifier": "NOT_RUN",
            "representative_environment": "NOT_RUN",
            "production_environment": "NOT_RUN",
        },
        "content_addressing": (
            "The environment digest is SHA-256 of this exact file and is bound by "
            "pack.json plus certification/repository-binding.json."
        ),
    }


def _repository_binding(
    path: Path,
    role: str,
    payload: bytes,
) -> dict[str, Any]:
    return {
        "path": path.as_posix(),
        "role": role,
        "sha256": digest(payload),
        "byte_size": len(payload),
    }


def _delta_engine_test_inputs(
    qualification: ValidatedQualification,
) -> tuple[Path, ...]:
    inputs = qualification.delta_receipt.get("inputs")
    if not isinstance(inputs, dict):
        raise VerificationPackError("delta fixed input set is invalid")
    discovered: set[Path] = set()
    for value in inputs:
        if not isinstance(value, str):
            raise VerificationPackError("delta fixed input path is invalid")
        pure = PurePosixPath(value)
        if pure.parent == PurePosixPath(
            (ENGINE_ROOT / "tests").as_posix()
        ) and pure.match(DELTA_ENGINE_TEST_PATTERN):
            discovered.add(Path(*pure.parts))
    required = set(DELTA_REQUIRED_ENGINE_TESTS)
    allowed = required | set(DELTA_OPTIONAL_ENGINE_TESTS)
    if not required.issubset(discovered) or not discovered.issubset(allowed):
        raise VerificationPackError(
            "delta repository-binding test inventory is invalid"
        )
    return tuple(sorted(discovered))


def _read_required_sources(
    repository_root: Path,
    qualification: ValidatedQualification,
    generated: Mapping[Path, bytes],
) -> list[dict[str, Any]]:
    roles = {
        ARCHIVE_RELATIVE: "source",
        DELTA_ARCHIVE_RELATIVE: "source-delta",
        QUALIFIER_RELATIVE: "qualification-producer",
        DELTA_QUALIFIER_RELATIVE: "delta-qualification-producer",
        RECEIPT_RELATIVE: "qualification-receipt",
        DELTA_RECEIPT_RELATIVE: "delta-qualification-receipt",
        PUBLISHER_RELATIVE: "verification-pack-publisher",
        PUBLISHER_TEST_RELATIVE: "verification-pack-negative-tests",
        IMPORTER_RELATIVE: "archive-importer",
        IMPORTER_TEST_RELATIVE: "archive-importer-negative-tests",
        DELTA_IMPORTER_RELATIVE: "delta-archive-importer",
        DELTA_IMPORTER_TEST_RELATIVE: "delta-archive-importer-negative-tests",
        DELTA_ACCEPTANCE_BINDINGS_RELATIVE: "delta-acceptance-traceability",
    }
    for path in _delta_engine_test_inputs(qualification):
        suffix = path.stem.removeprefix("test_delta_").replace("_", "-")
        roles[path] = f"delta-runtime-test-{suffix}"
    for raw_path in qualification.raw_logs:
        roles[ENGINE_ROOT / Path(*PurePosixPath(raw_path).parts)] = (
            "raw-log-" + PurePosixPath(raw_path).stem
        )
    for raw_path in qualification.delta_raw_logs:
        roles[ENGINE_ROOT / Path(*PurePosixPath(raw_path).parts)] = (
            "delta-raw-log-" + PurePosixPath(raw_path).stem
        )
    bindings: list[dict[str, Any]] = []
    with repository_anchor(repository_root) as (absolute, root_fd, root_identity):
        for path, role in roles.items():
            snapshot = read_file_at(
                root_fd,
                path,
                limit=MAX_REPOSITORY_FILE_BYTES,
            )
            assert snapshot is not None
            bindings.append(_repository_binding(path, role, snapshot.payload))
            revalidate_file_at(root_fd, path, snapshot.identity)
        assert_repository_anchor(absolute, root_identity)
    target_path = PACK_RELATIVE / "artifacts/engine-tree-inventory.json"
    environment_path = PACK_RELATIVE / "environment/local-environment.json"
    bindings.extend(
        (
            _repository_binding(
                target_path, "test", generated[target_path.relative_to(PACK_RELATIVE)]
            ),
            _repository_binding(
                environment_path,
                "environment",
                generated[environment_path.relative_to(PACK_RELATIVE)],
            ),
        )
    )
    bindings.sort(key=lambda item: item["path"])
    if len({binding["path"] for binding in bindings}) != len(bindings):
        raise VerificationPackError("repository binding paths are not unique")
    by_role = {binding["role"]: binding for binding in bindings}
    if by_role["source"]["sha256"] != "sha256:" + ARCHIVE_SHA256:
        raise VerificationPackError("source repository binding does not match archive")
    if by_role["source-delta"]["sha256"] != "sha256:" + DELTA_ARCHIVE_SHA256:
        raise VerificationPackError("delta source binding does not match archive")
    if by_role["test"]["sha256"] != "sha256:" + qualification.engine_tree_sha256:
        raise VerificationPackError(
            "target repository binding does not match engine tree"
        )
    return bindings


def _integrity_manifest(outputs: Mapping[Path, bytes]) -> bytes:
    entries = []
    for path in sorted(outputs, key=lambda item: item.as_posix()):
        if (
            path == Path("certification/integrity-manifest.json")
            or path in GATE_OUTPUTS
        ):
            continue
        payload = outputs[path]
        entries.append(
            {
                "path": path.as_posix(),
                "byte_size": len(payload),
                "sha256": sha256_hex(payload),
            }
        )
    return json_bytes(
        {
            "schema_version": 1,
            "algorithm": "sha256",
            "entries": entries,
        }
    )


def build_pack_outputs(
    repository_root: Path,
    qualification: ValidatedQualification,
) -> dict[Path, bytes]:
    """Build deterministic pack bytes; no timestamp, hostname, or random value enters."""

    outputs: dict[Path, bytes] = {}
    source_digest = "sha256:" + ARCHIVE_SHA256
    delta_source_digest = "sha256:" + DELTA_ARCHIVE_SHA256
    target_digest = "sha256:" + qualification.engine_tree_sha256
    receipt_digest = "sha256:" + qualification.receipt_sha256
    delta_receipt_digest = "sha256:" + qualification.delta_receipt_sha256

    outputs[Path("artifacts/engine-tree-inventory.json")] = canonical_bytes(
        list(qualification.engine_records)
    )
    if digest(outputs[Path("artifacts/engine-tree-inventory.json")]) != target_digest:
        raise VerificationPackError(
            "canonical engine inventory does not match target digest"
        )
    outputs[Path("qualification/source-receipt.json")] = qualification.receipt_payload
    outputs[Path("qualification/delta-v3.1/source-receipt.json")] = (
        qualification.delta_receipt_payload
    )
    outputs[Path("qualification/delta-v3.1/acceptance-results.json")] = json_bytes(
        qualification.delta_receipt["acceptance"]
    )
    for path, snapshot in qualification.raw_logs.items():
        outputs[Path("qualification/raw") / PurePosixPath(path).name] = snapshot.payload
    for path, snapshot in qualification.delta_raw_logs.items():
        outputs[Path("qualification/delta-v3.1/raw") / PurePosixPath(path).name] = (
            snapshot.payload
        )
    outputs[Path("environment/local-environment.json")] = json_bytes(
        _environment_record(qualification)
    )
    environment_digest = digest(outputs[Path("environment/local-environment.json")])
    scope = {
        "migration_route": "proof-driven-harness-v3.1-composite-local-qualification",
        "source_artifact_digest": source_digest,
        "delta_source_artifact_digest": delta_source_digest,
        "composite_version": COMPOSITE_VERSION,
        "target_artifact_digest": target_digest,
        "workload_key": "proof-driven-harness-v3.1-composite-local-development-negative",
        "risk_tier": "P0",
        "environment_digest": environment_digest,
        "controlled_public_dns_rebinding_campaign": "NOT_RUN",
        "independent_holdout": "NOT_RUN",
        "representative_production_workload": "NOT_RUN",
    }

    outputs[Path("qualification/receipt-validation.json")] = json_bytes(
        {
            "schema_version": 1,
            "kind": "elmos.proof-driven-harness-v3.receipt-validation",
            "status": "PASS",
            "receipt_sha256": receipt_digest,
            "source_archive_sha256": source_digest,
            "engine_tree_sha256": target_digest,
            "qualifier_sha256": digest(qualification.qualifier.payload),
            "skill_count": len(SKILL_NAMES),
            "skill_names_sha256": digest(canonical_bytes(list(SKILL_NAMES))),
            "component_count": len(COMPONENT_IDS),
            "component_ids_sha256": digest(canonical_bytes(list(COMPONENT_IDS))),
            "tests": {
                "status": "PASS",
                **{
                    key: qualification.receipt["tests"][key]
                    for key in sorted(TEST_TOTAL_KEYS)
                },
                "raw_log_count": len(qualification.raw_logs),
            },
            "postgresql17": qualification.receipt["postgresql17"],
            "external_evidence": "NOT_RUN",
            "independent_verification": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }
    )
    outputs[Path("qualification/delta-v3.1/receipt-validation.json")] = json_bytes(
        {
            "schema_version": 1,
            "kind": "elmos.harness-runtime-assurance-delta.receipt-validation",
            "status": "PASS",
            "base_source_version": PACKAGE_VERSION,
            "delta_source_version": DELTA_PACKAGE_VERSION,
            "composite_version": COMPOSITE_VERSION,
            "receipt_sha256": delta_receipt_digest,
            "source_archive_sha256": delta_source_digest,
            "engine_tree_sha256": target_digest,
            "qualifier_sha256": digest(qualification.delta_qualifier.payload),
            "tests": qualification.delta_receipt["tests"],
            "acceptance": qualification.delta_receipt["acceptance"]["local_cases"],
            "acceptance_binding_sha256": qualification.delta_receipt["acceptance"][
                "binding_sha256"
            ],
            "raw_log_count": len(qualification.delta_raw_logs),
            "adapter_profile_negotiation": qualification.delta_receipt[
                "adapter_profile_negotiation"
            ],
            "postgresql17": "NOT_RUN",
            "opa": "NOT_RUN",
            "provider_runtime": "NOT_RUN",
            "remote_executor": "NOT_RUN",
            "target_environment_conformance": "NOT_RUN",
            "external_evidence": "NOT_RUN",
            "independent_verification": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }
    )

    negative_cases = _negative_cases(qualification)
    outputs[Path("corpus/negative/cases.json")] = json_bytes(negative_cases)
    development_seed = {
        "schema_version": 1,
        "kind": "elmos.proof-driven-harness-v3.local-development-corpus",
        "receipt_sha256": receipt_digest,
        "delta_receipt_sha256": delta_receipt_digest,
        "source_digest": source_digest,
        "delta_source_digest": delta_source_digest,
        "target_digest": target_digest,
        "delta_acceptance": qualification.delta_receipt["acceptance"]["local_cases"],
        "raw_logs": [
            {
                "path": path,
                "sha256": digest(qualification.raw_logs[path].payload),
                "bytes": len(qualification.raw_logs[path].payload),
            }
            for path in sorted(qualification.raw_logs)
        ]
        + [
            {
                "path": path,
                "sha256": digest(qualification.delta_raw_logs[path].payload),
                "bytes": len(qualification.delta_raw_logs[path].payload),
            }
            for path in sorted(qualification.delta_raw_logs)
        ],
        "status": "LOCAL_EXECUTED_SELF_ATTESTED",
        "structured_test_outcomes": [
            {
                "raw_log": path,
                "results_sha256": digest(
                    canonical_bytes(qualification.structured_results[path])
                ),
                "totals": qualification.structured_results[path]["totals"],
            }
            for path in sorted(qualification.structured_results)
        ]
        + [
            {
                "raw_log": path,
                "results_sha256": digest(
                    canonical_bytes(qualification.delta_structured_results[path])
                ),
                "totals": qualification.delta_structured_results[path]["totals"],
            }
            for path in sorted(qualification.delta_structured_results)
        ],
        "limitations": [
            "This is repository-owned development evidence, not an independent holdout."
        ],
    }
    outputs[Path("corpus/development/seed.json")] = json_bytes(development_seed)
    holdout_not_run = {
        "schema_version": 1,
        "kind": "elmos.proof-driven-harness-v3.holdout-obligation",
        "status": "NOT_RUN",
        "reason": "No untouched independently executed holdout corpus is available.",
    }
    representative_not_run = {
        "schema_version": 1,
        "kind": "elmos.proof-driven-harness-v3.representative-workload-obligation",
        "status": "NOT_RUN",
        "reason": "No authorized production-derived representative workload is available.",
    }
    outputs[Path("corpus/holdout/not-run.json")] = json_bytes(holdout_not_run)
    outputs[Path("corpus/representative-workloads/not-run.json")] = json_bytes(
        representative_not_run
    )

    outputs[Path("corpus/development/manifest.json")] = json_bytes(
        {
            "schema_version": 1,
            "status": "passed",
            "classification": "LOCAL_EXECUTED_SELF_ATTESTED",
            "source_digest": source_digest,
            "dataset_digest": digest(outputs[Path("corpus/development/seed.json")]),
            "evidence_refs": [
                "corpus/development/seed.json",
                "qualification/receipt-validation.json",
                "qualification/raw/engine-tests.json",
                "qualification/raw/package-integration-tests.json",
            ],
            "limitations": [
                "Repository-owned local development corpus; executor and verifier are not independent."
            ],
        }
    )
    outputs[Path("corpus/negative/manifest.json")] = json_bytes(
        {
            "schema_version": 1,
            "status": "passed",
            "classification": "LOCAL_EXECUTED_SELF_ATTESTED",
            "source_digest": source_digest,
            "dataset_digest": digest(outputs[Path("corpus/negative/cases.json")]),
            "evidence_refs": [
                "corpus/negative/cases.json",
                "qualification/raw/engine-tests.json",
                "qualification/raw/package-integration-tests.json",
                "qualification/receipt-validation.json",
            ],
            "limitations": [
                "Repository-owned negative controls; no independent adversarial corpus was executed."
            ],
        }
    )
    outputs[Path("corpus/holdout/manifest.json")] = json_bytes(
        {
            "schema_version": 1,
            "status": "not-run",
            "source_digest": source_digest,
            "dataset_digest": digest(outputs[Path("corpus/holdout/not-run.json")]),
            "evidence_refs": ["corpus/holdout/not-run.json"],
            "independence": "NOT_RUN",
            "executor": None,
            "independent_verifier": None,
            "limitations": ["INDEPENDENT_HOLDOUT_NOT_RUN"],
        }
    )
    outputs[Path("corpus/representative-workloads/manifest.json")] = json_bytes(
        {
            "schema_version": 1,
            "status": "not-run",
            "source_digest": source_digest,
            "dataset_digest": digest(
                outputs[Path("corpus/representative-workloads/not-run.json")]
            ),
            "evidence_refs": ["corpus/representative-workloads/not-run.json"],
            "provenance": "NOT_RUN",
            "authorization_ref": None,
            "limitations": ["PRODUCTION_DERIVED_WORKLOAD_NOT_RUN"],
        }
    )

    outputs[Path("contracts/local-qualification-contract.json")] = json_bytes(
        {
            "schema_version": 1,
            "kind": "elmos.proof-driven-harness-v3.local-qualification-contract",
            "fixed_receipt_path": RECEIPT_RELATIVE.as_posix(),
            "required_status": "PASS",
            "source": {
                "archive_path": ARCHIVE_RELATIVE.as_posix(),
                "archive_sha256": source_digest,
                "archive_bytes": ARCHIVE_BYTES,
            },
            "delta_source": {
                "archive_path": DELTA_ARCHIVE_RELATIVE.as_posix(),
                "archive_sha256": delta_source_digest,
                "archive_bytes": DELTA_ARCHIVE_BYTES,
                "package_version": DELTA_PACKAGE_VERSION,
                "fixed_receipt_path": DELTA_RECEIPT_RELATIVE.as_posix(),
                "receipt_sha256": delta_receipt_digest,
            },
            "target": {
                "engine_root": ENGINE_ROOT.as_posix(),
                "engine_tree_sha256": target_digest,
                "inventory_path": "artifacts/engine-tree-inventory.json",
            },
            "registry": {
                "skill_count": 16,
                "component_count": 96,
                "skill_names_sha256": digest(canonical_bytes(list(SKILL_NAMES))),
                "component_ids_sha256": digest(canonical_bytes(list(COMPONENT_IDS))),
            },
            "raw_log_paths": sorted(qualification.raw_logs),
            "delta_raw_log_paths": sorted(qualification.delta_raw_logs),
            "delta_acceptance": {
                "binding_sha256": qualification.delta_receipt["acceptance"][
                    "binding_sha256"
                ],
                "local_cases": qualification.delta_receipt["acceptance"]["local_cases"],
                "target_environment": "NOT_RUN",
                "independent_verification": "NOT_RUN",
                "certification": "NOT_CERTIFIED",
            },
            "postgresql17": qualification.receipt["postgresql17"],
            "promotion_ceiling": "LOCAL_EXECUTED_SELF_ATTESTED",
            "external_evidence": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }
    )
    outputs[Path("contracts/repository-binding-contract.json")] = json_bytes(
        {
            "schema_version": 1,
            "kind": "elmos.batch35.exact-repository-binding-contract",
            "required_roles": [
                "source",
                "source-delta",
                "test",
                "environment",
                "delta-acceptance-traceability",
            ],
            "role_semantics": {
                "source": "exact source ZIP bytes",
                "source-delta": "exact runtime-assurance delta ZIP bytes",
                "test": (
                    "Batch35 target slot containing exact canonical engine-tree inventory bytes"
                ),
                "environment": "exact content-addressed local environment record bytes",
                "delta-acceptance-traceability": (
                    "repository-owned static 13x8 mapping; never independent execution evidence"
                ),
            },
            "required_test_totals": {
                "tests": qualification.test_count,
                "passed": qualification.test_count,
                "failed": 0,
            },
            "composite_version": COMPOSITE_VERSION,
            "base_source_version": PACKAGE_VERSION,
            "delta_source_version": DELTA_PACKAGE_VERSION,
            "all_bindings_require": ["path", "role", "sha256", "byte_size"],
        }
    )
    outputs[Path("contracts/status-boundary.json")] = json_bytes(
        {
            "schema_version": 1,
            "kind": "elmos.proof-driven-harness-v3.verification-status-boundary",
            "pack_status": "limited",
            "local_development_corpus": "passed",
            "local_negative_corpus": "passed",
            "holdout": "NOT_RUN",
            "representative_workloads": "NOT_RUN",
            "external_evidence": "NOT_RUN",
            "independent_verification": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
            "maximum_possible_local_gate_decision": "READY_FOR_EXTERNAL_GATE",
        }
    )

    claim_local_binding = "claim.local.qualification-binding"
    claim_local_publish = "claim.local.safe-deterministic-publication"
    claim_external = "claim.external.production-assurance"
    outputs[Path("validation-profile.json")] = json_bytes(
        {
            "schema_version": 1,
            "profile_key": f"{PACK_KEY}-profile-v1",
            "version": 1,
            "risk_tier": "P0",
            "claims": [
                {
                    "claim_id": claim_local_binding,
                    "description": (
                        "The publisher rejects any qualification receipt not exactly bound "
                        "to current archive, engine, registry, qualifier, and raw-log bytes."
                    ),
                    "criticality": "P0",
                    "required_oracles": [
                        "oracle.fixed-qualification-contract",
                        "oracle.byte-recomputation",
                    ],
                    "required_techniques": [
                        "contract",
                        "security",
                        "counterexample-replay",
                    ],
                },
                {
                    "claim_id": claim_local_publish,
                    "description": (
                        "Identical validated receipt inputs generate identical pack bytes and "
                        "linked or swapped output paths fail closed."
                    ),
                    "criticality": "P0",
                    "required_oracles": [
                        "oracle.byte-recomputation",
                        "oracle.local-negative-tests",
                    ],
                    "required_techniques": [
                        "property",
                        "metamorphic",
                        "model",
                        "security",
                    ],
                },
                {
                    "claim_id": claim_external,
                    "description": (
                        "External runtime correctness, independent holdout behavior, and "
                        "representative production suitability are established."
                    ),
                    "criticality": "P0",
                    "required_oracles": ["oracle.independent-verifier-not-run"],
                    "required_techniques": [
                        "mutation",
                        "fuzz",
                        "solver",
                        "data-money",
                        "concurrency",
                        "query",
                        "numeric",
                        "holdout",
                        "assurance-case",
                    ],
                },
            ],
            "techniques": [
                "property",
                "metamorphic",
                "mutation",
                "fuzz",
                "model",
                "contract",
                "data-money",
                "security",
                "concurrency",
                "query",
                "numeric",
                "solver",
                "counterexample-replay",
                "oracle-governance",
                "holdout",
                "assurance-case",
            ],
            "budgets": {
                "max_wall_time_minutes": 15,
                "max_receipt_bytes": MAX_RECEIPT_BYTES,
                "max_raw_log_bytes_each": MAX_LOG_BYTES,
                "max_engine_file_bytes_each": MAX_REPOSITORY_FILE_BYTES,
                "max_fuzz_seconds": 0,
                "max_mutants": 0,
                "max_solver_seconds": 0,
                "max_schedules": 0,
            },
            "stop_conditions": [
                "receipt-missing-or-invalid",
                "archive-digest-drift",
                "engine-tree-drift",
                "raw-log-drift",
                "repository-binding-drift",
                "symlink-or-special-output",
                "unknown-p0-external-obligation",
            ],
            "approvals": [],
        }
    )

    outputs[Path("oracle-registry.json")] = json_bytes(
        {
            "schema_version": 1,
            "pack_key": PACK_KEY,
            "oracles": [
                {
                    "oracle_id": "oracle.fixed-qualification-contract",
                    "type": "contract",
                    "owner": "elmos-proof-harness-engineering",
                    "scope": [claim_local_binding],
                    "independence": "dependent",
                    "trust_level": "supporting",
                    "version": "1",
                    "evidence_refs": [
                        "contracts/local-qualification-contract.json",
                        "qualification/source-receipt.json",
                    ],
                },
                {
                    "oracle_id": "oracle.byte-recomputation",
                    "type": "invariant",
                    "owner": "elmos-proof-harness-engineering",
                    "scope": [claim_local_binding, claim_local_publish],
                    "independence": "dependent",
                    "trust_level": "supporting",
                    "version": "1",
                    "evidence_refs": [
                        "qualification/receipt-validation.json",
                        "qualification/delta-v3.1/receipt-validation.json",
                        "certification/repository-binding.json",
                    ],
                },
                {
                    "oracle_id": "oracle.local-negative-tests",
                    "type": "test",
                    "owner": "elmos-proof-harness-engineering",
                    "scope": [claim_local_binding, claim_local_publish],
                    "independence": "dependent",
                    "trust_level": "supporting",
                    "version": "1",
                    "evidence_refs": [
                        "corpus/negative/cases.json",
                        "qualification/raw/engine-tests.json",
                        "qualification/raw/package-integration-tests.json",
                    ],
                },
                {
                    "oracle_id": "oracle.independent-verifier-not-run",
                    "type": "human-expert",
                    "owner": "independent-qualified-verifier-unassigned",
                    "scope": [claim_external],
                    "independence": "independent",
                    "trust_level": "advisory",
                    "version": "NOT_RUN",
                    "evidence_refs": ["corpus/holdout/not-run.json"],
                    "execution_status": "NOT_RUN",
                },
            ],
            "precedence_rules": [
                {
                    "claim_type": "local-byte-identity",
                    "ordered_oracles": [
                        "oracle.fixed-qualification-contract",
                        "oracle.byte-recomputation",
                        "oracle.local-negative-tests",
                    ],
                    "on_conflict": "BLOCK",
                }
            ],
            "conflicts": [],
            "approvals": [],
        }
    )

    outputs[Path("properties/sample.json")] = json_bytes(
        {
            "schema_version": 1,
            "property_id": "property.invalid-receipt-never-publishes",
            "claim_id": claim_local_binding,
            "owner": "elmos-proof-harness-engineering",
            "generator": {
                "kind": "fixed-field-mutation",
                "constraints": [
                    "mutate-one-of-archive-engine-registry-qualifier-raw-log-status",
                    "never-execute-mutated-content",
                    "bounded-to-one-receipt-per-case",
                ],
            },
            "oracle_refs": [
                "oracle.fixed-qualification-contract",
                "oracle.local-negative-tests",
            ],
            "assertion": {
                "kind": "fail-closed-no-output-publication",
                "expected_exception": "VerificationPackError",
            },
            "shrinker": {"kind": "single-field-delta"},
            "replay": {
                "seed": "proof-harness-v3-receipt-v1",
                "command": (
                    "python3 -m unittest discover -s "
                    "engines/proof-driven-harness-engine/tests -p "
                    "test_publish_verification_pack.py"
                ),
                "execution_status": "NOT_RUN",
                "trace_ref": None,
            },
            "execution_status": "DECLARED_NOT_RUN",
            "limitations": [
                "A fixed negative unittest exists, but no property generator campaign with per-case replay traces was executed."
            ],
        }
    )
    outputs[Path("metamorphic/sample.json")] = json_bytes(
        {
            "schema_version": 1,
            "relation_id": "relation.repeat-publication-byte-identical",
            "claim_id": claim_local_publish,
            "owner": "elmos-proof-harness-engineering",
            "preconditions": ["same-validated-receipt", "same-repository-bindings"],
            "transformation": {"kind": "repeat-pack-build"},
            "expected_relation": {
                "kind": "identical-relative-path-byte-map",
                "mutable_exclusions": [
                    "certification/gate-result.json",
                    "certification/gate-report.md",
                ],
            },
            "oracle_refs": [
                "oracle.byte-recomputation",
                "oracle.local-negative-tests",
            ],
            "non_applicable": ["changed-receipt", "changed-engine-tree"],
            "execution_status": "LOCAL_EXECUTED_SELF_ATTESTED",
        }
    )
    outputs[Path("mutation/campaign.json")] = json_bytes(
        {
            "schema_version": 1,
            "campaign_key": "mutation.proof-harness-v3-external",
            "owner": "elmos-proof-harness-engineering",
            "target_scope": [PUBLISHER_RELATIVE.as_posix()],
            "operators": [
                {"key": "accept-invalid-receipt-status", "risk": "P0"},
                {"key": "skip-engine-tree-digest-check", "risk": "P0"},
                {"key": "follow-output-symlink", "risk": "P0"},
            ],
            "budgets": {"max_mutants": 0, "max_minutes": 0},
            "required_tests": [
                "test_tampered_receipt_fails_closed",
                "test_symlink_output_fails_closed_without_escape",
            ],
            "equivalent_mutant_policy": "independent-review-required",
            "execution_status": "NOT_RUN",
        }
    )
    outputs[Path("fuzz/dictionary.json")] = json_bytes(
        {
            "schema_version": 1,
            "tokens": [
                "PASS",
                "NOT_RUN",
                "../",
                "sha256:",
                "local-qualification.json",
            ],
            "classification": "repository-owned-nonsensitive",
        }
    )
    outputs[Path("fuzz/campaign.json")] = json_bytes(
        {
            "schema_version": 1,
            "campaign_key": "fuzz.proof-harness-v3-receipt-parser",
            "owner": "elmos-proof-harness-engineering",
            "targets": ["qualification-receipt-json-parser"],
            "seed_corpus": ["corpus/development/seed.json"],
            "coverage_signal": "NOT_RUN",
            "budgets": {"max_seconds": 0, "max_memory_mb": 0, "max_inputs": 0},
            "sanitizers": [],
            "dictionary_refs": ["fuzz/dictionary.json"],
            "execution_status": "NOT_RUN",
        }
    )

    model = {
        "schema_version": 1,
        "model_key": "model.proof-harness-v3-pack-publication",
        "owner": "elmos-proof-harness-engineering",
        "states": [
            "receipt-unvalidated",
            "receipt-invalid",
            "receipt-valid",
            "pack-staged",
            "pack-published-limited",
            "publication-failed",
        ],
        "initial_state": "receipt-unvalidated",
        "commands": [
            {
                "command": "reject-invalid-receipt",
                "from": ["receipt-unvalidated"],
                "to": "receipt-invalid",
                "guard": "any-required-binding-invalid",
                "effects": ["publish-nothing"],
            },
            {
                "command": "accept-valid-receipt",
                "from": ["receipt-unvalidated"],
                "to": "receipt-valid",
                "guard": "all-required-bindings-recomputed",
                "effects": ["lock-exact-scope"],
            },
            {
                "command": "stage-pack",
                "from": ["receipt-valid"],
                "to": "pack-staged",
                "guard": "all-contracts-generated",
                "effects": ["write-private-sibling-stage"],
            },
            {
                "command": "publish-limited",
                "from": ["pack-staged"],
                "to": "pack-published-limited",
                "guard": "receipt-and-repository-still-stable",
                "effects": ["renameat-stage", "retain-not-certified"],
            },
            {
                "command": "fail-publication",
                "from": ["receipt-valid", "pack-staged"],
                "to": "publication-failed",
                "guard": "unsafe-output-or-drift",
                "effects": ["rollback-or-preserve-prior-pack"],
            },
        ],
        "invariants": [
            "receipt-invalid-never-reaches-pack-staged",
            "published-pack-status-is-limited",
            "external-and-independent-evidence-remain-not-run",
            "certification-remains-not-certified",
        ],
        "forbidden_transitions": [
            {"from": "receipt-invalid", "event": "stage-pack"},
            {"from": "pack-published-limited", "event": "self-certify"},
        ],
        "timeouts": [],
        "execution_status": "SPECIFIED_NOT_EXECUTED_AS_MODEL_CAMPAIGN",
    }
    outputs[Path("models/model.json")] = json_bytes(model)
    outputs[Path("state-machines/publisher-lifecycle.json")] = json_bytes(
        {
            "schema_version": 1,
            "model_ref": "models/model.json",
            "allowed_terminal_states": [
                "receipt-invalid",
                "pack-published-limited",
                "publication-failed",
            ],
            "forbidden_terminal_states": ["certified"],
            "execution_status": "SPECIFIED_NOT_EXECUTED_AS_MODEL_CAMPAIGN",
        }
    )
    outputs[Path("solver/proof.json")] = json_bytes(
        {
            "schema_version": 1,
            "proof_id": "proof.proof-harness-v3-publication-model",
            "property_id": "property.invalid-receipt-never-publishes",
            "solver": {
                "name": "NOT_RUN",
                "version": "NOT_RUN",
                "options": {"bounds": "NOT_RUN"},
                "timeout_ms": 1,
            },
            "status": "unknown",
            "assumptions": [
                "No solver or independent encoding has been executed for this pack."
            ],
            "input_digest": digest(outputs[Path("models/model.json")]),
            "model_ref": "models/model.json",
            "evidence_refs": ["symbolic/not-run.json"],
        }
    )
    outputs[Path("symbolic/not-run.json")] = json_bytes(
        {
            "schema_version": 1,
            "status": "NOT_RUN",
            "solver": "NOT_RUN",
            "symbolic_executor": "NOT_RUN",
            "bounded_claims": [],
            "unknown_is_pass": False,
        }
    )

    technique_not_run: dict[Path, dict[str, Any]] = {
        Path("concurrency/schedule-campaign.json"): {
            "technique": "deterministic-schedule-exploration",
            "max_schedules": 0,
            "forbidden_outcomes": ["output-path-escape", "partial-published-pack"],
        },
        Path("queries/query-equivalence.json"): {
            "technique": "query-equivalence",
            "reason": "The bounded local publisher performs no database queries.",
        },
        Path("numeric/numeric-policy.json"): {
            "technique": "numeric-verification",
            "reason": "No money, quantity, floating-point, or tolerance claim is executed.",
        },
        Path("invariants/invariants.json"): {
            "technique": "data-money-invariants",
            "reason": "Only byte identity and count equality invariants execute locally.",
            "local_invariants": [
                "archive-byte-count-and-digest-exact",
                "engine-tree-digest-exact",
                "test-passed-equals-tests-and-failed-zero",
            ],
        },
        Path("security/security-properties.json"): {
            "technique": "security-properties",
            "local_negative_cases_ref": "corpus/negative/cases.json",
            "external_security_campaign": "NOT_RUN",
            "tenant_noninterference": "NOT_RUN",
            "network_authority_validation": "NOT_RUN",
        },
        Path("coverage/local-coverage.json"): {
            "technique": "coverage",
            "local_tests": qualification.test_count,
            "local_test_pass_rate": 1.0,
            "line_coverage": "NOT_RUN",
            "branch_coverage": "NOT_RUN",
            "source_map_coverage": "NOT_RUN",
            "evidence_trace_coverage": "NOT_RUN",
        },
    }
    for output_path, content in technique_not_run.items():
        outputs[output_path] = json_bytes(
            {
                "schema_version": 1,
                "status": (
                    "LOCAL_EXECUTED_SELF_ATTESTED"
                    if output_path
                    in {
                        Path("invariants/invariants.json"),
                        Path("security/security-properties.json"),
                        Path("coverage/local-coverage.json"),
                    }
                    else "NOT_RUN"
                ),
                **content,
            }
        )

    failure_fingerprint = digest(
        canonical_bytes(
            {
                "case_id": "NEG-PACK-RECEIPT-TAMPER",
                "expected_exception": "VerificationPackError",
                "expected_effect": "NO_PACK_PUBLICATION",
            }
        )
    )
    outputs[Path("counterexamples/input.json")] = json_bytes(
        {
            "schema_version": 1,
            "case_id": "NEG-PACK-RECEIPT-TAMPER",
            "mutation": {"field": "status", "from": "PASS", "to": "FAILED"},
            "expected_exception": "VerificationPackError",
            "expected_effect": "NO_PACK_PUBLICATION",
        }
    )
    replay_command = (
        "python3 -m unittest discover -s "
        "engines/proof-driven-harness-engine/tests -p "
        "test_publish_verification_pack.py"
    )
    outputs[Path("counterexamples/sample.json")] = json_bytes(
        {
            "schema_version": 1,
            "counterexample_id": "ce.invalid-local-qualification-receipt",
            "technique": "negative-control",
            "claim_id": claim_local_binding,
            "failure_fingerprint": failure_fingerprint,
            "fingerprint_classification": "EXPECTED_NOT_OBSERVED",
            "environment_digest": environment_digest,
            "artifact_digests": [source_digest, target_digest, receipt_digest],
            "input_ref": "counterexamples/input.json",
            "replay": {
                "command": replay_command,
                "expected_fingerprint": failure_fingerprint,
                "execution_status": "NOT_RUN",
                "trace_ref": None,
            },
            "status": "open",
            "execution_status": "NOT_RUN",
            "owner": "elmos-proof-harness-engineering",
            "classification": "declared-seeded-negative-control-not-replayed",
            "limitations": [
                "The aggregate test log is not a per-counterexample trace and is therefore not cited as replay evidence."
            ],
        }
    )
    outputs[Path("counterexamples/replay-manifest.json")] = json_bytes(
        {
            "schema_version": 1,
            "counterexample_ref": "counterexamples/sample.json",
            "command": replay_command,
            "expected_fingerprint": failure_fingerprint,
            "execution_status": "NOT_RUN",
            "external_replay": "NOT_RUN",
        }
    )

    outputs[Path("assurance/residual-risk-register.json")] = json_bytes(
        {
            "schema_version": 1,
            "risks": [
                {
                    "risk_id": "RISK-INDEPENDENT-HOLDOUT",
                    "severity": "P0",
                    "status": "OPEN_NOT_RUN",
                    "owner": "independent-verification-owner-unassigned",
                    "required_closure": "Execute untouched holdout with distinct executor and verifier.",
                },
                {
                    "risk_id": "RISK-REPRESENTATIVE-WORKLOAD",
                    "severity": "P0",
                    "status": "OPEN_NOT_RUN",
                    "owner": "product-assurance-owner-unassigned",
                    "required_closure": "Authorize and execute production-derived representative workloads.",
                },
                {
                    "risk_id": "RISK-EXTERNAL-RUNTIME",
                    "severity": "P0",
                    "status": "OPEN_NOT_RUN",
                    "owner": "runtime-assurance-owner-unassigned",
                    "required_closure": "Collect independently verified external runtime evidence.",
                },
            ],
        }
    )
    outputs[Path("assurance/assurance-case.json")] = json_bytes(
        {
            "schema_version": 1,
            "case_key": f"{PACK_KEY}-assurance-v1",
            "version": 1,
            "owner": "elmos-proof-harness-engineering",
            "top_claim": (
                "The exact bounded local receipt can generate a deterministic limited "
                "verification pack without asserting external or certified assurance."
            ),
            "claims": [
                {
                    "claim_id": claim_local_binding,
                    "statement": "The fixed local receipt bindings were independently recomputed by the publisher implementation.",
                    "status": "partially-supported",
                    "evidence_refs": [
                        "qualification/receipt-validation.json",
                        "certification/repository-binding.json",
                    ],
                    "assumptions": [
                        "Repository-owned publisher and qualifier are not independent parties."
                    ],
                    "limitations": [
                        "Local self-attestation is not independent verification."
                    ],
                },
                {
                    "claim_id": claim_local_publish,
                    "statement": "Deterministic generation and unsafe-output negative controls execute locally.",
                    "status": "partially-supported",
                    "evidence_refs": [
                        "corpus/negative/cases.json",
                        "qualification/raw/engine-tests.json",
                    ],
                    "assumptions": [
                        "The fixed local filesystem semantics match the observed test environment."
                    ],
                    "limitations": ["No independent platform replay has occurred."],
                },
                {
                    "claim_id": claim_external,
                    "statement": "External runtime, holdout, representative, and production assurance is established.",
                    "status": "unsupported",
                    "evidence_refs": [
                        "corpus/holdout/not-run.json",
                        "corpus/representative-workloads/not-run.json",
                    ],
                    "assumptions": [],
                    "limitations": [
                        "Required external and independent evidence is NOT_RUN."
                    ],
                },
            ],
            "evidence": [
                "qualification/source-receipt.json",
                "qualification/receipt-validation.json",
                "certification/repository-binding.json",
                "corpus/development/manifest.json",
                "corpus/negative/manifest.json",
            ],
            "residual_risks": [
                {
                    "risk_id": "RISK-INDEPENDENT-HOLDOUT",
                    "status": "OPEN_NOT_RUN",
                    "owner": "independent-verification-owner-unassigned",
                },
                {
                    "risk_id": "RISK-REPRESENTATIVE-WORKLOAD",
                    "status": "OPEN_NOT_RUN",
                    "owner": "product-assurance-owner-unassigned",
                },
                {
                    "risk_id": "RISK-EXTERNAL-RUNTIME",
                    "status": "OPEN_NOT_RUN",
                    "owner": "runtime-assurance-owner-unassigned",
                },
            ],
            "monitoring_obligations": [
                "Invalidate the pack when archive, engine, qualifier, receipt, raw log, publisher, or bound test bytes drift.",
                "Keep unknown, unsupported, and not-run outcomes non-success.",
            ],
            "approvals": [],
            "expiry": "ON_ANY_BOUND_DIGEST_DRIFT",
        }
    )

    bindings = _read_required_sources(repository_root, qualification, outputs)
    raw_log_bindings = []
    for path in sorted(qualification.raw_logs):
        repository_path = ENGINE_ROOT / Path(*PurePosixPath(path).parts)
        raw_log_bindings.append(
            {
                "repository_path": repository_path.as_posix(),
                "pack_copy": (
                    Path("qualification/raw") / PurePosixPath(path).name
                ).as_posix(),
                "sha256": digest(qualification.raw_logs[path].payload),
                "bytes": len(qualification.raw_logs[path].payload),
                "argv": qualification.raw_records[path]["argv"],
                "returncode": 0,
                "timed_out": False,
            }
        )
    for path in sorted(qualification.delta_raw_logs):
        repository_path = ENGINE_ROOT / Path(*PurePosixPath(path).parts)
        raw_log_bindings.append(
            {
                "repository_path": repository_path.as_posix(),
                "pack_copy": (
                    Path("qualification/delta-v3.1/raw") / PurePosixPath(path).name
                ).as_posix(),
                "sha256": digest(qualification.delta_raw_logs[path].payload),
                "bytes": len(qualification.delta_raw_logs[path].payload),
                "argv": qualification.delta_raw_records[path]["argv"],
                "returncode": 0,
                "timed_out": False,
            }
        )
    repository_binding = {
        "schema_version": 1,
        "kind": "elmos.batch35.exact-repository-binding",
        "pack_key": PACK_KEY,
        "status": "passed",
        "classification": "LOCAL_EXECUTED_SELF_ATTESTED",
        "source_digest": source_digest,
        "delta_source_digest": delta_source_digest,
        "test_digest": target_digest,
        "environment_digest": environment_digest,
        "receipt_sha256": receipt_digest,
        "delta_receipt_sha256": delta_receipt_digest,
        "delta_acceptance_binding_sha256": qualification.delta_receipt["acceptance"][
            "binding_sha256"
        ],
        "tests": qualification.test_count,
        "passed": qualification.test_count,
        "failed": qualification.receipt["tests"]["failed"]
        + qualification.receipt["tests"]["errors"]
        + qualification.receipt["tests"]["unexpected_successes"]
        + qualification.delta_receipt["tests"]["failed"]
        + qualification.delta_receipt["tests"]["errors"]
        + qualification.delta_receipt["tests"]["unexpected_successes"],
        "skipped": qualification.receipt["tests"]["skipped"]
        + qualification.receipt["tests"]["expected_failures"]
        + qualification.delta_receipt["tests"]["skipped"]
        + qualification.delta_receipt["tests"]["expected_failures"],
        "postgresql17": qualification.receipt["postgresql17"],
        "delta_runtime_evidence": {
            "postgresql17": "NOT_RUN",
            "opa": "NOT_RUN",
            "provider_runtime": "NOT_RUN",
            "remote_executor": "NOT_RUN",
            "target_environment_conformance": "NOT_RUN",
        },
        "raw_logs": raw_log_bindings,
        "repository_bindings": bindings,
        "external_evidence": "NOT_RUN",
        "independent_verification": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
        "limitations": [
            "The Batch35-required test role binds canonical engine-tree inventory bytes; it is the exact target artifact, not a claim that a single test file represents the engine.",
            "Local executor and verifier are repository-owned and not independent.",
        ],
    }
    outputs[Path("certification/repository-binding.json")] = json_bytes(
        repository_binding
    )

    outputs[Path("support-matrix.json")] = json_bytes(
        {
            "schema_version": 1,
            "pack_key": PACK_KEY,
            "capabilities": [
                {
                    "key": "exact-receipt-revalidation",
                    "status": "supported",
                    "owner": "elmos-proof-harness-engineering",
                    "evidence_refs": [
                        "qualification/receipt-validation.json",
                        "certification/repository-binding.json",
                    ],
                    "limitations": ["Local self-attested byte and test identity only."],
                },
                {
                    "key": "deterministic-safe-pack-publication",
                    "status": "supported",
                    "owner": "elmos-proof-harness-engineering",
                    "evidence_refs": [
                        "corpus/negative/cases.json",
                        "qualification/raw/engine-tests.json",
                    ],
                    "limitations": [
                        "Independent cross-platform replay remains NOT_RUN."
                    ],
                },
                {
                    "key": "advanced-verification-contracts",
                    "status": "experimental",
                    "owner": "elmos-proof-harness-engineering",
                    "evidence_refs": [
                        "validation-profile.json",
                        "properties/sample.json",
                        "metamorphic/sample.json",
                        "models/model.json",
                    ],
                    "limitations": [
                        "Mutation, fuzz, model campaign, symbolic, solver, concurrency, query, numeric, and representative executions remain NOT_RUN."
                    ],
                },
                {
                    "key": "independent-production-assurance",
                    "status": "blocked",
                    "owner": "independent-verification-owner-unassigned",
                    "evidence_refs": [
                        "corpus/holdout/not-run.json",
                        "corpus/representative-workloads/not-run.json",
                    ],
                    "limitations": [
                        "External, independent, representative, production, and certification evidence is NOT_RUN."
                    ],
                },
            ],
        }
    )

    evidence_refs = [
        "artifacts/engine-tree-inventory.json",
        "environment/local-environment.json",
        "qualification/source-receipt.json",
        "qualification/receipt-validation.json",
        "qualification/delta-v3.1/source-receipt.json",
        "qualification/delta-v3.1/receipt-validation.json",
        "qualification/delta-v3.1/acceptance-results.json",
        *[
            (Path("qualification/raw") / PurePosixPath(path).name).as_posix()
            for path in sorted(qualification.raw_logs)
        ],
        *[
            (Path("qualification/delta-v3.1/raw") / PurePosixPath(path).name).as_posix()
            for path in sorted(qualification.delta_raw_logs)
        ],
        "certification/repository-binding.json",
        "corpus/development/seed.json",
        "corpus/negative/cases.json",
    ]
    outputs[Path("certification/evidence.json")] = json_bytes(
        {
            "schema_version": 1,
            "pack_key": PACK_KEY,
            "metrics": {
                "local_tests": qualification.test_count,
                "local_test_pass_rate": 1.0,
            },
            "zero_tolerance": {"local_negative_control_failures": 0},
            "execution_states": {
                "receipt_revalidation": "LOCAL_EXECUTED_SELF_ATTESTED",
                "delta_receipt_revalidation": "LOCAL_EXECUTED_SELF_ATTESTED",
                "delta_adapter_profile_negotiation": "LOCAL_EXECUTED_SELF_ATTESTED",
                "delta_acceptance_104": "LOCAL_EXECUTED_SELF_ATTESTED",
                "development_corpus": "LOCAL_EXECUTED_SELF_ATTESTED",
                "negative_corpus": "LOCAL_EXECUTED_SELF_ATTESTED",
                "postgresql17": qualification.receipt["postgresql17"]["status"],
                "delta_postgresql17": "NOT_RUN",
                "delta_opa": "NOT_RUN",
                "delta_provider_runtime": "NOT_RUN",
                "delta_remote_executor": "NOT_RUN",
                "delta_target_environment_conformance": "NOT_RUN",
                "mutation_campaign": "NOT_RUN",
                "fuzz_campaign": "NOT_RUN",
                "model_campaign": "NOT_RUN",
                "solver_symbolic": "NOT_RUN",
                "concurrency_campaign": "NOT_RUN",
                "query_numeric_data_money": "NOT_RUN",
                "independent_holdout": "NOT_RUN",
                "representative_workloads": "NOT_RUN",
                "external_verification": "NOT_RUN",
                "certification": "NOT_CERTIFIED",
            },
            "evidence_refs": evidence_refs,
            "repository_binding_records": ["certification/repository-binding.json"],
            "integrity_manifest": "certification/integrity-manifest.json",
            "notes": [
                "Only the development and negative local corpora are passed.",
                "Both qualification receipts and their raw logs are self-attested local engineering evidence.",
                "No source ZIP content was executed by this publisher.",
            ],
        }
    )
    outputs[Path("certification/certification.json")] = json_bytes(
        {
            "schema_version": 1,
            "pack_key": PACK_KEY,
            "status": "limited",
            "owner": "elmos-proof-harness-engineering",
            "exact_scope": scope,
            "metrics": {
                "local_tests": qualification.test_count,
                "local_test_pass_rate": 1.0,
            },
            "evidence_refs": [
                "certification/evidence.json",
                "certification/repository-binding.json",
                "assurance/assurance-case.json",
            ],
            "limitations": [
                "Local evidence is self-attested and does not establish source-target semantic equivalence or universal correctness.",
                "Holdout, representative, external runtime, independent verifier, deployment, production, and customer evidence remains NOT_RUN.",
                "The pack is NOT_CERTIFIED; a zero gate process exit for a limited pack means gate evaluation completed, not that certification passed.",
            ],
            "approved_at": None,
            "certification_decision": "NOT_CERTIFIED",
        }
    )
    outputs[Path("pack.json")] = json_bytes(
        {
            "schema_version": 1,
            "pack_key": PACK_KEY,
            "version": "1.1.0",
            "status": "limited",
            "owner": "elmos-proof-harness-engineering",
            "maintenance_owner": "elmos-proof-harness-engineering",
            "scope": scope,
            "contracts": {
                "validation_profile": "validation-profile.json",
                "oracle_registry": "oracle-registry.json",
                "assurance_case": "assurance/assurance-case.json",
                "local_qualification": "contracts/local-qualification-contract.json",
                "repository_binding": "contracts/repository-binding-contract.json",
                "status_boundary": "contracts/status-boundary.json",
            },
            "corpus": {
                "development": "corpus/development",
                "negative": "corpus/negative",
                "holdout": "corpus/holdout",
                "representative_workloads": "corpus/representative-workloads",
            },
            "certification": {
                "evidence_path": "certification/evidence.json",
                "result_path": "certification/gate-result.json",
                "decision": "NOT_CERTIFIED",
            },
            "tags": [
                "advanced-verification",
                "proof-driven-harness-v3",
                "runtime-assurance-delta-v3.1",
                "local-self-attested",
                "not-certified",
            ],
        }
    )
    outputs[Path("certification/gap-inventory.md")] = (
        "# Verification gap inventory\n\n"
        "The bounded local receipt, development corpus, and negative controls are "
        "self-attested and content-bound. The following P0 obligations remain open:\n\n"
        "- Independent untouched holdout execution and review: `NOT_RUN`.\n"
        "- Authorized production-derived representative workload: `NOT_RUN`.\n"
        "- External runtime/provider verification: `NOT_RUN`.\n"
        "- Mutation, fuzz, model, solver/symbolic, concurrency, query, numeric, and "
        "data/money campaigns: `NOT_RUN`.\n"
        "- Independent assurance approval and certification: `NOT_RUN` / `NOT_CERTIFIED`.\n"
    ).encode("utf-8")
    outputs[Path("README.md")] = (
        f"# {PACK_KEY}\n\n"
        "Deterministically generated Batch 35 local verification pack for the exact "
        "proof-driven harness v3.0 base and v3.1 runtime-assurance delta qualification "
        "receipts for composite artifact 3.1.0. Only development and negative "
        "local corpora are passed. All holdout, representative, external, independent, "
        "production, and certification evidence remains `NOT_RUN` or `NOT_CERTIFIED`.\n\n"
        "Run structural validation and the conservative gate:\n\n"
        "```sh\n"
        f"python3 scripts/batch35/validate_verification_pack.py verification-packs/{PACK_KEY}\n"
        f"python3 scripts/batch35/run_verification_gate.py verification-packs/{PACK_KEY}\n"
        "```\n\n"
        "For this canonical `limited` pack, gate exit code 0 means the gate evaluation "
        "executed successfully. It does not mean certification passed. The authoritative "
        "machine fields remain `certification_decision=NOT_CERTIFIED` and "
        "`certification_readiness=BLOCKED` until the named external obligations exist. "
        "A temporary certification-request copy is used only as a negative test and is "
        "never published.\n"
    ).encode("utf-8")

    outputs[Path("certification/integrity-manifest.json")] = _integrity_manifest(
        outputs
    )
    if any(b"TODO" in payload for payload in outputs.values()):
        raise VerificationPackError("generated pack contains a forbidden placeholder")
    return outputs


def _write_all(descriptor: int, payload: bytes, label: str) -> None:
    offset = 0
    while offset < len(payload):
        try:
            written = os.write(descriptor, payload[offset:])
        except InterruptedError:
            continue
        if written <= 0:
            raise VerificationPackError(f"short write while publishing {label}")
        offset += written


def _ensure_child_directory(parent_fd: int, name: str) -> int:
    try:
        metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        try:
            os.mkdir(name, 0o755, dir_fd=parent_fd)
        except OSError as exc:
            raise VerificationPackError(
                f"cannot create private staging directory component {name!r}: {exc}"
            ) from exc
        metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if not stat.S_ISDIR(metadata.st_mode):
        raise VerificationPackError(
            f"private staging path is not a directory: {name!r}"
        )
    try:
        child_fd = os.open(name, _directory_flags(), dir_fd=parent_fd)
    except OSError as exc:
        raise VerificationPackError(
            f"cannot safely open staging directory component {name!r}: {exc}"
        ) from exc
    opened = os.fstat(child_fd)
    if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
        os.close(child_fd)
        raise VerificationPackError(f"private staging directory raced open: {name!r}")
    return child_fd


def _write_staged_file(stage_fd: int, relative: Path, payload: bytes) -> None:
    parts = _relative_parts(relative)
    current = os.dup(stage_fd)
    try:
        for part in parts[:-1]:
            following = _ensure_child_directory(current, part)
            os.close(current)
            current = following
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            descriptor = os.open(parts[-1], flags, 0o600, dir_fd=current)
        except OSError as exc:
            raise VerificationPackError(
                f"cannot safely create staged file {relative}: {exc}"
            ) from exc
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode):
                raise VerificationPackError(
                    f"staged output is not a regular file: {relative}"
                )
            _write_all(descriptor, payload, relative.as_posix())
            os.fchmod(descriptor, 0o644)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.fsync(current)
    finally:
        os.close(current)


def _read_regular_child(
    directory_fd: int,
    name: str,
    metadata: os.stat_result,
    relative: Path,
) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
    except OSError as exc:
        raise VerificationPackError(
            f"cannot safely read published output {relative}: {exc}"
        ) from exc
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (
            metadata.st_dev,
            metadata.st_ino,
        ):
            raise VerificationPackError(f"published output raced open: {relative}")
        payload = _read_descriptor(
            descriptor,
            MAX_REPOSITORY_FILE_BYTES,
            relative.as_posix(),
        )
        after = os.fstat(descriptor)
        if _identity(opened) != _identity(after) or len(payload) != opened.st_size:
            raise VerificationPackError(
                f"published output changed while reading: {relative}"
            )
        return payload
    finally:
        os.close(descriptor)


def _read_tree(
    directory_fd: int,
    prefix: tuple[str, ...] = (),
) -> dict[Path, bytes]:
    before = _identity(os.fstat(directory_fd))
    outputs: dict[Path, bytes] = {}
    for name in sorted(os.listdir(directory_fd)):
        if name in {"", ".", ".."} or "/" in name or "\x00" in name:
            raise VerificationPackError(f"unsafe published member name: {name!r}")
        relative = Path(*prefix, name)
        metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if stat.S_ISDIR(metadata.st_mode):
            try:
                child_fd = os.open(name, _directory_flags(), dir_fd=directory_fd)
            except OSError as exc:
                raise VerificationPackError(
                    f"cannot safely open published directory {relative}: {exc}"
                ) from exc
            try:
                opened = os.fstat(child_fd)
                if (opened.st_dev, opened.st_ino) != (
                    metadata.st_dev,
                    metadata.st_ino,
                ):
                    raise VerificationPackError(
                        f"published directory raced open: {relative}"
                    )
                nested = _read_tree(child_fd, (*prefix, name))
                overlap = set(outputs).intersection(nested)
                if overlap:
                    raise VerificationPackError(
                        f"duplicate published paths: {sorted(map(str, overlap))}"
                    )
                outputs.update(nested)
            finally:
                os.close(child_fd)
        elif stat.S_ISREG(metadata.st_mode):
            outputs[relative] = _read_regular_child(
                directory_fd,
                name,
                metadata,
                relative,
            )
        else:
            raise VerificationPackError(
                f"linked or special published member is forbidden: {relative}"
            )
    if before != _identity(os.fstat(directory_fd)):
        raise VerificationPackError(
            f"published directory changed while reading: {Path(*prefix)}"
        )
    return outputs


def _remove_entry_no_follow(parent_fd: int, name: str) -> None:
    """Remove one private sibling without ever following a link."""

    try:
        metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if stat.S_ISDIR(metadata.st_mode):
        child_fd = os.open(name, _directory_flags(), dir_fd=parent_fd)
        try:
            opened = os.fstat(child_fd)
            if (opened.st_dev, opened.st_ino) != (
                metadata.st_dev,
                metadata.st_ino,
            ):
                raise VerificationPackError(
                    f"private cleanup directory raced open: {name!r}"
                )
            for child in sorted(os.listdir(child_fd)):
                if child in {"", ".", ".."} or "/" in child or "\x00" in child:
                    raise VerificationPackError(
                        f"unsafe private cleanup member: {child!r}"
                    )
                _remove_entry_no_follow(child_fd, child)
        finally:
            os.close(child_fd)
        os.rmdir(name, dir_fd=parent_fd)
    else:
        os.unlink(name, dir_fd=parent_fd)


def _assert_directory_path_identity(
    root_fd: int,
    relative: Path,
    expected: FileIdentity,
) -> None:
    descriptor = _open_directory_at(root_fd, relative)
    assert descriptor is not None
    try:
        current = _identity(os.fstat(descriptor))
    finally:
        os.close(descriptor)
    if (current.device, current.inode) != (expected.device, expected.inode):
        raise VerificationPackError(
            f"anchored output parent pathname identity changed: {relative}"
        )


def _assert_expected_tree(
    actual: Mapping[Path, bytes],
    expected: Mapping[Path, bytes],
    *,
    allow_gate_outputs: bool,
) -> None:
    extra_allowed = GATE_OUTPUTS if allow_gate_outputs else frozenset()
    unexpected = set(actual).difference(expected).difference(extra_allowed)
    missing = set(expected).difference(actual)
    if missing or unexpected:
        raise VerificationPackError(
            "verification pack file set drift: "
            f"missing={sorted(map(str, missing))}, "
            f"unexpected={sorted(map(str, unexpected))}"
        )
    for path, payload in expected.items():
        if actual[path] != payload:
            raise VerificationPackError(
                f"verification pack byte drift: {path.as_posix()}"
            )


@contextmanager
def publication_lock(repository_root: Path) -> Iterator[None]:
    absolute = Path(os.path.abspath(os.fspath(repository_root)))
    lock_key = hashlib.sha256(os.fsencode(absolute)).hexdigest()[:32]
    configured_temporary_root = Path(tempfile.gettempdir())
    try:
        # macOS exposes /tmp as a system-owned symlink to /private/tmp.  Resolve
        # that alias once, then require the opened target to remain the exact
        # real directory we inspected.  The lock file itself still uses
        # O_NOFOLLOW, so an attacker cannot substitute a linked lock target.
        temporary_root = configured_temporary_root.resolve(strict=True)
        pathname = _identity(os.stat(temporary_root, follow_symlinks=False))
        temporary_fd = os.open(temporary_root, _directory_flags())
    except OSError as exc:
        raise VerificationPackError(
            f"cannot safely open temporary lock directory: {exc}"
        ) from exc
    opened = _identity(os.fstat(temporary_fd))
    effective_uid = os.geteuid()
    root_owned_sticky = pathname.mode & stat.S_ISVTX and pathname.mode & stat.S_IWOTH
    if (
        not stat.S_ISDIR(pathname.mode)
        or not stat.S_ISDIR(opened.mode)
        or (pathname.device, pathname.inode) != (opened.device, opened.inode)
        or (pathname.mode & stat.S_IWOTH and not root_owned_sticky)
        or (pathname.device == 0 and pathname.inode == 0)
        or pathname.mode != opened.mode
        or os.fstat(temporary_fd).st_uid not in {0, effective_uid}
    ):
        os.close(temporary_fd)
        raise VerificationPackError(
            "temporary lock directory is not a stable, owned, safe directory"
        )
    lock_fd = -1
    try:
        flags = (
            os.O_RDWR
            | os.O_CREAT
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        lock_name = f"elmos-proof-harness-pack-{lock_key}.lock"
        try:
            lock_fd = os.open(lock_name, flags, 0o600, dir_fd=temporary_fd)
        except OSError as exc:
            raise VerificationPackError(
                f"cannot safely open publication lock: {exc}"
            ) from exc
        if not stat.S_ISREG(os.fstat(lock_fd).st_mode):
            raise VerificationPackError("publication lock is not a regular file")
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        yield
    finally:
        if lock_fd >= 0:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(lock_fd)
        os.close(temporary_fd)


def _qualification_matches(
    first: ValidatedQualification,
    second: ValidatedQualification,
) -> bool:
    return (
        first.receipt_payload == second.receipt_payload
        and first.receipt_sha256 == second.receipt_sha256
        and first.engine_records == second.engine_records
        and first.engine_tree_sha256 == second.engine_tree_sha256
        and first.archive.payload == second.archive.payload
        and first.qualifier.payload == second.qualifier.payload
        and first.delta_receipt_payload == second.delta_receipt_payload
        and first.delta_receipt_sha256 == second.delta_receipt_sha256
        and first.delta_archive.payload == second.delta_archive.payload
        and first.delta_qualifier.payload == second.delta_qualifier.payload
        and {key: snapshot.payload for key, snapshot in first.raw_logs.items()}
        == {key: snapshot.payload for key, snapshot in second.raw_logs.items()}
        and {key: snapshot.payload for key, snapshot in first.delta_raw_logs.items()}
        == {key: snapshot.payload for key, snapshot in second.delta_raw_logs.items()}
    )


def _result(
    action: str,
    qualification: ValidatedQualification,
    outputs: Mapping[Path, bytes],
) -> dict[str, Any]:
    environment_payload = outputs[Path("environment/local-environment.json")]
    return {
        "status": "PASS",
        "action": action,
        "pack_key": PACK_KEY,
        "pack_status": "limited",
        "certification_decision": "NOT_CERTIFIED",
        "certification_readiness": "BLOCKED",
        "qualification_receipt_sha256": digest(qualification.receipt_payload),
        "delta_qualification_receipt_sha256": digest(
            qualification.delta_receipt_payload
        ),
        "source_artifact_digest": "sha256:" + ARCHIVE_SHA256,
        "delta_source_artifact_digest": "sha256:" + DELTA_ARCHIVE_SHA256,
        "composite_version": COMPOSITE_VERSION,
        "target_artifact_digest": "sha256:" + qualification.engine_tree_sha256,
        "environment_digest": digest(environment_payload),
        "managed_file_count": len(outputs),
        "external_evidence": "NOT_RUN",
        "independent_verification": "NOT_RUN",
    }


def publish_pack(repository_root: Path) -> dict[str, Any]:
    """Atomically publish the fixed pack after two complete evidence validations."""

    with publication_lock(repository_root):
        qualification = validate_qualification(repository_root)
        outputs = build_pack_outputs(repository_root, qualification)
        with repository_anchor(repository_root) as (
            absolute,
            root_fd,
            root_identity,
        ):
            verification_fd = _open_directory_at(
                root_fd,
                Path("verification-packs"),
                create=True,
            )
            assert verification_fd is not None
            parent_identity = _identity(os.fstat(verification_fd))
            stage_name = f".{PACK_KEY}.stage-{secrets.token_hex(16)}"
            backup_name = f".{PACK_KEY}.backup-{secrets.token_hex(16)}"
            stage_fd = -1
            stage_identity: FileIdentity | None = None
            old_moved = False
            stage_moved = False
            try:
                current = (
                    os.stat(
                        PACK_KEY,
                        dir_fd=verification_fd,
                        follow_symlinks=False,
                    )
                    if _entry_exists(verification_fd, PACK_KEY)
                    else None
                )
                if current is not None and not stat.S_ISDIR(current.st_mode):
                    raise VerificationPackError(
                        "fixed verification pack output is linked or non-directory"
                    )
                if current is not None:
                    current_fd = os.open(
                        PACK_KEY,
                        _directory_flags(),
                        dir_fd=verification_fd,
                    )
                    try:
                        opened = os.fstat(current_fd)
                        if (opened.st_dev, opened.st_ino) != (
                            current.st_dev,
                            current.st_ino,
                        ):
                            raise VerificationPackError(
                                "existing verification pack raced open"
                            )
                        _read_tree(current_fd)
                    finally:
                        os.close(current_fd)

                os.mkdir(stage_name, 0o700, dir_fd=verification_fd)
                stage_fd = os.open(
                    stage_name,
                    _directory_flags(),
                    dir_fd=verification_fd,
                )
                stage_identity = _identity(os.fstat(stage_fd))
                for path in sorted(outputs, key=lambda item: item.as_posix()):
                    _write_staged_file(stage_fd, path, outputs[path])
                os.fsync(stage_fd)
                _assert_expected_tree(
                    _read_tree(stage_fd),
                    outputs,
                    allow_gate_outputs=False,
                )

                second = validate_qualification(repository_root)
                second_outputs = build_pack_outputs(repository_root, second)
                if not _qualification_matches(qualification, second):
                    raise VerificationPackError(
                        "qualification changed during pack publication"
                    )
                if outputs != second_outputs:
                    raise VerificationPackError(
                        "generated pack changed during pack publication"
                    )
                _assert_directory_path_identity(
                    root_fd,
                    Path("verification-packs"),
                    parent_identity,
                )
                assert_repository_anchor(absolute, root_identity)

                if current is not None:
                    os.rename(
                        PACK_KEY,
                        backup_name,
                        src_dir_fd=verification_fd,
                        dst_dir_fd=verification_fd,
                    )
                    old_moved = True
                    moved = os.stat(
                        backup_name,
                        dir_fd=verification_fd,
                        follow_symlinks=False,
                    )
                    if (moved.st_dev, moved.st_ino) != (
                        current.st_dev,
                        current.st_ino,
                    ):
                        raise VerificationPackError(
                            "existing verification pack identity changed during backup"
                        )
                _assert_directory_path_identity(
                    root_fd,
                    Path("verification-packs"),
                    parent_identity,
                )
                os.rename(
                    stage_name,
                    PACK_KEY,
                    src_dir_fd=verification_fd,
                    dst_dir_fd=verification_fd,
                )
                stage_moved = True
                os.fsync(verification_fd)
                published = os.stat(
                    PACK_KEY,
                    dir_fd=verification_fd,
                    follow_symlinks=False,
                )
                assert stage_identity is not None
                if (published.st_dev, published.st_ino) != (
                    stage_identity.device,
                    stage_identity.inode,
                ):
                    raise VerificationPackError("published pack identity is invalid")
                _assert_directory_path_identity(
                    root_fd,
                    Path("verification-packs"),
                    parent_identity,
                )
                assert_repository_anchor(absolute, root_identity)
                if old_moved:
                    _remove_entry_no_follow(verification_fd, backup_name)
                    old_moved = False
                os.fsync(verification_fd)
            except BaseException:
                if stage_moved:
                    failed_name = f".{PACK_KEY}.failed-{secrets.token_hex(16)}"
                    try:
                        os.rename(
                            PACK_KEY,
                            failed_name,
                            src_dir_fd=verification_fd,
                            dst_dir_fd=verification_fd,
                        )
                        stage_moved = False
                        if old_moved:
                            os.rename(
                                backup_name,
                                PACK_KEY,
                                src_dir_fd=verification_fd,
                                dst_dir_fd=verification_fd,
                            )
                            old_moved = False
                        _remove_entry_no_follow(verification_fd, failed_name)
                    except OSError:
                        pass
                elif old_moved:
                    try:
                        os.rename(
                            backup_name,
                            PACK_KEY,
                            src_dir_fd=verification_fd,
                            dst_dir_fd=verification_fd,
                        )
                        old_moved = False
                    except OSError:
                        pass
                try:
                    _remove_entry_no_follow(verification_fd, stage_name)
                except (OSError, VerificationPackError):
                    pass
                raise
            finally:
                if stage_fd >= 0:
                    os.close(stage_fd)
                os.close(verification_fd)
        check_pack(repository_root)
        return _result("publish", qualification, outputs)


def _entry_exists(parent_fd: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return True


def check_pack(repository_root: Path) -> dict[str, Any]:
    """Rebuild and byte-compare the fixed pack; optional gate outputs are derived."""

    qualification = validate_qualification(repository_root)
    expected = build_pack_outputs(repository_root, qualification)
    with repository_anchor(repository_root) as (absolute, root_fd, root_identity):
        pack_fd = _open_directory_at(root_fd, PACK_RELATIVE)
        assert pack_fd is not None
        try:
            actual = _read_tree(pack_fd)
        finally:
            os.close(pack_fd)
        _assert_expected_tree(actual, expected, allow_gate_outputs=True)
        assert_repository_anchor(absolute, root_identity)
    second = validate_qualification(repository_root)
    if not _qualification_matches(qualification, second):
        raise VerificationPackError("qualification changed during pack check")
    if expected != build_pack_outputs(repository_root, second):
        raise VerificationPackError("generated pack changed during pack check")
    return _result("check", qualification, expected)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[3],
        help="repository root; output remains fixed under verification-packs/",
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--publish", action="store_true")
    action.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = (
            publish_pack(args.repo_root) if args.publish else check_pack(args.repo_root)
        )
    except (OSError, ValueError, VerificationPackError) as exc:
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "pack_key": PACK_KEY,
                    "certification_decision": "NOT_CERTIFIED",
                    "error": str(exc),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
