"""
Operations Evidence Reporting Engine.
"""

from typing import List, Dict, Any, Optional
import hashlib
import json
import datetime

from elmos_mature_platform.types import (
    CustomerOperationsReport,
    OperationalEvidenceItem,
    EvidenceReportType,
)

class OperationsEvidenceReportingEngine:
    """Engine for operations evidence reporting and customer reports."""

    def __init__(self) -> None:
        """Initialize the OperationsEvidenceReportingEngine."""
        self._reports: Dict[str, CustomerOperationsReport] = {}
        self._evidence_items: Dict[str, OperationalEvidenceItem] = {}

    def _compute_hash(self, source_system: str, evidence_type: str, payload_str: str) -> str:
        """Compute SHA-256 hash for provenance."""
        content = f"{source_system}{evidence_type}{payload_str}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def create_report(self, report: CustomerOperationsReport) -> str:
        """Store report, return report_id."""
        if not report.report_id:
            raise ValueError("Report ID cannot be empty.")
        self._reports[report.report_id] = report
        return report.report_id

    def record_evidence(self, item: OperationalEvidenceItem) -> str:
        """Record evidence item and compute provenance_hash if missing."""
        if not item.item_id:
            raise ValueError("Evidence ID cannot be empty.")
            
        if not item.provenance_hash:
            item.provenance_hash = self._compute_hash(
                item.source_system, 
                item.evidence_type, 
                str(item.payload)
            )
            
        self._evidence_items[item.item_id] = item
        return item.item_id

    def link_evidence_to_report(self, report_id: str, item_id: str) -> CustomerOperationsReport:
        """Append item_id to report.evidence_items."""
        if report_id not in self._reports:
            raise ValueError(f"Unknown report ID: {report_id}")
        if item_id not in self._evidence_items:
            raise ValueError(f"Unknown evidence ID: {item_id}")
            
        report = self._reports[report_id]
        if item_id not in report.evidence_items:
            report.evidence_items.append(item_id)
            
        return report

    def verify_evidence_integrity(self, item_id: str) -> bool:
        """Recompute sha256 hash and verify match."""
        if item_id not in self._evidence_items:
            raise ValueError(f"Unknown evidence ID: {item_id}")
            
        item = self._evidence_items[item_id]
        computed_hash = self._compute_hash(
            item.source_system, 
            item.evidence_type, 
            str(item.payload)
        )
        
        is_valid = (item.provenance_hash == computed_hash)
        item.verified = is_valid
        return is_valid

    def signoff_report(self, report_id: str, approver: str) -> CustomerOperationsReport:
        """Sign off report if it has verified evidence items."""
        if report_id not in self._reports:
            raise ValueError(f"Unknown report ID: {report_id}")
            
        report = self._reports[report_id]
        
        if not report.evidence_items:
            raise ValueError("Cannot signoff report without evidence.")
            
        for item_id in report.evidence_items:
            if not self.verify_evidence_integrity(item_id):
                raise ValueError(f"Cannot signoff report: Evidence {item_id} failed verification.")
                
        if not approver:
            raise ValueError("Approver cannot be empty.")
            
        report.signoff_by = approver
        return report

    def publish_report(self, report_id: str) -> CustomerOperationsReport:
        """Publish a signed-off report."""
        if report_id not in self._reports:
            raise ValueError(f"Unknown report ID: {report_id}")
            
        report = self._reports[report_id]
        
        if not report.signoff_by:
            raise ValueError("Cannot publish report without signoff.")
            
        report.published = True
        return report

    def get_customer_reports(self, customer_id: str, report_type: Optional[EvidenceReportType] = None) -> List[CustomerOperationsReport]:
        """Get reports for a specific customer, optionally filtered by report_type."""
        result = []
        for report in self._reports.values():
            if report.customer_id == customer_id:
                if report_type is None or report.report_type == report_type:
                    result.append(report)
        return result

    def get_unverified_evidence(self) -> List[OperationalEvidenceItem]:
        """Get evidence items where verified=False or integrity check fails."""
        result = []
        for item in self._evidence_items.values():
            if not item.verified or not self.verify_evidence_integrity(item.item_id):
                result.append(item)
        return result

    def get_operations_audit_summary(self) -> Dict[str, Any]:
        """Total reports, published count, total evidence items, verification rate pct."""
        total_reports = len(self._reports)
        published_count = sum(1 for r in self._reports.values() if r.published)
        total_evidence_items = len(self._evidence_items)
        
        verified_count = 0
        if total_evidence_items > 0:
            for item in self._evidence_items.values():
                if self.verify_evidence_integrity(item.item_id):
                    verified_count += 1
            verification_rate_pct = (verified_count / total_evidence_items) * 100
        else:
            verification_rate_pct = 100.0
            
        return {
            "total_reports": total_reports,
            "published_count": published_count,
            "total_evidence_items": total_evidence_items,
            "verification_rate_pct": verification_rate_pct,
        }
