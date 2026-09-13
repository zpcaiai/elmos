#!/usr/bin/env python3
"""Fail-closed release-candidate and evidence-governance gate.

The gate produces candidate-bound engineering evidence. A passing result never
means external execution, independent verification, or production certification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PRIVATE_PATH = re.compile(
    r"(?:^|/)(?:[^/]*\.private\.pem|[^/]*-private\.pem|certifier-private\.pem|[^/]*\.(?:p12|pfx|jks|keystore))$",
    re.IGNORECASE,
)
PRIVATE_PEM = re.compile(
    rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----[\r\n]+"
    rb"(?:[A-Za-z0-9+/=]{16,}[\r\n]+){2,}"
)
DECISION_KEYS = {"decision", "verdict", "overall_verdict", "certification", "certification_decision", "gate_decision"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def git(*arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=ROOT, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def tracked_paths() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
    )
    return [item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def decisive_certified_values(payload: Any, prefix: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            current = f"{prefix}.{key}"
            if key.lower() in DECISION_KEYS and isinstance(value, str):
                upper = value.strip().upper()
                if upper == "CERTIFIED" or upper.startswith("CERTIFIED_") or upper.startswith("CERTIFIED "):
                    findings.append(f"{current}={value}")
            findings.extend(decisive_certified_values(value, current))
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            findings.extend(decisive_certified_values(value, f"{prefix}[{index}]"))
    return findings


def check_private_keys(paths: list[str]) -> tuple[bool, list[str]]:
    findings = [path for path in paths if PRIVATE_PATH.search(path)]
    content_candidates = [
        path for path in paths if Path(path).suffix.lower() in {".pem", ".key"}
    ]
    for relative in content_candidates:
        path = ROOT / relative
        if relative in findings or not path.is_file():
            continue
        try:
            if path.stat().st_size <= 2 * 1024 * 1024:
                data = path.read_bytes()
                if PRIVATE_PEM.search(data):
                    findings.append(relative)
        except OSError:
            findings.append(f"{relative}:UNREADABLE")
    return not findings, sorted(set(findings))


def check_revocation() -> tuple[bool, list[str]]:
    errors: list[str] = []
    ledger_path = ROOT / "certification/revoked-keys.json"
    if not ledger_path.is_file():
        return False, ["certification/revoked-keys.json is missing"]
    ledger = read_json(ledger_path)
    if ledger.get("incident_id") != "ELMOS-CERT-KEY-2026-09-13-01":
        errors.append("revocation incident id mismatch")
    if ledger.get("status") != "REVOKED" or ledger.get("certification_status") != "NOT_CERTIFIED":
        errors.append("revocation ledger is not fail-closed")
    if ledger.get("tracked_private_key_count") != 183:
        errors.append("revocation ledger must account for exactly 183 tracked private keys")

    for relative in (
        "certification/trust-store.json",
        "certification/batch1-37-trust-store.json",
        "certification/batch38-45-trust-store.json",
        "certification/mature-product-trust-store.json",
    ):
        payload = read_json(ROOT / relative)
        anchors = payload.get("authorities") or payload.get("trustedCertifiers") or payload.get("keys") or []
        ethan = [
            anchor for anchor in anchors
            if (anchor.get("signer_id") or anchor.get("keyId")) == "ethan-independent-certifier"
        ]
        if not ethan or any(anchor.get("revoked") is not True for anchor in ethan):
            errors.append(f"{relative} does not mark the Ethan trust anchor revoked")

    package_stores = sorted(ROOT.glob(
        "framework-packs/*/certification/campaign-runs/actor-ethan-certified/trust/trust-store.json"
    ))
    if len(package_stores) != 13:
        errors.append(f"expected 13 framework campaign trust stores, found {len(package_stores)}")
    for path in package_stores:
        payload = read_json(path)
        keys = payload.get("keys", [])
        if len(keys) != 14 or any(key.get("revoked") is not True for key in keys):
            errors.append(f"{path.relative_to(ROOT)} does not revoke all 14 campaign role keys")
        if "ELMOS-CERT-KEY-2026-09-13-01" not in payload.get("revoked_record_ids", []):
            errors.append(f"{path.relative_to(ROOT)} is not linked to the revocation incident")
    return not errors, errors


def check_untrusted_reports() -> tuple[bool, list[str]]:
    ledger = read_json(ROOT / "release-control/untrusted-certification-reports.json")
    errors: list[str] = []
    for relative in ledger.get("reports", []):
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"{relative}:missing")
            continue
        payload = read_json(path)
        findings = decisive_certified_values(payload)
        if findings:
            errors.extend(f"{relative}:{finding}" for finding in findings)
        root_values = [payload.get(key) for key in DECISION_KEYS if isinstance(payload, dict)]
        if "NOT_CERTIFIED" not in root_values:
            errors.append(f"{relative}:root decision is not NOT_CERTIFIED")
    return not errors, errors


def make_cyclonedx(inventory: dict[str, Any], candidate_sha: str) -> dict[str, Any]:
    components = []
    for component in inventory.get("components", []):
        entry: dict[str, Any] = {
            "type": "library",
            "name": component["name"],
            "properties": [
                {"name": "elmos:ecosystem", "value": component["ecosystem"]},
                {"name": "elmos:versionResolution", "value": component["versionResolution"]},
            ],
        }
        if component.get("group"):
            entry["group"] = component["group"]
        if component.get("version"):
            entry["version"] = component["version"]
        if component.get("purl") and component.get("version"):
            entry["purl"] = component["purl"]
        components.append(entry)
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, 'https://github.com/zpcaiai/elmos/commit/' + candidate_sha)}",
        "version": 1,
        "metadata": {
            "timestamp": inventory.get("finishedAt", utc_now()),
            "component": {"type": "application", "name": "elmos", "version": candidate_sha},
            "properties": [
                {"name": "elmos:evidenceClass", "value": "LOCAL_EXECUTED_SELF_ATTESTED"},
                {"name": "elmos:claim", "value": "PARTIAL_LOCAL_INVENTORY_ONLY"},
                {"name": "elmos:vulnerabilityScan", "value": "NOT_RUN"},
            ],
        },
        "components": components,
    }


def run(candidate_sha: str, output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    checks: list[dict[str, Any]] = []

    def record(name: str, passed: bool, details: Any = None) -> None:
        checks.append({"name": name, "status": "PASS" if passed else "FAIL", "details": details or []})

    head = git("rev-parse", "HEAD")
    tree = git("rev-parse", "HEAD^{tree}")
    record("exact-candidate-sha", bool(re.fullmatch(r"[0-9a-f]{40}", candidate_sha)) and candidate_sha == head,
           {"requested": candidate_sha, "head": head})
    dirty = git("status", "--porcelain", "--untracked-files=no")
    record("clean-tracked-worktree", not dirty, dirty.splitlines())

    paths = tracked_paths()
    private_ok, private_findings = check_private_keys(paths)
    record("no-tracked-private-keys", private_ok, private_findings)
    revoked_ok, revoked_errors = check_revocation()
    record("revocation-ledger-and-trust-stores", revoked_ok, revoked_errors)
    reports_ok, report_errors = check_untrusted_reports()
    record("untrusted-certified-reports-downgraded", reports_ok, report_errors)

    failures = read_json(ROOT / "release-control/ci-failures-2026-09-13.json")
    record("eleven-ci-failures-inventory", len(failures.get("failures", [])) == 11,
           {"count": len(failures.get("failures", [])), "source_run": failures.get("source_run", {})})
    catalog = read_json(ROOT / "release-control/evidence-catalog.json")
    missing_roots = [
        entry["path"] for entry in catalog.get("roots", [])
        if entry.get("committed", True)
        and not any(path == entry["path"] or path.startswith(entry["path"] + "/") for path in paths)
    ]
    record("evidence-roots", not missing_roots, missing_roots)

    inventory_path = output_dir / "dependency-inventory.json"
    inventory_run = subprocess.run(
        [sys.executable, str(ROOT / "scripts/batch40_dependency_inventory.py"), "--repo", str(ROOT), "--output", str(inventory_path)],
        cwd=ROOT, capture_output=True, text=True,
    )
    record("dependency-inventory", inventory_run.returncode == 0,
           {"returncode": inventory_run.returncode, "stderr": inventory_run.stderr.strip()})
    if inventory_path.is_file():
        inventory = read_json(inventory_path)
        sbom_path = output_dir / "sbom.cdx.json"
        write_json(sbom_path, make_cyclonedx(inventory, candidate_sha))
        record("cyclonedx-sbom", True, {
            "path": str(sbom_path.relative_to(ROOT)),
            "claim": "PARTIAL_LOCAL_INVENTORY_ONLY",
            "vulnerability_scan": "NOT_RUN",
        })
    else:
        sbom_path = output_dir / "sbom.cdx.json"
        record("cyclonedx-sbom", False, ["dependency inventory was not produced"])

    passed = all(check["status"] == "PASS" for check in checks)
    artifact_hashes = {}
    for path in (inventory_path, sbom_path):
        if path.is_file():
            artifact_hashes[path.name] = sha256_file(path)
    candidate = {
        "schema_version": 1,
        "candidate_sha": candidate_sha,
        "resolved_head_sha": head,
        "tree_sha": tree,
        "generated_at": utc_now(),
        "gate_status": "PASSED_LOCAL_GOVERNANCE" if passed else "BLOCKED",
        "release_decision": "NOT_CERTIFIED",
        "external_execution": "NOT_RUN",
        "independent_verification": "NOT_RUN",
        "artifact_hashes": artifact_hashes,
        "checks": checks,
    }
    write_json(output_dir / "candidate-manifest.json", candidate)
    write_json(output_dir / "gate-result.json", {
        "status": candidate["gate_status"],
        "release_decision": "NOT_CERTIFIED",
        "candidate_sha": candidate_sha,
        "failed_checks": [check["name"] for check in checks if check["status"] != "PASS"],
    })
    print(json.dumps(candidate, indent=2, ensure_ascii=False))
    return 0 if passed else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".release-control-artifacts")
    arguments = parser.parse_args()
    output = arguments.output_dir if arguments.output_dir.is_absolute() else ROOT / arguments.output_dir
    try:
        return run(arguments.candidate_sha, output)
    except Exception as exc:  # fail closed while preserving an uploadable result
        output.mkdir(parents=True, exist_ok=True)
        write_json(output / "gate-result.json", {
            "status": "BLOCKED",
            "release_decision": "NOT_CERTIFIED",
            "candidate_sha": arguments.candidate_sha,
            "error": f"{type(exc).__name__}: {exc}",
        })
        print(f"release-control gate blocked: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
