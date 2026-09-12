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
import re
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
IMMUTABLE_SOURCE_PREFIXES = (
    "client-packs/frontend-to-miniapp-vue3-wechat-v1/source-snapshots/",
    "client-packs/web-console-next16-react19-wechat-v1/source-snapshots/",
    "skills/elmos-autonomous-qa-self-healing-skills-v1.1.0/",
    "skills/subskills/sub/elmos-assurance-skills-v4.0.0/",
)
IMMUTABLE_CERTIFICATION_PREFIXES = (
    "routes/cpp-to-java/certification/formal-artifacts/",
)
VUE2_COMPATIBILITY_MANIFESTS = frozenset(
    {
        "client-packs/frontend-72-route-equivalence-v1/formal-campaign/engine/profiles/vue2/project/package.json",
        "client-packs/frontend-72-route-equivalence-v2/formal-campaign/artifacts/engine/profiles/vue2/project/package.json",
        "verification-packs/frontend-72-route-formal-equivalence-v1/formal-campaign/engine/profiles/vue2/project/package.json",
        "verification-packs/frontend-72-route-formal-equivalence-v2/formal-campaign/artifacts/engine/profiles/vue2/project/package.json",
    }
)
EOL_PACKAGES = {"vue", "vue-template-compiler", "vue-server-renderer"}
SCHEMA_VERSION = "2.0"
ALERT_KEY_FIELDS = frozenset(
    {
        "alert_number",
        "ecosystem",
        "package",
        "manifest_path",
        "dependency_scope",
        "relationship",
        "ghsa_id",
        "severity",
        "vulnerable_version_range",
        "first_patched_version",
    }
)


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()


def alert_snapshot_digest(alerts: Sequence[Mapping[str, Any]]) -> str:
    return alert_key_snapshot_digest([alert_key(alert) for alert in alerts])


def alert_key_snapshot_digest(keys: Sequence[Mapping[str, Any]]) -> str:
    normalized: list[dict[str, Any]] = []
    seen: set[int] = set()
    for key in keys:
        if set(key) != ALERT_KEY_FIELDS:
            raise ValueError("Dependabot source alert snapshot shape is not exact")
        number = int(key["alert_number"])
        if number <= 0 or number in seen:
            raise ValueError("Dependabot source alert snapshot identity is invalid")
        seen.add(number)
        normalized.append(dict(key))
    return digest(sorted(normalized, key=lambda item: int(item["alert_number"])))


def alert_key(alert: Mapping[str, Any]) -> dict[str, Any]:
    dependency = alert.get("dependency") or {}
    package = dependency.get("package") or {}
    advisory = alert.get("security_advisory") or {}
    vulnerability = alert.get("security_vulnerability") or {}
    patched = vulnerability.get("first_patched_version") or {}
    return {
        "alert_number": int(alert["number"]),
        "ecosystem": str(package.get("ecosystem", "")),
        "package": str(package.get("name", "")),
        "manifest_path": str(dependency.get("manifest_path", "")),
        "dependency_scope": str(dependency.get("scope", "")),
        "relationship": str(dependency.get("relationship", "")),
        "ghsa_id": str(advisory.get("ghsa_id", "")),
        "severity": str(advisory.get("severity", "")),
        "vulnerable_version_range": str(
            vulnerability.get("vulnerable_version_range", "")
        ),
        "first_patched_version": str(patched.get("identifier", "")),
    }


def classify(alert: Mapping[str, Any]) -> str | None:
    key = alert_key(alert)
    manifest_path = key["manifest_path"]
    if (
        key["ecosystem"] == "npm"
        and key["package"] in EOL_PACKAGES
        and key["manifest_path"] in VUE2_COMPATIBILITY_MANIFESTS
    ):
        return "eol_compatibility"
    if manifest_path.startswith(IMMUTABLE_SOURCE_PREFIXES):
        return "immutable_source"
    if (
        manifest_path.startswith(IMMUTABLE_CERTIFICATION_PREFIXES)
        or (
            manifest_path.startswith("routes/")
            and "/certification/formal-artifacts/" in manifest_path
        )
    ):
        return "immutable_certification_artifact"
    # Retain compatibility with older, already-issued exception registries.
    # New exceptions use the narrower rules above whenever possible.
    if manifest_path.startswith(IMMUTABLE_PREFIXES):
        return "immutable_evidence"
    return None


def file_identity(repo_root: Path, manifest_path: str) -> dict[str, Any]:
    candidate = (repo_root / manifest_path).resolve()
    root = repo_root.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ValueError("Dependabot manifest escapes the repository root") from error
    if not candidate.is_file():
        raise ValueError(f"Dependabot manifest is unavailable: {manifest_path}")
    raw = candidate.read_bytes()
    return {
        "path": manifest_path,
        "sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def build_registry(
    repo: str,
    alerts: Sequence[Mapping[str, Any]],
    *,
    now: datetime | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    root = (repo_root or Path.cwd()).resolve()
    expires = (
        (current + timedelta(days=90))
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    snapshot_digest = alert_snapshot_digest(alerts)
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
            if classification != "eol_compatibility"
            else [
                "vue2-route-isolated-from-new-production-routes",
                "runtime-templates-are-static-and-not-attacker-controlled",
                "migration-to-vue3-is-required-before-support-expansion",
                "revalidate-on-every-release-and-before-expiry",
            ]
        )
        justification = (
            "vulnerable_code_not_in_execute_path"
            if classification == "eol_compatibility"
            else "component_not_present_in_runtime"
        )
        exceptions.append(
            {
                **alert_key(alert),
                "classification": classification,
                "vex_status": "not_affected",
                "vex_justification": justification,
                "decision": "dismiss_tolerable_risk",
                "status": "ACTIVE",
                "reason": "The manifest is retained as immutable evidence, source material, or an isolated EOL compatibility fixture. It is not an installable production dependency and is not declared fixed.",
                "manifest": file_identity(root, alert_key(alert)["manifest_path"]),
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
    repo_root: Path | None = None,
    source_alert_keys: Sequence[Mapping[str, Any]] | None = None,
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
    expected_snapshot = (
        alert_key_snapshot_digest(source_alert_keys)
        if source_alert_keys is not None
        else alert_snapshot_digest(alerts)
    )
    if registry["source_alert_snapshot_digest"] != expected_snapshot:
        raise ValueError(
            "Dependabot exception registry is bound to a different alert snapshot"
        )
    exceptions = registry["exceptions"]
    if not isinstance(exceptions, list):
        raise TypeError("Dependabot exceptions must be a list")
    seen: set[int] = set()
    current = now or datetime.now(timezone.utc)
    root = (repo_root or Path.cwd()).resolve()
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
                "dependency_scope",
                "relationship",
                "ghsa_id",
                "severity",
                "vulnerable_version_range",
                "first_patched_version",
            )
        ):
            raise ValueError("Dependabot exception alert binding changed")
        if (
            exception.get("classification") != classify(alert)
            or exception.get("vex_status") != "not_affected"
            or exception.get("vex_justification")
            not in {
                "component_not_present_in_runtime",
                "vulnerable_code_not_in_execute_path",
            }
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
        expected_manifest = file_identity(root, alert_key(alert)["manifest_path"])
        if exception.get("manifest") != expected_manifest:
            raise ValueError("Dependabot exception manifest identity changed")
        expiry = _parse_time(exception.get("expires_at"))
        if expiry <= current or expiry > current + timedelta(days=180):
            raise ValueError(
                "Dependabot exception expiry is outside the allowed window"
            )


def build_vex_record(
    registry: Mapping[str, Any], *, applied: bool = False, dismissed_count: int = 0
) -> dict[str, Any]:
    records = []
    for exception in registry["exceptions"]:
        records.append(
            {
                "id": (
                    f"dependabot-{exception['alert_number']}-"
                    f"{exception['ghsa_id'].lower()}"
                ),
                "vulnerabilityId": exception["ghsa_id"],
                "alertNumber": exception["alert_number"],
                "component": {
                    "ecosystem": exception["ecosystem"],
                    "name": exception["package"],
                    "manifestPath": exception["manifest_path"],
                    "dependencyScope": exception["dependency_scope"],
                    "relationship": exception["relationship"],
                },
                "analysis": {
                    "state": "NOT_AFFECTED",
                    "justification": exception["vex_justification"],
                    "detail": exception["reason"],
                },
                "evidence": {"manifest": exception["manifest"]},
                "controls": exception["controls"],
                "expiresAt": exception["expires_at"],
            }
        )
    return {
        "schemaVersion": 1,
        "id": "elmos-platform-supply-chain-vex-record",
        "batch": 40,
        "version": "0.2.0",
        "owner": "elmos-security-owner",
        "status": "review",
        "evidenceRefs": ["b40-dependabot-vex"],
        "records": records,
        "metadata": {
            "repository": registry["repository"],
            "generatedAt": registry["generated_at"],
            "sourceAlertSnapshotDigest": registry["source_alert_snapshot_digest"],
            "exceptionCount": len(records),
            "fixedClaims": [],
            "evidenceStatus": "LOCAL_EXECUTED_SELF_ATTESTED",
            "githubDisposition": "DISMISSED" if applied else "PREPARED",
            "dismissedCount": len(records) if applied else 0,
            "independentVerification": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        },
        "packKey": "elmos-platform-supply-chain",
    }


def build_provenance_record(
    registry: Mapping[str, Any],
    registry_path: Path,
    *,
    external_operation_executed: bool = False,
) -> dict[str, Any]:
    script_path = Path(__file__).resolve()
    return {
        "schemaVersion": 1,
        "id": "batch40-dependabot-vex-provenance",
        "batch": 40,
        "packKey": "elmos-platform-supply-chain",
        "evidenceId": "b40-dependabot-vex",
        "status": "LOCAL_EXECUTED_SELF_ATTESTED",
        "owner": "elmos-security-owner",
        "source": {
            "repository": registry["repository"],
            "generatedAt": registry["generated_at"],
            "alertSnapshotDigest": registry["source_alert_snapshot_digest"],
            "registry": {
                "path": str(registry_path),
                "sha256": "sha256:"
                + hashlib.sha256(registry_path.read_bytes()).hexdigest(),
                "bytes": registry_path.stat().st_size,
            },
        },
        "analyzer": {
            "path": "scripts/dependabot_governance.py",
            "sha256": "sha256:" + hashlib.sha256(script_path.read_bytes()).hexdigest(),
        },
        "externalOperationExecuted": external_operation_executed,
        "independentVerification": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
    }


def _fetch_alert_inventory(repo: str, *, state: str | None = None) -> list[dict[str, Any]]:
    query = f"repos/{repo}/dependabot/alerts?per_page=100"
    if state is not None:
        query += f"&state={state}"
    result = subprocess.run(
        [
            "gh",
            "api",
            "--paginate",
            "--slurp",
            "-H",
            "Accept: application/vnd.github+json",
            query,
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=120,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"GitHub Dependabot inventory failed: {detail}")
    value = json.loads(result.stdout)
    if not isinstance(value, list) or not all(isinstance(page, list) for page in value):
        raise TypeError("GitHub Dependabot paginated response is not a list of pages")
    alerts = [dict(item) for page in value for item in page if isinstance(item, Mapping)]
    numbers = [int(item["number"]) for item in alerts]
    if len(numbers) != len(set(numbers)):
        raise ValueError("GitHub Dependabot inventory contains duplicate alert numbers")
    return alerts


def fetch_open_alerts(repo: str) -> list[dict[str, Any]]:
    return _fetch_alert_inventory(repo, state="open")


def fetch_all_alerts(repo: str) -> list[dict[str, Any]]:
    return _fetch_alert_inventory(repo)


def dismissal_comment(exception: Mapping[str, Any]) -> str:
    comment = (
        "VEX not_affected; not fixed; "
        + str(exception["classification"])
        + "; manifest "
        + str(exception["manifest"]["sha256"])
        + "; expires "
        + str(exception["expires_at"])
        + "; evidence b40-dependabot-vex"
    )
    if len(comment) > 280:
        raise ValueError("Dependabot dismissal comment exceeds GitHub's limit")
    return comment


def reconcile_dismissed_exception(
    exception: dict[str, Any], alert: Mapping[str, Any]
) -> bool:
    if alert.get("state") != "dismissed":
        raise ValueError(
            f"Dependabot alert {exception['alert_number']} has an unexpected closed state"
        )
    if alert.get("dismissed_reason") != "tolerable_risk":
        raise ValueError(
            f"Dependabot alert {exception['alert_number']} has an unexpected dismissal reason"
        )
    expected_prefix = (
        "VEX not_affected; not fixed; "
        + str(exception["classification"])
        + "; manifest "
        + str(exception["manifest"]["sha256"])
        + "; expires "
    )
    expected_suffix = "; evidence b40-dependabot-vex"
    comment = alert.get("dismissed_comment")
    if (
        not isinstance(comment, str)
        or not comment.startswith(expected_prefix)
        or not comment.endswith(expected_suffix)
    ):
        raise ValueError(
            f"Dependabot alert {exception['alert_number']} dismissal evidence is invalid"
        )
    expiry = comment[len(expected_prefix) : -len(expected_suffix)]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", expiry):
        raise ValueError(
            f"Dependabot alert {exception['alert_number']} dismissal expiry is invalid"
        )
    _parse_time(expiry)
    changed = exception.get("expires_at") != expiry
    exception["expires_at"] = expiry
    return changed


def reconcile_dismissed_exceptions(
    registry: Mapping[str, Any], alerts: Sequence[Mapping[str, Any]]
) -> int:
    by_number = {int(alert["number"]): alert for alert in alerts}
    changed = 0
    for raw_exception in registry["exceptions"]:
        exception = raw_exception
        number = int(exception["alert_number"])
        alert = by_number[number]
        if alert.get("state") == "open":
            continue
        if reconcile_dismissed_exception(exception, alert):
            changed += 1
    return changed


def dismiss_eligible(
    repo: str,
    registry: Mapping[str, Any],
    alerts: Sequence[Mapping[str, Any]],
    *,
    repo_root: Path | None = None,
    source_alert_keys: Sequence[Mapping[str, Any]] | None = None,
) -> int:
    validate_registry(
        registry,
        alerts,
        repo_root=repo_root,
        source_alert_keys=source_alert_keys,
    )
    by_number = {int(alert["number"]): alert for alert in alerts}
    count = 0
    for exception in registry["exceptions"]:
        number = int(exception["alert_number"])
        if by_number[number].get("state") != "open":
            reconcile_dismissed_exception(exception, by_number[number])
            continue
        comment = dismissal_comment(exception)
        result = subprocess.run(
            [
                "gh",
                "api",
                "--method",
                "PATCH",
                "-H",
                "Accept: application/vnd.github+json",
                f"repos/{repo}/dependabot/alerts/{number}",
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
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"Dependabot alert dismissal failed for alert {number}: {detail}"
            )
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
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--vex-record", type=Path)
    parser.add_argument("--provenance", type=Path)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="dismiss only registry-listed eligible alerts",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="replace the registry with the current open-alert inventory before applying",
    )
    args = parser.parse_args()
    snapshot_path = Path(args.snapshot)
    registry_path = Path(args.registry)
    source_alert_keys: list[dict[str, Any]] | None = None
    if not args.refresh and registry_path.exists():
        if not snapshot_path.is_file():
            raise ValueError("Dependabot source alert snapshot is unavailable")
        stored_snapshot = json.loads(snapshot_path.read_bytes())
        if not isinstance(stored_snapshot, list) or not all(
            isinstance(item, Mapping) for item in stored_snapshot
        ):
            raise ValueError("Dependabot source alert snapshot is invalid")
        source_alert_keys = [dict(item) for item in stored_snapshot]
    open_alerts = fetch_open_alerts(args.repo)
    if args.refresh:
        alerts = open_alerts
        registry = build_registry(args.repo, alerts, repo_root=args.repo_root)
        validate_registry(registry, alerts, repo_root=args.repo_root)
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.write_text(
            json.dumps(registry, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    elif registry_path.exists():
        registry = json.loads(registry_path.read_bytes())
        registered_numbers = {
            int(exception["alert_number"]) for exception in registry.get("exceptions", [])
        }
        unexpected_open = sorted(
            int(alert["number"])
            for alert in open_alerts
            if int(alert["number"]) not in registered_numbers
        )
        if unexpected_open:
            raise ValueError(
                "Dependabot registry does not cover open alerts: "
                + ", ".join(str(number) for number in unexpected_open)
            )
        all_alerts = {int(alert["number"]): alert for alert in fetch_all_alerts(args.repo)}
        missing_registered = sorted(registered_numbers - set(all_alerts))
        if missing_registered:
            raise ValueError(
                "Dependabot registry alerts are unavailable: "
                + ", ".join(str(number) for number in missing_registered)
            )
        alerts = [all_alerts[number] for number in sorted(registered_numbers)]
    else:
        alerts = open_alerts
        registry = build_registry(args.repo, alerts, repo_root=args.repo_root)
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.write_text(
            json.dumps(registry, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    validate_registry(
        registry,
        alerts,
        repo_root=args.repo_root,
        source_alert_keys=source_alert_keys,
    )
    eligible = len(registry["exceptions"])
    print(
        json.dumps(
            {
                "open_alerts": len(open_alerts),
                "registered_alerts": len(alerts),
                "eligible_residual_risk": eligible,
                "apply": args.apply,
            },
            sort_keys=True,
        )
    )
    dismissed_count = 0
    reconciled_count = 0
    if args.apply:
        reconciled_count = reconcile_dismissed_exceptions(registry, alerts)
        validate_registry(
            registry,
            alerts,
            repo_root=args.repo_root,
            source_alert_keys=source_alert_keys,
        )
        dismissed_count = dismiss_eligible(
            args.repo,
            registry,
            alerts,
            repo_root=args.repo_root,
            source_alert_keys=source_alert_keys,
        )
        print(
            json.dumps(
                {
                    "dismissed": dismissed_count,
                    "reconciled_dismissed_evidence": reconciled_count,
                },
                sort_keys=True,
            )
        )
        registry_path.write_text(
            json.dumps(registry, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    if args.vex_record is not None:
        args.vex_record.parent.mkdir(parents=True, exist_ok=True)
        args.vex_record.write_text(
            json.dumps(
                build_vex_record(
                    registry,
                    applied=args.apply,
                    dismissed_count=dismissed_count,
                ),
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
    if args.provenance is not None:
        args.provenance.parent.mkdir(parents=True, exist_ok=True)
        args.provenance.write_text(
            json.dumps(
                build_provenance_record(
                    registry,
                    registry_path,
                    external_operation_executed=args.apply,
                ),
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_bytes(canonical([alert_key(alert) for alert in open_alerts]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
