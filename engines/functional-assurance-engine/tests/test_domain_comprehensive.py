"""Comprehensive tests for Functional Assurance domain entities, models, and algorithms."""

from __future__ import annotations

import json
import math
import unittest

from elmos_functional_assurance.domain import (
    AssuranceLevel,
    CertificateRecord,
    CertificateStatus,
    ConformityDecision,
    DecisionRuleType,
    FunctionalAssuranceContext,
    GuardBandSpecification,
    MeasurementUncertaintyBudget,
    ProductAssuranceLevel,
    SectorType,
    UncertaintyComponent,
    WormMerkleTree,
)


class TestDomainComprehensive(unittest.TestCase):
    """Tests covering domain enums, dataclasses, Merkle trees, and uncertainty models."""

    def test_enums_values_and_identity(self) -> None:
        self.assertEqual(AssuranceLevel.E0.value, "E0")
        self.assertEqual(AssuranceLevel.E5.value, "E5")
        self.assertEqual(ProductAssuranceLevel.P01.value, "P01")
        self.assertEqual(ProductAssuranceLevel.P05.value, "P05")
        self.assertEqual(CertificateStatus.DRAFT.value, "DRAFT")
        self.assertEqual(CertificateStatus.EVALUATING.value, "EVALUATING")
        self.assertEqual(CertificateStatus.ISSUED.value, "ISSUED")
        self.assertEqual(CertificateStatus.SUSPENDED.value, "SUSPENDED")
        self.assertEqual(CertificateStatus.REVOKED.value, "REVOKED")
        self.assertEqual(CertificateStatus.EXPIRED.value, "EXPIRED")
        self.assertEqual(ConformityDecision.CONFORMING.value, "CONFORMING")
        self.assertEqual(ConformityDecision.NON_CONFORMING.value, "NON_CONFORMING")
        self.assertEqual(ConformityDecision.CONDITIONAL_CONFORMING.value, "CONDITIONAL_CONFORMING")
        self.assertEqual(ConformityDecision.INDETERMINATE.value, "INDETERMINATE")
        self.assertEqual(SectorType.AVIATION.value, "AVIATION")
        self.assertEqual(SectorType.AUTOMOTIVE.value, "AUTOMOTIVE")
        self.assertEqual(SectorType.MEDICAL.value, "MEDICAL")
        self.assertEqual(SectorType.RAIL.value, "RAIL")
        self.assertEqual(SectorType.FINANCIAL.value, "FINANCIAL")
        self.assertEqual(SectorType.INDUSTRIAL.value, "INDUSTRIAL")
        self.assertEqual(SectorType.PUBLIC_SECTOR.value, "PUBLIC_SECTOR")
        self.assertEqual(SectorType.AUTONOMOUS_SYSTEMS.value, "AUTONOMOUS_SYSTEMS")
        self.assertEqual(DecisionRuleType.BINARY_SIMPLE.value, "BINARY_SIMPLE")
        self.assertEqual(DecisionRuleType.GUARD_BAND_EXPANDED.value, "GUARD_BAND_EXPANDED")
        self.assertEqual(DecisionRuleType.GUARD_BAND_GUARDED.value, "GUARD_BAND_GUARDED")
        self.assertEqual(DecisionRuleType.SHARED_RISK.value, "SHARED_RISK")

    def test_context_valid_creation(self) -> None:
        ctx = FunctionalAssuranceContext(
            tenant_id="TENANT_123",
            project_id="PROJ_ABC",
            execution_epoch="EPOCH_2026",
            fencing_token=100,
            candidate_digest="sha256:" + "a" * 64,
            base_evidence_receipt="REC_01",
            authority_digest="AUTH_01",
        )
        self.assertEqual(ctx.tenant_id, "TENANT_123")
        self.assertEqual(ctx.project_id, "PROJ_ABC")
        self.assertEqual(ctx.fencing_token, 100)
        self.assertTrue(ctx.candidate_digest.startswith("sha256:"))
        self.assertTrue(ctx.request_timestamp)

    def test_context_fail_closed_validation(self) -> None:
        # Empty tenant
        with self.assertRaises(ValueError):
            FunctionalAssuranceContext(
                tenant_id="",
                project_id="PROJ",
                execution_epoch="EPOCH",
                fencing_token=1,
                candidate_digest="sha256:" + "a" * 64,
                base_evidence_receipt="REC",
                authority_digest="AUTH",
            )
        # Empty project
        with self.assertRaises(ValueError):
            FunctionalAssuranceContext(
                tenant_id="TENANT",
                project_id="",
                execution_epoch="EPOCH",
                fencing_token=1,
                candidate_digest="sha256:" + "a" * 64,
                base_evidence_receipt="REC",
                authority_digest="AUTH",
            )
        # Invalid candidate_digest format (must be >= 32 chars)
        with self.assertRaises(ValueError):
            FunctionalAssuranceContext(
                tenant_id="TENANT",
                project_id="PROJ",
                execution_epoch="EPOCH",
                fencing_token=1,
                candidate_digest="short_digest",
                base_evidence_receipt="REC",
                authority_digest="AUTH",
            )
        # Negative fencing token
        with self.assertRaises(ValueError):
            FunctionalAssuranceContext(
                tenant_id="TENANT",
                project_id="PROJ",
                execution_epoch="EPOCH",
                fencing_token=-1,
                candidate_digest="sha256:" + "a" * 64,
                base_evidence_receipt="REC",
                authority_digest="AUTH",
            )

    def test_uncertainty_component_distributions(self) -> None:
        normal = UncertaintyComponent(name="normal_noise", value=0.01, distribution="NORMAL")
        rect = UncertaintyComponent(name="quant_error", value=0.01, distribution="RECTANGULAR")
        tri = UncertaintyComponent(name="temp_drift", value=0.01, distribution="TRIANGULAR")
        u_shaped = UncertaintyComponent(name="harmonic", value=0.01, distribution="U_SHAPED")
        other = UncertaintyComponent(name="unknown", value=0.01, distribution="OTHER")

        self.assertAlmostEqual(normal.standard_uncertainty, 0.01)
        self.assertAlmostEqual(rect.standard_uncertainty, 0.01 / math.sqrt(3))
        self.assertAlmostEqual(tri.standard_uncertainty, 0.01 / math.sqrt(6))
        self.assertAlmostEqual(u_shaped.standard_uncertainty, 0.01 / math.sqrt(2))
        self.assertAlmostEqual(other.standard_uncertainty, 0.01)

    def test_measurement_uncertainty_budget_computation(self) -> None:
        components = [
            UncertaintyComponent(name="c1", value=0.03, distribution="NORMAL"),
            UncertaintyComponent(name="c2", value=0.04, distribution="NORMAL"),
        ]
        budget = MeasurementUncertaintyBudget(
            measurand="latency_ms",
            nominal_value=12.5,
            components=components,
            coverage_factor_k=2.0,
        )
        # Combined std uncertainty = sqrt(0.03^2 + 0.04^2) = 0.05
        self.assertAlmostEqual(budget.combined_standard_uncertainty, 0.05)
        # Expanded uncertainty = k * combined = 2.0 * 0.05 = 0.10
        self.assertAlmostEqual(budget.expanded_uncertainty, 0.10)

        budget_dict = budget.to_dict()
        self.assertEqual(budget_dict["measurand"], "latency_ms")
        self.assertEqual(budget_dict["nominal_value"], 12.5)
        self.assertAlmostEqual(budget_dict["expanded_uncertainty"], 0.10)
        self.assertEqual(len(budget_dict["components"]), 2)

    def test_guard_band_decision_expanded(self) -> None:
        gb = GuardBandSpecification(
            lower_spec_limit=10.0,
            upper_spec_limit=20.0,
            rule_type=DecisionRuleType.GUARD_BAND_EXPANDED,
        )
        uncertainty = 1.0
        # Acceptance zone is [10.0 + 1.0, 20.0 - 1.0] = [11.0, 19.0]
        self.assertEqual(gb.evaluate_conformity(15.0, uncertainty), ConformityDecision.CONFORMING)
        self.assertEqual(gb.evaluate_conformity(11.0, uncertainty), ConformityDecision.CONFORMING)
        self.assertEqual(gb.evaluate_conformity(19.0, uncertainty), ConformityDecision.CONFORMING)

        # In the guard zone [10.0, 11.0) and (19.0, 20.0] -> CONDITIONAL_CONFORMING
        self.assertEqual(gb.evaluate_conformity(10.5, uncertainty), ConformityDecision.CONDITIONAL_CONFORMING)
        self.assertEqual(gb.evaluate_conformity(19.5, uncertainty), ConformityDecision.CONDITIONAL_CONFORMING)

        # Outside [10.0, 20.0] -> NON_CONFORMING
        self.assertEqual(gb.evaluate_conformity(9.9, uncertainty), ConformityDecision.NON_CONFORMING)
        self.assertEqual(gb.evaluate_conformity(20.1, uncertainty), ConformityDecision.NON_CONFORMING)

    def test_guard_band_single_limit(self) -> None:
        # Upper limit only
        gb_upper = GuardBandSpecification(
            lower_spec_limit=None,
            upper_spec_limit=100.0,
        )
        self.assertEqual(gb_upper.evaluate_conformity(90.0, 5.0), ConformityDecision.CONFORMING)
        self.assertEqual(gb_upper.evaluate_conformity(97.0, 5.0), ConformityDecision.CONDITIONAL_CONFORMING)
        self.assertEqual(gb_upper.evaluate_conformity(101.0, 5.0), ConformityDecision.NON_CONFORMING)

        # Lower limit only
        gb_lower = GuardBandSpecification(
            lower_spec_limit=50.0,
            upper_spec_limit=None,
        )
        self.assertEqual(gb_lower.evaluate_conformity(60.0, 5.0), ConformityDecision.CONFORMING)
        self.assertEqual(gb_lower.evaluate_conformity(53.0, 5.0), ConformityDecision.CONDITIONAL_CONFORMING)
        self.assertEqual(gb_lower.evaluate_conformity(49.0, 5.0), ConformityDecision.NON_CONFORMING)

        # No limits specified
        gb_none = GuardBandSpecification(
            lower_spec_limit=None,
            upper_spec_limit=None,
        )
        self.assertEqual(gb_none.evaluate_conformity(100.0, 5.0), ConformityDecision.INDETERMINATE)

    def test_worm_merkle_tree_operations(self) -> None:
        tree = WormMerkleTree()
        # Empty tree has a deterministic 64-char sha256 root (sha256 of empty genesis seed)
        self.assertEqual(len(tree.root_digest), 64)
        self.assertEqual(len(tree.leaves), 0)
        self.assertTrue(tree.verify_integrity())

        # Append first leaf
        leaf1 = tree.append("sha256:" + "1" * 64, role="audit_report")
        self.assertEqual(leaf1.index, 0)
        self.assertEqual(leaf1.role, "audit_report")
        self.assertEqual(len(tree.leaves), 1)
        root1 = tree.root_digest
        self.assertTrue(tree.verify_integrity())

        # Append second leaf
        leaf2 = tree.append("sha256:" + "2" * 64, role="fuzz_receipt")
        self.assertEqual(leaf2.index, 1)
        self.assertEqual(leaf2.prev_leaf_hash, leaf1.leaf_hash)
        self.assertEqual(len(tree.leaves), 2)
        root2 = tree.root_digest
        self.assertTrue(tree.verify_integrity())

        self.assertNotEqual(root1, root2)

        # Append third leaf (odd count checks duplicate last node during Merkle pairing)
        leaf3 = tree.append({"test": "data"}, role="structured_payload")
        self.assertEqual(leaf3.index, 2)
        self.assertEqual(leaf3.prev_leaf_hash, leaf2.leaf_hash)
        self.assertEqual(len(tree.leaves), 3)
        self.assertTrue(tree.verify_integrity())

        # Tampering check
        tree.leaves[1].data_hash = "tampered_hash"
        self.assertFalse(tree.verify_integrity())

    def test_certificate_record_serialization(self) -> None:
        cert = CertificateRecord(
            certificate_id="CERT-TEST-9999",
            subject_candidate_digest="sha256:" + "d" * 64,
            tenant_id="TENANT_PROD",
            project_id="PROJ_AIR",
            assurance_level=AssuranceLevel.E4,
            product_level=ProductAssuranceLevel.P04,
            sector=SectorType.AVIATION,
            decision=ConformityDecision.CONFORMING,
            status=CertificateStatus.ISSUED,
            scope_description="Avionics Core Flight Software",
            merkle_root_digest="e" * 64,
            issued_at="2026-09-01T00:00:00Z",
            expires_at="2027-09-01T00:00:00Z",
            evaluator_id="AUDITOR_01",
            independent_reviewer_id="REVIEWER_02",
            hsm_key_id="KEY_HSM_P384",
            signature_receipt="SIG_HEX_PROOF",
            metadata={"check_count": 42},
        )
        data = cert.to_dict()
        self.assertEqual(data["certificate_id"], "CERT-TEST-9999")
        self.assertEqual(data["assurance_level"], "E4")
        self.assertEqual(data["product_level"], "P04")
        self.assertEqual(data["sector"], "AVIATION")
        self.assertEqual(data["decision"], "CONFORMING")
        self.assertEqual(data["status"], "ISSUED")
        self.assertEqual(data["metadata"], {"check_count": 42})


if __name__ == "__main__":
    unittest.main()
