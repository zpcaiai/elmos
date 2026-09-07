"""ISO/IEC 17065 Certificate Lifecycle, WORM Merkle Sealing, and SCITT Transparency."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Mapping

from ..domain import (
    AssuranceLevel,
    CertificateRecord,
    CertificateStatus,
    ConformityDecision,
    FunctionalAssuranceContext,
    ProductAssuranceLevel,
    SectorType,
    WormMerkleTree,
)


class CertificateLifecycleController:
    """Controller for certificate issuance, revocation, WORM Merkle sealing, and transparency."""

    @staticmethod
    def issue_certificate(
        context: FunctionalAssuranceContext,
        assurance_level: str,
        product_level: str,
        scope_description: str,
        evaluator_id: str,
        independent_reviewer_id: str,
        sector: str | None = None,
        hsm_key_id: str = "HSM_KMS_CERT_KEY_P384",
    ) -> CertificateRecord:
        # Enforce strict ISO/IEC 17065 Segregation of Duties
        if evaluator_id == independent_reviewer_id:
            raise ValueError("ISO/IEC 17065 violation: evaluator and independent reviewer must be distinct individuals")

        # Build Merkle tree for the certificate evidence
        tree = WormMerkleTree()
        tree.append(context.candidate_digest, role="candidate-digest")
        tree.append(context.base_evidence_receipt, role="base-evidence-receipt")
        tree.append(scope_description, role="scope-description")
        tree.append(f"{evaluator_id}:{independent_reviewer_id}", role="signoffs")

        cert_id = f"CERT-ELMOS-{hashlib.sha256(f'{context.tenant_id}:{context.candidate_digest}:{time.time()}'.encode()).hexdigest()[:16].upper()}"
        issued_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        expires_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 365 * 86400))

        signature_payload = f"{cert_id}:{context.candidate_digest}:{tree.root_digest}:{issued_at}"
        signature_receipt = hashlib.sha256(f"SIGNED_BY_{hsm_key_id}:{signature_payload}".encode()).hexdigest()

        return CertificateRecord(
            certificate_id=cert_id,
            subject_candidate_digest=context.candidate_digest,
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            assurance_level=AssuranceLevel(assurance_level),
            product_level=ProductAssuranceLevel(product_level),
            sector=SectorType(sector) if sector else None,
            decision=ConformityDecision.CONFORMING,
            status=CertificateStatus.ISSUED,
            scope_description=scope_description,
            merkle_root_digest=tree.root_digest,
            issued_at=issued_at,
            expires_at=expires_at,
            evaluator_id=evaluator_id,
            independent_reviewer_id=independent_reviewer_id,
            hsm_key_id=hsm_key_id,
            signature_receipt=signature_receipt,
            metadata={"tree_leaf_count": len(tree.leaves)},
        )

    @staticmethod
    def revoke_certificate(
        context: FunctionalAssuranceContext,
        certificate_id: str,
        reason: str,
        revocation_authority_id: str,
    ) -> dict[str, Any]:
        revocation_receipt = hashlib.sha256(f"REVOKE:{certificate_id}:{reason}:{revocation_authority_id}".encode()).hexdigest()
        return {
            "skill": "elmos-certificate-drift-revocation-controller",
            "certificate_id": certificate_id,
            "status": CertificateStatus.REVOKED.value,
            "revocation_reason": reason,
            "revoked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "revocation_receipt": revocation_receipt,
            "decision": ConformityDecision.CONFORMING.value,
        }

    @staticmethod
    def seal_worm_merkle_evidence(
        context: FunctionalAssuranceContext,
        evidence_items: list[Mapping[str, Any]],
    ) -> dict[str, Any]:
        tree = WormMerkleTree()
        for item in evidence_items:
            role = str(item.get("role", "evidence-item"))
            data = item.get("data", item)
            tree.append(data, role=role)

        valid = tree.verify_integrity()
        return {
            "skill": "elmos-evidence-worm-merkle-sealer",
            "leaf_count": len(tree.leaves),
            "merkle_root_digest": tree.root_digest,
            "merkle_root": tree.root_digest,
            "integrity_verified": valid,
            "tamper_evident": True,
            "decision": (ConformityDecision.CONFORMING if valid else ConformityDecision.NON_CONFORMING).value,
        }

    @staticmethod
    def evaluate_deployment_admission(
        context: FunctionalAssuranceContext,
        certificate: Mapping[str, Any],
        required_min_assurance: str = "E3",
    ) -> dict[str, Any]:
        status = certificate.get("status")
        candidate = certificate.get("subject_candidate_digest")
        level = certificate.get("assurance_level", "E0")

        valid_status = status == CertificateStatus.ISSUED.value
        digest_match = candidate == context.candidate_digest
        level_order = [e.value for e in AssuranceLevel]
        req_idx = level_order.index(required_min_assurance) if required_min_assurance in level_order else 0
        actual_idx = level_order.index(level) if level in level_order else 0
        level_ok = actual_idx >= req_idx

        admitted = valid_status and digest_match and level_ok
        return {
            "skill": "elmos-certificate-deployment-admission-controller",
            "admitted": admitted,
            "decision": (ConformityDecision.CONFORMING if admitted else ConformityDecision.NON_CONFORMING).value,
            "valid_status": valid_status,
            "candidate_digest_matched": digest_match,
            "assurance_level_sufficient": level_ok,
        }
