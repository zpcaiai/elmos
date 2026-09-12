"""SBOM Component Identity Engine (Batch 40 - Skill 1379).

Manages software bill of materials (SBOM) component identity, canonical Package URL (purl)
resolution, CPE matching, cryptographic hash attestation, and supply chain tamper detection.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    ComponentPurlType,
    SbomIdentityRecord,
    SbomIdentityVerificationResult,
)


class SbomComponentIdentityEngine:
    """Canonical component identity and tamper verification for software supply chains."""

    def __init__(self) -> None:
        self._components: Dict[str, SbomIdentityRecord] = {}
        self._purl_index: Dict[str, str] = {}
        self._verifications: Dict[str, SbomIdentityVerificationResult] = {}

    def register_component_identity(self, record: SbomIdentityRecord) -> str:
        """Register a software component's cryptographic and packaging identity."""
        if not record.component_name or not record.version:
            raise ValueError("component_name and version are required")
        if not record.purl:
            raise ValueError("purl (Package URL) is required")

        if not record.identity_id:
            record.identity_id = f"sbom-id-{uuid.uuid4().hex[:8]}"

        if not record.registered_at:
            record.registered_at = datetime.now(timezone.utc).isoformat()

        # Deduce purl type if generic
        purl_lower = record.purl.lower()
        if "pkg:maven" in purl_lower:
            record.purl_type = ComponentPurlType.MAVEN
        elif "pkg:npm" in purl_lower:
            record.purl_type = ComponentPurlType.NPM
        elif "pkg:pypi" in purl_lower:
            record.purl_type = ComponentPurlType.PYPI
        elif "pkg:golang" in purl_lower:
            record.purl_type = ComponentPurlType.GOLANG
        elif "pkg:cargo" in purl_lower:
            record.purl_type = ComponentPurlType.CARGO
        elif "pkg:nuget" in purl_lower:
            record.purl_type = ComponentPurlType.NUGET

        self._components[record.identity_id] = record
        self._purl_index[record.purl] = record.identity_id
        return record.identity_id

    def verify_component_digest(self, identity_id: str, actual_sha256: str) -> bool:
        """Verify the cryptographic digest of an installed component against its identity record."""
        record = self._components.get(identity_id)
        if not record:
            raise ValueError(f"Component identity not found: {identity_id}")
        if not actual_sha256:
            raise ValueError("actual_sha256 cannot be empty")

        if not record.sha256_digest:
            record.verified_identity = False
            return False

        if record.sha256_digest.lower().strip() != actual_sha256.lower().strip():
            record.tamper_detected = True
            record.verified_identity = False
            return False

        record.tamper_detected = False
        record.verified_identity = True
        return True

    def verify_bom_integrity(
        self, expected_digests: Dict[str, str]
    ) -> SbomIdentityVerificationResult:
        """Batch verify an entire bill of materials from a mapping of purl -> actual_sha256."""
        total = len(expected_digests)
        verified = 0
        mismatch = 0
        unresolved = 0
        tampered: List[str] = []

        for purl, actual_hash in expected_digests.items():
            comp_id = self._purl_index.get(purl)
            if not comp_id:
                unresolved += 1
                continue

            record = self._components[comp_id]
            if record.sha256_digest and record.sha256_digest.lower() == actual_hash.lower():
                record.verified_identity = True
                record.tamper_detected = False
                verified += 1
            else:
                record.tamper_detected = True
                record.verified_identity = False
                mismatch += 1
                tampered.append(record.purl)

        verdict = "pass" if (mismatch == 0 and unresolved == 0 and total > 0) else "fail"
        if mismatch == 0 and unresolved > 0:
            verdict = "warning"

        res = SbomIdentityVerificationResult(
            verification_id=f"ver-{uuid.uuid4().hex[:8]}",
            component_count=total,
            verified_count=verified,
            mismatch_count=mismatch,
            unresolved_count=unresolved,
            tampered_components=tampered,
            verdict=verdict,
            verified_at=datetime.now(timezone.utc).isoformat(),
        )
        self._verifications[res.verification_id] = res
        return res

    def lookup_by_purl(self, purl: str) -> Optional[SbomIdentityRecord]:
        """Lookup component identity record by canonical Package URL."""
        comp_id = self._purl_index.get(purl)
        if not comp_id:
            return None
        return self._components.get(comp_id)

    def get_components_by_license(self, license_expression: str) -> List[SbomIdentityRecord]:
        """Find all components governed by a particular license."""
        target = license_expression.lower().strip()
        return [
            c for c in self._components.values()
            if target in c.license_expression.lower()
        ]

    def get_identity_report(self) -> Dict[str, Any]:
        """Generate comprehensive SBOM component identity and integrity metrics."""
        total = len(self._components)
        verified_count = sum(1 for c in self._components.values() if c.verified_identity)
        tampered_count = sum(1 for c in self._components.values() if c.tamper_detected)
        direct_count = sum(1 for c in self._components.values() if c.is_direct_dependency)

        by_type: Dict[str, int] = {}
        for c in self._components.values():
            t = c.purl_type.value
            by_type[t] = by_type.get(t, 0) + 1

        return {
            "total_components": total,
            "verified_count": verified_count,
            "tampered_count": tampered_count,
            "direct_count": direct_count,
            "transitive_count": total - direct_count,
            "by_purl_type": by_type,
            "verifications_conducted": len(self._verifications),
        }
