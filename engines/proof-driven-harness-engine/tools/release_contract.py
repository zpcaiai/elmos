#!/usr/bin/env python3
"""Generate and verify the proof-harness release contract.

The contract is repository-owned release metadata.  It never executes the
untrusted source archive.  A successful check proves byte identity for the
listed local files only; it is not a signature, provenance attestation,
distribution approval, or certification decision.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import sysconfig
from typing import Any, BinaryIO, Iterator, Mapping, NamedTuple, Sequence
import unicodedata
import zipfile


ARTIFACT = "elmos-proof-driven-harness-engine@3.1.0"
SOURCE_MATERIALS = (
    {
        "archiveBytes": 5_601_254,
        "archiveSha256": "sha256:552268611c3edc55f58c6d4d488adaaeda8a549212cc5dc52c06e4333e0c3e07",
        "name": "elmos-proof-driven-agentic-harness-repository-semantic-compiler",
        "role": "base-declarative-source",
        "version": "3.0.0",
    },
    {
        "archiveBytes": 173_228,
        "archiveSha256": "sha256:13ba6f089d3c367affe3e03999418029873d842e07a8c80cfaeeffb4308a7a37",
        "name": "elmos-v3-harness-runtime-assurance-delta",
        "role": "runtime-assurance-delta-declarative-source",
        "version": "3.1.0",
    },
)
MANIFEST_RELATIVE = Path("supply-chain/release-contract-manifest.json")
ASSET_INSTALL_RELATIVE = Path("share/elmos-proof-harness")
MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_WHEEL_ENTRIES = 512
MAX_WHEEL_COMPRESSED_BYTES = 256 * 1024 * 1024
MAX_WHEEL_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_WHEEL_COMPRESSION_RATIO = 100
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_TREE_ENTRIES = 512
MAX_TREE_DEPTH = 32
EXCLUDED_NAMES = frozenset(
    {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", "build", "dist"}
)
SCHEMA_NAMES = (
    "admission.schema.json",
    "adapter-contract.schema.json",
    "architecture-graph.schema.json",
    "completion-certificate.schema.json",
    "completion-review.schema.json",
    "domain-pack.schema.json",
    "environment-authority.schema.json",
    "evidence.schema.json",
    "goal-contract.schema.json",
    "invocation.schema.json",
    "proof-obligation-graph.schema.json",
    "proof-result.schema.json",
    "repository-evidence-graph.schema.json",
    "result.schema.json",
    "revision-set.schema.json",
    "semantic-ir.schema.json",
    "semantic-profile.schema.json",
    "workflow-ir.schema.json",
)
DELTA_SCHEMA_NAMES = (
    "capability-lease.schema.json",
    "delta-invocation.schema.json",
    "delta-result.schema.json",
    "durable-event-registration.schema.json",
    "environment-authority-snapshot.schema.json",
    "executor-generation.schema.json",
    "permission-profile-replay.schema.json",
    "protocol-capabilities.schema.json",
    "skill-provenance.schema.json",
    "step-execution-plan.schema.json",
    "subagent-execution-spec.schema.json",
    "tool-result-commit.schema.json",
    "typed-ingress.schema.json",
    "verified-security-context.schema.json",
    "workspace-lease.schema.json",
)
CLAIM_BOUNDARY = {
    "certification": "NOT_CERTIFIED",
    "commercialDistribution": "BLOCKED",
    "externalEvidence": "NOT_RUN",
    "localEngineeringMaximum": "READY_FOR_EXTERNAL_GATE",
}
RUNTIME_SOURCE_NAMES = (
    "__init__.py",
    "__main__.py",
    "adapters.py",
    "architecture.py",
    "assurance_policies.py",
    "authority.py",
    "canonical.py",
    "certification.py",
    "certification_store.py",
    "cli.py",
    "contracts.py",
    "control_plane.py",
    "delta.py",
    "delta_storage.py",
    "domains.py",
    "errors.py",
    "evidence.py",
    "observability.py",
    "policy.py",
    "postgres.py",
    "proof_graph.py",
    "repository.py",
    "runtime_assurance.py",
    "scheduler.py",
    "semantic.py",
    "service.py",
    "skills.py",
    "storage.py",
    "store.py",
    "transformation.py",
    "workflow.py",
)
DELTA_EXAMPLE_NAMES = tuple(
    name.replace(".schema.json", ".example.json") for name in DELTA_SCHEMA_NAMES
)
DELTA_API_NAMES = (
    "asyncapi-overlay.yaml",
    "elmos_v3_delta.proto",
    "openapi-overlay.yaml",
)
DELTA_ADAPTER_NAMES = (
    "codex-main-2026-08-28.yaml",
    "codex-stable-0.150.1.yaml",
    "deepseek-harness-0.1.1-rc.2.yaml",
    "deepseek-harness-0.1.2-alpha.1.yaml",
    "upstream-type-map.yaml",
)
DELTA_POLICY_NAMES = (
    "capability_authority.rego",
    "event_ingress.rego",
    "permission_replay.rego",
    "result_commit.rego",
    "skill_trust.rego",
)
DELTA_MATRIX_NAMES = (
    "capability-security.yaml",
    "ownership-fencing.yaml",
    "permission-replay.yaml",
    "protocol-events-ingress.yaml",
    "tool-result-lifecycle.yaml",
)
HELM_FILE_NAMES = (
    "Chart.yaml",
    "templates/_helpers.tpl",
    "templates/deployment.yaml",
    "templates/networkpolicy.yaml",
    "templates/pdb.yaml",
    "templates/prometheusrule.yaml",
    "templates/service.yaml",
    "templates/serviceaccount.yaml",
    "templates/servicemonitor.yaml",
    "values.schema.json",
    "values.yaml",
)
DELTA_OBSERVABILITY_NAMES = ("alerts.yaml", "metrics.yaml")
TOOL_FILE_NAMES = (
    "apply_delta_migration.py",
    "apply_postgres_migration.py",
    "publish_verification_pack.py",
    "qualify_delta.py",
    "qualify_local.py",
    "release_contract.py",
    "run_structured_unittest.py",
)
WHEEL_DISTRIBUTION = "elmos_proof_driven_harness_engine-3.1.0"
WHEEL_DIST_INFO_NAMES = (
    "METADATA",
    "RECORD",
    "WHEEL",
    "entry_points.txt",
    "top_level.txt",
)


def _release_entries() -> tuple[tuple[str, str], ...]:
    entries: list[tuple[str, str]] = []
    entries.extend(
        ("runtime-source", f"src/elmos_proof_harness/{name}")
        for name in RUNTIME_SOURCE_NAMES
    )
    entries.extend(("json-schema", f"schemas/{name}") for name in SCHEMA_NAMES)
    entries.extend(
        ("delta-json-schema", f"schemas/delta-v3.1/{name}")
        for name in DELTA_SCHEMA_NAMES
    )
    entries.extend(
        (
            ("openapi", "openapi/proof-harness-v3.openapi.yaml"),
            ("database-migration", "migrations/V001__proof_harness_core.sql"),
            (
                "database-delta-migration",
                "migrations/V304__harness_runtime_assurance_delta.sql",
            ),
            ("observability-catalog", "observability/metrics.yaml"),
            ("observability-rule-source", "observability/alerts.yaml"),
            ("supply-chain-boundary", "supply-chain/README.md"),
            ("supply-chain-policy", "supply-chain/release-policy.json"),
            (
                "delta-acceptance-traceability",
                "supply-chain/delta-v3.1-acceptance-bindings.json",
            ),
            (
                "composite-source-integrity",
                "supply-chain/delta-v3.1-integrity.json",
            ),
            ("source-dependency-sbom", "supply-chain/sbom.cdx.json"),
            ("production-dependency-lock", "deploy/requirements-production.txt"),
            ("container-build-contract", "deploy/Dockerfile"),
            ("deployment-boundary", "deploy/README.md"),
            ("packaging-contract", "pyproject.toml"),
            ("implementation-boundary", "README.md"),
            (
                "postgres-migration-applicator",
                "tools/apply_postgres_migration.py",
            ),
            (
                "postgres-delta-migration-applicator",
                "tools/apply_delta_migration.py",
            ),
            ("release-contract-verifier", "tools/release_contract.py"),
            ("structured-test-runner", "tools/run_structured_unittest.py"),
            ("local-qualification-producer", "tools/qualify_local.py"),
            (
                "delta-local-qualification-producer",
                "tools/qualify_delta.py",
            ),
            (
                "verification-pack-publisher",
                "tools/publish_verification_pack.py",
            ),
        )
    )
    entries.extend(
        ("helm-release-asset", f"deploy/helm/proof-harness/{name}")
        for name in HELM_FILE_NAMES
    )
    entries.extend(
        ("delta-example", f"examples/delta-v3.1/{name}") for name in DELTA_EXAMPLE_NAMES
    )
    entries.extend(
        ("delta-api-contract", f"api/delta-v3.1/{name}") for name in DELTA_API_NAMES
    )
    entries.extend(
        ("delta-adapter-profile", f"adapters/delta-v3.1/{name}")
        for name in DELTA_ADAPTER_NAMES
    )
    entries.extend(
        ("delta-observability", f"observability/delta-v3.1/{name}")
        for name in DELTA_OBSERVABILITY_NAMES
    )
    entries.extend(
        ("delta-policy-source", f"policies/delta-v3.1/{name}")
        for name in DELTA_POLICY_NAMES
    )
    entries.append(
        ("delta-verification-contract", "verification/delta-v3.1/delta-gates.yaml")
    )
    entries.extend(
        (
            "delta-verification-contract",
            f"verification/delta-v3.1/matrices/{name}",
        )
        for name in DELTA_MATRIX_NAMES
    )
    return tuple(sorted(entries, key=lambda item: item[1]))


RELEASE_ENTRIES = _release_entries()
RELEASE_ROLE_BY_PATH = {path: role for role, path in RELEASE_ENTRIES}
MANAGED_TREE_ROOTS = (
    "src/elmos_proof_harness",
    "schemas",
    "examples/delta-v3.1",
    "api/delta-v3.1",
    "adapters/delta-v3.1",
    "migrations",
    "observability",
    "openapi",
    "policies/delta-v3.1",
    "verification/delta-v3.1",
    "deploy",
    "supply-chain",
    "tools",
)


class ReleaseContractError(RuntimeError):
    """Raised when release-contract bytes fail closed."""


class _FileSnapshot(NamedTuple):
    payload: bytes
    identity: tuple[int, int, int, int, int]


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def digest(payload: bytes) -> str:
    return "sha256:" + sha256_hex(payload)


def _absolute_path(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _directory_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _directory_identity(metadata: os.stat_result) -> tuple[int, int]:
    return metadata.st_dev, metadata.st_ino


def _identity(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _canonical_relative(value: str, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, str) or not value:
        raise ReleaseContractError(f"{label} must be a non-empty string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ReleaseContractError(f"{label} is not valid Unicode: {value!r}") from exc
    if "\\" in value or any(
        ord(character) < 32 or ord(character) == 127 for character in value
    ):
        raise ReleaseContractError(f"{label} contains a forbidden character: {value!r}")
    if (
        unicodedata.normalize("NFC", value) != value
        or unicodedata.normalize("NFKC", value) != value
    ):
        raise ReleaseContractError(f"{label} is not canonical Unicode: {value!r}")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ReleaseContractError(f"{label} is not a canonical POSIX path: {value!r}")
    return path.parts


def _open_child_directory(parent_fd: int, name: str, label: str) -> int:
    descriptor = -1
    try:
        before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISDIR(before.st_mode):
            raise ReleaseContractError(
                f"directory path component is linked or not a directory: {label}"
            )
        descriptor = os.open(name, _directory_flags(), dir_fd=parent_fd)
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            os.close(descriptor)
            descriptor = -1
            raise ReleaseContractError(
                f"directory path component changed while opening: {label}"
            )
        return descriptor
    except ReleaseContractError:
        if descriptor >= 0:
            os.close(descriptor)
        raise
    except OSError as exc:
        if descriptor >= 0:
            os.close(descriptor)
        raise ReleaseContractError(
            f"cannot safely open directory path component {label}: {exc}"
        ) from exc


def _open_anchored_path(
    absolute: Path,
) -> tuple[int, tuple[tuple[int, int], ...]]:
    descriptor = -1
    identities: list[tuple[int, int]] = []
    try:
        descriptor = os.open(os.sep, _directory_flags())
        identities.append(_directory_identity(os.fstat(descriptor)))
        traversed = ""
        for part in absolute.parts[1:]:
            traversed += "/" + part
            child = _open_child_directory(descriptor, part, traversed)
            os.close(descriptor)
            descriptor = child
            identities.append(_directory_identity(os.fstat(descriptor)))
        return descriptor, tuple(identities)
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        raise


def _revalidate_anchored_path(
    absolute: Path,
    identities: tuple[tuple[int, int], ...],
) -> None:
    descriptor = -1
    try:
        descriptor, current = _open_anchored_path(absolute)
        if current != identities:
            raise ReleaseContractError(
                f"anchored directory pathname identity changed: {absolute}"
            )
    except ReleaseContractError:
        raise
    except OSError as exc:
        raise ReleaseContractError(
            f"anchored directory pathname cannot be revalidated: {absolute}: {exc}"
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


@contextmanager
def _anchored_directory(path: Path) -> Iterator[tuple[Path, int]]:
    absolute = _absolute_path(path)
    descriptor = -1
    try:
        descriptor, identities = _open_anchored_path(absolute)
        before = _directory_identity(os.fstat(descriptor))
        yield absolute, descriptor
        after = _directory_identity(os.fstat(descriptor))
        if before != after:
            raise ReleaseContractError(
                f"anchored directory identity changed: {absolute}"
            )
        _revalidate_anchored_path(absolute, identities)
    except ReleaseContractError:
        raise
    except OSError as exc:
        raise ReleaseContractError(
            f"cannot safely anchor directory {absolute}: {exc}"
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


@contextmanager
def _open_directory_at(root_fd: int, relative: str) -> Iterator[int]:
    parts = _canonical_relative(relative, label="relative directory path")
    descriptor = -1
    try:
        descriptor = os.dup(root_fd)
        traversed: list[str] = []
        for part in parts:
            traversed.append(part)
            child = _open_child_directory(descriptor, part, "/".join(traversed))
            os.close(descriptor)
            descriptor = child
        expected = _directory_identity(os.fstat(descriptor))
        yield descriptor
        if _directory_identity(os.fstat(descriptor)) != expected:
            raise ReleaseContractError(
                f"relative directory identity changed: {relative}"
            )
        current = os.dup(root_fd)
        try:
            traversed = []
            for part in parts:
                traversed.append(part)
                child = _open_child_directory(current, part, "/".join(traversed))
                os.close(current)
                current = child
            if _directory_identity(os.fstat(current)) != expected:
                raise ReleaseContractError(
                    f"relative directory pathname identity changed: {relative}"
                )
        finally:
            os.close(current)
    finally:
        if descriptor >= 0:
            os.close(descriptor)


@contextmanager
def _duplicated_directory(root_fd: int) -> Iterator[int]:
    descriptor = os.dup(root_fd)
    try:
        yield descriptor
    finally:
        os.close(descriptor)


def _revalidate_regular_name(
    parent_fd: int,
    name: str,
    label: str,
    expected: tuple[int, int, int, int, int],
) -> None:
    descriptor = -1
    try:
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if stat.S_ISLNK(current.st_mode) or not stat.S_ISREG(current.st_mode):
            raise ReleaseContractError(
                f"release input pathname is linked or not regular: {label}"
            )
        descriptor = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
        reopened = os.fstat(descriptor)
        if _identity(current) != expected or _identity(reopened) != expected:
            raise ReleaseContractError(
                f"release input pathname identity changed: {label}"
            )
    except ReleaseContractError:
        raise
    except OSError as exc:
        raise ReleaseContractError(
            f"release input pathname cannot be revalidated {label}: {exc}"
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


@contextmanager
def _open_regular_at(
    root_fd: int, relative: str, *, limit: int
) -> Iterator[tuple[int, tuple[int, int, int, int, int]]]:
    parts = _canonical_relative(relative, label="release input path")
    parent = "/".join(parts[:-1])
    parent_context = (
        _open_directory_at(root_fd, parent)
        if parent
        else _duplicated_directory(root_fd)
    )
    with parent_context as parent_fd:
        name = parts[-1]
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = -1
        try:
            before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
                raise ReleaseContractError(
                    f"release input is linked or not regular: {relative}"
                )
            if before.st_size > limit:
                raise ReleaseContractError(
                    f"release input exceeds byte limit: {relative}"
                )
            descriptor = os.open(name, flags, dir_fd=parent_fd)
            after = os.fstat(descriptor)
            expected = _identity(after)
            if _identity(before) != expected:
                raise ReleaseContractError(
                    f"release input changed while opening: {relative}"
                )
            yield descriptor, expected
            _revalidate_regular_name(parent_fd, name, relative, expected)
        except OSError as exc:
            raise ReleaseContractError(
                f"cannot safely open release input {relative}: {exc}"
            ) from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)


def _read_descriptor(descriptor: int, label: str, *, limit: int) -> bytes:
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode):
        raise ReleaseContractError(f"release input is not a regular file: {label}")
    if before.st_size > limit:
        raise ReleaseContractError(f"release input exceeds byte limit: {label}")
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(descriptor, min(1024 * 1024, limit + 1 - total))
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise ReleaseContractError(f"release input exceeds byte limit: {label}")
        chunks.append(chunk)
    after = os.fstat(descriptor)
    payload = b"".join(chunks)
    if _identity(before) != _identity(after) or len(payload) != before.st_size:
        raise ReleaseContractError(f"release input changed while reading: {label}")
    return payload


def _read_file_snapshot_at(
    root_fd: int,
    relative: str,
    *,
    limit: int = MAX_FILE_BYTES,
) -> _FileSnapshot:
    with _open_regular_at(root_fd, relative, limit=limit) as (
        descriptor,
        identity,
    ):
        payload = _read_descriptor(descriptor, relative, limit=limit)
    return _FileSnapshot(payload=payload, identity=identity)


def _read_file_at(root_fd: int, relative: str, *, limit: int = MAX_FILE_BYTES) -> bytes:
    return _read_file_snapshot_at(root_fd, relative, limit=limit).payload


def _revalidate_file_at(
    root_fd: int,
    relative: str,
    expected: tuple[int, int, int, int, int],
) -> None:
    parts = _canonical_relative(relative, label="release input path")
    parent = "/".join(parts[:-1])
    parent_context = (
        _open_directory_at(root_fd, parent)
        if parent
        else _duplicated_directory(root_fd)
    )
    with parent_context as parent_fd:
        _revalidate_regular_name(parent_fd, parts[-1], relative, expected)


def _safe_bytes(path: Path, *, limit: int = MAX_FILE_BYTES) -> bytes:
    absolute = _absolute_path(path)
    with _anchored_directory(absolute.parent) as (_, parent_fd):
        return _read_file_at(parent_fd, absolute.name, limit=limit)


def _validate_pyc_directory(directory_fd: int, label: str) -> None:
    collision_keys: set[str] = set()
    names = sorted(os.listdir(directory_fd))
    if len(names) > MAX_TREE_ENTRIES:
        raise ReleaseContractError(f"too many generated bytecode members under {label}")
    for name in names:
        _canonical_relative(name, label=f"generated bytecode member under {label}")
        collision_key = unicodedata.normalize("NFKC", name).casefold()
        if collision_key in collision_keys:
            raise ReleaseContractError(
                f"generated bytecode name collision under {label}: {name}"
            )
        collision_keys.add(collision_key)
        metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or not name.endswith(".pyc")
        ):
            raise ReleaseContractError(
                f"unexpected generated bytecode member: {label}/{name}"
            )


def _walk_tree_at(
    root_fd: int,
    relative: str,
    *,
    allow_pycache: bool = False,
) -> tuple[set[str], set[str]]:
    files: set[str] = set()
    directories: set[str] = set()
    collision_keys: set[str] = set()
    observed_entries = 0

    def walk(directory_fd: int, prefix: str, depth: int) -> None:
        nonlocal observed_entries
        directory_before = _identity(os.fstat(directory_fd))
        if depth > MAX_TREE_DEPTH:
            raise ReleaseContractError(
                f"filesystem tree exceeds depth limit: {relative}/{prefix}"
            )
        local_collision_keys: set[str] = set()
        names = sorted(os.listdir(directory_fd))
        observed_entries += len(names)
        if observed_entries > MAX_TREE_ENTRIES:
            raise ReleaseContractError(
                f"filesystem tree exceeds entry limit: {relative}"
            )
        for name in names:
            _canonical_relative(
                name, label=f"filesystem member under {relative}/{prefix}"
            )
            local_key = unicodedata.normalize("NFKC", name).casefold()
            if local_key in local_collision_keys:
                raise ReleaseContractError(
                    f"filesystem name collision under {relative}/{prefix}: {name}"
                )
            local_collision_keys.add(local_key)
            member = f"{prefix}/{name}" if prefix else name
            global_key = unicodedata.normalize("NFKC", member).casefold()
            if global_key in collision_keys:
                raise ReleaseContractError(
                    f"filesystem path collision under {relative}: {member}"
                )
            collision_keys.add(global_key)
            metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if stat.S_ISLNK(metadata.st_mode):
                raise ReleaseContractError(
                    f"linked filesystem member is forbidden: {relative}/{member}"
                )
            if stat.S_ISDIR(metadata.st_mode):
                child = _open_child_directory(
                    directory_fd, name, f"{relative}/{member}"
                )
                child_identity = _identity(os.fstat(child))
                try:
                    if allow_pycache and name == "__pycache__":
                        _validate_pyc_directory(child, f"{relative}/{member}")
                    else:
                        directories.add(member)
                        walk(child, member, depth + 1)
                finally:
                    os.close(child)
                current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                if (
                    stat.S_ISLNK(current.st_mode)
                    or not stat.S_ISDIR(current.st_mode)
                    or _identity(current) != child_identity
                ):
                    raise ReleaseContractError(
                        f"filesystem directory pathname changed: {relative}/{member}"
                    )
                continue
            if not stat.S_ISREG(metadata.st_mode):
                raise ReleaseContractError(
                    f"special filesystem member is forbidden: {relative}/{member}"
                )
            files.add(member)

        if _identity(os.fstat(directory_fd)) != directory_before:
            raise ReleaseContractError(
                f"filesystem directory changed while scanning: {relative}/{prefix}"
            )

    directory_context = (
        _duplicated_directory(root_fd)
        if relative == "."
        else _open_directory_at(root_fd, relative)
    )
    with directory_context as directory_fd:
        walk(directory_fd, "", 0)
    return files, directories


def _parent_directories(paths: set[str]) -> set[str]:
    result: set[str] = set()
    for value in paths:
        parts = PurePosixPath(value).parts[:-1]
        for index in range(1, len(parts) + 1):
            result.add(PurePosixPath(*parts[:index]).as_posix())
    return result


def _validate_repository_tree(root_fd: int) -> None:
    release_paths = set(RELEASE_ROLE_BY_PATH)
    for tree_root in MANAGED_TREE_ROOTS:
        prefix = tree_root + "/"
        expected_files = {
            path.removeprefix(prefix)
            for path in release_paths
            if path.startswith(prefix)
        }
        optional_manifest = tree_root == "supply-chain"
        if optional_manifest:
            expected_with_manifest = expected_files | {MANIFEST_RELATIVE.name}
        else:
            expected_with_manifest = expected_files
        actual_files, actual_directories = _walk_tree_at(
            root_fd,
            tree_root,
            allow_pycache=tree_root in {"src/elmos_proof_harness", "tools"},
        )
        accepted_file_sets = {
            frozenset(expected_files),
            frozenset(expected_with_manifest),
        }
        if frozenset(actual_files) not in accepted_file_sets:
            missing = sorted(expected_files.difference(actual_files))
            unexpected = sorted(actual_files.difference(expected_with_manifest))
            raise ReleaseContractError(
                f"managed release tree is not exact ({tree_root}): "
                f"missing={missing}, unexpected={unexpected}"
            )
        expected_directories = _parent_directories(expected_with_manifest)
        if actual_directories != expected_directories:
            missing = sorted(expected_directories.difference(actual_directories))
            unexpected = sorted(actual_directories.difference(expected_directories))
            raise ReleaseContractError(
                f"managed release directory set is not exact ({tree_root}): "
                f"missing={missing}, unexpected={unexpected}"
            )


def inventory_paths(root: Path) -> list[tuple[str, Path]]:
    """Return the exact manifest-owned release inventory."""

    with _anchored_directory(root) as (absolute, root_fd):
        _validate_repository_tree(root_fd)
        return [(role, absolute / Path(path)) for role, path in RELEASE_ENTRIES]


def _build_manifest_at(root_fd: int) -> dict[str, Any]:
    _validate_repository_tree(root_fd)
    files: list[dict[str, Any]] = []
    role_counts: dict[str, int] = {}
    snapshots: dict[str, _FileSnapshot] = {}
    for role, relative in RELEASE_ENTRIES:
        snapshot = _read_file_snapshot_at(root_fd, relative)
        payload = snapshot.payload
        snapshots[relative] = snapshot
        files.append(
            {
                "bytes": len(payload),
                "path": relative,
                "role": role,
                "sha256": digest(payload),
            }
        )
        role_counts[role] = role_counts.get(role, 0) + 1
    for _, relative in RELEASE_ENTRIES:
        repeated = _read_file_snapshot_at(root_fd, relative)
        original = snapshots[relative]
        if (
            repeated.payload != original.payload
            or repeated.identity != original.identity
        ):
            raise ReleaseContractError(
                f"release input changed across manifest snapshot: {relative}"
            )
    _validate_repository_tree(root_fd)
    for _, relative in RELEASE_ENTRIES:
        _revalidate_file_at(root_fd, relative, snapshots[relative].identity)
    body: dict[str, Any] = {
        "artifact": ARTIFACT,
        "claimBoundary": dict(CLAIM_BOUNDARY),
        "counts": {
            "files": len(files),
            "roles": dict(sorted(role_counts.items())),
            "schemas": len(SCHEMA_NAMES) + len(DELTA_SCHEMA_NAMES),
            "baseSchemas": len(SCHEMA_NAMES),
            "deltaSchemas": len(DELTA_SCHEMA_NAMES),
        },
        "files": files,
        "hashAlgorithm": "sha256",
        "kind": "elmos.proof-harness.release-contract",
        "schemaVersion": "1.1.0",
        "sourceMaterials": _source_materials(),
    }
    return {**body, "contractRoot": digest(canonical_bytes(body))}


def build_manifest(root: Path) -> dict[str, Any]:
    with _anchored_directory(root) as (_, root_fd):
        return _build_manifest_at(root_fd)


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ReleaseContractError(f"duplicate release manifest field: {key}")
        value[key] = item
    return value


def _valid_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _expected_role_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for role, _ in RELEASE_ENTRIES:
        counts[role] = counts.get(role, 0) + 1
    return dict(sorted(counts.items()))


def _source_materials() -> list[dict[str, Any]]:
    return [dict(material) for material in SOURCE_MATERIALS]


def _load_manifest_checked(value: Any, payload: bytes, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ReleaseContractError(f"release manifest must be an object ({label})")
    expected_keys = {
        "artifact",
        "claimBoundary",
        "contractRoot",
        "counts",
        "files",
        "hashAlgorithm",
        "kind",
        "schemaVersion",
        "sourceMaterials",
    }
    if set(value) != expected_keys:
        raise ReleaseContractError(f"release manifest fields are not exact ({label})")
    if payload != json_bytes(value):
        raise ReleaseContractError(f"release manifest is not canonical JSON ({label})")
    if (
        value["artifact"] != ARTIFACT
        or value["claimBoundary"] != CLAIM_BOUNDARY
        or value["hashAlgorithm"] != "sha256"
        or value["kind"] != "elmos.proof-harness.release-contract"
        or value["schemaVersion"] != "1.1.0"
        or value["sourceMaterials"] != _source_materials()
    ):
        raise ReleaseContractError(
            f"release manifest identity/boundary mismatch ({label})"
        )
    counts = value["counts"]
    if not isinstance(counts, dict) or set(counts) != {
        "baseSchemas",
        "deltaSchemas",
        "files",
        "roles",
        "schemas",
    }:
        raise ReleaseContractError(f"release manifest counts are not exact ({label})")
    scalar_counts = {
        "baseSchemas": len(SCHEMA_NAMES),
        "deltaSchemas": len(DELTA_SCHEMA_NAMES),
        "files": len(RELEASE_ENTRIES),
        "schemas": len(SCHEMA_NAMES) + len(DELTA_SCHEMA_NAMES),
    }
    if any(
        not isinstance(counts[key], int)
        or isinstance(counts[key], bool)
        or counts[key] != expected
        for key, expected in scalar_counts.items()
    ):
        raise ReleaseContractError(f"release manifest scalar counts mismatch ({label})")
    expected_roles = _expected_role_counts()
    roles = counts["roles"]
    if (
        not isinstance(roles, dict)
        or set(roles) != set(expected_roles)
        or any(
            not isinstance(role, str)
            or not isinstance(count, int)
            or isinstance(count, bool)
            for role, count in roles.items()
        )
        or roles != expected_roles
    ):
        raise ReleaseContractError(f"release manifest role counts mismatch ({label})")
    files = value["files"]
    if not isinstance(files, list) or len(files) != len(RELEASE_ENTRIES):
        raise ReleaseContractError(f"release manifest file list is not exact ({label})")
    actual_paths: list[str] = []
    collision_keys: set[str] = set()
    for entry in files:
        if not isinstance(entry, dict) or set(entry) != {
            "bytes",
            "path",
            "role",
            "sha256",
        }:
            raise ReleaseContractError(
                f"release manifest file entry is not exact ({label})"
            )
        relative = entry["path"]
        _canonical_relative(relative, label="release manifest file path")
        collision_key = unicodedata.normalize("NFKC", relative).casefold()
        if collision_key in collision_keys:
            raise ReleaseContractError(
                f"release manifest file path collision ({label}): {relative}"
            )
        collision_keys.add(collision_key)
        expected_role = RELEASE_ROLE_BY_PATH.get(relative)
        if expected_role is None or entry["role"] != expected_role:
            raise ReleaseContractError(
                f"release manifest path/role is not allowlisted ({label}): {relative}"
            )
        byte_count = entry["bytes"]
        if (
            not isinstance(byte_count, int)
            or isinstance(byte_count, bool)
            or byte_count < 0
            or byte_count > MAX_FILE_BYTES
        ):
            raise ReleaseContractError(
                f"release manifest byte count is invalid ({label}): {relative}"
            )
        if not _valid_digest(entry["sha256"]):
            raise ReleaseContractError(
                f"release manifest digest is invalid ({label}): {relative}"
            )
        actual_paths.append(relative)
    expected_paths = [path for _, path in RELEASE_ENTRIES]
    if actual_paths != expected_paths:
        raise ReleaseContractError(
            f"release manifest paths/order are not exact ({label})"
        )
    if not _valid_digest(value["contractRoot"]):
        raise ReleaseContractError(
            f"release manifest contract root is malformed ({label})"
        )
    body = {key: value[key] for key in value if key != "contractRoot"}
    if value["contractRoot"] != digest(canonical_bytes(body)):
        raise ReleaseContractError(f"release manifest contract root mismatch ({label})")
    return value


def _load_manifest(payload: bytes, label: str) -> Mapping[str, Any]:
    try:
        decoded = payload.decode("utf-8")
        value = json.loads(
            decoded,
            object_pairs_hook=_strict_json_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ReleaseContractError(
                    f"invalid JSON constant in release manifest: {token}"
                )
            ),
        )
        return _load_manifest_checked(value, payload, label)
    except ReleaseContractError:
        raise
    except (
        KeyError,
        TypeError,
        ValueError,
        UnicodeDecodeError,
        UnicodeEncodeError,
        RecursionError,
        json.JSONDecodeError,
    ) as exc:
        raise ReleaseContractError(
            f"invalid release manifest ({label}): {exc}"
        ) from exc


def _expected_manifest_digest(value: str | None, payload: bytes) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        raise ReleaseContractError("expected manifest SHA-256 is malformed")
    expected = value.removeprefix("sha256:")
    if len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
        raise ReleaseContractError("expected manifest SHA-256 is malformed")
    if sha256_hex(payload) != expected:
        raise ReleaseContractError(
            "release manifest byte digest does not match the supplied pin"
        )


def check_repository(
    root: Path, expected_manifest_sha256: str | None = None
) -> Mapping[str, Any]:
    with _anchored_directory(root) as (absolute, root_fd):
        manifest_snapshot = _read_file_snapshot_at(
            root_fd,
            MANIFEST_RELATIVE.as_posix(),
            limit=MAX_MANIFEST_BYTES,
        )
        payload = manifest_snapshot.payload
        manifest = _load_manifest(payload, (absolute / MANIFEST_RELATIVE).as_posix())
        _expected_manifest_digest(expected_manifest_sha256, payload)
        expected = _build_manifest_at(root_fd)
        repeated_manifest = _read_file_snapshot_at(
            root_fd,
            MANIFEST_RELATIVE.as_posix(),
            limit=MAX_MANIFEST_BYTES,
        )
        if (
            repeated_manifest.payload != payload
            or repeated_manifest.identity != manifest_snapshot.identity
        ):
            raise ReleaseContractError(
                "release manifest changed across repository snapshot"
            )
        _revalidate_file_at(
            root_fd,
            MANIFEST_RELATIVE.as_posix(),
            manifest_snapshot.identity,
        )
    if manifest != expected:
        expected_by_path = {item["path"]: item for item in expected["files"]}
        actual_by_path: dict[str, Any] = {}
        for item in manifest.get("files", []):
            if isinstance(item, dict) and isinstance(item.get("path"), str):
                actual_by_path[item["path"]] = item
        missing = sorted(set(expected_by_path).difference(actual_by_path))
        unexpected = sorted(set(actual_by_path).difference(expected_by_path))
        changed = sorted(
            path
            for path in set(expected_by_path).intersection(actual_by_path)
            if expected_by_path[path] != actual_by_path[path]
        )
        raise ReleaseContractError(
            "release contract drift: "
            f"missing={missing}, unexpected={unexpected}, changed={changed}"
        )
    return manifest


def _atomic_write_at(root_fd: int, relative: str, payload: bytes) -> None:
    parts = _canonical_relative(relative, label="release output path")
    parent = "/".join(parts[:-1])
    name = parts[-1]
    temporary = f".{name}.{os.getpid()}.tmp"
    descriptor = -1
    with _open_directory_at(root_fd, parent) as directory_fd:
        try:
            existing = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        if existing is not None and (
            stat.S_ISLNK(existing.st_mode) or not stat.S_ISREG(existing.st_mode)
        ):
            raise ReleaseContractError(
                f"release output is linked or not regular: {relative}"
            )
        try:
            descriptor = os.open(
                temporary,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                0o644,
                dir_fd=directory_fd,
            )
            offset = 0
            while offset < len(payload):
                written = os.write(descriptor, payload[offset:])
                if written <= 0:
                    raise ReleaseContractError(f"short write: {relative}")
                offset += written
            os.fsync(descriptor)
            temporary_identity = os.fstat(descriptor)
            os.close(descriptor)
            descriptor = -1
            os.replace(
                temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd
            )
            installed = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if (
                stat.S_ISLNK(installed.st_mode)
                or not stat.S_ISREG(installed.st_mode)
                or (installed.st_dev, installed.st_ino)
                != (temporary_identity.st_dev, temporary_identity.st_ino)
            ):
                raise ReleaseContractError(
                    f"release output changed while installing: {relative}"
                )
            os.fsync(directory_fd)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            try:
                os.unlink(temporary, dir_fd=directory_fd)
            except FileNotFoundError:
                pass


def generate(root: Path) -> Mapping[str, Any]:
    with _anchored_directory(root) as (_, root_fd):
        manifest = _build_manifest_at(root_fd)
        _atomic_write_at(root_fd, MANIFEST_RELATIVE.as_posix(), json_bytes(manifest))
    return check_repository(root)


def _safe_zip_members(archive: zipfile.ZipFile) -> Mapping[str, zipfile.ZipInfo]:
    infos = archive.infolist()
    if len(infos) > MAX_WHEEL_ENTRIES:
        raise ReleaseContractError(
            f"wheel contains too many entries: {len(infos)} > {MAX_WHEEL_ENTRIES}"
        )
    members: dict[str, zipfile.ZipInfo] = {}
    collision_keys: set[str] = set()
    total_compressed = 0
    total_uncompressed = 0
    for info in infos:
        _canonical_relative(info.filename, label="wheel member")
        path = PurePosixPath(info.filename)
        normalized = path.as_posix()
        if (
            info.is_dir()
            or len(info.filename.encode("utf-8")) > 4096
            or normalized in members
            or info.flag_bits & 0x1
        ):
            raise ReleaseContractError(
                f"unsafe or duplicate wheel member: {info.filename!r}"
            )
        collision_key = unicodedata.normalize("NFKC", normalized).casefold()
        if collision_key in collision_keys:
            raise ReleaseContractError(
                f"canonical wheel member collision: {info.filename!r}"
            )
        collision_keys.add(collision_key)
        if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
            raise ReleaseContractError(
                f"unsupported wheel compression method: {normalized}"
            )
        if (
            info.file_size < 0
            or info.compress_size < 0
            or info.file_size > MAX_FILE_BYTES
        ):
            raise ReleaseContractError(f"wheel member exceeds byte limit: {normalized}")
        if info.file_size > max(info.compress_size, 1) * MAX_WHEEL_COMPRESSION_RATIO:
            raise ReleaseContractError(
                f"wheel member compression ratio exceeds limit: {normalized}"
            )
        mode = (info.external_attr >> 16) & 0xFFFF
        if mode and stat.S_IFMT(mode) not in {0, stat.S_IFREG}:
            raise ReleaseContractError(f"linked or special wheel member: {normalized}")
        total_compressed += info.compress_size
        total_uncompressed += info.file_size
        members[normalized] = info
    if total_compressed > MAX_WHEEL_COMPRESSED_BYTES:
        raise ReleaseContractError("wheel aggregate compressed bytes exceed limit")
    if total_uncompressed > MAX_WHEEL_UNCOMPRESSED_BYTES:
        raise ReleaseContractError("wheel aggregate uncompressed bytes exceed limit")
    if total_uncompressed > max(total_compressed, 1) * MAX_WHEEL_COMPRESSION_RATIO:
        raise ReleaseContractError("wheel aggregate compression ratio exceeds limit")
    return members


def _open_named_regular(parent_fd: int, name: str, label: str) -> int:
    _canonical_relative(name, label="wheel filename")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise ReleaseContractError(f"wheel path is linked or not regular: {label}")
        descriptor = os.open(name, flags, dir_fd=parent_fd)
        after = os.fstat(descriptor)
        if _identity(before) != _identity(after):
            os.close(descriptor)
            descriptor = -1
            raise ReleaseContractError(f"wheel changed while opening: {label}")
        return descriptor
    except ReleaseContractError:
        if descriptor >= 0:
            os.close(descriptor)
        raise
    except OSError as exc:
        if descriptor >= 0:
            os.close(descriptor)
        raise ReleaseContractError(f"cannot safely open wheel {label}: {exc}") from exc


@contextmanager
def _open_wheel(path: Path) -> Iterator[tuple[BinaryIO, str]]:
    absolute = _absolute_path(path)
    if absolute == Path(os.sep):
        raise ReleaseContractError("wheel path cannot be the filesystem root")
    descriptor = -1
    directory_fd = -1
    with _anchored_directory(absolute.parent) as (_, parent_fd):
        name = absolute.name
        try:
            metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except OSError as exc:
            raise ReleaseContractError(
                f"cannot inspect wheel input {absolute}: {exc}"
            ) from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise ReleaseContractError(f"wheel input symlink is forbidden: {absolute}")
        if stat.S_ISDIR(metadata.st_mode):
            directory_fd = _open_child_directory(parent_fd, name, absolute.as_posix())
            directory_identity = _identity(os.fstat(directory_fd))
            candidates = sorted(
                candidate
                for candidate in os.listdir(directory_fd)
                if candidate.startswith(WHEEL_DISTRIBUTION + "-")
                and candidate.endswith(".whl")
            )
            if len(candidates) != 1:
                os.close(directory_fd)
                directory_fd = -1
                raise ReleaseContractError(
                    f"expected exactly one proof-harness wheel in {absolute}, "
                    f"found {len(candidates)}"
                )
            candidate = candidates[0]
            try:
                descriptor = _open_named_regular(
                    directory_fd,
                    candidate,
                    f"{absolute}/{candidate}",
                )
            except BaseException:
                os.close(directory_fd)
                directory_fd = -1
                raise
            label = f"{absolute}/{candidate}"
            wheel_parent_fd = directory_fd
            wheel_name = candidate
        elif stat.S_ISREG(metadata.st_mode) and name.endswith(".whl"):
            descriptor = _open_named_regular(parent_fd, name, absolute.as_posix())
            label = absolute.as_posix()
            wheel_parent_fd = parent_fd
            wheel_name = name
        else:
            raise ReleaseContractError(
                f"wheel path must be a real .whl file: {absolute}"
            )
        try:
            handle = os.fdopen(descriptor, "rb", closefd=True)
            descriptor = -1
        except OSError as exc:
            if descriptor >= 0:
                os.close(descriptor)
            if directory_fd >= 0:
                os.close(directory_fd)
                directory_fd = -1
            raise ReleaseContractError(
                f"cannot create wheel stream for {label}: {exc}"
            ) from exc
        before = os.fstat(handle.fileno())
        try:
            yield handle, label
            after = os.fstat(handle.fileno())
            if _identity(before) != _identity(after):
                raise ReleaseContractError(f"wheel changed while reading: {label}")
            reopened = _open_named_regular(wheel_parent_fd, wheel_name, label)
            try:
                if _identity(os.fstat(reopened)) != _identity(before):
                    raise ReleaseContractError(
                        f"wheel pathname identity changed: {label}"
                    )
            finally:
                os.close(reopened)
            if directory_fd >= 0:
                current_directory = os.stat(
                    name, dir_fd=parent_fd, follow_symlinks=False
                )
                reopened_directory = _open_child_directory(
                    parent_fd, name, absolute.as_posix()
                )
                try:
                    if (
                        _identity(current_directory) != directory_identity
                        or _identity(os.fstat(reopened_directory)) != directory_identity
                        or _identity(os.fstat(directory_fd)) != directory_identity
                    ):
                        raise ReleaseContractError(
                            f"wheel directory pathname identity changed: {absolute}"
                        )
                finally:
                    os.close(reopened_directory)
                repeated_candidates = sorted(
                    candidate_name
                    for candidate_name in os.listdir(directory_fd)
                    if candidate_name.startswith(WHEEL_DISTRIBUTION + "-")
                    and candidate_name.endswith(".whl")
                )
                if repeated_candidates != [wheel_name]:
                    raise ReleaseContractError(
                        f"wheel directory inventory changed: {absolute}"
                    )
        finally:
            handle.close()
            if descriptor >= 0:
                os.close(descriptor)
            if directory_fd >= 0:
                os.close(directory_fd)


def _wheel_member_for_entry(path: str, data_prefix: str) -> str:
    runtime_prefix = "src/elmos_proof_harness/"
    if path.startswith(runtime_prefix):
        return "elmos_proof_harness/" + path.removeprefix(runtime_prefix)
    return data_prefix + ASSET_INSTALL_RELATIVE.as_posix() + "/" + path


def check_wheel(
    wheel: Path,
    *,
    repository_root: Path | None = None,
    expected_manifest_sha256: str | None = None,
) -> Mapping[str, Any]:
    with (
        _open_wheel(wheel) as (wheel_handle, wheel_label),
        zipfile.ZipFile(wheel_handle) as archive,
    ):
        members = _safe_zip_members(archive)
        data_prefix = WHEEL_DISTRIBUTION + ".data/data/"
        manifest_member = (
            data_prefix
            + ASSET_INSTALL_RELATIVE.as_posix()
            + "/"
            + MANIFEST_RELATIVE.as_posix()
        )
        if manifest_member not in members:
            raise ReleaseContractError("wheel does not contain the release manifest")
        if members[manifest_member].file_size > MAX_MANIFEST_BYTES:
            raise ReleaseContractError("wheel release manifest exceeds byte limit")
        manifest_payload = archive.read(members[manifest_member])
        manifest = _load_manifest(manifest_payload, manifest_member)
        _expected_manifest_digest(expected_manifest_sha256, manifest_payload)
        if repository_root is not None:
            with _anchored_directory(repository_root) as (_, repository_fd):
                repository_manifest = _read_file_at(
                    repository_fd,
                    MANIFEST_RELATIVE.as_posix(),
                    limit=MAX_MANIFEST_BYTES,
                )
            if repository_manifest != manifest_payload:
                raise ReleaseContractError(
                    "wheel manifest bytes differ from repository manifest"
                )
        expected_members = {manifest_member}
        for entry in manifest["files"]:
            if not isinstance(entry, dict) or set(entry) != {
                "bytes",
                "path",
                "role",
                "sha256",
            }:
                raise ReleaseContractError("release manifest file entry is not exact")
            member_name = _wheel_member_for_entry(entry["path"], data_prefix)
            expected_members.add(member_name)
            info = members.get(member_name)
            if info is None:
                raise ReleaseContractError(
                    f"wheel is missing release member: {member_name}"
                )
            payload = archive.read(info)
            if len(payload) != entry["bytes"] or digest(payload) != entry["sha256"]:
                raise ReleaseContractError(
                    f"wheel release member digest mismatch: {member_name}"
                )
        dist_info_prefix = WHEEL_DISTRIBUTION + ".dist-info/"
        expected_members.update(
            dist_info_prefix + name for name in WHEEL_DIST_INFO_NAMES
        )
        if set(members) != expected_members:
            missing = sorted(expected_members.difference(members))
            unexpected = sorted(set(members).difference(expected_members))
            raise ReleaseContractError(
                "wheel member set does not match the exact release inventory: "
                f"missing={missing}, unexpected={unexpected}, wheel={wheel_label}"
            )
        metadata = archive.read(members[dist_info_prefix + "METADATA"])
        if (
            b"Name: elmos-proof-driven-harness-engine\n" not in metadata
            or b"Version: 3.1.0\n" not in metadata
        ):
            raise ReleaseContractError("wheel metadata identity/version mismatch")
        return manifest


def check_installed(
    assets_root: Path | None,
    module_root: Path | None = None,
    expected_manifest_sha256: str | None = None,
) -> Mapping[str, Any]:
    if expected_manifest_sha256 is None:
        raise ReleaseContractError(
            "installed check requires --expected-manifest-sha256"
        )
    assets_root = (
        assets_root or Path(sysconfig.get_path("data")) / ASSET_INSTALL_RELATIVE
    )
    if module_root is None:
        spec = importlib.util.find_spec("elmos_proof_harness")
        if spec is None or not spec.submodule_search_locations:
            raise ReleaseContractError(
                "installed elmos_proof_harness package is unavailable"
            )
        locations = list(spec.submodule_search_locations)
        if len(locations) != 1:
            raise ReleaseContractError(
                "installed elmos_proof_harness package location is ambiguous"
            )
        module_root = Path(locations[0])
    with (
        _anchored_directory(assets_root) as (_, assets_fd),
        _anchored_directory(module_root) as (_, module_fd),
    ):
        manifest_snapshot = _read_file_snapshot_at(
            assets_fd,
            MANIFEST_RELATIVE.as_posix(),
            limit=MAX_MANIFEST_BYTES,
        )
        manifest_payload = manifest_snapshot.payload
        manifest = _load_manifest(manifest_payload, "installed release manifest")
        _expected_manifest_digest(expected_manifest_sha256, manifest_payload)
        runtime_prefix = "src/elmos_proof_harness/"
        expected_runtime: set[str] = set()
        expected_assets: set[str] = {MANIFEST_RELATIVE.as_posix()}
        runtime_snapshots: dict[str, _FileSnapshot] = {}
        asset_snapshots: dict[str, _FileSnapshot] = {}
        for entry in manifest["files"]:
            relative = entry["path"]
            if relative.startswith(runtime_prefix):
                target_relative = relative.removeprefix(runtime_prefix)
                snapshot = _read_file_snapshot_at(module_fd, target_relative)
                runtime_snapshots[target_relative] = snapshot
                expected_runtime.add(target_relative)
            else:
                target_relative = relative
                snapshot = _read_file_snapshot_at(assets_fd, target_relative)
                asset_snapshots[target_relative] = snapshot
                expected_assets.add(target_relative)
            if (
                len(snapshot.payload) != entry["bytes"]
                or digest(snapshot.payload) != entry["sha256"]
            ):
                raise ReleaseContractError(
                    f"installed release member digest mismatch: {relative}"
                )
        expected_runtime_directories = _parent_directories(expected_runtime)
        expected_asset_directories = _parent_directories(expected_assets)

        def assert_exact_trees() -> None:
            actual_runtime, actual_runtime_directories = _walk_tree_at(module_fd, ".")
            actual_assets, actual_asset_directories = _walk_tree_at(assets_fd, ".")
            if (
                actual_runtime != expected_runtime
                or actual_assets != expected_assets
                or actual_runtime_directories != expected_runtime_directories
                or actual_asset_directories != expected_asset_directories
            ):
                raise ReleaseContractError(
                    "installed release/runtime tree does not match the exact manifest inventory"
                )

        assert_exact_trees()
        for relative, original in runtime_snapshots.items():
            repeated = _read_file_snapshot_at(module_fd, relative)
            if repeated != original:
                raise ReleaseContractError(
                    f"installed runtime member changed across snapshot: {relative}"
                )
        for relative, original in asset_snapshots.items():
            repeated = _read_file_snapshot_at(assets_fd, relative)
            if repeated != original:
                raise ReleaseContractError(
                    f"installed asset member changed across snapshot: {relative}"
                )
        repeated_manifest = _read_file_snapshot_at(
            assets_fd,
            MANIFEST_RELATIVE.as_posix(),
            limit=MAX_MANIFEST_BYTES,
        )
        if repeated_manifest != manifest_snapshot:
            raise ReleaseContractError(
                "installed release manifest changed across snapshot"
            )
        assert_exact_trees()
        for relative, snapshot in runtime_snapshots.items():
            _revalidate_file_at(module_fd, relative, snapshot.identity)
        for relative, snapshot in asset_snapshots.items():
            _revalidate_file_at(assets_fd, relative, snapshot.identity)
        _revalidate_file_at(
            assets_fd,
            MANIFEST_RELATIVE.as_posix(),
            manifest_snapshot.identity,
        )
        return manifest


def _result(
    mode: str, manifest: Mapping[str, Any], manifest_payload: bytes
) -> dict[str, Any]:
    return {
        "artifact": ARTIFACT,
        "certification": "NOT_CERTIFIED",
        "commercial_distribution": "BLOCKED",
        "contract_root": manifest["contractRoot"],
        "external_evidence": "NOT_RUN",
        "files": manifest["counts"]["files"],
        "manifest_sha256": digest(manifest_payload),
        "mode": mode,
        "status": "PASS",
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(os.path.abspath(__file__)).parents[1],
        help="proof-harness engine root",
    )
    parser.add_argument("--expected-manifest-sha256")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--generate", action="store_true")
    action.add_argument("--check", action="store_true")
    action.add_argument("--check-wheel", type=Path)
    action.add_argument("--check-installed", action="store_true")
    parser.add_argument("--assets-root", type=Path)
    parser.add_argument("--module-root", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.generate:
            manifest = generate(args.root)
            mode = "generate"
            payload = json_bytes(manifest)
            _expected_manifest_digest(args.expected_manifest_sha256, payload)
        elif args.check:
            manifest = check_repository(args.root, args.expected_manifest_sha256)
            mode = "repository-check"
            payload = json_bytes(manifest)
        elif args.check_wheel is not None:
            manifest = check_wheel(
                args.check_wheel,
                repository_root=args.root,
                expected_manifest_sha256=args.expected_manifest_sha256,
            )
            mode = "wheel-check"
            payload = json_bytes(manifest)
        else:
            manifest = check_installed(
                args.assets_root,
                args.module_root,
                args.expected_manifest_sha256,
            )
            mode = "installed-check"
            payload = json_bytes(manifest)
    except (
        OSError,
        UnicodeError,
        ValueError,
        zipfile.BadZipFile,
        ReleaseContractError,
    ) as exc:
        print(
            json.dumps(
                {
                    "certification": "NOT_CERTIFIED",
                    "commercial_distribution": "BLOCKED",
                    "error": str(exc),
                    "status": "FAIL",
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(_result(mode, manifest, payload), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
