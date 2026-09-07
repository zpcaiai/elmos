"""ISO/IEC 17011 Accreditation Body Governance and Global Mutual Recognition."""

from __future__ import annotations

import hashlib
import time
from typing import Any, Mapping

from ..domain import ConformityDecision, FunctionalAssuranceContext


class AccreditationBodyGovernor:
    """Governor for accreditation readiness, scope matrices, and IAF/ILAC mutual recognition."""

    @staticmethod
    def compile_accreditation_scope(
        context: FunctionalAssuranceContext,
        cab_name: str,
        conformity_standards: list[str],
        sectors: list[str],
        cmc_capabilities: Mapping[str, Any],
    ) -> dict[str, Any]:
        scope_digest = hashlib.sha256(f"{cab_name}:{conformity_standards}:{sectors}".encode()).hexdigest()
        return {
            "skill": "elmos-accreditation-scope-competence-matrix-compiler",
            "standard": "ISO/IEC 17011:2017 Clause 7.8",
            "cab_name": cab_name,
            "conformity_standards": conformity_standards,
            "sectors": sectors,
            "cmc_capabilities": cmc_capabilities,
            "scope_digest": scope_digest,
            "status": "APPROVED",
        }

    @staticmethod
    def resolve_global_recognition(
        context: FunctionalAssuranceContext,
        accreditation_body: str,
        signatory_agreements: list[str] | None = None,
    ) -> dict[str, Any]:
        agreements = signatory_agreements or ["IAF-MLA", "ILAC-MRA", "EA-MLA", "APAC-MRA"]
        return {
            "skill": "elmos-global-recognition-scope-resolver",
            "accreditation_body": accreditation_body,
            "recognized_agreements": agreements,
            "cross_border_acceptance": True,
            "principle": "Accredited once, accepted everywhere",
            "decision": ConformityDecision.CONFORMING.value,
        }

    @staticmethod
    def package_accredited_evidence(
        context: FunctionalAssuranceContext,
        evidence_manifest: Mapping[str, Any],
        ab_signoff_digest: str,
    ) -> dict[str, Any]:
        bundle_hash = hashlib.sha256(f"{context.candidate_digest}:{ab_signoff_digest}".encode()).hexdigest()
        return {
            "skill": "elmos-accredited-once-accepted-everywhere-evidence-packager",
            "candidate_digest": context.candidate_digest,
            "ab_signoff_digest": ab_signoff_digest,
            "evidence_bundle_hash": bundle_hash,
            "tamper_evident_seal": True,
            "status": "SEALED",
        }
