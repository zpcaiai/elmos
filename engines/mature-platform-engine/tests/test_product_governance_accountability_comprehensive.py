"""Comprehensive test suite for ProductGovernanceAccountabilityEngine (Batch 45 - Skill 1492)."""

import unittest

from elmos_mature_platform.product_governance_accountability_engine import (
    ProductGovernanceAccountabilityEngine,
)
from elmos_mature_platform.types import (
    GovernanceDecisionType,
    GovernanceSignoffRecord,
    ProductGovernanceDecision,
    RaciRoleType,
)


class TestProductGovernanceAccountabilityComprehensive(unittest.TestCase):
    """Rigorous unit testing for ProductGovernanceAccountabilityEngine."""

    def setUp(self) -> None:
        self.engine = ProductGovernanceAccountabilityEngine()

    def test_propose_decision_success(self) -> None:
        dec = ProductGovernanceDecision(
            decision_id="dec-101",
            title="Adopt Lean SMT formal prover for banking routes",
            decision_type=GovernanceDecisionType.ARCHITECTURE_APPROVAL,
            accountable_executive="CTO Alice",
            summary="Formal verification requirement for financial services edition",
        )
        did = self.engine.propose_decision(dec)
        self.assertEqual(did, "dec-101")
        retrieved = self.engine.get_decision("dec-101")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.accountable_executive, "CTO Alice")
        self.assertFalse(retrieved.is_approved)

    def test_propose_decision_auto_generates_id(self) -> None:
        dec = ProductGovernanceDecision(
            decision_id="",
            title="Approve air-gapped deployment waiver",
            decision_type=GovernanceDecisionType.COMMERCIAL_TERMS_WAIVER,
            accountable_executive="VP Sales Bob",
        )
        did = self.engine.propose_decision(dec)
        self.assertTrue(did.startswith("govdec-"))

    def test_propose_decision_validation_errors(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.propose_decision(
                ProductGovernanceDecision(
                    decision_id="d1",
                    title="",
                    decision_type=GovernanceDecisionType.RELEASE_SIGN_OFF,
                    accountable_executive="VP",
                )
            )
        with self.assertRaises(ValueError):
            self.engine.propose_decision(
                ProductGovernanceDecision(
                    decision_id="d2",
                    title="Release v5.0",
                    decision_type=GovernanceDecisionType.RELEASE_SIGN_OFF,
                    accountable_executive="",
                )
            )

    def test_record_signoff_success(self) -> None:
        dec = ProductGovernanceDecision(
            decision_id="dec-sign",
            title="Decommission Legacy Oracle DB",
            decision_type=GovernanceDecisionType.DISASTER_RECOVERY_DECOMMISSION,
            accountable_executive="Head of Infrastructure Dan",
        )
        self.engine.propose_decision(dec)

        sign = GovernanceSignoffRecord(
            signoff_id="s1",
            decision_id="dec-sign",
            stakeholder_name="Lead DBA Charlie",
            raci_role=RaciRoleType.RESPONSIBLE,
            approved=True,
            rationale="All databases fully migrated to PostgreSQL with verified PITR",
        )
        updated_dec = self.engine.record_signoff("dec-sign", sign)
        self.assertEqual(len(updated_dec.signoffs), 1)
        self.assertEqual(updated_dec.signoffs[0].stakeholder_name, "Lead DBA Charlie")
        self.assertTrue(len(updated_dec.signoffs[0].timestamp) > 0)
        # Not approved yet because Accountable hasn't signed off
        self.assertFalse(updated_dec.is_approved)

    def test_record_signoff_auto_generates_id_and_updates_existing(self) -> None:
        dec = ProductGovernanceDecision(
            decision_id="dec-update",
            title="Security Policy Override",
            decision_type=GovernanceDecisionType.SECURITY_POLICY_OVERRIDE,
            accountable_executive="CISO Eve",
        )
        self.engine.propose_decision(dec)

        # Initial signoff with rejection
        sign1 = GovernanceSignoffRecord(
            signoff_id="",
            decision_id="dec-update",
            stakeholder_name="SecEng Frank",
            raci_role=RaciRoleType.CONSULTED,
            approved=False,
            rationale="Need mTLS clarification",
        )
        self.engine.record_signoff("dec-update", sign1)
        self.assertEqual(len(self.engine.get_decision("dec-update").signoffs), 1)

        # Re-sign with approval after clarification
        sign2 = GovernanceSignoffRecord(
            signoff_id="",
            decision_id="dec-update",
            stakeholder_name="SecEng Frank",
            raci_role=RaciRoleType.CONSULTED,
            approved=True,
            rationale="mTLS clarified and verified",
        )
        self.engine.record_signoff("dec-update", sign2)
        # Should update existing record, not duplicate
        self.assertEqual(len(self.engine.get_decision("dec-update").signoffs), 1)
        self.assertTrue(self.engine.get_decision("dec-update").signoffs[0].approved)

    def test_record_signoff_unknown_decision_raises(self) -> None:
        sign = GovernanceSignoffRecord("s", "ghost", "name", RaciRoleType.CONSULTED, True)
        with self.assertRaises(ValueError):
            self.engine.record_signoff("ghost", sign)

    def test_evaluate_approval_full_raci_flow(self) -> None:
        dec = ProductGovernanceDecision(
            decision_id="dec-raci",
            title="GA Release Sign-off v4.5.0",
            decision_type=GovernanceDecisionType.RELEASE_SIGN_OFF,
            accountable_executive="VP Eng Grace",
        )
        self.engine.propose_decision(dec)

        # 1. Add Consulted & Informed
        self.engine.record_signoff(
            "dec-raci",
            GovernanceSignoffRecord("s-c", "dec-raci", "Consultant Bob", RaciRoleType.CONSULTED, True),
        )
        self.engine.record_signoff(
            "dec-raci",
            GovernanceSignoffRecord("s-i", "dec-raci", "Informed Team", RaciRoleType.INFORMED, True),
        )
        self.assertFalse(self.engine.get_decision("dec-raci").is_approved)

        # 2. Add Responsible signoff
        self.engine.record_signoff(
            "dec-raci",
            GovernanceSignoffRecord("s-r", "dec-raci", "Release Manager Dave", RaciRoleType.RESPONSIBLE, True),
        )
        self.assertFalse(self.engine.get_decision("dec-raci").is_approved)

        # 3. Add Accountable signoff -> Now fully approved!
        self.engine.record_signoff(
            "dec-raci",
            GovernanceSignoffRecord("s-a", "dec-raci", "VP Eng Grace", RaciRoleType.ACCOUNTABLE, True),
        )
        approved_dec = self.engine.get_decision("dec-raci")
        self.assertTrue(approved_dec.is_approved)
        self.assertTrue(len(approved_dec.decided_at) > 0)

    def test_evaluate_approval_fails_if_any_stakeholder_rejects(self) -> None:
        dec = ProductGovernanceDecision(
            decision_id="dec-veto",
            title="Security Policy Override",
            decision_type=GovernanceDecisionType.SECURITY_POLICY_OVERRIDE,
            accountable_executive="CISO",
        )
        self.engine.propose_decision(dec)

        self.engine.record_signoff(
            "dec-veto",
            GovernanceSignoffRecord("s1", "dec-veto", "CISO", RaciRoleType.ACCOUNTABLE, True),
        )
        self.engine.record_signoff(
            "dec-veto",
            GovernanceSignoffRecord("s2", "dec-veto", "SecArch", RaciRoleType.RESPONSIBLE, False),
        )

        is_app = self.engine.evaluate_approval("dec-veto")
        self.assertFalse(is_app)
        self.assertFalse(self.engine.get_decision("dec-veto").is_approved)

    def test_get_pending_decisions(self) -> None:
        d1 = ProductGovernanceDecision("d1", "Title 1", GovernanceDecisionType.RELEASE_SIGN_OFF, "Exec 1")
        d2 = ProductGovernanceDecision("d2", "Title 2", GovernanceDecisionType.RELEASE_SIGN_OFF, "Exec 2")
        self.engine.propose_decision(d1)
        self.engine.propose_decision(d2)

        self.engine.record_signoff(
            "d1", GovernanceSignoffRecord("s", "d1", "Exec 1", RaciRoleType.ACCOUNTABLE, True)
        )

        pending = self.engine.get_pending_decisions()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].decision_id, "d2")

    def test_get_governance_report(self) -> None:
        d1 = ProductGovernanceDecision("d1", "Title 1", GovernanceDecisionType.RELEASE_SIGN_OFF, "Exec 1")
        d2 = ProductGovernanceDecision("d2", "Title 2", GovernanceDecisionType.ARCHITECTURE_APPROVAL, "Exec 2")
        self.engine.propose_decision(d1)
        self.engine.propose_decision(d2)
        self.engine.record_signoff(
            "d1", GovernanceSignoffRecord("s", "d1", "Exec 1", RaciRoleType.ACCOUNTABLE, True)
        )

        rep = self.engine.get_governance_report()
        self.assertEqual(rep["total_decisions"], 2)
        self.assertEqual(rep["approved_decisions"], 1)
        self.assertEqual(rep["pending_decisions"], 1)
        self.assertEqual(rep["approval_rate_pct"], 50.0)
        self.assertEqual(rep["total_signoffs_recorded"], 1)


if __name__ == "__main__":
    unittest.main()
