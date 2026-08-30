"""Truthful implementation/evidence inventory for all external PI Harness gates."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

GAPS: dict[str, dict[str, Any]] = {
    "P0-G01": {
        "name": "postgresql",
        "module": "elmos_pi_harness.postgres",
        "symbols": ["PostgresStore", "PostgresMigrator"],
    },
    "P0-G02": {
        "name": "temporal",
        "module": "elmos_pi_harness.temporal",
        "symbols": [
            "TemporalGateway",
            "run_worker",
            "run_task_worker",
            "replay_histories",
        ],
        "additional_module": "elmos_pi_harness.temporal_activities",
        "additional_symbols": ["TemporalTaskActivity", "build_temporal_activities"],
    },
    "P0-G03": {
        "name": "cloud_provider",
        "module": "elmos_pi_harness.provider",
        "symbols": ["ProviderControlPlane", "AWSCloudFormationAdapter"],
        "additional_module": "elmos_pi_harness.immutable_evidence",
        "additional_symbols": [
            "S3ImmutableEvidenceArchive",
            "S3ImmutableEvidenceConfig",
        ],
    },
    "P0-G04": {
        "name": "idp_mtls",
        "module": "elmos_pi_harness.identity",
        "symbols": ["OIDCAuthenticator", "MTLSAuthenticator", "bind_oidc_and_mtls"],
    },
    "P0-G05": {
        "name": "independent_verifier",
        "module": "elmos_pi_harness.independent_verifier",
        "symbols": ["VerifierTrustStore", "VerificationReceiptRegistry"],
        "additional_module": "elmos_pi_harness.external_gates",
        "additional_symbols": ["ExternalGateLedger", "QualificationTrustStore"],
    },
    "P0-G06": {
        "name": "disaster_recovery",
        "module": "elmos_pi_harness.disaster_recovery",
        "symbols": ["DisasterRecoveryOrchestrator", "PostgresLogicalBackupAdapter"],
    },
    "P1-G07": {
        "name": "customer_acceptance",
        "module": "elmos_pi_harness.acceptance",
        "symbols": ["AcceptanceRunner", "accept_customer_signoff"],
    },
    "P0-G08": {
        "name": "production_deployment",
        "module": "elmos_pi_harness.deployment",
        "symbols": ["DeploymentController", "validate_production_configuration"],
    },
}


def implementation_inventory(
    ledger_root: str | Path | None = None,
    *,
    trust_store: Any | None = None,
) -> dict[str, Any]:
    ledger_status: dict[str, Any] | None = None
    ledger_rows: dict[str, dict[str, Any]] = {}
    if ledger_root is not None:
        from .external_gates import ExternalGateLedger

        ledger_status = ExternalGateLedger(ledger_root).status(trust_store=trust_store)
        ledger_rows = {item["gap_id"]: item for item in ledger_status["gaps"]}
    rows: list[dict[str, Any]] = []
    for gap_id, definition in GAPS.items():
        missing_symbols: list[str] = []
        try:
            module = importlib.import_module(definition["module"])
            missing_symbols = [
                name for name in definition["symbols"] if not hasattr(module, name)
            ]
            if definition.get("additional_module"):
                additional = importlib.import_module(definition["additional_module"])
                missing_symbols.extend(
                    name
                    for name in definition["additional_symbols"]
                    if not hasattr(additional, name)
                )
        except Exception as exc:  # noqa: BLE001 - inventory must report every module-load failure
            missing_symbols = [f"module_load:{type(exc).__name__}"]
        external = ledger_rows.get(gap_id, {})
        rows.append(
            {
                "gap_id": gap_id,
                "name": definition["name"],
                "implementation_status": "CODE_COMPLETE"
                if not missing_symbols
                else "INCOMPLETE",
                "missing_symbols": missing_symbols,
                "external_evidence": external.get("external_evidence", "NOT_RUN"),
                "evidence_digest": external.get("evidence_digest"),
                "execution_digest": external.get("execution_digest"),
                "target": external.get("target"),
                "independent_verifier": external.get("independent_verifier"),
                "limitations": external.get("limitations", []),
            }
        )
    code_complete = all(
        item["implementation_status"] == "CODE_COMPLETE" for item in rows
    )
    result = {
        "implementation_status": "CODE_COMPLETE" if code_complete else "INCOMPLETE",
        "external_evidence": ledger_status["external_evidence"]
        if ledger_status
        else "NOT_RUN",
        "certification": "NOT_CERTIFIED",
        "certified": False,
        "gaps": rows,
        "limitations": [
            "real external execution and independent evidence remain required"
        ],
    }
    if ledger_status is not None:
        result.update(
            release_digest=ledger_status["release_digest"],
            ledger_head_digest=ledger_status["ledger_head_digest"],
            ledger_event_count=ledger_status["event_count"],
            ledger_object_count=ledger_status["object_count"],
            ledger_orphan_object_count=ledger_status["orphan_object_count"],
            receipt_revalidation=ledger_status["receipt_revalidation"],
            qualification_decision=ledger_status["qualification_decision"],
            blockers=ledger_status["blockers"],
        )
    return result
