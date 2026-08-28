"""Service Orchestration Layer for Certification Operations."""

from __future__ import annotations

import json
from typing import Any, Mapping

from .domain import FunctionalAssuranceContext
from .kernel import FunctionalAssuranceKernel
from .workflows import CertificationWorkflowRunner


class FunctionalAssuranceService:
    """High-level service interface for certification requests."""

    def __init__(self) -> None:
        self.kernel = FunctionalAssuranceKernel()
        self.runner = CertificationWorkflowRunner(self.kernel)

    def run_certification(self, request_payload: Mapping[str, Any]) -> dict[str, Any]:
        context = FunctionalAssuranceContext(
            tenant_id=str(request_payload["tenant_id"]),
            project_id=str(request_payload["project_id"]),
            execution_epoch=str(request_payload.get("execution_epoch", "EPOCH_DEFAULT")),
            fencing_token=int(request_payload.get("fencing_token", 1)),
            candidate_digest=str(request_payload["candidate_digest"]),
            base_evidence_receipt=str(request_payload.get("base_evidence_receipt", "EVIDENCE_BASE_RECEIPT_OK")),
            authority_digest=str(request_payload.get("authority_digest", "AUTH_DIGEST_DEFAULT")),
        )
        return self.runner.run_full_certification_campaign(
            context=context,
            target_assurance_level=str(request_payload.get("target_assurance_level", "E4")),
            sector=request_payload.get("sector"),
        )
