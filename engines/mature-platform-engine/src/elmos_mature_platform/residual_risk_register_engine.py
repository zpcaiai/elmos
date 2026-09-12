from typing import Dict, List, Optional
from datetime import datetime
from .types import (
    RiskSeverity,
    RiskTreatment,
    RiskStatus,
    ResidualRiskEntry,
    RiskAssessment,
    RiskWaiver
)

class ResidualRiskRegisterEngine:
    """Engine for managing residual risks for a mature product."""

    def __init__(self) -> None:
        self._risks: Dict[str, ResidualRiskEntry] = {}
        self._waivers: Dict[str, RiskWaiver] = {}

    def register_risk(self, risk: ResidualRiskEntry) -> str:
        """Register a new risk and auto-compute risk_score."""
        if risk.risk_id in self._risks:
            raise ValueError(f"Risk {risk.risk_id} already exists")
        
        risk.risk_score = risk.likelihood * risk.impact_score
        self._risks[risk.risk_id] = risk
        return risk.risk_id

    def update_risk(self, risk_id: str, **kwargs) -> ResidualRiskEntry:
        """Update risk fields."""
        if risk_id not in self._risks:
            raise ValueError(f"Risk {risk_id} not found")
        
        risk = self._risks[risk_id]
        
        for k, v in kwargs.items():
            if hasattr(risk, k):
                setattr(risk, k, v)
                
        # Recompute risk_score if likelihood or impact_score changed
        if "likelihood" in kwargs or "impact_score" in kwargs:
            risk.risk_score = risk.likelihood * risk.impact_score
            
        return risk

    def accept_risk(self, risk_id: str, accepted_by: str, justification: str) -> ResidualRiskEntry:
        """Accept a risk (requires justification, sets status=ACCEPTED)."""
        if risk_id not in self._risks:
            raise ValueError(f"Risk {risk_id} not found")
            
        if not justification:
            raise ValueError("Accepting a risk requires a justification")
            
        risk = self._risks[risk_id]
        
        if risk.severity == RiskSeverity.CRITICAL:
            # Check for active waiver
            has_waiver = any(
                w.risk_id == risk_id and w.expires_at > datetime.now().isoformat()
                for w in self._waivers.values()
            )
            if not has_waiver:
                raise PermissionError("CRITICAL risks cannot be accepted without an active waiver")
                
        risk.status = RiskStatus.ACCEPTED
        risk.accepted_by = accepted_by
        risk.acceptance_justification = justification
        risk.treatment = RiskTreatment.ACCEPT
        return risk

    def escalate_risk(self, risk_id: str, reason: str) -> ResidualRiskEntry:
        """Escalate a risk."""
        if risk_id not in self._risks:
            raise ValueError(f"Risk {risk_id} not found")
            
        risk = self._risks[risk_id]
        risk.status = RiskStatus.ESCALATED
        # Optionally store the reason in a list of notes/history if there was a field, but we can just update status
        return risk

    def close_risk(self, risk_id: str) -> ResidualRiskEntry:
        """Close a risk (only if mitigated or accepted)."""
        if risk_id not in self._risks:
            raise ValueError(f"Risk {risk_id} not found")
            
        risk = self._risks[risk_id]
        if risk.treatment not in (RiskTreatment.MITIGATE, RiskTreatment.ACCEPT) or risk.status not in (RiskStatus.MITIGATING, RiskStatus.ACCEPTED):
            # A risk could also just be closed if it's already mitigated or accepted.
            pass # We'll enforce that the risk's treatment is mitigate or accept, and it has some resolution.
            
        if risk.status not in (RiskStatus.MITIGATING, RiskStatus.ACCEPTED, RiskStatus.CLOSED):
             raise ValueError("Risk must be mitigated or accepted before it can be closed")
             
        risk.status = RiskStatus.CLOSED
        return risk

    def grant_waiver(self, waiver: RiskWaiver) -> str:
        """Grant a risk waiver."""
        if waiver.risk_id not in self._risks:
            raise ValueError(f"Risk {waiver.risk_id} not found")
            
        if waiver.waiver_id in self._waivers:
            raise ValueError(f"Waiver {waiver.waiver_id} already exists")
            
        self._waivers[waiver.waiver_id] = waiver
        return waiver.waiver_id

    def assess_release_readiness(self, assessment_id: str) -> RiskAssessment:
        """Assess: block if any CRITICAL/HIGH open risks without waiver."""
        critical_count = 0
        high_count = 0
        accepted_count = 0
        total_risks = len(self._risks)
        overall_score = 0.0
        blockers = []
        
        now_iso = datetime.now().isoformat()
        
        for risk in self._risks.values():
            overall_score += risk.risk_score
            
            if risk.status == RiskStatus.ACCEPTED:
                accepted_count += 1
                
            if risk.severity == RiskSeverity.CRITICAL:
                critical_count += 1
            elif risk.severity == RiskSeverity.HIGH:
                high_count += 1
                
            # Block if open CRITICAL/HIGH without active waiver
            if risk.status in (RiskStatus.OPEN, RiskStatus.MITIGATING, RiskStatus.ESCALATED):
                if risk.severity in (RiskSeverity.CRITICAL, RiskSeverity.HIGH):
                    has_waiver = any(
                        w.risk_id == risk.risk_id and w.expires_at > now_iso
                        for w in self._waivers.values()
                    )
                    if not has_waiver:
                        blockers.append(f"Unmitigated {risk.severity.value} risk {risk.risk_id} without waiver")
                        
        release_recommended = len(blockers) == 0
        
        return RiskAssessment(
            assessment_id=assessment_id,
            assessed_at=now_iso,
            total_risks=total_risks,
            critical_count=critical_count,
            high_count=high_count,
            accepted_count=accepted_count,
            overall_risk_score=overall_score,
            release_recommended=release_recommended,
            blockers=blockers
        )

    def get_risks_by_category(self, category: str) -> List[ResidualRiskEntry]:
        """Filter risks by category."""
        return [r for r in self._risks.values() if r.category == category]

    def get_risks_by_severity(self, severity: RiskSeverity) -> List[ResidualRiskEntry]:
        """Filter risks by severity."""
        return [r for r in self._risks.values() if r.severity == severity]

    def get_risk_heatmap(self) -> Dict[str, Dict[str, int]]:
        """Matrix of severity × category counts."""
        heatmap: Dict[str, Dict[str, int]] = {
            severity.value: {} for severity in RiskSeverity
        }
        for risk in self._risks.values():
            cat = risk.category
            sev = risk.severity.value
            heatmap[sev][cat] = heatmap[sev].get(cat, 0) + 1
        return heatmap

    def get_overdue_reviews(self, current_date: str) -> List[ResidualRiskEntry]:
        """Risks past review date."""
        overdue = []
        for risk in self._risks.values():
            if risk.review_date and risk.review_date < current_date and risk.status != RiskStatus.CLOSED:
                overdue.append(risk)
        return overdue

    def get_risk_register_report(self) -> Dict:
        """Full summary: counts, scores, trends."""
        total = len(self._risks)
        status_counts = {}
        severity_counts = {}
        total_score = 0.0
        
        for risk in self._risks.values():
            status_counts[risk.status.value] = status_counts.get(risk.status.value, 0) + 1
            severity_counts[risk.severity.value] = severity_counts.get(risk.severity.value, 0) + 1
            total_score += risk.risk_score
            
        return {
            "total_risks": total,
            "status_counts": status_counts,
            "severity_counts": severity_counts,
            "average_risk_score": total_score / total if total > 0 else 0.0,
            "total_risk_score": total_score
        }
