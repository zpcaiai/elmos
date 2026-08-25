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
import re
import shutil
from pathlib import Path
from typing import Any

from .engine import migrate
from .identifier_hygiene import repository_work_unit_namespace
from .models import (
    REPOSITORY_LANGUAGE_LIFECYCLE_DEPRECATED_REPLAY,
    REPOSITORY_SURFACE_LANGUAGES,
    RouteError,
    repository_language_lifecycle,
)
from .react_repository import (
    react_project_descriptor,
    validate_react_repository_verification,
)

SCHEMA_VERSION = "1.0.0"
CHECKPOINT_NAME = "batch-checkpoint.jsonl"
REPORT_NAME = "batch-report.json"
_UNIT_ID_PATTERN = re.compile(r"^WU-[0-9]{5}(?:-F[0-9]{3})?$")
_RAW_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class UnitStatus:
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED_NOT_READY = "SKIPPED_NOT_READY"
    SKIPPED_NO_CASES = "SKIPPED_NO_CASES"


def _load_checkpoint(path: Path) -> dict[str, dict[str, Any]]:
    """Read prior per-unit outcomes so an interrupted batch can resume."""
    if path.is_symlink():
        raise RouteError("BATCH_CHECKPOINT_UNSAFE")
    if not path.exists():
        return {}
    if not path.is_file():
        raise RouteError("BATCH_CHECKPOINT_UNSAFE")
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
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise RouteError("BATCH_CHECKPOINT_UNSAFE")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()


def _rewrite_checkpoint(path: Path, entries: list[dict[str, Any]]) -> None:
    """Compact interruption state to the exact units in the current discovery."""

    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise RouteError("BATCH_CHECKPOINT_UNSAFE")
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    if temporary.is_symlink() or (temporary.exists() and not temporary.is_file()):
        raise RouteError("BATCH_CHECKPOINT_UNSAFE")
    payload = "".join(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n" for entry in entries)
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)


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


def _checkpoint_identity(
    discovery: dict[str, Any],
    result: dict[str, Any],
    case_path: Path | None,
) -> dict[str, Any]:
    unit_namespace: dict[str, Any] | None = None
    unit_namespace_sha256: str | None = None
    if result.get("verdict") == "READY":
        snapshot_sha256 = discovery.get("snapshot_sha256")
        source_sha256 = result.get("observed_sha256") or result.get(
            "declared_sha256"
        )
        unit_id = result.get("id")
        source_path = result.get("source_path")
        if (
            not isinstance(snapshot_sha256, str)
            or _RAW_SHA256_PATTERN.fullmatch(snapshot_sha256) is None
            or not isinstance(source_sha256, str)
            or _RAW_SHA256_PATTERN.fullmatch(source_sha256) is None
            or not isinstance(unit_id, str)
            or _UNIT_ID_PATTERN.fullmatch(unit_id) is None
            or not isinstance(source_path, str)
            or not source_path
        ):
            raise RouteError("BATCH_IDENTIFIER_UNIT_NAMESPACE_INPUT_INVALID")
        namespace = repository_work_unit_namespace(
            repository_snapshot_sha256="sha256:" + snapshot_sha256,
            work_unit_id=unit_id,
            source_logical_path=source_path,
            source_sha256="sha256:" + source_sha256,
        )
        unit_namespace = namespace.to_mapping()
        unit_namespace_sha256 = namespace.digest
    return {
        "snapshot_sha256": discovery.get("snapshot_sha256"),
        "repository_scale": discovery.get("repository_scale"),
        "repository_limits": discovery.get("repository_limits"),
        "route_id": discovery.get("route_id"),
        "profile": discovery.get("profile"),
        "source_path": result.get("source_path"),
        "source_sha256": result.get("observed_sha256") or result.get("declared_sha256"),
        "function_name": result.get("function_name"),
        "verdict": result.get("verdict"),
        "cases_sha256": (_stable_sha256(case_path, "BEHAVIOR_CASES") if case_path is not None else None),
        "identifier_unit_namespace": unit_namespace,
        "identifier_unit_namespace_sha256": unit_namespace_sha256,
    }


def _recorded_artifact_intact(output: Path, recorded: dict[str, Any]) -> bool:
    status = recorded.get("status")
    if status in {UnitStatus.SKIPPED_NOT_READY, UnitStatus.SKIPPED_NO_CASES}:
        return True
    # A local JSONL checkpoint is interruption state, not an authentication
    # boundary.  A caller that can edit it can also forge matching target and
    # evidence digests, so PASSED (and transient FAILED) outcomes must execute
    # again.  Only non-success skips are safe to resume without runtime replay.
    if status != UnitStatus.PASSED:
        return False
    unit_id = str(recorded.get("id", ""))
    target_path = str(recorded.get("target_path", ""))
    expected = str(recorded.get("target_sha256", ""))
    if (
        not _UNIT_ID_PATTERN.fullmatch(unit_id)
        or not target_path
        or "/" in target_path
        or "\\" in target_path
        or not expected.startswith("sha256:")
    ):
        return False
    batch_root = output.resolve(strict=True)
    units_root = batch_root / "units"
    raw_unit_directory = units_root / unit_id
    raw_target = raw_unit_directory / target_path
    if (
        units_root.is_symlink()
        or not units_root.is_dir()
        or raw_unit_directory.is_symlink()
        or not raw_unit_directory.is_dir()
        or raw_target.is_symlink()
        or not raw_target.is_file()
    ):
        return False
    unit_directory = raw_unit_directory.resolve(strict=True)
    target = raw_target.resolve(strict=True)
    if unit_directory.parent != units_root.resolve(strict=True) or target.parent != unit_directory:
        return False
    # Even an intact target is not enough to establish that its behavior was
    # ever executed.  Keep the structural checks above as a tamper diagnostic,
    # then force the normal migration/behavior path below.
    return False


def _owned_units_directory(output: Path) -> Path:
    """Return a real units directory owned directly by the batch output."""

    batch_root = output.resolve(strict=True)
    units = output / "units"
    if units.is_symlink() or (units.exists() and not units.is_dir()):
        raise RouteError("BATCH_UNITS_DIRECTORY_UNSAFE")
    units.mkdir(parents=False, exist_ok=True)
    if units.is_symlink() or units.resolve(strict=True).parent != batch_root:
        raise RouteError("BATCH_UNITS_DIRECTORY_UNSAFE")
    return units


def _reset_unit_output(output: Path, unit_id: str) -> None:
    if not _UNIT_ID_PATTERN.fullmatch(unit_id):
        raise RouteError(f"WORK_UNIT_ID_UNSAFE:{unit_id}")
    batch_root = output.resolve(strict=True)
    units = batch_root / "units"
    if units.is_symlink() or (units.exists() and not units.is_dir()):
        raise RouteError("BATCH_UNITS_DIRECTORY_UNSAFE")
    raw_candidate = units / unit_id
    if raw_candidate.is_symlink():
        raise RouteError(f"WORK_UNIT_OUTPUT_UNSAFE:{unit_id}")
    if raw_candidate.exists():
        if not raw_candidate.is_dir():
            raise RouteError(f"WORK_UNIT_OUTPUT_UNSAFE:{unit_id}")
        candidate = raw_candidate.resolve(strict=True)
        if candidate.parent != units.resolve(strict=True):
            raise RouteError(f"WORK_UNIT_OUTPUT_ESCAPES_BATCH:{unit_id}")
        shutil.rmtree(raw_candidate)


def _prune_stale_unit_outputs(output: Path, current_unit_ids: set[str]) -> None:
    """Remove only owned unit directories absent from the current discovery.

    Unit outputs are derived, resumable state.  Keeping a directory after its
    source subject disappeared would let an unrelated prior artifact leak into
    a later repository handoff, so the current discovery is the exact owner
    set.  Anything that is not a regular, directly-owned unit directory fails
    closed instead of being deleted.
    """

    units = _owned_units_directory(output)
    resolved_units = units.resolve(strict=True)
    for candidate in sorted(units.iterdir(), key=lambda path: path.name):
        if candidate.is_symlink() or not candidate.is_dir():
            raise RouteError(f"WORK_UNIT_OUTPUT_UNSAFE:{candidate.name}")
        if _UNIT_ID_PATTERN.fullmatch(candidate.name) is None:
            raise RouteError(f"WORK_UNIT_OUTPUT_UNSAFE:{candidate.name}")
        resolved = candidate.resolve(strict=True)
        if resolved.parent != resolved_units:
            raise RouteError(f"WORK_UNIT_OUTPUT_ESCAPES_BATCH:{candidate.name}")
        if candidate.name not in current_unit_ids:
            shutil.rmtree(candidate)


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
    if source_language not in REPOSITORY_SURFACE_LANGUAGES or target_language not in REPOSITORY_SURFACE_LANGUAGES:
        raise RouteError("UNSUPPORTED_LANGUAGE")
    language_lifecycle = repository_language_lifecycle(source_language, target_language)
    if (
        language_lifecycle is None
        or discovery.get("language_lifecycle") != language_lifecycle
    ):
        raise RouteError("DISCOVERY_LANGUAGE_LIFECYCLE_INVALID")
    if language_lifecycle == REPOSITORY_LANGUAGE_LIFECYCLE_DEPRECATED_REPLAY:
        raise RouteError("DEPRECATED_REPLAY_AGGREGATION_FORBIDDEN")
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
    declared_react_descriptor: dict[str, Any] | None = None
    declared_react_verification: dict[str, Any] | None = None
    declared_react_source_paths: list[str] | None = None
    if source_language == "react":
        raw_descriptor = discovery.get("react_project_descriptor")
        if not isinstance(raw_descriptor, dict):
            raise RouteError("REACT_PROJECT_DESCRIPTOR_REQUIRED")
        declared_react_descriptor = raw_descriptor
        if react_project_descriptor(root) != declared_react_descriptor:
            raise RouteError("REACT_PROJECT_DESCRIPTOR_CHANGED")
        raw_paths = discovery.get("react_project_source_paths")
        raw_verification = discovery.get("react_project_verification")
        if (
            not isinstance(raw_paths, list)
            or not raw_paths
            or any(not isinstance(value, str) or not value for value in raw_paths)
            or not isinstance(raw_verification, dict)
        ):
            raise RouteError("REACT_PROJECT_VERIFICATION_REQUIRED")
        declared_react_source_paths = raw_paths
        declared_react_verification = validate_react_repository_verification(
            root,
            declared_react_source_paths,
            declared_react_descriptor,
            raw_verification,
        )
    if output.exists() and (output.is_symlink() or not output.is_dir()):
        raise RouteError("BATCH_OUTPUT_DIRECTORY_UNSAFE")
    output.mkdir(parents=True, exist_ok=True)
    _owned_units_directory(output)
    checkpoint = output / CHECKPOINT_NAME
    recorded = _load_checkpoint(checkpoint)

    unit_ids = [str(result.get("id", "")) for result in results if isinstance(result, dict)]
    if len(unit_ids) != len(results) or any(_UNIT_ID_PATTERN.fullmatch(unit_id) is None for unit_id in unit_ids):
        raise RouteError("DISCOVERY_RESULT_ID_INVALID")
    if len(set(unit_ids)) != len(unit_ids):
        raise RouteError("DISCOVERY_RESULT_ID_DUPLICATED")
    _prune_stale_unit_outputs(output, set(unit_ids))

    selected = results if limit is None else results[:limit]
    outcomes: list[dict[str, Any]] = []
    resumed = 0

    for result in selected:
        unit_id = str(result.get("id", ""))
        if _UNIT_ID_PATTERN.fullmatch(unit_id) is None:
            raise RouteError("DISCOVERY_RESULT_ID_INVALID")
        case_path = _case_file(cases_directory, unit_id) if result.get("verdict") == "READY" else None
        identity = _checkpoint_identity(discovery, result, case_path)
        prior = recorded.get(unit_id)
        if (
            prior is not None
            and prior.get("checkpoint_identity") == identity
            and _recorded_artifact_intact(output, prior)
        ):
            # Resumable skip records have no legitimate generated unit tree.
            _reset_unit_output(output, unit_id)
            outcomes.append({**prior, "resumed_from_checkpoint": True})
            resumed += 1
            continue
        # PASSED outcomes are deliberately replayed and a missing checkpoint is
        # not authority for reusing bytes.  Reset any current non-resumed unit
        # before migration so orphaned content cannot survive into this run.
        _reset_unit_output(output, unit_id)

        entry: dict[str, Any]
        if result.get("verdict") != "READY":
            entry = {
                "id": unit_id,
                "source_path": result.get("source_path"),
                "status": UnitStatus.SKIPPED_NOT_READY,
                "reason": str(result.get("verdict", "UNKNOWN")),
                "checkpoint_identity": identity,
            }
        else:
            source = (root / str(result["source_path"])).resolve()
            if source.parent != root and not str(source).startswith(f"{root}/"):
                raise RouteError(f"WORK_UNIT_PATH_ESCAPES_REPOSITORY:{result['source_path']}")
            observed_source_sha256 = _stable_sha256(source, "WORK_UNIT_SOURCE")
            if observed_source_sha256 != identity["source_sha256"]:
                raise RouteError(f"WORK_UNIT_CONTENT_CHANGED:{result['source_path']}")
            if case_path is None:
                entry = {
                    "id": unit_id,
                    "source_path": result.get("source_path"),
                    "status": UnitStatus.SKIPPED_NO_CASES,
                    "reason": "No independent behavior-case corpus was supplied for this unit.",
                    "checkpoint_identity": identity,
                }
            else:
                units_directory = _owned_units_directory(output)
                unit_output = units_directory / unit_id
                if unit_output.is_symlink() or (unit_output.exists() and not unit_output.is_dir()):
                    raise RouteError(f"WORK_UNIT_OUTPUT_UNSAFE:{unit_id}")
                try:
                    identifier_unit_namespace = repository_work_unit_namespace(
                        repository_snapshot_sha256=(
                            "sha256:" + str(discovery["snapshot_sha256"])
                        ),
                        work_unit_id=unit_id,
                        source_logical_path=str(result["source_path"]),
                        source_sha256="sha256:" + observed_source_sha256,
                    )
                    if (
                        identity.get("identifier_unit_namespace")
                        != identifier_unit_namespace.to_mapping()
                        or identity.get("identifier_unit_namespace_sha256")
                        != identifier_unit_namespace.digest
                    ):
                        raise RouteError(
                            f"BATCH_IDENTIFIER_UNIT_NAMESPACE_DRIFT:{unit_id}"
                        )
                    report = migrate(
                        source,
                        source_language,
                        target_language,
                        str(result["function_name"]),
                        case_path,
                        unit_output,
                        repository_execution_mode=True,
                        repository_language_lifecycle=language_lifecycle,
                        identifier_unit_namespace=identifier_unit_namespace,
                    )
                    if _stable_sha256(source, "WORK_UNIT_SOURCE") != identity["source_sha256"]:
                        raise RouteError(f"WORK_UNIT_CONTENT_CHANGED:{result['source_path']}")
                    if _stable_sha256(case_path, "BEHAVIOR_CASES") != identity["cases_sha256"]:
                        raise RouteError(f"BEHAVIOR_CASES_CHANGED:{unit_id}")
                    evidence_path = unit_output / "route-evidence.json"
                    identifier_hygiene = report.get("identifier_hygiene")
                    if (
                        not isinstance(identifier_hygiene, dict)
                        or identifier_hygiene.get("unit_namespace")
                        != identifier_unit_namespace.to_mapping()
                        or identifier_hygiene.get("unit_namespace_sha256")
                        != identifier_unit_namespace.digest
                    ):
                        raise RouteError(
                            f"BATCH_IDENTIFIER_UNIT_NAMESPACE_EVIDENCE_MISMATCH:{unit_id}"
                        )
                    entry = {
                        "id": unit_id,
                        "source_path": result.get("source_path"),
                        "status": UnitStatus.PASSED,
                        "function_name": result.get("function_name"),
                        "target_function_name": report.get("target", {}).get("function_name"),
                        "identifier_plan_path": report.get("identifier_hygiene", {}).get("plan_path"),
                        "identifier_plan_sha256": report.get("identifier_hygiene", {}).get("plan_sha256"),
                        "identifier_unit_namespace": identifier_unit_namespace.to_mapping(),
                        "identifier_unit_namespace_sha256": identifier_unit_namespace.digest,
                        "behavior_case_count": report.get("behavior_case_count"),
                        "execution_status": report.get("status"),
                        "route_pack_status": report.get("route_pack_status"),
                        "target_path": report.get("target", {}).get("path"),
                        "target_sha256": report.get("target", {}).get("sha256"),
                        "evidence_path": f"units/{unit_id}/route-evidence.json",
                        "evidence_sha256": ("sha256:" + _stable_sha256(evidence_path, "ROUTE_EVIDENCE")),
                        "checkpoint_identity": identity,
                    }
                except (RouteError, OSError, ValueError) as error:
                    # A unit failure is recorded, never swallowed, and never
                    # allowed to stop the remaining queue.
                    entry = {
                        "id": unit_id,
                        "source_path": result.get("source_path"),
                        "status": UnitStatus.FAILED,
                        "function_name": result.get("function_name"),
                        "reason": str(error)[:300] or type(error).__name__,
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

    report = {
        "schema_version": SCHEMA_VERSION,
        "kind": "elmos.repository-batch-report",
        # COMPLETE means every unit in the plan was attempted and passed. Any
        # skip, failure or partial selection keeps the batch at PARTIAL.
        "status": "COMPLETE" if complete else "PARTIAL",
        "repository_ref": discovery.get("repository_ref"),
        "snapshot_sha256": discovery.get("snapshot_sha256"),
        "repository_scale": discovery.get("repository_scale"),
        "repository_limits": discovery.get("repository_limits"),
        "route_id": discovery.get("route_id"),
        "source_language": source_language,
        "target_language": target_language,
        "language_lifecycle": language_lifecycle,
        "react_project_descriptor": declared_react_descriptor,
        "react_project_source_paths": declared_react_source_paths,
        "react_project_verification": declared_react_verification,
        "profile": discovery.get("profile"),
        "work_unit_count": len(results),
        "selected_count": len(selected),
        "resumed_count": resumed,
        "attempted_count": attempted,
        "unattempted_count": unattempted,
        "status_counts": counts,
        "units": outcomes,
        "react_project_descriptor": declared_react_descriptor,
        "external_verification_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
        "limitations": [
            "Per-unit passes are bounded-profile evidence; they are not a repository migration.",
            "Skipped and failed units keep the batch at PARTIAL and block any repository claim.",
            "Independent verification and external certification remain NOT_RUN.",
        ],
    }
    report_path = output / REPORT_NAME
    if (
        declared_react_descriptor is not None
        and react_project_descriptor(root) != declared_react_descriptor
    ):
        raise RouteError("REACT_PROJECT_DESCRIPTOR_CHANGED")
    if report_path.is_symlink() or (report_path.exists() and not report_path.is_file()):
        raise RouteError("BATCH_REPORT_OUTPUT_UNSAFE")
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _rewrite_checkpoint(checkpoint, outcomes)
    return report
