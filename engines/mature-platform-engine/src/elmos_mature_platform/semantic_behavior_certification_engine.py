"""Semantic Behavior Certification Engine - Batch 45 Skill 1479.

Certifies end-to-end semantic behavior equivalence across 5 differential dimensions
(output payload, side effects, latency profile, error recovery, event stream)
for migrated workloads and modernized microservices.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import uuid

from .types import (
    SemanticEquivalenceTier,
    DifferentialBehaviorDimension,
    SemanticBehaviorAssertionResult,
    SemanticBehaviorCertificationRecord,
)


class SemanticBehaviorCertificationEngine:
    """Certifies semantic and behavioral correctness between source and target systems."""

    def __init__(self) -> None:
        self._records: Dict[str, SemanticBehaviorCertificationRecord] = {}

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_certification_record(
        self,
        source_system_ref: str,
        target_system_ref: str,
        min_assertions: int = 5,
    ) -> SemanticBehaviorCertificationRecord:
        """Create a new semantic equivalence certification record."""
        if not source_system_ref or not target_system_ref:
            raise ValueError("source_system_ref and target_system_ref must not be empty")
        if min_assertions < 1:
            raise ValueError("min_assertions must be at least 1")

        cert_id = f"semcert-{uuid.uuid4().hex[:12]}"
        record = SemanticBehaviorCertificationRecord(
            cert_id=cert_id,
            source_system_ref=source_system_ref,
            target_system_ref=target_system_ref,
            tier=SemanticEquivalenceTier.NON_EQUIVALENT,
            is_certified=False,
            assertions=[],
            certified_at="",
            certified_by="",
            min_assertions_required=min_assertions,
        )
        self._records[cert_id] = record
        return record

    def record_assertion(
        self,
        cert_id: str,
        assertion: SemanticBehaviorAssertionResult,
    ) -> SemanticBehaviorCertificationRecord:
        """Add a behavioral differential assertion result."""
        if cert_id not in self._records:
            raise ValueError(f"Certification record {cert_id} not found")
        if not assertion.assertion_id or not assertion.name:
            raise ValueError("assertion_id and name must not be empty")

        record = self._records[cert_id]
        record.assertions.append(assertion)
        return record

    def evaluate_equivalence(self, cert_id: str) -> SemanticBehaviorCertificationRecord:
        """Evaluate assertions and classify equivalence tier and certification readiness."""
        if cert_id not in self._records:
            raise ValueError(f"Certification record {cert_id} not found")

        record = self._records[cert_id]
        if len(record.assertions) < record.min_assertions_required:
            record.tier = SemanticEquivalenceTier.NON_EQUIVALENT
            record.is_certified = False
            return record

        payload_failures = [
            a for a in record.assertions
            if a.dimension == DifferentialBehaviorDimension.OUTPUT_PAYLOAD and not a.equivalent
        ]
        side_effect_failures = [
            a for a in record.assertions
            if a.dimension == DifferentialBehaviorDimension.SIDE_EFFECT and not a.equivalent
        ]

        if payload_failures or side_effect_failures:
            record.tier = SemanticEquivalenceTier.NON_EQUIVALENT
            record.is_certified = False
            return record

        other_failures = [
            a for a in record.assertions
            if not a.equivalent
        ]

        if not other_failures:
            record.tier = SemanticEquivalenceTier.STRICT_EQUIVALENT
            record.is_certified = True
        elif all(a.dimension in (DifferentialBehaviorDimension.LATENCY_PROFILE, DifferentialBehaviorDimension.EVENT_STREAM) for a in other_failures):
            record.tier = SemanticEquivalenceTier.OBSERVABLE_EQUIVALENT
            record.is_certified = True
        else:
            record.tier = SemanticEquivalenceTier.PERMISSIBLE_DELTA
            record.is_certified = False

        return record

    def issue_certification(
        self,
        cert_id: str,
        certified_by: str,
    ) -> SemanticBehaviorCertificationRecord:
        """Issue certification attestation if equivalence criteria are met."""
        if cert_id not in self._records:
            raise ValueError(f"Certification record {cert_id} not found")
        if not certified_by:
            raise ValueError("certified_by must not be empty")

        record = self.evaluate_equivalence(cert_id)
        if not record.is_certified:
            raise ValueError(
                f"Cannot certify semantic behavior: equivalence tier is {record.tier.value}; "
                f"strict or observable equivalence required with at least {record.min_assertions_required} assertions."
            )

        record.certified_by = certified_by
        record.certified_at = self._now_iso()
        return record

    def get_record(self, cert_id: str) -> Optional[SemanticBehaviorCertificationRecord]:
        """Retrieve certification record by ID."""
        return self._records.get(cert_id)

    def get_dimension_summary(self, cert_id: str) -> Dict[str, Any]:
        """Break down assertion outcomes by differential dimension."""
        if cert_id not in self._records:
            raise ValueError(f"Certification record {cert_id} not found")

        record = self._records[cert_id]
        summary: Dict[str, Dict[str, int]] = {}

        for dim in DifferentialBehaviorDimension:
            dim_assertions = [a for a in record.assertions if a.dimension == dim]
            passed = sum(1 for a in dim_assertions if a.equivalent)
            summary[dim.value] = {
                "total": len(dim_assertions),
                "equivalent": passed,
                "divergent": len(dim_assertions) - passed,
            }

        return summary

    def get_certification_report(self) -> Dict[str, Any]:
        """Generate high-level report across all semantic behavior certifications."""
        total = len(self._records)
        by_tier = {t.value: 0 for t in SemanticEquivalenceTier}
        certified_count = sum(1 for r in self._records.values() if r.is_certified)

        for r in self._records.values():
            by_tier[r.tier.value] = by_tier.get(r.tier.value, 0) + 1

        return {
            "total_certifications": total,
            "certified_count": certified_count,
            "certification_rate_pct": round((certified_count / total * 100.0), 2) if total > 0 else 0.0,
            "by_tier": by_tier,
        }
