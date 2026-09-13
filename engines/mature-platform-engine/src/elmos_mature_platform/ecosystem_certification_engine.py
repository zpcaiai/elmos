"""Ecosystem Certification Engine (Batch 45 - Skill 1484).

Evaluates, tests, and certifies partner integrations, plugins, connectors,
and ecosystem solution blueprints against security, reliability, schema compatibility,
and SLSA supply chain requirements.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from typing import Any, Dict, List, Optional
import uuid

from elmos_mature_platform.types import (
    EcosystemCertificationRecord,
    EcosystemCertificationScope,
    EcosystemPartnerTier,
)


class EcosystemCertificationEngine:
    """Industrial engine for partner and community ecosystem certification (B45)."""

    PASSING_THRESHOLD = 85.0

    def __init__(self, validity_days: int = 365):
        self.validity_days = validity_days
        self._certifications: Dict[str, EcosystemCertificationRecord] = {}

    def register_candidate(
        self,
        partner_id: str,
        extension_name: str,
        version: str,
        scope: EcosystemCertificationScope,
        tier: EcosystemPartnerTier = EcosystemPartnerTier.COMMUNITY,
    ) -> EcosystemCertificationRecord:
        """Register a new candidate extension for ecosystem certification."""
        for c in self._certifications.values():
            if c.partner_id == partner_id and c.extension_name == extension_name and c.version == version:
                raise ValueError(
                    f"Candidate '{extension_name} v{version}' already registered for partner '{partner_id}'"
                )

        cert_id = f"eco-{scope.value[:4]}-{uuid.uuid4().hex[:6]}"
        record = EcosystemCertificationRecord(
            cert_id=cert_id,
            partner_id=partner_id,
            extension_name=extension_name,
            version=version,
            scope=scope,
            tier=tier,
            is_certified=False,
            compliance_score=0.0,
            certified_at="",
            expires_at="",
            signature="",
            badges=[],
        )
        self._certifications[cert_id] = record
        return record

    def evaluate_certification(
        self,
        cert_id: str,
        security_clean: bool,
        tests_passed: bool,
        schema_valid: bool,
        slsa_verified: bool,
        certifier_key: str = "elmos-ecosystem-notary",
    ) -> EcosystemCertificationRecord:
        """Evaluate compliance criteria and issue certification if threshold met."""
        record = self._certifications.get(cert_id)
        if not record:
            raise ValueError(f"Certification record '{cert_id}' not found")

        score = 0.0
        badges: List[str] = []

        if security_clean:
            score += 35.0
            badges.append("SECURITY_VERIFIED")
        if tests_passed:
            score += 30.0
            badges.append("TEST_COMPLIANT")
        if schema_valid:
            score += 20.0
            badges.append("SCHEMA_COMPATIBLE")
        if slsa_verified:
            score += 15.0
            badges.append("SLSA_PROVENANCE")

        record.compliance_score = score
        now = datetime.now(timezone.utc)

        if score >= self.PASSING_THRESHOLD:
            record.is_certified = True
            record.certified_at = now.isoformat()
            record.expires_at = (now + timedelta(days=self.validity_days)).isoformat()
            record.badges = badges

            # Generate HMAC attestation signature
            payload = f"{record.cert_id}:{record.partner_id}:{record.extension_name}:{record.version}:{score}"
            sig = hmac.new(certifier_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
            record.signature = sig
        else:
            record.is_certified = False
            record.certified_at = ""
            record.expires_at = ""
            record.signature = ""
            record.badges = []

        return record

    def revoke_certification(
        self,
        cert_id: str,
        reason: str,
    ) -> EcosystemCertificationRecord:
        """Revoke active certification due to policy violation, vulnerability, or deprecation."""
        record = self._certifications.get(cert_id)
        if not record:
            raise ValueError(f"Certification record '{cert_id}' not found")
        if not reason.strip():
            raise ValueError("Revocation reason cannot be empty")

        record.is_certified = False
        record.signature = ""
        record.badges.append(f"REVOKED: {reason}")
        return record

    def check_validity(self, cert_id: str) -> bool:
        """Check if certification is active and unexpired."""
        record = self._certifications.get(cert_id)
        if not record or not record.is_certified or not record.expires_at:
            return False

        try:
            exp = datetime.fromisoformat(record.expires_at)
            return datetime.now(timezone.utc) <= exp
        except Exception:
            return False

    def get_ecosystem_directory(self) -> Dict[str, Any]:
        """Aggregate certified extensions by scope and partner tier."""
        by_scope: Dict[str, int] = {}
        for s in EcosystemCertificationScope:
            by_scope[s.value] = 0

        by_tier: Dict[str, int] = {}
        for t in EcosystemPartnerTier:
            by_tier[t.value] = 0

        certified_count = 0
        for c in self._certifications.values():
            if c.is_certified and self.check_validity(c.cert_id):
                certified_count += 1
                by_scope[c.scope.value] += 1
                by_tier[c.tier.value] += 1

        return {
            "total_registered_candidates": len(self._certifications),
            "active_certified_count": certified_count,
            "certified_by_scope": by_scope,
            "certified_by_tier": by_tier,
        }

    def get_certification(self, cert_id: str) -> Optional[EcosystemCertificationRecord]:
        """Retrieve certification by ID."""
        return self._certifications.get(cert_id)

    def list_certifications(
        self,
        scope: Optional[EcosystemCertificationScope] = None,
        certified_only: bool = False,
    ) -> List[EcosystemCertificationRecord]:
        """List certifications, optionally filtered by scope and certified state."""
        results = list(self._certifications.values())
        if scope:
            results = [c for c in results if c.scope == scope]
        if certified_only:
            results = [c for c in results if c.is_certified and self.check_validity(c.cert_id)]
        return results
