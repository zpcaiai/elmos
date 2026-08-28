"""Resumable repository translation pipeline and content-addressed handoff.

This module composes the existing inventory, discovery, batch and assembly
primitives without weakening any of their gates.  It is intentionally a local
engineering workflow: a COMPLETE result means that every discovered functional
obligation passed its supplied behavior cases and the assembled project built
with the exact local toolchains.  Independent and external verification remain
NOT_RUN.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any

from .assembly import (
    assemble_project,
    verify_assembled_project,
    verify_assembly_closure,
)
from .batch import REPORT_NAME as BATCH_REPORT_NAME
from .batch import run_batch
from .conversion_reporting import (
    JSON_REPORT_NAME as FUNCTION_REPORT_JSON_NAME,
)
from .conversion_reporting import (
    MARKDOWN_REPORT_NAME as FUNCTION_REPORT_MARKDOWN_NAME,
)
from .conversion_reporting import (
    build_conversion_report,
    render_conversion_markdown,
    reset_conversion_report_outputs,
    write_conversion_reports,
)
from .discovery import discover_repository, inventory_repository_incident
from .models import (
    REPOSITORY_SURFACE_LANGUAGES,
    SUPPORTED_LANGUAGES,
    Language,
    RouteError,
)
from .project_graph import build_project_graph, verify_project_graph
from .repository import plan_repository
from .safe_io import atomic_output_file, atomic_write_bytes, stable_file_digest, stable_read_bytes

SCHEMA_VERSION = "1.0.0"
REPORT_NAME = "repository-pipeline-report.json"
ARTIFACT_NAME = "repository-migration-artifact.zip"
ARTIFACT_MANIFEST_NAME = "artifact-manifest.json"
PROJECT_GRAPH_NAME = "project-graph.json"
_GRAPH_OBLIGATION_STATUSES = ("FAILED", "NOT_RUN", "PASSED", "UNKNOWN")
_CONVERSION_COVERAGE_STATUSES = ("BLOCKED", "FAILED", "NOT_RUN", "PASSED", "UNKNOWN")
#: Surfaces a consumer may read as "this run completed".  A failed run must
#: not leave any of them from an earlier one visible.
_FINAL_CLAIM_NAMES = (ARTIFACT_NAME, REPORT_NAME, ARTIFACT_MANIFEST_NAME)
_PRIOR_CLAIM_SUFFIX = ".previous-handoff"
CASES_MANIFEST_NAME = "behavior-cases-manifest.json"
_MAX_CASE_FILES = 10_000
_MAX_CASE_BYTES = 64 * 1024 * 1024
MAX_ARTIFACT_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
MAX_ARTIFACT_COMPRESSED_BYTES = 256 * 1024 * 1024
_MAX_PIPELINE_JSON_BYTES = 64 * 1024 * 1024
# SwiftPM's `.build` tree is a disposable compiler cache.  It can contain
# toolchain-owned symlinks (for example `.build/release`) and is never part of
# the published migration artifact.  Other symlinks in the artifact tree
# remain unsafe and are still rejected below.
_ARTIFACT_CACHE_DIRECTORIES = frozenset({".build"})



def _validate_handoff_targets(output: Path) -> None:
    for name in (
        ARTIFACT_NAME,
        REPORT_NAME,
        ARTIFACT_MANIFEST_NAME,
        PROJECT_GRAPH_NAME,
        f"{ARTIFACT_NAME}.tmp",
        f"{PROJECT_GRAPH_NAME}.tmp",
        *(f"{claim}{_PRIOR_CLAIM_SUFFIX}" for claim in _FINAL_CLAIM_NAMES),
    ):
        candidate = output / name
        if candidate.is_symlink():
            raise RouteError("PIPELINE_OUTPUT_UNSAFE")
        if candidate.exists() and not candidate.is_file():
            raise RouteError("PIPELINE_OUTPUT_UNSAFE")


def _quarantine_prior_final_claims(output: Path) -> list[tuple[Path, Path]]:
    """Atomically remove prior COMPLETE surfaces from their public paths."""

    moved: list[tuple[Path, Path]] = []
    try:
        for name in _FINAL_CLAIM_NAMES:
            final = output / name
            previous = output / f"{name}{_PRIOR_CLAIM_SUFFIX}"
            if previous.exists():
                previous.unlink()
            if final.exists():
                final.replace(previous)
                moved.append((final, previous))
    except OSError:
        for final, previous in reversed(moved):
            if previous.is_file() and not final.exists():
                previous.replace(final)
        raise
    return moved


def _discard_prior_final_claims(moved: list[tuple[Path, Path]]) -> None:
    for _, previous in moved:
        if previous.is_symlink() or (previous.exists() and not previous.is_file()):
            raise RouteError("PIPELINE_PRIOR_HANDOFF_INVALID")
        previous.unlink(missing_ok=True)


def _invalidate_current_final_claims(output: Path) -> None:
    for name in _FINAL_CLAIM_NAMES:
        candidate = output / name
        if candidate.is_symlink() or (candidate.exists() and not candidate.is_file()):
            raise RouteError("PIPELINE_OUTPUT_UNSAFE")
        candidate.unlink(missing_ok=True)


def _write_json(path: Path, value: dict[str, Any]) -> None:
    content = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    atomic_write_bytes(
        path,
        content,
        max_bytes=_MAX_PIPELINE_JSON_BYTES,
        unsafe_error="PIPELINE_OUTPUT_UNSAFE",
        limit_error="PIPELINE_JSON_LIMIT_EXCEEDED",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(64 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_file(
    path: Path,
    error_code: str,
    *,
    max_bytes: int,
    limit_error: str,
) -> tuple[int, str]:
    return stable_file_digest(
        path,
        max_bytes=max_bytes,
        unsafe_error=f"{error_code}_UNSAFE",
        changed_error=f"{error_code}_CHANGED_DURING_READ",
        limit_error=limit_error,
    )


def _cases_manifest(cases: Path, plan: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Bind every case byte and every expected missing-case state."""
    root = cases.resolve(strict=True)
    inventory: list[dict[str, Any]] = []
    total_bytes = 0
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        safe_directories: list[str] = []
        for directory in sorted(directories):
            candidate = current_path / directory
            if candidate.is_symlink():
                raise RouteError("BEHAVIOR_CASES_SYMLINK_REJECTED")
            safe_directories.append(directory)
        directories[:] = safe_directories
        for name in sorted(files):
            candidate = current_path / name
            if candidate.is_symlink():
                raise RouteError("BEHAVIOR_CASES_SYMLINK_REJECTED")
            relative = candidate.relative_to(root).as_posix()
            if any(ord(character) < 32 or ord(character) == 127 for character in relative):
                raise RouteError("BEHAVIOR_CASES_PATH_INVALID")
            size, digest = _stable_file(
                candidate,
                "BEHAVIOR_CASES_FILE",
                max_bytes=max(0, _MAX_CASE_BYTES - total_bytes),
                limit_error="BEHAVIOR_CASES_MANIFEST_LIMIT_EXCEEDED",
            )
            total_bytes += size
            if len(inventory) >= _MAX_CASE_FILES or total_bytes > _MAX_CASE_BYTES:
                raise RouteError("BEHAVIOR_CASES_MANIFEST_LIMIT_EXCEEDED")
            inventory.append({"path": relative, "bytes": size, "sha256": digest})
    inventory.sort(key=lambda item: str(item["path"]))
    by_path = {str(item["path"]): item for item in inventory}
    expected: list[dict[str, Any]] = []
    for unit in plan.get("work_units", []):
        unit_id = str(unit.get("id", ""))
        relative = f"{unit_id}.json"
        entry = by_path.get(relative)
        expected.append(
            {
                "work_unit_id": unit_id,
                "path": relative,
                "status": "PRESENT" if entry else "MISSING",
                "bytes": entry["bytes"] if entry else None,
                "sha256": entry["sha256"] if entry else None,
            }
        )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "kind": "elmos.behavior-cases-manifest",
        "snapshot_sha256": plan.get("snapshot_sha256"),
        "expected": expected,
        "inventory": inventory,
    }
    digest = hashlib.sha256(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return manifest, digest


def _owned_directory(output: Path, child: str) -> Path:
    if not child or Path(child).name != child:
        raise RouteError("PIPELINE_PATH_CONFINEMENT_FAILED")
    root = output.resolve(strict=True)
    candidate = output / child
    if candidate.is_symlink() or candidate.parent.resolve(strict=True) != root:
        raise RouteError("PIPELINE_PATH_CONFINEMENT_FAILED")
    if candidate.exists() and candidate.resolve(strict=True).parent != root:
        raise RouteError("PIPELINE_PATH_CONFINEMENT_FAILED")
    return candidate


def _reset_owned_directory(output: Path, child: str) -> Path:
    candidate = _owned_directory(output, child)
    if candidate.exists():
        if candidate.is_symlink() or not candidate.is_dir():
            raise RouteError("PIPELINE_OUTPUT_UNSAFE")
        shutil.rmtree(candidate)
    return candidate


def _remove_stale_handoff(output: Path) -> None:
    reset_conversion_report_outputs(output)
    for name in (
        ARTIFACT_NAME,
        REPORT_NAME,
        ARTIFACT_MANIFEST_NAME,
        f"{FUNCTION_REPORT_JSON_NAME}.tmp",
        f"{FUNCTION_REPORT_MARKDOWN_NAME}.tmp",
        f"{ARTIFACT_NAME}.tmp",
    ):
        candidate = output / name
        if candidate.is_symlink():
            raise RouteError("PIPELINE_OUTPUT_UNSAFE")
        if candidate.exists():
            if not candidate.is_file():
                raise RouteError("PIPELINE_OUTPUT_UNSAFE")
            candidate.unlink()


def _artifact_inventory(output: Path) -> list[dict[str, Any]]:
    excluded = {ARTIFACT_NAME, f"{ARTIFACT_NAME}.tmp", REPORT_NAME, ARTIFACT_MANIFEST_NAME}
    root = output.resolve(strict=True)
    files: list[dict[str, Any]] = []
    total_bytes = 0
    for current, directories, names in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        safe_directories: list[str] = []
        for name in sorted(directories):
            candidate = current_path / name
            if candidate.is_symlink():
                raise RouteError("PIPELINE_ARTIFACT_SOURCE_UNSAFE")
            if name in _ARTIFACT_CACHE_DIRECTORIES:
                continue
            safe_directories.append(name)
        directories[:] = safe_directories
        for name in sorted(names):
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            if relative in excluded:
                continue
            if path.is_symlink() or not path.is_file():
                raise RouteError("PIPELINE_ARTIFACT_SOURCE_UNSAFE")
            if any(ord(character) < 32 or ord(character) == 127 for character in relative):
                raise RouteError("PIPELINE_ARTIFACT_PATH_INVALID")
            size, digest = _stable_file(
                path,
                "PIPELINE_ARTIFACT_SOURCE",
                max_bytes=max(0, MAX_ARTIFACT_UNCOMPRESSED_BYTES - total_bytes),
                limit_error="PIPELINE_ARTIFACT_UNCOMPRESSED_LIMIT_EXCEEDED",
            )
            total_bytes += size
            if total_bytes > MAX_ARTIFACT_UNCOMPRESSED_BYTES:
                raise RouteError("PIPELINE_ARTIFACT_UNCOMPRESSED_LIMIT_EXCEEDED")
            files.append({"path": relative, "bytes": size, "sha256": digest})
    files.sort(key=lambda item: str(item["path"]))
    if not files:
        raise RouteError("PIPELINE_ARTIFACT_EMPTY")
    return files


def _bound_artifact_bytes(output: Path, entry: dict[str, Any]) -> bytes:
    relative = str(entry.get("path", ""))
    if (
        not relative
        or relative.startswith("/")
        or "\\" in relative
        or any(part in {"", ".", ".."} for part in relative.split("/"))
        or any(ord(character) < 32 or ord(character) == 127 for character in relative)
    ):
        raise RouteError("PIPELINE_ARTIFACT_PATH_INVALID")
    root = output.resolve(strict=True)
    current = root
    for part in Path(relative).parts:
        current /= part
        if current.is_symlink():
            raise RouteError("PIPELINE_ARTIFACT_SOURCE_UNSAFE")
    try:
        source = (root / relative).resolve(strict=True)
        source.relative_to(root)
    except (FileNotFoundError, ValueError) as error:
        raise RouteError("PIPELINE_ARTIFACT_SOURCE_UNSAFE") from error
    expected_bytes = entry.get("bytes")
    expected_sha256 = str(entry.get("sha256", ""))
    if (
        not isinstance(expected_bytes, int)
        or expected_bytes < 0
        or expected_bytes > MAX_ARTIFACT_UNCOMPRESSED_BYTES
        or len(expected_sha256) != 64
        or any(character not in "0123456789abcdef" for character in expected_sha256)
    ):
        raise RouteError("PIPELINE_ARTIFACT_DESCRIPTOR_MISMATCH")
    content = stable_read_bytes(
        source,
        max_bytes=expected_bytes,
        unsafe_error="PIPELINE_ARTIFACT_SOURCE_UNSAFE",
        changed_error="PIPELINE_ARTIFACT_SOURCE_CHANGED_DURING_READ",
        limit_error="PIPELINE_ARTIFACT_DESCRIPTOR_MISMATCH",
    )
    if len(content) != expected_bytes or hashlib.sha256(content).hexdigest() != expected_sha256:
        raise RouteError("PIPELINE_ARTIFACT_DESCRIPTOR_MISMATCH")
    return content


def _verify_zip_content(content: bytes, entries: list[dict[str, Any]]) -> None:
    expected_paths = [str(entry["path"]) for entry in entries]
    try:
        with zipfile.ZipFile(io.BytesIO(content), "r") as bundle:
            if bundle.namelist() != expected_paths or len(set(bundle.namelist())) != len(expected_paths):
                raise RouteError("PIPELINE_ARTIFACT_ARCHIVE_MANIFEST_MISMATCH")
            for entry in entries:
                archived = bundle.read(str(entry["path"]))
                if len(archived) != entry["bytes"] or hashlib.sha256(archived).hexdigest() != entry["sha256"]:
                    raise RouteError("PIPELINE_ARTIFACT_ARCHIVE_MANIFEST_MISMATCH")
    except (KeyError, zipfile.BadZipFile) as error:
        raise RouteError("PIPELINE_ARTIFACT_ARCHIVE_INVALID") from error


def _verify_zip_entries(archive: Path, entries: list[dict[str, Any]]) -> bytes:
    content = stable_read_bytes(
        archive,
        max_bytes=MAX_ARTIFACT_COMPRESSED_BYTES,
        unsafe_error="PIPELINE_ARTIFACT_ARCHIVE_UNSAFE",
        changed_error="PIPELINE_ARTIFACT_ARCHIVE_CHANGED_DURING_READ",
        limit_error="PIPELINE_ARTIFACT_COMPRESSED_LIMIT_EXCEEDED",
    )
    _verify_zip_content(content, entries)
    return content


def _write_deterministic_zip(output: Path, paths: list[dict[str, Any]]) -> tuple[Path, int, str]:
    archive = output / ARTIFACT_NAME
    ordered = sorted(paths, key=lambda entry: str(entry.get("path", "")))
    path_names = [str(entry.get("path", "")) for entry in ordered]
    if len(path_names) != len(set(path_names)) or ARTIFACT_MANIFEST_NAME not in path_names:
        raise RouteError("PIPELINE_ARTIFACT_DESCRIPTOR_SET_INVALID")
    if sum(int(entry.get("bytes", -1)) for entry in ordered) > MAX_ARTIFACT_UNCOMPRESSED_BYTES:
        raise RouteError("PIPELINE_ARTIFACT_UNCOMPRESSED_LIMIT_EXCEEDED")
    published = False
    completed = False
    try:
        with atomic_output_file(
            archive,
            max_bytes=MAX_ARTIFACT_COMPRESSED_BYTES,
            unsafe_error="PIPELINE_ARTIFACT_ARCHIVE_UNSAFE",
            limit_error="PIPELINE_ARTIFACT_COMPRESSED_LIMIT_EXCEEDED",
        ) as handle:
            with zipfile.ZipFile(handle, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
                for entry in ordered:
                    relative = str(entry["path"])
                    content = _bound_artifact_bytes(output, entry)
                    info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o100644 << 16
                    bundle.writestr(info, content)
            handle.flush()
            handle.seek(0)
            temporary_content = handle.read(MAX_ARTIFACT_COMPRESSED_BYTES + 1)
            if len(temporary_content) > MAX_ARTIFACT_COMPRESSED_BYTES:
                raise RouteError("PIPELINE_ARTIFACT_COMPRESSED_LIMIT_EXCEEDED")
            _verify_zip_content(temporary_content, ordered)
        published = True
        current_inventory = _artifact_inventory(output)
        expected_inventory = [entry for entry in ordered if entry["path"] != ARTIFACT_MANIFEST_NAME]
        if current_inventory != expected_inventory:
            raise RouteError("PIPELINE_ARTIFACT_INVENTORY_CHANGED_DURING_ARCHIVE")
        for entry in ordered:
            _bound_artifact_bytes(output, entry)
        archive_bytes = _verify_zip_entries(archive, ordered)
        completed = True
        return archive, len(archive_bytes), hashlib.sha256(archive_bytes).hexdigest()
    finally:
        if published and not completed and archive.exists():
            if archive.is_symlink() or not archive.is_file():
                raise RouteError("PIPELINE_ARTIFACT_ARCHIVE_UNSAFE")
            archive.unlink()


def _reportable_assembly_failure(error: RouteError) -> bool:
    reason = str(error)
    return reason.startswith(
        (
            "ASSEMBLY_UNSUPPORTED_TARGET_LANGUAGE",
            "ASSEMBLY_BUILD_VERIFICATION_FAILED",
            "ASSEMBLY_BUILD_TIMEOUT",
            "ASSEMBLY_RUNTIME_",
            "EXACT_TOOLCHAIN_",
        )
    )


def _assembly_failure_status(error: RouteError) -> str:
    return "NOT_RUN" if str(error).startswith("EXACT_TOOLCHAIN_") else "FAILED"


def _reportable_discovery_incident(error: RouteError) -> bool:
    return str(error).startswith(
        (
            "EXACT_TOOLCHAIN_",
            "NATIVE_ANALYZER_FAILED",
            "NATIVE_ANALYZER_CONTRACT_INVALID",
            "NATIVE_ANALYZER_INVALID_JSON",
            "NATIVE_ANALYZER_OBJECT_REQUIRED",
            "NATIVE_ANALYZER_TIMEOUT",
            "SWIFT_ANALYZER_BUILD_FAILED",
            "SWIFT_ANALYZER_BUILD_TIMEOUT",
            "TYPESCRIPT_ANALYZER_BUILD_FAILED",
            "TYPESCRIPT_ANALYZER_BUILD_TIMEOUT",
        )
    )


def _reportable_artifact_capacity(error: RouteError) -> bool:
    return str(error).split(":", 1)[0] in {
        "PIPELINE_ARTIFACT_UNCOMPRESSED_LIMIT_EXCEEDED",
        "PIPELINE_ARTIFACT_COMPRESSED_LIMIT_EXCEEDED",
    }


def _incident_batch(discovery: dict[str, Any], reason: str) -> dict[str, Any]:
    reason_code = reason.split(":", 1)[0][:120]
    units = [
        {
            "id": result["id"],
            "source_path": result["source_path"],
            "status": "SKIPPED_NOT_READY",
            "reason_code": reason_code,
            "reason": reason[:2_000],
            "failure_stage": "ANALYSIS",
            "analysis_incident": True,
        }
        for result in discovery["results"]
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "elmos.repository-batch-report",
        "status": "PARTIAL",
        "repository_ref": discovery.get("repository_ref"),
        "snapshot_sha256": discovery.get("snapshot_sha256"),
        "route_id": discovery.get("route_id"),
        "profile": discovery.get("profile"),
        "work_unit_count": len(units),
        "selected_unit_count": len(units),
        "attempted_count": 0,
        "unattempted_count": len(units),
        "resumed_count": 0,
        "status_counts": {"SKIPPED_NOT_READY": len(units)},
        "units": units,
        "execution_status": "NOT_RUN",
        "external_verification_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
    }


def _commit_owned_directory(output: Path, staging_name: str, final_name: str) -> Path:
    staging = _owned_directory(output, staging_name)
    final = _owned_directory(output, final_name)
    backup = _owned_directory(output, f"{final_name}.previous")
    if not staging.is_dir() or staging.is_symlink():
        raise RouteError("PIPELINE_STAGING_DIRECTORY_INVALID")
    if backup.exists():
        if backup.is_symlink() or not backup.is_dir():
            raise RouteError("PIPELINE_OUTPUT_UNSAFE")
        shutil.rmtree(backup)
    if final.exists():
        if final.is_symlink() or not final.is_dir():
            raise RouteError("PIPELINE_OUTPUT_UNSAFE")
        final.replace(backup)
    try:
        staging.replace(final)
    except OSError:
        if backup.exists() and not final.exists():
            backup.replace(final)
        raise
    if backup.exists():
        shutil.rmtree(backup)
    return final


def _project_graph_summary(graph: dict[str, object]) -> dict[str, Any]:
    if not verify_project_graph(graph):
        raise RouteError("PROJECT_GRAPH_DIGEST_INVALID")
    graph_id = graph.get("graph_id")
    graph_sha256 = graph.get("graph_sha256")
    snapshot_sha256 = graph.get("snapshot_sha256")
    repository_complete = graph.get("repository_complete")
    completeness_status = graph.get("completeness_status")
    obligations = graph.get("diagnostic_obligations")
    inventory = graph.get("inventory")
    if not isinstance(graph_id, str) or not isinstance(graph_sha256, str):
        raise RouteError("PROJECT_GRAPH_IDENTITY_INVALID")
    if (
        not isinstance(snapshot_sha256, str)
        or len(snapshot_sha256) != 64
        or any(character not in "0123456789abcdef" for character in snapshot_sha256)
    ):
        raise RouteError("PROJECT_GRAPH_SNAPSHOT_INVALID")
    if not isinstance(repository_complete, bool):
        raise RouteError("PROJECT_GRAPH_COMPLETENESS_INVALID")
    if completeness_status not in {"COMPLETE", "INCOMPLETE"}:
        raise RouteError("PROJECT_GRAPH_COMPLETENESS_INVALID")
    if not isinstance(obligations, list) or not isinstance(inventory, dict):
        raise RouteError("PROJECT_GRAPH_OBLIGATIONS_INVALID")
    excluded_count = inventory.get("excluded_count")
    excluded_entries = inventory.get("excluded_entries")
    if (
        not isinstance(excluded_count, int)
        or excluded_count < 0
        or not isinstance(excluded_entries, list)
        or excluded_count != len(excluded_entries)
    ):
        raise RouteError("PROJECT_GRAPH_EXCLUDED_INVENTORY_INVALID")
    for entry in excluded_entries:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("path"), str)
            or not isinstance(entry.get("reason"), str)
            or entry.get("verification_status") != "NOT_RUN"
        ):
            raise RouteError("PROJECT_GRAPH_EXCLUDED_INVENTORY_INVALID")

    status_counts = {status: 0 for status in _GRAPH_OBLIGATION_STATUSES}
    for obligation in obligations:
        if not isinstance(obligation, dict):
            raise RouteError("PROJECT_GRAPH_OBLIGATION_INVALID")
        status = obligation.get("verification_status")
        if not isinstance(status, str) or status not in status_counts:
            raise RouteError("PROJECT_GRAPH_OBLIGATION_STATUS_INVALID")
        if obligation.get("blocks_repository_complete") is not True:
            raise RouteError("PROJECT_GRAPH_OBLIGATION_NOT_BLOCKING")
        status_counts[str(status)] += 1

    if repository_complete != (not obligations):
        raise RouteError("PROJECT_GRAPH_COMPLETENESS_CONTRADICTORY")
    if repository_complete != (completeness_status == "COMPLETE"):
        raise RouteError("PROJECT_GRAPH_COMPLETENESS_CONTRADICTORY")
    return {
        "path": PROJECT_GRAPH_NAME,
        "graph_id": graph_id,
        "graph_sha256": graph_sha256,
        "snapshot_sha256": snapshot_sha256,
        "repository_complete": repository_complete,
        "completeness_status": completeness_status,
        "obligation_count": len(obligations),
        "obligation_status_counts": status_counts,
        "excluded_count": excluded_count,
        "excluded_status": "NOT_RUN" if excluded_count else "PASSED",
        "verification_status": "PASSED",
    }


def _neutral_project_snapshot(graph: dict[str, object]) -> str:
    """Bind invocation-time repository bytes without contextual language labels.

    React discovery legitimately reclassifies project-local ``.ts`` files from
    TypeScript to React.  Comparing the graph's own snapshot across that
    boundary would therefore report a false drift, while taking the
    post-discovery graph as the baseline would let changes during compiler
    discovery disappear into a new snapshot.  This identity includes every
    scanned file and excluded entry, but intentionally omits semantic labels
    and discovery-derived attributes.
    """

    _project_graph_summary(graph)
    nodes = graph.get("nodes")
    inventory = graph.get("inventory")
    if not isinstance(nodes, list) or not isinstance(inventory, dict):
        raise RouteError("PROJECT_GRAPH_NEUTRAL_SNAPSHOT_INVALID")
    files: list[list[object]] = []
    seen: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict) or node.get("kind") != "file":
            continue
        path = node.get("path")
        attributes = node.get("attributes")
        if not isinstance(path, str) or not isinstance(attributes, dict) or path in seen:
            raise RouteError("PROJECT_GRAPH_NEUTRAL_SNAPSHOT_INVALID")
        seen.add(path)
        files.append(
            [
                path,
                attributes.get("role"),
                attributes.get("sha256"),
                attributes.get("byte_count"),
                attributes.get("read_status"),
            ]
        )
    excluded = inventory.get("excluded_entries")
    if not isinstance(excluded, list):
        raise RouteError("PROJECT_GRAPH_NEUTRAL_SNAPSHOT_INVALID")
    excluded_identity: list[list[object]] = []
    for entry in excluded:
        if not isinstance(entry, dict):
            raise RouteError("PROJECT_GRAPH_NEUTRAL_SNAPSHOT_INVALID")
        excluded_identity.append(
            [entry.get("path"), entry.get("reason"), entry.get("verification_status")]
        )
    payload = {
        "files": sorted(files, key=lambda item: str(item[0])),
        "excluded_entries": sorted(excluded_identity, key=lambda item: str(item[0])),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _write_and_verify_project_graph(output: Path, graph: dict[str, object]) -> dict[str, Any]:
    expected_summary = _project_graph_summary(graph)
    graph_path = output / PROJECT_GRAPH_NAME
    _write_json(graph_path, graph)
    try:
        observed = json.loads(graph_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RouteError("PROJECT_GRAPH_FILE_INVALID") from error
    if not isinstance(observed, dict) or observed != graph:
        raise RouteError("PROJECT_GRAPH_FILE_MISMATCH")
    observed_graph = {str(key): value for key, value in observed.items()}
    observed_summary = _project_graph_summary(observed_graph)
    if observed_summary != expected_summary:
        raise RouteError("PROJECT_GRAPH_FILE_MISMATCH")
    return observed_summary


def _bind_project_graph_to_plan(graph: dict[str, object], plan: dict[str, Any]) -> None:
    if graph.get("repository_ref") != plan.get("repository_ref"):
        raise RouteError("PROJECT_GRAPH_REPOSITORY_REF_MISMATCH")
    graph_languages = graph.get("supported_languages")
    if (
        not isinstance(graph_languages, list)
        or len(graph_languages) != len(REPOSITORY_SURFACE_LANGUAGES)
        or any(not isinstance(language, str) for language in graph_languages)
        or len(set(graph_languages)) != len(graph_languages)
        or set(graph_languages) != set(REPOSITORY_SURFACE_LANGUAGES)
    ):
        raise RouteError("PROJECT_GRAPH_LANGUAGE_SET_MISMATCH")
    nodes = graph.get("nodes")
    work_units = plan.get("work_units")
    source_language = plan.get("source_language")
    if (
        not isinstance(nodes, list)
        or not isinstance(work_units, list)
        or source_language not in REPOSITORY_SURFACE_LANGUAGES
    ):
        raise RouteError("PROJECT_GRAPH_PLAN_BINDING_INVALID")

    file_bindings: dict[str, tuple[str, str]] = {}
    for node in nodes:
        if not isinstance(node, dict) or node.get("kind") != "file":
            continue
        path = node.get("path")
        language = node.get("language")
        attributes = node.get("attributes")
        if not isinstance(path, str) or not isinstance(attributes, dict):
            raise RouteError("PROJECT_GRAPH_FILE_NODE_INVALID")
        digest = attributes.get("sha256")
        if not isinstance(digest, str) or language not in REPOSITORY_SURFACE_LANGUAGES:
            continue
        binding = (digest, str(language))
        previous = file_bindings.get(path)
        if previous is not None and previous != binding:
            raise RouteError("PROJECT_GRAPH_FILE_IDENTITY_CONTRADICTORY")
        file_bindings[path] = binding

    for unit in work_units:
        if not isinstance(unit, dict):
            raise RouteError("PROJECT_GRAPH_PLAN_BINDING_INVALID")
        path = unit.get("source_path")
        digest = unit.get("source_sha256")
        if not isinstance(path, str) or not isinstance(digest, str):
            raise RouteError("PROJECT_GRAPH_PLAN_BINDING_INVALID")
        if file_bindings.get(path) != (digest, source_language):
            raise RouteError(f"PROJECT_GRAPH_PLAN_SOURCE_MISMATCH:{path}")


def _conversion_coverage_summary(
    graph: dict[str, object],
    discovery: dict[str, Any],
    batch: dict[str, Any],
) -> dict[str, Any]:
    """Bind every compiler-indexed source subject to one exact batch outcome."""

    source_language = discovery.get("source_language")
    status_counts = {status: 0 for status in _CONVERSION_COVERAGE_STATUSES}
    if source_language not in REPOSITORY_SURFACE_LANGUAGES:
        raise RouteError("CONVERSION_COVERAGE_LANGUAGE_INVALID")

    nodes = graph.get("nodes")
    discovery_results = discovery.get("results")
    batch_units = batch.get("units")
    if not isinstance(nodes, list) or not isinstance(discovery_results, list) or not isinstance(batch_units, list):
        raise RouteError("CONVERSION_COVERAGE_INPUT_INVALID")

    subjects: dict[str, dict[str, Any]] = {}
    module_statuses: list[str] = []
    for node in nodes:
        if not isinstance(node, dict) or node.get("language") != source_language:
            continue
        if node.get("kind") == "module":
            module_attributes = node.get("attributes")
            if not isinstance(module_attributes, dict):
                raise RouteError("CONVERSION_COVERAGE_MODULE_INVALID")
            module_status = module_attributes.get("semantic_index_status")
            if not isinstance(module_status, str):
                raise RouteError("CONVERSION_COVERAGE_MODULE_INVALID")
            module_statuses.append(module_status)
            continue
        if node.get("kind") not in {"symbol", "effect"}:
            continue
        attributes = node.get("attributes")
        if not isinstance(attributes, dict):
            raise RouteError("CONVERSION_COVERAGE_SUBJECT_INVALID")
        if attributes.get("conversion_coverage_requirement") != "REQUIRED":
            continue
        coverage_key = attributes.get("coverage_key")
        if not isinstance(coverage_key, str) or not coverage_key.startswith(f"{source_language}:sha256:"):
            raise RouteError("CONVERSION_COVERAGE_KEY_INVALID")
        if coverage_key in subjects:
            raise RouteError("CONVERSION_COVERAGE_KEY_DUPLICATED")
        subjects[coverage_key] = {
            "coverage_key": coverage_key,
            "node_id": node.get("id"),
            "path": node.get("path"),
            "qualified_name": attributes.get("qualified_name"),
            "subject_kind": attributes.get("subject_kind"),
            "source_location": node.get("source_location"),
        }

    ready_units: dict[str, list[str]] = {}
    blockers: dict[str, list[str]] = {}
    for result in discovery_results:
        if not isinstance(result, dict):
            raise RouteError("CONVERSION_COVERAGE_DISCOVERY_INVALID")
        coverage_key = result.get("coverage_key")
        if not isinstance(coverage_key, str):
            source_symbol = result.get("source_symbol")
            if isinstance(source_symbol, dict):
                coverage_key = source_symbol.get("coverage_key")
        if not isinstance(coverage_key, str):
            continue
        unit_id = result.get("id")
        if not isinstance(unit_id, str):
            raise RouteError("CONVERSION_COVERAGE_DISCOVERY_INVALID")
        if result.get("verdict") == "READY":
            ready_units.setdefault(coverage_key, []).append(unit_id)
        else:
            blockers.setdefault(coverage_key, []).append(
                str(result.get("blocker_code") or result.get("reason") or "EXPLICIT_BLOCKER")
            )

    outcome_by_id: dict[str, str] = {}
    for unit in batch_units:
        if not isinstance(unit, dict):
            raise RouteError("CONVERSION_COVERAGE_BATCH_INVALID")
        unit_id = unit.get("id")
        unit_status = unit.get("status")
        if not isinstance(unit_id, str) or not isinstance(unit_status, str):
            raise RouteError("CONVERSION_COVERAGE_BATCH_INVALID")
        if unit_id in outcome_by_id:
            raise RouteError("CONVERSION_COVERAGE_BATCH_UNIT_DUPLICATED")
        outcome_by_id[unit_id] = unit_status

    coverage_results: list[dict[str, Any]] = []
    for coverage_key, subject in sorted(subjects.items()):
        subject_blockers = sorted(set(blockers.get(coverage_key, [])))
        subject_units = sorted(set(ready_units.get(coverage_key, [])))
        coverage_unit_id: str | None = subject_units[0] if len(subject_units) == 1 else None
        batch_status = outcome_by_id.get(coverage_unit_id) if coverage_unit_id is not None else None
        if subject_blockers:
            status = "BLOCKED"
            reason = "EXPLICIT_DISCOVERY_BLOCKER"
        elif len(subject_units) != 1:
            status = "UNKNOWN"
            reason = "READY_UNIT_COVERAGE_MISSING_OR_AMBIGUOUS"
        elif batch_status == "PASSED":
            status = "PASSED"
            reason = None
        elif batch_status == "FAILED":
            status = "FAILED"
            reason = "BATCH_UNIT_FAILED"
        elif batch_status in {"SKIPPED_NOT_READY", "SKIPPED_NO_CASES"}:
            status = "NOT_RUN"
            reason = "BATCH_UNIT_NOT_EXECUTED"
        else:
            status = "UNKNOWN"
            reason = "BATCH_OUTCOME_MISSING_OR_UNKNOWN"
        status_counts[status] += 1
        coverage_results.append(
            {
                **subject,
                "status": status,
                "reason": reason,
                "ready_unit_ids": subject_units,
                "batch_status": batch_status,
                "blocker_codes": subject_blockers,
            }
        )

    inventory_status = (
        "PASSED"
        if module_statuses and all(status == "PASSED" for status in module_statuses)
        else "FAILED"
        if any(status == "FAILED" for status in module_statuses)
        else "NOT_RUN"
    )
    complete = (
        inventory_status == "PASSED" and bool(coverage_results) and status_counts["PASSED"] == len(coverage_results)
    )
    return {
        "profile": "compiler-semantic-symbol-coverage-v1",
        "source_language": source_language,
        "inventory_status": inventory_status,
        "status": "PASSED" if complete else "LIMITED",
        "complete": complete,
        "subject_count": len(coverage_results),
        "status_counts": status_counts,
        "subjects": coverage_results,
        "reason": (
            None
            if complete
            else "COMPILER_SEMANTIC_SYMBOL_INDEX_NOT_RUN"
            if inventory_status == "NOT_RUN"
            else "NOT_EVERY_INDEXED_SUBJECT_PASSED"
        ),
    }


def _run_repository_pipeline_attempt(
    repository_root: Path,
    repository_ref: str,
    source_language: Language,
    target_language: Language,
    cases_directory: Path,
    output: Path,
) -> dict[str, Any]:
    """Run and package a bounded repository translation.

    The output directory is a durable checkpoint boundary.  Batch execution
    resumes from its existing checkpoint; inventory and discovery are
    recomputed from the read-only source on every invocation so source drift is
    detected before prior work is reused.

    Two drift detectors run side by side here and are deliberately not
    interchangeable.  Re-inventorying the plan and the behaviour cases catches
    byte, name and presence changes in the two *declared* inputs.  The neutral
    project-graph snapshot catches a change anywhere in the scanned tree,
    including files no plan ever selected.  Either one firing invalidates the
    run; neither subsumes the other.

    Failure handling is white-listed, not permissive.  A discovery or assembly
    failure becomes a reportable PARTIAL only when one of the ``_reportable_*``
    predicates recognises it.  Confinement, digest and unsafe-output failures
    still raise and can never be packaged as trustworthy evidence.
    """
    if source_language not in SUPPORTED_LANGUAGES or target_language not in SUPPORTED_LANGUAGES:
        raise RouteError("UNSUPPORTED_LANGUAGE")
    if source_language == target_language:
        raise RouteError("SOURCE_AND_TARGET_MUST_DIFFER")
    if output.exists() and (output.is_symlink() or not output.is_dir()):
        raise RouteError("PIPELINE_OUTPUT_UNSAFE")
    output.mkdir(parents=True, exist_ok=True)
    _remove_stale_handoff(output)
    root = repository_root.resolve(strict=True)
    cases = cases_directory.resolve(strict=True)
    if repository_root.is_symlink() or not root.is_dir():
        raise RouteError("REPOSITORY_DIRECTORY_INVALID")
    if cases_directory.is_symlink() or not cases.is_dir():
        raise RouteError("BEHAVIOR_CASES_DIRECTORY_INVALID")

    invocation_graph = build_project_graph(root, repository_ref)
    invocation_snapshot = _neutral_project_snapshot(invocation_graph)

    plan = plan_repository(root, repository_ref, source_language, target_language)
    cases_manifest, cases_manifest_sha256 = _cases_manifest(cases, plan)

    discovery_incident: str | None = None
    discovery: dict[str, Any] | None = None
    if source_language == "react":
        # React's repository identity is project-contextual: an exact React
        # project may contain both .tsx and .ts helpers, and its package and
        # tsconfig bytes are part of repository completeness.  The compiler-
        # backed discovery receipt is therefore required before the graph can
        # classify those .ts files as React or close the two descriptors.
        try:
            discovery = discover_repository(plan, root)
        except RouteError as error:
            if not _reportable_discovery_incident(error):
                raise
            discovery_incident = str(error)[:2_000]
            discovery = inventory_repository_incident(plan, root, discovery_incident)
        if discovery_incident is None:
            project_graph = build_project_graph(root, repository_ref, discovery)
            if _neutral_project_snapshot(project_graph) != invocation_snapshot:
                raise RouteError("PROJECT_GRAPH_CHANGED_DURING_PIPELINE")
        else:
            # An incident discovery carries no compiler receipt, so it cannot
            # reclassify anything.  Fall back to the uninformed graph rather
            # than binding a graph to a receipt that was never produced.
            project_graph = invocation_graph
    else:
        project_graph = invocation_graph

    initial_graph_summary = _project_graph_summary(project_graph)
    _bind_project_graph_to_plan(project_graph, plan)
    _write_json(output / "repository-route-plan.json", plan)
    _write_json(output / CASES_MANIFEST_NAME, cases_manifest)

    if discovery is None:
        try:
            discovery = discover_repository(plan, root)
        except RouteError as error:
            if not _reportable_discovery_incident(error):
                raise
            discovery_incident = str(error)[:2_000]
            discovery = inventory_repository_incident(plan, root, discovery_incident)
    _write_json(output / "repository-discovery-report.json", discovery)

    if discovery_incident is None:
        batch_output = _owned_directory(output, "batch")
        batch = run_batch(discovery, root, cases, batch_output)
    else:
        batch_output = _reset_owned_directory(output, "batch")
        batch_output.mkdir(parents=True)
        batch = _incident_batch(discovery, discovery_incident)
        _write_json(batch_output / BATCH_REPORT_NAME, batch)

    passed = int(batch.get("status_counts", {}).get("PASSED", 0))
    # An empty behavior-case corpus is not a reportable incident: with nothing
    # verified there is no evidence to package, and a run that got this far
    # without a discovery incident must refuse rather than emit a report that
    # reads like a result.  A *discovery* incident still takes the diagnostic
    # path below, which is the tolerance the other side of this merge added.
    if passed < 1 and discovery_incident is None:
        raise RouteError("PIPELINE_NO_VERIFIED_UNITS")
    assembly: dict[str, Any] | None = None
    assembly_failure: str | None = discovery_incident
    build_status = "NOT_RUN"
    runtime_status = "NOT_RUN"
    # Assembly is derived exclusively from digest-verified batch bytes, and is
    # built in a staging directory so a mid-run failure leaves the previous
    # `assembled` tree intact rather than half-overwritten.
    assembly_staging = _reset_owned_directory(output, "assembled.staging")
    if passed > 0:
        try:
            assembly = assemble_project(batch, batch_output, assembly_staging)
            try:
                assembly = verify_assembled_project(
                    target_language,
                    assembly_staging,
                    cases_directory=cases,
                    cases_manifest=cases_manifest,
                )
                build_status = "PASSED"
                runtime_status = str(assembly.get("runtime_verification_status", "NOT_RUN"))
            except RouteError as error:
                if not _reportable_assembly_failure(error):
                    raise
                assembly_failure = str(error)[:4_000]
                if str(error).startswith("ASSEMBLY_RUNTIME_"):
                    # The build manifest is persisted before runtime replay,
                    # so a runtime-only failure still carries truthful build
                    # evidence while remaining ineligible for completion.
                    build_status = "PASSED"
                    runtime_status = _assembly_failure_status(error)
                    try:
                        assembly = json.loads(
                            (assembly_staging / "assembly-manifest.json").read_text(encoding="utf-8")
                        )
                    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as manifest_error:
                        raise RouteError("PIPELINE_ASSEMBLY_MANIFEST_UNREADABLE") from manifest_error
                else:
                    build_status = _assembly_failure_status(error)
        except RouteError as error:
            if not _reportable_assembly_failure(error):
                raise
            assembly_failure = str(error)[:4_000]
            build_status = _assembly_failure_status(error)

    def _discard_staging() -> None:
        if assembly_staging.exists():
            if assembly_staging.is_symlink() or not assembly_staging.is_dir():
                raise RouteError("PIPELINE_STAGING_DIRECTORY_INVALID")
            shutil.rmtree(assembly_staging)

    replayed_graph = build_project_graph(
        root,
        repository_ref,
        discovery if source_language == "react" and discovery_incident is None else None,
    )
    if _neutral_project_snapshot(replayed_graph) != invocation_snapshot:
        _discard_staging()
        raise RouteError("PROJECT_GRAPH_CHANGED_DURING_PIPELINE")
    if _project_graph_summary(replayed_graph) != initial_graph_summary:
        _discard_staging()
        raise RouteError("PROJECT_GRAPH_CHANGED_DURING_PIPELINE")

    if not assembly_staging.is_dir():
        assembly_staging.mkdir(parents=True)
    assembled_output = _commit_owned_directory(output, "assembled.staging", "assembled")
    if build_status == "PASSED":
        # Closure is only meaningful over a tree that actually built.  A
        # reportable assembly failure leaves a partial tree on purpose; running
        # the closure gate over it would convert a diagnosable PARTIAL into an
        # unrelated raise.
        assembly = verify_assembly_closure(
            target_language,
            assembled_output,
            require_runtime_passed=runtime_status == "PASSED",
        )

    semantic_graph = build_project_graph(root, repository_ref, discovery)
    if (
        _neutral_project_snapshot(semantic_graph) != invocation_snapshot
        or semantic_graph.get("snapshot_sha256") != project_graph.get("snapshot_sha256")
    ):
        raise RouteError("PROJECT_GRAPH_CHANGED_DURING_PIPELINE")
    _bind_project_graph_to_plan(semantic_graph, plan)
    graph_summary = _write_and_verify_project_graph(output, semantic_graph)
    conversion_coverage = _conversion_coverage_summary(semantic_graph, discovery, batch)
    behavior_coverage = _behavior_coverage_summary(discovery, batch)
    repository_complete = (
        graph_summary["repository_complete"] is True
        and conversion_coverage["complete"] is True
        and behavior_coverage["complete"] is True
        and build_status == "PASSED"
        and runtime_status == "PASSED"
    )

    function_report = build_conversion_report(
        discovery,
        batch,
        root,
        batch_output,
        build_status=build_status,
        build_reason=assembly_failure,
        cases_manifest_sha256=cases_manifest_sha256,
        runtime_status=runtime_status,
    )

    # Re-inventory both independent inputs after all analysis, target execution
    # and assembly work. Any addition, deletion, rename, byte drift or change
    # from PRESENT to MISSING is an integrity failure, not a reportable partial.
    try:
        final_plan = plan_repository(root, repository_ref, source_language, target_language)
    except RouteError as error:
        if str(error).startswith("NO_SOURCE_FILES:"):
            raise RouteError("PIPELINE_SOURCE_SNAPSHOT_CHANGED_DURING_RUN") from error
        raise
    if final_plan != plan:
        raise RouteError("PIPELINE_SOURCE_SNAPSHOT_CHANGED_DURING_RUN")
    final_cases_manifest, final_cases_manifest_sha256 = _cases_manifest(cases, final_plan)
    if final_cases_manifest != cases_manifest or final_cases_manifest_sha256 != cases_manifest_sha256:
        raise RouteError("PIPELINE_BEHAVIOR_CASES_CHANGED_DURING_RUN")

    functional_conversion = write_conversion_reports(function_report, output)
    status = str(function_report["status"])
    if status == "COMPLETE" and not repository_complete:
        # Functional obligations can all pass while the project graph still
        # has unresolved repository-scope obligations.  Keep the top-level
        # project result partial so callers cannot mistake function coverage
        # for whole-repository conversion completion.
        status = "PARTIAL"

    def _shared_claim(current_status: str) -> dict[str, Any]:
        """Fields the report and the manifest must agree on, byte for byte.

        The console compares the two documents field by field, so they are
        built once from a single source rather than written out twice.  The
        two execution-evidence vocabularies are the console's, not this
        module's: it expects PASSED/LIMITED, never PARTIAL.
        """
        complete = current_status == "COMPLETE"
        return {
            "status": current_status,
            "repository_ref": repository_ref,
            "snapshot_sha256": plan["snapshot_sha256"],
            "repository_scale": plan["repository_scale"],
            "repository_limits": plan["repository_limits"],
            "route_id": plan["route_id"],
            "source_language": source_language,
            "target_language": target_language,
            "profile": "typed-pure-function-v1",
            "unit_batch_status": batch.get("status"),
            "project_graph": graph_summary,
            "conversion_coverage": conversion_coverage,
            "behavior_coverage": behavior_coverage,
            "repository_complete": repository_complete,
            "runtime_verification_status": runtime_status,
            "local_execution_evidence": "PASSED" if complete else "LIMITED",
            "repository_execution_status": "PASSED_LOCAL" if complete else "LIMITED",
            "independent_verification_status": "NOT_RUN",
            "external_verification_status": "NOT_RUN",
            "certification_status": "NOT_CERTIFIED",
        }

    artifact: dict[str, Any] | None = None
    artifact_packaging: dict[str, Any] = {
        "status": "NOT_RUN",
        "reason_code": "FUNCTIONAL_CONVERSION_NOT_CODE_READY",
        "reason": "No verified build-ready target artifact was available for packaging.",
        "max_uncompressed_bytes": MAX_ARTIFACT_UNCOMPRESSED_BYTES,
        "max_compressed_bytes": MAX_ARTIFACT_COMPRESSED_BYTES,
    }
    if functional_conversion["code_artifact_ready"]:
        try:
            inventory = _artifact_inventory(output)
            manifest = {
                "schema_version": SCHEMA_VERSION,
                "kind": "elmos.repository-migration-artifact-manifest",
                **_shared_claim(status),
                "functional_conversion": {
                    "definition_id": functional_conversion["definition_id"],
                    "numerator": functional_conversion["numerator"],
                    "denominator": functional_conversion["denominator"],
                    "success_rate_basis_points": functional_conversion["success_rate_basis_points"],
                    "measurement_status": functional_conversion["measurement_status"],
                    "denominator_complete": functional_conversion["denominator_complete"],
                    "project_success_rate_display": functional_conversion[
                        "project_success_rate_display"
                    ],
                    "code_artifact_ready": True,
                    "cases_manifest_sha256": cases_manifest_sha256,
                },
                "files": inventory,
            }
            _write_json(output / ARTIFACT_MANIFEST_NAME, manifest)
            manifest_bytes, manifest_sha256 = _stable_file(
                output / ARTIFACT_MANIFEST_NAME,
                "PIPELINE_ARTIFACT_MANIFEST",
                max_bytes=MAX_ARTIFACT_UNCOMPRESSED_BYTES,
                limit_error="PIPELINE_ARTIFACT_UNCOMPRESSED_LIMIT_EXCEEDED",
            )
            archive_entries = [
                *inventory,
                {
                    "path": ARTIFACT_MANIFEST_NAME,
                    "bytes": manifest_bytes,
                    "sha256": manifest_sha256,
                },
            ]
            archive, artifact_size, artifact_sha256 = _write_deterministic_zip(
                output, archive_entries
            )
            artifact = {
                "path": archive.name,
                "bytes": artifact_size,
                "sha256": artifact_sha256,
            }
            artifact_packaging = {
                "status": "PASSED",
                "reason_code": None,
                "reason": None,
                "max_uncompressed_bytes": MAX_ARTIFACT_UNCOMPRESSED_BYTES,
                "max_compressed_bytes": MAX_ARTIFACT_COMPRESSED_BYTES,
            }
        except RouteError as error:
            if not _reportable_artifact_capacity(error):
                raise
            reason_code = str(error).split(":", 1)[0]
            status = "BLOCKED"
            artifact_packaging = {
                "status": "FAILED",
                "reason_code": reason_code,
                "reason": str(error)[:2_000],
                "max_uncompressed_bytes": MAX_ARTIFACT_UNCOMPRESSED_BYTES,
                "max_compressed_bytes": MAX_ARTIFACT_COMPRESSED_BYTES,
            }
            # The manifest that was just written describes an archive that does
            # not exist.  Remove it rather than leave a claim behind, which is
            # also what keeps report and manifest from disagreeing.
            manifest_path = output / ARTIFACT_MANIFEST_NAME
            if manifest_path.exists():
                if manifest_path.is_symlink() or not manifest_path.is_file():
                    raise RouteError("PIPELINE_OUTPUT_UNSAFE") from error
                manifest_path.unlink()
            function_report["code_artifact_ready"] = False
            function_report["markdown_sha256"] = hashlib.sha256(
                render_conversion_markdown(function_report).encode("utf-8")
            ).hexdigest()
            functional_conversion = write_conversion_reports(function_report, output)

    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "elmos.repository-pipeline-report",
        **_shared_claim(status),
        "work_unit_count": batch["work_unit_count"],
        "ready_count": discovery["ready_count"],
        "resumed_count": batch["resumed_count"],
        "status_counts": batch["status_counts"],
        "included_unit_count": int(assembly.get("included_unit_count", 0)) if assembly else 0,
        "excluded_units": (
            assembly.get("excluded_units", [])
            if assembly
            else [
                {
                    "id": unit.get("id"),
                    "status": unit.get("status"),
                    "reason": unit.get("reason", assembly_failure or "TARGET_PROJECT_NOT_ASSEMBLED"),
                }
                for unit in batch.get("units", [])
            ]
        ),
        "build_verification": {
            "status": build_status,
            "commands": (assembly.get("build_verification", {}) or {}).get("commands", [])
            if assembly
            else [],
            "toolchain": {
                "language": (assembly.get("build_verification", {}) or {}).get("toolchain_language")
                if assembly
                else None,
                "version": (assembly.get("build_verification", {}) or {}).get("toolchain_version")
                if assembly
                else None,
            },
            "reason": assembly_failure,
        },
        "runtime_verification": {
            "status": runtime_status,
            "commands": (assembly.get("runtime_verification", {}) or {}).get("commands", [])
            if assembly
            else [],
            "toolchain": {
                "language": (assembly.get("runtime_verification", {}) or {}).get("toolchain_language")
                if assembly
                else None,
                "version": (assembly.get("runtime_verification", {}) or {}).get("toolchain_version")
                if assembly
                else None,
            },
            "reason": assembly_failure if runtime_status != "PASSED" else None,
        },
        "functional_conversion": functional_conversion,
        "cases_manifest_sha256": cases_manifest_sha256,
        "artifact": artifact,
        "artifact_packaging": artifact_packaging,
        "limitations": [
            "The result covers typed-pure-function-v1 only.",
            "Cross-file calls, shared state, original build dependencies, resources, and configuration "
            "must be represented by a project graph and remain blocking when unresolved.",
            "A locally passing unit batch remains LIMITED while any project-graph obligation is open.",
            "Every compiler-indexed declaration and module effect must bind to one READY unit that PASSED.",
            "Non-Python declaration inventories remain INDETERMINATE until a compiler-complete "
            "inventory is available for that source language.",
            "PARTIAL means at least one repository unit was skipped, failed, unsupported, or unknown.",
            "BLOCKED can still carry a content-addressed diagnostic report, but it never makes "
            "target code downloadable.",
            "Local exact-toolchain execution is engineering evidence, not independent or external certification.",
        ],
    }
    _write_json(output / REPORT_NAME, report)
    return report




_BEHAVIOR_COVERAGE_STATUSES = ("FAILED", "NOT_RUN", "PASSED", "UNKNOWN")
_BATCH_TO_BEHAVIOR_STATUS = {
    "FAILED": "FAILED",
    "PASSED": "PASSED",
    "SKIPPED_NO_CASES": "NOT_RUN",
    "SKIPPED_NOT_READY": "NOT_RUN",
}
def _behavior_coverage_summary(
    discovery: dict[str, Any],
    batch: dict[str, Any],
) -> dict[str, Any]:
    """Account for every discovered work unit without rounding up partial evidence."""

    discovery_results = discovery.get("results")
    discovery_work_unit_count = discovery.get("work_unit_count")
    units = batch.get("units")
    work_unit_count = batch.get("work_unit_count")
    selected_count = batch.get("selected_count")
    attempted_count = batch.get("attempted_count")
    unattempted_count = batch.get("unattempted_count")
    if (
        not isinstance(discovery_results, list)
        or not isinstance(units, list)
        or not isinstance(discovery_work_unit_count, int)
        or isinstance(discovery_work_unit_count, bool)
        or not isinstance(work_unit_count, int)
        or isinstance(work_unit_count, bool)
        or not isinstance(selected_count, int)
        or isinstance(selected_count, bool)
        or not isinstance(attempted_count, int)
        or isinstance(attempted_count, bool)
        or not isinstance(unattempted_count, int)
        or isinstance(unattempted_count, bool)
        or min(
            discovery_work_unit_count,
            work_unit_count,
            selected_count,
            attempted_count,
            unattempted_count,
        )
        < 0
        or work_unit_count < 1
        or discovery_work_unit_count != work_unit_count
        or work_unit_count != len(discovery_results)
        or work_unit_count != len(units)
        or selected_count != work_unit_count
    ):
        raise RouteError("BEHAVIOR_COVERAGE_INPUT_INVALID")

    discovery_by_id: dict[str, dict[str, Any]] = {}
    discovery_ids: list[str] = []
    for result in discovery_results:
        if not isinstance(result, dict) or not isinstance(result.get("id"), str):
            raise RouteError("BEHAVIOR_COVERAGE_DISCOVERY_UNIT_INVALID")
        unit_id = result["id"]
        if not unit_id or unit_id in discovery_by_id:
            raise RouteError("BEHAVIOR_COVERAGE_DISCOVERY_UNIT_DUPLICATED")
        discovery_by_id[unit_id] = result
        discovery_ids.append(unit_id)

    raw_status_counts: dict[str, int] = {}
    unit_ids: list[str] = []
    for unit in units:
        if not isinstance(unit, dict) or not isinstance(unit.get("id"), str) or not isinstance(unit.get("status"), str):
            raise RouteError("BEHAVIOR_COVERAGE_UNIT_INVALID")
        unit_id = unit["id"]
        if not unit_id or unit_id in unit_ids:
            raise RouteError("BEHAVIOR_COVERAGE_UNIT_DUPLICATED")
        unit_ids.append(unit_id)
        unit_status = unit["status"]
        raw_status_counts[unit_status] = raw_status_counts.get(unit_status, 0) + 1

    if unit_ids != discovery_ids:
        raise RouteError("BEHAVIOR_COVERAGE_WORK_UNIT_SET_MISMATCH")
    if batch.get("status_counts") != raw_status_counts:
        raise RouteError("BEHAVIOR_COVERAGE_BATCH_COUNTS_MISMATCH")

    counts = {status: 0 for status in _BEHAVIOR_COVERAGE_STATUSES}
    executed_behavior_case_count = 0
    covered_units: list[dict[str, Any]] = []
    for unit in units:
        unit_id = unit["id"]
        discovery_unit = discovery_by_id[unit_id]
        if unit.get("source_path") != discovery_unit.get("source_path"):
            raise RouteError("BEHAVIOR_COVERAGE_WORK_UNIT_IDENTITY_MISMATCH")
        discovered_function = discovery_unit.get("function_name")
        observed_function = unit.get("function_name")
        if observed_function is not None and observed_function != discovered_function:
            raise RouteError("BEHAVIOR_COVERAGE_WORK_UNIT_IDENTITY_MISMATCH")

        unit_status = unit["status"]
        status = _BATCH_TO_BEHAVIOR_STATUS.get(unit_status, "UNKNOWN")
        behavior_case_count: int | None = None
        evidence_path: str | None = None
        evidence_sha256: str | None = None
        if status == "PASSED":
            execution_status = unit.get("execution_status")
            raw_case_count = unit.get("behavior_case_count")
            raw_evidence_path = unit.get("evidence_path")
            raw_evidence_sha256 = unit.get("evidence_sha256")
            raw_target_function = unit.get("target_function_name")
            raw_identifier_plan_path = unit.get("identifier_plan_path")
            raw_identifier_plan_sha256 = unit.get("identifier_plan_sha256")
            expected_evidence_path = f"units/{unit_id}/route-evidence.json"
            if (
                execution_status not in {"PASSED", "PASSED_LOCAL_UNCERTIFIED"}
                or type(raw_case_count) is not int
                or raw_case_count < 1
                or raw_evidence_path != expected_evidence_path
                or not isinstance(raw_evidence_sha256, str)
                or not raw_evidence_sha256.startswith("sha256:")
                or len(raw_evidence_sha256) != 71
                or any(character not in "0123456789abcdef" for character in raw_evidence_sha256[7:])
                or not isinstance(raw_target_function, str)
                or not raw_target_function
                or raw_identifier_plan_path != "identifier-plan.json"
                or not isinstance(raw_identifier_plan_sha256, str)
                or not re.fullmatch(r"sha256:[0-9a-f]{64}", raw_identifier_plan_sha256)
            ):
                raise RouteError("BEHAVIOR_COVERAGE_PASSED_UNIT_INVALID")
            behavior_case_count = raw_case_count
            evidence_path = raw_evidence_path
            evidence_sha256 = raw_evidence_sha256
            executed_behavior_case_count += behavior_case_count
        elif unit_status == "SKIPPED_NO_CASES":
            # This is the sole non-success state with a known exact case count.
            behavior_case_count = 0

        counts[status] += 1
        covered_units.append(
            {
                "id": unit_id,
                "source_path": discovery_unit.get("source_path"),
                "function_name": discovered_function,
                "target_function_name": unit.get("target_function_name"),
                "identifier_plan_path": unit.get("identifier_plan_path"),
                "identifier_plan_sha256": unit.get("identifier_plan_sha256"),
                "batch_status": unit_status,
                "status": status,
                "behavior_case_count": behavior_case_count,
                "evidence_path": evidence_path,
                "evidence_sha256": evidence_sha256,
            }
        )

    accounted_work_unit_count = sum(counts.values())
    attempted_work_unit_count = counts["PASSED"] + counts["FAILED"]
    unresolved_work_unit_count = counts["NOT_RUN"] + counts["UNKNOWN"]
    if (
        accounted_work_unit_count != work_unit_count
        or attempted_count != attempted_work_unit_count
        or unattempted_count != work_unit_count - attempted_work_unit_count
    ):
        raise RouteError("BEHAVIOR_COVERAGE_COUNTS_NOT_CLOSED")

    complete = counts == {"FAILED": 0, "NOT_RUN": 0, "PASSED": work_unit_count, "UNKNOWN": 0}
    expected_batch_status = "COMPLETE" if complete else "PARTIAL"
    if batch.get("status") != expected_batch_status:
        raise RouteError("BEHAVIOR_COVERAGE_BATCH_STATUS_CONTRADICTORY")
    status = "PASSED" if complete else "FAILED" if counts["FAILED"] else "UNKNOWN" if counts["UNKNOWN"] else "NOT_RUN"
    return {
        "profile": "typed-pure-function-v1",
        "status": status,
        "complete": complete,
        "work_unit_denominator": work_unit_count,
        "work_unit_count": work_unit_count,
        "accounted_work_unit_count": accounted_work_unit_count,
        "attempted_work_unit_count": attempted_work_unit_count,
        "unresolved_work_unit_count": unresolved_work_unit_count,
        "pass_rate": counts["PASSED"] / work_unit_count,
        # Retain the existing field for consumers, while making its bounded
        # denominator explicit: failed/unknown units cannot contribute a
        # fabricated zero or an inferred case count.
        "behavior_case_count": executed_behavior_case_count,
        "behavior_case_count_scope": "PASSED_WORK_UNITS_ONLY",
        "status_counts": counts,
        "units": covered_units,
        "evidence_strength": "LOCAL_SOURCE_TARGET_RUNTIME_COMPARISON",
        "independent_verification_status": "NOT_RUN",
        "external_verification_status": "NOT_RUN",
    }


def run_repository_pipeline(
    repository_root: Path,
    repository_ref: str,
    source_language: Language,
    target_language: Language,
    cases_directory: Path,
    output: Path,
) -> dict[str, Any]:
    """Run one attempt while atomically isolating prior final status claims.

    Argument validation happens *before* the quarantine on purpose.  Quarantine
    is destructive on failure -- a run that fails deletes the previous run's
    COMPLETE surfaces, because the directory it half-overwrote no longer
    represents that earlier run.  A caller passing an unsupported language must
    therefore be refused before anything is moved, or a typo would destroy a
    perfectly good previous result.
    """
    if (
        source_language not in SUPPORTED_LANGUAGES
        or target_language not in SUPPORTED_LANGUAGES
    ):
        raise RouteError("UNSUPPORTED_LANGUAGE")
    if source_language == target_language:
        raise RouteError("SOURCE_AND_TARGET_MUST_DIFFER")
    if output.exists() and (output.is_symlink() or not output.is_dir()):
        raise RouteError("PIPELINE_OUTPUT_UNSAFE")
    output.mkdir(parents=True, exist_ok=True)
    _validate_handoff_targets(output)
    prior_claims = _quarantine_prior_final_claims(output)
    try:
        report = _run_repository_pipeline_attempt(
            repository_root,
            repository_ref,
            source_language,
            target_language,
            cases_directory,
            output,
        )
    except BaseException:
        _invalidate_current_final_claims(output)
        _discard_prior_final_claims(prior_claims)
        raise
    _discard_prior_final_claims(prior_claims)
    return report
