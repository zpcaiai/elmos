#!/usr/bin/env python3
"""Batch 35 entry point for the exact frontend interaction v2 campaign."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import runpy
import sys
from pathlib import Path
from typing import Any

PACK_KEY = "frontend-72-route-formal-equivalence-v2"
CAMPAIGN_RELATIVE = "formal-campaign/frontend-formal-route-campaign-v2.json"
PROVENANCE_RELATIVE = "formal-campaign/oracle/provenance-graph.json"
EXTERNAL_NOT_RUN = {
    "provided": False,
    "status": "NOT_RUN",
    "intake_artifact_id": None,
    "trust_store_artifact_id": None,
    "trust_root_id": None,
    "trust_root_fingerprint": None,
    "trust_store_authorization_status": "NOT_RUN",
    "replay_verifier_fingerprint": None,
    "artifact_ids": [],
    "scope_digest": None,
    "authorization_status": "NOT_RUN",
    "signature_status": "NOT_RUN",
    "replay_status": "NOT_RUN",
    "independent_status": "NOT_RUN",
    "holdout_status": "NOT_RUN",
    "representative_status": "NOT_RUN",
    "customer_status": "NOT_RUN",
    "organization_ids": [],
}


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def fail(result: dict[str, Any], message: str) -> None:
    result.setdefault("errors", []).append(message)
    result.update(
        {
            "status": "invalid",
            "structural_status": "FAILED",
            "model_formal_ready": False,
            "formal_ready": False,
            "browser_ready": False,
            "native_ready": False,
            "runtime_ready": False,
            "independent_ready": False,
            "certification_ready": False,
        }
    )


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def expected_oracle_registry(external_status: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "pack_key": PACK_KEY,
        "oracles": [
            {
                "oracle_id": "oracle.canonical-model-v2",
                "type": "formal-spec",
                "owner": "frontend-formal-verification-team",
                "scope": ["claim.behavior"],
                "independence": "dependent",
                "trust_level": "supporting",
                "version": "2.0.0",
                "status": "PASSED",
                "evidence_refs": [CAMPAIGN_RELATIVE, PROVENANCE_RELATIVE],
            },
            {
                "oracle_id": "oracle.bounded-z3-v2",
                "type": "solver",
                "owner": "frontend-formal-verification-team",
                "scope": ["claim.behavior"],
                "independence": "dependent",
                "trust_level": "supporting",
                "version": "4.16.0",
                "status": "PASSED",
                "evidence_refs": [CAMPAIGN_RELATIVE],
            },
            {
                "oracle_id": "oracle.external-runtime-v2",
                "type": "reference-implementation",
                "owner": "external-independent-verifier",
                "scope": ["claim.behavior"],
                "independence": "independent",
                "trust_level": "strong",
                "version": "2.0.0",
                "status": external_status,
                "evidence_refs": (
                    [CAMPAIGN_RELATIVE, PROVENANCE_RELATIVE]
                    if external_status == "PASSED"
                    else []
                ),
            },
        ],
        "precedence_rules": [
            {
                "claim_type": "behavior",
                "ordered_oracles": [
                    "oracle.external-runtime-v2",
                    "oracle.canonical-model-v2",
                    "oracle.bounded-z3-v2",
                ],
            }
        ],
        "conflicts": [],
        "approvals": [],
    }


def expected_assurance_case(campaign: dict[str, Any]) -> dict[str, Any]:
    external_passed = campaign.get("external_evidence", {}).get("status") == "PASSED"
    external_limitation = (
        "Scoped independent runtime, holdout, representative and customer "
        "evidence passed the external trust protocol; unconditional proof, "
        "complete browser/native production coverage and certification remain open."
        if external_passed
        else "Independent runtime, holdout, representative and customer evidence is NOT_RUN."
    )
    external_risk = (
        {
            "risk_id": "frontend-v2-production-certification-incomplete",
            "description": (
                "Scoped external qualification does not establish unconditional "
                "proof, complete browser/native production coverage or certification."
            ),
            "severity": "critical",
            "mitigation": (
                "Close unconditional formal, required runtime, operational and "
                "certification gates."
            ),
            "owner": "frontend-formal-verification-team",
            "status": "open",
        }
        if external_passed
        else {
            "risk_id": "frontend-v2-external-evidence-not-run",
            "description": "External runtime and customer qualification is absent.",
            "severity": "critical",
            "mitigation": "Run the externally trusted intake and replay protocol.",
            "owner": "frontend-formal-verification-team",
            "status": "open",
        }
    )
    return {
        "schema_version": 1,
        "case_key": f"{PACK_KEY}-assurance-v1",
        "version": 1,
        "owner": "frontend-formal-verification-team",
        "top_claim": (
            "The exact bounded frontend interaction scope has local model "
            "evidence; production correctness remains unsupported."
        ),
        "claims": [
            {
                "claim_id": "claim.behavior",
                "statement": "Critical migrated behavior remains correct.",
                "status": "unsupported",
                "evidence_refs": [CAMPAIGN_RELATIVE],
                "assumptions": list(campaign.get("assumptions", [])),
                "limitations": [external_limitation],
            }
        ],
        "evidence": [],
        "residual_risks": [external_risk],
        "monitoring_obligations": [],
        "approvals": [],
    }


def validate_frontend_governance_v2(
    pack: Path, manifest: dict[str, Any], result: dict[str, Any]
) -> None:
    try:
        registry_path = pack / "oracle-registry.json"
        assurance_path = pack / "assurance/assurance-case.json"
        registry = load(registry_path)
        assurance = load(assurance_path)
        campaign = load(pack / CAMPAIGN_RELATIVE)
        if campaign.get("external_evidence") != EXTERNAL_NOT_RUN:
            raise ValueError(
                "V2_EXTERNAL_POSITIVE_PROTOCOL_NOT_IMPLEMENTED"
            )
        governance = manifest.get("frontend_governance_v2")
        external_status = campaign.get("external_evidence", {}).get(
            "status", "NOT_RUN"
        )
        if governance != {
            "oracle_registry_sha256": sha256_file(registry_path),
            "assurance_case_sha256": sha256_file(assurance_path),
            "status": "PASSED" if external_status == "PASSED" else "NOT_RUN",
        }:
            raise ValueError("governance digest/status binding drift")
        if registry != expected_oracle_registry(str(external_status)):
            raise ValueError("oracle registry exact closure drift")
        if assurance != expected_assurance_case(campaign):
            raise ValueError("assurance case exact fail-closed closure drift")
        if not (pack / PROVENANCE_RELATIVE).is_file():
            raise ValueError("oracle provenance evidence is missing")
    except Exception as exc:
        fail(result, f"Batch 35 frontend v2 governance invalid: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pack_dir")
    parser.add_argument("--campaign")
    parser.add_argument("--no-replay-execute", action="store_true")
    parser.add_argument("--external-trust-root", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    here = Path(__file__).resolve()
    repo_root = here.parents[2]
    batch32_dir = here.parents[1] / "batch32"
    sys.path.insert(0, str(batch32_dir))
    namespace = runpy.run_path(
        str(batch32_dir / "validate_frontend_formal_route_campaign_v2.py"),
        run_name="elmos_batch35_frontend_formal_validator_v2",
    )
    validate_campaign = namespace.get("validate_campaign")
    if not callable(validate_campaign):
        result: dict[str, Any] = {}
        fail(result, "Batch 32 frontend v2 validator is unavailable")
    else:
        result = validate_campaign(
            Path(args.pack_dir),
            campaign_relative=args.campaign,
            schema_path=repo_root
            / "schemas/batch32/frontend-formal-route-campaign-v2.schema.json",
            route_schema_path=repo_root
            / "schemas/batch32/frontend-formal-route-evidence-v2.schema.json",
            execute_replay=not args.no_replay_execute,
            external_trust_root_path=(
                args.external_trust_root
                if args.external_trust_root is not None
                else Path(os.environ["ELMOS_FRONTEND_EXTERNAL_TRUST_ROOT"])
                if os.environ.get("ELMOS_FRONTEND_EXTERNAL_TRUST_ROOT")
                else None
            ),
        )
        result["batch35_frontend_profile"] = PACK_KEY
        try:
            manifest = load(Path(args.pack_dir) / "pack.json")
            if manifest.get("pack_key") != PACK_KEY:
                fail(result, "Batch 35 frontend v2 campaign pack_key must be exact")
            else:
                validate_frontend_governance_v2(
                    Path(args.pack_dir), manifest, result
                )
        except Exception as exc:
            fail(result, f"cannot load Batch 35 v2 pack manifest: {exc}")
    if args.json:
        print(json.dumps(result, sort_keys=True))
    elif result.get("status") == "valid":
        print(
            "OK: Batch 35 frontend v2 formal campaign "
            f"model_formal_ready={str(result.get('model_formal_ready')).lower()} "
            f"certification_ready={str(result.get('certification_ready')).lower()}"
        )
    else:
        print(
            "\n".join("ERROR: " + item for item in result.get("errors", [])),
            file=sys.stderr,
        )
    return 0 if result.get("status") == "valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
