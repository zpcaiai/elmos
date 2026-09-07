"""Policy Engine and OPA/Rego Evaluator for Functional Assurance."""

from __future__ import annotations

from typing import Any, Mapping

from .domain import FunctionalAssuranceContext, ConformityDecision


class CertificationPolicyEngine:
    """Evaluates security, impartiality, and regulatory policies."""

    @staticmethod
    def evaluate_impartiality_policy(evaluator_id: str, reviewer_id: str) -> bool:
        """ISO/IEC 17065 Clause 4.2 Impartiality: Evaluator cannot review their own work."""
        if not evaluator_id or not reviewer_id:
            return False
        return evaluator_id.strip() != reviewer_id.strip()

    @staticmethod
    def evaluate_tenant_isolation_policy(context: FunctionalAssuranceContext, target_tenant: str) -> bool:
        """Strict cross-tenant denial policy."""
        return bool(context.tenant_id and target_tenant and context.tenant_id == target_tenant)

    @staticmethod
    def evaluate_assurance_level_policy(current_level: str, required_level: str) -> bool:
        """Enforce strict monotonicity on assurance levels."""
        levels = ["E0", "E1", "E2", "E3", "E4", "E5"]
        if current_level not in levels or required_level not in levels:
            return False
        return levels.index(current_level) >= levels.index(required_level)
