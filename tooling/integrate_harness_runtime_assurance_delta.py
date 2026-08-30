#!/usr/bin/env python3
"""Safely integrate the pinned v3.1 harness-runtime-assurance delta.

The delta ZIP is untrusted source material.  This importer independently
validates its byte identity, ZIP metadata, checksums, manifest, registry and
JSON contracts.  It never imports or executes archive scripts, the reference
implementation, Rego, SQL, Markdown instructions, or installer workflows.
Schemas, examples and an exact allowlist of declarative assets may be copied
as untrusted data.  The source SQL migration is verified but never published;
only a separately authored repository migration may become runtime authority.
Skill wrappers point at :mod:`elmos_proof_harness.delta`, the repository-owned
implementation.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import errno
import fcntl
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import unicodedata
import uuid
import zipfile
from typing import Any, Callable, Iterator, Mapping, Sequence


PACKAGE_NAME = "elmos-v3-harness-runtime-assurance-delta"
PACKAGE_VERSION = "3.1.0"
ARCHIVE_ROOT = f"{PACKAGE_NAME}-v{PACKAGE_VERSION}"
ARCHIVE_RELATIVE_PATH = Path("skills/subskills") / f"{ARCHIVE_ROOT}.zip"
ARCHIVE_SHA256 = "13ba6f089d3c367affe3e03999418029873d842e07a8c80cfaeeffb4308a7a37"
ARCHIVE_BYTES = 173_228
EXPECTED_ENTRIES = 150
EXPECTED_FILES = 150
EXPECTED_UNCOMPRESSED_BYTES = 339_731
EXPECTED_CHECKSUM_ROWS = 149
EXPECTED_PAYLOAD_FILES = 130
EXPECTED_EXTENSION_SKILLS = 13
EXPECTED_SCHEMAS = 15
EXPECTED_ADAPTER_PROFILES = 4
EXPECTED_REGO_MODULES = 5
EXPECTED_ACCEPTANCE_SCENARIOS_PER_SKILL = 8
EXPECTED_ACCEPTANCE_SCENARIO_COUNT = 104
ACCEPTANCE_CASE_SUFFIXES = (
    "A01",
    "A02",
    "A03",
    "A04",
    "A05",
    "NEG-STALE",
    "NEG-REPLAY",
    "RECOVERY",
)
_TEST_SELECTOR_PATTERN = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*){2,}")
DELTA_API_VERSION = "elmos.ai/v3delta1"
BASE_PACKAGE = "elmos-proof-driven-agentic-harness-repository-semantic-compiler"
BASE_VERSION = "3.0.0"
DELTA_ROOT = Path("docs/proof-driven-harness-v3/delta-v3.1")
ENGINE_ROOT = Path("engines/proof-driven-harness-engine")
RECEIPT_PATH = ENGINE_ROOT / "qualification/delta-v3.1/local-qualification.json"
ACCEPTANCE_BINDINGS_PATH = (
    ENGINE_ROOT / "supply-chain/delta-v3.1-acceptance-bindings.json"
)
MAX_MEMBER_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024
MAX_PATH_BYTES = 1024
MAX_COMPONENT_BYTES = 255
MAX_COMPRESSION_RATIO = 100.0
MAX_RECEIPT_BYTES = 4 * 1024 * 1024
MAX_RAW_LOG_BYTES = 4 * 1024 * 1024
QUALIFICATION_EXCLUDED = frozenset(
    {
        "qualification",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "build",
        "dist",
    }
)

EXPECTED_SKILLS: tuple[tuple[str, str, str, tuple[str, ...], str], ...] = (
    (
        "ELMOS-V3D-001",
        "elmos-tool-result-interception-commit",
        "P0",
        ("K7", "K6", "K8"),
        "P0/elmos-tool-result-interception-commit/SKILL.md",
    ),
    (
        "ELMOS-V3D-002",
        "elmos-step-finalized-execution-plan",
        "P0",
        ("K7", "K4"),
        "P0/elmos-step-finalized-execution-plan/SKILL.md",
    ),
    (
        "ELMOS-V3D-003",
        "elmos-lossless-permission-replay",
        "P0",
        ("K7", "K8"),
        "P0/elmos-lossless-permission-replay/SKILL.md",
    ),
    (
        "ELMOS-V3D-004",
        "elmos-invocation-scoped-capability-lease",
        "P0",
        ("K7",),
        "P0/elmos-invocation-scoped-capability-lease/SKILL.md",
    ),
    (
        "ELMOS-V3D-005",
        "elmos-host-minted-security-context",
        "P0",
        ("K7", "K8"),
        "P0/elmos-host-minted-security-context/SKILL.md",
    ),
    (
        "ELMOS-V3D-006",
        "elmos-environment-attachment-authority",
        "P0",
        ("K7",),
        "P0/elmos-environment-attachment-authority/SKILL.md",
    ),
    (
        "ELMOS-V3D-007",
        "elmos-executor-generation-fencing",
        "P0",
        ("K7",),
        "P0/elmos-executor-generation-fencing/SKILL.md",
    ),
    (
        "ELMOS-V3D-008",
        "elmos-workspace-ownership-lease",
        "P0",
        ("K7", "K5"),
        "P0/elmos-workspace-ownership-lease/SKILL.md",
    ),
    (
        "ELMOS-V3D-009",
        "elmos-harness-transport-version-negotiation",
        "P0",
        ("K7",),
        "P0/elmos-harness-transport-version-negotiation/SKILL.md",
    ),
    (
        "ELMOS-V3D-010",
        "elmos-skill-trust-domain-provenance",
        "P0",
        ("K7", "K8"),
        "P0/elmos-skill-trust-domain-provenance/SKILL.md",
    ),
    (
        "ELMOS-V3D-011",
        "elmos-registered-durable-plugin-events",
        "P1",
        ("K7", "K8"),
        "P1/elmos-registered-durable-plugin-events/SKILL.md",
    ),
    (
        "ELMOS-V3D-012",
        "elmos-typed-external-ingress",
        "P1",
        ("K7", "K1"),
        "P1/elmos-typed-external-ingress/SKILL.md",
    ),
    (
        "ELMOS-V3D-013",
        "elmos-subagent-model-execution-spec",
        "P1",
        ("K4", "K7"),
        "P1/elmos-subagent-model-execution-spec/SKILL.md",
    ),
)
EXPECTED_SKILL_NAMES = frozenset(row[1] for row in EXPECTED_SKILLS)
EXPECTED_SCHEMA_FILES = (
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

# These declarative members are copied byte-for-byte from the one audited
# in-memory snapshot.  They remain untrusted data and are never imported,
# evaluated, executed, or treated as policy authority by this importer.
SOURCE_ASSET_TARGETS: Mapping[str, Path] = {
    "payload/api/delta-v3.1/asyncapi-overlay.yaml": ENGINE_ROOT
    / "api/delta-v3.1/asyncapi-overlay.yaml",
    "payload/api/delta-v3.1/elmos_v3_delta.proto": ENGINE_ROOT
    / "api/delta-v3.1/elmos_v3_delta.proto",
    "payload/api/delta-v3.1/openapi-overlay.yaml": ENGINE_ROOT
    / "api/delta-v3.1/openapi-overlay.yaml",
    "payload/harness/adapters/delta-v3.1/codex-main-2026-08-28.yaml": ENGINE_ROOT
    / "adapters/delta-v3.1/codex-main-2026-08-28.yaml",
    "payload/harness/adapters/delta-v3.1/codex-stable-0.150.1.yaml": ENGINE_ROOT
    / "adapters/delta-v3.1/codex-stable-0.150.1.yaml",
    "payload/harness/adapters/delta-v3.1/deepseek-harness-0.1.1-rc.2.yaml": ENGINE_ROOT
    / "adapters/delta-v3.1/deepseek-harness-0.1.1-rc.2.yaml",
    "payload/harness/adapters/delta-v3.1/deepseek-harness-0.1.2-alpha.1.yaml": ENGINE_ROOT
    / "adapters/delta-v3.1/deepseek-harness-0.1.2-alpha.1.yaml",
    "payload/harness/adapters/delta-v3.1/upstream-type-map.yaml": ENGINE_ROOT
    / "adapters/delta-v3.1/upstream-type-map.yaml",
    "payload/observability/delta-v3.1/alerts.yaml": ENGINE_ROOT
    / "observability/delta-v3.1/alerts.yaml",
    "payload/observability/delta-v3.1/metrics.yaml": ENGINE_ROOT
    / "observability/delta-v3.1/metrics.yaml",
    "payload/policy/delta-rego/capability_authority.rego": ENGINE_ROOT
    / "policies/delta-v3.1/capability_authority.rego",
    "payload/policy/delta-rego/event_ingress.rego": ENGINE_ROOT
    / "policies/delta-v3.1/event_ingress.rego",
    "payload/policy/delta-rego/permission_replay.rego": ENGINE_ROOT
    / "policies/delta-v3.1/permission_replay.rego",
    "payload/policy/delta-rego/result_commit.rego": ENGINE_ROOT
    / "policies/delta-v3.1/result_commit.rego",
    "payload/policy/delta-rego/skill_trust.rego": ENGINE_ROOT
    / "policies/delta-v3.1/skill_trust.rego",
    "payload/verification/delta-gates.yaml": ENGINE_ROOT
    / "verification/delta-v3.1/delta-gates.yaml",
    "payload/verification/matrices/capability-security.yaml": ENGINE_ROOT
    / "verification/delta-v3.1/matrices/capability-security.yaml",
    "payload/verification/matrices/ownership-fencing.yaml": ENGINE_ROOT
    / "verification/delta-v3.1/matrices/ownership-fencing.yaml",
    "payload/verification/matrices/permission-replay.yaml": ENGINE_ROOT
    / "verification/delta-v3.1/matrices/permission-replay.yaml",
    "payload/verification/matrices/protocol-events-ingress.yaml": ENGINE_ROOT
    / "verification/delta-v3.1/matrices/protocol-events-ingress.yaml",
    "payload/verification/matrices/tool-result-lifecycle.yaml": ENGINE_ROOT
    / "verification/delta-v3.1/matrices/tool-result-lifecycle.yaml",
}
SOURCE_MIGRATION = (
    "payload/database/delta-migrations/V304__harness_runtime_assurance_delta.sql"
)

ENGINE_DELTA_TEST_PATTERN = "test_delta_*.py"
REQUIRED_ENGINE_DELTA_TESTS = (
    ENGINE_ROOT / "tests/test_delta_contract_closure.py",
    ENGINE_ROOT / "tests/test_delta_migration.py",
    ENGINE_ROOT / "tests/test_delta_qualification.py",
    ENGINE_ROOT / "tests/test_delta_skills.py",
)
# These are fixed reserved entrypoints.  If either is present it is part of the
# exact qualification corpus; an arbitrary extra test_delta_*.py is rejected
# instead of being allowed to dilute the required assurance suite.
OPTIONAL_ENGINE_DELTA_TESTS = (
    ENGINE_ROOT / "tests/test_delta_control_plane.py",
    ENGINE_ROOT / "tests/test_delta_storage.py",
)
STATIC_QUALIFICATION_INPUTS = (
    Path("engines/proof-driven-harness-engine/tools/qualify_delta.py"),
    Path("engines/proof-driven-harness-engine/tools/run_structured_unittest.py"),
    Path("tooling/integrate_harness_runtime_assurance_delta.py"),
    ACCEPTANCE_BINDINGS_PATH,
    Path("tests/proof-driven-harness-v3/test_delta_integration.py"),
)
QUALIFICATION_INPUTS = (
    *STATIC_QUALIFICATION_INPUTS[:3],
    STATIC_QUALIFICATION_INPUTS[3],
    *REQUIRED_ENGINE_DELTA_TESTS,
    STATIC_QUALIFICATION_INPUTS[4],
)


class IntegrationError(RuntimeError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise IntegrationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _strict_json(data: bytes, source: str) -> Any:
    def reject(value: str) -> None:
        raise ValueError(f"non-finite JSON number {value}")

    try:
        return json.loads(
            data.decode("utf-8", "strict"),
            parse_constant=reject,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise IntegrationError(f"invalid JSON in {source}: {exc}") from exc


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n"
    ).encode()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _identity(item: os.stat_result) -> tuple[int, int, int, int, int]:
    return (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns)


@contextmanager
def _stable_snapshot(
    path: Path,
    *,
    expected_size: int | None = None,
    limit: int = MAX_MEMBER_BYTES,
) -> Iterator[bytes]:
    absolute = Path(os.path.abspath(os.fspath(path)))
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(absolute, flags)
    except OSError as exc:
        raise IntegrationError(f"cannot open input safely: {absolute}: {exc}") from exc
    original: os.stat_result | None = None
    try:
        before = os.fstat(fd)
        original = before
        if not stat.S_ISREG(before.st_mode):
            raise IntegrationError(f"input is not a regular file: {absolute}")
        if expected_size is not None and before.st_size != expected_size:
            raise IntegrationError(
                f"input size mismatch: expected {expected_size}, got {before.st_size}"
            )
        if before.st_size > limit:
            raise IntegrationError(f"input exceeds bounded read limit: {absolute}")
        chunks: list[bytes] = []
        total = 0
        while True:
            part = os.read(fd, min(1024 * 1024, limit + 1 - total))
            if not part:
                break
            total += len(part)
            if total > limit:
                raise IntegrationError(f"input exceeded bounded read limit: {absolute}")
            chunks.append(part)
        after = os.fstat(fd)
        if _identity(before) != _identity(after) or total != before.st_size:
            raise IntegrationError(f"input changed while reading: {absolute}")
        yield b"".join(chunks)
    finally:
        try:
            if original is not None:
                pathname = os.stat(absolute, follow_symlinks=False)
                if not stat.S_ISREG(pathname.st_mode) or _identity(
                    pathname
                ) != _identity(original):
                    raise IntegrationError(
                        f"input pathname identity changed during audit: {absolute}"
                    )
        except FileNotFoundError as exc:
            raise IntegrationError(
                f"input pathname disappeared during audit: {absolute}"
            ) from exc
        finally:
            os.close(fd)


def _read_stable(
    path: Path,
    *,
    expected_size: int | None = None,
    limit: int = MAX_MEMBER_BYTES,
) -> bytes:
    with _stable_snapshot(path, expected_size=expected_size, limit=limit) as payload:
        return payload


def _relative_name(name: str) -> str:
    prefix = ARCHIVE_ROOT + "/"
    if not name.startswith(prefix):
        raise IntegrationError(f"member outside pinned archive root: {name!r}")
    value = name[len(prefix) :]
    if not value:
        raise IntegrationError("archive root entry is not a file")
    return value


def _validate_infos(infos: Sequence[zipfile.ZipInfo]) -> dict[str, zipfile.ZipInfo]:
    if len(infos) != EXPECTED_ENTRIES:
        raise IntegrationError(
            f"entry count mismatch: expected {EXPECTED_ENTRIES}, got {len(infos)}"
        )
    files: dict[str, zipfile.ZipInfo] = {}
    folded: set[str] = set()
    total = 0
    for info in infos:
        raw = info.filename
        if (
            not raw
            or "\x00" in raw
            or "\\" in raw
            or raw.endswith("/")
            or len(raw.encode("utf-8")) > MAX_PATH_BYTES
        ):
            raise IntegrationError(f"unsafe ZIP member name: {raw!r}")
        relative = _relative_name(raw)
        if unicodedata.normalize("NFC", raw) != raw:
            raise IntegrationError(f"non-NFC ZIP member name: {raw!r}")
        pure = PurePosixPath(relative)
        if (
            pure.is_absolute()
            or re.match(r"^[A-Za-z]:", pure.parts[0])
            or any(
                not part
                or part in {".", ".."}
                or len(part.encode("utf-8")) > MAX_COMPONENT_BYTES
                for part in pure.parts
            )
        ):
            raise IntegrationError(f"unsafe ZIP path: {raw!r}")
        key = unicodedata.normalize("NFKC", relative).casefold()
        if key in folded:
            raise IntegrationError(f"ZIP path collision: {raw!r}")
        folded.add(key)
        if info.flag_bits & ((1 << 0) | (1 << 6)):
            raise IntegrationError(f"encrypted ZIP member: {raw!r}")
        if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
            raise IntegrationError(f"unsupported ZIP compression: {raw!r}")
        mode = (info.external_attr >> 16) & 0xFFFF
        if stat.S_IFMT(mode) not in {0, stat.S_IFREG}:
            raise IntegrationError(f"special ZIP member: {raw!r}")
        if info.file_size > MAX_MEMBER_BYTES:
            raise IntegrationError(f"member too large: {raw!r}")
        ratio = info.file_size / max(1, info.compress_size)
        if ratio > MAX_COMPRESSION_RATIO:
            raise IntegrationError(f"member compression ratio too high: {raw!r}")
        total += info.file_size
        files[relative] = info
    if (
        len(files) != EXPECTED_FILES
        or total != EXPECTED_UNCOMPRESSED_BYTES
        or total > MAX_TOTAL_BYTES
    ):
        raise IntegrationError(
            f"member totals drifted: files={len(files)} bytes={total}"
        )
    return files


def _member_bytes(
    archive: zipfile.ZipFile,
    files: Mapping[str, zipfile.ZipInfo],
    name: str,
    *,
    limit: int = MAX_MEMBER_BYTES,
) -> bytes:
    info = files.get(name)
    if info is None:
        raise IntegrationError(f"required archive member missing: {name}")
    if info.file_size > limit:
        raise IntegrationError(f"member exceeds bounded read limit: {name}")
    try:
        data = archive.read(info)
    except (RuntimeError, zipfile.BadZipFile) as exc:
        raise IntegrationError(f"cannot read ZIP member {name}: {exc}") from exc
    if len(data) != info.file_size:
        raise IntegrationError(f"short ZIP member read: {name}")
    return data


def _parse_checksums(data: bytes) -> dict[str, str]:
    try:
        lines = data.decode("utf-8", "strict").splitlines()
    except UnicodeDecodeError as exc:
        raise IntegrationError("FILES.sha256 is not strict UTF-8") from exc
    rows: dict[str, str] = {}
    folded: set[str] = set()
    for line_number, line in enumerate(lines, 1):
        match = re.fullmatch(r"([0-9a-f]{64})  ([^\r\n]+)", line)
        if match is None:
            raise IntegrationError(f"malformed FILES.sha256 row {line_number}")
        digest, name = match.groups()
        pure = PurePosixPath(name)
        if (
            pure.is_absolute()
            or "\\" in name
            or any(part in {"", ".", ".."} for part in pure.parts)
        ):
            raise IntegrationError(f"unsafe checksum path: {name!r}")
        key = unicodedata.normalize("NFKC", name).casefold()
        if key in folded:
            raise IntegrationError(f"duplicate checksum path: {name!r}")
        folded.add(key)
        rows[name] = digest
    if len(rows) != EXPECTED_CHECKSUM_ROWS:
        raise IntegrationError(
            f"checksum row mismatch: expected {EXPECTED_CHECKSUM_ROWS}, got {len(rows)}"
        )
    return rows


def _validate_type(value: Any, expected: str) -> bool:
    return {
        "object": isinstance(value, Mapping),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(expected, False)


def _validate_schema(
    value: Any,
    schema: Mapping[str, Any],
    path: str = "$",
    *,
    root: Mapping[str, Any] | None = None,
) -> None:
    root = root or schema
    if "oneOf" in schema:
        matches = 0
        for option in schema["oneOf"]:
            try:
                _validate_schema(value, option, path, root=root)
                matches += 1
            except IntegrationError:
                pass
        if matches != 1:
            raise IntegrationError(f"{path} does not match oneOf")
        return
    if "enum" in schema and value not in schema["enum"]:
        raise IntegrationError(f"{path} is not an allowed enum value")
    expected_type = schema.get("type")
    if expected_type is not None:
        types = expected_type if isinstance(expected_type, list) else [expected_type]
        if not any(_validate_type(value, item) for item in types):
            raise IntegrationError(f"{path} has wrong type")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            raise IntegrationError(f"{path} is shorter than minLength")
        if schema.get("format") == "date-time":
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise IntegrationError(f"{path} is not date-time") from exc
            if parsed.tzinfo is None:
                raise IntegrationError(f"{path} date-time omits a timezone")
    if (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value < schema.get("minimum", value)
    ):
        raise IntegrationError(f"{path} is below minimum")
    if isinstance(value, Mapping):
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                raise IntegrationError(f"{path} missing required property {key}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            unknown = set(value) - set(properties)
            if unknown:
                raise IntegrationError(
                    f"{path} has unknown properties: {sorted(unknown)}"
                )
        for key, child in properties.items():
            if key in value:
                _validate_schema(value[key], child, f"{path}.{key}", root=root)
    if isinstance(value, list):
        items = schema.get("items")
        if isinstance(items, Mapping):
            for index, item in enumerate(value):
                _validate_schema(item, items, f"{path}[{index}]", root=root)


def _validate_registry(
    manifest: Mapping[str, Any],
    registry: Mapping[str, Any],
    files: Mapping[str, zipfile.ZipInfo],
) -> None:
    if (
        manifest.get("apiVersion") != DELTA_API_VERSION
        or manifest.get("kind") != "KernelExtensionDeltaPackage"
    ):
        raise IntegrationError("delta manifest identity drifted")
    metadata = manifest.get("metadata")
    spec = manifest.get("spec")
    if not isinstance(metadata, Mapping) or not isinstance(spec, Mapping):
        raise IntegrationError("delta manifest shape is invalid")
    if (
        metadata.get("version") != PACKAGE_VERSION
        or metadata.get("packageId") != f"{ARCHIVE_ROOT}"
        or metadata.get("incrementalOnly") is not True
    ):
        raise IntegrationError("delta manifest version/package identity drifted")
    base = spec.get("base", {})
    scope = spec.get("scope", {})
    if (
        base.get("name") != BASE_PACKAGE
        or base.get("exactVersion") != BASE_VERSION
        or base.get("compositeVersionAfterInstall") != PACKAGE_VERSION
    ):
        raise IntegrationError("delta base contract is not exact v3.0.0")
    if (
        scope.get("newKernels") != 0
        or scope.get("newRoutableBusinessLines") != 0
        or scope.get("kernelExtensionSkills") != EXPECTED_EXTENSION_SKILLS
        or scope.get("preservesRoutableSkillCount") != 16
    ):
        raise IntegrationError("delta scope count drifted")
    if (
        not isinstance(registry, Mapping)
        or registry.get("version") != PACKAGE_VERSION
        or registry.get("routable") is not False
    ):
        raise IntegrationError("delta registry identity drifted")
    entries = registry.get("entries")
    if not isinstance(entries, list) or len(entries) != EXPECTED_EXTENSION_SKILLS:
        raise IntegrationError("delta registry entry count drifted")
    expected_rows = {row[0]: row for row in EXPECTED_SKILLS}
    actual_ids: set[str] = set()
    actual_names: set[str] = set()
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise IntegrationError("delta registry entry is not an object")
        entry_id = entry.get("id")
        name = entry.get("name")
        path = entry.get("path")
        if (
            not isinstance(entry_id, str)
            or entry_id in actual_ids
            or entry_id not in expected_rows
        ):
            raise IntegrationError("delta registry IDs are not exact")
        if (
            not isinstance(name, str)
            or name in actual_names
            or not name.startswith("elmos-")
        ):
            raise IntegrationError("delta registry names are not exact")
        owners = entry.get("ownerKernels")
        if not isinstance(owners, list) or not owners:
            raise IntegrationError(f"delta registry owner drifted: {name}")
        (
            expected_id,
            expected_name,
            expected_priority,
            expected_owners,
            expected_path,
        ) = expected_rows[entry_id]
        if (
            entry_id != expected_id
            or name != expected_name
            or entry.get("version") != PACKAGE_VERSION
            or entry.get("routable") is not False
            or entry.get("priority") != expected_priority
            or tuple(owners) != expected_owners
            or path != expected_path
            or set(entry)
            != {"id", "name", "version", "priority", "routable", "ownerKernels", "path"}
        ):
            raise IntegrationError(f"delta registry entry flags drifted: {name}")
        if any(owner not in {f"K{i}" for i in range(1, 9)} for owner in owners):
            raise IntegrationError(f"delta registry owner drifted: {name}")
        if (
            not isinstance(path, str)
            or f"payload/skills/extensions/{path}" not in files
        ):
            raise IntegrationError(f"delta registry source path missing: {name}")
        actual_ids.add(entry_id)
        actual_names.add(name)
    if actual_ids != set(expected_rows) or actual_names != EXPECTED_SKILL_NAMES:
        raise IntegrationError("delta registry ID set drifted")


@dataclass(frozen=True)
class ArchiveAudit:
    archive_sha256: str
    archive_bytes: int
    member_hashes: Mapping[str, str]
    member_sizes: Mapping[str, int]
    payload_hashes: Mapping[str, str]
    manifest: Mapping[str, Any]
    registry: Mapping[str, Any]
    schemas: Mapping[str, Any]
    examples: Mapping[str, Any]
    source_assets: Mapping[str, bytes]
    acceptance_sources: Mapping[str, bytes]
    source_migration_sha256: str

    @property
    def extension_count(self) -> int:
        return len(self.registry["entries"])

    def summary(
        self, *, implementation_status: str = "DECLARED_RUNTIME_UNQUALIFIED"
    ) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "package": f"{PACKAGE_NAME}@{PACKAGE_VERSION}",
            "archive": {
                "sha256": self.archive_sha256,
                "bytes": self.archive_bytes,
                "entries": EXPECTED_ENTRIES,
                "files": EXPECTED_FILES,
                "uncompressed_bytes": EXPECTED_UNCOMPRESSED_BYTES,
                "checksum_rows": EXPECTED_CHECKSUM_ROWS,
            },
            "counts": {
                "extensionSkills": self.extension_count,
                "P0": sum(
                    entry["priority"] == "P0" for entry in self.registry["entries"]
                ),
                "P1": sum(
                    entry["priority"] == "P1" for entry in self.registry["entries"]
                ),
                "schemas": len(self.schemas),
                "payloadFiles": len(self.payload_hashes),
                "adapterProfiles": EXPECTED_ADAPTER_PROFILES,
                "regoModules": EXPECTED_REGO_MODULES,
                "databaseMigrations": 1,
            },
            "security": {
                "archiveContentExecuted": False,
                "archiveExecutableContentMaterializedAsAuthority": False,
                "archiveInstructionContentMaterialized": False,
                "referenceImplementationMaterialized": False,
                "declarativeSourceAssetsMaterializedAsUntrustedData": len(
                    self.source_assets
                ),
                "sourceMigrationValidatedButNotMaterialized": True,
                "checksumsVerified": EXPECTED_CHECKSUM_ROWS,
                "schemasValidated": len(self.schemas),
            },
            "implementation_status": implementation_status,
            "external_runtime_status": "NOT_RUN",
            "certification_status": "NOT_CERTIFIED",
        }


def audit_archive(path: Path) -> ArchiveAudit:
    with _stable_snapshot(
        path,
        expected_size=ARCHIVE_BYTES,
        limit=ARCHIVE_BYTES,
    ) as snapshot:
        archive_digest = _sha256(snapshot)
        if archive_digest != ARCHIVE_SHA256:
            raise IntegrationError(
                f"archive SHA-256 mismatch: expected {ARCHIVE_SHA256}, got {archive_digest}"
            )
        try:
            archive = zipfile.ZipFile(io.BytesIO(snapshot), "r")
        except zipfile.BadZipFile as exc:
            raise IntegrationError(f"invalid ZIP: {exc}") from exc
        with archive:
            if archive.comment:
                raise IntegrationError("ZIP comments are forbidden")
            files = _validate_infos(archive.infolist())
            checksums = _parse_checksums(_member_bytes(archive, files, "FILES.sha256"))
            if set(checksums) != set(files) - {"FILES.sha256"}:
                raise IntegrationError(
                    "FILES.sha256 does not cover exactly all non-manifest members"
                )
            member_hashes: dict[str, str] = {}
            member_sizes: dict[str, int] = {}
            member_payloads: dict[str, bytes] = {}
            acceptance_payloads: dict[str, bytes] = {}
            for name in files:
                data = _member_bytes(archive, files, name)
                member_hashes[name] = _sha256(data)
                member_sizes[name] = len(data)
                if (
                    name != "FILES.sha256"
                    and checksums.get(name) != member_hashes[name]
                ):
                    raise IntegrationError(f"member checksum mismatch: {name}")
                if name in SOURCE_ASSET_TARGETS:
                    member_payloads[name] = data
                if name.startswith("payload/skills/extensions/") and name.endswith(
                    "/acceptance.yaml"
                ):
                    acceptance_payloads[name] = data
            if set(member_payloads) != set(SOURCE_ASSET_TARGETS):
                raise IntegrationError("declarative source asset inventory drifted")
            if len(acceptance_payloads) != EXPECTED_EXTENSION_SKILLS:
                raise IntegrationError("acceptance source inventory drifted")

            payload_obj = _strict_json(
                _member_bytes(archive, files, "PAYLOAD_HASHES.json"),
                "PAYLOAD_HASHES.json",
            )
            if (
                not isinstance(payload_obj, Mapping)
                or len(payload_obj) != EXPECTED_PAYLOAD_FILES
            ):
                raise IntegrationError("PAYLOAD_HASHES payload count drifted")
            payload_hashes: dict[str, str] = {}
            for key, value in payload_obj.items():
                if not isinstance(key, str) or not isinstance(value, str):
                    raise IntegrationError("PAYLOAD_HASHES rows must be strings")
                pure = PurePosixPath(key)
                if (
                    pure.is_absolute()
                    or "\\" in key
                    or any(part in {"", ".", ".."} for part in pure.parts)
                    or re.fullmatch(r"[0-9a-f]{64}", value) is None
                ):
                    raise IntegrationError(f"unsafe payload hash row: {key!r}")
                payload_hashes[key] = value
            expected_payload_names = {
                name.removeprefix("payload/")
                for name in files
                if name.startswith("payload/")
            }
            if set(payload_hashes) != expected_payload_names:
                raise IntegrationError(
                    "PAYLOAD_HASHES does not cover the exact payload"
                )
            for name, claimed in payload_hashes.items():
                archive_name = "payload/" + name
                if claimed != member_hashes[archive_name]:
                    raise IntegrationError(f"payload hash mismatch: {name}")

            manifest = _strict_json(
                _member_bytes(archive, files, "DELTA_MANIFEST.json"),
                "DELTA_MANIFEST.json",
            )
            registry = _strict_json(
                _member_bytes(
                    archive,
                    files,
                    "payload/skills/extensions/registry.v3.1.json",
                ),
                "registry.v3.1.json",
            )
            if not isinstance(manifest, Mapping) or not isinstance(registry, Mapping):
                raise IntegrationError("manifest and registry must be JSON objects")
            _validate_registry(manifest, registry, files)
            schemas: dict[str, Any] = {}
            examples: dict[str, Any] = {}
            for name in files:
                if name.startswith(
                    "payload/contracts/schemas/delta-v3.1/"
                ) and name.endswith(".schema.json"):
                    schema = _strict_json(_member_bytes(archive, files, name), name)
                    if (
                        not isinstance(schema, Mapping)
                        or schema.get("$schema")
                        != "https://json-schema.org/draft/2020-12/schema"
                    ):
                        raise IntegrationError(f"schema draft drifted: {name}")
                    schemas[
                        name.removeprefix("payload/contracts/schemas/delta-v3.1/")
                    ] = schema
                if name.startswith(
                    "payload/contracts/examples/delta-v3.1/"
                ) and name.endswith(".example.json"):
                    examples[
                        name.removeprefix("payload/contracts/examples/delta-v3.1/")
                    ] = _strict_json(_member_bytes(archive, files, name), name)
            if len(schemas) != EXPECTED_SCHEMAS or len(examples) != EXPECTED_SCHEMAS:
                raise IntegrationError("schema/example count drifted")
            for filename, example in examples.items():
                schema_name = filename.removesuffix(".example.json") + ".schema.json"
                schema = schemas.get(schema_name)
                if schema is None:
                    raise IntegrationError(
                        f"example has no matching schema: {filename}"
                    )
                _validate_schema(example, schema, filename)
            return ArchiveAudit(
                archive_digest,
                len(snapshot),
                member_hashes,
                member_sizes,
                payload_hashes,
                manifest,
                registry,
                schemas,
                examples,
                member_payloads,
                acceptance_payloads,
                member_hashes[SOURCE_MIGRATION],
            )


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _qualification_excluded(relative: PurePosixPath) -> bool:
    return (
        any(
            part in QUALIFICATION_EXCLUDED or part.endswith(".egg-info")
            for part in relative.parts
        )
        or relative.suffix == ".pyc"
    )


def _engine_inventory_at(repo_fd: int) -> list[dict[str, Any]]:
    engine_fd = _open_directory_at(repo_fd, ENGINE_ROOT)
    assert engine_fd is not None
    records: list[dict[str, Any]] = []

    def walk(directory_fd: int, prefix: PurePosixPath) -> None:
        for name in sorted(os.listdir(directory_fd)):
            relative = prefix / name
            if _qualification_excluded(relative):
                continue
            metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if stat.S_ISLNK(metadata.st_mode):
                raise IntegrationError(f"linked engine qualification input: {relative}")
            if stat.S_ISDIR(metadata.st_mode):
                child = os.open(name, _directory_flags(), dir_fd=directory_fd)
                try:
                    opened = os.fstat(child)
                    if (opened.st_dev, opened.st_ino) != (
                        metadata.st_dev,
                        metadata.st_ino,
                    ):
                        raise IntegrationError(
                            f"engine directory changed while opening: {relative}"
                        )
                    walk(child, relative)
                finally:
                    os.close(child)
                continue
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_size > MAX_MEMBER_BYTES
            ):
                raise IntegrationError(f"unsafe engine qualification input: {relative}")
            descriptor = os.open(
                name,
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=directory_fd,
            )
            try:
                before = os.fstat(descriptor)
                chunks: list[bytes] = []
                total = 0
                while True:
                    chunk = os.read(
                        descriptor,
                        min(1024 * 1024, MAX_MEMBER_BYTES + 1 - total),
                    )
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_MEMBER_BYTES:
                        raise IntegrationError(
                            f"engine qualification input exceeds limit: {relative}"
                        )
                    chunks.append(chunk)
                after = os.fstat(descriptor)
                payload = b"".join(chunks)
                if (
                    _identity(before) != _identity(after)
                    or len(payload) != before.st_size
                    or (metadata.st_dev, metadata.st_ino, metadata.st_size)
                    != (before.st_dev, before.st_ino, before.st_size)
                ):
                    raise IntegrationError(
                        f"engine qualification input changed: {relative}"
                    )
            finally:
                os.close(descriptor)
            records.append(
                {
                    "path": relative.as_posix(),
                    "bytes": len(payload),
                    "sha256": "sha256:" + _sha256(payload),
                }
            )

    try:
        walk(engine_fd, PurePosixPath())
    finally:
        os.close(engine_fd)
    if not records or not any(
        row["path"] == "src/elmos_proof_harness/delta.py" for row in records
    ):
        raise IntegrationError(
            "delta runtime is absent from engine qualification inventory"
        )
    return records


def _qualification_inputs_for_inventory(
    inventory: Sequence[Mapping[str, Any]],
) -> tuple[Path, ...]:
    discovered = {
        ENGINE_ROOT / str(row.get("path"))
        for row in inventory
        if PurePosixPath(str(row.get("path"))).parent == PurePosixPath("tests")
        and PurePosixPath(str(row.get("path"))).match(ENGINE_DELTA_TEST_PATTERN)
    }
    required = set(REQUIRED_ENGINE_DELTA_TESTS)
    allowed = required | set(OPTIONAL_ENGINE_DELTA_TESTS)
    missing = required - discovered
    unexpected = discovered - allowed
    if missing or unexpected:
        raise IntegrationError(
            "delta qualification test inventory drifted: "
            f"missing={sorted(map(str, missing))} "
            f"unexpected={sorted(map(str, unexpected))}"
        )
    engine_tests = tuple(sorted(discovered))
    return (
        *STATIC_QUALIFICATION_INPUTS[:3],
        STATIC_QUALIFICATION_INPUTS[3],
        *engine_tests,
        STATIC_QUALIFICATION_INPUTS[4],
    )


_TEST_TOTAL_KEYS = (
    "selected",
    "passed",
    "failed",
    "errors",
    "skipped",
    "expected_failures",
    "unexpected_successes",
)


def _validated_test_totals(value: Any, *, minimum: int = 1) -> dict[str, int]:
    if not isinstance(value, Mapping) or set(value) != set(_TEST_TOTAL_KEYS):
        raise IntegrationError("qualification test totals are not exact")
    totals: dict[str, int] = {}
    for key in _TEST_TOTAL_KEYS:
        item = value[key]
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise IntegrationError(f"qualification test total is invalid: {key}")
        totals[key] = item
    if (
        totals["selected"] < minimum
        or totals["selected"] != totals["passed"]
        or any(
            totals[key] != 0
            for key in (
                "failed",
                "errors",
                "skipped",
                "expected_failures",
                "unexpected_successes",
            )
        )
    ):
        raise IntegrationError("qualification contains non-passing test outcomes")
    return totals


def _validate_raw_envelope(
    raw: Any, name: str, argv_tail: Sequence[str]
) -> Mapping[str, Any]:
    if not isinstance(raw, Mapping):
        raise IntegrationError(f"raw qualification log is not an object: {name}")
    required = {
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
    }
    argv = raw.get("argv")
    wall = raw.get("wall_clock_milliseconds")
    if (
        set(raw) != required
        or raw.get("schema_version") != "1.0.0"
        or raw.get("name") != name
        or raw.get("cwd") != "."
        or raw.get("returncode") != 0
        or raw.get("timed_out") is not False
        or isinstance(wall, bool)
        or not isinstance(wall, int)
        or wall < 0
        or not isinstance(argv, list)
        or len(argv) != len(argv_tail) + 1
        or not isinstance(argv[0], str)
        or not argv[0]
        or argv[1:] != list(argv_tail)
        or not isinstance(raw.get("stdout"), str)
        or not isinstance(raw.get("stderr"), str)
    ):
        raise IntegrationError(f"raw qualification envelope drifted: {name}")
    environment = raw.get("execution_environment")
    if (
        not isinstance(environment, Mapping)
        or environment.get("network") != "LOOPBACK_PROXY_DENY"
        or environment.get("external_evidence") != "NOT_RUN"
        or environment.get("independent_verification") != "NOT_RUN"
        or environment.get("certification") != "NOT_CERTIFIED"
        or not isinstance(environment.get("python"), Mapping)
        or not isinstance(environment.get("os"), Mapping)
    ):
        raise IntegrationError(f"raw qualification evidence boundary drifted: {name}")
    return raw


def _acceptance_source_scenarios(
    payload: bytes,
    *,
    skill_id: str,
    priority: str,
) -> list[tuple[str, str]]:
    """Read only scenario identities from one inert source acceptance document."""

    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise IntegrationError("acceptance source is not canonical UTF-8") from exc
    if "\x00" in text or "\r" in text:
        raise IntegrationError("acceptance source has non-canonical line content")
    scenarios: list[tuple[str, str]] = []
    current: str | None = None
    for line in text.splitlines():
        identifier = re.fullmatch(
            r"\s*- id: (ELMOS-V3D-\d{3}-(?:A0[1-5]|NEG-STALE|NEG-REPLAY|RECOVERY))\s*",
            line,
        )
        if identifier is not None:
            if current is not None:
                raise IntegrationError("acceptance scenario lacks an exact priority")
            current = identifier.group(1)
            continue
        source_priority = re.fullmatch(r"\s+priority: (P0|P1)\s*", line)
        if current is not None and source_priority is not None:
            scenarios.append((current, source_priority.group(1)))
            current = None
    expected_ids = [f"{skill_id}-{suffix}" for suffix in ACCEPTANCE_CASE_SUFFIXES]
    if current is not None or [item[0] for item in scenarios] != expected_ids:
        raise IntegrationError(
            f"acceptance source scenario inventory drifted: {skill_id}"
        )
    return scenarios


def _validate_acceptance_bindings(
    payload: bytes,
    audit: ArchiveAudit,
) -> Mapping[str, Any]:
    """Independently validate static traceability against the audited ZIP bytes."""

    value = _strict_json(payload, str(ACCEPTANCE_BINDINGS_PATH))
    root_keys = {
        "schema_version",
        "kind",
        "package",
        "source_archive",
        "binding_semantics",
        "expected_skill_count",
        "expected_scenarios_per_skill",
        "expected_scenario_count",
        "skills",
    }
    expected_archive = {
        "path": ARCHIVE_RELATIVE_PATH.as_posix(),
        "sha256": "sha256:" + ARCHIVE_SHA256,
        "bytes": ARCHIVE_BYTES,
        "executed": False,
    }
    expected_semantics = {
        "classification": "STATIC_TRACEABILITY_ONLY",
        "successful_local_result_boundary": "LOCAL_EXECUTED_SELF_ATTESTED",
        "target_environment": "NOT_RUN",
        "independent_verification": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
        "static_mapping_is_execution_evidence": False,
    }
    if (
        not isinstance(value, Mapping)
        or set(value) != root_keys
        or value.get("schema_version") != "1.0.0"
        or value.get("kind")
        != "elmos.harness-runtime-assurance-delta.acceptance-bindings"
        or value.get("package") != f"{PACKAGE_NAME}@{PACKAGE_VERSION}"
        or value.get("source_archive") != expected_archive
        or value.get("binding_semantics") != expected_semantics
        or value.get("expected_skill_count") != EXPECTED_EXTENSION_SKILLS
        or value.get("expected_scenarios_per_skill")
        != EXPECTED_ACCEPTANCE_SCENARIOS_PER_SKILL
        or value.get("expected_scenario_count") != EXPECTED_ACCEPTANCE_SCENARIO_COUNT
    ):
        raise IntegrationError("delta acceptance binding header drifted")
    skills = value.get("skills")
    if not isinstance(skills, list) or len(skills) != EXPECTED_EXTENSION_SKILLS:
        raise IntegrationError("delta acceptance skill inventory drifted")

    cases: list[dict[str, Any]] = []
    observed_ids: set[str] = set()
    for raw_skill, expected_skill in zip(skills, EXPECTED_SKILLS, strict=True):
        skill_id, skill, priority, _owners, _skill_path = expected_skill
        if not isinstance(raw_skill, Mapping) or set(raw_skill) != {
            "skill",
            "priority",
            "source_acceptance",
            "cases",
        }:
            raise IntegrationError("delta acceptance skill binding is not exact")
        expected_member = f"{ARCHIVE_ROOT}/payload/skills/extensions/{priority}/{skill}/acceptance.yaml"
        source = raw_skill.get("source_acceptance")
        relative_member = expected_member.removeprefix(ARCHIVE_ROOT + "/")
        expected_source = {
            "archive_member": expected_member,
            "sha256": "sha256:" + audit.member_hashes.get(relative_member, ""),
            "bytes": audit.member_sizes.get(relative_member),
            "executed": False,
        }
        source_payload = audit.acceptance_sources.get(relative_member)
        if (
            raw_skill.get("skill") != skill
            or raw_skill.get("priority") != priority
            or not isinstance(source, Mapping)
            or set(source) != {"archive_member", "sha256", "bytes", "executed"}
            or source != expected_source
            or source_payload is None
        ):
            raise IntegrationError(f"delta acceptance source binding drifted: {skill}")
        source_scenarios = _acceptance_source_scenarios(
            source_payload,
            skill_id=skill_id,
            priority=priority,
        )
        raw_cases = raw_skill.get("cases")
        if (
            not isinstance(raw_cases, list)
            or len(raw_cases) != EXPECTED_ACCEPTANCE_SCENARIOS_PER_SKILL
        ):
            raise IntegrationError(f"delta acceptance cases are incomplete: {skill}")
        for raw_case, (acceptance_id, source_priority) in zip(
            raw_cases, source_scenarios, strict=True
        ):
            if not isinstance(raw_case, Mapping) or set(raw_case) != {
                "acceptance_id",
                "priority",
                "repository_test_selectors",
                "local_evidence_boundary",
                "target_environment",
                "certification",
            }:
                raise IntegrationError("delta acceptance case binding is not exact")
            selectors = raw_case.get("repository_test_selectors")
            if (
                raw_case.get("acceptance_id") != acceptance_id
                or acceptance_id in observed_ids
                or raw_case.get("priority") != source_priority
                or not isinstance(selectors, list)
                or not 1 <= len(selectors) <= 8
                or any(
                    not isinstance(selector, str)
                    or len(selector) > 1024
                    or _TEST_SELECTOR_PATTERN.fullmatch(selector) is None
                    for selector in selectors
                )
                or len(set(selectors)) != len(selectors)
                or raw_case.get("local_evidence_boundary")
                != "LOCAL_EXECUTED_SELF_ATTESTED"
                or raw_case.get("target_environment") != "NOT_RUN"
                or raw_case.get("certification") != "NOT_CERTIFIED"
            ):
                raise IntegrationError(
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
    if len(cases) != EXPECTED_ACCEPTANCE_SCENARIO_COUNT:
        raise IntegrationError("delta acceptance binding is not exactly 13x8")
    return {
        "path": ACCEPTANCE_BINDINGS_PATH.as_posix(),
        "sha256": "sha256:" + _sha256(payload),
        "skills": EXPECTED_EXTENSION_SKILLS,
        "scenarios_per_skill": EXPECTED_ACCEPTANCE_SCENARIOS_PER_SKILL,
        "scenarios": EXPECTED_ACCEPTANCE_SCENARIO_COUNT,
        "mapping_classification": "STATIC_TRACEABILITY_ONLY",
        "static_mapping_is_execution_evidence": False,
        "cases": cases,
    }


def _expected_acceptance_receipt(
    bindings: Mapping[str, Any],
    outcomes: Mapping[str, Mapping[str, str]],
) -> Mapping[str, Any]:
    raw_cases = bindings.get("cases")
    if (
        not isinstance(raw_cases, list)
        or len(raw_cases) != EXPECTED_ACCEPTANCE_SCENARIO_COUNT
    ):
        raise IntegrationError("validated delta acceptance cases are unavailable")
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
            outcome = outcomes.get(str(selector))
            if outcome is None:
                raise IntegrationError(
                    f"delta acceptance selector did not pass: {case['acceptance_id']}:{selector}"
                )
            evidence.append(dict(outcome))
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
        "skills": EXPECTED_EXTENSION_SKILLS,
        "scenarios_per_skill": EXPECTED_ACCEPTANCE_SCENARIOS_PER_SKILL,
        "scenarios": EXPECTED_ACCEPTANCE_SCENARIO_COUNT,
        "local_cases": {
            "passed": EXPECTED_ACCEPTANCE_SCENARIO_COUNT,
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


def _validate_acceptance_receipt(
    value: Any,
    bindings: Mapping[str, Any],
    outcomes: Mapping[str, Mapping[str, str]],
) -> None:
    if value != _expected_acceptance_receipt(bindings, outcomes):
        raise IntegrationError("delta acceptance receipt evidence drifted")


def _validate_structured_test_log(
    raw: Mapping[str, Any],
    *,
    start_directory: str,
    pattern: str,
    expected_sources: Mapping[str, str],
) -> tuple[dict[str, int], list[str], dict[str, Mapping[str, str]]]:
    if not expected_sources or any(
        not isinstance(path, str)
        or not path
        or not isinstance(digest, str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
        for path, digest in expected_sources.items()
    ):
        raise IntegrationError("structured test source inventory is invalid")
    parsed = _strict_json(raw["stdout"].encode("utf-8"), "structured test stdout")
    expected_result_keys = {
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
    }
    if (
        not isinstance(parsed, Mapping)
        or set(parsed) != expected_result_keys
        or parsed.get("schema_version") != "1.0.0"
        or parsed.get("kind") != "elmos.proof-harness.structured-unittest-results"
        or parsed.get("status") != "PASS"
        or parsed.get("discovery")
        != {"start_directory": start_directory, "pattern": pattern}
        or not isinstance(parsed.get("runner_output"), str)
        or not isinstance(parsed.get("captured_stdout"), str)
        or not isinstance(parsed.get("captured_stderr"), str)
    ):
        raise IntegrationError("structured qualification result drifted")
    totals = _validated_test_totals(parsed.get("totals"))
    boundary = parsed.get("evidence_boundary")
    if boundary != {
        "classification": "LOCAL_EXECUTED_SELF_ATTESTED",
        "external_evidence": "NOT_RUN",
        "independent_verification": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
    }:
        raise IntegrationError("structured test evidence boundary drifted")
    outcomes = parsed.get("outcomes")
    if not isinstance(outcomes, list) or len(outcomes) != totals["selected"]:
        raise IntegrationError("structured test outcome count drifted")
    selectors: list[str] = []
    selector_evidence: dict[str, Mapping[str, str]] = {}
    observed_sources: set[str] = set()
    expected_outcome_keys = {
        "selector",
        "source_path",
        "source_sha256",
        "selector_source_binding_sha256",
        "status",
        "duration_milliseconds",
    }
    for outcome in outcomes:
        if not isinstance(outcome, Mapping) or set(outcome) != expected_outcome_keys:
            raise IntegrationError("structured test outcome is not an object")
        selector = outcome.get("selector")
        source_path = outcome.get("source_path")
        source_digest = outcome.get("source_sha256")
        binding_digest = outcome.get("selector_source_binding_sha256")
        duration = outcome.get("duration_milliseconds")
        if (
            not isinstance(selector, str)
            or not selector
            or selector in selectors
            or outcome.get("status") != "PASSED"
            or not isinstance(source_path, str)
            or source_path not in expected_sources
            or source_digest != expected_sources[source_path]
            or not isinstance(binding_digest, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", binding_digest) is None
            or isinstance(duration, bool)
            or not isinstance(duration, int)
            or duration < 0
        ):
            raise IntegrationError("structured test outcome binding drifted")
        binding = {
            "selector": selector,
            "source_path": source_path,
            "source_sha256": source_digest,
        }
        if binding_digest != "sha256:" + _sha256(_canonical_bytes(binding)):
            raise IntegrationError("structured selector binding digest drifted")
        selectors.append(selector)
        selector_evidence[selector] = binding
        observed_sources.add(source_path)
    if observed_sources != set(expected_sources):
        raise IntegrationError("structured test source coverage is incomplete")
    return totals, selectors, selector_evidence


def _validate_qualification_receipt_at(
    repo_fd: int,
    audit: ArchiveAudit,
    payload: bytes,
) -> None:
    receipt = _strict_json(payload, str(RECEIPT_PATH))
    required = {
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
    }
    if (
        not isinstance(receipt, Mapping)
        or set(receipt) != required
        or receipt.get("schema_version") != "1.0.0"
        or receipt.get("kind")
        != "elmos.harness-runtime-assurance-delta.local-qualification"
        or receipt.get("package") != f"{PACKAGE_NAME}@{PACKAGE_VERSION}"
        or receipt.get("base_package_version") != BASE_VERSION
        or receipt.get("composite_version") != PACKAGE_VERSION
        or receipt.get("archive_sha256") != audit.archive_sha256
        or receipt.get("archive_bytes") != audit.archive_bytes
        or receipt.get("install_roundtrip") != "PASS"
        or receipt.get("adapter_profile_negotiation") != "PASS"
        or receipt.get("implementation_status") != "LOCAL_EXECUTED_SELF_ATTESTED"
        or receipt.get("status") != "PASS"
    ):
        raise IntegrationError("delta qualification receipt identity drifted")
    for field in (
        "postgresql17",
        "opa",
        "provider_runtime",
        "remote_executor",
        "target_environment_conformance",
        "independent_verification",
    ):
        if receipt.get(field) != "NOT_RUN":
            raise IntegrationError(f"delta qualification overclaims {field}")
    if receipt.get("certification") != "NOT_CERTIFIED":
        raise IntegrationError("delta qualification overclaims certification")

    engine = receipt.get("engine")
    inventory = _engine_inventory_at(repo_fd)
    qualification_inputs = _qualification_inputs_for_inventory(inventory)
    tree_digest = "sha256:" + _sha256(_canonical_bytes(inventory))
    if (
        not isinstance(engine, Mapping)
        or set(engine) != {"files", "tree_sha256", "inventory"}
        or engine.get("files") != len(inventory)
        or engine.get("tree_sha256") != tree_digest
        or engine.get("inventory") != inventory
    ):
        raise IntegrationError("delta qualification engine inventory drifted")

    inputs = receipt.get("inputs")
    if not isinstance(inputs, Mapping) or set(inputs) != {
        path.as_posix() for path in qualification_inputs
    }:
        raise IntegrationError("delta qualification input inventory drifted")
    input_digests: dict[str, str] = {}
    acceptance_payload: bytes | None = None
    for relative in qualification_inputs:
        loaded = _read_at(repo_fd, relative, missing_ok=False)
        assert loaded is not None
        expected_digest = "sha256:" + _sha256(loaded[0])
        expected = {
            "bytes": len(loaded[0]),
            "sha256": expected_digest,
        }
        if inputs.get(relative.as_posix()) != expected:
            raise IntegrationError(f"delta qualification input drifted: {relative}")
        input_digests[relative.as_posix()] = expected_digest
        if relative == ACCEPTANCE_BINDINGS_PATH:
            acceptance_payload = loaded[0]
    if acceptance_payload is None:
        raise IntegrationError("delta acceptance binding input is missing")
    acceptance_bindings = _validate_acceptance_bindings(acceptance_payload, audit)

    raw_logs = receipt.get("raw_logs")
    raw_specs = (
        (
            "delta-engine-tests",
            "delta-engine-tests.json",
            (
                "engines/proof-driven-harness-engine/tools/run_structured_unittest.py",
                "--repo-root",
                ".",
                "--start-directory",
                "engines/proof-driven-harness-engine/tests",
                "--pattern",
                ENGINE_DELTA_TEST_PATTERN,
            ),
        ),
        (
            "delta-importer-tests",
            "delta-importer-tests.json",
            (
                "engines/proof-driven-harness-engine/tools/run_structured_unittest.py",
                "--repo-root",
                ".",
                "--start-directory",
                "tests/proof-driven-harness-v3",
                "--pattern",
                "test_delta_integration.py",
            ),
        ),
        (
            "delta-installation-check",
            "delta-installation-check.json",
            (
                "tooling/integrate_harness_runtime_assurance_delta.py",
                "--repo-root",
                ".",
                "--check",
            ),
        ),
    )
    if not isinstance(raw_logs, list) or len(raw_logs) != len(raw_specs):
        raise IntegrationError("delta qualification raw log inventory drifted")
    test_totals: list[dict[str, int]] = []
    adapter_selectors: list[str] = []
    engine_outcomes: dict[str, Mapping[str, str]] = {}
    for row, (name, filename, argv_tail) in zip(raw_logs, raw_specs, strict=True):
        relative = (
            Path("engines/proof-driven-harness-engine/qualification/delta-v3.1/raw")
            / filename
        )
        expected_record_path = (
            Path("qualification/delta-v3.1/raw") / filename
        ).as_posix()
        if not isinstance(row, Mapping):
            raise IntegrationError("delta qualification raw log row is invalid")
        loaded = _read_at(repo_fd, relative, limit=MAX_RAW_LOG_BYTES, missing_ok=False)
        assert loaded is not None
        _assert_evidence_file_metadata(loaded[1], relative)
        if row != {
            "name": name,
            "path": expected_record_path,
            "sha256": "sha256:" + _sha256(loaded[0]),
            "returncode": 0,
        }:
            raise IntegrationError(
                f"delta qualification raw log binding drifted: {name}"
            )
        raw = _strict_json(loaded[0], str(relative))
        envelope = _validate_raw_envelope(raw, name, argv_tail)
        if name == "delta-engine-tests":
            engine_test_sources = {
                path.as_posix(): input_digests[path.as_posix()]
                for path in qualification_inputs
                if path in REQUIRED_ENGINE_DELTA_TESTS
                or path in OPTIONAL_ENGINE_DELTA_TESTS
            }
            totals, selectors, engine_outcomes = _validate_structured_test_log(
                envelope,
                start_directory="engines/proof-driven-harness-engine/tests",
                pattern=ENGINE_DELTA_TEST_PATTERN,
                expected_sources=engine_test_sources,
            )
            test_totals.append(totals)
            adapter_selectors.extend(
                selector
                for selector in selectors
                if any(
                    token in selector.lower()
                    for token in ("protocol", "adapter", "permission")
                )
            )
        elif name == "delta-importer-tests":
            totals, _selectors, _importer_outcomes = _validate_structured_test_log(
                envelope,
                start_directory="tests/proof-driven-harness-v3",
                pattern="test_delta_integration.py",
                expected_sources={
                    "tests/proof-driven-harness-v3/test_delta_integration.py": (
                        input_digests[
                            "tests/proof-driven-harness-v3/test_delta_integration.py"
                        ]
                    )
                },
            )
            test_totals.append(totals)
        else:
            result = _strict_json(
                envelope["stdout"].encode("utf-8"),
                "delta installation check stdout",
            )
            installation_archive = (
                result.get("archive") if isinstance(result, Mapping) else None
            )
            if (
                not isinstance(result, Mapping)
                or result.get("schema_version") != "1.0.0"
                or result.get("package") != f"{PACKAGE_NAME}@{PACKAGE_VERSION}"
                or not isinstance(installation_archive, Mapping)
                or installation_archive.get("sha256") != audit.archive_sha256
                or installation_archive.get("bytes") != audit.archive_bytes
                or result.get("action") != "check"
                or not isinstance(result.get("installation"), Mapping)
                or result["installation"].get("status") != "PASS"
                or result.get("implementation_status")
                not in {
                    "DECLARED_RUNTIME_UNQUALIFIED",
                    "LOCAL_EXECUTED_SELF_ATTESTED",
                }
                or result.get("external_runtime_status") != "NOT_RUN"
                or result.get("certification_status") != "NOT_CERTIFIED"
            ):
                raise IntegrationError("delta installation check evidence drifted")

    aggregate = {
        key: sum(totals[key] for totals in test_totals) for key in _TEST_TOTAL_KEYS
    }
    receipt_totals = _validated_test_totals(receipt.get("tests"), minimum=25)
    if aggregate != receipt_totals:
        raise IntegrationError("delta qualification aggregate test totals drifted")
    if len(adapter_selectors) < 3:
        raise IntegrationError("delta qualification adapter coverage is incomplete")
    _validate_acceptance_receipt(
        receipt.get("acceptance"),
        acceptance_bindings,
        engine_outcomes,
    )
    # Recompute after validating all subordinate evidence to reject concurrent
    # engine changes between the first inventory and final promotion.
    if _engine_inventory_at(repo_fd) != inventory:
        raise IntegrationError("delta engine changed during receipt validation")


def _assert_evidence_file_metadata(metadata: os.stat_result, relative: Path) -> None:
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        raise IntegrationError(f"delta qualification evidence is unsafe: {relative}")


def _receipt_status(repo_root: Path, audit: ArchiveAudit) -> str:
    try:
        with _repo_anchor(repo_root) as (absolute, repo_fd, root_identity):
            loaded = _read_at(
                repo_fd,
                RECEIPT_PATH,
                limit=MAX_RECEIPT_BYTES,
                missing_ok=True,
            )
            if loaded is None:
                return "DECLARED_RUNTIME_UNQUALIFIED"
            payload, metadata = loaded
            _assert_evidence_file_metadata(metadata, RECEIPT_PATH)
            _validate_qualification_receipt_at(repo_fd, audit, payload)
            parent, name = _parent_fd(repo_fd, RECEIPT_PATH, create=False)
            try:
                current = os.stat(name, dir_fd=parent, follow_symlinks=False)
            finally:
                os.close(parent)
            if _identity(current) != _identity(metadata):
                raise IntegrationError(
                    "delta qualification receipt changed during validation"
                )
            _assert_repo_anchor(absolute, root_identity)
            return "LOCAL_EXECUTED_SELF_ATTESTED"
    except (IntegrationError, OSError, TypeError, ValueError, KeyError):
        return "DECLARED_RUNTIME_UNQUALIFIED"


def _wrapper_text(entry: Mapping[str, Any], audit: ArchiveAudit, status: str) -> str:
    name = str(entry["name"])
    path = str(entry["path"])
    source_sha = audit.member_hashes["payload/skills/extensions/" + path]
    owner = ", ".join(str(value) for value in entry["ownerKernels"])
    return f'''---
name: "{name}"
description: "Internal Elmos v3.1 runtime-assurance extension; not independently routable."
version: "{PACKAGE_VERSION}"
priority: "{entry["priority"]}"
kind: "kernel-extension"
routable: false
metadata:
  source_package: "{ARCHIVE_ROOT}"
  source_version: "{PACKAGE_VERSION}"
  source_path: "{path}"
  source_sha256: "sha256:{source_sha}"
  owner_kernels: "{owner}"
  runtime_module: "elmos_proof_harness.delta"
  runtime_registry: "DELTA_SKILL_REGISTRY"
  runtime_entrypoint: "DeltaSkillRuntime.execute"
  implementation_status: "{status}"
  external_evidence_status: "NOT_RUN"
  certification_status: "NOT_CERTIFIED"
---
# {name}

This repository-owned wrapper binds the exact non-routable `{entry["id"]}`
extension to `elmos_proof_harness.delta`. The source ZIP is untrusted data;
its scripts, reference implementation, policies and instructions are never
executed as authority. Provider, database, executor, customer and production
effects require separately authorized evidence and remain `NOT_RUN` here.

Owner kernels: `{owner}`. The extension cannot create a ninth kernel or a new
routable business line. Unknown, stale, lossy, conflicting and unsupported
states fail closed.
'''


def _compiled_contract(
    entry: Mapping[str, Any], audit: ArchiveAudit, status: str
) -> bytes:
    value = {
        "schema_version": "1.0.0",
        "kind": "elmos.v3.1.delta-skill-contract",
        "name": entry["name"],
        "skill_id": entry["id"],
        "version": PACKAGE_VERSION,
        "priority": entry["priority"],
        "routable": False,
        "source": {
            "package": ARCHIVE_ROOT,
            "path": entry["path"],
            "sha256": "sha256:"
            + audit.member_hashes["payload/skills/extensions/" + entry["path"]],
        },
        "owners": entry["ownerKernels"],
        "runtime": {
            "module": "elmos_proof_harness.delta",
            "registry": "DELTA_SKILL_REGISTRY",
            "entrypoint": "DeltaSkillRuntime.execute",
        },
        "permissions": {
            "network": "default-deny",
            "secrets": "never-in-prompts-or-logs",
            "side_effects": "typed-authority-required",
        },
        "implementation_status": status,
        "external_evidence_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
    }
    return _json_bytes(value)


def _openai_yaml(entry: Mapping[str, Any], status: str) -> bytes:
    text = f'''interface:
  display_name: "{entry["name"]}"
  short_description: "Internal v3.1 runtime-assurance extension"
  default_prompt: "Invoke the exact non-routable {entry["id"]} handler with typed, tenant-bound input."
runtime:
  module: "elmos_proof_harness.delta"
  registry: "DELTA_SKILL_REGISTRY"
  entrypoint: "DeltaSkillRuntime.execute"
  routable: false
  implementation_status: "{status}"
security:
  network: "default-deny"
  external_effects: "not-authorized"
'''
    return text.encode()


def build_outputs(audit: ArchiveAudit, *, status: str) -> dict[Path, bytes]:
    outputs: dict[Path, bytes] = {}
    # Every byte below came from the exact snapshot retained by audit_archive;
    # this function never reopens a pathname or ZIP.  The source migration is
    # deliberately excluded: the repository-owned migration must be authored,
    # reviewed and qualified independently.
    for filename in sorted(audit.schemas):
        outputs[ENGINE_ROOT / "schemas/delta-v3.1" / filename] = _json_bytes(
            audit.schemas[filename]
        )
    for filename in sorted(audit.examples):
        outputs[ENGINE_ROOT / "examples/delta-v3.1" / filename] = _json_bytes(
            audit.examples[filename]
        )
    if set(audit.source_assets) != set(SOURCE_ASSET_TARGETS):
        raise IntegrationError("audited source asset inventory is incomplete")
    for source, target in SOURCE_ASSET_TARGETS.items():
        payload = audit.source_assets[source]
        if _sha256(payload) != audit.member_hashes[source]:
            raise IntegrationError(f"audited source asset changed in memory: {source}")
        outputs[target] = payload
    outputs[DELTA_ROOT / ".source-data/DELTA_MANIFEST.json"] = _json_bytes(
        audit.manifest
    )
    outputs[DELTA_ROOT / ".source-data/registry.v3.1.json"] = _json_bytes(
        audit.registry
    )
    outputs[DELTA_ROOT / ".source-data/PAYLOAD_HASHES.json"] = _json_bytes(
        audit.payload_hashes
    )
    boundary = {
        "schema_version": "1.0.0",
        "archive_sha256": audit.archive_sha256,
        "base_version": BASE_VERSION,
        "composite_version": PACKAGE_VERSION,
        "archive_content_executed": False,
        "instruction_content_materialized": False,
        "reference_implementation_materialized": False,
        "declarative_source_assets": {
            "classification": "UNTRUSTED_DATA_NOT_RUNTIME_AUTHORITY",
            "count": len(audit.source_assets),
            "members": [
                {
                    "source": source,
                    "target": str(SOURCE_ASSET_TARGETS[source]),
                    "sha256": "sha256:" + audit.member_hashes[source],
                }
                for source in sorted(SOURCE_ASSET_TARGETS)
            ],
        },
        "source_migration": {
            "path": SOURCE_MIGRATION,
            "sha256": "sha256:" + audit.source_migration_sha256,
            "materialized": False,
            "executed": False,
            "authority": "NONE",
        },
        "local_qualification": status,
        "external_runtime_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
    }
    outputs[DELTA_ROOT / "source-boundary.json"] = _json_bytes(boundary)
    for entry in audit.registry["entries"]:
        for root in (Path(".agents/skills"), Path("agent-skills/runtime")):
            base = root / str(entry["name"])
            outputs[base / "SKILL.md"] = _wrapper_text(entry, audit, status).encode()
            outputs[base / "compiled-contract.json"] = _compiled_contract(
                entry, audit, status
            )
            outputs[base / "agents/openai.yaml"] = _openai_yaml(entry, status)
    _validate_outputs(outputs)
    return outputs


def _relative_parts(relative: Path) -> tuple[str, ...]:
    if relative.is_absolute() or not relative.parts:
        raise IntegrationError(f"unsafe repository-relative path: {relative}")
    parts = tuple(relative.parts)
    if any(part in {"", ".", ".."} or "/" in part or "\x00" in part for part in parts):
        raise IntegrationError(f"unsafe repository-relative path: {relative}")
    return parts


def _directory_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


@contextmanager
def _repo_anchor(repo_root: Path) -> Iterator[tuple[Path, int, tuple[int, int]]]:
    absolute = Path(os.path.abspath(os.fspath(repo_root)))
    try:
        root_fd = os.open(absolute, _directory_flags())
    except OSError as exc:
        raise IntegrationError(
            f"cannot safely open repository root {absolute}: {exc}"
        ) from exc
    try:
        opened = os.fstat(root_fd)
        pathname = os.stat(absolute, follow_symlinks=False)
        if not stat.S_ISDIR(opened.st_mode) or not stat.S_ISDIR(pathname.st_mode):
            raise IntegrationError("repository root is not a real directory")
        identity = (opened.st_dev, opened.st_ino)
        if identity != (pathname.st_dev, pathname.st_ino):
            raise IntegrationError("repository root pathname is not stable")
        yield absolute, root_fd, identity
    finally:
        os.close(root_fd)


def _assert_repo_anchor(absolute: Path, identity: tuple[int, int]) -> None:
    try:
        current = os.stat(absolute, follow_symlinks=False)
    except OSError as exc:
        raise IntegrationError("repository root pathname disappeared") from exc
    if (
        not stat.S_ISDIR(current.st_mode)
        or (current.st_dev, current.st_ino) != identity
    ):
        raise IntegrationError("repository root pathname identity changed")


def _open_directory_at(
    root_fd: int,
    relative: Path,
    *,
    create: bool = False,
    missing_ok: bool = False,
    mode: int = 0o755,
) -> int | None:
    parts = _relative_parts(relative) if relative != Path(".") else ()
    current = os.dup(root_fd)
    try:
        for part in parts:
            created = False
            if create:
                try:
                    os.mkdir(part, mode, dir_fd=current)
                    created = True
                    os.fsync(current)
                except FileExistsError:
                    pass
            try:
                metadata = os.stat(part, dir_fd=current, follow_symlinks=False)
            except FileNotFoundError:
                if missing_ok and not create:
                    os.close(current)
                    return None
                raise IntegrationError(
                    f"missing anchored directory: {relative}"
                ) from None
            if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
                raise IntegrationError(f"unsafe anchored directory: {relative}")
            try:
                child = os.open(part, _directory_flags(), dir_fd=current)
            except OSError as exc:
                raise IntegrationError(
                    f"cannot safely open directory {relative}: {exc}"
                ) from exc
            opened = os.fstat(child)
            if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
                os.close(child)
                raise IntegrationError(
                    f"anchored directory changed while opening: {relative}"
                )
            if created:
                os.fsync(child)
            os.close(current)
            current = child
        return current
    except BaseException:
        try:
            os.close(current)
        except OSError:
            pass
        raise


def _parent_fd(root_fd: int, relative: Path, *, create: bool) -> tuple[int, str]:
    parts = _relative_parts(relative)
    if len(parts) == 1:
        return os.dup(root_fd), parts[0]
    opened = _open_directory_at(root_fd, Path(*parts[:-1]), create=create)
    assert opened is not None
    return opened, parts[-1]


def _read_at(
    root_fd: int,
    relative: Path,
    *,
    limit: int = MAX_MEMBER_BYTES,
    missing_ok: bool = True,
) -> tuple[bytes, os.stat_result] | None:
    try:
        parent, name = _parent_fd(root_fd, relative, create=False)
    except IntegrationError:
        if missing_ok:
            return None
        raise
    parent_metadata = os.fstat(parent)
    parent_identity = (parent_metadata.st_dev, parent_metadata.st_ino)
    try:
        try:
            descriptor = os.open(
                name,
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=parent,
            )
        except FileNotFoundError:
            if missing_ok:
                return None
            raise IntegrationError(f"missing anchored file: {relative}") from None
        except OSError as exc:
            raise IntegrationError(
                f"cannot safely open anchored file {relative}: {exc}"
            ) from exc
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
                raise IntegrationError(
                    f"anchored file is not bounded regular data: {relative}"
                )
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(descriptor, min(1024 * 1024, limit + 1 - total))
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise IntegrationError(
                        f"anchored file exceeds byte limit: {relative}"
                    )
                chunks.append(chunk)
            after = os.fstat(descriptor)
            payload = b"".join(chunks)
            try:
                pathname = os.stat(name, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError as exc:
                raise IntegrationError(
                    f"anchored file pathname disappeared while reading: {relative}"
                ) from exc
            if (
                _identity(before) != _identity(after)
                or _identity(before) != _identity(pathname)
                or len(payload) != before.st_size
            ):
                raise IntegrationError(
                    f"anchored file changed while reading: {relative}"
                )
            if _directory_identity_at(root_fd, relative.parent) != parent_identity:
                raise IntegrationError(
                    f"anchored file parent changed while reading: {relative.parent}"
                )
            return payload, before
        finally:
            os.close(descriptor)
    finally:
        os.close(parent)


def _directory_identity_at(root_fd: int, relative: Path) -> tuple[int, int]:
    opened = _open_directory_at(root_fd, relative)
    assert opened is not None
    try:
        metadata = os.fstat(opened)
        return metadata.st_dev, metadata.st_ino
    finally:
        os.close(opened)


def _write_at(root_fd: int, relative: Path, data: bytes, mode: int = 0o644) -> None:
    if not isinstance(data, bytes) or len(data) > MAX_MEMBER_BYTES:
        raise IntegrationError(f"output is not bounded bytes: {relative}")
    if isinstance(mode, bool) or not isinstance(mode, int) or not 0 <= mode <= 0o777:
        raise IntegrationError(f"output mode is unsafe: {relative}")
    parent, name = _parent_fd(root_fd, relative, create=True)
    parent_identity = _identity(os.fstat(parent))
    temporary = f".{name}.delta-{uuid.uuid4().hex}"
    descriptor = -1
    try:
        try:
            existing = os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        if existing is not None and not stat.S_ISREG(existing.st_mode):
            raise IntegrationError(f"unsafe anchored output target: {relative}")
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        descriptor = os.open(temporary, flags, 0o600, dir_fd=parent)
        offset = 0
        while offset < len(data):
            written = os.write(descriptor, data[offset:])
            if written <= 0:
                raise IntegrationError(f"short anchored write: {relative}")
            offset += written
        os.fchmod(descriptor, mode)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
        os.fsync(parent)
        if _directory_identity_at(root_fd, relative.parent) != (
            parent_identity[0],
            parent_identity[1],
        ):
            raise IntegrationError(
                f"anchored output parent changed during publication: {relative.parent}"
            )
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary, dir_fd=parent)
        except FileNotFoundError:
            pass
        os.close(parent)


def _unlink_at(root_fd: int, relative: Path, *, missing_ok: bool = False) -> None:
    parent, name = _parent_fd(root_fd, relative, create=False)
    parent_metadata = os.fstat(parent)
    parent_identity = (parent_metadata.st_dev, parent_metadata.st_ino)
    try:
        try:
            metadata = os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            if missing_ok:
                return
            raise
        if not stat.S_ISREG(metadata.st_mode):
            raise IntegrationError(f"refusing to unlink non-regular path: {relative}")
        os.unlink(name, dir_fd=parent)
        os.fsync(parent)
        if _directory_identity_at(root_fd, relative.parent) != parent_identity:
            raise IntegrationError(f"anchored unlink parent changed: {relative.parent}")
    finally:
        os.close(parent)


def _expected_output_paths() -> frozenset[Path]:
    paths = set(SOURCE_ASSET_TARGETS.values())
    for schema in EXPECTED_SCHEMA_FILES:
        paths.add(ENGINE_ROOT / "schemas/delta-v3.1" / schema)
        paths.add(
            ENGINE_ROOT
            / "examples/delta-v3.1"
            / schema.replace(".schema.json", ".example.json")
        )
    paths.update(
        {
            DELTA_ROOT / ".source-data/DELTA_MANIFEST.json",
            DELTA_ROOT / ".source-data/registry.v3.1.json",
            DELTA_ROOT / ".source-data/PAYLOAD_HASHES.json",
            DELTA_ROOT / "source-boundary.json",
        }
    )
    for skill_name in EXPECTED_SKILL_NAMES:
        for root in (Path(".agents/skills"), Path("agent-skills/runtime")):
            paths.update(
                {
                    root / skill_name / "SKILL.md",
                    root / skill_name / "compiled-contract.json",
                    root / skill_name / "agents/openai.yaml",
                }
            )
    return frozenset(paths)


def _validate_outputs(outputs: Mapping[Path, bytes]) -> None:
    expected = _expected_output_paths()
    if set(outputs) != expected:
        missing = sorted(str(path) for path in expected - set(outputs))
        extra = sorted(str(path) for path in set(outputs) - expected)
        raise IntegrationError(
            f"generated output inventory drifted: missing={missing} extra={extra}"
        )
    for path, data in outputs.items():
        _relative_parts(path)
        if not isinstance(data, bytes) or len(data) > MAX_MEMBER_BYTES:
            raise IntegrationError(f"output must be bounded bytes: {path}")
    for skill_name in EXPECTED_SKILL_NAMES:
        for relative in (
            Path("SKILL.md"),
            Path("compiled-contract.json"),
            Path("agents/openai.yaml"),
        ):
            left = Path(".agents/skills") / skill_name / relative
            right = Path("agent-skills/runtime") / skill_name / relative
            if outputs[left] != outputs[right]:
                raise IntegrationError(
                    f"generated dual Skill roots differ: {skill_name}/{relative}"
                )


def _managed_roots() -> tuple[Path, ...]:
    roots = {
        DELTA_ROOT,
        ENGINE_ROOT / "schemas/delta-v3.1",
        ENGINE_ROOT / "examples/delta-v3.1",
        ENGINE_ROOT / "api/delta-v3.1",
        ENGINE_ROOT / "adapters/delta-v3.1",
        ENGINE_ROOT / "observability/delta-v3.1",
        ENGINE_ROOT / "policies/delta-v3.1",
        ENGINE_ROOT / "verification/delta-v3.1",
    }
    for skill_name in EXPECTED_SKILL_NAMES:
        roots.add(Path(".agents/skills") / skill_name)
        roots.add(Path("agent-skills/runtime") / skill_name)
    return tuple(sorted(roots))


def _existing_files_under_at(
    root_fd: int,
    relative: Path,
    *,
    skip_transaction_root: bool = False,
    allowed_directories: frozenset[Path] | None = None,
) -> set[Path]:
    directory = _open_directory_at(root_fd, relative, missing_ok=True)
    if directory is None:
        return set()
    found: set[Path] = set()

    def walk(directory_fd: int, prefix: Path) -> None:
        for name in sorted(os.listdir(directory_fd)):
            if name in {"", ".", ".."} or "/" in name or "\x00" in name:
                raise IntegrationError(f"unsafe managed entry: {prefix / name}")
            child_relative = prefix / name
            if skip_transaction_root and child_relative == DELTA_ROOT / ".transactions":
                continue
            metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if stat.S_ISLNK(metadata.st_mode):
                raise IntegrationError(
                    f"managed symlink is forbidden: {child_relative}"
                )
            if stat.S_ISREG(metadata.st_mode):
                found.add(child_relative)
            elif stat.S_ISDIR(metadata.st_mode):
                if (
                    allowed_directories is not None
                    and child_relative not in allowed_directories
                ):
                    raise IntegrationError(
                        f"unexpected managed directory: {child_relative}"
                    )
                child = os.open(name, _directory_flags(), dir_fd=directory_fd)
                try:
                    opened = os.fstat(child)
                    if (opened.st_dev, opened.st_ino) != (
                        metadata.st_dev,
                        metadata.st_ino,
                    ):
                        raise IntegrationError(
                            f"managed directory raced open: {child_relative}"
                        )
                    walk(child, child_relative)
                finally:
                    os.close(child)
            else:
                raise IntegrationError(
                    f"managed special file is forbidden: {child_relative}"
                )

    try:
        walk(directory, relative)
    finally:
        os.close(directory)
    return found


def _managed_inventory_at(root_fd: int) -> set[Path]:
    found: set[Path] = set()
    allowed_directories = frozenset(
        parent
        for path in _expected_output_paths()
        for parent in path.parents
        if parent != Path(".")
    )
    for managed in _managed_roots():
        found.update(
            _existing_files_under_at(
                root_fd,
                managed,
                skip_transaction_root=managed == DELTA_ROOT,
                allowed_directories=allowed_directories,
            )
        )
    return found


TRANSACTION_ROOT = DELTA_ROOT / ".transactions"
_TRANSACTION_ID = re.compile(r"[0-9a-f]{32}")
_TRANSACTION_JOURNAL_KEYS = {
    "schema_version",
    "transaction_id",
    "state",
    "allowed_outputs",
    "entries",
}


def _validate_transaction_path(
    transaction: Path, *, allow_descendant: bool = False
) -> str:
    """Return the transaction id only for the reserved transaction subtree.

    This intentionally rejects ``Path()``/``Path('.')``, the repository root,
    the transaction container itself, arbitrary repository directories, and a
    descendant when a transaction root is required.  Cleanup authority must
    never be inferred merely from a directory file descriptor.
    """

    parts = _relative_parts(transaction)
    root_parts = _relative_parts(TRANSACTION_ROOT)
    minimum = len(root_parts) + 1
    if (
        len(parts) < minimum
        or parts[: len(root_parts)] != root_parts
        or _TRANSACTION_ID.fullmatch(parts[len(root_parts)]) is None
        or (not allow_descendant and len(parts) != minimum)
    ):
        raise IntegrationError(f"unsafe transaction cleanup path: {transaction}")
    return parts[len(root_parts)]


def _assert_private_transaction_directory(directory_fd: int, label: Path) -> None:
    metadata = os.fstat(directory_fd)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise IntegrationError(f"transaction directory is not private: {label}")


def _assert_open_directory_binding_at(
    root_fd: int, directory_fd: int, relative: Path
) -> None:
    opened = os.fstat(directory_fd)
    current = _directory_identity_at(root_fd, relative)
    if not stat.S_ISDIR(opened.st_mode) or current != (opened.st_dev, opened.st_ino):
        raise IntegrationError(f"transaction directory binding changed: {relative}")


def _remove_directory_contents_at(root_fd: int, directory_fd: int, label: Path) -> None:
    _validate_transaction_path(label, allow_descendant=True)
    _assert_open_directory_binding_at(root_fd, directory_fd, label)
    for name in sorted(os.listdir(directory_fd)):
        if name in {"", ".", ".."} or "/" in name or "\x00" in name:
            raise IntegrationError(f"unsafe transaction entry name: {name!r}")
        relative = label / name
        metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if stat.S_ISREG(metadata.st_mode):
            os.unlink(name, dir_fd=directory_fd)
        elif stat.S_ISDIR(metadata.st_mode):
            child = os.open(name, _directory_flags(), dir_fd=directory_fd)
            try:
                opened = os.fstat(child)
                if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
                    raise IntegrationError(
                        f"transaction directory raced open: {relative}"
                    )
                _remove_directory_contents_at(root_fd, child, relative)
            finally:
                os.close(child)
            current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != (
                metadata.st_dev,
                metadata.st_ino,
            ):
                raise IntegrationError(
                    f"transaction directory changed before removal: {relative}"
                )
            os.rmdir(name, dir_fd=directory_fd)
        else:
            raise IntegrationError(f"unsafe transaction entry: {relative}")
    os.fsync(directory_fd)
    _assert_open_directory_binding_at(root_fd, directory_fd, label)


def _remove_tree_at(root_fd: int, relative: Path) -> None:
    _validate_transaction_path(relative)
    parent, name = _parent_fd(root_fd, relative, create=False)
    try:
        metadata = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if not stat.S_ISDIR(metadata.st_mode):
            raise IntegrationError(f"transaction path is not a directory: {relative}")
        child = os.open(name, _directory_flags(), dir_fd=parent)
        try:
            opened = os.fstat(child)
            if (opened.st_dev, opened.st_ino) != (
                metadata.st_dev,
                metadata.st_ino,
            ):
                raise IntegrationError(f"transaction directory raced open: {relative}")
            _assert_private_transaction_directory(child, relative)
            _remove_directory_contents_at(root_fd, child, relative)
        finally:
            os.close(child)
        current = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (
            metadata.st_dev,
            metadata.st_ino,
        ):
            raise IntegrationError(
                f"transaction directory changed before removal: {relative}"
            )
        os.rmdir(name, dir_fd=parent)
        os.fsync(parent)
    finally:
        os.close(parent)


def _remove_empty_directory_at(root_fd: int, relative: Path) -> None:
    if relative != TRANSACTION_ROOT:
        raise IntegrationError(f"unsafe empty-directory cleanup path: {relative}")
    parts = _relative_parts(relative)
    parent = _open_directory_at(root_fd, Path(*parts[:-1]), missing_ok=True)
    if parent is None:
        return
    name = parts[-1]
    try:
        try:
            metadata = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if not stat.S_ISDIR(metadata.st_mode):
                raise IntegrationError(
                    f"transaction container is not a directory: {relative}"
                )
            child = os.open(name, _directory_flags(), dir_fd=parent)
            try:
                opened = os.fstat(child)
                if (opened.st_dev, opened.st_ino) != (
                    metadata.st_dev,
                    metadata.st_ino,
                ):
                    raise IntegrationError(
                        f"transaction container raced open: {relative}"
                    )
                _assert_private_transaction_directory(child, relative)
                if os.listdir(child):
                    return
            finally:
                os.close(child)
            current = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != (
                metadata.st_dev,
                metadata.st_ino,
            ):
                raise IntegrationError(
                    f"transaction container changed before removal: {relative}"
                )
            os.rmdir(name, dir_fd=parent)
            os.fsync(parent)
        except FileNotFoundError:
            pass
        except OSError as exc:
            if exc.errno not in {errno.ENOTEMPTY, errno.EEXIST}:
                raise IntegrationError(
                    f"cannot safely remove transaction container: {relative}: {exc}"
                ) from exc
    finally:
        os.close(parent)


def _write_journal_at(root_fd: int, path: Path, journal: Mapping[str, Any]) -> None:
    _validate_transaction_path(path.parent)
    if path.name != "journal.json":
        raise IntegrationError(f"unsafe transaction journal path: {path}")
    _write_at(root_fd, path, _json_bytes(journal), 0o600)


def _validated_transaction_entries(
    transaction: Path,
    journal: Mapping[str, Any],
    expected_paths: frozenset[Path],
) -> tuple[Mapping[str, Any], ...]:
    transaction_id = _validate_transaction_path(transaction)
    expected_strings = [str(path) for path in sorted(expected_paths)]
    if (
        set(journal) != _TRANSACTION_JOURNAL_KEYS
        or journal.get("schema_version") != "1.0.0"
        or journal.get("transaction_id") != transaction_id
        or journal.get("state") not in {"ACTIVE", "ROLLED_BACK", "COMMITTED"}
        or journal.get("allowed_outputs") != expected_strings
        or not isinstance(journal.get("entries"), list)
        or len(journal["entries"]) > len(expected_strings)
    ):
        raise IntegrationError(f"invalid transaction journal: {transaction}")

    validated: list[Mapping[str, Any]] = []
    for index, entry in enumerate(journal["entries"]):
        if not isinstance(entry, Mapping):
            raise IntegrationError(f"invalid transaction row: {transaction}")
        target = entry.get("target")
        digest = entry.get("output_sha256")
        existed = entry.get("existed")
        expected_keys = {
            "target",
            "existed",
            "output_sha256",
            "state",
        }
        if existed is True:
            expected_keys.update({"backup", "backup_sha256", "mode"})
        if (
            set(entry) != expected_keys
            or target != expected_strings[index]
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or entry.get("state") not in {"PREPARED", "PUBLISHED"}
            or not isinstance(existed, bool)
        ):
            raise IntegrationError(f"unsafe transaction row: {transaction}")
        if existed is True:
            backup_name = entry.get("backup")
            backup_digest = entry.get("backup_sha256")
            mode = entry.get("mode")
            if (
                backup_name != f"backups/{index:04d}.bin"
                or not isinstance(backup_digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", backup_digest) is None
                or isinstance(mode, bool)
                or not isinstance(mode, int)
                or not 0 <= mode <= 0o777
            ):
                raise IntegrationError(f"invalid transaction backup: {transaction}")
        validated.append(entry)
    if journal["state"] == "COMMITTED" and (
        len(validated) != len(expected_strings)
        or any(entry["state"] != "PUBLISHED" for entry in validated)
    ):
        raise IntegrationError(f"incomplete committed transaction: {transaction}")
    return tuple(validated)


def _rollback_transaction_at(
    root_fd: int,
    transaction: Path,
    journal: Mapping[str, Any],
    expected_paths: frozenset[Path],
) -> None:
    entries = _validated_transaction_entries(transaction, journal, expected_paths)
    if journal["state"] != "ACTIVE":
        raise IntegrationError(
            f"refusing rollback for non-active transaction: {transaction}"
        )
    for entry in reversed(entries):
        target = entry.get("target")
        digest = entry.get("output_sha256")
        existed = entry.get("existed")
        assert isinstance(target, str)
        assert isinstance(digest, str)
        relative = Path(target)
        current = _read_at(root_fd, relative)
        if existed is True:
            backup_name = entry.get("backup")
            backup_digest = entry.get("backup_sha256")
            mode = entry.get("mode")
            assert isinstance(backup_name, str)
            assert isinstance(backup_digest, str)
            assert isinstance(mode, int) and not isinstance(mode, bool)
            loaded = _read_at(root_fd, transaction / backup_name, missing_ok=False)
            assert loaded is not None
            backup = loaded[0]
            if _sha256(backup) != backup_digest:
                raise IntegrationError(
                    f"transaction backup digest mismatch: {transaction}"
                )
            if current is not None and _sha256(current[0]) not in {
                digest,
                backup_digest,
            }:
                raise IntegrationError(
                    f"concurrent mutation prevents rollback: {relative}"
                )
            _write_at(root_fd, relative, backup, mode)
        elif existed is False:
            if current is not None:
                if _sha256(current[0]) != digest:
                    raise IntegrationError(
                        f"concurrent mutation prevents rollback: {relative}"
                    )
                _unlink_at(root_fd, relative)
        else:
            raise IntegrationError(
                f"invalid transaction existence state: {transaction}"
            )


def _verify_committed_transaction_at(
    root_fd: int,
    transaction: Path,
    journal: Mapping[str, Any],
    expected_paths: frozenset[Path],
) -> None:
    entries = _validated_transaction_entries(transaction, journal, expected_paths)
    if journal["state"] != "COMMITTED":
        raise IntegrationError(f"transaction is not committed: {transaction}")
    for entry in entries:
        target = entry["target"]
        loaded = _read_at(root_fd, Path(target), missing_ok=False)
        assert loaded is not None
        if _sha256(loaded[0]) != entry["output_sha256"]:
            raise IntegrationError(f"committed transaction output drifted: {target}")


def _is_safe_uninitialized_transaction_at(root_fd: int, transaction: Path) -> bool:
    """Recognize only the crash window before the journal became visible."""

    _validate_transaction_path(transaction)
    directory = _open_directory_at(root_fd, transaction)
    assert directory is not None
    try:
        _assert_private_transaction_directory(directory, transaction)
        for name in sorted(os.listdir(directory)):
            metadata = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if name == "backups" and stat.S_ISDIR(metadata.st_mode):
                child = os.open(name, _directory_flags(), dir_fd=directory)
                try:
                    _assert_private_transaction_directory(
                        child, transaction / "backups"
                    )
                    if os.listdir(child):
                        return False
                finally:
                    os.close(child)
                continue
            if (
                re.fullmatch(r"\.journal\.json\.delta-[0-9a-f]{32}", name)
                and stat.S_ISREG(metadata.st_mode)
                and metadata.st_uid == os.geteuid()
                and metadata.st_nlink == 1
                and metadata.st_size <= MAX_RECEIPT_BYTES
            ):
                continue
            return False
        return True
    finally:
        os.close(directory)


def _recover_transactions_at(root_fd: int, expected_paths: frozenset[Path]) -> None:
    transaction_root = _open_directory_at(root_fd, TRANSACTION_ROOT, missing_ok=True)
    if transaction_root is None:
        return
    try:
        _assert_private_transaction_directory(transaction_root, TRANSACTION_ROOT)
        names = sorted(os.listdir(transaction_root))
    finally:
        os.close(transaction_root)
    for name in names:
        if _TRANSACTION_ID.fullmatch(name) is None:
            raise IntegrationError(f"unsafe transaction directory: {name!r}")
        transaction = TRANSACTION_ROOT / name
        loaded = _read_at(
            root_fd,
            transaction / "journal.json",
            limit=MAX_RECEIPT_BYTES,
            missing_ok=True,
        )
        if loaded is None:
            if not _is_safe_uninitialized_transaction_at(root_fd, transaction):
                raise IntegrationError(
                    f"transaction journal is missing from non-empty state: {transaction}"
                )
            _remove_tree_at(root_fd, transaction)
            continue
        journal = _strict_json(loaded[0], str(transaction / "journal.json"))
        if not isinstance(journal, Mapping):
            raise IntegrationError(f"invalid transaction journal: {transaction}")
        _validated_transaction_entries(transaction, journal, expected_paths)
        if journal["state"] == "ACTIVE":
            _rollback_transaction_at(root_fd, transaction, journal, expected_paths)
            journal = dict(journal)
            journal["state"] = "ROLLED_BACK"
            _write_journal_at(root_fd, transaction / "journal.json", journal)
        elif journal["state"] == "COMMITTED":
            _verify_committed_transaction_at(
                root_fd, transaction, journal, expected_paths
            )
        _remove_tree_at(root_fd, transaction)
    _remove_empty_directory_at(root_fd, TRANSACTION_ROOT)


def _create_transaction_at(
    root_fd: int, expected_paths: frozenset[Path]
) -> tuple[Path, dict[str, Any]]:
    transaction_parent = _open_directory_at(
        root_fd, TRANSACTION_ROOT.parent, create=True, mode=0o755
    )
    assert transaction_parent is not None
    try:
        try:
            os.mkdir(TRANSACTION_ROOT.name, 0o700, dir_fd=transaction_parent)
            os.fsync(transaction_parent)
        except FileExistsError:
            pass
    finally:
        os.close(transaction_parent)
    transaction_root = _open_directory_at(root_fd, TRANSACTION_ROOT)
    assert transaction_root is not None
    try:
        _assert_private_transaction_directory(transaction_root, TRANSACTION_ROOT)
    except BaseException:
        os.close(transaction_root)
        raise
    name = uuid.uuid4().hex
    transaction = TRANSACTION_ROOT / name
    created = False
    try:
        try:
            os.mkdir(name, 0o700, dir_fd=transaction_root)
            created = True
            os.fsync(transaction_root)
        finally:
            os.close(transaction_root)
        transaction_fd = _open_directory_at(root_fd, transaction)
        assert transaction_fd is not None
        try:
            _assert_private_transaction_directory(transaction_fd, transaction)
        finally:
            os.close(transaction_fd)
        backups = _open_directory_at(
            root_fd, transaction / "backups", create=True, mode=0o700
        )
        assert backups is not None
        try:
            _assert_private_transaction_directory(backups, transaction / "backups")
            os.fsync(backups)
        finally:
            os.close(backups)
        journal: dict[str, Any] = {
            "schema_version": "1.0.0",
            "transaction_id": name,
            "state": "ACTIVE",
            "allowed_outputs": [str(path) for path in sorted(expected_paths)],
            "entries": [],
        }
        _write_journal_at(root_fd, transaction / "journal.json", journal)
        return transaction, journal
    except BaseException as original:
        if created:
            try:
                _remove_tree_at(root_fd, transaction)
                _remove_empty_directory_at(root_fd, TRANSACTION_ROOT)
            except BaseException as cleanup_error:
                raise IntegrationError(
                    "transaction initialization failed and cleanup failed: "
                    f"{cleanup_error}"
                ) from original
        raise


def _verify_installation_at(
    root_fd: int, outputs: Mapping[Path, bytes]
) -> dict[str, Any]:
    _validate_outputs(outputs)
    actual = _managed_inventory_at(root_fd)
    expected = set(outputs)
    if actual != expected:
        missing = sorted(str(path) for path in expected - actual)
        extra = sorted(str(path) for path in actual - expected)
        raise IntegrationError(
            f"delta installed inventory drifted: missing={missing} extra={extra}"
        )
    for path, data in outputs.items():
        current = _read_at(root_fd, path, missing_ok=False)
        assert current is not None
        if current[0] != data:
            raise IntegrationError(f"delta installation content drifted: {path}")
    return {
        "status": "PASS",
        "files": len(outputs),
        "skills": EXPECTED_EXTENSION_SKILLS,
        "dual_roots_byte_identical": True,
        "sha256": _sha256(b"".join(outputs[path] for path in sorted(outputs))),
    }


def install_outputs(
    repo_root: Path,
    outputs: Mapping[Path, bytes],
    *,
    failure_after: int | None = None,
    precommit_validate: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Publish the exact delta inventory with durable crash recovery."""

    outputs = dict(outputs)
    _validate_outputs(outputs)
    expected_paths = _expected_output_paths()
    with _repo_anchor(repo_root) as (absolute, root_fd, root_identity):
        _recover_transactions_at(root_fd, expected_paths)
        unmanaged = _managed_inventory_at(root_fd) - expected_paths
        if unmanaged:
            raise IntegrationError(
                f"refusing to overwrite unmanaged delta files: {sorted(map(str, unmanaged))}"
            )
        transaction, journal = _create_transaction_at(root_fd, expected_paths)
        journal_path = transaction / "journal.json"
        published = 0
        try:
            for index, relative in enumerate(sorted(outputs)):
                current = _read_at(root_fd, relative)
                entry: dict[str, Any] = {
                    "target": str(relative),
                    "existed": current is not None,
                    "output_sha256": _sha256(outputs[relative]),
                    "state": "PREPARED",
                }
                if current is not None:
                    backup_name = f"backups/{index:04d}.bin"
                    _write_at(root_fd, transaction / backup_name, current[0], 0o600)
                    entry.update(
                        {
                            "backup": backup_name,
                            "backup_sha256": _sha256(current[0]),
                            "mode": stat.S_IMODE(current[1].st_mode),
                        }
                    )
                journal["entries"].append(entry)
                _write_journal_at(root_fd, journal_path, journal)
                _write_at(root_fd, relative, outputs[relative])
                entry["state"] = "PUBLISHED"
                _write_journal_at(root_fd, journal_path, journal)
                published += 1
                if failure_after is not None and published >= failure_after:
                    raise IntegrationError("injected integration failure")
            result = _verify_installation_at(root_fd, outputs)
            _assert_repo_anchor(absolute, root_identity)
            if precommit_validate is not None:
                precommit_validate()
            journal["state"] = "COMMITTED"
            _write_journal_at(root_fd, journal_path, journal)
        except BaseException as original:
            try:
                _rollback_transaction_at(root_fd, transaction, journal, expected_paths)
                journal["state"] = "ROLLED_BACK"
                _write_journal_at(root_fd, journal_path, journal)
                _remove_tree_at(root_fd, transaction)
                _remove_empty_directory_at(root_fd, TRANSACTION_ROOT)
            except BaseException as rollback_error:
                raise IntegrationError(
                    f"delta install failed and rollback failed: {rollback_error}"
                ) from original
            raise
        _remove_tree_at(root_fd, transaction)
        _remove_empty_directory_at(root_fd, TRANSACTION_ROOT)
        _assert_repo_anchor(absolute, root_identity)
        return result


def verify_installation(
    repo_root: Path, outputs: Mapping[Path, bytes]
) -> dict[str, Any]:
    outputs = dict(outputs)
    _validate_outputs(outputs)
    with _repo_anchor(repo_root) as (absolute, root_fd, root_identity):
        _recover_transactions_at(root_fd, _expected_output_paths())
        result = _verify_installation_at(root_fd, outputs)
        _assert_repo_anchor(absolute, root_identity)
        return result


def _lock_path(repo_root: Path) -> Path:
    lock_root = Path(tempfile.gettempdir()).resolve(strict=True)
    return lock_root / (
        "elmos-harness-runtime-delta-"
        + hashlib.sha256(str(repo_root.resolve()).encode()).hexdigest()[:24]
        + ".lock"
    )


def _assert_lock_binding(path: Path, descriptor: int) -> None:
    opened = os.fstat(descriptor)
    try:
        pathname = os.stat(path, follow_symlinks=False)
    except FileNotFoundError as exc:
        raise IntegrationError("integration lock pathname disappeared") from exc
    if (
        not stat.S_ISREG(opened.st_mode)
        or not stat.S_ISREG(pathname.st_mode)
        or opened.st_uid != os.geteuid()
        or pathname.st_uid != os.geteuid()
        or opened.st_nlink != 1
        or pathname.st_nlink != 1
        or stat.S_IMODE(opened.st_mode) & 0o022
        or stat.S_IMODE(pathname.st_mode) & 0o022
        or (opened.st_dev, opened.st_ino) != (pathname.st_dev, pathname.st_ino)
    ):
        raise IntegrationError("integration lock pathname binding is unsafe")


@contextmanager
def _exclusive_lock(repo_root: Path) -> Iterator[None]:
    path = _lock_path(repo_root)
    flags = (
        os.O_RDWR
        | os.O_CREAT
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise IntegrationError(
            f"cannot safely open integration lock {path}: {exc}"
        ) from exc
    try:
        _assert_lock_binding(path, descriptor)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        _assert_lock_binding(path, descriptor)
        try:
            yield
        except BaseException:
            raise
        else:
            _assert_lock_binding(path, descriptor)
    finally:
        os.close(descriptor)


def run(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).resolve(strict=True)
    archive_path = Path(args.archive)
    if not archive_path.is_absolute():
        archive_path = repo_root / archive_path
    audit = audit_archive(archive_path)
    with _exclusive_lock(repo_root):
        status = _receipt_status(repo_root, audit)
        outputs = build_outputs(audit, status=status)

        def require_stable_qualification() -> None:
            if _receipt_status(repo_root, audit) != status:
                raise IntegrationError(
                    "delta qualification binding changed during integration"
                )

        if args.audit:
            require_stable_qualification()
            return {
                "action": "audit",
                **audit.summary(implementation_status=status),
            }
        if args.install:
            result = install_outputs(
                repo_root,
                outputs,
                precommit_validate=require_stable_qualification,
            )
            return {
                "action": "install",
                **audit.summary(implementation_status=status),
                "installation": result,
            }
        result = verify_installation(repo_root, outputs)
        require_stable_qualification()
        return {
            "action": "check",
            **audit.summary(implementation_status=status),
            "installation": result,
        }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--archive", type=Path, default=ARCHIVE_RELATIVE_PATH)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--audit", action="store_true")
    action.add_argument("--install", action="store_true")
    action.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        print(
            json.dumps(
                run(args), ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False
            )
        )
        return 0
    except (IntegrationError, OSError, ValueError) as exc:
        print(
            json.dumps(
                {"status": "FAIL", "error": str(exc)},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
