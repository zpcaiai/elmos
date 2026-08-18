"""Assemble a batch report's PASSED units into one buildable target-language project.

The repository-scope pipeline (`repository.py` -> `discovery.py` -> `batch.py`)
proves each work unit in isolation: one function, one fixed-name emitted file
(`Migrated.java` / `Migrated.cs` / `migrated.py` / `migrated.ts`), one harness,
one exact-toolchain verification run. None of that is a project a human or a
CI pipeline could actually build, because every PASSED unit reuses the same
file name and, for Java/C#, the same class name -- combining two units
verbatim would collide on the first duplicate.

This module closes that gap for a single already-run batch report:

1. `assemble_project` places each PASSED unit's already-emitted source under a
   per-unit namespace so nothing collides, writes a real per-language build
   manifest, and records exactly which units were included and which were
   excluded (and why). It never re-derives or re-emits source -- it only
   relocates bytes the batch already produced, re-verifying each unit's
   recorded sha256 first (defense in depth against a tampered or stale batch
   output directory).
2. `verify_assembled_project` runs a real whole-project compile/build check
   against the assembled project using the same exact-toolchain contract the
   per-unit harness in `validation.py` already enforces, and folds the result
   back into the manifest on disk.

Both functions fail closed: a missing unit source, a sha256 mismatch, a path
that escapes its unit directory, or a failed compiler invocation raises
`RouteError` rather than producing a project that looks assembled but is not
actually attributable to proven work.
"""

from __future__ import annotations

import atexit
import base64
import hashlib
import json
import math
import os
import re
import shutil
import stat
import struct
import subprocess
import tempfile
import threading
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .assembly_deployment_guidance import render_assembly_deployment_guidance
from .identifier_hygiene import (
    IdentifierPlan,
    IdentifierUnitNamespace,
    repository_work_unit_namespace,
    target_function_view,
    validate_identifier_plan,
)
from .models import Language, RouteError, SemanticIR
from .toolchains import exact_toolchain, sanitized_subprocess_env
from .validation import _bounded_process_diagnostic, safe_output

SCHEMA_VERSION = "1.0.0"
MANIFEST_NAME = "assembly-manifest.json"

_EVIDENCE_ROOT = "evidence"
_ROUTE_EVIDENCE_NAME = "route-evidence.json"
_BEHAVIOR_EVIDENCE_NAME = "behavior-equivalence.json"
_SOURCE_SEMANTIC_IR_NAME = "source-semantic-ir.json"
_IDENTIFIER_PLAN_NAME = "identifier-plan.json"
_JAVASCRIPT_ESM_DESCRIPTOR_NAME = "source-javascript-esm-package.json"
_EVIDENCE_ROLE_ORDER = {
    "route-evidence": 0,
    "behavior-equivalence": 1,
    "source-semantic-ir": 2,
    "identifier-plan": 3,
    "emitted-target": 4,
    "source-javascript-esm-descriptor": 5,
}

_EXPECTED_CMAKE_PREFIX = Path("/opt/homebrew/Cellar/cmake/4.4.0")
_EXPECTED_CMAKE_EXECUTABLE = Path("/opt/homebrew/Cellar/cmake/4.4.0/bin/cmake")
_EXPECTED_CMAKE_RESOURCE_ROOT = Path("/opt/homebrew/Cellar/cmake/4.4.0/share/cmake")
_EXPECTED_CMAKE_VERSION = "cmake version 4.4.0"
_EXPECTED_CMAKE_BYTES = 14_081_864
_EXPECTED_CMAKE_SHA256 = "8f136fce6bb8e9dbea38320f8a615b1f4896fe80cc7da5c1ff3da69e834f5d4c"
_EXPECTED_CMAKE_SOURCE_UID = 501
_EXPECTED_CMAKE_SOURCE_GID = 80
_EXPECTED_CMAKE_TREE_ENTRY_COUNT = 4_201
_EXPECTED_CMAKE_TREE_FILE_BYTES = 24_264_810
_EXPECTED_CMAKE_TREE_SHA256 = "6b431db533d7e04224af02cb02e0c374fb61803fc988dafcfa2ffdaa83d26c7c"
_EXPECTED_CMAKE_RUNTIME_MANIFEST_BYTES = 1_194_151
_EXPECTED_CMAKE_RUNTIME_MANIFEST_SHA256 = "8af497a7db37497c4faf5b2cdcfce7cff65b6bdf204d2063d010d0f59892d648"
_CMAKE_RUNTIME_MANIFEST = "cmake-runtime-manifest.json"


@dataclass(frozen=True)
class _CMakeBinding:
    path: str
    kind: str
    mode: int
    uid: int
    gid: int
    bytes: int
    sha256: str

    def record(self) -> dict[str, int | str]:
        return {
            "path": self.path,
            "kind": self.kind,
            "mode": self.mode,
            "uid": self.uid,
            "gid": self.gid,
            "bytes": self.bytes,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class _CMakeSourceSnapshot:
    bindings: tuple[_CMakeBinding, ...]
    contents: Mapping[str, bytes]
    identity_sha256: str
    total_file_bytes: int


@dataclass(frozen=True)
class _CMakeRuntimeBundle:
    cache_root: Path
    prefix: Path
    executable: Path
    source_prefix: Path
    source_identity_sha256: str
    source_bindings: tuple[_CMakeBinding, ...]
    manifest_bytes: bytes
    manifest_sha256: str


@dataclass(frozen=True)
class _VerifiedEvidenceArtifact:
    unit_id: str
    role: str
    source_path: str
    assembled_path: str
    content: bytes

    @property
    def sha256(self) -> str:
        return "sha256:" + hashlib.sha256(self.content).hexdigest()

    def record(self) -> dict[str, object]:
        return {
            "unit_id": self.unit_id,
            "role": self.role,
            "source_path": self.source_path,
            "assembled_path": self.assembled_path,
            "bytes": len(self.content),
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class _VerifiedUnitEvidence:
    report: dict[str, Any]
    artifacts: tuple[_VerifiedEvidenceArtifact, ...]
    unit_namespace: IdentifierUnitNamespace


_CMAKE_RUNTIME_LOCK = threading.Lock()
_CMAKE_RUNTIME: _CMakeRuntimeBundle | None = None

_UNIT_ID_PATTERN = re.compile(r"^WU-[0-9]{5}(?:-F[0-9]{3})?$")
_RAW_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

_BUILD_FILES: dict[Language, tuple[str, ...]] = {
    "java": ("pom.xml",),
    "csharp": ("polyglot-migrated-library.csproj",),
    "python": ("pyproject.toml",),
    "typescript": ("package.json", "tsconfig.json"),
    "javascript": ("package.json",),
    "go": ("go.mod",),
    "rust": ("Cargo.toml", "src/lib.rs"),
    "cpp": ("CMakeLists.txt",),
    "objc": ("CMakeLists.txt",),
    "swift": ("Package.swift",),
    "php": ("composer.json",),
}

_SOURCE_LAYOUTS: dict[Language, tuple[str, str, frozenset[str]]] = {
    "java": ("src/main/java", ".java", frozenset()),
    "csharp": ("src/Units", ".cs", frozenset()),
    "python": ("src/elmos_generated", ".py", frozenset({"src/elmos_generated/__init__.py"})),
    "typescript": ("src/generated", ".ts", frozenset()),
    "javascript": ("src/generated", ".mjs", frozenset()),
    "go": ("units", ".go", frozenset()),
    "rust": ("src", ".rs", frozenset({"src/lib.rs"})),
    "cpp": ("src", ".cpp", frozenset()),
    "objc": ("src", ".m", frozenset()),
    "swift": ("Sources", ".swift", frozenset()),
    "php": ("src", ".php", frozenset()),
}

# These generated source files participate in the whole-project compiler input
# but are not one converted unit.  Rust's ``src/lib.rs`` is already included in
# ``_BUILD_FILES`` because Cargo.toml names it as the library entry point.
_AUXILIARY_BUILD_INPUTS: dict[Language, tuple[str, ...]] = {
    "python": ("src/elmos_generated/__init__.py",),
}


def _safe_unit_id(unit_id: str) -> str:
    if not _UNIT_ID_PATTERN.fullmatch(unit_id):
        raise RouteError(f"ASSEMBLY_UNIT_ID_UNSAFE:{unit_id}")
    return unit_id


def _namespace(unit_id: str) -> str:
    # "WU-00001" -> "wu00001". Stable and filesystem/identifier-safe. Discovery
    # assigns each unit a unique sequential id (repository.py's plan_repository),
    # so namespaces derived from it are collision-free by construction.
    return unit_id.lower().replace("-", "")


def _read_verified_unit_source(batch_output: Path, unit: dict[str, Any]) -> str:
    """Read one PASSED unit's already-emitted file, re-verifying its recorded sha256.

    This is defense in depth, not the primary trust boundary: `run_batch`
    already proved the content by compiling and executing it. Re-hashing here
    only guards against the batch output directory having been altered or
    gone stale between the batch run and this assembly run.
    """
    unit_id = _safe_unit_id(str(unit.get("id", "")))
    target_path = str(unit.get("target_path", ""))
    if not target_path or "/" in target_path or "\\" in target_path:
        raise RouteError(f"ASSEMBLY_UNIT_TARGET_PATH_INVALID:{unit_id}")
    batch_root = batch_output.resolve(strict=True)
    units_root = batch_root / "units"
    raw_unit_directory = units_root / unit_id
    raw_source_file = raw_unit_directory / target_path
    # Check the unresolved path components before ``resolve``.  Calling
    # ``is_symlink`` only after resolution loses the evidence that a child was
    # a link and could let a tampered batch directory redirect assembly reads
    # outside the content-addressed output tree.
    if (
        units_root.is_symlink()
        or not units_root.is_dir()
        or raw_unit_directory.is_symlink()
        or not raw_unit_directory.is_dir()
        or raw_source_file.is_symlink()
        or not raw_source_file.is_file()
    ):
        raise RouteError(f"ASSEMBLY_UNIT_SOURCE_MISSING:{unit_id}")
    unit_directory = raw_unit_directory.resolve(strict=True)
    source_file = raw_source_file.resolve(strict=True)
    if unit_directory.parent != units_root.resolve(strict=True) or source_file.parent != unit_directory:
        raise RouteError(f"ASSEMBLY_UNIT_SOURCE_MISSING:{unit_id}")
    content = source_file.read_text(encoding="utf-8")
    expected = unit.get("target_sha256")
    if not isinstance(expected, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", expected):
        raise RouteError(f"ASSEMBLY_UNIT_TARGET_DIGEST_REQUIRED:{unit_id}")
    observed = "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
    if observed != expected:
        raise RouteError(f"ASSEMBLY_UNIT_CONTENT_DRIFTED:{unit_id}")
    return content


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _json_object(content: bytes, error_code: str) -> dict[str, Any]:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    try:
        value = json.loads(content, object_pairs_hook=reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise RouteError(error_code) from error
    if not isinstance(value, dict):
        raise RouteError(error_code)
    return value


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], error_code: str) -> None:
    if set(value) != expected:
        raise RouteError(error_code)


def _read_confined_stable_bytes(
    root: Path,
    relative: str,
    *,
    missing_code: str,
    changed_code: str,
) -> bytes:
    """Read a regular confined file through a no-follow descriptor and rebind its path."""

    path = _confined_regular_file(root, relative, missing_code)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise RouteError(missing_code) from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise RouteError(missing_code)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
    except OSError as error:
        raise RouteError(changed_code) from error
    finally:
        os.close(descriptor)
    content = b"".join(chunks)
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_nlink,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_nlink,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    rebound = _confined_regular_file(root, relative, missing_code)
    current = rebound.stat(follow_symlinks=False)
    if (
        identity_before != identity_after
        or (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino)
        or not stat.S_ISREG(current.st_mode)
        or len(content) != before.st_size
    ):
        raise RouteError(changed_code)
    return content


def _strict_json_value(content: str, error_code: str) -> object:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def reject_non_finite(constant: str) -> object:
        raise ValueError(f"non-finite JSON constant: {constant}")

    try:
        return json.loads(
            content,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_non_finite,
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise RouteError(error_code) from error


def _decoded_text_observation(raw: str, value: object, error_code: str) -> object:
    if type(value) is bool:
        if raw.lower() not in {"true", "false"}:
            raise RouteError(error_code)
        return raw.lower() == "true"
    if type(value) is int:
        if re.fullmatch(r"-?(?:0|[1-9][0-9]*)", raw) is None:
            raise RouteError(error_code)
        return int(raw)
    if type(value) is float:
        try:
            decoded = float(raw)
        except ValueError as error:
            raise RouteError(error_code) from error
        if not math.isfinite(decoded):
            raise RouteError(error_code)
        return decoded
    if isinstance(value, str):
        return raw
    raise RouteError(error_code)


def _validate_observation_raw(observation: Mapping[str, Any], error_code: str) -> None:
    case_id = observation["case_id"]
    encoding = observation["encoding"]
    raw = observation["raw"]
    value = observation["value"]
    assert isinstance(case_id, int)
    assert isinstance(encoding, str)
    assert isinstance(raw, str)
    decoded: object
    if encoding == "json":
        payload = _strict_json_value(raw, error_code)
        if not isinstance(payload, Mapping) or set(payload) != {"case_id", "value"}:
            raise RouteError(error_code)
        if type(payload.get("case_id")) is not int or payload.get("case_id") != case_id:
            raise RouteError(error_code)
        decoded = payload.get("value")
    elif encoding == "i64-dec":
        if re.fullmatch(r"-?(?:0|[1-9][0-9]*)", raw) is None:
            raise RouteError(error_code)
        decoded = int(raw)
        if not -(2**63) <= decoded <= 2**63 - 1:
            raise RouteError(error_code)
    elif encoding == "fp64-hex":
        if re.fullmatch(r"[0-9a-f]{16}", raw) is None:
            raise RouteError(error_code)
        if type(value) not in {int, float}:
            raise RouteError(error_code)
        if isinstance(value, int):
            numeric_value = float(value)
        elif isinstance(value, float):
            numeric_value = float(value)
        else:
            raise RouteError(error_code)
        fp64_decoded = struct.unpack(">d", bytes.fromhex(raw))[0]
        if not math.isfinite(fp64_decoded) or not math.isfinite(numeric_value):
            raise RouteError(error_code)
        if struct.pack(">d", fp64_decoded) != struct.pack(">d", numeric_value):
            raise RouteError(error_code)
        return
    elif encoding == "bool":
        if raw not in {"true", "false"}:
            raise RouteError(error_code)
        decoded = raw == "true"
    elif encoding == "hex-utf8":
        if re.fullmatch(r"(?:[0-9a-f]{2})*", raw) is None:
            raise RouteError(error_code)
        try:
            decoded = bytes.fromhex(raw).decode("utf-8")
        except UnicodeDecodeError as error:
            raise RouteError(error_code) from error
    elif encoding == "b64":
        try:
            text = base64.b64decode(raw, validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as error:
            raise RouteError(error_code) from error
        decoded = _decoded_text_observation(text, value, error_code)
    elif encoding == "rust-debug":
        if isinstance(value, str):
            decoded = _strict_json_value(raw, error_code)
            if not isinstance(decoded, str):
                raise RouteError(error_code)
        else:
            decoded = _decoded_text_observation(raw, value, error_code)
    else:
        raise RouteError(error_code)
    if _canonical_json_bytes(decoded) != _canonical_json_bytes(value):
        raise RouteError(error_code)


def _observation_sequence(value: object, case_count: int, error_code: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) != case_count:
        raise RouteError(error_code)
    observations: list[dict[str, Any]] = []
    for case_id, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise RouteError(error_code)
        _require_exact_keys(raw, {"case_id", "status", "value", "encoding", "raw"}, error_code)
        if (
            type(raw.get("case_id")) is not int
            or raw.get("case_id") != case_id
            or raw.get("status") != "RETURNED"
            or not isinstance(raw.get("encoding"), str)
            or not raw["encoding"]
            or not isinstance(raw.get("raw"), str)
        ):
            raise RouteError(error_code)
        _validate_observation_raw(raw, error_code)
        observations.append(raw)
    return observations


def _logical_descriptor_path(source_path: str, logical_path: str, error_code: str) -> str:
    source = PurePosixPath(source_path)
    logical = PurePosixPath(logical_path)
    if (
        not source_path
        or source.is_absolute()
        or ".." in source.parts
        or "\\" in source_path
        or source.as_posix() != source_path
        or logical.is_absolute()
        or "\\" in logical_path
        or logical.as_posix() != logical_path
    ):
        raise RouteError(error_code)
    resolved = list(source.parent.parts)
    for part in logical.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if not resolved:
                raise RouteError(error_code)
            resolved.pop()
        else:
            resolved.append(part)
    if not resolved or resolved[-1] != "package.json":
        raise RouteError(error_code)
    return PurePosixPath(*resolved).as_posix()


def _validate_behavior_and_descriptor_closure(
    evidence: Mapping[str, Any],
    behavior_content: bytes,
    descriptor_content: bytes | None,
    *,
    unit_id: str,
    source_language: Language,
    source_path: str,
) -> None:
    error_code = f"ASSEMBLY_UNIT_BEHAVIOR_EVIDENCE_INVALID:{unit_id}"
    case_count = evidence.get("behavior_case_count")
    source_validation = evidence.get("source_validation")
    target_validation = evidence.get("validation")
    reference = evidence.get("behavior_equivalence")
    if (
        type(case_count) is not int
        or case_count < 1
        or not isinstance(source_validation, Mapping)
        or not isinstance(target_validation, Mapping)
        or not isinstance(reference, Mapping)
    ):
        raise RouteError(error_code)
    _require_exact_keys(
        reference,
        {
            "status",
            "case_count",
            "pass_count",
            "source_runtime_passed",
            "target_runtime_passed",
            "oracle_conflict_count",
            "artifact_path",
            "artifact_sha256",
        },
        error_code,
    )
    behavior_sha256 = "sha256:" + hashlib.sha256(behavior_content).hexdigest()
    if (
        reference.get("status") != "PASSED"
        or reference.get("case_count") != case_count
        or reference.get("pass_count") != case_count
        or reference.get("source_runtime_passed") is not True
        or reference.get("target_runtime_passed") is not True
        or reference.get("oracle_conflict_count") != 0
        or reference.get("artifact_path") != _BEHAVIOR_EVIDENCE_NAME
        or reference.get("artifact_sha256") != behavior_sha256
    ):
        raise RouteError(error_code)

    source_observations = _observation_sequence(source_validation.get("observations"), case_count, error_code)
    target_observations = _observation_sequence(target_validation.get("observations"), case_count, error_code)
    behavior = _json_object(behavior_content, error_code)
    _require_exact_keys(
        behavior,
        {
            "schema_version",
            "kind",
            "status",
            "case_count",
            "pass_count",
            "source_runtime_pass_count",
            "target_runtime_pass_count",
            "source_runtime_passed",
            "target_runtime_passed",
            "oracle_conflict_count",
            "counterexample_count",
            "results",
            "counterexamples",
        },
        error_code,
    )
    results = behavior.get("results")
    if (
        behavior.get("schema_version") != SCHEMA_VERSION
        or behavior.get("kind") != "elmos.behavior-equivalence"
        or behavior.get("status") != "PASSED"
        or behavior.get("case_count") != case_count
        or behavior.get("pass_count") != case_count
        or behavior.get("source_runtime_pass_count") != case_count
        or behavior.get("target_runtime_pass_count") != case_count
        or behavior.get("source_runtime_passed") is not True
        or behavior.get("target_runtime_passed") is not True
        or behavior.get("oracle_conflict_count") != 0
        or behavior.get("counterexample_count") != 0
        or behavior.get("counterexamples") != []
        or not isinstance(results, list)
        or len(results) != case_count
    ):
        raise RouteError(error_code)
    for case_id, result in enumerate(results):
        if not isinstance(result, Mapping):
            raise RouteError(error_code)
        _require_exact_keys(
            result,
            {
                "case_id",
                "arguments_sha256",
                "canonical",
                "source_native",
                "target_native",
                "independent_expected",
                "status",
            },
            error_code,
        )
        canonical = result.get("canonical")
        arguments_sha256 = result.get("arguments_sha256")
        if not isinstance(canonical, Mapping):
            raise RouteError(error_code)
        _require_exact_keys(canonical, {"status", "value", "error"}, error_code)
        canonical_value = _canonical_json_bytes(canonical.get("value"))
        if (
            result.get("case_id") != case_id
            or not isinstance(arguments_sha256, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", arguments_sha256) is None
            or canonical.get("status") != "RETURNED"
            or canonical.get("error") is not None
            or result.get("status") != "PASSED"
            or canonical_value != _canonical_json_bytes(result.get("independent_expected"))
            or canonical_value != _canonical_json_bytes(source_observations[case_id].get("value"))
            or canonical_value != _canonical_json_bytes(target_observations[case_id].get("value"))
            or _canonical_json_bytes(result.get("source_native"))
            != _canonical_json_bytes(source_observations[case_id])
            or _canonical_json_bytes(result.get("target_native"))
            != _canonical_json_bytes(target_observations[case_id])
        ):
            raise RouteError(error_code)

    descriptor_expected = (
        source_language == "javascript" and PurePosixPath(source_path).suffix.lower() == ".js"
    )
    descriptor_keys = {
        "logical_path",
        "snapshot_path",
        "artifact_path",
        "sha256",
        "bytes",
        "type",
    }
    source = evidence.get("source")
    if not isinstance(source, Mapping):
        raise RouteError(f"ASSEMBLY_UNIT_EVIDENCE_NOT_CLOSED:{unit_id}")
    if not descriptor_expected:
        if (
            descriptor_content is not None
            or "javascript_esm_descriptor" in evidence
            or "javascript_esm_descriptor_observation" in evidence
            or "javascript_esm_descriptor" in source
            or "javascript_esm_descriptor" in source_validation
            or "javascript_esm_descriptor_observation" in source_validation
        ):
            raise RouteError(f"ASSEMBLY_UNIT_JAVASCRIPT_ESM_DESCRIPTOR_UNEXPECTED:{unit_id}")
        return

    descriptor = evidence.get("javascript_esm_descriptor")
    top_observation = evidence.get("javascript_esm_descriptor_observation")
    source_descriptor = source.get("javascript_esm_descriptor")
    validation_descriptor = source_validation.get("javascript_esm_descriptor")
    validation_observation = source_validation.get("javascript_esm_descriptor_observation")
    descriptor_error = f"ASSEMBLY_UNIT_JAVASCRIPT_ESM_DESCRIPTOR_INVALID:{unit_id}"
    if descriptor_content is None or not isinstance(descriptor, Mapping):
        raise RouteError(descriptor_error)
    _require_exact_keys(descriptor, descriptor_keys, descriptor_error)
    logical_path = descriptor.get("logical_path")
    if not isinstance(logical_path, str):
        raise RouteError(descriptor_error)
    _logical_descriptor_path(source_path, logical_path, descriptor_error)
    stable_descriptor = {
        key: descriptor[key] for key in ("logical_path", "sha256", "bytes", "type")
    }
    observed_origin_path = (
        top_observation.get("observed_origin_path")
        if isinstance(top_observation, Mapping)
        else None
    )
    validation_origin_path = (
        validation_observation.get("observed_origin_path")
        if isinstance(validation_observation, Mapping)
        else None
    )
    if (
        descriptor.get("snapshot_path") != "source/package.json"
        or descriptor.get("artifact_path") != _JAVASCRIPT_ESM_DESCRIPTOR_NAME
        or not isinstance(descriptor.get("sha256"), str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", descriptor["sha256"]) is None
        or type(descriptor.get("bytes")) is not int
        or descriptor["bytes"] < 1
        or descriptor.get("type") != "module"
        or descriptor["bytes"] != len(descriptor_content)
        or descriptor["sha256"] != "sha256:" + hashlib.sha256(descriptor_content).hexdigest()
        or source_descriptor != descriptor
        or validation_descriptor != stable_descriptor
        or not isinstance(top_observation, Mapping)
        or set(top_observation) != {"observed_origin_path"}
        or not isinstance(observed_origin_path, str)
        or not observed_origin_path
        or not isinstance(validation_observation, Mapping)
        or set(validation_observation) != {"observed_origin_path"}
        or validation_origin_path != observed_origin_path
        or not PurePosixPath(observed_origin_path).is_absolute()
        or PurePosixPath(observed_origin_path).name != "package.json"
    ):
        raise RouteError(descriptor_error)
    package = _json_object(descriptor_content, descriptor_error)
    if package.get("type") != "module":
        raise RouteError(descriptor_error)


def _verified_artifact(
    unit_id: str,
    role: str,
    filename: str,
    content: bytes,
) -> _VerifiedEvidenceArtifact:
    return _VerifiedEvidenceArtifact(
        unit_id=unit_id,
        role=role,
        source_path=f"units/{unit_id}/{filename}",
        assembled_path=f"{_EVIDENCE_ROOT}/{unit_id}/{filename}",
        content=content,
    )


def _expected_repository_unit_namespace(
    *,
    repository_snapshot_sha256: str,
    unit_id: str,
    source_path: str,
    source_sha256: str,
    error_code: str,
) -> IdentifierUnitNamespace:
    if (
        _RAW_SHA256_PATTERN.fullmatch(repository_snapshot_sha256) is None
        or _RAW_SHA256_PATTERN.fullmatch(source_sha256) is None
    ):
        raise RouteError(error_code)
    try:
        return repository_work_unit_namespace(
            repository_snapshot_sha256="sha256:" + repository_snapshot_sha256,
            work_unit_id=_safe_unit_id(unit_id),
            source_logical_path=source_path,
            source_sha256="sha256:" + source_sha256,
        )
    except RouteError as error:
        raise RouteError(error_code) from error


def _batch_unit_namespace(
    unit: Mapping[str, Any],
    repository_snapshot_sha256: str,
) -> IdentifierUnitNamespace:
    unit_id = _safe_unit_id(str(unit.get("id", "")))
    source_path = unit.get("source_path")
    checkpoint = unit.get("checkpoint_identity")
    error_code = f"ASSEMBLY_UNIT_IDENTIFIER_NAMESPACE_INVALID:{unit_id}"
    if not isinstance(source_path, str) or not isinstance(checkpoint, Mapping):
        raise RouteError(error_code)
    source_sha256 = checkpoint.get("source_sha256")
    if not isinstance(source_sha256, str):
        raise RouteError(error_code)
    expected = _expected_repository_unit_namespace(
        repository_snapshot_sha256=repository_snapshot_sha256,
        unit_id=unit_id,
        source_path=source_path,
        source_sha256=source_sha256,
        error_code=error_code,
    )
    expected_mapping = expected.to_mapping()
    if (
        checkpoint.get("snapshot_sha256") != repository_snapshot_sha256
        or checkpoint.get("source_path") != source_path
        or checkpoint.get("function_name") != unit.get("function_name")
        or checkpoint.get("verdict") != "READY"
        or checkpoint.get("identifier_unit_namespace") != expected_mapping
        or checkpoint.get("identifier_unit_namespace_sha256") != expected.digest
        or unit.get("identifier_unit_namespace") != expected_mapping
        or unit.get("identifier_unit_namespace_sha256") != expected.digest
    ):
        raise RouteError(error_code)
    return expected


def _read_verified_unit_evidence(
    batch_output: Path,
    unit: dict[str, Any],
    source_language: Language,
    repository_snapshot_sha256: str,
    target_content: bytes,
) -> _VerifiedUnitEvidence:
    """Validate and retain the persisted behavior-evidence closure for one PASSED unit."""

    unit_id = _safe_unit_id(str(unit.get("id", "")))
    unit_namespace = _batch_unit_namespace(unit, repository_snapshot_sha256)
    expected_path = f"units/{unit_id}/{_ROUTE_EVIDENCE_NAME}"
    evidence_path = unit.get("evidence_path")
    expected_digest = unit.get("evidence_sha256")
    if evidence_path != expected_path:
        raise RouteError(f"ASSEMBLY_UNIT_EVIDENCE_PATH_INVALID:{unit_id}")
    if not isinstance(expected_digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", expected_digest):
        raise RouteError(f"ASSEMBLY_UNIT_EVIDENCE_DIGEST_REQUIRED:{unit_id}")
    units_root = batch_output / "units"
    unit_directory = units_root / unit_id
    if (
        units_root.is_symlink()
        or not units_root.is_dir()
        or unit_directory.is_symlink()
        or not unit_directory.is_dir()
        or unit_directory.resolve(strict=True).parent != units_root.resolve(strict=True)
    ):
        raise RouteError(f"ASSEMBLY_UNIT_EVIDENCE_MISSING:{unit_id}")
    evidence_bytes = _read_confined_stable_bytes(
        unit_directory,
        _ROUTE_EVIDENCE_NAME,
        missing_code=f"ASSEMBLY_UNIT_EVIDENCE_MISSING:{unit_id}",
        changed_code=f"ASSEMBLY_UNIT_EVIDENCE_CHANGED_DURING_READ:{unit_id}",
    )
    if "sha256:" + hashlib.sha256(evidence_bytes).hexdigest() != expected_digest:
        raise RouteError(f"ASSEMBLY_UNIT_EVIDENCE_DRIFTED:{unit_id}")
    evidence = _json_object(evidence_bytes, f"ASSEMBLY_UNIT_EVIDENCE_INVALID:{unit_id}")

    case_count = unit.get("behavior_case_count")
    source_path = unit.get("source_path")
    source = evidence.get("source")
    target = evidence.get("target")
    identifier_hygiene = evidence.get("identifier_hygiene")
    source_validation = evidence.get("source_validation")
    target_validation = evidence.get("validation")
    if (
        evidence.get("status") not in {"PASSED", "PASSED_LOCAL_UNCERTIFIED"}
        or evidence.get("repository_execution_mode") is not True
        or not isinstance(case_count, int)
        or case_count < 1
        or evidence.get("behavior_case_count") != case_count
        or evidence.get("behavior_pass_rate") != 1.0
        or not isinstance(source_path, str)
        or not isinstance(source, Mapping)
        or source.get("path") != PurePosixPath(source_path).name
        or source.get("sha256") != unit_namespace.source_sha256
        or source.get("language") != source_language
        or source.get("function_name") != unit.get("function_name")
        or not isinstance(target, Mapping)
        or target.get("path") != unit.get("target_path")
        or target.get("sha256") != unit.get("target_sha256")
        or target.get("function_name") != unit.get("target_function_name")
        or not isinstance(identifier_hygiene, Mapping)
        or identifier_hygiene.get("status") != "PASSED"
        or identifier_hygiene.get("plan_path") != unit.get("identifier_plan_path")
        or identifier_hygiene.get("plan_sha256") != unit.get("identifier_plan_sha256")
        or identifier_hygiene.get("source_function_name") != unit.get("function_name")
        or identifier_hygiene.get("target_function_name") != unit.get("target_function_name")
        or identifier_hygiene.get("unit_namespace") != unit_namespace.to_mapping()
        or identifier_hygiene.get("unit_namespace_sha256") != unit_namespace.digest
        or not isinstance(source_validation, Mapping)
        or source_validation.get("status") != "PASSED"
        or source_validation.get("case_count") != case_count
        or not isinstance(target_validation, Mapping)
        or target_validation.get("status") != "PASSED"
        or target_validation.get("case_count") != case_count
    ):
        raise RouteError(f"ASSEMBLY_UNIT_EVIDENCE_NOT_CLOSED:{unit_id}")

    behavior_reference = evidence.get("behavior_equivalence")
    if (
        not isinstance(behavior_reference, Mapping)
        or behavior_reference.get("artifact_path") != _BEHAVIOR_EVIDENCE_NAME
    ):
        raise RouteError(f"ASSEMBLY_UNIT_BEHAVIOR_EVIDENCE_INVALID:{unit_id}")
    behavior_bytes = _read_confined_stable_bytes(
        unit_directory,
        _BEHAVIOR_EVIDENCE_NAME,
        missing_code=f"ASSEMBLY_UNIT_BEHAVIOR_EVIDENCE_MISSING:{unit_id}",
        changed_code=f"ASSEMBLY_UNIT_BEHAVIOR_EVIDENCE_CHANGED_DURING_READ:{unit_id}",
    )
    descriptor_expected = (
        source_language == "javascript" and PurePosixPath(source_path).suffix.lower() == ".js"
    )
    descriptor_candidate = unit_directory / _JAVASCRIPT_ESM_DESCRIPTOR_NAME
    descriptor_bytes: bytes | None = None
    if descriptor_expected:
        descriptor_bytes = _read_confined_stable_bytes(
            unit_directory,
            _JAVASCRIPT_ESM_DESCRIPTOR_NAME,
            missing_code=f"ASSEMBLY_UNIT_JAVASCRIPT_ESM_DESCRIPTOR_MISSING:{unit_id}",
            changed_code=f"ASSEMBLY_UNIT_JAVASCRIPT_ESM_DESCRIPTOR_CHANGED_DURING_READ:{unit_id}",
        )
    elif descriptor_candidate.exists() or descriptor_candidate.is_symlink():
        raise RouteError(f"ASSEMBLY_UNIT_JAVASCRIPT_ESM_DESCRIPTOR_UNEXPECTED:{unit_id}")
    _validate_behavior_and_descriptor_closure(
        evidence,
        behavior_bytes,
        descriptor_bytes,
        unit_id=unit_id,
        source_language=source_language,
        source_path=source_path,
    )

    plan_bytes = _read_confined_stable_bytes(
        unit_directory,
        _IDENTIFIER_PLAN_NAME,
        missing_code=f"ASSEMBLY_UNIT_IDENTIFIER_EVIDENCE_MISSING:{unit_id}",
        changed_code=f"ASSEMBLY_UNIT_IDENTIFIER_EVIDENCE_CHANGED_DURING_READ:{unit_id}",
    )
    source_ir_bytes = _read_confined_stable_bytes(
        unit_directory,
        _SOURCE_SEMANTIC_IR_NAME,
        missing_code=f"ASSEMBLY_UNIT_IDENTIFIER_EVIDENCE_MISSING:{unit_id}",
        changed_code=f"ASSEMBLY_UNIT_IDENTIFIER_EVIDENCE_CHANGED_DURING_READ:{unit_id}",
    )
    observed_plan_sha256 = "sha256:" + hashlib.sha256(plan_bytes).hexdigest()
    if observed_plan_sha256 != unit.get("identifier_plan_sha256"):
        raise RouteError(f"ASSEMBLY_UNIT_IDENTIFIER_PLAN_DRIFTED:{unit_id}")
    plan_payload = _json_object(plan_bytes, f"ASSEMBLY_UNIT_IDENTIFIER_EVIDENCE_INVALID:{unit_id}")
    source_ir_payload = _json_object(source_ir_bytes, f"ASSEMBLY_UNIT_IDENTIFIER_EVIDENCE_INVALID:{unit_id}")
    plan = IdentifierPlan.from_mapping(plan_payload)
    source_ir = SemanticIR.from_mapping(source_ir_payload)
    validate_identifier_plan(source_ir, plan, expected_unit_namespace=unit_namespace)
    if len(source_ir.functions) != 1:
        raise RouteError(f"ASSEMBLY_UNIT_IDENTIFIER_FUNCTION_SET_INVALID:{unit_id}")
    target_function = target_function_view(source_ir, source_ir.functions[0], plan)
    if (
        source_ir.functions[0].name != unit.get("function_name")
        or target_function.name != unit.get("target_function_name")
        or plan.target_language != target.get("language")
        or unit.get("identifier_plan_path") != _IDENTIFIER_PLAN_NAME
        or "sha256:" + hashlib.sha256(target_content).hexdigest() != unit.get("target_sha256")
    ):
        raise RouteError(f"ASSEMBLY_UNIT_IDENTIFIER_BINDING_MISMATCH:{unit_id}")
    artifacts = [
        _verified_artifact(unit_id, "route-evidence", _ROUTE_EVIDENCE_NAME, evidence_bytes),
        _verified_artifact(unit_id, "behavior-equivalence", _BEHAVIOR_EVIDENCE_NAME, behavior_bytes),
        _verified_artifact(unit_id, "source-semantic-ir", _SOURCE_SEMANTIC_IR_NAME, source_ir_bytes),
        _verified_artifact(unit_id, "identifier-plan", _IDENTIFIER_PLAN_NAME, plan_bytes),
        _VerifiedEvidenceArtifact(
            unit_id=unit_id,
            role="emitted-target",
            source_path=f"units/{unit_id}/{unit.get('target_path')}",
            assembled_path=f"{_EVIDENCE_ROOT}/{unit_id}/{unit.get('target_path')}",
            content=target_content,
        ),
    ]
    if descriptor_bytes is not None:
        artifacts.append(
            _verified_artifact(
                unit_id,
                "source-javascript-esm-descriptor",
                _JAVASCRIPT_ESM_DESCRIPTOR_NAME,
                descriptor_bytes,
            )
        )
    return _VerifiedUnitEvidence(
        report=evidence,
        artifacts=tuple(artifacts),
        unit_namespace=unit_namespace,
    )


def _validate_batch_report_closure(batch_report: dict[str, Any]) -> None:
    units = batch_report.get("units")
    snapshot_sha256 = batch_report.get("snapshot_sha256")
    if (
        not isinstance(units, list)
        or not units
        or not isinstance(snapshot_sha256, str)
        or _RAW_SHA256_PATTERN.fullmatch(snapshot_sha256) is None
    ):
        raise RouteError("ASSEMBLY_BATCH_REPORT_UNITS_REQUIRED")
    statuses = [unit.get("status") for unit in units if isinstance(unit, dict)]
    allowed = {"PASSED", "FAILED", "SKIPPED_NOT_READY", "SKIPPED_NO_CASES"}
    if len(statuses) != len(units) or any(status not in allowed for status in statuses):
        raise RouteError("ASSEMBLY_BATCH_STATUS_COUNTS_INVALID")
    observed_counts = {status: statuses.count(status) for status in allowed if status in statuses}
    work_unit_count = batch_report.get("work_unit_count")
    selected_count = batch_report.get("selected_count")
    attempted_count = batch_report.get("attempted_count")
    unattempted_count = batch_report.get("unattempted_count")
    if (
        not isinstance(work_unit_count, int)
        or not isinstance(selected_count, int)
        or work_unit_count < 1
        or selected_count != len(units)
        or selected_count > work_unit_count
        or batch_report.get("status_counts") != observed_counts
        or attempted_count != observed_counts.get("PASSED", 0) + observed_counts.get("FAILED", 0)
        or unattempted_count != work_unit_count - attempted_count
    ):
        raise RouteError("ASSEMBLY_BATCH_STATUS_COUNTS_INVALID")
    complete = selected_count == work_unit_count and observed_counts == {"PASSED": work_unit_count}
    if batch_report.get("status") != ("COMPLETE" if complete else "PARTIAL"):
        raise RouteError("ASSEMBLY_BATCH_STATUS_CLOSURE_INVALID")


def _place_java(destination: Path, namespace: str, content: str) -> str:
    relative = f"src/main/java/elmos/generated/{namespace}/Migrated.java"
    target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"package elmos.generated.{namespace};\n\n{content}", encoding="utf-8")
    return relative


def _place_csharp(destination: Path, namespace: str, content: str) -> str:
    relative = f"src/Units/{namespace}/Migrated.cs"
    target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    pascal_namespace = namespace.capitalize()
    target.write_text(f"namespace Elmos.Generated.{pascal_namespace};\n\n{content}", encoding="utf-8")
    return relative


def _place_python(destination: Path, namespace: str, content: str) -> str:
    package_directory = destination / "src" / "elmos_generated"
    package_directory.mkdir(parents=True, exist_ok=True)
    init_file = package_directory / "__init__.py"
    if not init_file.exists():
        init_file.write_text("", encoding="utf-8")
    relative = f"src/elmos_generated/{namespace}.py"
    (destination / relative).write_text(content, encoding="utf-8")
    return relative


def _place_typescript(destination: Path, namespace: str, content: str) -> str:
    relative = f"src/generated/{namespace}.ts"
    target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return relative


def _place_javascript(destination: Path, namespace: str, content: str) -> str:
    relative = f"src/generated/{namespace}.mjs"
    target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return relative


def _place_go(destination: Path, namespace: str, content: str) -> str:
    if not content.startswith("package main\n"):
        raise RouteError(f"ASSEMBLY_GO_PACKAGE_DECLARATION_INVALID:{namespace}")
    relative = f"units/{namespace}/migrated.go"
    target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"package {namespace}\n" + content.removeprefix("package main\n"), encoding="utf-8")
    return relative


def _place_rust(destination: Path, namespace: str, content: str) -> str:
    relative = f"src/{namespace}.rs"
    target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return relative


def _place_cpp(destination: Path, namespace: str, content: str) -> str:
    relative = f"src/{namespace}/migrated.cpp"
    target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return relative


def _place_objc(destination: Path, namespace: str, content: str) -> str:
    relative = f"src/{namespace}/migrated.m"
    target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return relative


def _place_php(destination: Path, namespace: str, content: str) -> str:
    """Place one emitted PHP unit, giving it its own namespace.

    This is the same division of labour Java and C# already use: the emitted
    file carries no package or namespace, and the placer adds the one that
    matches where the file lands. For PHP it is not a style choice but the only
    thing that makes a multi-unit project loadable at all -- a `function` at
    file scope is unconditionally global, so two units that both need
    `elmos_checked_add` would otherwise be a fatal "Cannot redeclare function"
    the moment Composer autoloads the second one. Directory placement, which
    isolates every other target (a Go package, a Rust module, a C++ translation
    unit, a Java package), buys PHP nothing on its own.

    The namespace has to go *after* `declare(strict_types=1);`: the declare must
    be the first statement in the file, and the namespace must be the first
    statement except for a declare. Unqualified calls inside the namespace still
    fall back to the global namespace, so `fmod` and `intdiv` keep resolving.
    """
    relative = f"src/{namespace}/migrated.php"
    target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    declaration = "declare(strict_types=1);\n"
    if declaration not in content:
        raise RouteError("ASSEMBLY_PHP_STRICT_TYPES_DECLARATION_MISSING")
    prefix, _, suffix = content.partition(declaration)
    namespaced = (
        f"{prefix}{declaration}\nnamespace Elmos\\Generated\\{namespace.capitalize()};\n{suffix}"
    )
    target.write_text(namespaced, encoding="utf-8")
    return relative


def _place_swift(destination: Path, namespace: str, content: str) -> str:
    module = namespace.capitalize()
    relative = f"Sources/{module}/migrated.swift"
    target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return relative


_PLACERS = {
    "java": _place_java,
    "csharp": _place_csharp,
    "python": _place_python,
    "typescript": _place_typescript,
    "javascript": _place_javascript,
    "go": _place_go,
    "rust": _place_rust,
    "cpp": _place_cpp,
    "objc": _place_objc,
    "swift": _place_swift,
    "php": _place_php,
}


def _expected_assembled_path(target_language: Language, namespace: str) -> str:
    paths = {
        "java": f"src/main/java/elmos/generated/{namespace}/Migrated.java",
        "csharp": f"src/Units/{namespace}/Migrated.cs",
        "python": f"src/elmos_generated/{namespace}.py",
        "typescript": f"src/generated/{namespace}.ts",
        "javascript": f"src/generated/{namespace}.mjs",
        "go": f"units/{namespace}/migrated.go",
        "rust": f"src/{namespace}.rs",
        "cpp": f"src/{namespace}/migrated.cpp",
        "objc": f"src/{namespace}/migrated.m",
        "swift": f"Sources/{namespace.capitalize()}/migrated.swift",
        "php": f"src/{namespace}/migrated.php",
    }
    return paths[target_language]


def _confined_regular_file(root: Path, relative: str, error_code: str) -> Path:
    """Resolve one manifest-owned regular file without following a symlink."""

    pure = PurePosixPath(relative)
    if not relative or pure.is_absolute() or ".." in pure.parts or "\\" in relative or pure.as_posix() != relative:
        raise RouteError(error_code)
    raw = root.joinpath(*pure.parts)
    cursor = root
    for part in pure.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise RouteError(error_code)
    if not raw.is_file():
        raise RouteError(error_code)
    resolved_root = root.resolve(strict=True)
    resolved = raw.resolve(strict=True)
    if resolved_root not in resolved.parents:
        raise RouteError(error_code)
    return raw


def _stable_file_bytes(path: Path, error_code: str) -> bytes:
    before = path.stat(follow_symlinks=False)
    content = path.read_bytes()
    after = path.stat(follow_symlinks=False)
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or before.st_ctime_ns != after.st_ctime_ns
        or len(content) != before.st_size
    ):
        raise RouteError(error_code)
    return content


def _stable_file_binding(path: Path, error_code: str) -> tuple[int, str]:
    content = _stable_file_bytes(path, error_code)
    return len(content), "sha256:" + hashlib.sha256(content).hexdigest()


def _assembled_source_paths(destination: Path, target_language: Language) -> set[str]:
    root_name, suffix, auxiliary = _SOURCE_LAYOUTS[target_language]
    source_root = destination / root_name
    if source_root.is_symlink() or not source_root.is_dir():
        raise RouteError("ASSEMBLY_SOURCE_TREE_UNSAFE")
    paths: set[str] = set()
    for current, directories, files in os.walk(source_root, topdown=True, followlinks=False):
        current_path = Path(current)
        for directory in directories:
            if (current_path / directory).is_symlink():
                raise RouteError("ASSEMBLY_SOURCE_TREE_UNSAFE")
        for name in files:
            candidate = current_path / name
            if candidate.suffix != suffix:
                continue
            if candidate.is_symlink() or not candidate.is_file():
                raise RouteError("ASSEMBLY_SOURCE_TREE_UNSAFE")
            relative = candidate.relative_to(destination).as_posix()
            if relative not in auxiliary:
                paths.add(relative)
    return paths


def _expected_build_input_paths(target_language: Language, source_paths: Collection[str]) -> list[str]:
    return sorted(
        {
            *source_paths,
            *_BUILD_FILES[target_language],
            *_AUXILIARY_BUILD_INPUTS.get(target_language, ()),
        }
    )


def _assembled_evidence_paths(destination: Path) -> set[str]:
    evidence_root = destination / _EVIDENCE_ROOT
    if evidence_root.is_symlink() or not evidence_root.is_dir():
        raise RouteError("ASSEMBLY_EVIDENCE_TREE_UNSAFE")
    paths: set[str] = set()
    for current, directories, files in os.walk(evidence_root, topdown=True, followlinks=False):
        current_path = Path(current)
        for directory in directories:
            if (current_path / directory).is_symlink():
                raise RouteError("ASSEMBLY_EVIDENCE_TREE_UNSAFE")
        for name in files:
            candidate = current_path / name
            if candidate.is_symlink() or not candidate.is_file():
                raise RouteError("ASSEMBLY_EVIDENCE_TREE_UNSAFE")
            paths.add(candidate.relative_to(destination).as_posix())
    return paths


def _validate_bound_evidence_contents(
    contents: Mapping[str, bytes],
    *,
    unit_id: str,
    source_language: Language,
    repository_snapshot_sha256: str,
    included_unit: Mapping[str, Any],
) -> None:
    source_path = included_unit.get("source_path")
    source_sha256 = included_unit.get("source_sha256")
    function_name = included_unit.get("function_name")
    target_function_name = included_unit.get("target_function_name")
    target_path = included_unit.get("target_path")
    target_sha256 = included_unit.get("target_sha256")
    identifier_plan_path = included_unit.get("identifier_plan_path")
    identifier_plan_sha256 = included_unit.get("identifier_plan_sha256")
    if (
        not isinstance(source_path, str)
        or not isinstance(source_sha256, str)
        or not isinstance(function_name, str)
        or not isinstance(target_function_name, str)
        or not isinstance(target_path, str)
        or not isinstance(target_sha256, str)
        or identifier_plan_path != _IDENTIFIER_PLAN_NAME
        or not isinstance(identifier_plan_sha256, str)
    ):
        raise RouteError(f"ASSEMBLY_UNIT_IDENTIFIER_BINDING_MISMATCH:{unit_id}")
    expected_roles = {
        "route-evidence",
        "behavior-equivalence",
        "source-semantic-ir",
        "identifier-plan",
        "emitted-target",
    }
    if source_language == "javascript" and PurePosixPath(source_path).suffix.lower() == ".js":
        expected_roles.add("source-javascript-esm-descriptor")
    if set(contents) != expected_roles:
        raise RouteError(f"ASSEMBLY_UNIT_EVIDENCE_ROLE_SET_INVALID:{unit_id}")
    evidence = _json_object(
        contents["route-evidence"],
        f"ASSEMBLY_UNIT_EVIDENCE_INVALID:{unit_id}",
    )
    unit_namespace = _expected_repository_unit_namespace(
        repository_snapshot_sha256=repository_snapshot_sha256,
        unit_id=unit_id,
        source_path=source_path,
        source_sha256=source_sha256,
        error_code=f"ASSEMBLY_UNIT_IDENTIFIER_NAMESPACE_INVALID:{unit_id}",
    )
    source = evidence.get("source")
    target = evidence.get("target")
    identifier_hygiene = evidence.get("identifier_hygiene")
    if (
        not isinstance(source, Mapping)
        or source.get("path") != PurePosixPath(source_path).name
        or source.get("sha256") != unit_namespace.source_sha256
        or source.get("language") != source_language
        or source.get("function_name") != function_name
        or not isinstance(target, Mapping)
        or target.get("path") != target_path
        or target.get("sha256") != target_sha256
        or target.get("function_name") != target_function_name
        or not isinstance(identifier_hygiene, Mapping)
        or identifier_hygiene.get("status") != "PASSED"
        or identifier_hygiene.get("plan_path") != identifier_plan_path
        or identifier_hygiene.get("plan_sha256") != identifier_plan_sha256
        or identifier_hygiene.get("source_function_name") != function_name
        or identifier_hygiene.get("target_function_name") != target_function_name
        or identifier_hygiene.get("unit_namespace") != unit_namespace.to_mapping()
        or identifier_hygiene.get("unit_namespace_sha256") != unit_namespace.digest
    ):
        raise RouteError(f"ASSEMBLY_UNIT_IDENTIFIER_NAMESPACE_INVALID:{unit_id}")

    source_ir_content = contents["source-semantic-ir"]
    plan_content = contents["identifier-plan"]
    emitted_target = contents["emitted-target"]
    if (
        "sha256:" + hashlib.sha256(plan_content).hexdigest() != identifier_plan_sha256
        or "sha256:" + hashlib.sha256(emitted_target).hexdigest() != target_sha256
    ):
        raise RouteError(f"ASSEMBLY_UNIT_IDENTIFIER_BINDING_MISMATCH:{unit_id}")
    source_ir = SemanticIR.from_mapping(
        _json_object(source_ir_content, f"ASSEMBLY_UNIT_IDENTIFIER_EVIDENCE_INVALID:{unit_id}")
    )
    plan = IdentifierPlan.from_mapping(
        _json_object(plan_content, f"ASSEMBLY_UNIT_IDENTIFIER_EVIDENCE_INVALID:{unit_id}")
    )
    validate_identifier_plan(source_ir, plan, expected_unit_namespace=unit_namespace)
    if len(source_ir.functions) != 1:
        raise RouteError(f"ASSEMBLY_UNIT_IDENTIFIER_FUNCTION_SET_INVALID:{unit_id}")
    target_function = target_function_view(source_ir, source_ir.functions[0], plan)
    if (
        source_ir.source_language != source_language
        or source_ir.source_file != PurePosixPath(source_path).name
        or source_ir.functions[0].name != function_name
        or target_function.name != target_function_name
        or plan.target_language != target.get("language")
    ):
        raise RouteError(f"ASSEMBLY_UNIT_IDENTIFIER_BINDING_MISMATCH:{unit_id}")
    _validate_behavior_and_descriptor_closure(
        evidence,
        contents["behavior-equivalence"],
        contents.get("source-javascript-esm-descriptor"),
        unit_id=unit_id,
        source_language=source_language,
        source_path=source_path,
    )


def _validate_build_verification(
    manifest: Mapping[str, Any],
    target_language: Language,
    *,
    require_build_passed: bool,
) -> None:
    status = manifest.get("build_verification_status")
    if status not in {"NOT_RUN", "PASSED"}:
        raise RouteError("ASSEMBLY_BUILD_VERIFICATION_STATUS_INVALID")
    if status != "PASSED":
        if require_build_passed:
            raise RouteError("ASSEMBLY_BUILD_VERIFICATION_NOT_PASSED")
        return
    verification = manifest.get("build_verification")
    if not isinstance(verification, Mapping):
        raise RouteError("ASSEMBLY_BUILD_VERIFICATION_INVALID")
    commands = verification.get("commands")
    if (
        verification.get("toolchain_language") != target_language
        or not isinstance(verification.get("toolchain_version"), str)
        or not verification["toolchain_version"]
        or not isinstance(commands, list)
        or not commands
    ):
        raise RouteError("ASSEMBLY_BUILD_VERIFICATION_INVALID")
    for record in commands:
        if (
            not isinstance(record, Mapping)
            or not isinstance(record.get("command"), list)
            or not record["command"]
            or any(not isinstance(part, str) or not part for part in record["command"])
            or not isinstance(record.get("stdout"), str)
            or not isinstance(record.get("stderr"), str)
        ):
            raise RouteError("ASSEMBLY_BUILD_VERIFICATION_INVALID")
    cmake_runtime = verification.get("cmake_runtime")
    if target_language in {"cpp", "objc"}:
        if (
            not isinstance(cmake_runtime, Mapping)
            or cmake_runtime.get("kind") != "private-content-addressed-cmake-runtime-v1"
            or cmake_runtime.get("version") != _EXPECTED_CMAKE_VERSION
            or cmake_runtime.get("source_prefix") != str(_EXPECTED_CMAKE_PREFIX)
            or cmake_runtime.get("source_identity_sha256") != _EXPECTED_CMAKE_TREE_SHA256
            or cmake_runtime.get("source_entry_count") != _EXPECTED_CMAKE_TREE_ENTRY_COUNT
            or cmake_runtime.get("source_total_file_bytes") != _EXPECTED_CMAKE_TREE_FILE_BYTES
            or cmake_runtime.get("bundle_manifest_bytes") != _EXPECTED_CMAKE_RUNTIME_MANIFEST_BYTES
            or cmake_runtime.get("bundle_manifest_sha256") != _EXPECTED_CMAKE_RUNTIME_MANIFEST_SHA256
        ):
            raise RouteError("ASSEMBLY_CMAKE_RUNTIME_BINDING_INVALID")
    elif cmake_runtime is not None:
        raise RouteError("ASSEMBLY_CMAKE_RUNTIME_BINDING_UNEXPECTED")


def _manifest_owned_bindings(
    manifest: Mapping[str, Any],
    target_language: Language,
    *,
    require_build_passed: bool,
) -> tuple[
    dict[str, tuple[str, int, str]],
    dict[str, tuple[int, str]],
    dict[str, tuple[str, str, str, int, str]],
]:
    """Validate manifest structure and return its exact static build inputs."""

    included = manifest.get("included_units")
    excluded = manifest.get("excluded_units")
    build_inputs = manifest.get("build_inputs")
    evidence_artifacts = manifest.get("verified_evidence_artifacts")
    repository_snapshot_sha256 = manifest.get("snapshot_sha256")
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("kind") != "elmos.repository-assembly-report"
        or manifest.get("status") != "ASSEMBLED"
        or manifest.get("target_language") != target_language
        or target_language not in _PLACERS
        or manifest.get("source_language") not in _PLACERS
        or manifest.get("source_language") == target_language
        or not isinstance(repository_snapshot_sha256, str)
        or _RAW_SHA256_PATTERN.fullmatch(repository_snapshot_sha256) is None
        or not isinstance(included, list)
        or not included
        or not isinstance(excluded, list)
        or type(manifest.get("included_unit_count")) is not int
        or type(manifest.get("excluded_unit_count")) is not int
        or manifest.get("included_unit_count") != len(included)
        or manifest.get("excluded_unit_count") != len(excluded)
        or manifest.get("build_files") != list(_BUILD_FILES[target_language])
        or not isinstance(build_inputs, list)
        or type(manifest.get("build_input_count")) is not int
        or manifest.get("build_input_count") != len(build_inputs)
        or not isinstance(evidence_artifacts, list)
        or type(manifest.get("verified_evidence_artifact_count")) is not int
        or manifest.get("verified_evidence_artifact_count") != len(evidence_artifacts)
        or manifest.get("batch_status") not in {"COMPLETE", "PARTIAL"}
        or (manifest.get("batch_status") == "COMPLETE" and excluded)
        or manifest.get("external_verification_status") != "NOT_RUN"
        or manifest.get("certification_status") != "NOT_CERTIFIED"
    ):
        raise RouteError("ASSEMBLY_MANIFEST_CLOSURE_INVALID")

    seen_ids: set[str] = set()
    included_bindings: dict[str, tuple[str, int, str]] = {}
    included_sources: dict[str, str] = {}
    included_records: dict[str, Mapping[str, Any]] = {}
    for raw in included:
        if not isinstance(raw, Mapping):
            raise RouteError("ASSEMBLY_MANIFEST_INCLUDED_UNIT_INVALID")
        _require_exact_keys(
            raw,
            {
                "id",
                "namespace",
                "source_path",
                "function_name",
                "target_function_name",
                "target_path",
                "identifier_plan_path",
                "identifier_plan_sha256",
                "identifier_unit_namespace",
                "identifier_unit_namespace_sha256",
                "assembled_path",
                "assembled_bytes",
                "assembled_sha256",
                "source_sha256",
                "target_sha256",
            },
            "ASSEMBLY_MANIFEST_INCLUDED_UNIT_INVALID",
        )
        unit_id = raw.get("id")
        namespace = raw.get("namespace")
        relative = raw.get("assembled_path")
        source_path = raw.get("source_path")
        function_name = raw.get("function_name")
        target_function_name = raw.get("target_function_name")
        target_path = raw.get("target_path")
        identifier_plan_path = raw.get("identifier_plan_path")
        identifier_plan_sha256 = raw.get("identifier_plan_sha256")
        source_sha256 = raw.get("source_sha256")
        target_sha256 = raw.get("target_sha256")
        expected_bytes = raw.get("assembled_bytes")
        expected_sha256 = raw.get("assembled_sha256")
        if (
            not isinstance(unit_id, str)
            or _UNIT_ID_PATTERN.fullmatch(unit_id) is None
            or unit_id in seen_ids
            or namespace != _namespace(unit_id)
            or not isinstance(source_path, str)
            or not source_path
            or PurePosixPath(source_path).is_absolute()
            or ".." in PurePosixPath(source_path).parts
            or "\\" in source_path
            or PurePosixPath(source_path).as_posix() != source_path
            or not isinstance(function_name, str)
            or not function_name
            or not isinstance(target_function_name, str)
            or not target_function_name
            or not isinstance(target_path, str)
            or not target_path
            or "/" in target_path
            or "\\" in target_path
            or identifier_plan_path != _IDENTIFIER_PLAN_NAME
            or not isinstance(identifier_plan_sha256, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", identifier_plan_sha256) is None
            or not isinstance(source_sha256, str)
            or _RAW_SHA256_PATTERN.fullmatch(source_sha256) is None
            or not isinstance(target_sha256, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", target_sha256) is None
            or not isinstance(relative, str)
            or relative != _expected_assembled_path(target_language, str(namespace))
            or type(expected_bytes) is not int
            or expected_bytes < 0
            or not isinstance(expected_sha256, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", expected_sha256) is None
            or relative in included_bindings
        ):
            raise RouteError("ASSEMBLY_MANIFEST_INCLUDED_UNIT_INVALID")
        expected_unit_namespace = _expected_repository_unit_namespace(
            repository_snapshot_sha256=repository_snapshot_sha256,
            unit_id=unit_id,
            source_path=source_path,
            source_sha256=source_sha256,
            error_code="ASSEMBLY_MANIFEST_INCLUDED_UNIT_INVALID",
        )
        if (
            raw.get("identifier_unit_namespace") != expected_unit_namespace.to_mapping()
            or raw.get("identifier_unit_namespace_sha256") != expected_unit_namespace.digest
        ):
            raise RouteError("ASSEMBLY_MANIFEST_INCLUDED_UNIT_INVALID")
        seen_ids.add(unit_id)
        included_bindings[relative] = (unit_id, expected_bytes, expected_sha256)
        included_sources[unit_id] = source_path
        included_records[unit_id] = raw

    for raw in excluded:
        if not isinstance(raw, Mapping):
            raise RouteError("ASSEMBLY_MANIFEST_EXCLUDED_UNIT_INVALID")
        unit_id = raw.get("id")
        if (
            not isinstance(unit_id, str)
            or _UNIT_ID_PATTERN.fullmatch(unit_id) is None
            or unit_id in seen_ids
            or raw.get("status") not in {"FAILED", "SKIPPED_NOT_READY", "SKIPPED_NO_CASES"}
        ):
            raise RouteError("ASSEMBLY_MANIFEST_EXCLUDED_UNIT_INVALID")
        seen_ids.add(unit_id)

    source_language = manifest.get("source_language")
    assert source_language in _PLACERS
    expected_role_sets: dict[str, set[str]] = {}
    for unit_id, source_path in included_sources.items():
        roles = {
            "route-evidence",
            "behavior-equivalence",
            "source-semantic-ir",
            "identifier-plan",
            "emitted-target",
        }
        if source_language == "javascript":
            suffix = PurePosixPath(source_path).suffix.lower()
            if suffix == ".js":
                roles.add("source-javascript-esm-descriptor")
            elif suffix != ".mjs":
                raise RouteError("ASSEMBLY_MANIFEST_INCLUDED_UNIT_INVALID")
        expected_role_sets[unit_id] = roles

    evidence_bindings: dict[str, tuple[str, str, str, int, str]] = {}
    observed_roles: dict[str, set[str]] = {unit_id: set() for unit_id in included_sources}
    ordering: list[tuple[str, int]] = []
    filenames = {
        "route-evidence": _ROUTE_EVIDENCE_NAME,
        "behavior-equivalence": _BEHAVIOR_EVIDENCE_NAME,
        "source-semantic-ir": _SOURCE_SEMANTIC_IR_NAME,
        "identifier-plan": _IDENTIFIER_PLAN_NAME,
        "source-javascript-esm-descriptor": _JAVASCRIPT_ESM_DESCRIPTOR_NAME,
    }
    for raw in evidence_artifacts:
        if not isinstance(raw, Mapping):
            raise RouteError("ASSEMBLY_MANIFEST_EVIDENCE_ARTIFACT_INVALID")
        _require_exact_keys(
            raw,
            {"unit_id", "role", "source_path", "assembled_path", "bytes", "sha256"},
            "ASSEMBLY_MANIFEST_EVIDENCE_ARTIFACT_INVALID",
        )
        unit_id = raw.get("unit_id")
        role = raw.get("role")
        source_relative = raw.get("source_path")
        assembled_relative = raw.get("assembled_path")
        byte_count = raw.get("bytes")
        sha256 = raw.get("sha256")
        if (
            not isinstance(unit_id, str)
            or unit_id not in included_sources
            or (role not in filenames and role != "emitted-target")
        ):
            raise RouteError("ASSEMBLY_MANIFEST_EVIDENCE_ARTIFACT_INVALID")
        assert isinstance(role, str)
        assert isinstance(unit_id, str)
        filename = (
            str(included_records[unit_id]["target_path"])
            if role == "emitted-target"
            else filenames[role]
        )
        if (
            role not in expected_role_sets[unit_id]
            or role in observed_roles[unit_id]
            or source_relative != f"units/{unit_id}/{filename}"
            or assembled_relative != f"{_EVIDENCE_ROOT}/{unit_id}/{filename}"
            or type(byte_count) is not int
            or byte_count < 1
            or not isinstance(sha256, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", sha256) is None
            or assembled_relative in evidence_bindings
        ):
            raise RouteError("ASSEMBLY_MANIFEST_EVIDENCE_ARTIFACT_INVALID")
        observed_roles[unit_id].add(role)
        ordering.append((unit_id, _EVIDENCE_ROLE_ORDER[role]))
        evidence_bindings[assembled_relative] = (unit_id, role, source_relative, byte_count, sha256)
    if observed_roles != expected_role_sets or ordering != sorted(ordering):
        raise RouteError("ASSEMBLY_MANIFEST_EVIDENCE_ARTIFACT_SET_MISMATCH")

    owned_bindings: dict[str, tuple[int, str]] = {}
    for raw in build_inputs:
        if not isinstance(raw, Mapping):
            raise RouteError("ASSEMBLY_BUILD_INPUT_INVALID")
        relative = raw.get("path")
        byte_count = raw.get("bytes")
        sha256 = raw.get("sha256")
        pure = PurePosixPath(str(relative))
        if (
            not isinstance(relative, str)
            or not relative
            or pure.is_absolute()
            or ".." in pure.parts
            or "\\" in relative
            or pure.as_posix() != relative
            or type(byte_count) is not int
            or byte_count < 0
            or not isinstance(sha256, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", sha256) is None
            or relative in owned_bindings
        ):
            raise RouteError("ASSEMBLY_BUILD_INPUT_INVALID")
        owned_bindings[relative] = (byte_count, sha256)

    expected_inputs = _expected_build_input_paths(target_language, included_bindings)
    if sorted(owned_bindings) != expected_inputs:
        raise RouteError("ASSEMBLY_BUILD_INPUT_SET_MISMATCH")
    for relative, (_, expected_bytes, expected_sha256) in included_bindings.items():
        if owned_bindings.get(relative) != (expected_bytes, expected_sha256):
            raise RouteError("ASSEMBLY_BUILD_INPUT_SOURCE_BINDING_MISMATCH")
    _validate_build_verification(
        manifest,
        target_language,
        require_build_passed=require_build_passed,
    )
    return included_bindings, owned_bindings, evidence_bindings


def _validate_assembly_manifest(
    manifest: dict[str, Any],
    target_language: Language,
    destination: Path,
    *,
    require_build_passed: bool = False,
) -> None:
    """Bind assembly claims to the exact regular target-source files on disk."""

    included_bindings, owned_bindings, evidence_bindings = _manifest_owned_bindings(
        manifest,
        target_language,
        require_build_passed=require_build_passed,
    )
    for relative, (unit_id, expected_bytes, expected_sha256) in included_bindings.items():
        path = _confined_regular_file(
            destination,
            relative,
            f"ASSEMBLY_INCLUDED_SOURCE_MISSING_OR_UNSAFE:{unit_id}",
        )
        observed_bytes, observed_sha256 = _stable_file_binding(
            path,
            f"ASSEMBLY_INCLUDED_SOURCE_CHANGED_DURING_READ:{unit_id}",
        )
        if observed_bytes != expected_bytes or observed_sha256 != expected_sha256:
            raise RouteError(f"ASSEMBLY_INCLUDED_SOURCE_DRIFTED:{unit_id}")

    for relative, (expected_bytes, expected_sha256) in owned_bindings.items():
        path = _confined_regular_file(
            destination,
            relative,
            f"ASSEMBLY_BUILD_INPUT_MISSING_OR_UNSAFE:{relative}",
        )
        observed_bytes, observed_sha256 = _stable_file_binding(
            path,
            f"ASSEMBLY_BUILD_INPUT_CHANGED_DURING_READ:{relative}",
        )
        if observed_bytes != expected_bytes or observed_sha256 != expected_sha256:
            raise RouteError(f"ASSEMBLY_BUILD_INPUT_DRIFTED:{relative}")
    if _assembled_source_paths(destination, target_language) != set(included_bindings):
        raise RouteError("ASSEMBLY_SOURCE_SET_MISMATCH")
    evidence_contents: dict[str, dict[str, bytes]] = {}
    for relative, (unit_id, role, _source_relative, expected_bytes, expected_sha256) in evidence_bindings.items():
        path = _confined_regular_file(
            destination,
            relative,
            f"ASSEMBLY_EVIDENCE_ARTIFACT_MISSING_OR_UNSAFE:{unit_id}:{role}",
        )
        content = _stable_file_bytes(
            path,
            f"ASSEMBLY_EVIDENCE_ARTIFACT_CHANGED_DURING_READ:{unit_id}:{role}",
        )
        observed_sha256 = "sha256:" + hashlib.sha256(content).hexdigest()
        if len(content) != expected_bytes or observed_sha256 != expected_sha256:
            raise RouteError(f"ASSEMBLY_EVIDENCE_ARTIFACT_DRIFTED:{unit_id}:{role}")
        evidence_contents.setdefault(unit_id, {})[role] = content
    if _assembled_evidence_paths(destination) != set(evidence_bindings):
        raise RouteError("ASSEMBLY_EVIDENCE_ARTIFACT_SET_MISMATCH")
    source_language = manifest.get("source_language")
    assert source_language in _PLACERS
    repository_snapshot_sha256 = manifest.get("snapshot_sha256")
    assert isinstance(repository_snapshot_sha256, str)
    included_by_id = {
        str(raw["id"]): raw for raw in manifest["included_units"] if isinstance(raw, Mapping)
    }
    for unit_id, contents in evidence_contents.items():
        included_unit = included_by_id[unit_id]
        _validate_bound_evidence_contents(
            contents,
            unit_id=unit_id,
            source_language=source_language,
            repository_snapshot_sha256=repository_snapshot_sha256,
            included_unit=included_unit,
        )


def _archived_source_paths(
    archive_paths: Collection[str],
    target_language: Language,
    root_prefix: str,
) -> set[str]:
    root_name, suffix, auxiliary = _SOURCE_LAYOUTS[target_language]
    source_prefix = f"{root_prefix}{root_name}/"
    paths: set[str] = set()
    for archived_path in archive_paths:
        if not archived_path.startswith(source_prefix) or not archived_path.endswith(suffix):
            continue
        relative = archived_path.removeprefix(root_prefix)
        if relative not in auxiliary:
            paths.add(relative)
    return paths


def verify_archived_assembly_closure(
    manifest_bytes: bytes,
    target_language: Language,
    archive_paths: Collection[str],
    read_bytes: Callable[[str], bytes],
    *,
    root_prefix: str = "assembled/",
) -> dict[str, Any]:
    """Recompute assembly-owned build inputs exclusively from archive bytes."""

    prefix = PurePosixPath(root_prefix)
    if not root_prefix.endswith("/") or prefix.is_absolute() or ".." in prefix.parts or "\\" in root_prefix:
        raise RouteError("ASSEMBLY_ARCHIVE_ROOT_INVALID")
    try:
        raw_manifest = json.loads(manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RouteError("ASSEMBLY_ARCHIVE_MANIFEST_INVALID") from error
    if not isinstance(raw_manifest, dict):
        raise RouteError("ASSEMBLY_ARCHIVE_MANIFEST_INVALID")
    manifest: dict[str, Any] = raw_manifest
    included_bindings, owned_bindings, evidence_bindings = _manifest_owned_bindings(
        manifest,
        target_language,
        require_build_passed=True,
    )
    names = set(archive_paths)
    if _archived_source_paths(names, target_language, root_prefix) != set(included_bindings):
        raise RouteError("ASSEMBLY_ARCHIVE_SOURCE_SET_MISMATCH")
    for relative, (expected_bytes, expected_sha256) in owned_bindings.items():
        archived_path = f"{root_prefix}{relative}"
        if archived_path not in names:
            raise RouteError(f"ASSEMBLY_ARCHIVE_BUILD_INPUT_MISSING:{relative}")
        content = read_bytes(archived_path)
        observed = "sha256:" + hashlib.sha256(content).hexdigest()
        if len(content) != expected_bytes or observed != expected_sha256:
            raise RouteError(f"ASSEMBLY_ARCHIVE_BUILD_INPUT_DRIFTED:{relative}")
    source_language = manifest.get("source_language")
    assert source_language in _PLACERS
    repository_snapshot_sha256 = manifest.get("snapshot_sha256")
    assert isinstance(repository_snapshot_sha256, str)
    included_by_id = {
        str(raw["id"]): raw for raw in manifest["included_units"] if isinstance(raw, Mapping)
    }
    copied_contents: dict[str, dict[str, bytes]] = {}
    source_contents: dict[str, dict[str, bytes]] = {}
    expected_assembled_evidence = {f"{root_prefix}{relative}" for relative in evidence_bindings}
    observed_assembled_evidence = {
        name for name in names if name.startswith(f"{root_prefix}{_EVIDENCE_ROOT}/")
    }
    if observed_assembled_evidence != expected_assembled_evidence:
        raise RouteError("ASSEMBLY_ARCHIVE_EVIDENCE_ARTIFACT_SET_MISMATCH")
    evidence_filenames = {
        _ROUTE_EVIDENCE_NAME,
        _BEHAVIOR_EVIDENCE_NAME,
        _SOURCE_SEMANTIC_IR_NAME,
        _IDENTIFIER_PLAN_NAME,
        _JAVASCRIPT_ESM_DESCRIPTOR_NAME,
        *(str(raw["target_path"]) for raw in included_by_id.values()),
    }
    expected_source_evidence = {
        f"batch/{source_relative}"
        for _relative, (_unit_id, _role, source_relative, _bytes, _sha256) in evidence_bindings.items()
    }
    observed_source_evidence = {
        name
        for name in names
        if len(PurePosixPath(name).parts) == 4
        and PurePosixPath(name).parts[:2] == ("batch", "units")
        and PurePosixPath(name).parts[2] in included_by_id
        and PurePosixPath(name).name in evidence_filenames
    }
    if observed_source_evidence - expected_source_evidence:
        raise RouteError("ASSEMBLY_ARCHIVE_SOURCE_EVIDENCE_ARTIFACT_SET_MISMATCH")
    for relative, (unit_id, role, source_relative, expected_bytes, expected_sha256) in evidence_bindings.items():
        assembled_archive_path = f"{root_prefix}{relative}"
        source_archive_path = f"batch/{source_relative}"
        if assembled_archive_path not in names or source_archive_path not in names:
            raise RouteError(f"ASSEMBLY_ARCHIVE_EVIDENCE_ARTIFACT_MISSING:{unit_id}:{role}")
        copied = read_bytes(assembled_archive_path)
        source = read_bytes(source_archive_path)
        observed_sha256 = "sha256:" + hashlib.sha256(copied).hexdigest()
        if (
            len(copied) != expected_bytes
            or len(source) != expected_bytes
            or copied != source
            or observed_sha256 != expected_sha256
        ):
            raise RouteError(f"ASSEMBLY_ARCHIVE_EVIDENCE_ARTIFACT_DRIFTED:{unit_id}:{role}")
        copied_contents.setdefault(unit_id, {})[role] = copied
        source_contents.setdefault(unit_id, {})[role] = source
    for unit_id in copied_contents:
        included_unit = included_by_id[unit_id]
        _validate_bound_evidence_contents(
            copied_contents[unit_id],
            unit_id=unit_id,
            source_language=source_language,
            repository_snapshot_sha256=repository_snapshot_sha256,
            included_unit=included_unit,
        )
        _validate_bound_evidence_contents(
            source_contents[unit_id],
            unit_id=unit_id,
            source_language=source_language,
            repository_snapshot_sha256=repository_snapshot_sha256,
            included_unit=included_unit,
        )
    return manifest


def _write_build_files(
    destination: Path,
    target_language: Language,
    included_units: list[dict[str, Any]],
) -> None:
    if target_language == "java":
        (destination / "pom.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<project xmlns="http://maven.apache.org/POM/4.0.0">\n'
            "    <modelVersion>4.0.0</modelVersion>\n"
            "    <groupId>io.elmos.generated</groupId>\n"
            "    <artifactId>polyglot-migrated-library</artifactId>\n"
            "    <version>0.0.0-experimental</version>\n"
            "    <packaging>jar</packaging>\n"
            "    <properties>\n"
            "        <maven.compiler.release>21</maven.compiler.release>\n"
            "        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>\n"
            "    </properties>\n"
            "</project>\n",
            encoding="utf-8",
        )
    elif target_language == "csharp":
        (destination / "polyglot-migrated-library.csproj").write_text(
            '<Project Sdk="Microsoft.NET.Sdk">\n'
            "  <PropertyGroup>\n"
            "    <TargetFramework>net10.0</TargetFramework>\n"
            "    <ImplicitUsings>enable</ImplicitUsings>\n"
            "    <Nullable>enable</Nullable>\n"
            "    <AssemblyName>Elmos.Generated.PolyglotMigratedLibrary</AssemblyName>\n"
            "    <RootNamespace>Elmos.Generated</RootNamespace>\n"
            "    <TreatWarningsAsErrors>true</TreatWarningsAsErrors>\n"
            "    <EnableDefaultCompileItems>false</EnableDefaultCompileItems>\n"
            "  </PropertyGroup>\n"
            "  <ItemGroup>\n"
            '    <Compile Include="src/**/*.cs" />\n'
            "  </ItemGroup>\n"
            "</Project>\n",
            encoding="utf-8",
        )
    elif target_language == "python":
        (destination / "pyproject.toml").write_text(
            "[project]\n"
            'name = "elmos-polyglot-migrated-library"\n'
            'version = "0.0.0"\n'
            'requires-python = ">=3.12"\n'
            "\n"
            "[build-system]\n"
            'requires = ["setuptools>=68"]\n'
            'build-backend = "setuptools.build_meta"\n'
            "\n"
            "[tool.setuptools.packages.find]\n"
            'where = ["src"]\n',
            encoding="utf-8",
        )
    elif target_language == "typescript":
        (destination / "package.json").write_text(
            json.dumps(
                {
                    "name": "elmos-polyglot-migrated-library",
                    "version": "0.0.0-experimental",
                    "private": True,
                    "type": "module",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (destination / "tsconfig.json").write_text(
            json.dumps(
                {
                    "compilerOptions": {
                        "target": "ES2022",
                        "module": "NodeNext",
                        "moduleResolution": "NodeNext",
                        "strict": True,
                        "declaration": True,
                        "outDir": "dist",
                        "rootDir": "src",
                    },
                    "include": ["src/**/*.ts"],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    elif target_language == "javascript":
        (destination / "package.json").write_text(
            json.dumps(
                {
                    "name": "elmos-polyglot-migrated-library",
                    "version": "0.0.0-experimental",
                    "private": True,
                    "type": "module",
                    "engines": {"node": "26.0.0"},
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    elif target_language == "go":
        (destination / "go.mod").write_text(
            "module elmos.local/polyglot-migrated-library\n\ngo 1.25.0\n",
            encoding="utf-8",
        )
    elif target_language == "rust":
        (destination / "Cargo.toml").write_text(
            "[package]\n"
            'name = "elmos-polyglot-migrated-library"\n'
            'version = "0.0.0"\n'
            'edition = "2021"\n'
            "publish = false\n\n"
            "[lib]\n"
            'path = "src/lib.rs"\n',
            encoding="utf-8",
        )
        modules = "\n".join(f"pub mod {unit['namespace']};" for unit in included_units)
        (destination / "src" / "lib.rs").write_text(modules + "\n", encoding="utf-8")
    elif target_language in {"cpp", "objc"}:
        cmake_language = "CXX" if target_language == "cpp" else "OBJC"
        standard = (
            "set(CMAKE_CXX_STANDARD 17)\nset(CMAKE_CXX_STANDARD_REQUIRED ON)\n" if target_language == "cpp" else ""
        )
        sources = "\n    ".join(str(unit["assembled_path"]) for unit in included_units)
        platform_linkage = (
            "find_library(FOUNDATION_FRAMEWORK Foundation REQUIRED)\n"
            "target_link_libraries(elmos_migrated PRIVATE ${FOUNDATION_FRAMEWORK})\n"
            if target_language == "objc"
            else ""
        )
        (destination / "CMakeLists.txt").write_text(
            "cmake_minimum_required(VERSION 3.20)\n"
            f"project(elmos_polyglot_migrated_library LANGUAGES {cmake_language})\n"
            f"{standard}add_library(elmos_migrated SHARED\n    {sources}\n)\n"
            f"{platform_linkage}",
            encoding="utf-8",
        )
    elif target_language == "swift":
        products = ",\n".join(
            f'        .library(name: "{unit["namespace"].capitalize()}", targets: ["{unit["namespace"].capitalize()}"])'
            for unit in included_units
        )
        targets = ",\n".join(f'        .target(name: "{unit["namespace"].capitalize()}")' for unit in included_units)
        (destination / "Package.swift").write_text(
            "// swift-tools-version: 6.0\n"
            "import PackageDescription\n\n"
            "let package = Package(\n"
            '    name: "ElmosPolyglotMigratedLibrary",\n'
            "    products: [\n"
            f"{products}\n"
            "    ],\n"
            "    targets: [\n"
            f"{targets}\n"
            "    ]\n"
            ")\n",
            encoding="utf-8",
        )
    elif target_language == "php":
        # Classmap over the whole generated tree rather than PSR-4: the emitted
        # unit is a file of plain functions with no class and no namespace, and
        # PSR-4 only ever autoloads classes. `files` is the one autoload mode
        # that loads function declarations, so every unit is listed explicitly
        # and the order is the manifest order, which is already deterministic.
        files = ",\n".join(
            f'            "src/{unit["namespace"]}/migrated.php"' for unit in included_units
        )
        (destination / "composer.json").write_text(
            "{\n"
            '    "name": "elmos/polyglot-migrated-library",\n'
            '    "description": "ELMOS polyglot route engine assembled target project",\n'
            '    "type": "library",\n'
            '    "license": "proprietary",\n'
            '    "require": {\n'
            '        "php": ">=8.4"\n'
            "    },\n"
            '    "autoload": {\n'
            '        "files": [\n'
            f"{files}\n"
            "        ]\n"
            "    },\n"
            '    "config": {\n'
            '        "optimize-autoloader": true\n'
            "    }\n"
            "}\n",
            encoding="utf-8",
        )
    else:
        raise RouteError(f"ASSEMBLY_UNSUPPORTED_TARGET_LANGUAGE:{target_language}")


def _build_input_bindings(
    destination: Path,
    target_language: Language,
    included_units: Collection[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    source_paths = [str(unit.get("assembled_path", "")) for unit in included_units]
    bindings: list[dict[str, Any]] = []
    for relative in _expected_build_input_paths(target_language, source_paths):
        path = _confined_regular_file(
            destination,
            relative,
            f"ASSEMBLY_BUILD_INPUT_MISSING_OR_UNSAFE:{relative}",
        )
        byte_count, sha256 = _stable_file_binding(
            path,
            f"ASSEMBLY_BUILD_INPUT_CHANGED_DURING_READ:{relative}",
        )
        bindings.append({"path": relative, "bytes": byte_count, "sha256": sha256})
    return bindings


def _persist_verified_evidence_artifacts(
    destination: Path,
    artifacts: Collection[_VerifiedEvidenceArtifact],
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for artifact in artifacts:
        path = destination / artifact.assembled_path
        if path.exists() or path.is_symlink():
            raise RouteError(
                f"ASSEMBLY_EVIDENCE_ARTIFACT_DUPLICATED:{artifact.unit_id}:{artifact.role}"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(artifact.content)
        persisted = _confined_regular_file(
            destination,
            artifact.assembled_path,
            f"ASSEMBLY_EVIDENCE_ARTIFACT_MISSING_OR_UNSAFE:{artifact.unit_id}:{artifact.role}",
        )
        byte_count, sha256 = _stable_file_binding(
            persisted,
            f"ASSEMBLY_EVIDENCE_ARTIFACT_CHANGED_DURING_WRITE:{artifact.unit_id}:{artifact.role}",
        )
        if byte_count != len(artifact.content) or sha256 != artifact.sha256:
            raise RouteError(f"ASSEMBLY_EVIDENCE_ARTIFACT_DRIFTED:{artifact.unit_id}:{artifact.role}")
        records.append(artifact.record())
    return records


def assemble_project(
    batch_report: dict[str, Any],
    batch_output: Path,
    destination: Path,
) -> dict[str, Any]:
    """Assemble a batch report's PASSED units into one buildable project skeleton.

    `destination` must not already exist (see `validation.safe_output`); this
    function only ever creates a fresh assembly, never merges into one.
    """
    if batch_report.get("kind") != "elmos.repository-batch-report":
        raise RouteError("ASSEMBLY_BATCH_REPORT_KIND_INVALID")
    _validate_batch_report_closure(batch_report)
    target_language = batch_report.get("target_language")
    source_language = batch_report.get("source_language")
    repository_snapshot_sha256 = batch_report.get("snapshot_sha256")
    if target_language not in _PLACERS:
        raise RouteError("ASSEMBLY_UNSUPPORTED_TARGET_LANGUAGE")
    if source_language not in _PLACERS:
        raise RouteError("ASSEMBLY_SOURCE_LANGUAGE_INVALID")
    assert isinstance(repository_snapshot_sha256, str)
    units = batch_report.get("units")
    assert isinstance(units, list)
    if batch_output.is_symlink() or not batch_output.is_dir():
        raise RouteError("ASSEMBLY_BATCH_OUTPUT_DIRECTORY_INVALID")

    destination = safe_output(destination)
    if destination.exists():
        raise RouteError("ASSEMBLY_DESTINATION_ALREADY_EXISTS")
    destination.mkdir(parents=True)

    placer = _PLACERS[target_language]
    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    verified_evidence_artifacts: list[dict[str, object]] = []
    seen_ids: set[str] = set()

    for unit in units:
        unit_id = str(unit.get("id", ""))
        if unit_id in seen_ids:
            raise RouteError(f"ASSEMBLY_DUPLICATE_UNIT_ID:{unit_id}")
        seen_ids.add(unit_id)
        if unit.get("status") != "PASSED":
            excluded.append(
                {
                    "id": unit_id,
                    "status": unit.get("status"),
                    "reason": unit.get("reason", "Unit did not reach PASSED status in the batch run."),
                }
            )
            continue
        namespace = _namespace(_safe_unit_id(unit_id))
        content = _read_verified_unit_source(batch_output, unit)
        verified_evidence = _read_verified_unit_evidence(
            batch_output,
            unit,
            source_language,
            repository_snapshot_sha256,
            content.encode("utf-8"),
        )
        verified_evidence_artifacts.extend(
            _persist_verified_evidence_artifacts(destination, verified_evidence.artifacts)
        )
        relative_path = placer(destination, namespace, content)
        assembled_path = _confined_regular_file(
            destination,
            relative_path,
            f"ASSEMBLY_INCLUDED_SOURCE_MISSING_OR_UNSAFE:{unit_id}",
        )
        assembled_bytes, assembled_sha256 = _stable_file_binding(
            assembled_path,
            f"ASSEMBLY_INCLUDED_SOURCE_CHANGED_DURING_READ:{unit_id}",
        )
        included.append(
            {
                "id": unit_id,
                "namespace": namespace,
                "source_path": unit.get("source_path"),
                "function_name": unit.get("function_name"),
                "target_function_name": unit.get("target_function_name"),
                "target_path": unit.get("target_path"),
                "identifier_plan_path": unit.get("identifier_plan_path"),
                "identifier_plan_sha256": unit.get("identifier_plan_sha256"),
                "identifier_unit_namespace": verified_evidence.unit_namespace.to_mapping(),
                "identifier_unit_namespace_sha256": verified_evidence.unit_namespace.digest,
                "assembled_path": relative_path,
                "assembled_bytes": assembled_bytes,
                "assembled_sha256": assembled_sha256,
                "source_sha256": verified_evidence.unit_namespace.source_sha256.removeprefix("sha256:"),
                "target_sha256": unit.get("target_sha256"),
            }
        )

    if not included:
        raise RouteError("ASSEMBLY_NO_PASSED_UNITS_TO_ASSEMBLE")

    _write_build_files(destination, target_language, included)
    build_inputs = _build_input_bindings(destination, target_language, included)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "kind": "elmos.repository-assembly-report",
        "status": "ASSEMBLED",
        "repository_ref": batch_report.get("repository_ref"),
        "snapshot_sha256": batch_report.get("snapshot_sha256"),
        "repository_scale": batch_report.get("repository_scale"),
        "repository_limits": batch_report.get("repository_limits"),
        "route_id": batch_report.get("route_id"),
        "source_language": batch_report.get("source_language"),
        "target_language": target_language,
        "batch_status": batch_report.get("status"),
        "build_files": list(_BUILD_FILES[target_language]),
        "build_input_count": len(build_inputs),
        "build_inputs": build_inputs,
        "verified_evidence_artifact_count": len(verified_evidence_artifacts),
        "verified_evidence_artifacts": verified_evidence_artifacts,
        "included_unit_count": len(included),
        "excluded_unit_count": len(excluded),
        "included_units": included,
        "excluded_units": excluded,
        "build_verification_status": "NOT_RUN",
        "external_verification_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
        "limitations": [
            "Assembly only relocates already-emitted, already-verified per-unit source; "
            "it performs no additional translation.",
            "Each unit keeps its own namespace/module; units are never merged into a shared "
            "namespace, because cross-unit name collisions (e.g. two files defining a "
            "same-named function with different behavior) are not resolved at the semantic level.",
            "A batch_status of PARTIAL means the source repository was not fully migrated; "
            "this project covers only the included units listed above, not the whole repository.",
            "build_verification_status reflects a real whole-project compile/build invocation, "
            "not a re-run of per-unit behavior cases; those already passed during the batch run "
            "for every included unit, and assembly does not repeat them.",
            "build_verification_status is NOT_RUN until verify_assembled_project is executed.",
            "build_inputs binds every manifest-owned source, auxiliary source, and project build file ",
            "by exact path, byte count, and sha256.",
            "verified_evidence_artifacts binds the independently parsed route, behavior, source "
            "semantic IR, identifier plan, emitted target, and optional JavaScript ESM descriptor "
            "evidence copied into this assembly.",
            "External verification and certification remain NOT_RUN / NOT_CERTIFIED.",
        ],
    }
    _write_manifest(destination, manifest)
    return manifest


def _write_manifest(destination: Path, manifest: dict[str, Any]) -> None:
    (destination / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_assembly_manifest(destination: Path) -> dict[str, Any]:
    manifest_path = _confined_regular_file(
        destination,
        MANIFEST_NAME,
        "ASSEMBLY_MANIFEST_MISSING_OR_UNSAFE",
    )
    manifest_bytes = _stable_file_bytes(manifest_path, "ASSEMBLY_MANIFEST_CHANGED_DURING_READ")
    try:
        raw_manifest = json.loads(manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RouteError("ASSEMBLY_MANIFEST_INVALID") from error
    if not isinstance(raw_manifest, dict):
        raise RouteError("ASSEMBLY_MANIFEST_INVALID")
    return raw_manifest


def verify_assembly_closure(target_language: Language, destination: Path) -> dict[str, Any]:
    """Verify final on-disk assembly inputs and require a closed passing build."""

    destination = destination.expanduser()
    if destination.is_symlink() or not destination.is_dir():
        raise RouteError("ASSEMBLY_DESTINATION_UNSAFE")
    resolved = destination.resolve(strict=True)
    manifest = _read_assembly_manifest(resolved)
    _validate_assembly_manifest(
        manifest,
        target_language,
        resolved,
        require_build_passed=True,
    )
    return manifest


def _run(
    command: list[str],
    cwd: Path,
    *,
    timeout: int = 300,
    executable_dirs: tuple[Path, ...] = (),
) -> subprocess.CompletedProcess[str]:
    executable = Path(command[0])
    executable = executable if executable.is_absolute() else (cwd / executable)
    try:
        with tempfile.TemporaryDirectory(prefix="elmos-assembly-process-") as temporary:
            root = Path(temporary)
            home = root / "home"
            scratch = root / "tmp"
            cache = home / ".cache"
            home.mkdir(mode=0o700)
            scratch.mkdir(mode=0o700)
            cache.mkdir(mode=0o700)
            completed = subprocess.run(
                command,
                cwd=cwd,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=sanitized_subprocess_env(
                    home=home,
                    temp_dir=scratch,
                    executable_dirs=(executable.resolve().parent, *executable_dirs),
                ),
            )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RouteError(
            f"ASSEMBLY_BUILD_VERIFICATION_FAILED:{Path(command[0]).name}:process"
        ) from error
    if completed.returncode != 0:
        stdout = _bounded_process_diagnostic(completed.stdout, cwd=cwd)
        stderr = _bounded_process_diagnostic(completed.stderr, cwd=cwd)
        raise RouteError(
            "ASSEMBLY_BUILD_VERIFICATION_FAILED:"
            f"{Path(command[0]).name}:returncode={completed.returncode}:"
            f"stdout={json.dumps(stdout, ensure_ascii=True)}:"
            f"stderr={json.dumps(stderr, ensure_ascii=True)}"
        )
    return completed


def _stat_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_uid,
        value.st_gid,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _stable_cmake_file_bytes(
    path: Path,
    *,
    expected_uid: int,
    expected_gid: int,
    error_code: str,
    maximum_bytes: int | None = None,
) -> tuple[os.stat_result, bytes]:
    try:
        path_before = path.lstat()
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            opened_before = os.fstat(descriptor)
            chunks: list[bytes] = []
            total = 0
            while chunk := os.read(descriptor, 1024 * 1024):
                total += len(chunk)
                if total > (_EXPECTED_CMAKE_TREE_FILE_BYTES if maximum_bytes is None else maximum_bytes):
                    raise RouteError(error_code)
                chunks.append(chunk)
            opened_after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        path_after = path.lstat()
    except OSError as error:
        raise RouteError(error_code) from error
    identity = _stat_identity(path_before)
    content = b"".join(chunks)
    if (
        not stat.S_ISREG(path_before.st_mode)
        or path_before.st_uid != expected_uid
        or path_before.st_gid != expected_gid
        or path_before.st_nlink != 1
        or len(content) != path_before.st_size
        or identity != _stat_identity(opened_before)
        or identity != _stat_identity(opened_after)
        or identity != _stat_identity(path_after)
    ):
        raise RouteError(error_code)
    return path_before, content


def _canonical_cmake_bindings(bindings: tuple[_CMakeBinding, ...]) -> bytes:
    return json.dumps(
        [binding.record() for binding in bindings],
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _cmake_source_paths() -> list[Path]:
    if (
        _EXPECTED_CMAKE_EXECUTABLE != _EXPECTED_CMAKE_PREFIX / "bin" / "cmake"
        or _EXPECTED_CMAKE_RESOURCE_ROOT != _EXPECTED_CMAKE_PREFIX / "share" / "cmake"
    ):
        raise RouteError("EXACT_TOOLCHAIN_CMAKE_SOURCE_PATH_INVALID")
    required_directories = (
        _EXPECTED_CMAKE_PREFIX,
        _EXPECTED_CMAKE_PREFIX / "bin",
        _EXPECTED_CMAKE_PREFIX / "share",
        _EXPECTED_CMAKE_RESOURCE_ROOT,
    )
    try:
        for directory in required_directories:
            metadata = directory.lstat()
            if (
                directory.resolve(strict=True) != directory
                or not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid != _EXPECTED_CMAKE_SOURCE_UID
                or metadata.st_gid != _EXPECTED_CMAKE_SOURCE_GID
                or stat.S_IMODE(metadata.st_mode) & 0o022
            ):
                raise RouteError("EXACT_TOOLCHAIN_CMAKE_SOURCE_PATH_UNSAFE")
        executable_metadata = _EXPECTED_CMAKE_EXECUTABLE.lstat()
        if not stat.S_ISREG(executable_metadata.st_mode):
            raise RouteError("EXACT_TOOLCHAIN_CMAKE_SOURCE_PATH_UNSAFE")
    except OSError as error:
        raise RouteError("EXACT_TOOLCHAIN_UNAVAILABLE:cmake-runtime") from error

    paths = [_EXPECTED_CMAKE_EXECUTABLE, _EXPECTED_CMAKE_RESOURCE_ROOT]
    for current, raw_directories, raw_files in os.walk(
        _EXPECTED_CMAKE_RESOURCE_ROOT,
        topdown=True,
        followlinks=False,
    ):
        current_path = Path(current)
        raw_directories.sort()
        raw_files.sort()
        for name in (*raw_directories, *raw_files):
            candidate = current_path / name
            try:
                metadata = candidate.lstat()
            except OSError as error:
                raise RouteError("EXACT_TOOLCHAIN_CMAKE_SOURCE_CHANGED_DURING_ENUMERATION") from error
            if stat.S_ISLNK(metadata.st_mode) or not (stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode)):
                raise RouteError("EXACT_TOOLCHAIN_CMAKE_SOURCE_PATH_UNSAFE")
            paths.append(candidate)
    return sorted(paths, key=lambda path: path.relative_to(_EXPECTED_CMAKE_PREFIX).as_posix())


def _read_cmake_source_snapshot(*, retain_contents: bool) -> _CMakeSourceSnapshot:
    bindings: list[_CMakeBinding] = []
    contents: dict[str, bytes] = {}
    directory_identities: dict[Path, tuple[int, ...]] = {}
    total_file_bytes = 0
    for path in _cmake_source_paths():
        relative = path.relative_to(_EXPECTED_CMAKE_PREFIX).as_posix()
        try:
            metadata = path.lstat()
        except OSError as error:
            raise RouteError("EXACT_TOOLCHAIN_CMAKE_SOURCE_CHANGED_DURING_READ") from error
        if metadata.st_uid != _EXPECTED_CMAKE_SOURCE_UID or metadata.st_gid != _EXPECTED_CMAKE_SOURCE_GID:
            raise RouteError("EXACT_TOOLCHAIN_CMAKE_SOURCE_IDENTITY_MISMATCH")
        if stat.S_ISDIR(metadata.st_mode):
            directory_identities[path] = _stat_identity(metadata)
            binding = _CMakeBinding(
                path=relative,
                kind="directory",
                mode=stat.S_IMODE(metadata.st_mode),
                uid=metadata.st_uid,
                gid=metadata.st_gid,
                bytes=0,
                sha256="",
            )
        elif stat.S_ISREG(metadata.st_mode):
            stable_metadata, content = _stable_cmake_file_bytes(
                path,
                expected_uid=_EXPECTED_CMAKE_SOURCE_UID,
                expected_gid=_EXPECTED_CMAKE_SOURCE_GID,
                error_code="EXACT_TOOLCHAIN_CMAKE_SOURCE_CHANGED_DURING_READ",
            )
            total_file_bytes += len(content)
            if total_file_bytes > _EXPECTED_CMAKE_TREE_FILE_BYTES:
                raise RouteError("EXACT_TOOLCHAIN_CMAKE_SOURCE_IDENTITY_MISMATCH")
            binding = _CMakeBinding(
                path=relative,
                kind="file",
                mode=stat.S_IMODE(stable_metadata.st_mode),
                uid=stable_metadata.st_uid,
                gid=stable_metadata.st_gid,
                bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
            )
            if retain_contents:
                contents[relative] = content
        else:
            raise RouteError("EXACT_TOOLCHAIN_CMAKE_SOURCE_PATH_UNSAFE")
        bindings.append(binding)
    try:
        if any(identity != _stat_identity(path.lstat()) for path, identity in directory_identities.items()):
            raise RouteError("EXACT_TOOLCHAIN_CMAKE_SOURCE_CHANGED_DURING_ENUMERATION")
    except OSError as error:
        raise RouteError("EXACT_TOOLCHAIN_CMAKE_SOURCE_CHANGED_DURING_ENUMERATION") from error
    ordered = tuple(bindings)
    identity_sha256 = hashlib.sha256(_canonical_cmake_bindings(ordered)).hexdigest()
    binary = next((binding for binding in ordered if binding.path == "bin/cmake"), None)
    if (
        len(ordered) != _EXPECTED_CMAKE_TREE_ENTRY_COUNT
        or total_file_bytes != _EXPECTED_CMAKE_TREE_FILE_BYTES
        or identity_sha256 != _EXPECTED_CMAKE_TREE_SHA256
        or binary is None
        or binary.kind != "file"
        or binary.bytes != _EXPECTED_CMAKE_BYTES
        or binary.sha256 != _EXPECTED_CMAKE_SHA256
    ):
        raise RouteError("EXACT_TOOLCHAIN_CMAKE_SOURCE_IDENTITY_MISMATCH")
    return _CMakeSourceSnapshot(
        bindings=ordered,
        contents=contents,
        identity_sha256=identity_sha256,
        total_file_bytes=total_file_bytes,
    )


def _cmake_bundle_mode(binding: _CMakeBinding) -> int:
    if binding.kind == "directory":
        return 0o500
    return 0o500 if binding.mode & 0o111 else 0o400


def _cmake_runtime_manifest(snapshot: _CMakeSourceSnapshot) -> bytes:
    payload = {
        "schema_version": "1.0.0",
        "kind": "elmos.private-content-addressed-cmake-runtime",
        "cmake_version": _EXPECTED_CMAKE_VERSION,
        "source_prefix": str(_EXPECTED_CMAKE_PREFIX),
        "source_identity_sha256": snapshot.identity_sha256,
        "source_entry_count": len(snapshot.bindings),
        "source_total_file_bytes": snapshot.total_file_bytes,
        "entries": [{**binding.record(), "bundle_mode": _cmake_bundle_mode(binding)} for binding in snapshot.bindings],
    }
    return json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _write_private_file(path: Path, content: bytes, mode: int) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
        try:
            view = memoryview(content)
            written = 0
            while written < len(content):
                count = os.write(descriptor, view[written:])
                if count <= 0:
                    raise OSError("short write")
                written += count
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        path.chmod(mode, follow_symlinks=False)
    except OSError as error:
        raise RouteError("EXACT_TOOLCHAIN_CMAKE_BUNDLE_CREATION_FAILED") from error


def _create_cmake_runtime_bundle(snapshot: _CMakeSourceSnapshot) -> _CMakeRuntimeBundle:
    try:
        temporary_parent = Path(tempfile.gettempdir()).resolve(strict=True)
        cache_root = Path(
            tempfile.mkdtemp(
                prefix="elmos-cmake-runtime-",
                dir=temporary_parent,
            )
        )
        cache_root.chmod(0o700)
        prefix = cache_root / f"cmake-4.4.0-{snapshot.identity_sha256}"
        prefix.mkdir(mode=0o700)
        (prefix / "bin").mkdir(mode=0o700)
        (prefix / "share").mkdir(mode=0o700)
        for binding in snapshot.bindings:
            target = prefix / binding.path
            if binding.kind == "directory":
                target.mkdir(parents=True, exist_ok=True, mode=0o700)
        for binding in snapshot.bindings:
            if binding.kind != "file":
                continue
            content = snapshot.contents.get(binding.path)
            if (
                content is None
                or len(content) != binding.bytes
                or hashlib.sha256(content).hexdigest() != binding.sha256
            ):
                raise RouteError("EXACT_TOOLCHAIN_CMAKE_SOURCE_SNAPSHOT_INCOMPLETE")
            _write_private_file(prefix / binding.path, content, _cmake_bundle_mode(binding))
        manifest_bytes = _cmake_runtime_manifest(snapshot)
        if (
            len(manifest_bytes) != _EXPECTED_CMAKE_RUNTIME_MANIFEST_BYTES
            or hashlib.sha256(manifest_bytes).hexdigest() != _EXPECTED_CMAKE_RUNTIME_MANIFEST_SHA256
        ):
            raise RouteError("EXACT_TOOLCHAIN_CMAKE_BUNDLE_MANIFEST_IDENTITY_MISMATCH")
        _write_private_file(prefix / _CMAKE_RUNTIME_MANIFEST, manifest_bytes, 0o400)
        for directory in sorted(
            (path for path in prefix.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            directory.chmod(0o500, follow_symlinks=False)
        prefix.chmod(0o700, follow_symlinks=False)
    except OSError as error:
        if "cache_root" in locals():
            _remove_cmake_cache_root(cache_root)
        raise RouteError("EXACT_TOOLCHAIN_CMAKE_BUNDLE_CREATION_FAILED") from error
    except RouteError:
        if "cache_root" in locals():
            _remove_cmake_cache_root(cache_root)
        raise
    return _CMakeRuntimeBundle(
        cache_root=cache_root,
        prefix=prefix,
        executable=prefix / "bin" / "cmake",
        source_prefix=_EXPECTED_CMAKE_PREFIX,
        source_identity_sha256=snapshot.identity_sha256,
        source_bindings=snapshot.bindings,
        manifest_bytes=manifest_bytes,
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
    )


def _expected_cmake_bundle_paths(bundle: _CMakeRuntimeBundle) -> dict[str, tuple[str, int, int, str]]:
    expected: dict[str, tuple[str, int, int, str]] = {
        "bin": ("directory", 0o500, 0, ""),
        "share": ("directory", 0o500, 0, ""),
        _CMAKE_RUNTIME_MANIFEST: (
            "file",
            0o400,
            len(bundle.manifest_bytes),
            bundle.manifest_sha256,
        ),
    }
    for binding in bundle.source_bindings:
        expected[binding.path] = (
            binding.kind,
            _cmake_bundle_mode(binding),
            binding.bytes,
            binding.sha256,
        )
    return expected


def _verify_cmake_bundle(bundle: _CMakeRuntimeBundle) -> None:
    try:
        prefix_metadata = bundle.prefix.lstat()
    except OSError as error:
        raise RouteError("EXACT_TOOLCHAIN_CMAKE_BUNDLE_UNAVAILABLE") from error
    if (
        not stat.S_ISDIR(prefix_metadata.st_mode)
        or stat.S_IMODE(prefix_metadata.st_mode) != 0o700
        or prefix_metadata.st_uid != os.getuid()
        or prefix_metadata.st_gid != os.getgid()
        or bundle.prefix.resolve(strict=True) != bundle.prefix
        or bundle.executable != bundle.prefix / "bin" / "cmake"
        or len(bundle.manifest_bytes) != _EXPECTED_CMAKE_RUNTIME_MANIFEST_BYTES
        or bundle.manifest_sha256 != _EXPECTED_CMAKE_RUNTIME_MANIFEST_SHA256
        or hashlib.sha256(bundle.manifest_bytes).hexdigest() != bundle.manifest_sha256
    ):
        raise RouteError("EXACT_TOOLCHAIN_CMAKE_BUNDLE_ROOT_UNSAFE")
    expected = _expected_cmake_bundle_paths(bundle)
    observed: dict[str, Path] = {}
    for current, raw_directories, raw_files in os.walk(bundle.prefix, topdown=True, followlinks=False):
        current_path = Path(current)
        raw_directories.sort()
        raw_files.sort()
        for name in (*raw_directories, *raw_files):
            candidate = current_path / name
            relative = candidate.relative_to(bundle.prefix).as_posix()
            try:
                metadata = candidate.lstat()
            except OSError as error:
                raise RouteError("EXACT_TOOLCHAIN_CMAKE_BUNDLE_CHANGED_DURING_READ") from error
            if stat.S_ISLNK(metadata.st_mode):
                raise RouteError("EXACT_TOOLCHAIN_CMAKE_BUNDLE_PATH_UNSAFE")
            observed[relative] = candidate
    if set(observed) != set(expected):
        raise RouteError("EXACT_TOOLCHAIN_CMAKE_BUNDLE_PATH_SET_MISMATCH")
    for relative, (kind, mode, expected_bytes, expected_sha256) in expected.items():
        path = observed[relative]
        try:
            metadata = path.lstat()
        except OSError as error:
            raise RouteError("EXACT_TOOLCHAIN_CMAKE_BUNDLE_CHANGED_DURING_READ") from error
        if metadata.st_uid != os.getuid() or metadata.st_gid != os.getgid() or stat.S_IMODE(metadata.st_mode) != mode:
            raise RouteError("EXACT_TOOLCHAIN_CMAKE_BUNDLE_IDENTITY_MISMATCH")
        if kind == "directory":
            if not stat.S_ISDIR(metadata.st_mode):
                raise RouteError("EXACT_TOOLCHAIN_CMAKE_BUNDLE_IDENTITY_MISMATCH")
            continue
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise RouteError("EXACT_TOOLCHAIN_CMAKE_BUNDLE_IDENTITY_MISMATCH")
        _, content = _stable_cmake_file_bytes(
            path,
            expected_uid=os.getuid(),
            expected_gid=os.getgid(),
            error_code="EXACT_TOOLCHAIN_CMAKE_BUNDLE_CHANGED_DURING_READ",
            maximum_bytes=expected_bytes + 1_048_576,
        )
        if len(content) != expected_bytes or hashlib.sha256(content).hexdigest() != expected_sha256:
            if relative == _CMAKE_RUNTIME_MANIFEST:
                raise RouteError("EXACT_TOOLCHAIN_CMAKE_BUNDLE_MANIFEST_DRIFTED")
            raise RouteError(f"EXACT_TOOLCHAIN_CMAKE_BUNDLE_CONTENT_DRIFTED:{relative}")


def _remove_cmake_cache_root(cache_root: Path) -> None:
    try:
        if cache_root.is_symlink() or not cache_root.is_dir():
            return
        cache_root.chmod(0o700, follow_symlinks=False)
        for current, raw_directories, raw_files in os.walk(cache_root, topdown=True, followlinks=False):
            current_path = Path(current)
            current_path.chmod(0o700, follow_symlinks=False)
            for name in raw_directories:
                directory = current_path / name
                if not directory.is_symlink():
                    directory.chmod(0o700, follow_symlinks=False)
            for name in raw_files:
                path = current_path / name
                if not path.is_symlink():
                    path.chmod(0o600, follow_symlinks=False)
        shutil.rmtree(cache_root)
    except OSError:
        # Cleanup is best effort at interpreter shutdown. Runtime verification
        # never treats a cleanup result as toolchain evidence.
        return


def _clear_cmake_runtime() -> None:
    global _CMAKE_RUNTIME
    with _CMAKE_RUNTIME_LOCK:
        runtime = _CMAKE_RUNTIME
        _CMAKE_RUNTIME = None
        if runtime is not None:
            _remove_cmake_cache_root(runtime.cache_root)


atexit.register(_clear_cmake_runtime)


def _run_cmake(
    bundle: _CMakeRuntimeBundle,
    arguments: list[str],
    cwd: Path,
    *,
    executable_dirs: tuple[Path, ...] = (),
) -> subprocess.CompletedProcess[str]:
    _verify_cmake_bundle(bundle)
    try:
        return _run(
            [str(bundle.executable), *arguments],
            cwd,
            executable_dirs=executable_dirs,
        )
    finally:
        _verify_cmake_bundle(bundle)


def _exact_cmake(cwd: Path) -> _CMakeRuntimeBundle:
    global _CMAKE_RUNTIME
    with _CMAKE_RUNTIME_LOCK:
        if _CMAKE_RUNTIME is not None:
            if (
                _CMAKE_RUNTIME.source_prefix != _EXPECTED_CMAKE_PREFIX
                or _CMAKE_RUNTIME.source_identity_sha256 != _EXPECTED_CMAKE_TREE_SHA256
            ):
                _remove_cmake_cache_root(_CMAKE_RUNTIME.cache_root)
                _CMAKE_RUNTIME = None
            else:
                _verify_cmake_bundle(_CMAKE_RUNTIME)
                return _CMAKE_RUNTIME

        snapshot = _read_cmake_source_snapshot(retain_contents=True)
        runtime = _create_cmake_runtime_bundle(snapshot)
        try:
            try:
                source_after = _read_cmake_source_snapshot(retain_contents=False)
            except RouteError as error:
                raise RouteError("EXACT_TOOLCHAIN_CMAKE_SOURCE_CHANGED_AFTER_COPY") from error
            if (
                source_after.bindings != snapshot.bindings
                or source_after.identity_sha256 != snapshot.identity_sha256
                or source_after.total_file_bytes != snapshot.total_file_bytes
            ):
                raise RouteError("EXACT_TOOLCHAIN_CMAKE_SOURCE_CHANGED_AFTER_COPY")
            _verify_cmake_bundle(runtime)
            version = _run_cmake(runtime, ["--version"], cwd)
            if version.stdout.splitlines()[:1] != [_EXPECTED_CMAKE_VERSION]:
                raise RouteError("EXACT_TOOLCHAIN_MISMATCH:cmake-runtime")
        except BaseException:
            _remove_cmake_cache_root(runtime.cache_root)
            raise
        _CMAKE_RUNTIME = runtime
        return runtime


def verify_assembled_project(target_language: Language, destination: Path) -> dict[str, Any]:
    """Run a real whole-project compile/build check against an assembled project.

    Uses the same exact-toolchain contract as the per-unit harness in
    `validation.py`. This is what actually proves the assembled project is
    buildable as a whole, catching cross-unit issues (e.g. a shared build
    file rejecting one unit's construct) that per-unit validation cannot see.

    On success, `assembly-manifest.json` is rewritten with
    `build_verification_status: "PASSED"` and the command log. On failure,
    `RouteError` propagates and the manifest on disk is left untouched --
    it is not rewritten to a failure state, because "NOT_RUN" and "the last
    attempt failed" both correctly mean "do not treat this as buildable,"
    and leaving the file alone avoids ever writing a manifest that claims
    more than what actually happened.
    """
    destination = destination.expanduser()
    if destination.is_symlink() or not destination.is_dir():
        raise RouteError("ASSEMBLY_DESTINATION_UNSAFE")
    destination = destination.resolve(strict=True)
    manifest = _read_assembly_manifest(destination)
    _validate_assembly_manifest(manifest, target_language, destination)

    toolchain = exact_toolchain(target_language)
    commands: list[dict[str, Any]] = []
    toolchain_dirs = tuple(
        dict.fromkeys(
            Path(path).resolve().parent for path in (toolchain.executable, toolchain.auxiliary) if path is not None
        )
    )

    if target_language == "java":
        sources = sorted(str(path) for path in destination.glob("src/main/java/**/*.java"))
        if not sources:
            raise RouteError("ASSEMBLY_NO_JAVA_SOURCES_FOUND")
        build_directory = destination / "build" / "classes"
        build_directory.mkdir(parents=True, exist_ok=True)
        assert toolchain.auxiliary is not None
        command = [toolchain.auxiliary, "-d", str(build_directory), *sources]
        completed = _run(command, destination, executable_dirs=toolchain_dirs)
        commands.append({"command": command, "stdout": completed.stdout[-2_000:], "stderr": completed.stderr[-2_000:]})
    elif target_language == "python":
        source_directory = destination / "src"
        command = [toolchain.executable, "-m", "compileall", "-q", str(source_directory)]
        completed = _run(command, destination, executable_dirs=toolchain_dirs)
        commands.append({"command": command, "stdout": completed.stdout[-2_000:], "stderr": completed.stderr[-2_000:]})
    elif target_language == "csharp":
        command = [toolchain.executable, "build", "polyglot-migrated-library.csproj", "-c", "Release"]
        completed = _run(command, destination, executable_dirs=toolchain_dirs)
        commands.append({"command": command, "stdout": completed.stdout[-2_000:], "stderr": completed.stderr[-2_000:]})
    elif target_language == "typescript":
        assert toolchain.auxiliary is not None
        command = [toolchain.auxiliary, "-p", "tsconfig.json"]
        completed = _run(command, destination, executable_dirs=toolchain_dirs)
        commands.append({"command": command, "stdout": completed.stdout[-2_000:], "stderr": completed.stderr[-2_000:]})
    elif target_language == "javascript":
        included = manifest.get("included_units")
        if not isinstance(included, list) or not included:
            raise RouteError("ASSEMBLY_NO_JAVASCRIPT_SOURCES_FOUND")
        javascript_sources = sorted(str(unit.get("assembled_path")) for unit in included if isinstance(unit, Mapping))
        if len(javascript_sources) != len(included) or any(
            not source.endswith(".mjs") for source in javascript_sources
        ):
            raise RouteError("ASSEMBLY_JAVASCRIPT_SOURCE_SET_INVALID")
        for source in javascript_sources:
            command = [toolchain.executable, "--check", source]
            completed = _run(command, destination, executable_dirs=toolchain_dirs)
            commands.append(
                {
                    "command": command,
                    "stdout": completed.stdout[-2_000:],
                    "stderr": completed.stderr[-2_000:],
                }
            )
    elif target_language == "go":
        command = [toolchain.executable, "test", "./..."]
        completed = _run(command, destination, executable_dirs=toolchain_dirs)
        commands.append({"command": command, "stdout": completed.stdout[-2_000:], "stderr": completed.stderr[-2_000:]})
    elif target_language == "rust":
        assert toolchain.auxiliary is not None
        command = [toolchain.auxiliary, "check", "--offline"]
        completed = _run(command, destination, executable_dirs=toolchain_dirs)
        commands.append({"command": command, "stdout": completed.stdout[-2_000:], "stderr": completed.stderr[-2_000:]})
    elif target_language in {"cpp", "objc"}:
        cmake = _exact_cmake(destination)
        compiler_key = "CMAKE_CXX_COMPILER" if target_language == "cpp" else "CMAKE_OBJC_COMPILER"
        configure_arguments = [
            "-S",
            ".",
            "-B",
            "build",
            f"-D{compiler_key}={toolchain.executable}",
            "-DCMAKE_BUILD_TYPE=Release",
        ]
        configured = _run_cmake(
            cmake,
            configure_arguments,
            destination,
            executable_dirs=toolchain_dirs,
        )
        configure = [str(cmake.executable), *configure_arguments]
        commands.append(
            {
                "command": configure,
                "stdout": configured.stdout[-2_000:],
                "stderr": configured.stderr[-2_000:],
            }
        )
        build_arguments = ["--build", "build", "--config", "Release"]
        built = _run_cmake(
            cmake,
            build_arguments,
            destination,
            executable_dirs=toolchain_dirs,
        )
        build = [str(cmake.executable), *build_arguments]
        commands.append(
            {
                "command": build,
                "stdout": built.stdout[-2_000:],
                "stderr": built.stderr[-2_000:],
            }
        )
    elif target_language == "swift":
        swift = toolchain.auxiliary
        if swift is None:
            raise RouteError("EXACT_TOOLCHAIN_UNAVAILABLE:swift")
        if not Path(swift).is_file():
            raise RouteError("EXACT_TOOLCHAIN_UNAVAILABLE:swift")
        command = [swift, "build", "-c", "release", "--disable-sandbox"]
        completed = _run(command, destination, timeout=900, executable_dirs=toolchain_dirs)
        commands.append({"command": command, "stdout": completed.stdout[-2_000:], "stderr": completed.stderr[-2_000:]})
    elif target_language == "php":
        # PHP has no build step. `php -l` is the closest thing the runtime
        # offers to "this compilation unit is well formed", and it is run over
        # every assembled unit rather than once over the descriptor, because a
        # composer autoload entry never parses the file it names.
        sources = sorted(str(path.relative_to(destination)) for path in destination.glob("src/**/*.php"))
        if not sources:
            raise RouteError("ASSEMBLY_NO_PHP_SOURCES_FOUND")
        for relative in sources:
            command = [
                toolchain.executable,
                "-n",
                "-d",
                "error_reporting=E_ALL",
                "-d",
                "opcache.enable_cli=0",
                "-l",
                relative,
            ]
            completed = _run(command, destination, timeout=120, executable_dirs=toolchain_dirs)
            commands.append(
                {
                    "command": command,
                    "stdout": completed.stdout[-2_000:],
                    "stderr": completed.stderr[-2_000:],
                }
            )
    else:
        raise RouteError(f"ASSEMBLY_UNSUPPORTED_TARGET_LANGUAGE:{target_language}")

    # Build tools may generate arbitrary output trees, but they must not mutate,
    # replace, remove, add, or relabel target source files covered by this
    # assembly.  Re-read the manifest too, rather than trusting the in-memory
    # pre-build value across the compiler invocation.
    try:
        observed_manifest = _read_assembly_manifest(destination)
    except RouteError as error:
        raise RouteError("ASSEMBLY_MANIFEST_CHANGED_DURING_BUILD") from error
    if observed_manifest != manifest:
        raise RouteError("ASSEMBLY_MANIFEST_CHANGED_DURING_BUILD")
    _validate_assembly_manifest(observed_manifest, target_language, destination)
    manifest["build_verification_status"] = "PASSED"
    manifest["build_verification"] = {
        "toolchain_language": toolchain.language,
        "toolchain_version": toolchain.version,
        "commands": commands,
    }
    if target_language in {"cpp", "objc"}:
        manifest["build_verification"]["cmake_runtime"] = {
            "kind": "private-content-addressed-cmake-runtime-v1",
            "version": _EXPECTED_CMAKE_VERSION,
            "source_prefix": str(cmake.source_prefix),
            "source_identity_sha256": cmake.source_identity_sha256,
            "source_entry_count": len(cmake.source_bindings),
            "source_total_file_bytes": sum(
                binding.bytes for binding in cmake.source_bindings if binding.kind == "file"
            ),
            "bundle_manifest_bytes": len(cmake.manifest_bytes),
            "bundle_manifest_sha256": cmake.manifest_sha256,
        }
    _write_manifest(destination, manifest)
    write_assembly_deployment_guidance(destination, target_language, int(manifest["included_unit_count"]))
    return verify_assembly_closure(target_language, destination)


def write_assembly_deployment_guidance(
    destination: Path,
    target_language: Language,
    included_unit_count: int,
) -> list[str]:
    """Write local-run + cloud-publishing guidance for a build-verified assembly.

    Deliberately only called from `verify_assembled_project` after a real
    build passes -- guidance for a project that has not been shown to build
    would document steps for an artifact that does not yet demonstrably exist.
    """
    files = render_assembly_deployment_guidance(target_language, included_unit_count)
    written: list[str] = []
    for relative_path, content in files.items():
        target = destination / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(relative_path)
    return written
