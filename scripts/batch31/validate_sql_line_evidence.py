#!/usr/bin/env python3
"""Validate that checked-in SQL launch evidence is current and fail-closed."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs" / "batch31" / "evidence"
SOURCE_ROOT = (
    ROOT / "modules" / "persistence" / "src" / "main" / "resources" / "db" / "migration"
)
EXPECTED_TRANSLATION_POLICY = {
    "typeMigration": {
        "jsonBinary": "json",
        "array": "fail-closed",
        "unboundedDecimal": "fail-closed",
        "unboundedVarchar": "postgres-only",
        "unsignedBigint": "ask",
    },
    "allowTriggerShim": True,
    "allowAlterColumn": False,
    "allowIndexShim": False,
    "allowIfNotExistsShim": False,
    "allowSchemaShim": False,
    "allowRlsShim": True,
    "allowPrivilegeShim": True,
    "allowCommentShim": False,
    "allowIndexExpressionShim": False,
    "allowRoutineShim": False,
    "allowMysqlTextPrefix": False,
    "allowCheckShim": False,
    "allowMysqlTextDefault": False,
    "allowReservedWordShim": False,
}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return value


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _source_tree() -> tuple[int, str]:
    digest = hashlib.sha256()
    paths = sorted(SOURCE_ROOT.rglob("*.sql"))
    for path in paths:
        digest.update(path.relative_to(SOURCE_ROOT).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return len(paths), "sha256:" + digest.hexdigest()


def validate() -> list[str]:
    summary_path = EVIDENCE / "sql-corpus-scan-summary.json"
    reachability_path = EVIDENCE / "sql-target-reachability.json"
    backlog_path = EVIDENCE / "sql-manual-review-backlog.json"
    closure_path = EVIDENCE / "sql-route-closure-plan.json"
    summary = _load(summary_path)
    reachability = _load(reachability_path)
    backlog = _load(backlog_path)
    closure = _load(closure_path)
    failures: list[str] = []

    def require(condition: bool, code: str) -> None:
        if not condition:
            failures.append(code)

    scan_report_ref = summary.get("scan_report_path")
    require(
        scan_report_ref == "docs/batch31/evidence/sql-corpus-scan-report.json",
        "SCAN_REPORT_PATH_MISSING",
    )
    scan_report_path = ROOT / str(scan_report_ref)
    require(scan_report_path.is_file(), "SCAN_REPORT_MISSING")
    if scan_report_path.is_file():
        require(
            summary.get("scan_report_digest") == _digest(scan_report_path),
            "SCAN_REPORT_DIGEST_DRIFT",
        )

    totals = summary.get("totals", {})
    current = closure.get("current", {})
    files, source_tree_digest = _source_tree()
    discovered = reachability.get("discovered_units")
    admitted = reachability.get("admitted_source_side")
    manual = backlog.get("summary", {}).get("total")
    candidate_rate = (
        round(admitted / discovered, 4)
        if isinstance(admitted, int) and isinstance(discovered, int) and discovered
        else -1
    )
    source_review = (
        discovered - admitted - manual
        if all(isinstance(value, int) for value in (discovered, admitted, manual))
        else -1
    )

    require(
        summary.get("source_tree_digest") == source_tree_digest,
        "SOURCE_TREE_DIGEST_STALE",
    )
    require(totals.get("files") == files, "SOURCE_FILE_COUNT_STALE")
    require(totals.get("discovered") == discovered, "DISCOVERED_COUNT_DRIFT")
    require(
        totals.get("automated_translation_candidates") == admitted,
        "ADMITTED_COUNT_DRIFT",
    )
    require(totals.get("manual_migration_required") == manual, "MANUAL_COUNT_DRIFT")
    require(
        totals.get("source_format_review") == source_review, "SOURCE_REVIEW_COUNT_DRIFT"
    )
    require(
        backlog.get("summary", {}).get("total") == len(backlog.get("items", [])),
        "BACKLOG_ITEM_DRIFT",
    )
    require(
        summary.get("reachability_report_digest") == _digest(reachability_path),
        "REACHABILITY_DIGEST_DRIFT",
    )
    require(
        summary.get("scan_report_digest") == backlog.get("source_report_digest"),
        "SCAN_REPORT_DIGEST_DRIFT",
    )
    require(
        totals.get("automatic_candidate_rate") == candidate_rate,
        "AUTOMATIC_CANDIDATE_RATE_DRIFT",
    )

    four = summary.get("four_target_reachability", {})
    require(
        four.get("intersection") == reachability.get("translatable_to_all_four"),
        "INTERSECTION_COUNT_DRIFT",
    )
    require(
        four.get("intersection_rate_of_candidates")
        == reachability.get("all_four_ratio_of_admitted"),
        "INTERSECTION_RATE_DRIFT",
    )
    for target in ("postgres", "mysql", "oracle", "tsql"):
        require(
            four.get(target)
            == reachability.get("reachable_per_target", {}).get(target),
            f"{target.upper()}_COUNT_DRIFT",
        )

    ledger = summary.get("chinadb_route_ledger", {})
    expected_route_units = discovered * 13 if isinstance(discovered, int) else -1
    require(ledger.get("target_count") == 13, "CHINADB_TARGET_COUNT_DRIFT")
    require(
        ledger.get("route_units") == expected_route_units, "CHINADB_ROUTE_UNIT_DRIFT"
    )
    require(
        ledger.get("disposition_covered") == expected_route_units,
        "CHINADB_DISPOSITION_DRIFT",
    )
    require(ledger.get("automatic_target_emissions") == 0, "CHINADB_EMISSION_OVERCLAIM")

    require(
        reachability.get("translationPolicy") == EXPECTED_TRANSLATION_POLICY,
        "TRANSLATION_POLICY_DRIFT",
    )

    require(
        current.get("frozenSourceUnits") == discovered, "CLOSURE_SOURCE_COUNT_DRIFT"
    )
    require(
        current.get("admittedCandidateUnits") == admitted,
        "CLOSURE_ADMITTED_COUNT_DRIFT",
    )
    require(current.get("manualMigrationItems") == manual, "CLOSURE_MANUAL_COUNT_DRIFT")
    require(
        current.get("sourceFormatReviewItems") == source_review,
        "CLOSURE_SOURCE_REVIEW_DRIFT",
    )
    require(
        current.get("manualMigrationOpen")
        == backlog.get("summary", {}).get("open", 0)
        + backlog.get("summary", {}).get("in_review", 0)
        + backlog.get("summary", {}).get("blocked", 0),
        "CLOSURE_MANUAL_OPEN_DRIFT",
    )
    p0_cells = sum(
        item.get("routeCellCount", 0)
        for item in closure.get("workstreams", [])
        if item.get("priority") == "P0"
    )
    require(p0_cells == 0, "P0_ROUTE_CELLS_OPEN")
    require(
        closure.get("executionSequence", [{}])[0].get("state") == "PASSED",
        "P0_SEQUENCE_NOT_PASSED",
    )
    require(
        closure.get("inputs", {}).get("reachabilityDigest")
        == _digest(reachability_path),
        "CLOSURE_REACHABILITY_DIGEST_DRIFT",
    )
    require(
        closure.get("inputs", {}).get("manualBacklogDigest") == _digest(backlog_path),
        "CLOSURE_BACKLOG_DIGEST_DRIFT",
    )

    for document in (summary, reachability):
        require(
            document.get("externalExecution", document.get("external_execution"))
            == "NOT_RUN",
            "EXTERNAL_EXECUTION_OVERCLAIM",
        )
        require(
            document.get(
                "independentVerification", document.get("independent_verification")
            )
            == "NOT_RUN",
            "INDEPENDENT_VERIFICATION_OVERCLAIM",
        )
        require(
            document.get("certification") == "NOT_CERTIFIED", "CERTIFICATION_OVERCLAIM"
        )
    require(
        current.get("externalExecution") == "NOT_RUN",
        "CLOSURE_EXTERNAL_EXECUTION_OVERCLAIM",
    )
    require(
        current.get("independentVerification") == "NOT_RUN",
        "CLOSURE_INDEPENDENT_VERIFICATION_OVERCLAIM",
    )
    require(
        current.get("certification") == "NOT_CERTIFIED",
        "CLOSURE_CERTIFICATION_OVERCLAIM",
    )

    sql_claims = [
        line
        for line in (ROOT / "README.md").read_text(encoding="utf-8").splitlines()
        if "数据库与 SQL 方言迁移" in line or "SQL 方言转写与国产数据库" in line
    ]
    require(bool(sql_claims), "README_SQL_STATUS_MISSING")
    require(
        all("NOT_CERTIFIED" in line for line in sql_claims),
        "README_SQL_CERTIFICATION_OVERCLAIM",
    )
    return failures


def main() -> int:
    failures = validate()
    if failures:
        for failure in failures:
            print(f"SQL LINE EVIDENCE INVALID: {failure}")
        return 2
    print(
        "SQL LINE EVIDENCE: PASS (external execution NOT_RUN; certification NOT_CERTIFIED)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
