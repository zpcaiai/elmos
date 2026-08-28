#!/usr/bin/env python3
"""Independent, read-only verifier for the local production-runtime report."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


EXPECTED_PACKAGE_SHA256 = "7685f34453d896747c177b9299c01f1a101c94a1ea4808ae6dc92fec51203c37"
REQUIRED_EXTERNAL_KEYS = {
    "provider_runtime",
    "target_cluster_load",
    "chaos",
    "worker_process_kill",
    "redis_loss",
    "backup_pitr",
    "independent_verification",
    "production_deployment",
    "production_certification",
}
REQUIRED_LOCAL_SCENARIOS = {
    "ProviderRuntime",
    "TargetClusterLoadSubstitute",
    "ChaosMatrix",
    "WorkerCrashCheckpointResume",
    "RedisLoss",
    "PITRRestore",
}


class VerificationError(ValueError):
    pass


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def verify(report_path: Path) -> dict[str, object]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise VerificationError("report must be an object")
    if report.get("schema_version") != 1:
        raise VerificationError("unsupported report schema")
    if report.get("source_archive_sha256") != EXPECTED_PACKAGE_SHA256:
        raise VerificationError("report is not bound to the pinned source archive")
    if report.get("package_execution") is not False:
        raise VerificationError("report must prove that package executables were not run")
    if report.get("production_certification") != "NOT_CERTIFIED":
        raise VerificationError("local report cannot certify production")

    external = report.get("external_evidence")
    if not isinstance(external, dict) or set(external) != REQUIRED_EXTERNAL_KEYS:
        raise VerificationError("external evidence keys are incomplete or broadened")
    if any(value != "NOT_RUN" and key != "production_certification" for key, value in external.items()):
        raise VerificationError("unexecuted external evidence must remain NOT_RUN")
    if external["production_certification"] != "NOT_CERTIFIED":
        raise VerificationError("production certification boundary changed")

    local = report.get("local_scenarios")
    if not isinstance(local, dict) or set(local) != REQUIRED_LOCAL_SCENARIOS:
        raise VerificationError("local scenario inventory is incomplete or changed")
    for scenario, value in local.items():
        if not isinstance(value, dict) or value.get("status") not in {"LOCAL_HARNESS_PASS", "PARTIAL_LOCAL"}:
            raise VerificationError(f"local scenario is not explicitly qualified: {scenario}")
        if not value.get("test_run_id") or not value.get("test"):
            raise VerificationError(f"local scenario lacks execution binding: {scenario}")

    artifacts = report.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise VerificationError("report has no evidence artifacts")
    for item in artifacts:
        if not isinstance(item, dict) or not item.get("path") or not item.get("sha256"):
            raise VerificationError("evidence artifact binding is incomplete")
        artifact_path = (report_path.parent / item["path"]).resolve()
        if not artifact_path.is_file() or digest(artifact_path) != item["sha256"]:
            raise VerificationError(f"evidence artifact digest mismatch: {item.get('path')}")

    return {
        "status": "LOCAL_INDEPENDENT_VERIFIER_PASS",
        "verified_report": str(report_path),
        "verified_source_archive_sha256": EXPECTED_PACKAGE_SHA256,
        "production_certification": "NOT_CERTIFIED",
        "external_evidence": "NOT_RUN",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = verify(args.report)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"production-runtime local evidence verification: FAIL: {exc}", file=sys.stderr)
        return 1
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
