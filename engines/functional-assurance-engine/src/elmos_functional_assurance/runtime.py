"""Runtime Execution Services and Context Loaders."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .domain import FunctionalAssuranceContext
from .kernel import FunctionalAssuranceKernel


class FunctionalAssuranceRuntime:
    """Runtime service wrapper for functional assurance execution."""

    def __init__(self, kernel: FunctionalAssuranceKernel | None = None) -> None:
        self.kernel = kernel or FunctionalAssuranceKernel()

    def execute(self, skill_name: str, payload_json: Mapping[str, Any], context_dict: Mapping[str, Any]) -> dict[str, Any]:
        context = FunctionalAssuranceContext(
            tenant_id=str(context_dict["tenant_id"]),
            project_id=str(context_dict["project_id"]),
            execution_epoch=str(context_dict.get("execution_epoch", "EPOCH_01")),
            fencing_token=int(context_dict.get("fencing_token", 1)),
            candidate_digest=str(context_dict["candidate_digest"]),
            base_evidence_receipt=str(context_dict.get("base_evidence_receipt", "EVIDENCE_BASE_RECEIPT_OK")),
            authority_digest=str(context_dict.get("authority_digest", "AUTH_DIGEST_DEF")),
        )
        return self.kernel.dispatch(skill_name, payload_json, context)
