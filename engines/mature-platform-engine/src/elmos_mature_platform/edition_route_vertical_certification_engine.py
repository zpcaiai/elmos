"""Edition Route Vertical Certification Engine (Batch 45 - Skill 1495).

Certifies the multi-dimensional compatibility and compliance matrix across
platform editions (Air-Gapped, Sovereign, Customer VPC, Multi-Tenant SaaS),
transformation routes, and industry vertical regulatory domains.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    MatrixCertificationRecord,
    MatrixCertificationStatus,
    VerticalDomain,
)


class EditionRouteVerticalCertificationEngine:
    """Multi-dimensional matrix certifier across editions, routes, and industry verticals."""

    def __init__(self) -> None:
        self._matrix: Dict[str, MatrixCertificationRecord] = {}

    def register_matrix_cell(self, record: MatrixCertificationRecord) -> str:
        """Register an edition-route-vertical qualification cell."""
        if not record.edition or not record.route_key:
            raise ValueError("edition and route_key are required")

        if not record.matrix_id:
            record.matrix_id = f"mat-{uuid.uuid4().hex[:8]}"

        self._matrix[record.matrix_id] = record
        return record.matrix_id

    def record_compliance_controls(
        self, matrix_id: str, passed: int, total: int
    ) -> MatrixCertificationRecord:
        """Record regulatory compliance control audit results for a matrix cell."""
        if passed < 0 or total < 0:
            raise ValueError("control counts cannot be negative")
        if passed > total:
            raise ValueError("passed controls cannot exceed total controls")

        record = self._matrix.get(matrix_id)
        if not record:
            raise ValueError(f"Matrix record not found: {matrix_id}")

        record.compliance_controls_passed = passed
        record.compliance_controls_total = total
        return record

    def update_certification_status(
        self,
        matrix_id: str,
        status: MatrixCertificationStatus,
        certified_by: str = "",
        evidence_ref: str = "",
        notes: str = "",
    ) -> MatrixCertificationRecord:
        """Update qualification status for a matrix cell with evidence and auditor signoff."""
        record = self._matrix.get(matrix_id)
        if not record:
            raise ValueError(f"Matrix record not found: {matrix_id}")

        # When certifying, if compliance controls were tested, ensure all passed
        if status == MatrixCertificationStatus.CERTIFIED:
            if record.compliance_controls_total > 0 and record.compliance_controls_passed < record.compliance_controls_total:
                raise ValueError("Cannot certify when compliance controls have not passed 100%")
            if not certified_by:
                raise ValueError("certified_by authority is required to grant CERTIFIED status")

            record.certified_at = datetime.now(timezone.utc).isoformat()
            record.certified_by = certified_by

        record.status = status
        if evidence_ref:
            record.evidence_bundle_ref = evidence_ref
        if notes:
            record.notes = notes

        return record

    def get_matrix_cell(self, matrix_id: str) -> Optional[MatrixCertificationRecord]:
        """Retrieve matrix certification record."""
        return self._matrix.get(matrix_id)

    def query_matrix(
        self,
        edition: Optional[str] = None,
        route_key: Optional[str] = None,
        vertical: Optional[VerticalDomain] = None,
    ) -> List[MatrixCertificationRecord]:
        """Filter matrix cells by edition, route key, or vertical industry domain."""
        results = list(self._matrix.values())

        if edition:
            results = [r for r in results if r.edition == edition]
        if route_key:
            results = [r for r in results if r.route_key == route_key]
        if vertical:
            results = [r for r in results if r.vertical == vertical]

        return results

    def get_vertical_certification_report(self) -> Dict[str, Any]:
        """Generate macro compliance and certification coverage report across all verticals."""
        total = len(self._matrix)
        by_status: Dict[str, int] = {s.value: 0 for s in MatrixCertificationStatus}
        by_vertical: Dict[str, Dict[str, int]] = {v.value: {"total": 0, "certified": 0} for v in VerticalDomain}
        by_edition: Dict[str, Dict[str, int]] = {}

        total_controls_passed = 0
        total_controls_total = 0

        for r in self._matrix.values():
            by_status[r.status.value] += 1
            v_key = r.vertical.value
            by_vertical[v_key]["total"] += 1
            if r.status == MatrixCertificationStatus.CERTIFIED:
                by_vertical[v_key]["certified"] += 1

            if r.edition not in by_edition:
                by_edition[r.edition] = {"total": 0, "certified": 0}
            by_edition[r.edition]["total"] += 1
            if r.status == MatrixCertificationStatus.CERTIFIED:
                by_edition[r.edition]["certified"] += 1

            total_controls_passed += r.compliance_controls_passed
            total_controls_total += r.compliance_controls_total

        certified_count = by_status[MatrixCertificationStatus.CERTIFIED.value]
        overall_coverage_pct = (certified_count / total * 100.0) if total > 0 else 0.0
        control_pass_pct = (
            (total_controls_passed / total_controls_total * 100.0)
            if total_controls_total > 0
            else 0.0
        )

        return {
            "total_cells": total,
            "certified_cells": certified_count,
            "overall_coverage_pct": round(overall_coverage_pct, 2),
            "total_controls_passed": total_controls_passed,
            "total_controls_total": total_controls_total,
            "control_compliance_pct": round(control_pass_pct, 2),
            "status_distribution": by_status,
            "by_vertical": by_vertical,
            "by_edition": by_edition,
        }
