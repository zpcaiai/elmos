"""Execute a discovered repository plan unit by unit, with resumable state.

A repository migration is not one long transaction. It is a queue of
independent units, each of which can fail for its own reason, and the queue has
to survive an interrupted run without redoing verified work or, worse, losing
the record of a failure.

Two invariants shape this module. First, a unit only runs when discovery marked
it READY *and* an independent behavior-case corpus exists for it -- there is no
"migrate and hope" path. Second, the aggregate never rounds up: a batch where
every attempted unit passed is still reported as ``PARTIAL`` while any unit
remains unattempted, because repository-wide success cannot be inferred from a
subset.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .engine import migrate
from .models import SUPPORTED_LANGUAGES, RouteError

SCHEMA_VERSION = "1.0.0"
CHECKPOINT_NAME = "batch-checkpoint.jsonl"
REPORT_NAME = "batch-report.json"
_UNIT_ID_PATTERN = re.compile(r"^WU-[0-9]{5}$")
_TARGET_FILE_BY_LANGUAGE = {
    "java": "Migrated.java",
    "python": "migrated.py",
    "csharp": "Migrated.cs",
    "typescript": "migrated.ts",
    "go": "migrated.go",
    "rust": "migrated.rs",
    "cpp": "migrated.cpp",
    "objc": "migrated.m",
    "swift": "migrated.swift",
}
_REPORTABLE_UNIT_FAILURES = {
    "BEHAVIOR_CASES_REQUIRED",
    "INVALID_BEHAVIOR_CASE",
    "INVALID_BEHAVIOR_CASES_JSON",
    "BEHAVIOR_ARGUMENT_COUNT_MISMATCH",
    "TARGET_VALIDATION_FAILED",
    "UNSUPPORTED_TYPE_MAPPING",
    "INTEGER_LITERAL_OUTSIDE_CERTIFIED_RANGE",
    "INTEGER_LITERAL_UNSAFE_FOR_TYPESCRIPT",
    "NON_FINITE_LITERAL_OUTSIDE_CERTIFIED_SUBSET",
    "NULL_LITERAL_OUTSIDE_CERTIFIED_SUBSET",
    "UNDECLARED_NAME",
    "UNSUPPORTED_EMISSION_EXPRESSION",
    "UNSUPPORTED_EMISSION_STATEMENT",
    "SOURCE_DIAGNOSTICS_BLOCK_EMISSION",
    "SOURCE_VALIDATION_FAILED",
    "SOURCE_VALIDATION_EXTRACTION_FAILED",
    "SOURCE_VALIDATION_TIMEOUT",
    "TARGET_VALIDATION_TIMEOUT",
}
_RETRYABLE_INCIDENT_PREFIXES = (
    "EXACT_TOOLCHAIN_",
    "NATIVE_ANALYZER_",
    "SWIFT_ANALYZER_",
    "TYPESCRIPT_ANALYZER_",
    "SOURCE_VALIDATION_TIMEOUT",
    "TARGET_VALIDATION_TIMEOUT",
)


class UnitStatus:
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED_NOT_READY = "SKIPPED_NOT_READY"
    SKIPPED_NO_CASES = "SKIPPED_NO_CASES"


def _load_checkpoint(path: Path) -> dict[str, dict[str, Any]]:
    """Read prior per-unit outcomes so an interrupted batch can resume."""
    if path.is_symlink():
        raise RouteError("BATCH_CHECKPOINT_UNSAFE")
    if not path.is_file():
        return {}
    recorded: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            entry = json.loads(stripped)
        except json.JSONDecodeError as error:
            raise RouteError("BATCH_CHECKPOINT_CORRUPT") from error
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            raise RouteError("BATCH_CHECKPOINT_ENTRY_INVALID")
        recorded[entry["id"]] = entry
    return recorded


def _append_checkpoint(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise RouteError("BATCH_CHECKPOINT_UNSAFE")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()


def _compact_checkpoint(path: Path, outcomes: list[dict[str, Any]]) -> None:
    if path.is_symlink():
        raise RouteError("BATCH_CHECKPOINT_UNSAFE")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            for outcome in outcomes:
                durable = {key: value for key, value in outcome.items() if key != "resumed_from_checkpoint"}
                handle.write(json.dumps(durable, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _case_file(cases_directory: Path, unit_id: str) -> Path | None:
    candidate = cases_directory / f"{unit_id}.json"
    if candidate.is_symlink():
        raise RouteError(f"BEHAVIOR_CASES_SYMLINK_REJECTED:{unit_id}")
    return candidate if candidate.is_file() else None


def _stable_sha256(path: Path, error_code: str) -> str:
    if path.is_symlink() or not path.is_file():
        raise RouteError(f"{error_code}_MISSING_OR_UNSAFE")
    before = path.stat(follow_symlinks=False)
    content = path.read_bytes()
    after = path.stat(follow_symlinks=False)
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns or len(content) != before.st_size:
        raise RouteError(f"{error_code}_CHANGED_DURING_READ")
    return hashlib.sha256(content).hexdigest()


def _confined_source(root: Path, relative: str) -> Path:
    if not relative or relative.startswith("/") or "\\" in relative or ".." in relative.split("/"):
        raise RouteError(f"WORK_UNIT_PATH_UNSAFE:{relative}")
    candidate = root / relative
    current = root
    for component in Path(relative).parts:
        current /= component
        if current.is_symlink():
            raise RouteError(f"WORK_UNIT_SOURCE_MISSING_OR_UNSAFE:{relative}")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (FileNotFoundError, ValueError) as error:
        raise RouteError(f"WORK_UNIT_PATH_ESCAPES_REPOSITORY:{relative}") from error
    if not resolved.is_file():
        raise RouteError(f"WORK_UNIT_SOURCE_MISSING_OR_UNSAFE:{relative}")
    return resolved


def _checkpoint_identity(
    discovery: dict[str, Any],
    result: dict[str, Any],
    case_path: Path | None,
) -> dict[str, Any]:
    return {
        "snapshot_sha256": discovery.get("snapshot_sha256"),
        "route_id": discovery.get("route_id"),
        "profile": discovery.get("profile"),
        "source_path": result.get("source_path"),
        "source_sha256": result.get("observed_sha256") or result.get("declared_sha256"),
        "function_name": result.get("function_name"),
        "verdict": result.get("verdict"),
        "cases_sha256": (_stable_sha256(case_path, "BEHAVIOR_CASES") if case_path is not None else None),
    }


def _recorded_artifact_intact(output: Path, recorded: dict[str, Any]) -> bool:
    if recorded.get("status") != UnitStatus.PASSED:
        return not str(recorded.get("reason_code", "")).startswith(_RETRYABLE_INCIDENT_PREFIXES)
    unit_id = str(recorded.get("id", ""))
    target_path = str(recorded.get("target_path", ""))
    expected = str(recorded.get("target_sha256", ""))
    evidence_path = str(recorded.get("evidence_path", ""))
    evidence_sha256 = str(recorded.get("evidence_sha256", ""))
    if (
        not _UNIT_ID_PATTERN.fullmatch(unit_id)
        or not target_path
        or "/" in target_path
        or "\\" in target_path
        or not expected.startswith("sha256:")
        or evidence_path != f"units/{unit_id}/route-evidence.json"
        or not evidence_sha256.startswith("sha256:")
        or recorded.get("source_validation_status") != "PASSED"
        or recorded.get("source_target_declared_case_equivalence") != "PASSED"
    ):
        return False
    units_directory = output / "units"
    unit_directory = units_directory / unit_id
    target = unit_directory / target_path
    if (
        units_directory.is_symlink()
        or unit_directory.is_symlink()
        or target.is_symlink()
        or not unit_directory.is_dir()
        or not target.is_file()
    ):
        return False
    resolved_units = units_directory.resolve(strict=True)
    resolved_unit = unit_directory.resolve(strict=True)
    resolved_target = target.resolve(strict=True)
    if resolved_unit.parent != resolved_units or resolved_target.parent != resolved_unit:
        return False
    evidence = output / evidence_path
    if evidence.is_symlink() or not evidence.is_file():
        return False
    if f"sha256:{_stable_sha256(evidence, 'CHECKPOINT_EVIDENCE')}" != evidence_sha256:
        return False
    try:
        evidence_report = json.loads(evidence.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    return (
        f"sha256:{_stable_sha256(resolved_target, 'CHECKPOINT_TARGET')}" == expected
        and evidence_report.get("source_validation", {}).get("status") == "PASSED"
        and evidence_report.get("source_target_declared_case_equivalence") == "PASSED"
    )


def _prepare_unit_directories(output: Path, allowed_ids: set[str]) -> None:
    units = output / "units"
    if units.is_symlink():
        raise RouteError("WORK_UNIT_OUTPUT_UNSAFE")
    units.mkdir(parents=True, exist_ok=True)
    resolved_units = units.resolve(strict=True)
    if resolved_units.parent != output.resolve(strict=True):
        raise RouteError("WORK_UNIT_OUTPUT_ESCAPES_BATCH")
    for child in units.iterdir():
        if child.is_symlink() or not child.is_dir():
            raise RouteError(f"WORK_UNIT_OUTPUT_UNSAFE:{child.name}")
        if child.name not in allowed_ids:
            shutil.rmtree(child)


def _reset_unit_output(output: Path, unit_id: str) -> None:
    if not _UNIT_ID_PATTERN.fullmatch(unit_id):
        raise RouteError(f"WORK_UNIT_ID_UNSAFE:{unit_id}")
    units = output / "units"
    candidate = units / unit_id
    if units.is_symlink() or candidate.is_symlink():
        raise RouteError(f"WORK_UNIT_OUTPUT_UNSAFE:{unit_id}")
    resolved_units = units.resolve(strict=True)
    resolved_candidate = candidate.resolve(strict=False)
    if resolved_candidate.parent != resolved_units:
        raise RouteError(f"WORK_UNIT_OUTPUT_ESCAPES_BATCH:{unit_id}")
    if candidate.exists():
        if not candidate.is_dir():
            raise RouteError(f"WORK_UNIT_OUTPUT_UNSAFE:{unit_id}")
        shutil.rmtree(candidate)


def _partial_target(unit_output: Path, target_language: str) -> dict[str, str]:
    """Bind a generated target even when later compile/behavior replay failed."""
    name = _TARGET_FILE_BY_LANGUAGE.get(target_language)
    if not name or not unit_output.exists():
        return {}
    if unit_output.is_symlink() or not unit_output.is_dir():
        raise RouteError("WORK_UNIT_OUTPUT_UNSAFE")
    target = unit_output / name
    if target.is_symlink() or not target.is_file() or target.resolve().parent != unit_output.resolve():
        return {}
    return {
        "target_path": name,
        "target_sha256": f"sha256:{_stable_sha256(target, 'FAILED_UNIT_TARGET')}",
        "target_verification_status": "FAILED",
    }


def _reportable_unit_failure(error: RouteError) -> bool:
    reason_code = str(error).split(":", 1)[0]
    return reason_code in _REPORTABLE_UNIT_FAILURES or reason_code.startswith(_RETRYABLE_INCIDENT_PREFIXES)


def run_batch(
    discovery: dict[str, Any],
    repository_root: Path,
    cases_directory: Path,
    output: Path,
    *,
    limit: int | None = None,
) -> dict[str, Any]:
    if discovery.get("kind") != "elmos.repository-discovery-report":
        raise RouteError("DISCOVERY_REPORT_KIND_INVALID")
    source_language = discovery.get("source_language")
    target_language = discovery.get("target_language")
    if source_language not in SUPPORTED_LANGUAGES or target_language not in SUPPORTED_LANGUAGES:
        raise RouteError("UNSUPPORTED_LANGUAGE")
    if source_language == target_language:
        raise RouteError("SOURCE_AND_TARGET_MUST_DIFFER")
    results = discovery.get("results")
    if not isinstance(results, list) or not results:
        raise RouteError("DISCOVERY_RESULTS_REQUIRED")
    if repository_root.is_symlink() or not repository_root.is_dir():
        raise RouteError("REPOSITORY_DIRECTORY_INVALID")
    if cases_directory.is_symlink() or not cases_directory.is_dir():
        raise RouteError("BEHAVIOR_CASES_DIRECTORY_INVALID")

    root = repository_root.resolve(strict=True)
    if output.exists() and (output.is_symlink() or not output.is_dir()):
        raise RouteError("BATCH_OUTPUT_UNSAFE")
    output.mkdir(parents=True, exist_ok=True)
    checkpoint = output / CHECKPOINT_NAME
    recorded = _load_checkpoint(checkpoint)

    selected = results if limit is None else results[:limit]
    allowed_ids = {str(result.get("id", "")) for result in results}
    if len(allowed_ids) != len(results) or any(not _UNIT_ID_PATTERN.fullmatch(unit_id) for unit_id in allowed_ids):
        raise RouteError("DISCOVERY_RESULT_ID_INVALID")
    _prepare_unit_directories(output, allowed_ids)
    outcomes: list[dict[str, Any]] = []
    resumed = 0

    for result in selected:
        unit_id = str(result.get("id", ""))
        if not unit_id:
            raise RouteError("DISCOVERY_RESULT_ID_REQUIRED")
        case_path = _case_file(cases_directory, unit_id) if result.get("verdict") == "READY" else None
        identity = _checkpoint_identity(discovery, result, case_path)
        prior = recorded.get(unit_id)
        if (
            prior is not None
            and prior.get("checkpoint_identity") == identity
            and _recorded_artifact_intact(output, prior)
        ):
            outcomes.append({**prior, "resumed_from_checkpoint": True})
            resumed += 1
            continue
        _reset_unit_output(output, unit_id)

        entry: dict[str, Any]
        if result.get("verdict") != "READY":
            entry = {
                "id": unit_id,
                "source_path": result.get("source_path"),
                "status": UnitStatus.SKIPPED_NOT_READY,
                "reason_code": str(result.get("verdict", "UNKNOWN")),
                "reason": str(result.get("reason", result.get("verdict", "UNKNOWN")))[:2_000],
                "failure_stage": "ANALYSIS",
                "candidates": result.get("candidates", []),
                "eligible_candidates": result.get("eligible_candidates", []),
                "rejected_candidates": result.get("rejected_candidates", []),
                "required_inputs": result.get("required_inputs", []),
                "checkpoint_identity": identity,
            }
        else:
            source = _confined_source(root, str(result["source_path"]))
            observed_source_sha256 = _stable_sha256(source, "WORK_UNIT_SOURCE")
            if observed_source_sha256 != identity["source_sha256"]:
                raise RouteError(f"WORK_UNIT_CONTENT_CHANGED:{result['source_path']}")
            if case_path is None:
                entry = {
                    "id": unit_id,
                    "source_path": result.get("source_path"),
                    "status": UnitStatus.SKIPPED_NO_CASES,
                    "function_name": result.get("function_name"),
                    "reason_code": "SKIPPED_NO_CASES",
                    "reason": "No independent behavior-case corpus was supplied for this unit.",
                    "failure_stage": "BEHAVIOR_REPLAY",
                    "checkpoint_identity": identity,
                }
            else:
                unit_output = output / "units" / unit_id
                try:
                    report = migrate(
                        source,
                        source_language,
                        target_language,
                        str(result["function_name"]),
                        case_path,
                        unit_output,
                    )
                    if _stable_sha256(source, "WORK_UNIT_SOURCE") != identity["source_sha256"]:
                        raise RouteError(f"WORK_UNIT_CONTENT_CHANGED:{result['source_path']}")
                    if _stable_sha256(case_path, "BEHAVIOR_CASES") != identity["cases_sha256"]:
                        raise RouteError(f"BEHAVIOR_CASES_CHANGED:{unit_id}")
                    entry = {
                        "id": unit_id,
                        "source_path": result.get("source_path"),
                        "status": UnitStatus.PASSED,
                        "function_name": result.get("function_name"),
                        "behavior_case_count": report.get("behavior_case_count"),
                        "target_path": report.get("target", {}).get("path"),
                        "target_sha256": report.get("target", {}).get("sha256"),
                        "evidence_path": f"units/{unit_id}/route-evidence.json",
                        "evidence_sha256": (
                            "sha256:"
                            + _stable_sha256(unit_output / "route-evidence.json", "ROUTE_EVIDENCE")
                        ),
                        "source_validation_status": report.get("source_validation", {}).get("status"),
                        "source_target_declared_case_equivalence": report.get(
                            "source_target_declared_case_equivalence"
                        ),
                        "checkpoint_identity": identity,
                    }
                except json.JSONDecodeError as error:
                    route_error = RouteError(f"INVALID_BEHAVIOR_CASES_JSON:{error.msg}")
                    partial_target = _partial_target(unit_output, str(target_language))
                    entry = {
                        "id": unit_id,
                        "source_path": result.get("source_path"),
                        "status": UnitStatus.FAILED,
                        "function_name": result.get("function_name"),
                        "reason_code": "INVALID_BEHAVIOR_CASES_JSON",
                        "reason": str(route_error)[:2_000],
                        "failure_stage": "BEHAVIOR_REPLAY",
                        **partial_target,
                        "checkpoint_identity": identity,
                    }
                except RouteError as error:
                    # A unit failure is recorded, never swallowed, and never
                    # allowed to stop the remaining queue.
                    if not _reportable_unit_failure(error):
                        raise
                    partial_target = _partial_target(unit_output, str(target_language))
                    reason_code = (str(error).split(":", 1)[0] or type(error).__name__)[:120]
                    failure_stage = (
                        "SOURCE_BEHAVIOR_REPLAY"
                        if reason_code in {
                            "SOURCE_VALIDATION_FAILED",
                            "SOURCE_VALIDATION_EXTRACTION_FAILED",
                            "SOURCE_VALIDATION_TIMEOUT",
                        }
                        else (
                            ("TARGET_BUILD" if partial_target else "ANALYSIS")
                            if reason_code.startswith("EXACT_TOOLCHAIN_")
                            else (
                                "ANALYSIS"
                                if reason_code.startswith(
                                    ("NATIVE_ANALYZER_", "SWIFT_ANALYZER_", "TYPESCRIPT_ANALYZER_")
                                )
                                else ("BEHAVIOR_REPLAY" if partial_target else "LOWERING")
                            )
                        )
                    )
                    entry = {
                        "id": unit_id,
                        "source_path": result.get("source_path"),
                        "status": UnitStatus.FAILED,
                        "function_name": result.get("function_name"),
                        "reason_code": reason_code,
                        "reason": str(error)[:2_000] or type(error).__name__,
                        "failure_stage": failure_stage,
                        **partial_target,
                        "checkpoint_identity": identity,
                    }
        _append_checkpoint(checkpoint, entry)
        outcomes.append(entry)

    counts: dict[str, int] = {}
    for outcome in outcomes:
        counts[outcome["status"]] = counts.get(outcome["status"], 0) + 1

    attempted = counts.get(UnitStatus.PASSED, 0) + counts.get(UnitStatus.FAILED, 0)
    unattempted = len(results) - attempted
    complete = counts.get(UnitStatus.FAILED, 0) == 0 and unattempted == 0 and len(selected) == len(results)
    _compact_checkpoint(checkpoint, outcomes)

    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "elmos.repository-batch-report",
        # COMPLETE means every unit in the plan was attempted and passed. Any
        # skip, failure or partial selection keeps the batch at PARTIAL.
        "status": "COMPLETE" if complete else "PARTIAL",
        "repository_ref": discovery.get("repository_ref"),
        "snapshot_sha256": discovery.get("snapshot_sha256"),
        "route_id": discovery.get("route_id"),
        "source_language": source_language,
        "target_language": target_language,
        "profile": discovery.get("profile"),
        "work_unit_count": len(results),
        "selected_count": len(selected),
        "resumed_count": resumed,
        "attempted_count": attempted,
        "unattempted_count": unattempted,
        "status_counts": counts,
        "units": outcomes,
        "external_verification_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
        "limitations": [
            "Per-unit passes are bounded-profile evidence; they are not a repository migration.",
            "Skipped and failed units keep the batch at PARTIAL and block any repository claim.",
            "Independent verification and external certification remain NOT_RUN.",
        ],
    }
    (output / REPORT_NAME).write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report
