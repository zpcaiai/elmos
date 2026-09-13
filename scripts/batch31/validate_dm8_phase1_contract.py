#!/usr/bin/env python3
"""Validate the fail-closed PostgreSQL 17.5 -> DM8 8.1.3.140 Phase-1 contract.

This validator checks repository-owned structure and exact pins. It never
executes a database and never produces a certification decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = "1.3.0"
PACK_KEY = "postgresql-to-dm8"
SURFACES = {
    "ddl",
    "dml",
    "typeBoundary",
    "constraints",
    "indexes",
    "sequences",
    "routines",
    "triggers",
    "privileges",
    "rowLevelSecurity",
}
FAILURES = {
    "processTermination",
    "networkInterruption",
    "duplicateEvent",
    "outOfOrderEvent",
    "diskPressure",
    "cdcRestart",
    "cutoverFailure",
    "rollback",
}
GATE_IDS = {f"DM8-P1-{index:02d}" for index in range(1, 9)}
REQUIRED_FILES = {
    "source-snapshots/ddl/postgresql-schema.sql",
    "target-profile/ddl/dm8-schema.sql",
    "target-profile/ddl/dm8-security.sql",
    "target-profile/config/dm8-rls-bootstrap.sql",
    "corpus/development/dm8-phase1-cases.json",
    "migration/backfill/plan.json",
    "migration/cdc/plan.json",
    "migration/reconciliation/plan.json",
    "migration/failure-injection/plan.json",
    "migration/cutover/plan.json",
    "migration/performance/plan.json",
    "certification/dm8-phase1-acceptance-profile.json",
}


def _load(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{path}: {exc}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{path}: root must be an object")
        return {}
    return value


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _require_equal(
    errors: list[str], label: str, actual: object, expected: object
) -> None:
    if actual != expected:
        errors.append(f"{label}: expected {expected!r}, got {actual!r}")


def validate(pack: Path, repo_root: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    blockers: list[str] = []
    for relative in sorted(REQUIRED_FILES):
        if not (pack / relative).is_file():
            errors.append(f"missing Phase-1 artifact: {relative}")

    manifest = _load(pack / "pack.json", errors)
    target = _load(pack / "target-profile/profile.json", errors)
    acceptance = _load(
        pack / "certification/dm8-phase1-acceptance-profile.json", errors
    )
    certification = _load(pack / "certification/certification.json", errors)
    evidence = _load(pack / "certification/evidence.json", errors)
    fingerprint = _load(pack / "source-fingerprint/manifest.json", errors)
    ir = _load(pack / "canonical-ir/model.json", errors)
    cases = _load(pack / "corpus/development/dm8-phase1-cases.json", errors)
    cdc = _load(pack / "migration/cdc/plan.json", errors)
    reconciliation = _load(pack / "migration/reconciliation/plan.json", errors)
    failures = _load(pack / "migration/failure-injection/plan.json", errors)
    cutover = _load(pack / "migration/cutover/plan.json", errors)
    performance = _load(pack / "migration/performance/plan.json", errors)

    _require_equal(errors, "pack key", manifest.get("pack_key"), PACK_KEY)
    source = manifest.get("source", {})
    manifest_target = manifest.get("target", {})
    exact_source = {
        "engine": "postgresql",
        "versions": ["17.5"],
        "edition": "community",
        "driver_versions": ["psql:17.5"],
        "charset": "UTF8",
        "collation": "C",
        "timezone": "UTC",
    }
    exact_target = {
        "engine": "dm8",
        "versions": ["8.1.3.140"],
        "edition": "enterprise",
        "driver_versions": ["dm-jdbc:8.1.3.140"],
        "charset": "UTF-8",
        "collation": "BINARY",
        "timezone": "Asia/Shanghai",
    }
    for field, expected in exact_source.items():
        _require_equal(errors, f"source.{field}", source.get(field), expected)
    for field, expected in exact_target.items():
        _require_equal(errors, f"target.{field}", manifest_target.get(field), expected)
        _require_equal(errors, f"target profile.{field}", target.get(field), expected)
    _require_equal(errors, "target patch", target.get("patch_version"), "8.1.3.140")
    providers = target.get("providers", {})
    _require_equal(
        errors,
        "target topology",
        providers.get("deployment_topology"),
        "single-instance-non-mpp",
    )
    _require_equal(
        errors,
        "target compatibility mode",
        providers.get("compatibility_mode"),
        "oracle-compatible-explicit",
    )
    rls = providers.get("rls", {})
    _require_equal(errors, "DM8 ENABLE_RLS", rls.get("enable_rls"), 1)
    _require_equal(
        errors,
        "DM8 RLS initialization",
        rls.get("initialization"),
        "SP_INIT_RLS_SYS(1)",
    )
    _require_equal(errors, "DM8 RLS MPP support", rls.get("mpp_supported"), False)

    for schema_name in (
        "chinadb-production-qualification-result.schema.json",
        "chinadb-production-qualification-requirements.schema.json",
        "chinadb-vendor-execution-request.schema.json",
    ):
        schema = _load(repo_root / "schemas/batch31" / schema_name, errors)
        schema_text = json.dumps(schema, sort_keys=True)
        if PROTOCOL_VERSION not in schema_text:
            errors.append(f"{schema_name}: does not bind protocol {PROTOCOL_VERSION}")

    _require_equal(
        errors,
        "acceptance protocol",
        acceptance.get("protocolVersion"),
        PROTOCOL_VERSION,
    )
    _require_equal(
        errors,
        "certification authority",
        acceptance.get("certificationAuthority"),
        "BATCH31_GATE_ONLY",
    )
    gates = acceptance.get("gates", [])
    gate_ids = {gate.get("id") for gate in gates if isinstance(gate, dict)}
    _require_equal(errors, "Phase-1 gate ids", gate_ids, GATE_IDS)
    if any(gate.get("status") in {"PASSED", "CERTIFIED"} for gate in gates):
        errors.append("acceptance profile must not claim unexecuted gates passed")

    case_surfaces = cases.get("surfaces", {})
    _require_equal(errors, "database surfaces", set(case_surfaces), SURFACES)
    for name, case in case_surfaces.items():
        if not case.get("positive") or not case.get("negative"):
            errors.append(f"surface {name} requires positive and negative cases")

    _require_equal(
        errors,
        "failure scenario ids",
        {item.get("id") for item in failures.get("scenarios", [])},
        FAILURES,
    )
    failure_acceptance = failures.get("acceptance", {})
    _require_equal(
        errors,
        "target-window write loss",
        failure_acceptance.get("targetWindowWriteLossCount"),
        0,
    )
    _require_equal(
        errors,
        "CDC missing events",
        cdc.get("acceptance", {}).get("missingEventCount"),
        0,
    )
    _require_equal(
        errors,
        "CDC duplicate effects",
        cdc.get("acceptance", {}).get("duplicateEffectCount"),
        0,
    )
    target_ledger = cdc.get("targetTransactionLedger", {})
    _require_equal(
        errors,
        "CDC target transaction ledger",
        target_ledger.get("table"),
        "elmos_cdc_event_ledger",
    )
    _require_equal(
        errors,
        "CDC ledger atomicity",
        target_ledger.get("atomicWithTargetMutation"),
        True,
    )
    reconciliation_acceptance = reconciliation.get("acceptance", {})
    for field in (
        "tableDifferenceCount",
        "missingPrimaryKeyCount",
        "duplicatePrimaryKeyCount",
        "rowDifferenceCount",
        "fieldMismatchCount",
        "p0DifferenceCount",
    ):
        _require_equal(
            errors, f"reconciliation {field}", reconciliation_acceptance.get(field), 0
        )
    _require_equal(
        errors,
        "money precision exact",
        reconciliation_acceptance.get("moneyPrecisionExact"),
        True,
    )
    _require_equal(
        errors,
        "money scale exact",
        reconciliation_acceptance.get("moneyScaleExact"),
        True,
    )
    _require_equal(
        errors,
        "cutover write-loss gate",
        cutover.get("acceptance", {}).get("targetWindowWriteLossCount"),
        0,
    )

    sampling = performance.get("sampling", {})
    thresholds = performance.get("thresholds", {})
    runner = performance.get("runner", {})
    _require_equal(
        errors, "performance warmups", sampling.get("warmupCountPerQuery"), 5
    )
    _require_equal(
        errors, "performance samples", sampling.get("sampleCountPerQueryPerEngine"), 40
    )
    _require_equal(
        errors,
        "source p95 threshold",
        thresholds.get("sourceP95MillisecondsMaximum"),
        75.0,
    )
    _require_equal(
        errors,
        "target p95 threshold",
        thresholds.get("targetP95MillisecondsMaximum"),
        75.0,
    )
    _require_equal(errors, "runner class", runner.get("class"), "DEDICATED")
    _require_equal(errors, "runner exclusive", runner.get("exclusive"), True)
    _require_equal(
        errors, "runner attestation required", runner.get("attestationRequired"), True
    )

    source_schema = pack / "source-snapshots/ddl/postgresql-schema.sql"
    if source_schema.is_file():
        digest = _sha256(source_schema)
        _require_equal(
            errors,
            "source fingerprint digest",
            fingerprint.get("snapshot_digest"),
            digest,
        )
        _require_equal(
            errors,
            "canonical IR source digest",
            ir.get("source_snapshot_digest"),
            digest,
        )
    target_schema = pack / "target-profile/ddl/dm8-schema.sql"
    if (
        target_schema.is_file()
        and "elmos_cdc_event_ledger" not in target_schema.read_text()
    ):
        errors.append("target schema is missing the atomic CDC event ledger")

    if manifest.get("status") == "certified":
        errors.append("pack cannot be certified without external Phase-1 evidence")
    _require_equal(
        errors,
        "production certification",
        certification.get("production_certification"),
        "NOT_CERTIFIED",
    )
    _require_equal(
        errors,
        "acceptance production certification",
        acceptance.get("productionCertification"),
        "NOT_CERTIFIED",
    )
    if evidence.get("evidence_status", {}).get("independent_verification") != "NOT_RUN":
        errors.append("independent verification must remain NOT_RUN without receipt")

    external_pins = acceptance.get("externalPins", {})
    pin_fields = (
        "sourceRuntimeArtifactDigest",
        "sourceDriverArtifactDigest",
        "targetRuntimeArtifactDigest",
        "targetDriverArtifactDigest",
        "targetLicenseRef",
        "targetLicenseDigest",
        "sourceEnvironmentId",
        "targetEnvironmentId",
        "runnerAttestationDigest",
        "independentVerifierEngagementRef",
    )
    for field in pin_fields:
        if not external_pins.get(field):
            blockers.append(f"externalPins.{field}")
    if external_pins.get("targetLicenseVerified") != "VERIFIED":
        blockers.append("externalPins.targetLicenseVerified")
    if performance.get("status") != "PASSED_EXTERNAL":
        blockers.append("migration/performance/plan.json:status")
    if any(gate.get("status") != "PASSED_EXTERNAL" for gate in gates):
        blockers.append("certification/dm8-phase1-acceptance-profile.json:gates")

    return sorted(set(errors)), sorted(set(blockers))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    parser.add_argument("--pack-dir", type=Path)
    parser.add_argument("--require-external-ready", action="store_true")
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    pack = (
        args.pack_dir.resolve()
        if args.pack_dir
        else repo_root / "database-packs" / PACK_KEY
    )
    errors, blockers = validate(pack, repo_root)
    if errors:
        print("\n".join(f"ERROR: {error}" for error in errors), file=sys.stderr)
        return 1
    print(f"OK: DM8 Phase-1 repository contract is structurally complete: {pack}")
    if blockers:
        print("EXTERNAL_BLOCKERS:")
        print("\n".join(f"- {blocker}" for blocker in blockers))
        print("CERTIFICATION: NOT_CERTIFIED")
        if args.require_external_ready:
            return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
