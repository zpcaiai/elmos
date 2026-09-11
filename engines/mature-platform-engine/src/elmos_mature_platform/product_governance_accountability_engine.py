"""Product Governance Accountability Engine (Batch 45 - Skill 1492).

Enforces RACI-governed product decision rights (Responsible, Accountable, Consulted, Informed),
formal executive sign-off trails, policy overrides, and architectural waivers.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from .types import (
    GovernanceDecisionType,
    GovernanceSignoffRecord,
    ProductGovernanceDecision,
    RaciRoleType,
)


class ProductGovernanceAccountabilityEngine:
    """Formal RACI product governance and decision rights enforcement engine."""

    def __init__(self) -> None:
        self._decisions: Dict[str, ProductGovernanceDecision] = {}

    def propose_decision(self, decision: ProductGovernanceDecision) -> str:
        """Propose a formal product architecture or governance decision."""
        if not decision.title:
            raise ValueError("title is required")

        if not decision.accountable_executive:
            raise ValueError("accountable_executive is required for governance accountability")

        if not decision.decision_id:
            decision.decision_id = f"govdec-{uuid.uuid4().hex[:8]}"

        self._decisions[decision.decision_id] = decision
        return decision.decision_id

    def record_signoff(
        self, decision_id: str, signoff: GovernanceSignoffRecord
    ) -> ProductGovernanceDecision:
        """Record a formal RACI stakeholder sign-off on a decision."""
        decision = self._decisions.get(decision_id)
        if not decision:
            raise ValueError(f"Governance decision not found: {decision_id}")

        if not signoff.signoff_id:
            signoff.signoff_id = f"sign-{uuid.uuid4().hex[:8]}"

        if not signoff.decision_id:
            signoff.decision_id = decision_id

        if not signoff.timestamp:
            signoff.timestamp = datetime.now(timezone.utc).isoformat()

        # Update existing signoff by same stakeholder if present, else append
        existing_idx = None
        for i, s in enumerate(decision.signoffs):
            if s.stakeholder_name == signoff.stakeholder_name and s.raci_role == signoff.raci_role:
                existing_idx = i
                break

        if existing_idx is not None:
            decision.signoffs[existing_idx] = signoff
        else:
            decision.signoffs.append(signoff)

        # Re-evaluate approval
        self.evaluate_approval(decision_id)
        return decision

    def evaluate_approval(self, decision_id: str) -> bool:
        """Evaluate if the decision satisfies all RACI approval criteria."""
        decision = self._decisions.get(decision_id)
        if not decision:
            raise ValueError(f"Governance decision not found: {decision_id}")

        # Check for any explicit rejection from any stakeholder
        has_rejection = any(not s.approved for s in decision.signoffs)
        if has_rejection:
            decision.is_approved = False
            return False

        # Must have signoff from the ACCOUNTABLE executive that is approved
        accountable_signoffs = [
            s
            for s in decision.signoffs
            if s.raci_role == RaciRoleType.ACCOUNTABLE
            and s.stakeholder_name == decision.accountable_executive
            and s.approved
        ]

        if not accountable_signoffs:
            decision.is_approved = False
            return False

        # Any RESPONSIBLE signoffs must be approved
        responsible_signoffs = [
            s for s in decision.signoffs if s.raci_role == RaciRoleType.RESPONSIBLE
        ]
        if responsible_signoffs and not all(s.approved for s in responsible_signoffs):
            decision.is_approved = False
            return False

        decision.is_approved = True
        if not decision.decided_at:
            decision.decided_at = datetime.now(timezone.utc).isoformat()
        return True

    def get_decision(self, decision_id: str) -> Optional[ProductGovernanceDecision]:
        """Retrieve governance decision details."""
        return self._decisions.get(decision_id)

    def get_pending_decisions(self) -> List[ProductGovernanceDecision]:
        """Retrieve all pending, non-approved decisions."""
        return [d for d in self._decisions.values() if not d.is_approved]

    def get_governance_report(self) -> Dict[str, Any]:
        """Generate platform product governance accountability report."""
        total = len(self._decisions)
        approved = sum(1 for d in self._decisions.values() if d.is_approved)
        pending = total - approved

        by_type: Dict[str, int] = {t.value: 0 for t in GovernanceDecisionType}
        total_signoffs = 0

        for d in self._decisions.values():
            by_type[d.decision_type.value] += 1
            total_signoffs += len(d.signoffs)

        return {
            "total_decisions": total,
            "approved_decisions": approved,
            "pending_decisions": pending,
            "approval_rate_pct": round(approved / total * 100.0, 2) if total > 0 else 0.0,
            "decisions_by_type": by_type,
            "total_signoffs_recorded": total_signoffs,
        }
