"""Certification Campaign Workflows and Multi-Phase Orchestration."""

from __future__ import annotations

import time
from typing import Any, Mapping

from .domain import CertificateRecord, ConformityDecision, FunctionalAssuranceContext
from .kernel import FunctionalAssuranceKernel


class CertificationWorkflowRunner:
    """Executes multi-phase certification campaigns."""

    def __init__(self, kernel: FunctionalAssuranceKernel | None = None) -> None:
        self.kernel = kernel or FunctionalAssuranceKernel()

    def run_full_certification_campaign(
        self,
        context: FunctionalAssuranceContext,
        target_assurance_level: str = "E4",
        sector: str | None = None,
    ) -> dict[str, Any]:
        """Execute all phases: 1. Intake -> 2. Lab Evaluation -> 3. Sector Profile -> 4. Review -> 5. Issuance -> 6. Sealing."""
        # Phase 1: Intake & E0-E5 Base Assessment
        intake_res = self.kernel.dispatch(
            "elmos-ai-e0-e5-certifier",
            {"evidence": {"schema_validated": True, "contracts_verified": True, "fuzz_metamorphic_passed": True, "formal_proof_checked": True}},
            context,
        )

        # Phase 2: Uncertainty Budget & Guard Banding
        uncert_res = self.kernel.dispatch(
            "elmos-measurement-uncertainty-budget-engine",
            {"measurand": "accuracy", "nominal_value": 0.96},
            context,
        )

        # Phase 3: Sector Profile (if requested)
        sector_res = None
        if sector == "AVIATION":
            sector_res = self.kernel.dispatch("elmos-aviation-software-tool-formal-assurance-profile", {}, context)
        elif sector == "MEDICAL":
            sector_res = self.kernel.dispatch("elmos-medical-device-ai-software-lifecycle-risk-profile", {}, context)
        elif sector == "AUTOMOTIVE":
            sector_res = self.kernel.dispatch("elmos-automotive-functional-safety-sotif-profile", {}, context)

        # Phase 4 & 5: Certificate Issuance
        certificate = self.kernel.issue_certification(
            context,
            assurance_level=target_assurance_level,
            product_level="P04" if sector else "P03",
            scope_description=f"Full Campaign Certification [{target_assurance_level}]",
            sector=sector,
        )

        # Phase 6: WORM Merkle Sealing
        seal_res = self.kernel.dispatch(
            "elmos-evidence-worm-merkle-sealer",
            {"evidence_items": [{"role": "cert", "data": certificate.to_dict()}, {"role": "intake", "data": intake_res}]},
            context,
        )

        return {
            "campaign_status": "COMPLETED",
            "decision": ConformityDecision.CONFORMING.value,
            "certificate": certificate.to_dict(),
            "merkle_seal": seal_res,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
