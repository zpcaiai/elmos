#!/usr/bin/env python3
"""Structural validation for a Batch 46 runnable-smoke pack.

Checks shape, provenance and internal consistency. It does not decide
certification — `run_smoke_gate.py` does that, and only from a real executed
run.

    python3 scripts/batch46/validate_smoke_pack.py <project-root>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from smoke_common import (
    DATA_SOURCES,
    DEFAULT_FREE_QUOTA_SECONDS,
    RUNNER_ENTRIES,
    read_json,
    smoke_dir,
)

REQUIRED_FILES = (
    "pack.json",
    "profile.json",
    "minimal-data-requirements.json",
    "seed-manifest.json",
    "assertions.json",
    "runner-manifest.json",
    "tools/run_smoke.py",
    "tools/smoke_lease.py",
    "tools/smoke_common.py",
)
REQUIRED_ASSERTIONS = ("process-started", "http-readiness", "graceful-shutdown", "lease-teardown")


def validate(root: Path) -> list[str]:
    root = Path(root).resolve()
    smoke = smoke_dir(root)
    failures: list[str] = []

    for name in REQUIRED_FILES:
        if not (smoke / name).is_file():
            failures.append(f"missing smoke/{name}")
    if failures:
        return failures

    if not (root / "run-smoke.sh").is_file():
        failures.append("missing run-smoke.sh at the project root")
    if not (root / "Makefile.smoke").is_file():
        failures.append("missing Makefile.smoke at the project root")

    pack = read_json(smoke / "pack.json")
    profile = read_json(smoke / "profile.json")
    requirements = read_json(smoke / "minimal-data-requirements.json")
    seed_manifest = read_json(smoke / "seed-manifest.json")
    assertions = read_json(smoke / "assertions.json")
    runner = read_json(smoke / "runner-manifest.json")

    if pack.get("digests", {}).get("profile") != profile.get("profile_digest"):
        failures.append("pack.json profile digest does not match smoke/profile.json")
    if pack.get("digests", {}).get("requirements") != requirements.get("requirements_digest"):
        failures.append("pack.json requirements digest does not match minimal-data-requirements.json")
    if requirements.get("profile_digest") != profile.get("profile_digest"):
        failures.append("minimal-data-requirements.json was derived from a different profile revision")
    if runner.get("profile_digest") != profile.get("profile_digest"):
        failures.append("runner-manifest.json was emitted from a different profile revision")

    if seed_manifest.get("production_data_used") is not False:
        failures.append("seed-manifest.json must record production_data_used=false")
    if seed_manifest.get("classification") != "ephemeral-disposable":
        failures.append("seed data must be classified ephemeral-disposable")
    for entry in seed_manifest.get("provenance", []):
        source = entry.get("data_source")
        if source not in DATA_SOURCES:
            failures.append(f"unknown seed data source '{source}'")
        if source == "desensitized-sample" and not entry.get("authorization"):
            failures.append("desensitized-sample provenance requires an authorization reference")
        if source == "desensitized-sample" and entry.get("scan_findings") and not entry.get("accepted_with_findings"):
            failures.append("desensitized-sample has unresolved sensitive-value findings")
    for artifact in seed_manifest.get("artifacts", []):
        path = root / artifact["path"]
        if not path.is_file():
            failures.append(f"seed artifact declared but missing on disk: {artifact['path']}")

    declared = {check["id"] for check in assertions.get("checks", [])}
    for required in REQUIRED_ASSERTIONS:
        if required not in declared:
            failures.append(f"assertions.json is missing the mandatory check '{required}'")

    entries = runner.get("entries", {})
    for name in RUNNER_ENTRIES:
        entry = entries.get(name)
        if not entry:
            failures.append(f"runner-manifest.json does not describe the '{name}' entry")
            continue
        if entry.get("status") not in ("available", "unavailable"):
            failures.append(f"entry '{name}' has an invalid status '{entry.get('status')}'")
        if entry.get("status") == "unavailable" and not entry.get("reason"):
            failures.append(f"entry '{name}' is unavailable without a stated reason")
    if not any(e.get("status") == "available" for e in entries.values()):
        failures.append("no runnable entry is available; the project cannot be smoke tested as configured")

    lease = runner.get("lease_policy", {})
    if lease.get("free_quota_seconds") != DEFAULT_FREE_QUOTA_SECONDS:
        failures.append(f"lease free quota must be {DEFAULT_FREE_QUOTA_SECONDS}s")
    if lease.get("auto_renew") is not False:
        failures.append("lease auto_renew must be false")
    if lease.get("extend_policy") != "explicit-only":
        failures.append("lease extend policy must be explicit-only")

    zero_dep = entries.get("zero-dep", {})
    if zero_dep.get("status") == "available" and zero_dep.get("substitutes") and not zero_dep.get("semantic_warning"):
        failures.append("an available zero-dep entry using engine substitutes must carry its semantic warning")

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a Batch 46 smoke pack")
    parser.add_argument("project_root")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    failures = validate(Path(args.project_root))
    if args.json:
        print(json.dumps({"valid": not failures, "failures": failures}, indent=2, ensure_ascii=False))
    elif failures:
        print("smoke pack validation FAILED:")
        for failure in failures:
            print(f"  - {failure}")
    else:
        print("smoke pack validation passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
