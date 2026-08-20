"""Resumable repository translation pipeline and content-addressed handoff.

This module composes the existing project graph, inventory, discovery, batch,
and assembly primitives without weakening any of their gates.  It is
intentionally a local engineering workflow: a COMPLETE result means that the
content-addressed project graph has no open obligations, every discovered work
unit passed its supplied behavior cases, and the assembled project built with
the exact local toolchains.  Independent and external verification remain
NOT_RUN.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any

from .assembly import (
    MANIFEST_NAME as ASSEMBLY_MANIFEST_NAME,
)
from .assembly import (
    assemble_project,
    verify_archived_assembly_closure,
    verify_assembled_project,
    verify_assembly_closure,
)
from .batch import run_batch
from .discovery import discover_repository
from .models import REPOSITORY_SURFACE_LANGUAGES, Language, RouteError
from .project_graph import build_project_graph, verify_project_graph
from .repository import plan_repository

SCHEMA_VERSION = "1.0.0"
REPORT_NAME = "repository-pipeline-report.json"
ARTIFACT_NAME = "repository-migration-artifact.zip"
ARTIFACT_MANIFEST_NAME = "artifact-manifest.json"
PROJECT_GRAPH_NAME = "project-graph.json"
_GRAPH_OBLIGATION_STATUSES = ("FAILED", "NOT_RUN", "PASSED", "UNKNOWN")
_CONVERSION_COVERAGE_STATUSES = ("BLOCKED", "FAILED", "NOT_RUN", "PASSED", "UNKNOWN")
_BEHAVIOR_COVERAGE_STATUSES = ("FAILED", "NOT_RUN", "PASSED", "UNKNOWN")
_BATCH_TO_BEHAVIOR_STATUS = {
    "FAILED": "FAILED",
    "PASSED": "PASSED",
    "SKIPPED_NO_CASES": "NOT_RUN",
    "SKIPPED_NOT_READY": "NOT_RUN",
}
_FINAL_CLAIM_NAMES = (ARTIFACT_NAME, REPORT_NAME, ARTIFACT_MANIFEST_NAME)
_PRIOR_CLAIM_SUFFIX = ".previous-handoff"
_ARTIFACT_CONTROL_PATHS = frozenset(
    {
        ARTIFACT_NAME,
        f"{ARTIFACT_NAME}.tmp",
        REPORT_NAME,
        ARTIFACT_MANIFEST_NAME,
        *(f"{name}{_PRIOR_CLAIM_SUFFIX}" for name in _FINAL_CLAIM_NAMES),
    }
)


def _write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(64 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _owned_directory(output: Path, child: str) -> Path:
    root = output.resolve(strict=True)
    raw_candidate = output / child
    if raw_candidate.is_symlink():
        raise RouteError("PIPELINE_OUTPUT_UNSAFE")
    candidate = raw_candidate.resolve()
    if candidate.parent != root:
        raise RouteError("PIPELINE_PATH_CONFINEMENT_FAILED")
    return candidate


def _reset_owned_directory(output: Path, child: str) -> Path:
    candidate = _owned_directory(output, child)
    if candidate.exists():
        if candidate.is_symlink() or not candidate.is_dir():
            raise RouteError("PIPELINE_OUTPUT_UNSAFE")
        shutil.rmtree(candidate)
    return candidate


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


def _clean_archive_temporary(output: Path) -> None:
    temporary = output / f"{ARTIFACT_NAME}.tmp"
    if temporary.is_symlink() or (temporary.exists() and not temporary.is_file()):
        raise RouteError("PIPELINE_OUTPUT_UNSAFE")
    if temporary.exists():
        temporary.unlink()


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


def _artifact_inventory(output: Path) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for path in sorted(output.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(output).as_posix()
        if relative in _ARTIFACT_CONTROL_PATHS:
            continue
        files.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    if not files:
        raise RouteError("PIPELINE_ARTIFACT_EMPTY")
    return files


def _archive_entry_path(output: Path, relative: str) -> Path:
    pure = Path(relative)
    if not relative or pure.is_absolute() or ".." in pure.parts or "\\" in relative or pure.as_posix() != relative:
        raise RouteError("PIPELINE_ARTIFACT_PATH_INVALID")
    cursor = output
    for part in pure.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise RouteError("PIPELINE_ARTIFACT_SOURCE_UNSAFE")
    if not cursor.is_file():
        raise RouteError("PIPELINE_ARTIFACT_SOURCE_MISSING")
    root = output.resolve(strict=True)
    resolved = cursor.resolve(strict=True)
    if root not in resolved.parents:
        raise RouteError("PIPELINE_ARTIFACT_SOURCE_UNSAFE")
    return cursor


def _validate_archive_entry(entry: dict[str, Any]) -> tuple[str, int, str]:
    relative = entry.get("path")
    byte_count = entry.get("bytes")
    sha256 = entry.get("sha256")
    if (
        not isinstance(relative, str)
        or type(byte_count) is not int
        or byte_count < 0
        or not isinstance(sha256, str)
        or len(sha256) != 64
        or any(character not in "0123456789abcdef" for character in sha256)
    ):
        raise RouteError("PIPELINE_ARTIFACT_ENTRY_INVALID")
    return relative, byte_count, sha256


def _verify_deterministic_zip(archive: Path, entries: list[dict[str, Any]]) -> None:
    expected: dict[str, tuple[int, str]] = {}
    for entry in entries:
        relative, byte_count, sha256 = _validate_archive_entry(entry)
        if relative in expected:
            raise RouteError("PIPELINE_ARTIFACT_ENTRY_DUPLICATED")
        expected[relative] = (byte_count, sha256)
    try:
        with zipfile.ZipFile(archive) as bundle:
            infos = bundle.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)) or set(names) != set(expected):
                raise RouteError("PIPELINE_ARTIFACT_PATH_SET_MISMATCH")
            for info in infos:
                if info.is_dir():
                    raise RouteError("PIPELINE_ARTIFACT_PATH_SET_MISMATCH")
                content = bundle.read(info)
                expected_bytes, expected_sha256 = expected[info.filename]
                if (
                    len(content) != expected_bytes
                    or info.file_size != expected_bytes
                    or hashlib.sha256(content).hexdigest() != expected_sha256
                ):
                    raise RouteError(f"PIPELINE_ARTIFACT_ENTRY_MISMATCH:{info.filename}")
            try:
                embedded_manifest = json.loads(bundle.read(ARTIFACT_MANIFEST_NAME))
            except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise RouteError("PIPELINE_ARTIFACT_MANIFEST_INVALID") from error
            declared_files = embedded_manifest.get("files") if isinstance(embedded_manifest, dict) else None
            if not isinstance(declared_files, list):
                raise RouteError("PIPELINE_ARTIFACT_MANIFEST_INVALID")
            declared: dict[str, tuple[int, str]] = {}
            for entry in declared_files:
                if not isinstance(entry, dict):
                    raise RouteError("PIPELINE_ARTIFACT_MANIFEST_INVALID")
                relative, byte_count, sha256 = _validate_archive_entry(entry)
                if relative in declared or relative in _ARTIFACT_CONTROL_PATHS:
                    raise RouteError("PIPELINE_ARTIFACT_MANIFEST_INVALID")
                declared[relative] = (byte_count, sha256)
            expected_declared = {
                relative: binding for relative, binding in expected.items() if relative != ARTIFACT_MANIFEST_NAME
            }
            if declared != expected_declared:
                raise RouteError("PIPELINE_ARTIFACT_MANIFEST_PATH_SET_MISMATCH")
            source_language = embedded_manifest.get("source_language")
            target_language = embedded_manifest.get("target_language")
            if (
                source_language not in REPOSITORY_SURFACE_LANGUAGES
                or target_language not in REPOSITORY_SURFACE_LANGUAGES
                or source_language == target_language
                or embedded_manifest.get("route_id") != f"{source_language}-to-{target_language}"
            ):
                raise RouteError("PIPELINE_ARTIFACT_ROUTE_IDENTITY_INVALID")
            assembly_manifest_path = f"assembled/{ASSEMBLY_MANIFEST_NAME}"
            try:
                assembly_manifest_bytes = bundle.read(assembly_manifest_path)
            except KeyError as error:
                raise RouteError("PIPELINE_ARTIFACT_ASSEMBLY_MANIFEST_MISSING") from error
            verify_archived_assembly_closure(
                assembly_manifest_bytes,
                target_language,
                names,
                bundle.read,
            )
    except (OSError, zipfile.BadZipFile) as error:
        raise RouteError("PIPELINE_ARTIFACT_INVALID") from error


def _write_deterministic_zip(output: Path, paths: list[dict[str, Any]]) -> tuple[Path, int, str]:
    archive = output / ARTIFACT_NAME
    temporary = output / f"{ARTIFACT_NAME}.tmp"
    _clean_archive_temporary(output)
    seen: set[str] = set()
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for entry in paths:
            relative, expected_bytes, expected_sha256 = _validate_archive_entry(entry)
            if relative in seen or relative in {ARTIFACT_NAME, f"{ARTIFACT_NAME}.tmp"}:
                raise RouteError("PIPELINE_ARTIFACT_ENTRY_DUPLICATED")
            seen.add(relative)
            source = _archive_entry_path(output, relative)
            content = source.read_bytes()
            if len(content) != expected_bytes or hashlib.sha256(content).hexdigest() != expected_sha256:
                raise RouteError(f"PIPELINE_ARTIFACT_SOURCE_DRIFTED:{relative}")
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, content)
    temporary.replace(archive)
    try:
        _verify_deterministic_zip(archive, paths)
    except RouteError:
        archive.unlink(missing_ok=True)
        raise
    return archive, archive.stat().st_size, _sha256(archive)


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
    """
    if source_language not in REPOSITORY_SURFACE_LANGUAGES or target_language not in REPOSITORY_SURFACE_LANGUAGES:
        raise RouteError("UNSUPPORTED_LANGUAGE")
    if source_language == target_language:
        raise RouteError("SOURCE_AND_TARGET_MUST_DIFFER")
    if output.exists() and (output.is_symlink() or not output.is_dir()):
        raise RouteError("PIPELINE_OUTPUT_UNSAFE")
    output.mkdir(parents=True, exist_ok=True)
    _validate_handoff_targets(output)
    _clean_archive_temporary(output)
    root = repository_root.resolve(strict=True)
    cases = cases_directory.resolve(strict=True)
    if repository_root.is_symlink() or not root.is_dir():
        raise RouteError("REPOSITORY_DIRECTORY_INVALID")
    if cases_directory.is_symlink() or not cases.is_dir():
        raise RouteError("BEHAVIOR_CASES_DIRECTORY_INVALID")

    project_graph = build_project_graph(root, repository_ref)
    initial_graph_summary = _project_graph_summary(project_graph)

    plan = plan_repository(root, repository_ref, source_language, target_language)
    _bind_project_graph_to_plan(project_graph, plan)
    _write_json(output / "repository-route-plan.json", plan)

    discovery = discover_repository(plan, root)
    _write_json(output / "repository-discovery-report.json", discovery)

    batch_output = _owned_directory(output, "batch")
    batch = run_batch(discovery, root, cases, batch_output)

    passed = int(batch.get("status_counts", {}).get("PASSED", 0))
    if passed < 1:
        raise RouteError("PIPELINE_NO_VERIFIED_UNITS")

    # Assembly is derived exclusively from digest-verified batch bytes. Rebuild
    # this cheap final view on recovery instead of trusting an interrupted tree.
    assembly_staging = _reset_owned_directory(output, "assembled.staging")
    assembly = assemble_project(batch, batch_output, assembly_staging)
    assembly = verify_assembled_project(target_language, assembly_staging)

    replayed_graph = build_project_graph(root, repository_ref)
    replayed_summary = _project_graph_summary(replayed_graph)
    if replayed_summary != initial_graph_summary:
        if assembly_staging.is_symlink() or not assembly_staging.is_dir():
            raise RouteError("PIPELINE_STAGING_DIRECTORY_INVALID")
        shutil.rmtree(assembly_staging)
        raise RouteError("PROJECT_GRAPH_CHANGED_DURING_PIPELINE")
    assembled_output = _commit_owned_directory(
        output,
        "assembled.staging",
        "assembled",
    )
    assembly = verify_assembly_closure(target_language, assembled_output)
    semantic_graph = build_project_graph(root, repository_ref, discovery)
    if semantic_graph.get("snapshot_sha256") != project_graph.get("snapshot_sha256"):
        raise RouteError("PROJECT_GRAPH_CHANGED_DURING_PIPELINE")
    _bind_project_graph_to_plan(semantic_graph, plan)
    graph_summary = _write_and_verify_project_graph(output, semantic_graph)
    conversion_coverage = _conversion_coverage_summary(semantic_graph, discovery, batch)
    behavior_coverage = _behavior_coverage_summary(discovery, batch)

    repository_complete = (
        graph_summary["repository_complete"] is True
        and conversion_coverage["complete"] is True
        and behavior_coverage["complete"] is True
        and assembly.get("build_verification_status") == "PASSED"
    )
    status = "COMPLETE" if repository_complete else "PARTIAL"
    repository_execution_status = "PASSED_LOCAL" if status == "COMPLETE" else "LIMITED"
    shared_claim = {
        "status": status,
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
        "local_execution_evidence": "PASSED" if status == "COMPLETE" else "LIMITED",
        "repository_execution_status": repository_execution_status,
        "independent_verification_status": "NOT_RUN",
        "external_verification_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
    }
    _clean_archive_temporary(output)
    inventory = _artifact_inventory(output)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "kind": "elmos.repository-migration-artifact-manifest",
        **shared_claim,
        "files": inventory,
    }
    _write_json(output / ARTIFACT_MANIFEST_NAME, manifest)
    archive_entries = [
        *inventory,
        {
            "path": ARTIFACT_MANIFEST_NAME,
            "bytes": (output / ARTIFACT_MANIFEST_NAME).stat().st_size,
            "sha256": _sha256(output / ARTIFACT_MANIFEST_NAME),
        },
    ]
    try:
        archive, artifact_size, artifact_sha256 = _write_deterministic_zip(output, archive_entries)
    except RouteError:
        (output / ARTIFACT_MANIFEST_NAME).unlink(missing_ok=True)
        raise

    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "elmos.repository-pipeline-report",
        **shared_claim,
        "work_unit_count": batch["work_unit_count"],
        "ready_count": discovery["ready_count"],
        "resumed_count": batch["resumed_count"],
        "status_counts": batch["status_counts"],
        "included_unit_count": assembly["included_unit_count"],
        "excluded_units": assembly["excluded_units"],
        "build_verification": {
            "status": assembly["build_verification_status"],
            "commands": assembly.get("build_verification", {}).get("commands", []),
            "toolchain": {
                "language": assembly.get("build_verification", {}).get("toolchain_language"),
                "version": assembly.get("build_verification", {}).get("toolchain_version"),
            },
        },
        "artifact": {
            "path": archive.name,
            "bytes": artifact_size,
            "sha256": artifact_sha256,
        },
        "limitations": [
            "The result covers typed-pure-function-v1 only.",
            "Cross-file calls, shared state, original build dependencies, resources, and configuration "
            "must be represented by a project graph and remain blocking when unresolved.",
            "A locally passing unit batch remains LIMITED while any project-graph obligation is open.",
            "Every compiler-indexed declaration and module effect must bind to one READY unit that PASSED.",
            "PARTIAL means at least one repository unit was skipped or failed and blocks a whole-repository claim.",
            "Local exact-toolchain execution is engineering evidence, not independent or external certification.",
        ],
    }
    _write_json(output / REPORT_NAME, report)
    return report


def run_repository_pipeline(
    repository_root: Path,
    repository_ref: str,
    source_language: Language,
    target_language: Language,
    cases_directory: Path,
    output: Path,
) -> dict[str, Any]:
    """Run one attempt while atomically isolating prior final status claims."""

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
