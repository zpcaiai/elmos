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

import json
from pathlib import Path
from typing import Any

from .engine import migrate
from .models import SUPPORTED_LANGUAGES, RouteError

SCHEMA_VERSION = "1.0.0"
CHECKPOINT_NAME = "batch-checkpoint.jsonl"
REPORT_NAME = "batch-report.json"


class UnitStatus:
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED_NOT_READY = "SKIPPED_NOT_READY"
    SKIPPED_NO_CASES = "SKIPPED_NO_CASES"


def _load_checkpoint(path: Path) -> dict[str, dict[str, Any]]:
    """Read prior per-unit outcomes so an interrupted batch can resume."""
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
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()


def _case_file(cases_directory: Path, unit_id: str) -> Path | None:
    candidate = cases_directory / f"{unit_id}.json"
    if candidate.is_symlink():
        raise RouteError(f"BEHAVIOR_CASES_SYMLINK_REJECTED:{unit_id}")
    return candidate if candidate.is_file() else None


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
    output.mkdir(parents=True, exist_ok=True)
    checkpoint = output / CHECKPOINT_NAME
    recorded = _load_checkpoint(checkpoint)

    selected = results if limit is None else results[:limit]
    outcomes: list[dict[str, Any]] = []
    resumed = 0

    for result in selected:
        unit_id = str(result.get("id", ""))
        if not unit_id:
            raise RouteError("DISCOVERY_RESULT_ID_REQUIRED")
        if unit_id in recorded:
            outcomes.append({**recorded[unit_id], "resumed_from_checkpoint": True})
            resumed += 1
            continue

        entry: dict[str, Any]
        if result.get("verdict") != "READY":
            entry = {
                "id": unit_id,
                "source_path": result.get("source_path"),
                "status": UnitStatus.SKIPPED_NOT_READY,
                "reason": str(result.get("verdict", "UNKNOWN")),
            }
        else:
            cases = _case_file(cases_directory, unit_id)
            if cases is None:
                entry = {
                    "id": unit_id,
                    "source_path": result.get("source_path"),
                    "status": UnitStatus.SKIPPED_NO_CASES,
                    "reason": "No independent behavior-case corpus was supplied for this unit.",
                }
            else:
                source = (root / str(result["source_path"])).resolve()
                if not str(source).startswith(str(root)):
                    raise RouteError(f"WORK_UNIT_PATH_ESCAPES_REPOSITORY:{result['source_path']}")
                unit_output = output / "units" / unit_id
                try:
                    report = migrate(
                        source,
                        source_language,
                        target_language,
                        str(result["function_name"]),
                        cases,
                        unit_output,
                    )
                    entry = {
                        "id": unit_id,
                        "source_path": result.get("source_path"),
                        "status": UnitStatus.PASSED,
                        "function_name": result.get("function_name"),
                        "behavior_case_count": report.get("behavior_case_count"),
                        "target_path": report.get("target", {}).get("path"),
                        "target_sha256": report.get("target", {}).get("sha256"),
                        "evidence_path": f"units/{unit_id}/route-evidence.json",
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
                    }
        _append_checkpoint(checkpoint, entry)
        outcomes.append(entry)

    counts: dict[str, int] = {}
    for outcome in outcomes:
        counts[outcome["status"]] = counts.get(outcome["status"], 0) + 1

    attempted = counts.get(UnitStatus.PASSED, 0) + counts.get(UnitStatus.FAILED, 0)
    unattempted = len(results) - attempted
    complete = (
        counts.get(UnitStatus.FAILED, 0) == 0
        and unattempted == 0
        and len(selected) == len(results)
    )

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
