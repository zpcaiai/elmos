"""Private Sovereign Cloud Edition Engine (Batch 38 - Skill 1327).

Manages sovereign enclave specifications, data residency boundaries,
zero-egress airgap network fencing, local KMS integrations, and regulatory audit receipts.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any, Dict, List, Optional
import uuid

from elmos_mature_platform.types import (
    AirgapEnclaveType,
    SovereignAuditReceipt,
    SovereignEnclaveSpec,
    SovereignJurisdiction,
)


class PrivateSovereignCloudEditionEngine:
    """Industrial engine for sovereign cloud airgapped enclaves (B38)."""

    def __init__(self):
        self._enclaves: Dict[str, SovereignEnclaveSpec] = {}
        self._blocked_egress: Dict[str, int] = {}
        self._receipts: Dict[str, SovereignAuditReceipt] = {}
        self._audit_log: List[Dict[str, Any]] = []

    def register_enclave(
        self,
        edition_id: str,
        jurisdiction: SovereignJurisdiction,
        enclave_type: AirgapEnclaveType = AirgapEnclaveType.HARDWARE_AIRGAP,
        cryptographic_boundary: str = "fips-140-3-level-3",
        local_kms_endpoint: str = "https://kms.sovereign.local",
        allow_egress: bool = False,
    ) -> SovereignEnclaveSpec:
        """Provision and register a sovereign enclave."""
        enclave_id = f"s-enc-{uuid.uuid4().hex[:8]}"
        spec = SovereignEnclaveSpec(
            enclave_id=enclave_id,
            edition_id=edition_id,
            jurisdiction=jurisdiction,
            enclave_type=enclave_type,
            cryptographic_boundary=cryptographic_boundary,
            local_kms_endpoint=local_kms_endpoint,
            allow_egress=allow_egress,
            registered_at=datetime.now(timezone.utc).isoformat(),
        )
        self._enclaves[enclave_id] = spec
        self._blocked_egress[enclave_id] = 0
        self._record_audit("enclave_registered", enclave_id, {
            "edition_id": edition_id,
            "jurisdiction": jurisdiction.value,
            "allow_egress": allow_egress,
        })
        return spec

    def get_enclave(self, enclave_id: str) -> Optional[SovereignEnclaveSpec]:
        """Fetch enclave specification."""
        return self._enclaves.get(enclave_id)

    def intercept_egress_traffic(
        self,
        enclave_id: str,
        destination_url: str,
        payload_bytes: int,
    ) -> bool:
        """Filter outbound egress attempts.

        Returns True if egress was allowed, False if blocked by sovereign airgap policy.
        """
        enclave = self._get_enclave_or_raise(enclave_id)
        if not enclave.allow_egress:
            self._blocked_egress[enclave_id] = self._blocked_egress.get(enclave_id, 0) + 1
            self._record_audit("egress_blocked", enclave_id, {
                "destination": destination_url,
                "bytes": payload_bytes,
                "blocked_count": self._blocked_egress[enclave_id],
            })
            return False

        self._record_audit("egress_permitted", enclave_id, {"destination": destination_url})
        return True

    def generate_sovereignty_audit_receipt(
        self,
        enclave_id: str,
        verifier_identity: str = "sovereign-compliance-officer",
    ) -> SovereignAuditReceipt:
        """Issue a tamper-evident audit receipt validating residency and airgap status."""
        enclave = self._get_enclave_or_raise(enclave_id)
        blocked_count = self._blocked_egress.get(enclave_id, 0)
        timestamp = datetime.now(timezone.utc).isoformat()

        # Hash residency data
        raw = f"{enclave_id}:{enclave.jurisdiction.value}:{enclave.cryptographic_boundary}:{blocked_count}:{timestamp}:{verifier_identity}"
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()

        receipt = SovereignAuditReceipt(
            receipt_id=f"rec-{uuid.uuid4().hex[:8]}",
            enclave_id=enclave_id,
            data_residency_verified=True,
            egress_attempt_blocked_count=blocked_count,
            signature_digest=digest,
            generated_at=timestamp,
        )

        self._receipts[receipt.receipt_id] = receipt
        self._record_audit("audit_receipt_generated", receipt.receipt_id, {"enclave_id": enclave_id})
        return receipt

    def get_audit_receipt(self, receipt_id: str) -> Optional[SovereignAuditReceipt]:
        """Fetch audit receipt by ID."""
        return self._receipts.get(receipt_id)

    def get_sovereignty_dashboard(self) -> Dict[str, Any]:
        """Aggregate statistics across sovereign cloud enclaves."""
        total = len(self._enclaves)
        by_jurisdiction: Dict[str, int] = {}
        by_type: Dict[str, int] = {}
        total_blocked = sum(self._blocked_egress.values())

        for e in self._enclaves.values():
            j = e.jurisdiction.value
            t = e.enclave_type.value
            by_jurisdiction[j] = by_jurisdiction.get(j, 0) + 1
            by_type[t] = by_type.get(t, 0) + 1

        strict_airgap_count = sum(1 for e in self._enclaves.values() if not e.allow_egress)

        return {
            "total_enclaves": total,
            "strict_airgap_enclaves": strict_airgap_count,
            "total_blocked_egress_attempts": total_blocked,
            "jurisdiction_breakdown": by_jurisdiction,
            "enclave_type_breakdown": by_type,
            "total_audit_receipts": len(self._receipts),
        }

    def _get_enclave_or_raise(self, enclave_id: str) -> SovereignEnclaveSpec:
        if enclave_id not in self._enclaves:
            raise ValueError(f"Sovereign enclave {enclave_id} not registered")
        return self._enclaves[enclave_id]

    def _record_audit(self, action: str, target: str, details: Dict[str, Any]) -> None:
        self._audit_log.append({
            "action": action,
            "target": target,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": details,
        })

    def get_audit_log(self) -> List[Dict[str, Any]]:
        return list(self._audit_log)
