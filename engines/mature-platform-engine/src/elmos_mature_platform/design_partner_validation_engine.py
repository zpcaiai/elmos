from typing import Dict, List, Optional
from collections import defaultdict
from .types import (
    DesignPartner,
    PartnerEngagementStatus,
    ValidationScenario,
    ValidationOutcome,
    PartnerReport
)

class DesignPartnerValidationEngine:
    """Engine for managing design partner validations and tracking maturity."""
    
    def __init__(self):
        self._partners: Dict[str, DesignPartner] = {}
        self._scenarios: Dict[str, ValidationScenario] = {}
        
        self._status_order = {
            PartnerEngagementStatus.PROSPECT: 0,
            PartnerEngagementStatus.ONBOARDING: 1,
            PartnerEngagementStatus.ACTIVE: 2,
            PartnerEngagementStatus.FEEDBACK: 3,
            PartnerEngagementStatus.GRADUATED: 4
        }
        
    def register_partner(self, partner: DesignPartner) -> str:
        """Register a new design partner."""
        if partner.partner_id in self._partners:
            raise ValueError(f"Partner {partner.partner_id} already exists")
        self._partners[partner.partner_id] = partner
        return partner.partner_id
        
    def update_partner_status(self, partner_id: str, status: PartnerEngagementStatus) -> DesignPartner:
        """Update engagement status, ensuring forward progress except for CHURNED."""
        partner = self.get_partner(partner_id)
        
        if status == PartnerEngagementStatus.CHURNED:
            partner.engagement_status = status
            return partner
            
        current_status = partner.engagement_status
        if current_status == PartnerEngagementStatus.CHURNED:
            raise ValueError("Cannot update status of a churned partner")
            
        if self._status_order[status] <= self._status_order[current_status]:
            if status != current_status:
                raise ValueError("Cannot move backward in lifecycle")
            return partner
            
        if status == PartnerEngagementStatus.GRADUATED:
            passed_scenarios = [s for s in self._scenarios.values() 
                              if s.partner_id == partner_id and s.outcome == ValidationOutcome.PASSED]
            if not passed_scenarios:
                raise ValueError("Cannot graduate partner without at least one passed validation scenario")
                
        partner.engagement_status = status
        return partner

    def create_validation_scenario(self, scenario: ValidationScenario) -> str:
        """Create a new validation scenario for a partner."""
        if scenario.scenario_id in self._scenarios:
            raise ValueError(f"Scenario {scenario.scenario_id} already exists")
        if scenario.partner_id not in self._partners:
            raise ValueError(f"Unknown partner {scenario.partner_id}")
            
        self._scenarios[scenario.scenario_id] = scenario
        return scenario.scenario_id
        
    def record_validation_result(self, scenario_id: str, outcome: ValidationOutcome, feedback: str, hours: float) -> ValidationScenario:
        """Record the result of a validation scenario."""
        if scenario_id not in self._scenarios:
            raise ValueError(f"Scenario {scenario_id} not found")
            
        scenario = self._scenarios[scenario_id]
        scenario.outcome = outcome
        scenario.feedback = feedback
        scenario.time_to_complete_hours = hours
        
        if outcome == ValidationOutcome.PASSED:
            partner = self._partners[scenario.partner_id]
            if scenario.feature not in partner.features_validated:
                partner.features_validated.append(scenario.feature)
                
        return scenario
        
    def get_partner(self, partner_id: str) -> DesignPartner:
        """Get details for a specific partner."""
        if partner_id not in self._partners:
            raise ValueError(f"Partner {partner_id} not found")
        return self._partners[partner_id]
        
    def get_partner_scenarios(self, partner_id: str) -> List[ValidationScenario]:
        """Get all scenarios associated with a partner."""
        if partner_id not in self._partners:
            raise ValueError(f"Partner {partner_id} not found")
        return [s for s in self._scenarios.values() if s.partner_id == partner_id]
        
    def record_nps(self, partner_id: str, score: int) -> DesignPartner:
        """Record NPS score for a partner (-100 to 100)."""
        if not (-100 <= score <= 100):
            raise ValueError("NPS score must be between -100 and 100")
            
        partner = self.get_partner(partner_id)
        partner.nps_score = score
        return partner
        
    def add_feature_request(self, partner_id: str, feature: str):
        """Add a requested feature for a partner."""
        partner = self.get_partner(partner_id)
        if feature not in partner.features_requested:
            partner.features_requested.append(feature)
            
    def get_feature_demand(self) -> Dict[str, int]:
        """Calculate feature request demand across all partners."""
        demand = defaultdict(int)
        for partner in self._partners.values():
            for feature in partner.features_requested:
                demand[feature] += 1
        return dict(demand)
        
    def get_validation_coverage(self, feature: str) -> Dict:
        """Get validation coverage metrics for a specific feature."""
        relevant_scenarios = [s for s in self._scenarios.values() if s.feature == feature]
        if not relevant_scenarios:
            return {"partners_validated": 0, "pass_rate": 0.0}
            
        passed = sum(1 for s in relevant_scenarios if s.outcome == ValidationOutcome.PASSED)
        unique_partners = len(set(s.partner_id for s in relevant_scenarios))
        
        pass_rate = passed / len(relevant_scenarios)
        return {
            "partners_validated": unique_partners,
            "pass_rate": pass_rate
        }
        
    def get_partner_report(self) -> PartnerReport:
        """Generate a comprehensive report across all partners."""
        total = len(self._partners)
        if total == 0:
            return PartnerReport()
            
        active = sum(1 for p in self._partners.values() if p.engagement_status == PartnerEngagementStatus.ACTIVE)
        graduated = sum(1 for p in self._partners.values() if p.engagement_status == PartnerEngagementStatus.GRADUATED)
        
        nps_scores = [p.nps_score for p in self._partners.values()]
        avg_nps = sum(nps_scores) / total if nps_scores else 0.0
        
        demand = self.get_feature_demand()
        top_features = [{"feature": f, "requests": count} for f, count in sorted(demand.items(), key=lambda x: x[1], reverse=True)]
        
        all_blockers = []
        for p in self._partners.values():
            all_blockers.extend(p.blockers)
            
        total_scenarios = len(self._scenarios)
        passed_scenarios = sum(1 for s in self._scenarios.values() if s.outcome == ValidationOutcome.PASSED)
        pass_rate = (passed_scenarios / total_scenarios) if total_scenarios > 0 else 0.0
        
        return PartnerReport(
            total_partners=total,
            active_count=active,
            graduated_count=graduated,
            average_nps=avg_nps,
            top_requested_features=top_features,
            validation_pass_rate=pass_rate,
            blockers=list(set(all_blockers))
        )
        
    def assess_product_readiness(self) -> PartnerReport:
        """Assess overall product readiness: needs min 3 graduated partners, >=70% validation pass rate."""
        report = self.get_partner_report()
        if report.graduated_count < 3:
            raise ValueError(f"Product not ready: Need 3 graduated partners, have {report.graduated_count}")
        if report.validation_pass_rate < 0.70:
            raise ValueError(f"Product not ready: Pass rate {report.validation_pass_rate} < 0.70")
        return report
