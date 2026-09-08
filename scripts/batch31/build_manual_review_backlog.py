#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

TERMINAL = {"RESOLVED", "WAIVED"}


def _digest(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return value


def _fingerprint(finding: dict[str, Any]) -> str:
    material = json.dumps(
        {
            "source_path": finding.get("source_path"),
            "statement_index": finding.get("statement_index"),
            "reason_code": finding.get("reason_code"),
            "excerpt": finding.get("excerpt"),
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return _digest(material)


def _recommended_action(reason_code: str) -> str:
    if "NAMESPACE_MAPPING_REQUIRED" in reason_code:
        return "Add an exact reviewed namespace mapping, regenerate, and rerun source/target validation."
    if "SOURCE_FORMAT" in reason_code or "PARSE_FAILED" in reason_code:
        return "Correct or explicitly classify the source statement, then rerun the scanner."
    if "ROUTINE" in reason_code or "STATIC_DO" in reason_code:
        return (
            "Hand-port through typed routine IR with source/target behavior evidence."
        )
    if "TYPE" in reason_code or "DECIMAL" in reason_code:
        return "Record an exact type policy and prove boundary, precision, null, and error behavior."
    return "Implement an exact typed adapter or hand-port, then attach target execution and revalidation evidence."


def _validate_resolution(item: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    status = item.get("status")
    resolution = item.get("resolution", {})
    waiver = item.get("waiver", {})
    revalidation = item.get("revalidation", {})
    if status == "RESOLVED":
        if resolution.get("strategy") == "NOT_SET" or not resolution.get(
            "artifact_refs"
        ):
            failures.append(
                f"{item.get('finding_id')}: resolved item has no implementation artifact"
            )
        if revalidation.get("status") != "PASSED" or not revalidation.get(
            "evidence_refs"
        ):
            failures.append(
                f"{item.get('finding_id')}: resolved item lacks passed revalidation evidence"
            )
    if status == "WAIVED":
        approvers = waiver.get("approved_by", [])
        distinct_approvers = {
            approver.strip()
            for approver in approvers
            if isinstance(approver, str) and approver.strip()
        }
        if waiver.get("status") != "APPROVED" or len(distinct_approvers) < 2:
            failures.append(
                f"{item.get('finding_id')}: waiver needs two distinct approvers"
            )
        if not waiver.get("expires_at") or not waiver.get("reason"):
            failures.append(f"{item.get('finding_id')}: waiver needs expiry and reason")
    return failures


def build(report_path: Path, existing_path: Path | None = None) -> dict[str, Any]:
    report_bytes = report_path.read_bytes()
    report = json.loads(report_bytes)
    if not isinstance(report, dict):
        raise TypeError("scan report must be a JSON object")
    findings = report.get("findings")
    if not isinstance(findings, list):
        raise TypeError("scan report must be generated with --all-findings")
    manual = [
        item
        for item in findings
        if isinstance(item, dict)
        and item.get("disposition") == "MANUAL_MIGRATION_REQUIRED"
    ]
    declared = report.get("disposition_counts", {}).get("MANUAL_MIGRATION_REQUIRED")
    if declared != len(manual):
        raise ValueError(
            f"manual finding count mismatch: report={declared!r} findings={len(manual)}"
        )

    previous_by_id: dict[str, dict[str, Any]] = {}
    if existing_path is not None:
        for item in _load(existing_path).get("items", []):
            if isinstance(item, dict) and isinstance(item.get("finding_id"), str):
                previous_by_id[item["finding_id"]] = item

    items: list[dict[str, Any]] = []
    identities: set[str] = set()
    for finding in manual:
        fingerprint = _fingerprint(finding)
        finding_id = f"sql-review-{fingerprint.removeprefix('sha256:')[:20]}"
        if finding_id in identities:
            raise ValueError(f"duplicate manual finding identity: {finding_id}")
        identities.add(finding_id)
        item = {
            "finding_id": finding_id,
            "fingerprint": fingerprint,
            "source_path": finding["source_path"],
            "statement_index": finding["statement_index"],
            "reason_code": finding["reason_code"],
            "reason": finding["reason"],
            "family": finding.get("family"),
            "excerpt": finding.get("excerpt", ""),
            "status": "OPEN",
            "owner": "UNASSIGNED",
            "recommended_action": _recommended_action(str(finding["reason_code"])),
            "resolution": {"strategy": "NOT_SET", "artifact_refs": []},
            "waiver": {
                "status": "NOT_REQUESTED",
                "approved_by": [],
                "expires_at": None,
                "reason": None,
            },
            "revalidation": {"status": "NOT_RUN", "evidence_refs": []},
        }
        previous = previous_by_id.get(finding_id)
        if previous is not None and previous.get("fingerprint") == fingerprint:
            for field in ("status", "owner", "resolution", "waiver", "revalidation"):
                item[field] = previous.get(field, item[field])
        items.append(item)

    items.sort(
        key=lambda item: (
            item["source_path"],
            item["statement_index"],
            item["finding_id"],
        )
    )
    states = Counter(str(item["status"]) for item in items)
    return {
        "schema_version": 1,
        "kind": "elmos.batch31.manual-review-backlog",
        "source_report_digest": _digest(report_bytes),
        "summary": {
            "total": len(items),
            "open": states["OPEN"],
            "in_review": states["IN_REVIEW"],
            "resolved": states["RESOLVED"],
            "waived": states["WAIVED"],
            "blocked": states["BLOCKED"],
            "release_blocked": any(item["status"] not in TERMINAL for item in items),
        },
        "items": items,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scan_report", type=Path)
    parser.add_argument("--existing", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-closed", action="store_true")
    args = parser.parse_args()
    backlog = build(args.scan_report, args.existing)
    failures = [
        failure for item in backlog["items"] for failure in _validate_resolution(item)
    ]
    if failures:
        print(
            "\n".join(f"BACKLOG INVALID: {failure}" for failure in failures),
            file=sys.stderr,
        )
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(backlog, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"BACKLOG: total={backlog['summary']['total']} open={backlog['summary']['open']} "
        f"release_blocked={str(backlog['summary']['release_blocked']).lower()}"
    )
    if args.require_closed and backlog["summary"]["release_blocked"]:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
