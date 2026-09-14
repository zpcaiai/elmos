#!/usr/bin/env python3
"""Build the checked-in SQL-line summary from raw scanner evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return value


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _source_tree(root: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    paths = sorted(root.rglob("*.sql"))
    for path in paths:
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return len(paths), "sha256:" + digest.hexdigest()


def build(
    scan_path: Path,
    reachability_path: Path,
    source_root: Path,
    source_root_label: str,
) -> dict[str, Any]:
    scan = _load(scan_path)
    reachability = _load(reachability_path)
    totals = scan.get("totals", {})
    dispositions = scan.get("disposition_counts", {})
    namespace_profile = scan.get("namespace_profile")
    if namespace_profile != reachability.get("namespaceProfile"):
        raise ValueError("scan and reachability namespace profiles differ")
    if totals.get("discovered") != reachability.get("discovered_units"):
        raise ValueError("scan and reachability discovered counts differ")
    if totals.get("inSubset") != reachability.get("admitted_source_side"):
        raise ValueError("scan and reachability admitted counts differ")
    if totals.get("scanErrors") != 0 or totals.get("dispositionUnknown") != 0:
        raise ValueError("scan has engine errors or unknown dispositions")
    files, source_tree_digest = _source_tree(source_root)
    if files != totals.get("files"):
        raise ValueError("source SQL file count differs from scanner evidence")
    discovered = int(totals["discovered"])
    admitted = int(totals["inSubset"])
    manual = int(dispositions.get("MANUAL_MIGRATION_REQUIRED", -1))
    source_review = int(dispositions.get("SOURCE_FORMAT_REVIEW", -1))
    if admitted + manual + source_review != discovered:
        raise ValueError("scanner dispositions do not cover every source unit")
    china = scan.get("chinadb_coverage", {})
    if china.get("routeUnits") != discovered * china.get("targetCount", 0):
        raise ValueError("ChinaDB route ledger does not cover every source unit")
    common = int(reachability["translatable_to_all_four"])
    return {
        "schema_version": 1,
        "kind": "elmos.batch31.sql-corpus-scan-summary",
        "scanned_at": scan.get("scanned_at"),
        "source_root": source_root_label,
        "source_dialect": scan.get("source_dialect"),
        "namespace_profile": namespace_profile,
        "source_tree_digest": source_tree_digest,
        "scan_report_path": "docs/batch31/evidence/sql-corpus-scan-report.json",
        "scan_report_digest": _digest(scan_path),
        "reachability_report_digest": _digest(reachability_path),
        "totals": {
            "files": files,
            "discovered": discovered,
            "automated_translation_candidates": admitted,
            "manual_migration_required": manual,
            "source_format_review": source_review,
            "engine_defects": 0,
            "disposition_coverage": 1.0,
            "automatic_candidate_rate": round(admitted / discovered, 4),
        },
        "four_target_reachability": {
            "intersection": common,
            "intersection_rate_of_candidates": round(common / admitted, 4),
            **reachability["reachable_per_target"],
        },
        "chinadb_route_ledger": {
            "target_count": china["targetCount"],
            "planned_routes": china["plannedRouteCount"],
            "route_units": china["routeUnits"],
            "disposition_covered": china["routeDispositionCovered"],
            "automatic_target_emissions": china["automaticTargetEmissions"],
            "implementation_status": "LOCAL_BOUNDED",
            "external_execution": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        },
        "replay": [
            "uv --directory engines/sql-dialect-engine run --locked elmos-sql-dialect scan --repository \"$(pwd)/modules/persistence/src/main/resources/db/migration\" --source-dialect postgres --namespace-profile '{\"name\":\"persistence-public-to-dbo\",\"mapping\":{\"\":\"dbo\",\"public\":\"dbo\"}}' --require-disposition-complete --all-findings --output <output-dir>",
            "uv --directory engines/sql-dialect-engine run --locked python tools/target_reachability.py --corpus \"persistence=$(pwd)/modules/persistence/src/main/resources/db/migration=postgres\" --namespace-profile '{\"name\":\"persistence-public-to-dbo\",\"mapping\":{\"\":\"dbo\",\"public\":\"dbo\"}}' --policy-json-binary json --allow-trigger-shim --allow-rls-shim --allow-privilege-shim --output <output-json>",
        ],
        "external_execution": "NOT_RUN",
        "independent_verification": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan-report", type=Path, required=True)
    parser.add_argument("--reachability", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--source-root-label", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rendered = json.dumps(
        build(
            args.scan_report,
            args.reachability,
            args.source_root,
            args.source_root_label,
        ),
        ensure_ascii=False,
        indent=2,
    ) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
