"""License IP Provenance Engine - Batch 40 Skill 1381.

Governs open-source licenses, SPDX identifiers, copyleft contamination risks,
and commercial use compliance across software artifacts and generated repositories.
"""

from datetime import datetime, timezone
import hashlib
from typing import Dict, List, Optional, Any
import uuid

from .types import (
    LicenseType,
    IpContaminationRisk,
    CodeArtifactLicenseRecord,
)


class LicenseIpProvenanceEngine:
    """Classifies software licenses, assesses copyleft risk, and gates commercial distribution."""

    SPDX_MAP: Dict[str, LicenseType] = {
        "mit": LicenseType.PERMISSIVE,
        "apache-2.0": LicenseType.PERMISSIVE,
        "bsd-2-clause": LicenseType.PERMISSIVE,
        "bsd-3-clause": LicenseType.PERMISSIVE,
        "isc": LicenseType.PERMISSIVE,
        "unlicense": LicenseType.PERMISSIVE,
        "lgpl-2.1": LicenseType.WEAK_COPYLEFT,
        "lgpl-3.0": LicenseType.WEAK_COPYLEFT,
        "mpl-2.0": LicenseType.WEAK_COPYLEFT,
        "epl-2.0": LicenseType.WEAK_COPYLEFT,
        "gpl-2.0": LicenseType.STRONG_COPYLEFT,
        "gpl-3.0": LicenseType.STRONG_COPYLEFT,
        "agpl-3.0": LicenseType.STRONG_COPYLEFT,
        "proprietary": LicenseType.PROPRIETARY,
        "commercial": LicenseType.PROPRIETARY,
    }

    def __init__(self) -> None:
        self._records: Dict[str, CodeArtifactLicenseRecord] = {}
        self._waivers: Dict[str, str] = {}

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def classify_spdx(self, spdx_identifier: str) -> LicenseType:
        """Classify license type based on SPDX identifier."""
        cleaned = spdx_identifier.strip().lower()
        return self.SPDX_MAP.get(cleaned, LicenseType.UNKNOWN)

    def scan_artifact(self, record: CodeArtifactLicenseRecord) -> str:
        """Register and analyze an artifact license record."""
        if not record.record_id or not record.artifact_name:
            raise ValueError("record_id and artifact_name must not be empty")

        if not record.license_type or record.license_type == LicenseType.UNKNOWN:
            record.license_type = self.classify_spdx(record.spdx_identifier)

        # Automatically derive contamination risk and initial approval status
        if record.license_type == LicenseType.PERMISSIVE:
            record.contamination_risk = IpContaminationRisk.NONE
            record.is_approved_for_commercial_use = True
        elif record.license_type == LicenseType.PROPRIETARY:
            record.contamination_risk = IpContaminationRisk.LOW
            record.is_approved_for_commercial_use = True
        elif record.license_type == LicenseType.WEAK_COPYLEFT:
            record.contamination_risk = IpContaminationRisk.MEDIUM
            record.is_approved_for_commercial_use = False
        elif record.license_type in (LicenseType.STRONG_COPYLEFT, LicenseType.UNKNOWN):
            record.contamination_risk = IpContaminationRisk.CRITICAL
            record.is_approved_for_commercial_use = False

        if not record.scanned_at:
            record.scanned_at = self._now_iso()

        self._records[record.record_id] = record
        return record.record_id

    def approve_commercial_use(self, record_id: str, waiver_reason: str) -> CodeArtifactLicenseRecord:
        """Approve an artifact for commercial use with recorded waiver reason."""
        if record_id not in self._records:
            raise ValueError(f"License record {record_id} not found")
        if not waiver_reason or len(waiver_reason.strip()) < 10:
            raise ValueError("Waiver reason must be provided with sufficient technical rationale (>= 10 chars)")

        record = self._records[record_id]
        if record.license_type == LicenseType.STRONG_COPYLEFT and "dual-licensed" not in waiver_reason.lower():
            raise ValueError("Strong copyleft licenses (GPL/AGPL) cannot be approved without dual-licensing proof")

        record.is_approved_for_commercial_use = True
        self._waivers[record_id] = waiver_reason
        return record

    def revoke_commercial_use(self, record_id: str, reason: str) -> CodeArtifactLicenseRecord:
        """Revoke commercial use approval for an artifact."""
        if record_id not in self._records:
            raise ValueError(f"License record {record_id} not found")

        record = self._records[record_id]
        record.is_approved_for_commercial_use = False
        self._waivers.pop(record_id, None)
        return record

    def verify_license_digest(self, record_id: str, license_text: str) -> bool:
        """Verify license file text against the recorded SHA-256 digest."""
        if record_id not in self._records:
            raise ValueError(f"License record {record_id} not found")

        record = self._records[record_id]
        if not record.license_file_digest:
            return False

        computed = hashlib.sha256(license_text.encode("utf-8")).hexdigest()
        return computed == record.license_file_digest

    def get_record(self, record_id: str) -> Optional[CodeArtifactLicenseRecord]:
        """Retrieve license record by ID."""
        return self._records.get(record_id)

    def get_contaminated_artifacts(self) -> List[CodeArtifactLicenseRecord]:
        """List all artifacts bearing MEDIUM or CRITICAL copyleft risk."""
        return [
            r for r in self._records.values()
            if r.contamination_risk in (IpContaminationRisk.MEDIUM, IpContaminationRisk.CRITICAL)
        ]

    def get_unapproved_artifacts(self) -> List[CodeArtifactLicenseRecord]:
        """List all artifacts not approved for commercial release."""
        return [r for r in self._records.values() if not r.is_approved_for_commercial_use]

    def get_license_governance_report(self) -> Dict[str, Any]:
        """Generate comprehensive license and IP provenance report."""
        total = len(self._records)
        by_type = {t.value: 0 for t in LicenseType}
        by_risk = {r.value: 0 for r in IpContaminationRisk}
        approved_count = 0

        for rec in self._records.values():
            by_type[rec.license_type.value] = by_type.get(rec.license_type.value, 0) + 1
            by_risk[rec.contamination_risk.value] = by_risk.get(rec.contamination_risk.value, 0) + 1
            if rec.is_approved_for_commercial_use:
                approved_count += 1

        return {
            "total_artifacts": total,
            "approved_count": approved_count,
            "unapproved_count": total - approved_count,
            "compliance_rate_pct": round((approved_count / total * 100.0), 2) if total > 0 else 0.0,
            "by_license_type": by_type,
            "by_contamination_risk": by_risk,
            "waivers_issued": len(self._waivers),
        }
