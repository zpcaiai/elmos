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

import hashlib
import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable, Collection, Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .assembly_deployment_guidance import render_assembly_deployment_guidance
from .models import Language, RouteError
from .toolchains import exact_toolchain
from .validation import safe_output

SCHEMA_VERSION = "1.0.0"
MANIFEST_NAME = "assembly-manifest.json"

_UNIT_ID_PATTERN = re.compile(r"^WU-[0-9]{5}(?:-F[0-9]{3})?$")

_BUILD_FILES: dict[Language, tuple[str, ...]] = {
    "java": ("pom.xml",),
    "csharp": ("polyglot-migrated-library.csproj",),
    "python": ("pyproject.toml",),
    "typescript": ("package.json", "tsconfig.json"),
    "go": ("go.mod",),
    "rust": ("Cargo.toml", "src/lib.rs"),
    "cpp": ("CMakeLists.txt",),
    "objc": ("CMakeLists.txt",),
    "swift": ("Package.swift",),
}

_SOURCE_LAYOUTS: dict[Language, tuple[str, str, frozenset[str]]] = {
    "java": ("src/main/java", ".java", frozenset()),
    "csharp": ("src/Units", ".cs", frozenset()),
    "python": ("src/elmos_generated", ".py", frozenset({"src/elmos_generated/__init__.py"})),
    "typescript": ("src/generated", ".ts", frozenset()),
    "go": ("units", ".go", frozenset()),
    "rust": ("src", ".rs", frozenset({"src/lib.rs"})),
    "cpp": ("src", ".cpp", frozenset()),
    "objc": ("src", ".m", frozenset()),
    "swift": ("Sources", ".swift", frozenset()),
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


def _read_verified_unit_evidence(batch_output: Path, unit: dict[str, Any]) -> dict[str, Any]:
    """Validate the persisted behavior-evidence closure for one PASSED unit."""

    unit_id = _safe_unit_id(str(unit.get("id", "")))
    expected_path = f"units/{unit_id}/route-evidence.json"
    evidence_path = unit.get("evidence_path")
    expected_digest = unit.get("evidence_sha256")
    if evidence_path != expected_path:
        raise RouteError(f"ASSEMBLY_UNIT_EVIDENCE_PATH_INVALID:{unit_id}")
    if not isinstance(expected_digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", expected_digest):
        raise RouteError(f"ASSEMBLY_UNIT_EVIDENCE_DIGEST_REQUIRED:{unit_id}")
    raw_path = batch_output / expected_path
    units_root = batch_output / "units"
    unit_directory = units_root / unit_id
    if (
        units_root.is_symlink()
        or not units_root.is_dir()
        or unit_directory.is_symlink()
        or not unit_directory.is_dir()
        or raw_path.is_symlink()
        or not raw_path.is_file()
    ):
        raise RouteError(f"ASSEMBLY_UNIT_EVIDENCE_MISSING:{unit_id}")
    resolved_units = units_root.resolve(strict=True)
    resolved_unit = unit_directory.resolve(strict=True)
    resolved_path = raw_path.resolve(strict=True)
    if resolved_unit.parent != resolved_units or resolved_path.parent != resolved_unit:
        raise RouteError(f"ASSEMBLY_UNIT_EVIDENCE_MISSING:{unit_id}")
    evidence_bytes = raw_path.read_bytes()
    observed_digest = "sha256:" + hashlib.sha256(evidence_bytes).hexdigest()
    if observed_digest != expected_digest:
        raise RouteError(f"ASSEMBLY_UNIT_EVIDENCE_DRIFTED:{unit_id}")
    try:
        evidence = json.loads(evidence_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RouteError(f"ASSEMBLY_UNIT_EVIDENCE_INVALID:{unit_id}") from error
    if not isinstance(evidence, dict):
        raise RouteError(f"ASSEMBLY_UNIT_EVIDENCE_INVALID:{unit_id}")

    case_count = unit.get("behavior_case_count")
    target = evidence.get("target")
    source_validation = evidence.get("source_validation")
    target_validation = evidence.get("validation")
    if (
        evidence.get("status") not in {"PASSED", "PASSED_LOCAL_UNCERTIFIED"}
        or not isinstance(case_count, int)
        or case_count < 1
        or evidence.get("behavior_case_count") != case_count
        or evidence.get("behavior_pass_rate") != 1.0
        or not isinstance(target, dict)
        or target.get("path") != unit.get("target_path")
        or target.get("sha256") != unit.get("target_sha256")
        or not isinstance(source_validation, dict)
        or source_validation.get("status") != "PASSED"
        or source_validation.get("case_count") != case_count
        or not isinstance(source_validation.get("observations"), list)
        or len(source_validation["observations"]) != case_count
        or not isinstance(target_validation, dict)
        or target_validation.get("status") != "PASSED"
        or target_validation.get("case_count") != case_count
        or not isinstance(target_validation.get("observations"), list)
        or len(target_validation["observations"]) != case_count
    ):
        raise RouteError(f"ASSEMBLY_UNIT_EVIDENCE_NOT_CLOSED:{unit_id}")
    return evidence


def _validate_batch_report_closure(batch_report: dict[str, Any]) -> None:
    units = batch_report.get("units")
    if not isinstance(units, list) or not units:
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
    "go": _place_go,
    "rust": _place_rust,
    "cpp": _place_cpp,
    "objc": _place_objc,
    "swift": _place_swift,
}


def _expected_assembled_path(target_language: Language, namespace: str) -> str:
    paths = {
        "java": f"src/main/java/elmos/generated/{namespace}/Migrated.java",
        "csharp": f"src/Units/{namespace}/Migrated.cs",
        "python": f"src/elmos_generated/{namespace}.py",
        "typescript": f"src/generated/{namespace}.ts",
        "go": f"units/{namespace}/migrated.go",
        "rust": f"src/{namespace}.rs",
        "cpp": f"src/{namespace}/migrated.cpp",
        "objc": f"src/{namespace}/migrated.m",
        "swift": f"Sources/{namespace.capitalize()}/migrated.swift",
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


def _manifest_owned_bindings(
    manifest: Mapping[str, Any],
    target_language: Language,
    *,
    require_build_passed: bool,
) -> tuple[dict[str, tuple[str, int, str]], dict[str, tuple[int, str]]]:
    """Validate manifest structure and return its exact static build inputs."""

    included = manifest.get("included_units")
    excluded = manifest.get("excluded_units")
    build_inputs = manifest.get("build_inputs")
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("kind") != "elmos.repository-assembly-report"
        or manifest.get("status") != "ASSEMBLED"
        or manifest.get("target_language") != target_language
        or target_language not in _PLACERS
        or manifest.get("source_language") not in _PLACERS
        or manifest.get("source_language") == target_language
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
        or manifest.get("batch_status") not in {"COMPLETE", "PARTIAL"}
        or (manifest.get("batch_status") == "COMPLETE" and excluded)
        or manifest.get("external_verification_status") != "NOT_RUN"
        or manifest.get("certification_status") != "NOT_CERTIFIED"
    ):
        raise RouteError("ASSEMBLY_MANIFEST_CLOSURE_INVALID")

    seen_ids: set[str] = set()
    included_bindings: dict[str, tuple[str, int, str]] = {}
    for raw in included:
        if not isinstance(raw, Mapping):
            raise RouteError("ASSEMBLY_MANIFEST_INCLUDED_UNIT_INVALID")
        unit_id = raw.get("id")
        namespace = raw.get("namespace")
        relative = raw.get("assembled_path")
        expected_bytes = raw.get("assembled_bytes")
        expected_sha256 = raw.get("assembled_sha256")
        if (
            not isinstance(unit_id, str)
            or _UNIT_ID_PATTERN.fullmatch(unit_id) is None
            or unit_id in seen_ids
            or namespace != _namespace(unit_id)
            or not isinstance(relative, str)
            or relative != _expected_assembled_path(target_language, str(namespace))
            or type(expected_bytes) is not int
            or expected_bytes < 0
            or not isinstance(expected_sha256, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", expected_sha256) is None
            or relative in included_bindings
        ):
            raise RouteError("ASSEMBLY_MANIFEST_INCLUDED_UNIT_INVALID")
        seen_ids.add(unit_id)
        included_bindings[relative] = (unit_id, expected_bytes, expected_sha256)

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
    return included_bindings, owned_bindings


def _validate_assembly_manifest(
    manifest: dict[str, Any],
    target_language: Language,
    destination: Path,
    *,
    require_build_passed: bool = False,
) -> None:
    """Bind assembly claims to the exact regular target-source files on disk."""

    included_bindings, owned_bindings = _manifest_owned_bindings(
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
    included_bindings, owned_bindings = _manifest_owned_bindings(
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
            "  </PropertyGroup>\n"
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
    if target_language not in _PLACERS:
        raise RouteError("ASSEMBLY_UNSUPPORTED_TARGET_LANGUAGE")
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
        _read_verified_unit_evidence(batch_output, unit)
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
                "assembled_path": relative_path,
                "assembled_bytes": assembled_bytes,
                "assembled_sha256": assembled_sha256,
                "source_sha256": unit.get("checkpoint_identity", {}).get("source_sha256"),
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


def _run(command: list[str], cwd: Path, *, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["NO_COLOR"] = "1"
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=environment,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[-4_000:]
        raise RouteError(f"ASSEMBLY_BUILD_VERIFICATION_FAILED:{command[0]}:{detail}")
    return completed


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

    if target_language == "java":
        sources = sorted(str(path) for path in destination.glob("src/main/java/**/*.java"))
        if not sources:
            raise RouteError("ASSEMBLY_NO_JAVA_SOURCES_FOUND")
        build_directory = destination / "build" / "classes"
        build_directory.mkdir(parents=True, exist_ok=True)
        assert toolchain.auxiliary is not None
        command = [toolchain.auxiliary, "-d", str(build_directory), *sources]
        completed = _run(command, destination)
        commands.append({"command": command, "stdout": completed.stdout[-2_000:], "stderr": completed.stderr[-2_000:]})
    elif target_language == "python":
        source_directory = destination / "src"
        command = [toolchain.executable, "-m", "compileall", "-q", str(source_directory)]
        completed = _run(command, destination)
        commands.append({"command": command, "stdout": completed.stdout[-2_000:], "stderr": completed.stderr[-2_000:]})
    elif target_language == "csharp":
        command = [toolchain.executable, "build", "polyglot-migrated-library.csproj", "-c", "Release"]
        completed = _run(command, destination)
        commands.append({"command": command, "stdout": completed.stdout[-2_000:], "stderr": completed.stderr[-2_000:]})
    elif target_language == "typescript":
        assert toolchain.auxiliary is not None
        command = [toolchain.auxiliary, "-p", "tsconfig.json"]
        completed = _run(command, destination)
        commands.append({"command": command, "stdout": completed.stdout[-2_000:], "stderr": completed.stderr[-2_000:]})
    elif target_language == "go":
        command = [toolchain.executable, "test", "./..."]
        completed = _run(command, destination)
        commands.append({"command": command, "stdout": completed.stdout[-2_000:], "stderr": completed.stderr[-2_000:]})
    elif target_language == "rust":
        assert toolchain.auxiliary is not None
        command = [toolchain.auxiliary, "check", "--offline"]
        completed = _run(command, destination)
        commands.append({"command": command, "stdout": completed.stdout[-2_000:], "stderr": completed.stderr[-2_000:]})
    elif target_language in {"cpp", "objc"}:
        cmake = shutil.which("cmake")
        if cmake is None:
            raise RouteError("EXACT_TOOLCHAIN_UNAVAILABLE:cmake")
        compiler_key = "CMAKE_CXX_COMPILER" if target_language == "cpp" else "CMAKE_OBJC_COMPILER"
        configure = [
            cmake,
            "-S",
            ".",
            "-B",
            "build",
            f"-D{compiler_key}={toolchain.executable}",
            "-DCMAKE_BUILD_TYPE=Release",
        ]
        configured = _run(configure, destination)
        commands.append(
            {
                "command": configure,
                "stdout": configured.stdout[-2_000:],
                "stderr": configured.stderr[-2_000:],
            }
        )
        build = [cmake, "--build", "build", "--config", "Release"]
        built = _run(build, destination)
        commands.append(
            {
                "command": build,
                "stdout": built.stdout[-2_000:],
                "stderr": built.stderr[-2_000:],
            }
        )
    elif target_language == "swift":
        swift = str(Path(toolchain.executable).with_name("swift"))
        if not Path(swift).is_file():
            raise RouteError("EXACT_TOOLCHAIN_UNAVAILABLE:swift")
        command = [swift, "build", "-c", "release", "--disable-sandbox"]
        completed = _run(command, destination, timeout=900)
        commands.append({"command": command, "stdout": completed.stdout[-2_000:], "stderr": completed.stderr[-2_000:]})
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
