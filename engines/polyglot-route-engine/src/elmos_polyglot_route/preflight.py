"""Non-executing repository conversion capacity preflight."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .discovery import MAX_REPOSITORY_FUNCTIONAL_OBLIGATIONS, _preflight_inventory
from .models import Language, RouteError
from .repository import plan_repository

SCHEMA_VERSION = "1.0.0"
PREFLIGHT_KIND = "elmos.repository-conversion-preflight"


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def preflight_identity(report: dict[str, Any]) -> str:
    identity = {key: value for key, value in report.items() if key != "preflight_id"}
    return "sha256:" + hashlib.sha256(_canonical_bytes(identity)).hexdigest()


def repository_preflight(
    repository_root: Path,
    repository_ref: str,
    source_language: Language,
    target_language: Language,
) -> dict[str, Any]:
    """Plan and count declarations without invoking any native analyzer."""
    plan = plan_repository(repository_root, repository_ref, source_language, target_language)
    root = repository_root.resolve(strict=True)
    status = "PASSED"
    reason_code: str | None = None
    count_complete = True
    try:
        inventory = _preflight_inventory(
            plan["work_units"],
            root,
            source_language,
            limit=None,
        )
        obligation_count = sum(
            len(item["candidates"])
            + (0 if item["candidates"] and item["candidate_enumeration_complete"] else 1)
            for item in inventory
        )
        count_complete = all(bool(item["candidate_enumeration_complete"]) for item in inventory)
        status = "PASSED" if count_complete else "PASSED_WITH_INCOMPLETE_INVENTORY"
        actual_obligation_count = (
            sum(len(item["candidates"]) for item in inventory) if count_complete else None
        )
    except RouteError as error:
        if not str(error).startswith("FUNCTIONAL_OBLIGATION_LIMIT_EXCEEDED:"):
            raise
        status = "REJECTED"
        reason_code = "FUNCTIONAL_OBLIGATION_LIMIT_EXCEEDED"
        obligation_count = MAX_REPOSITORY_FUNCTIONAL_OBLIGATIONS + 1
        count_complete = False
        actual_obligation_count = None
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": PREFLIGHT_KIND,
        "preflight_id": "sha256:" + "0" * 64,
        "status": status,
        "reason_code": reason_code,
        "repository_ref": plan["repository_ref"],
        "snapshot_sha256": plan["snapshot_sha256"],
        "route_id": plan["route_id"],
        "source_language": source_language,
        "target_language": target_language,
        "obligation_count": obligation_count,
        "reported_obligation_lower_bound": obligation_count,
        "obligation_count_semantics": (
            "EXACT_REPORTED_ROWS" if count_complete else "REPORTED_ROW_LOWER_BOUND"
        ),
        "actual_obligation_count": actual_obligation_count,
        "actual_obligation_count_status": "EXACT" if actual_obligation_count is not None else "UNKNOWN",
        "obligation_limit": MAX_REPOSITORY_FUNCTIONAL_OBLIGATIONS,
        "count_complete": count_complete,
        "execution_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
    }
    report["preflight_id"] = preflight_identity(report)
    return report
