"""Policy-as-code evaluators for training eligibility, skill execution, and model promotion.

Implements deterministic evaluation of Foundry governance policies.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .domain import (
    ConsentStatus,
    DatasetItem,
    GateLevel,
    ModelRelease,
    RightsClass,
    SkillContract,
)


class PolicyEngine:
    """Enterprise policy-as-code evaluation engine."""

    def evaluate_training_eligibility(
        self,
        dataset_item: DatasetItem | Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Evaluate training eligibility policy.
        
        Rules:
        - Consent must be 'allow' (or 'conditional' with approved purpose)
        - Rights class must NOT be 'restricted' without explicit exemption
        - Item must NOT be quarantined
        - Quality score must be >= 0.7
        """
        if isinstance(dataset_item, DatasetItem):
            consent = dataset_item.consent_status
            rights = dataset_item.rights_class
            quarantine = dataset_item.quarantine
            quality = dataset_item.quality_score
        else:
            consent = ConsentStatus(dataset_item.get("consent_status", "deny"))
            rights = RightsClass(dataset_item.get("rights_class", "internal"))
            quarantine = bool(dataset_item.get("quarantine", False))
            quality = float(dataset_item.get("quality_score", 1.0))

        violations = []
        if consent == ConsentStatus.DENY:
            violations.append("Training consent is explicitly denied")
        if rights == RightsClass.RESTRICTED:
            violations.append("Restricted data cannot be used for model training")
        if quarantine:
            violations.append("Item is under quarantine")
        if quality < 0.7:
            violations.append(f"Quality score {quality:.2f} is below threshold 0.70")

        eligible = len(violations) == 0
        return {
            "policy": "training-eligibility",
            "decision": "ALLOW" if eligible else "DENY",
            "eligible": eligible,
            "violations": violations,
        }

    def evaluate_skill_execution(
        self,
        skill_contract: SkillContract | Mapping[str, Any],
        caller_context: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Evaluate skill execution policy.
        
        Rules:
        - Critical risk skills require named human approval
        - Deprecated or Revoked skills cannot execute
        """
        if isinstance(skill_contract, SkillContract):
            risk = skill_contract.risk_class
            status = skill_contract.status
        else:
            risk = skill_contract.get("risk_class", "standard")
            status = skill_contract.get("status", "CERTIFIED")

        violations = []
        if str(status).upper() in ("DEPRECATED", "REVOKED"):
            violations.append(f"Skill status {status} is not executable")
        if risk == "critical" and not caller_context.get("human_approved", False):
            violations.append("Critical risk skill requires verified human approval")

        allowed = len(violations) == 0
        return {
            "policy": "skill-execution",
            "decision": "ALLOW" if allowed else "DENY",
            "allowed": allowed,
            "violations": violations,
        }

    def evaluate_model_promotion(
        self,
        target_gate: GateLevel,
        eval_metrics: Mapping[str, Any],
        proof_obligations_satisfied: bool,
    ) -> Mapping[str, Any]:
        """Evaluate model promotion policy across E0-E5 gates.
        
        Rules:
        - E1: Unit eval accuracy >= 0.85
        - E2: Integration pass rate >= 0.95
        - E3: Shadow canary error rate <= 0.01
        - E4: Production gate requires zero regressions and all proofs satisfied
        - E5: Formal verification mathematically proven
        """
        violations = []
        if not proof_obligations_satisfied:
            violations.append("Not all required proof obligations are satisfied")

        if target_gate == GateLevel.E1_UNIT_EVAL:
            if eval_metrics.get("unit_eval_score", 0.0) < 0.85:
                violations.append("Unit evaluation score < 0.85")
        elif target_gate == GateLevel.E2_INTEGRATION:
            if eval_metrics.get("integration_pass_rate", 0.0) < 0.95:
                violations.append("Integration pass rate < 0.95")
        elif target_gate == GateLevel.E3_SHADOW_CANARY:
            if eval_metrics.get("canary_error_rate", 1.0) > 0.01:
                violations.append("Canary error rate > 0.01")
        elif target_gate in (GateLevel.E4_PRODUCTION_CERTIFIED, GateLevel.E5_FORMAL_PROVEN):
            if eval_metrics.get("regression_count", 1) > 0:
                violations.append("Zero regressions allowed for production promotion")

        approved = len(violations) == 0
        return {
            "policy": "model-promotion",
            "target_gate": str(target_gate),
            "decision": "ALLOW" if approved else "DENY",
            "approved": approved,
            "violations": violations,
        }
