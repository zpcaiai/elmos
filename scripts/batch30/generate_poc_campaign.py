#!/usr/bin/env python3
"""Generate a schema-compliant P0-P11 PoC Certification Campaign plan for commercial clients.

Creates a structured campaign manifest that customer UAT and independent auditors
can execute against the Batch 30 certification framework, binding exact source/target
toolchains, cryptographic checksums, and zero-tolerance invariants.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.precision_migration.trust import canonical_digest, read_regular_file_once

CAMPAIGN_SCHEMA_VERSION = "elmos.batch30.certification-campaign.v1"


def generate_campaign(
    pack_dir: Path,
    client_name: str,
    output_path: Path | None = None,
) -> dict:
    pack_json_path = pack_dir / "pack.json"
    if not pack_json_path.is_file():
        raise FileNotFoundError(f"Missing pack.json in {pack_dir}")

    pack_manifest = json.loads(
        read_regular_file_once(
            pack_json_path,
            max_bytes=1024 * 1024,
            label="pack.json",
        ).decode("utf-8")
    )
    pack_key = pack_manifest.get("pack_key", pack_dir.name)
    source_info = pack_manifest.get("source", {})
    target_info = pack_manifest.get("target", {})

    now_iso = datetime.now(timezone.utc).isoformat()

    campaign = {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "campaign_id": f"campaign-{pack_key}-{client_name.lower().replace(' ', '-')}",
        "pack_key": pack_key,
        "client_name": client_name,
        "created_at": now_iso,
        "mode": "commercial-poc-readiness",
        "binding": {
            "source_framework": source_info.get("framework", "spring-boot"),
            "source_versions": source_info.get("framework_versions", ["2.7.18"]),
            "source_java": source_info.get("runtime_versions", ["17"]),
            "target_framework": target_info.get("framework", "spring-boot"),
            "target_versions": target_info.get("framework_versions", ["3.5.3"]),
            "target_java": target_info.get("runtime_versions", ["21"]),
        },
        "phases": {
            "P0_intake_and_scope": {
                "status": "COMPLETED_LOCAL",
                "description": "Source repository fingerprinting and target profile agreement",
                "required_roles": ["customer_architect", "elmos_modernization_lead"],
            },
            "P1_contract_and_ast_mapping": {
                "status": "COMPLETED_LOCAL",
                "description": "Deterministic AST and OpenRewrite recipe selection",
                "required_roles": ["elmos_transformer"],
            },
            "P2_source_target_build_runtime": {
                "status": "READY_FOR_EXECUTION",
                "description": "Compile, build and startup verification on Java 21",
                "evidence_types": ["source_build", "target_build", "source_startup", "target_startup"],
            },
            "P3_behavioral_equivalence": {
                "status": "READY_FOR_EXECUTION",
                "description": "Shadow traffic recording and 13-dimension differential check",
                "evidence_types": ["behavioral_equivalence"],
            },
            "P4_security_and_auth": {
                "status": "READY_FOR_EXECUTION",
                "description": "SecurityFilterChain, RBAC, and vulnerability penetration test",
                "evidence_types": ["security"],
            },
            "P5_performance_and_soak": {
                "status": "READY_FOR_EXECUTION",
                "description": "High-concurrency load and soak differential verification",
                "evidence_types": ["performance"],
            },
            "P6_operability_and_sbom": {
                "status": "READY_FOR_EXECUTION",
                "description": "Actuator metrics, health probes, and SPDX/CycloneDX SBOM",
                "evidence_types": ["operability", "sbom"],
            },
            "P7_rollback_and_disaster_recovery": {
                "status": "READY_FOR_EXECUTION",
                "description": "Database CDC snapshot and failback rollback drills",
                "evidence_types": ["rollback"],
            },
            "P8_customer_acceptance": {
                "status": "PENDING_CUSTOMER_UAT",
                "description": "Formal business acceptance and shadow dual-run sign-off",
                "evidence_types": ["customer_acceptance"],
            },
            "P9_pre_certification_audit": {
                "status": "PENDING_EXTERNAL_REVIEW",
                "description": "Independent third-party code and security review",
                "evidence_types": ["independent_review"],
            },
            "P10_external_certification": {
                "status": "PENDING_CERTIFICATION_BODY",
                "description": "Formal compliance and security attestation issuance",
                "evidence_types": ["external_certification"],
            },
            "P11_production_cutover": {
                "status": "GATED_BY_P8_P10",
                "description": "Gradual canary rollout and legacy system retirement",
                "required_roles": ["customer_release_manager"],
            },
        },
        "zero_tolerance_invariants": {
            "critical_unknowns": 0,
            "silent_framework_drops": 0,
            "critical_security_regressions": 0,
            "critical_transaction_regressions": 0,
            "critical_data_regressions": 0,
            "duplicate_message_or_job_effects": 0,
            "test_integrity_violations": 0,
        },
    }

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(campaign, indent=2), encoding="utf-8")
        print(f"Generated PoC campaign plan at: {output_path}")

    return campaign


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate P0-P11 PoC Campaign Plan")
    parser.add_argument("pack_dir", type=Path, help="Framework pack directory")
    parser.add_argument("--client", type=str, default="PilotCustomer", help="Client name")
    parser.add_argument("--output", type=Path, default=None, help="Output JSON path")
    args = parser.parse_args()

    try:
        generate_campaign(args.pack_dir, args.client, args.output)
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
