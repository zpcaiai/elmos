#!/usr/bin/env python3
"""Turn a GitHub Dependabot alert snapshot into bounded Batch 40 evidence.

The tool deliberately does not call GitHub itself.  A caller must provide the
exact JSON response captured from the approved API request.  This keeps
credentials and network authority outside the repository-owned analyzer while
making the result deterministic and replayable.

Exit codes:
  0: the snapshot is valid and has no open alerts above ``--max-open``.
  2: the snapshot or scope is malformed; fail closed.
  3: the snapshot is valid but the open-alert threshold is exceeded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ALLOWED_STATES = {"open", "fixed", "dismissed", "auto_dismissed"}
ALLOWED_SEVERITIES = {"critical", "high", "medium", "low"}
SEVERITY_ALIASES = {"moderate": "medium"}
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class AlertSnapshotError(ValueError):
    """Raised when an alert snapshot cannot support a trustworthy result."""


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def replay_command(endpoint: str) -> str:
    """Return the exact GitHub CLI form for replaying this API request."""
    api_path = endpoint.removeprefix("https://api.github.com/")
    target = api_path if api_path != endpoint else endpoint
    return f"gh api {target} --paginate --slurp"


def _non_empty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AlertSnapshotError(f"{label} must be a non-empty string")
    return value.strip()


def _flatten_pages(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise AlertSnapshotError("snapshot must be a JSON array or paginated JSON array")
    if not payload:
        return []
    if all(isinstance(item, dict) for item in payload):
        return payload
    if not all(isinstance(page, list) for page in payload):
        raise AlertSnapshotError("paginated snapshot must contain only JSON arrays")
    alerts: list[dict[str, Any]] = []
    for page in payload:
        if not all(isinstance(item, dict) for item in page):
            raise AlertSnapshotError("each snapshot page must contain only JSON objects")
        alerts.extend(page)
    return alerts


def _severity(alert: dict[str, Any], number: int) -> str:
    advisory = alert.get("security_advisory")
    vulnerability = alert.get("security_vulnerability")
    advisory = advisory if isinstance(advisory, dict) else {}
    vulnerability = vulnerability if isinstance(vulnerability, dict) else {}
    value = advisory.get("severity") or vulnerability.get("severity")
    value = SEVERITY_ALIASES.get(value, value)
    if value not in ALLOWED_SEVERITIES:
        raise AlertSnapshotError(
            f"open alert {number} has no supported security severity"
        )
    return value


def _normalized_alert(alert: dict[str, Any], state: str, number: int) -> dict[str, Any]:
    dependency = alert.get("dependency")
    if not isinstance(dependency, dict):
        raise AlertSnapshotError(f"alert {number} dependency is missing")
    package = dependency.get("package")
    if not isinstance(package, dict):
        raise AlertSnapshotError(f"alert {number} dependency package is missing")
    package_name = _non_empty_string(package.get("name"), f"alert {number} package name")
    manifest_path = _non_empty_string(
        dependency.get("manifest_path"), f"alert {number} manifest path"
    )
    advisory = alert.get("security_advisory")
    vulnerability = alert.get("security_vulnerability")
    advisory = advisory if isinstance(advisory, dict) else {}
    vulnerability = vulnerability if isinstance(vulnerability, dict) else {}
    result: dict[str, Any] = {
        "number": number,
        "state": state,
        "package": package_name,
        "manifestPath": manifest_path,
    }
    if state == "open":
        result.update(
            {
                "severity": _severity(alert, number),
                "ghsaId": _non_empty_string(
                    advisory.get("ghsa_id"), f"open alert {number} GHSA id"
                ),
                "vulnerableVersionRange": vulnerability.get("vulnerable_version_range"),
                "firstPatchedVersion": (
                    (vulnerability.get("first_patched_version") or {}).get("identifier")
                    if isinstance(vulnerability.get("first_patched_version"), dict)
                    else None
                ),
            }
        )
    return result


def analyze_snapshot(
    raw: bytes,
    payload: Any,
    *,
    repository: str,
    commit: str,
    endpoint: str,
    queried_at: str,
    max_open: int = 0,
) -> dict[str, Any]:
    if not REPOSITORY_PATTERN.fullmatch(repository):
        raise AlertSnapshotError("repository must be owner/name")
    if not COMMIT_PATTERN.fullmatch(commit):
        raise AlertSnapshotError("commit must be a full 40-character SHA-1")
    if not isinstance(endpoint, str) or not endpoint.startswith("https://"):
        raise AlertSnapshotError("endpoint must be an HTTPS URL")
    if max_open < 0:
        raise AlertSnapshotError("max-open cannot be negative")
    try:
        parsed_time = datetime.fromisoformat(queried_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AlertSnapshotError("queried-at must be an ISO-8601 timestamp") from exc
    if parsed_time.tzinfo is None:
        raise AlertSnapshotError("queried-at must include a timezone")

    alerts = _flatten_pages(payload)
    seen_numbers: set[int] = set()
    normalized: list[dict[str, Any]] = []
    state_counts: Counter[str] = Counter()
    open_alerts: list[dict[str, Any]] = []
    for index, alert in enumerate(alerts):
        raw_number = alert.get("number")
        if isinstance(raw_number, bool) or not isinstance(raw_number, int) or raw_number <= 0:
            raise AlertSnapshotError(f"alert at index {index} has an invalid number")
        if raw_number in seen_numbers:
            raise AlertSnapshotError(f"duplicate alert number {raw_number}")
        seen_numbers.add(raw_number)
        state = alert.get("state")
        if state not in ALLOWED_STATES:
            raise AlertSnapshotError(f"alert {raw_number} has an unsupported state")
        item = _normalized_alert(alert, state, raw_number)
        normalized.append(item)
        state_counts[state] += 1
        if state == "open":
            open_alerts.append(item)

    open_alerts.sort(key=lambda item: item["number"])
    open_by_severity = {severity: 0 for severity in sorted(ALLOWED_SEVERITIES)}
    for alert in open_alerts:
        open_by_severity[alert["severity"]] += 1
    open_count = len(open_alerts)
    status = "PASS" if open_count <= max_open else "BLOCKED"
    blockers = [
        f"open Dependabot alert #{item['number']} {item['severity']} "
        f"{item['package']} ({item['manifestPath']})"
        for item in open_alerts[max_open:]
    ]
    return {
        "check": "batch40-dependabot-alerts",
        "batch": 40,
        "status": status,
        "repository": repository,
        "commit": commit,
        "endpoint": endpoint,
        "queriedAt": parsed_time.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "replayCommand": replay_command(endpoint),
        "inputSha256": sha256_bytes(raw),
        "alertCount": len(normalized),
        "stateCounts": dict(sorted(state_counts.items())),
        "openCount": open_count,
        "openBySeverity": open_by_severity,
        "maxOpen": max_open,
        "metrics": {
            "criticalVulnerabilityCount": open_by_severity["critical"],
            "highVulnerabilityCount": open_by_severity["high"],
        },
        "openAlerts": open_alerts,
        "blockers": blockers,
        "limitations": [
            "This is an exact GitHub Dependabot alert API snapshot, not a complete build-graph SCA result.",
            "A clean snapshot does not prove that unreported, unreachable, or non-GitHub advisories do not exist.",
            "The snapshot is self-attested evidence until an independently authorized verifier signs it.",
        ],
        "alerts": normalized,
    }


def _write_report(path: Path | None, report: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_raw_snapshot(path: Path | None, raw: bytes) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--alerts-file", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--queried-at", required=True)
    parser.add_argument("--max-open", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--raw-output",
        type=Path,
        help="optional path that receives the exact input snapshot bytes",
    )
    args = parser.parse_args(argv)

    try:
        raw = args.alerts_file.read_bytes()
        _write_raw_snapshot(args.raw_output, raw)
        payload = json.loads(raw.decode("utf-8"))
        report = analyze_snapshot(
            raw,
            payload,
            repository=args.repository,
            commit=args.commit,
            endpoint=args.endpoint,
            queried_at=args.queried_at,
            max_open=args.max_open,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, AlertSnapshotError) as exc:
        report = {
            "check": "batch40-dependabot-alerts",
            "batch": 40,
            "status": "INVALID",
            "error": str(exc),
        }
        _write_report(args.output, report)
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    _write_report(args.output, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
