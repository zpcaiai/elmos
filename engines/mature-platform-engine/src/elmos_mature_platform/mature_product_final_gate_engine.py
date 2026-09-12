from typing import Dict, List, Any
from datetime import datetime, timezone
import uuid

from .types import (
    FinalGateDecision,
    FinalGateDimensionAssessment,
    FinalGateDimensionAssessment as DimensionAssessment,
    FinalGateMaturityDimension as MaturityDimension,
    DimensionVerdict
)

class MatureProductFinalGateEngine:
    """Engine for managing the final maturity gate before releasing mature platform components."""
    
    def __init__(self) -> None:
        self._gates: Dict[str, FinalGateDecision] = {}
        
    def create_gate(self, gate: FinalGateDecision) -> str:
        """Create a new gate review."""
        if not gate.gate_id:
            gate.gate_id = str(uuid.uuid4())
        self._gates[gate.gate_id] = gate
        return gate.gate_id
        
    def set_mandatory_dimensions(self, gate_id: str, dimensions: List[MaturityDimension]) -> FinalGateDecision:
        """Set which dimensions are mandatory for this gate."""
        if gate_id not in self._gates:
            raise ValueError(f"Gate {gate_id} not found")
        
        gate = self._gates[gate_id]
        gate.mandatory_dimensions = [dim.value if hasattr(dim, 'value') else dim for dim in dimensions]
        return gate
        
    def submit_assessment(self, gate_id: str, assessment: DimensionAssessment) -> FinalGateDecision:
        """Submit a dimension assessment."""
        if gate_id not in self._gates:
            raise ValueError(f"Gate {gate_id} not found")
            
        gate = self._gates[gate_id]
        dim_str = assessment.dimension.value if hasattr(assessment.dimension, 'value') else assessment.dimension
        gate.assessments[dim_str] = assessment
        return gate
        
    def evaluate_gate(self, gate_id: str) -> FinalGateDecision:
        """
        Compute overall verdict: 
        PASS if all mandatory PASS, 
        CONDITIONAL if any CONDITIONAL but no FAIL in mandatory, 
        FAIL if any mandatory FAIL
        """
        if gate_id not in self._gates:
            raise ValueError(f"Gate {gate_id} not found")
            
        gate = self._gates[gate_id]
        
        has_conditional = False
        has_fail = False
        all_mandatory_assessed = True
        
        for mand_dim in gate.mandatory_dimensions:
            dim_str = mand_dim.value if hasattr(mand_dim, 'value') else mand_dim
            if dim_str not in gate.assessments:
                all_mandatory_assessed = False
                continue
                
            assessment = gate.assessments[dim_str]
            if assessment.verdict == DimensionVerdict.FAIL:
                has_fail = True
            elif assessment.verdict == DimensionVerdict.CONDITIONAL_PASS:
                has_conditional = True
            elif assessment.verdict == DimensionVerdict.NOT_EVALUATED:
                all_mandatory_assessed = False
                
        if has_fail or not all_mandatory_assessed:
            gate.overall_verdict = DimensionVerdict.FAIL
        elif has_conditional:
            gate.overall_verdict = DimensionVerdict.CONDITIONAL_PASS
        else:
            gate.overall_verdict = DimensionVerdict.PASS
            
        return gate
        
    def authorize_release(self, gate_id: str, decision_maker: str) -> FinalGateDecision:
        """Only if overall is PASS or CONDITIONAL_PASS."""
        if gate_id not in self._gates:
            raise ValueError(f"Gate {gate_id} not found")
            
        gate = self._gates[gate_id]
        
        if gate.overall_verdict not in [DimensionVerdict.PASS, DimensionVerdict.CONDITIONAL_PASS]:
            raise ValueError(f"Cannot authorize release for gate with verdict {gate.overall_verdict}")
            
        gate.release_authorized = True
        gate.decision_maker = decision_maker
        gate.decision_made_at = datetime.now(timezone.utc).isoformat()
        
        return gate
        
    def get_blocking_dimensions(self, gate_id: str) -> List[DimensionAssessment]:
        """Failed mandatory dimensions."""
        if gate_id not in self._gates:
            raise ValueError(f"Gate {gate_id} not found")
            
        gate = self._gates[gate_id]
        blockers = []
        
        for mand_dim in gate.mandatory_dimensions:
            dim_str = mand_dim.value if hasattr(mand_dim, 'value') else mand_dim
            if dim_str in gate.assessments:
                assessment = gate.assessments[dim_str]
                if assessment.verdict == DimensionVerdict.FAIL:
                    blockers.append(assessment)
                    
        return blockers
        
    def get_conditions(self, gate_id: str) -> List[str]:
        """All conditions across dimensions."""
        if gate_id not in self._gates:
            raise ValueError(f"Gate {gate_id} not found")
            
        gate = self._gates[gate_id]
        conditions = []
        
        for assessment in gate.assessments.values():
            if assessment.conditions:
                conditions.extend(assessment.conditions)
                
        return conditions
        
    def get_readiness_score(self, gate_id: str) -> float:
        """Weighted avg of dimension scores (for now just simple avg of assessed)."""
        if gate_id not in self._gates:
            raise ValueError(f"Gate {gate_id} not found")
            
        gate = self._gates[gate_id]
        if not gate.assessments:
            return 0.0
            
        total_score = sum(assessment.score for assessment in gate.assessments.values())
        return total_score / len(gate.assessments)
        
    def compare_gates(self, gate_id_a: str, gate_id_b: str) -> Dict[str, Dict[str, float]]:
        """Compare dimension scores between versions."""
        if gate_id_a not in self._gates or gate_id_b not in self._gates:
            raise ValueError("One or both gates not found")
            
        gate_a = self._gates[gate_id_a]
        gate_b = self._gates[gate_id_b]
        
        comparison = {}
        all_dims = set(gate_a.assessments.keys()) | set(gate_b.assessments.keys())
        
        for dim in all_dims:
            score_a = gate_a.assessments[dim].score if dim in gate_a.assessments else 0.0
            score_b = gate_b.assessments[dim].score if dim in gate_b.assessments else 0.0
            comparison[dim] = {
                gate_id_a: score_a,
                gate_id_b: score_b,
                "diff": score_b - score_a
            }
            
        return comparison
        
    def get_gate_report(self, gate_id: str) -> Dict[str, Any]:
        """Full report with all dimensions, scores, blockers."""
        if gate_id not in self._gates:
            raise ValueError(f"Gate {gate_id} not found")
            
        gate = self._gates[gate_id]
        
        report = {
            "gate_id": gate.gate_id,
            "product_name": gate.product_name,
            "version": gate.version,
            "overall_verdict": gate.overall_verdict.value if hasattr(gate.overall_verdict, 'value') else gate.overall_verdict,
            "readiness_score": self.get_readiness_score(gate_id),
            "release_authorized": gate.release_authorized,
            "assessments": {},
            "blockers": [b.dimension.value if hasattr(b.dimension, 'value') else b.dimension for b in self.get_blocking_dimensions(gate_id)],
            "conditions": self.get_conditions(gate_id)
        }
        
        for dim, assessment in gate.assessments.items():
            report["assessments"][dim] = {
                "verdict": assessment.verdict.value if hasattr(assessment.verdict, 'value') else assessment.verdict,
                "score": assessment.score
            }
            
        return report
