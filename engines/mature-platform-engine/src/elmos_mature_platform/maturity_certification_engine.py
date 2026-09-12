"""Maturity Certification Engine."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from elmos_mature_platform.types import (
    CertificationDecision,
    DimensionAssessment,
    MaturityDimension,
    MaturityLevel,
    MaturityReport,
    ProductionReadinessChecklist,
    ResidualRisk,
    SeverityLevel,
)

class MaturityCertificationEngine:
    def __init__(self):
        self._reports: Dict[str, MaturityReport] = {}
        self._risks: Dict[str, ResidualRisk] = {}
        self._checklists: Dict[str, ProductionReadinessChecklist] = {}

    def assess_dimension(
        self,
        dimension: MaturityDimension,
        evidence_count: int,
        passing_tests: int,
        total_tests: int,
        gaps: Optional[List[str]] = None,
        blockers: Optional[List[str]] = None,
    ) -> DimensionAssessment:
        """Assess a single maturity dimension and compute its score and level."""
        gaps = gaps or []
        blockers = blockers or []
        
        # Compute score
        max_tests = max(total_tests, 1)
        base_score = (passing_tests / max_tests) * 100.0
        
        # Deduct for blockers
        score = max(0.0, base_score - (len(blockers) * 20.0))
        
        # Compute level
        level = MaturityLevel.L0_ABSENT
        if score >= 95.0:
            level = MaturityLevel.L5_OPTIMIZING
        elif score >= 80.0:
            level = MaturityLevel.L4_MEASURED
        elif score >= 60.0:
            level = MaturityLevel.L3_DEFINED
        elif score >= 40.0:
            level = MaturityLevel.L2_DEVELOPING
        elif score >= 20.0:
            level = MaturityLevel.L1_INITIAL

        return DimensionAssessment(
            dimension=dimension,
            level=level,
            score=score,
            evidence_count=evidence_count,
            passing_tests=passing_tests,
            total_tests=total_tests,
            gaps=gaps,
            blockers=blockers,
        )

    def generate_maturity_report(
        self,
        product_version: str,
        assessor: str,
        assessments: List[DimensionAssessment],
    ) -> MaturityReport:
        """Generate a complete maturity assessment report."""
        overall_score = 0.0
        if assessments:
            overall_score = sum(a.score for a in assessments) / len(assessments)
            
        overall_level = MaturityLevel.L0_ABSENT
        if overall_score >= 95.0:
            overall_level = MaturityLevel.L5_OPTIMIZING
        elif overall_score >= 80.0:
            overall_level = MaturityLevel.L4_MEASURED
        elif overall_score >= 60.0:
            overall_level = MaturityLevel.L3_DEFINED
        elif overall_score >= 40.0:
            overall_level = MaturityLevel.L2_DEVELOPING
        elif overall_score >= 20.0:
            overall_level = MaturityLevel.L1_INITIAL

        blocking_dimensions = [
            a.dimension for a in assessments if a.blockers or a.score < 60.0
        ]
        
        report_id = f"rpt-{product_version}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

        report = MaturityReport(
            report_id=report_id,
            product_version=product_version,
            assessment_date=datetime.now(timezone.utc).isoformat(),
            assessor=assessor,
            dimensions=assessments,
            overall_score=overall_score,
            overall_level=overall_level,
            blocking_dimensions=blocking_dimensions,
        )
        self._reports[report.report_id] = report
        return report

    def register_residual_risk(self, risk: ResidualRisk) -> None:
        """Add to risk register."""
        self._risks[risk.risk_id] = risk

    def accept_residual_risk(self, risk_id: str, accepted_by: str) -> ResidualRisk:
        """Mark risk as accepted with timestamp."""
        if risk_id not in self._risks:
            raise ValueError(f"Risk {risk_id} not found.")
        risk = self._risks[risk_id]
        risk.accepted_by = accepted_by
        risk.accepted_at = datetime.now(timezone.utc).isoformat()
        return risk

    def get_unaccepted_risks(self) -> List[ResidualRisk]:
        """Return risks without acceptance."""
        return [r for r in self._risks.values() if not r.accepted_by]

    def evaluate_certification_gate(self, report: MaturityReport) -> CertificationDecision:
        """Evaluate the certification gate readiness."""
        unaccepted_critical_high_risks = [
            r for r in self.get_unaccepted_risks()
            if r.severity in (SeverityLevel.CRITICAL, SeverityLevel.HIGH)
        ]
        
        has_critical_blocker = any(
            any("critical" in b.lower() for b in a.blockers)
            for a in report.dimensions
        )

        if has_critical_blocker or report.overall_score < 40.0:
            report.certification_decision = CertificationDecision.REJECTED
        elif unaccepted_critical_high_risks:
            report.certification_decision = CertificationDecision.BLOCKED
        elif report.overall_score >= 80.0 and not report.blocking_dimensions:
            unaccepted_critical_risks = [
                r for r in self.get_unaccepted_risks()
                if r.severity == SeverityLevel.CRITICAL
            ]
            if not unaccepted_critical_risks:
                report.certification_decision = CertificationDecision.APPROVED
            else:
                report.certification_decision = CertificationDecision.BLOCKED
        elif report.overall_score >= 60.0:
            report.certification_decision = CertificationDecision.CONDITIONALLY_APPROVED
        else:
            report.certification_decision = CertificationDecision.IN_PROGRESS

        return report.certification_decision

    def create_readiness_checklist(self, service_name: str) -> ProductionReadinessChecklist:
        """Create a production readiness checklist with standard 12 items."""
        standard_items = [
            "has_monitoring", "has_alerting", "has_runbook", "has_backup",
            "has_dr_plan", "has_capacity_plan", "has_security_review", "has_load_test",
            "has_rollback_plan", "has_incident_playbook", "has_slo_defined", "has_error_budget"
        ]
        checklist_id = f"chk-{service_name}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        
        items = {item: False for item in standard_items}
        
        checklist = ProductionReadinessChecklist(
            checklist_id=checklist_id,
            service_name=service_name,
            items=items,
        )
        self._checklists[checklist_id] = checklist
        return checklist

    def update_checklist_item(
        self, checklist_id: str, item_name: str, value: bool
    ) -> ProductionReadinessChecklist:
        """Update an item in the checklist and re-evaluate readiness."""
        if checklist_id not in self._checklists:
            raise ValueError(f"Checklist {checklist_id} not found.")
            
        checklist = self._checklists[checklist_id]
        if item_name in checklist.items:
            checklist.items[item_name] = value
            
        checklist.overall_ready = all(checklist.items.values())
        return checklist

    def evaluate_readiness(self, checklist_id: str) -> Dict[str, Any]:
        """Evaluate readiness statistics for a given checklist."""
        if checklist_id not in self._checklists:
            raise ValueError(f"Checklist {checklist_id} not found.")
            
        checklist = self._checklists[checklist_id]
        total_items = len(checklist.items)
        passed_items = sum(1 for v in checklist.items.values() if v)
        missing_items = [k for k, v in checklist.items.items() if not v]
        ready_percentage = (passed_items / max(total_items, 1)) * 100.0
        
        return {
            "total_items": total_items,
            "passed_items": passed_items,
            "missing_items": missing_items,
            "ready_percentage": ready_percentage,
            "overall_ready": checklist.overall_ready,
        }

    def get_dimension_gap_report(self, dimension: MaturityDimension) -> Dict[str, Any]:
        """Aggregate gaps and blockers for a dimension across all assessments."""
        all_gaps = []
        all_blockers = []
        for report in self._reports.values():
            for a in report.dimensions:
                if a.dimension == dimension:
                    all_gaps.extend(a.gaps)
                    all_blockers.extend(a.blockers)
                    
        return {
            "dimension": dimension,
            "total_gaps": len(all_gaps),
            "total_blockers": len(all_blockers),
            "unique_gaps": list(set(all_gaps)),
            "unique_blockers": list(set(all_blockers)),
        }

    def compare_assessments(self, report_id_a: str, report_id_b: str) -> Dict[str, Any]:
        """Compare two reports."""
        if report_id_a not in self._reports or report_id_b not in self._reports:
            raise ValueError("One or both reports not found.")
            
        report_a = self._reports[report_id_a]
        report_b = self._reports[report_id_b]
        
        deltas = {}
        improved = []
        regressed = []
        
        a_scores = {a.dimension: a.score for a in report_a.dimensions}
        b_scores = {a.dimension: a.score for a in report_b.dimensions}
        
        all_dims = set(a_scores.keys()).union(set(b_scores.keys()))
        for dim in all_dims:
            score_a = a_scores.get(dim, 0.0)
            score_b = b_scores.get(dim, 0.0)
            delta = score_b - score_a
            deltas[dim] = delta
            if delta > 0:
                improved.append(dim)
            elif delta < 0:
                regressed.append(dim)
                
        return {
            "overall_score_delta": report_b.overall_score - report_a.overall_score,
            "dimension_deltas": deltas,
            "improved_dimensions": improved,
            "regressed_dimensions": regressed,
        }

    def get_certification_summary(self) -> Dict[str, Any]:
        """Get summary statistics across all reports."""
        total_reports = len(self._reports)
        by_decision = {}
        total_score = 0.0
        all_blockers = []
        
        for r in self._reports.values():
            decision = r.certification_decision.value
            by_decision[decision] = by_decision.get(decision, 0) + 1
            total_score += r.overall_score
            for a in r.dimensions:
                all_blockers.extend(a.blockers)
                
        average_score = total_score / max(total_reports, 1)
        
        blocker_counts = {}
        for b in all_blockers:
            blocker_counts[b] = blocker_counts.get(b, 0) + 1
            
        most_common_blockers = sorted(
            blocker_counts.items(), key=lambda x: x[1], reverse=True
        )[:5]
        
        return {
            "total_reports": total_reports,
            "by_decision": by_decision,
            "average_score": average_score,
            "most_common_blockers": most_common_blockers,
        }
