"""Truthful implementation/evidence inventory for all external PI Harness gates."""

from __future__ import annotations

import importlib
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


def implementation_inventory() -> dict[str, Any]:
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
        rows.append(
            {
                "gap_id": gap_id,
                "name": definition["name"],
                "implementation_status": "CODE_COMPLETE"
                if not missing_symbols
                else "INCOMPLETE",
                "missing_symbols": missing_symbols,
                "external_evidence": "NOT_RUN",
                "evidence_digest": None,
                "independent_verifier": None,
            }
        )
    code_complete = all(
        item["implementation_status"] == "CODE_COMPLETE" for item in rows
    )
    return {
        "implementation_status": "CODE_COMPLETE" if code_complete else "INCOMPLETE",
        "external_evidence": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
        "certified": False,
        "gaps": rows,
        "limitations": [
            "real external execution and independent evidence remain required"
        ],
    }
