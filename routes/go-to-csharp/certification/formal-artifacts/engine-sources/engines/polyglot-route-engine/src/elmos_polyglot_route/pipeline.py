"""Resumable repository translation pipeline and content-addressed handoff.

This module composes the existing inventory, discovery, batch and assembly
primitives without weakening any of their gates.  It is intentionally a local
engineering workflow: a COMPLETE result means that every discovered work unit
passed its supplied behavior cases and the assembled project built with the
exact local toolchains.  Independent and external verification remain NOT_RUN.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

from .assembly import assemble_project, verify_assembled_project
from .batch import run_batch
from .discovery import discover_repository
from .models import SUPPORTED_LANGUAGES, Language, RouteError
from .repository import plan_repository

SCHEMA_VERSION = "1.0.0"
REPORT_NAME = "repository-pipeline-report.json"
ARTIFACT_NAME = "repository-migration-artifact.zip"
ARTIFACT_MANIFEST_NAME = "artifact-manifest.json"


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
    candidate = (root / child).resolve()
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


def _remove_stale_handoff(output: Path) -> None:
    for name in (ARTIFACT_NAME, REPORT_NAME, ARTIFACT_MANIFEST_NAME, f"{ARTIFACT_NAME}.tmp"):
        candidate = output / name
        if candidate.is_symlink():
            raise RouteError("PIPELINE_OUTPUT_UNSAFE")
        if candidate.exists():
            if not candidate.is_file():
                raise RouteError("PIPELINE_OUTPUT_UNSAFE")
            candidate.unlink()


def _artifact_inventory(output: Path) -> list[dict[str, Any]]:
    excluded = {ARTIFACT_NAME, REPORT_NAME, ARTIFACT_MANIFEST_NAME}
    files: list[dict[str, Any]] = []
    for path in sorted(output.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or path.is_symlink() or path.name in excluded:
            continue
        relative = path.relative_to(output).as_posix()
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


def _write_deterministic_zip(output: Path, paths: list[dict[str, Any]]) -> tuple[Path, int, str]:
    archive = output / ARTIFACT_NAME
    temporary = output / f"{ARTIFACT_NAME}.tmp"
    if temporary.exists():
        temporary.unlink()
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for entry in paths:
            relative = str(entry["path"])
            source = output / relative
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, source.read_bytes())
    temporary.replace(archive)
    return archive, archive.stat().st_size, _sha256(archive)


def run_repository_pipeline(
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

    plan = plan_repository(root, repository_ref, source_language, target_language)
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
    assembly_output = _reset_owned_directory(output, "assembled")
    assembly = assemble_project(batch, batch_output, assembly_output)
    assembly = verify_assembled_project(target_language, assembly_output)

    status = "COMPLETE" if batch.get("status") == "COMPLETE" else "PARTIAL"
    inventory = _artifact_inventory(output)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "kind": "elmos.repository-migration-artifact-manifest",
        "status": status,
        "repository_ref": repository_ref,
        "snapshot_sha256": plan["snapshot_sha256"],
        "route_id": plan["route_id"],
        "profile": "typed-pure-function-v1",
        "files": inventory,
        "external_verification_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
    }
    _write_json(output / ARTIFACT_MANIFEST_NAME, manifest)
    archive_entries = [*inventory, {
        "path": ARTIFACT_MANIFEST_NAME,
        "bytes": (output / ARTIFACT_MANIFEST_NAME).stat().st_size,
        "sha256": _sha256(output / ARTIFACT_MANIFEST_NAME),
    }]
    archive, artifact_size, artifact_sha256 = _write_deterministic_zip(output, archive_entries)

    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "elmos.repository-pipeline-report",
        "status": status,
        "repository_ref": repository_ref,
        "snapshot_sha256": plan["snapshot_sha256"],
        "route_id": plan["route_id"],
        "source_language": source_language,
        "target_language": target_language,
        "profile": "typed-pure-function-v1",
        "work_unit_count": batch["work_unit_count"],
        "ready_count": discovery["ready_count"],
        "resumed_count": batch["resumed_count"],
        "status_counts": batch["status_counts"],
        "included_unit_count": assembly["included_unit_count"],
        "excluded_units": assembly["excluded_units"],
        "build_verification": {
            "status": assembly["build_verification_status"],
            "command": assembly.get("build_command"),
            "toolchain": assembly.get("toolchain"),
        },
        "artifact": {
            "path": archive.name,
            "bytes": artifact_size,
            "sha256": artifact_sha256,
        },
        "local_execution_evidence": "PASSED" if status == "COMPLETE" else "PARTIAL",
        "independent_verification_status": "NOT_RUN",
        "external_verification_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
        "limitations": [
            "The result covers typed-pure-function-v1 only.",
            "PARTIAL means at least one repository unit was skipped or failed and blocks a whole-repository claim.",
            "Local exact-toolchain execution is engineering evidence, not independent or external certification.",
        ],
    }
    _write_json(output / REPORT_NAME, report)
    return report
