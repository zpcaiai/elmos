from typing import List, Dict, Optional
from datetime import datetime
from elmos_mature_platform.types import (
    ReadinessLevel,
    UpgradeCheckCategory,
    UpgradeCheck,
    UpgradeReadinessAssessment
)

class CustomerUpgradeReadinessEngine:
    def __init__(self):
        self.assessments: Dict[str, UpgradeReadinessAssessment] = {}
        self.checks: Dict[str, UpgradeCheck] = {}

    def create_assessment(self, assessment: UpgradeReadinessAssessment) -> str:
        """Create a new upgrade readiness assessment."""
        if assessment.assessment_id in self.assessments:
            raise ValueError(f"Assessment {assessment.assessment_id} already exists")
        self.assessments[assessment.assessment_id] = assessment
        return assessment.assessment_id

    def add_check(self, check: UpgradeCheck) -> str:
        """Add a new upgrade check to the system."""
        self.checks[check.check_id] = check
        return check.check_id

    def link_check(self, assessment_id: str, check_id: str) -> UpgradeReadinessAssessment:
        """Link an existing check to an assessment."""
        if assessment_id not in self.assessments:
            raise ValueError(f"Assessment {assessment_id} not found")
        if check_id not in self.checks:
            raise ValueError(f"Check {check_id} not found")
            
        assessment = self.assessments[assessment_id]
        if check_id not in assessment.checks:
            assessment.checks.append(check_id)
        return assessment

    def run_check(self, check_id: str, passed: bool) -> UpgradeCheck:
        """Update the result of an upgrade check."""
        if check_id not in self.checks:
            raise ValueError(f"Check {check_id} not found")
            
        check = self.checks[check_id]
        check.passed = passed
        return check

    def evaluate_readiness(self, assessment_id: str) -> UpgradeReadinessAssessment:
        """Compute the readiness of an assessment based on its linked checks."""
        if assessment_id not in self.assessments:
            raise ValueError(f"Assessment {assessment_id} not found")
            
        assessment = self.assessments[assessment_id]
        if not assessment.checks:
            assessment.readiness = ReadinessLevel.NOT_READY
            assessment.overall_score = 0.0
            return assessment

        total_checks = len(assessment.checks)
        passed_checks = 0
        has_blocking_failure = False
        has_non_blocking_failure = False
        total_effort = 0.0

        for check_id in assessment.checks:
            if check_id not in self.checks:
                continue
            check = self.checks[check_id]
            if check.passed:
                passed_checks += 1
            else:
                total_effort += check.effort_hours
                if check.blocking:
                    has_blocking_failure = True
                else:
                    has_non_blocking_failure = True

        assessment.overall_score = (passed_checks / total_checks) * 100.0
        assessment.total_effort_hours = total_effort
        
        if has_blocking_failure:
            assessment.readiness = ReadinessLevel.BLOCKED
        elif has_non_blocking_failure:
            assessment.readiness = ReadinessLevel.READY_WITH_ACTIONS
        else:
            assessment.readiness = ReadinessLevel.READY
            
        return assessment

    def get_remediation_plan(self, assessment_id: str) -> List[Dict]:
        """Get a plan consisting of failed checks along with remediation and effort."""
        if assessment_id not in self.assessments:
            raise ValueError(f"Assessment {assessment_id} not found")
            
        plan = []
        assessment = self.assessments[assessment_id]
        for check_id in assessment.checks:
            if check_id in self.checks:
                check = self.checks[check_id]
                if not check.passed:
                    plan.append({
                        "check_id": check.check_id,
                        "name": check.name,
                        "remediation": check.remediation,
                        "effort_hours": check.effort_hours,
                        "blocking": check.blocking
                    })
        return plan

    def get_total_effort(self, assessment_id: str) -> float:
        """Sum the effort_hours for all failed checks linked to an assessment."""
        if assessment_id not in self.assessments:
            raise ValueError(f"Assessment {assessment_id} not found")
            
        return self.evaluate_readiness(assessment_id).total_effort_hours

    def get_blocking_issues(self, assessment_id: str) -> List[UpgradeCheck]:
        """Return the list of failed blocking checks."""
        if assessment_id not in self.assessments:
            raise ValueError(f"Assessment {assessment_id} not found")
            
        issues = []
        assessment = self.assessments[assessment_id]
        for check_id in assessment.checks:
            if check_id in self.checks:
                check = self.checks[check_id]
                if not check.passed and check.blocking:
                    issues.append(check)
        return issues

    def compare_versions(self, assessment_a_id: str, assessment_b_id: str) -> Dict:
        """Compare readiness between two different version assessments."""
        if assessment_a_id not in self.assessments:
            raise ValueError(f"Assessment {assessment_a_id} not found")
        if assessment_b_id not in self.assessments:
            raise ValueError(f"Assessment {assessment_b_id} not found")
            
        a = self.evaluate_readiness(assessment_a_id)
        b = self.evaluate_readiness(assessment_b_id)
        
        return {
            "version_a": a.target_version,
            "version_b": b.target_version,
            "score_diff": b.overall_score - a.overall_score,
            "effort_diff": b.total_effort_hours - a.total_effort_hours,
            "readiness_a": a.readiness.value,
            "readiness_b": b.readiness.value
        }

    def get_fleet_readiness(self, target_version: str) -> Dict:
        """Get aggregate readiness status for all customers moving to a specific version."""
        total = 0
        ready = 0
        ready_with_actions = 0
        blocked = 0
        not_ready = 0
        
        for assessment in self.assessments.values():
            if assessment.target_version == target_version:
                total += 1
                r = assessment.readiness
                if r == ReadinessLevel.READY:
                    ready += 1
                elif r == ReadinessLevel.READY_WITH_ACTIONS:
                    ready_with_actions += 1
                elif r == ReadinessLevel.BLOCKED:
                    blocked += 1
                else:
                    not_ready += 1
                    
        return {
            "target_version": target_version,
            "total_assessments": total,
            "ready": ready,
            "ready_with_actions": ready_with_actions,
            "blocked": blocked,
            "not_ready": not_ready
        }

    def get_readiness_report(self, assessment_id: str) -> Dict:
        """Generate a detailed report by category, score, blockers, and effort."""
        if assessment_id not in self.assessments:
            raise ValueError(f"Assessment {assessment_id} not found")
            
        assessment = self.evaluate_readiness(assessment_id)
        
        category_breakdown = {}
        for check_id in assessment.checks:
            if check_id in self.checks:
                check = self.checks[check_id]
                cat = check.category.value
                if cat not in category_breakdown:
                    category_breakdown[cat] = {"passed": 0, "failed": 0, "effort": 0.0}
                
                if check.passed:
                    category_breakdown[cat]["passed"] += 1
                else:
                    category_breakdown[cat]["failed"] += 1
                    category_breakdown[cat]["effort"] += check.effort_hours
                    
        return {
            "assessment_id": assessment_id,
            "customer_id": assessment.customer_id,
            "readiness": assessment.readiness.value,
            "overall_score": assessment.overall_score,
            "total_effort_hours": assessment.total_effort_hours,
            "blockers_count": len(self.get_blocking_issues(assessment_id)),
            "category_breakdown": category_breakdown
        }
