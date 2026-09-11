"""Target Maintainability Certification Engine (Batch 45 - Skill 1483).

Assesses, grades, and certifies the code maintainability of migrated target
codebases against complexity limits, code smell standards, and quality gates.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    MaintainabilityMetricType,
    MaintainabilityRating,
    MaintainabilitySmellFinding,
    TargetCodeMetric,
    TargetMaintainabilityCertification,
)


class TargetMaintainabilityCertificationEngine:
    """Evaluates and certifies target code maintainability."""

    GRADE_HIERARCHY = {
        MaintainabilityRating.GRADE_A: 4,
        MaintainabilityRating.GRADE_B: 3,
        MaintainabilityRating.GRADE_C: 2,
        MaintainabilityRating.GRADE_D: 1,
        MaintainabilityRating.UNACCEPTABLE: 0,
    }

    def __init__(self) -> None:
        self._certs: Dict[str, TargetMaintainabilityCertification] = {}

    def create_certification_assessment(
        self, project_id: str, repo_name: str, target_lang: str
    ) -> str:
        """Initialize a new maintainability assessment for a project."""
        if not project_id or not repo_name:
            raise ValueError("project_id and repo_name are required")

        cert_id = f"maint-{uuid.uuid4().hex[:8]}"
        cert = TargetMaintainabilityCertification(
            cert_id=cert_id,
            project_id=project_id,
            target_repo_name=repo_name,
            target_language=target_lang,
            overall_grade=MaintainabilityRating.GRADE_C,
        )
        self._certs[cert_id] = cert
        return cert_id

    def record_code_metric(
        self, cert_id: str, metric: TargetCodeMetric
    ) -> TargetMaintainabilityCertification:
        """Record a code complexity or quality metric."""
        cert = self._certs.get(cert_id)
        if not cert:
            raise ValueError(f"Certification record not found: {cert_id}")

        if not metric.metric_id:
            metric.metric_id = f"metric-{uuid.uuid4().hex[:8]}"

        # Determine pass/fail based on metric semantics
        if metric.metric_type in (
            MaintainabilityMetricType.CYCLOMATIC_COMPLEXITY,
            MaintainabilityMetricType.COGNITIVE_COMPLEXITY,
            MaintainabilityMetricType.DUPLICATION_PERCENTAGE,
            MaintainabilityMetricType.TECHNICAL_DEBT_RATIO,
            MaintainabilityMetricType.SMELL_DENSITY,
        ):
            metric.passed = (metric.value <= metric.acceptable_limit)
        else:  # MAINTAINABILITY_INDEX, COMMENT_DENSITY
            metric.passed = (metric.value >= metric.acceptable_limit)

        cert.metrics.append(metric)
        return cert

    def record_smell_finding(
        self, cert_id: str, finding: MaintainabilitySmellFinding
    ) -> TargetMaintainabilityCertification:
        """Record a detected architectural or code smell finding."""
        cert = self._certs.get(cert_id)
        if not cert:
            raise ValueError(f"Certification record not found: {cert_id}")

        if not finding.finding_id:
            finding.finding_id = f"smell-{uuid.uuid4().hex[:8]}"

        cert.smell_findings.append(finding)
        return cert

    def compute_maintainability_grade(
        self, cert_id: str
    ) -> TargetMaintainabilityCertification:
        """Compute maintainability grade based on recorded metrics and smells."""
        cert = self._certs.get(cert_id)
        if not cert:
            raise ValueError(f"Certification record not found: {cert_id}")

        if not cert.metrics:
            cert.overall_grade = MaintainabilityRating.UNACCEPTABLE
            cert.remediation_backlog = ["No metrics provided"]
            return cert

        total_weight = sum(m.weight for m in cert.metrics)
        passed_weight = sum(m.weight for m in cert.metrics if m.passed)
        pass_rate = (passed_weight / total_weight) if total_weight > 0 else 0.0

        mi_metrics = [
            m.value
            for m in cert.metrics
            if m.metric_type == MaintainabilityMetricType.MAINTAINABILITY_INDEX
        ]
        mi_avg = (sum(mi_metrics) / len(mi_metrics)) if mi_metrics else 80.0
        cert.maintainability_index_avg = round(mi_avg, 2)

        critical_smells = sum(
            1 for s in cert.smell_findings if s.severity.lower() == "critical"
        )

        # Grade grading logic
        if critical_smells > 2 or pass_rate < 0.60:
            grade = MaintainabilityRating.UNACCEPTABLE
        elif pass_rate >= 0.95 and mi_avg >= 85.0 and critical_smells == 0:
            grade = MaintainabilityRating.GRADE_A
        elif pass_rate >= 0.85 and mi_avg >= 75.0 and critical_smells <= 1:
            grade = MaintainabilityRating.GRADE_B
        elif pass_rate >= 0.70 and mi_avg >= 65.0:
            grade = MaintainabilityRating.GRADE_C
        else:
            grade = MaintainabilityRating.GRADE_D

        cert.overall_grade = grade

        # Compile remediation backlog
        backlog = []
        for m in cert.metrics:
            if not m.passed:
                backlog.append(
                    f"Violated {m.metric_type.value} on {m.target_file_or_module}: {m.value} vs limit {m.acceptable_limit}"
                )
        for s in cert.smell_findings:
            if s.severity.lower() in ("critical", "major"):
                backlog.append(f"{s.severity.upper()} smell [{s.category}] at {s.location}")

        cert.remediation_backlog = backlog
        return cert

    def certify_maintainability(
        self,
        cert_id: str,
        certifier: str,
        min_grade: MaintainabilityRating = MaintainabilityRating.GRADE_B,
    ) -> TargetMaintainabilityCertification:
        """Issue formal maintainability certification if min_grade is satisfied."""
        cert = self.compute_maintainability_grade(cert_id)

        current_val = self.GRADE_HIERARCHY.get(cert.overall_grade, 0)
        target_val = self.GRADE_HIERARCHY.get(min_grade, 3)

        critical_smells = any(
            s.severity.lower() == "critical" for s in cert.smell_findings
        )

        if current_val >= target_val and not critical_smells:
            cert.is_certified = True
            cert.certified_at = datetime.now(timezone.utc).isoformat()
            cert.certifier = certifier
        else:
            cert.is_certified = False
            cert.certified_at = ""
            cert.certifier = ""

        return cert

    def get_debt_remediation_estimate(self, cert_id: str) -> Dict[str, Any]:
        """Estimate developer effort required to remediate maintainability smells."""
        cert = self._certs.get(cert_id)
        if not cert:
            raise ValueError(f"Certification record not found: {cert_id}")

        total_minutes = sum(s.remediation_effort_minutes for s in cert.smell_findings)
        severity_breakdown: Dict[str, int] = {}
        for s in cert.smell_findings:
            sev = s.severity.lower()
            severity_breakdown[sev] = severity_breakdown.get(sev, 0) + s.remediation_effort_minutes

        quick_wins = [
            {
                "finding_id": s.finding_id,
                "category": s.category,
                "location": s.location,
                "effort_minutes": s.remediation_effort_minutes,
            }
            for s in cert.smell_findings
            if s.remediation_effort_minutes <= 15
        ]

        return {
            "total_effort_minutes": total_minutes,
            "total_effort_hours": round(total_minutes / 60.0, 2),
            "severity_breakdown_minutes": severity_breakdown,
            "quick_wins_count": len(quick_wins),
            "quick_wins": quick_wins,
        }

    def compare_maintainability(
        self, cert_id_a: str, cert_id_b: str
    ) -> Dict[str, Any]:
        """Compare two maintainability assessments."""
        cert_a = self._certs.get(cert_id_a)
        cert_b = self._certs.get(cert_id_b)
        if not cert_a or not cert_b:
            raise ValueError("Both certification records must exist")

        return {
            "cert_a": {
                "repo": cert_a.target_repo_name,
                "grade": cert_a.overall_grade.value,
                "mi_avg": cert_a.maintainability_index_avg,
                "certified": cert_a.is_certified,
                "smells_count": len(cert_a.smell_findings),
            },
            "cert_b": {
                "repo": cert_b.target_repo_name,
                "grade": cert_b.overall_grade.value,
                "mi_avg": cert_b.maintainability_index_avg,
                "certified": cert_b.is_certified,
                "smells_count": len(cert_b.smell_findings),
            },
            "higher_grade": (
                cert_a.overall_grade.value
                if self.GRADE_HIERARCHY[cert_a.overall_grade] >= self.GRADE_HIERARCHY[cert_b.overall_grade]
                else cert_b.overall_grade.value
            ),
        }

    def get_language_maintainability_benchmark(self, language: str) -> Dict[str, Any]:
        """Calculate average maintainability statistics for a given target language."""
        matching = [
            c for c in self._certs.values() if c.target_language.lower() == language.lower()
        ]
        if not matching:
            return {
                "target_language": language,
                "total_assessed": 0,
                "avg_maintainability_index": 0.0,
                "certification_rate": 0.0,
            }

        total = len(matching)
        certified = sum(1 for c in matching if c.is_certified)
        avg_mi = sum(c.maintainability_index_avg for c in matching) / total

        return {
            "target_language": language,
            "total_assessed": total,
            "avg_maintainability_index": round(avg_mi, 2),
            "certification_rate": round(certified / total, 4),
        }

    def get_fleet_maintainability_report(self) -> Dict[str, Any]:
        """Return fleet-wide maintainability assessment summary."""
        total = len(self._certs)
        certified = sum(1 for c in self._certs.values() if c.is_certified)
        grade_dist: Dict[str, int] = {}
        for c in self._certs.values():
            grade_dist[c.overall_grade.value] = grade_dist.get(c.overall_grade.value, 0) + 1

        avg_mi = (
            sum(c.maintainability_index_avg for c in self._certs.values()) / total
            if total > 0
            else 0.0
        )

        return {
            "total_assessments": total,
            "certified_assessments": certified,
            "certification_rate": round(certified / total, 4) if total > 0 else 0.0,
            "average_maintainability_index": round(avg_mi, 2),
            "grade_distribution": grade_dist,
        }
