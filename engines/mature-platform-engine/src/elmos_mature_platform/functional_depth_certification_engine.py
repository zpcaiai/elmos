"""Functional Depth Certification Engine - Batch 45 Skill 1477.

Evaluates test coverage and execution results across all 10 critical functional categories,
calculates weighted depth scores, and certifies applications against enterprise depth gates.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Set
import uuid

from .types import (
    FunctionalCategory,
    FunctionalTestCaseResult,
    FunctionalDepthCertificationRecord,
)


class FunctionalDepthCertificationEngine:
    """Enforces functional depth certification across all enterprise functional categories."""

    def __init__(self) -> None:
        self._records: Dict[str, FunctionalDepthCertificationRecord] = {}

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_certification_record(
        self,
        application_id: str,
        version: str,
        min_depth_threshold: float = 95.0,
    ) -> FunctionalDepthCertificationRecord:
        """Create a new functional depth certification record."""
        if not application_id or not version:
            raise ValueError("application_id and version must not be empty")
        if min_depth_threshold <= 0.0 or min_depth_threshold > 100.0:
            raise ValueError("min_depth_threshold must be between 0.0 and 100.0")

        cert_id = f"fdcert-{uuid.uuid4().hex[:12]}"
        record = FunctionalDepthCertificationRecord(
            cert_id=cert_id,
            application_id=application_id,
            version=version,
            depth_score=0.0,
            is_certified=False,
            test_results=[],
            certified_at="",
            certified_by="",
            min_depth_threshold=min_depth_threshold,
        )
        self._records[cert_id] = record
        return record

    def record_test_result(
        self,
        cert_id: str,
        test_result: FunctionalTestCaseResult,
    ) -> FunctionalDepthCertificationRecord:
        """Add a functional test case execution result."""
        if cert_id not in self._records:
            raise ValueError(f"Certification record {cert_id} not found")
        if not test_result.test_id or not test_result.name:
            raise ValueError("test_id and name must not be empty")
        if test_result.depth_weight <= 0.0:
            raise ValueError("depth_weight must be positive")

        record = self._records[cert_id]
        record.test_results.append(test_result)
        return record

    def evaluate_depth(self, cert_id: str) -> FunctionalDepthCertificationRecord:
        """Calculate weighted score, verify category coverage, and evaluate certification status."""
        if cert_id not in self._records:
            raise ValueError(f"Certification record {cert_id} not found")

        record = self._records[cert_id]
        if not record.test_results:
            record.depth_score = 0.0
            record.is_certified = False
            return record

        total_weight = sum(t.depth_weight for t in record.test_results)
        passed_weight = sum(t.depth_weight for t in record.test_results if t.passed)

        record.depth_score = round((passed_weight / total_weight * 100.0), 2) if total_weight > 0 else 0.0

        # Check coverage across all 10 mandatory functional categories
        covered_cats: Set[FunctionalCategory] = {t.category for t in record.test_results}
        all_cats: Set[FunctionalCategory] = set(FunctionalCategory)
        all_covered = all_cats.issubset(covered_cats)

        # Certification requires meeting the depth threshold AND covering all 10 categories
        record.is_certified = (record.depth_score >= record.min_depth_threshold) and all_covered
        return record

    def issue_certification(
        self,
        cert_id: str,
        certified_by: str,
    ) -> FunctionalDepthCertificationRecord:
        """Issue final certification attestation if depth criteria are met."""
        if cert_id not in self._records:
            raise ValueError(f"Certification record {cert_id} not found")
        if not certified_by:
            raise ValueError("certified_by must not be empty")

        record = self.evaluate_depth(cert_id)
        if not record.is_certified:
            uncovered = self.get_uncovered_categories(cert_id)
            reasons = []
            if record.depth_score < record.min_depth_threshold:
                reasons.append(f"depth score {record.depth_score}% < threshold {record.min_depth_threshold}%")
            if uncovered:
                reasons.append(f"uncovered categories: {[c.value for c in uncovered]}")
            raise ValueError(f"Cannot certify application: {'; '.join(reasons)}")

        record.certified_by = certified_by
        record.certified_at = self._now_iso()
        return record

    def get_uncovered_categories(self, cert_id: str) -> List[FunctionalCategory]:
        """Return any functional categories that lack test results."""
        if cert_id not in self._records:
            raise ValueError(f"Certification record {cert_id} not found")

        record = self._records[cert_id]
        covered = {t.category for t in record.test_results}
        return [c for c in FunctionalCategory if c not in covered]

    def get_category_breakdown(self, cert_id: str) -> Dict[str, Any]:
        """Generate test results and pass rate per functional category."""
        if cert_id not in self._records:
            raise ValueError(f"Certification record {cert_id} not found")

        record = self._records[cert_id]
        breakdown: Dict[str, Dict[str, Any]] = {}

        for cat in FunctionalCategory:
            cat_tests = [t for t in record.test_results if t.category == cat]
            passed = sum(1 for t in cat_tests if t.passed)
            total = len(cat_tests)
            breakdown[cat.value] = {
                "total_tests": total,
                "passed_tests": passed,
                "failed_tests": total - passed,
                "pass_rate_pct": round((passed / total * 100.0), 2) if total > 0 else 0.0,
            }

        return breakdown

    def get_record(self, cert_id: str) -> Optional[FunctionalDepthCertificationRecord]:
        """Retrieve certification record by ID."""
        return self._records.get(cert_id)

    def get_certification_summary(self) -> Dict[str, Any]:
        """Generate high-level summary across all certification records."""
        total = len(self._records)
        certified_count = sum(1 for r in self._records.values() if r.is_certified)
        total_score = sum(r.depth_score for r in self._records.values())

        return {
            "total_certifications": total,
            "certified_count": certified_count,
            "certification_rate_pct": round((certified_count / total * 100.0), 2) if total > 0 else 0.0,
            "avg_depth_score": round(total_score / total, 2) if total > 0 else 0.0,
        }
