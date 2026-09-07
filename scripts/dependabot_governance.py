"""Inventory, govern, and optionally dismiss only eligible Dependabot alerts.

An alert dismissed by this tool is recorded as accepted residual risk, never as
fixed. Runtime manifests must be remediated in source first; immutable corpus
and explicitly EOL compatibility fixtures are handled by a short-lived,
digest-bound exception registry.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

IMMUTABLE_PREFIXES = (
    ".matrix",
    "routes/",
    "verification-packs/",
    "client-packs/",
    "skills/migration-platform-batch20-b29-b45-mature-complete-strict-tests/",
)
EOL_PACKAGES = {"vue", "vue-template-compiler", "vue-server-renderer"}
SCHEMA_VERSION = "1.0"


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()


def alert_key(alert: Mapping[str, Any]) -> dict[str, Any]:
    dependency = alert.get("dependency") or {}
    package = dependency.get("package") or {}
    advisory = alert.get("security_advisory") or {}
    return {
        "alert_number": int(alert["number"]),
        "ecosystem": str(package.get("ecosystem", "")),
        "package": str(package.get("name", "")),
        "manifest_path": str(dependency.get("manifest_path", "")),
        "ghsa_id": str(advisory.get("ghsa_id", "")),
        "severity": str(advisory.get("severity", "")),
    }


def classify(alert: Mapping[str, Any]) -> str | None:
    key = alert_key(alert)
    if key["manifest_path"].startswith(IMMUTABLE_PREFIXES):
        return "immutable_evidence"
    if (
        key["ecosystem"] == "npm"
        and key["package"] in EOL_PACKAGES
        and key["manifest_path"].startswith(IMMUTABLE_PREFIXES)
    ):
        return "eol_compatibility"
    return None


def build_registry(
    repo: str, alerts: Sequence[Mapping[str, Any]], *, now: datetime | None = None
) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    expires = (
        (current + timedelta(days=90))
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    snapshot_digest = digest([alert_key(alert) for alert in alerts])
    exceptions: list[dict[str, Any]] = []
    for alert in sorted(alerts, key=lambda item: int(item["number"])):
        classification = classify(alert)
        if classification is None:
            continue
        controls = (
            [
                "immutable-byte-digest-and-source-corpus-retained",
                "no-runtime-install-or-production-deployment",
                "revalidate-on-every-release-and-before-expiry",
            ]
            if classification == "immutable_evidence"
            else [
                "vue2-route-isolated-from-new-production-routes",
                "migration-to-vue3-is-required-before-support-expansion",
                "revalidate-on-every-release-and-before-expiry",
            ]
        )
        exceptions.append(
            {
                **alert_key(alert),
                "classification": classification,
                "decision": "dismiss_tolerable_risk",
                "status": "ACTIVE",
                "reason": "The alert belongs to an immutable evidence/corpus fixture or an explicitly retained EOL Vue 2 compatibility route; it is not declared fixed.",
                "controls": controls,
                "owner": "elmos-security-owner",
                "expires_at": expires,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "repository": repo,
        "generated_at": current.isoformat().replace("+00:00", "Z"),
        "source_alert_snapshot_digest": snapshot_digest,
        "exceptions": exceptions,
        "fixed_claims": [],
        "certification": "NOT_CERTIFIED",
    }


def validate_registry(
    registry: Mapping[str, Any],
    alerts: Sequence[Mapping[str, Any]],
    *,
    now: datetime | None = None,
) -> None:
    if set(registry) != {
        "schema_version",
        "repository",
        "generated_at",
        "source_alert_snapshot_digest",
        "exceptions",
        "fixed_claims",
        "certification",
    }:
        raise ValueError("Dependabot registry shape is not exact")
    if (
        registry["schema_version"] != SCHEMA_VERSION
        or registry["certification"] != "NOT_CERTIFIED"
        or registry["fixed_claims"] != []
    ):
        raise ValueError("Dependabot registry cannot certify or claim fixes")
    by_number = {int(alert["number"]): alert for alert in alerts}
    if len(by_number) != len(alerts):
        raise ValueError("Dependabot snapshot contains duplicate alert numbers")
    expected_snapshot = digest([alert_key(alert) for alert in alerts])
    if registry["source_alert_snapshot_digest"] != expected_snapshot:
        raise ValueError(
            "Dependabot exception registry is bound to a different alert snapshot"
        )
    exceptions = registry["exceptions"]
    if not isinstance(exceptions, list):
        raise TypeError("Dependabot exceptions must be a list")
    seen: set[int] = set()
    current = now or datetime.now(timezone.utc)
    for exception in exceptions:
        if not isinstance(exception, Mapping):
            raise TypeError("Dependabot exception must be an object")
        number = int(exception.get("alert_number", -1))
        if number in seen or number not in by_number:
            raise ValueError("Dependabot exception alert identity is invalid")
        seen.add(number)
        alert = by_number[number]
        if any(
            exception.get(field) != alert_key(alert)[field]
            for field in (
                "ecosystem",
                "package",
                "manifest_path",
                "ghsa_id",
                "severity",
            )
        ):
            raise ValueError("Dependabot exception alert binding changed")
        if (
            exception.get("classification") != classify(alert)
            or exception.get("decision") != "dismiss_tolerable_risk"
            or exception.get("status") != "ACTIVE"
        ):
            raise ValueError(
                "Dependabot exception is not an eligible tolerable-risk decision"
            )
        if (
            not isinstance(exception.get("controls"), list)
            or len(exception["controls"]) < 2
            or not all(isinstance(item, str) and item for item in exception["controls"])
        ):
            raise ValueError("Dependabot exception controls are incomplete")
        expiry = _parse_time(exception.get("expires_at"))
        if expiry <= current or expiry > current + timedelta(days=180):
            raise ValueError(
                "Dependabot exception expiry is outside the allowed window"
            )


def fetch_open_alerts(repo: str) -> list[dict[str, Any]]:
    result = subprocess.run(
        [
            "gh",
            "api",
            "--paginate",
            "-H",
            "Accept: application/vnd.github+json",
            f"/repos/{repo}/dependabot/alerts?state=open&per_page=100",
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=120,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("GitHub Dependabot inventory failed")
    value = json.loads(result.stdout)
    if not isinstance(value, list):
        raise TypeError("GitHub Dependabot response is not a list")
    return [dict(item) for item in value if isinstance(item, Mapping)]


def dismiss_eligible(
    repo: str, registry: Mapping[str, Any], alerts: Sequence[Mapping[str, Any]]
) -> int:
    validate_registry(registry, alerts)
    by_number = {int(alert["number"]): alert for alert in alerts}
    count = 0
    for exception in registry["exceptions"]:
        number = int(exception["alert_number"])
        classification = str(exception["classification"])
        comment = (
            "Accepted residual risk, not fixed. "
            + classification
            + "; controls: "
            + ", ".join(str(item) for item in exception["controls"])
            + "; expires "
            + str(exception["expires_at"])
        )
        result = subprocess.run(
            [
                "gh",
                "api",
                "--method",
                "PATCH",
                "-H",
                "Accept: application/vnd.github+json",
                f"/repos/{repo}/dependabot/alerts/{number}",
                "-f",
                "state=dismissed",
                "-f",
                "dismissed_reason=tolerable_risk",
                "-f",
                "dismissed_comment=" + comment,
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=60,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Dependabot alert dismissal failed for alert {number}")
        count += 1
        del by_number[number]
    return count


def _parse_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise TypeError("Dependabot exception expiry is invalid")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError("Dependabot exception expiry is invalid") from error
    if parsed.tzinfo is None:
        raise ValueError("Dependabot exception expiry must include a timezone")
    return parsed.astimezone(timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="zpcaiai/elmos")
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--registry", required=True)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="dismiss only registry-listed eligible alerts",
    )
    args = parser.parse_args()
    alerts = fetch_open_alerts(args.repo)
    snapshot_path = Path(args.snapshot)
    snapshot_path.write_bytes(canonical([alert_key(alert) for alert in alerts]))
    registry_path = Path(args.registry)
    if registry_path.exists():
        registry = json.loads(registry_path.read_bytes())
    else:
        registry = build_registry(args.repo, alerts)
        registry_path.write_bytes(canonical(registry))
    validate_registry(registry, alerts)
    eligible = len(registry["exceptions"])
    print(
        json.dumps(
            {
                "open_alerts": len(alerts),
                "eligible_residual_risk": eligible,
                "apply": args.apply,
            },
            sort_keys=True,
        )
    )
    if args.apply:
        print(
            json.dumps(
                {"dismissed": dismiss_eligible(args.repo, registry, alerts)},
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
