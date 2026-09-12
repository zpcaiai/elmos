#!/usr/bin/env python3
"""Conservative Live Workbench external-evidence gate.

This repository-owned gate never executes source-package code and never turns
local test results into deployment or certification evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

ARCHIVE_SHA256 = "c7619ce2955b083e39660a159166b6c9b498855203a55b5b8dd3b2cc68d84cfe"
REQUIRED = {
    "ui-e2e", "dap-python", "dap-javascript", "dap-jvm", "dap-dotnet", "real-600s",
    "expiry-enforcement", "cleanup", "sandbox-isolation", "tenant-security", "recovery-fencing",
    "evidence-accuracy", "learning-privacy", "failure-transparency", "conversion-mapping",
    "admission-quota", "trace-correlation", "accessibility",
}
DIGEST = re.compile(r"^[a-f0-9]{64}$")
IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{2,199}$")


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def current_revision(root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def validate(bundle_path: Path, root: Path) -> list[str]:
    errors: list[str] = []
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"EVIDENCE_BUNDLE_INVALID:{type(error).__name__}"]
    if bundle.get("schema_version") != "lw-production-evidence.v1":
        errors.append("SCHEMA_VERSION_INVALID")
    if bundle.get("source_archive_sha256") != ARCHIVE_SHA256:
        errors.append("SOURCE_ARCHIVE_BINDING_INVALID")
    revision = bundle.get("implementation_revision")
    if not isinstance(revision, str) or not re.fullmatch(r"[a-f0-9]{40,64}", revision):
        errors.append("IMPLEMENTATION_REVISION_INVALID")
    elif revision != current_revision(root):
        errors.append("IMPLEMENTATION_REVISION_NOT_CURRENT_HEAD")
    environment = bundle.get("environment")
    if not isinstance(environment, dict):
        errors.append("ENVIRONMENT_BINDING_REQUIRED")
    else:
        deployment_url = environment.get("deployment_url")
        parsed = urlparse(deployment_url) if isinstance(deployment_url, str) else None
        if not parsed or parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            errors.append("HTTPS_DEPLOYMENT_BINDING_REQUIRED")
        for field in ("provider_id", "region", "environment_digest", "deployed_artifact_digest"):
            value = environment.get(field)
            if field.endswith("digest"):
                if not isinstance(value, str) or not DIGEST.fullmatch(value): errors.append(f"{field.upper()}_INVALID")
            elif not isinstance(value, str) or not IDENTITY.fullmatch(value): errors.append(f"{field.upper()}_INVALID")

    cases = bundle.get("cases")
    if not isinstance(cases, list):
        return errors + ["CASES_REQUIRED"]
    ids = [case.get("id") for case in cases if isinstance(case, dict)]
    if len(ids) != len(set(ids)) or set(ids) != REQUIRED:
        errors.append("EXACT_18_CASE_INVENTORY_REQUIRED")
    evidence_root = bundle_path.parent.resolve()
    for case in cases:
        if not isinstance(case, dict) or case.get("id") not in REQUIRED:
            continue
        case_id = case["id"]
        if case.get("status") != "PASSED": errors.append(f"{case_id}:STATUS_NOT_PASSED")
        executor, verifier = case.get("executor"), case.get("independent_verifier")
        if not isinstance(executor, str) or not IDENTITY.fullmatch(executor): errors.append(f"{case_id}:EXECUTOR_INVALID")
        if not isinstance(verifier, str) or not IDENTITY.fullmatch(verifier) or verifier == executor:
            errors.append(f"{case_id}:INDEPENDENT_VERIFIER_REQUIRED")
        if not isinstance(case.get("authorization_ref"), str) or not case["authorization_ref"].strip():
            errors.append(f"{case_id}:AUTHORIZATION_REQUIRED")
        evidence = case.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"{case_id}:RAW_EVIDENCE_REQUIRED")
            continue
        for index, item in enumerate(evidence):
            if not isinstance(item, dict):
                errors.append(f"{case_id}:EVIDENCE_{index}_INVALID"); continue
            relative, expected = item.get("path"), item.get("sha256")
            if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
                errors.append(f"{case_id}:EVIDENCE_{index}_PATH_INVALID"); continue
            resolved = (evidence_root / relative).resolve()
            if evidence_root not in resolved.parents or not resolved.is_file():
                errors.append(f"{case_id}:EVIDENCE_{index}_MISSING"); continue
            if not isinstance(expected, str) or not DIGEST.fullmatch(expected) or sha256(resolved) != expected:
                errors.append(f"{case_id}:EVIDENCE_{index}_DIGEST_MISMATCH")
    approval = bundle.get("independent_approval")
    if not isinstance(approval, dict) or not all(isinstance(approval.get(key), str) and approval[key].strip()
                                                 for key in ("request_digest", "signer", "signature_ref")):
        errors.append("INDEPENDENT_SIGNED_APPROVAL_REQUIRED")
    elif not DIGEST.fullmatch(approval["request_digest"]):
        errors.append("APPROVAL_REQUEST_DIGEST_INVALID")
    if bundle.get("self_certified") is not False:
        errors.append("SELF_CERTIFICATION_FORBIDDEN")
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=Path("docs/live-workbench/production-evidence.json"))
    parser.add_argument("--expect-blocked", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    evidence = args.evidence if args.evidence.is_absolute() else root / args.evidence
    errors = validate(evidence, root)
    decision = "BLOCKED" if errors else "READY_FOR_EXTERNAL_CERTIFICATION"
    print(json.dumps({
        "schema_version": "lw-production-gate.v1", "decision": decision,
        "certified": False, "deployment_qualified": not errors,
        "errors": errors,
        "limitations": ["This gate cannot self-certify E5; an authorized independent certification authority is still required."],
    }, indent=2, sort_keys=True))
    if args.expect_blocked:
        return 0 if errors else 1
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
