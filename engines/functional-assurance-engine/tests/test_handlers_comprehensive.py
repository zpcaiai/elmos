"""Comprehensive tests directly covering all 12 domain handlers in Functional Assurance Engine."""

from __future__ import annotations

import unittest

from elmos_functional_assurance.domain import (
    AssuranceLevel,
    CertificateStatus,
    ConformityDecision,
    FunctionalAssuranceContext,
)
from elmos_functional_assurance.handlers import (
    AccreditationBodyGovernor,
    AIAssuranceCertifier,
    CertificateLifecycleController,
    DataDatabaseCertifier,
    FormalProofCertifier,
    GovernanceComplianceMonitor,
    LabMetrologyGovernor,
    OperationsSRECertifier,
    PolyglotQACertifier,
    SectorProfileCompiler,
    SecurityPrivacyCertifier,
    SupplyChainAttestationCertifier,
)


class TestHandlersComprehensive(unittest.TestCase):
    """Direct testing of domain handlers across standard conforming and non-conforming branches."""

    def setUp(self) -> None:
        self.context = FunctionalAssuranceContext(
            tenant_id="TENANT_HANDLERS",
            project_id="PROJ_HANDLERS",
            execution_epoch="EPOCH_2026_01",
            fencing_token=42,
            candidate_digest="sha256:" + "8" * 64,
            base_evidence_receipt="BASE_REC_HANDLERS",
            authority_digest="AUTH_DIGEST_HANDLERS",
        )

    # ── 1. AccreditationBodyGovernor ──

    def test_accreditation_body_governor(self) -> None:
        # Scope compilation
        scope = AccreditationBodyGovernor.compile_accreditation_scope(
            self.context,
            cab_name="Global Conformity Cert Corp",
            conformity_standards=["ISO/IEC 17065", "ISO/IEC 17025"],
            sectors=["AVIATION", "MEDICAL"],
            cmc_capabilities={"precision": 1e-6},
        )
        self.assertEqual(scope["status"], "APPROVED")
        self.assertEqual(scope["cab_name"], "Global Conformity Cert Corp")
        self.assertTrue(scope["scope_digest"])

        # Global recognition
        rec = AccreditationBodyGovernor.resolve_global_recognition(
            self.context,
            accreditation_body="DAkkS",
            signatory_agreements=["IAF-MLA", "ILAC-MRA"],
        )
        self.assertTrue(rec["cross_border_acceptance"])
        self.assertEqual(rec["decision"], ConformityDecision.CONFORMING.value)

        # Evidence package
        pkg = AccreditationBodyGovernor.package_accredited_evidence(
            self.context,
            evidence_manifest={"test_runs": 10},
            ab_signoff_digest="SIG_AB_ROOT",
        )
        self.assertEqual(pkg["candidate_digest"], self.context.candidate_digest)
        self.assertTrue(pkg["evidence_bundle_hash"])
        self.assertEqual(pkg["status"], "SEALED")

    # ── 2. AIAssuranceCertifier ──

    def test_ai_assurance_adversarial_robustness(self) -> None:
        # Conforming case (low epsilon)
        res_pass = AIAssuranceCertifier.evaluate_adversarial_robustness(
            self.context,
            model_digest=self.context.candidate_digest,
            test_dataset_digest="DATASET_DIGEST_01",
            perturbation_epsilon=0.01,
        )
        self.assertEqual(res_pass["decision"], ConformityDecision.CONFORMING.value)
        self.assertEqual(res_pass["certified_assurance_level"], AssuranceLevel.E4.value)

        # Non-conforming case (high epsilon -> large drop)
        res_fail = AIAssuranceCertifier.evaluate_adversarial_robustness(
            self.context,
            model_digest=self.context.candidate_digest,
            test_dataset_digest="DATASET_DIGEST_01",
            perturbation_epsilon=0.10,
        )
        self.assertEqual(res_fail["decision"], ConformityDecision.NON_CONFORMING.value)
        self.assertEqual(res_fail["certified_assurance_level"], AssuranceLevel.E1.value)

    def test_ai_assurance_conformal_coverage(self) -> None:
        # Conforming (low test errors)
        res_pass = AIAssuranceCertifier.evaluate_conformal_coverage(
            self.context,
            calibration_set_size=1000,
            significance_level_alpha=0.05,
            test_errors=30,
            total_test_samples=1000,
        )
        self.assertEqual(res_pass["decision"], ConformityDecision.CONFORMING.value)
        self.assertTrue(res_pass["finite_sample_guarantee"])

        # Non-conforming (excessive test errors)
        res_fail = AIAssuranceCertifier.evaluate_conformal_coverage(
            self.context,
            calibration_set_size=1000,
            significance_level_alpha=0.05,
            test_errors=200,
            total_test_samples=1000,
        )
        self.assertEqual(res_fail["decision"], ConformityDecision.NON_CONFORMING.value)

    def test_ai_assurance_fairness_and_bias(self) -> None:
        # Conforming (balanced groups)
        subgroups_pass = {
            "group_1": {"positive_rate": 0.85, "tpr": 0.90},
            "group_2": {"positive_rate": 0.82, "tpr": 0.88},
        }
        res_pass = AIAssuranceCertifier.evaluate_fairness_and_bias(
            self.context, subgroup_metrics=subgroups_pass, disparate_impact_threshold=0.80
        )
        self.assertEqual(res_pass["decision"], ConformityDecision.CONFORMING.value)
        self.assertFalse(res_pass["intersectional_bias_detected"])

        # Non-conforming (large disparity)
        subgroups_fail = {
            "group_1": {"positive_rate": 0.90, "tpr": 0.95},
            "group_2": {"positive_rate": 0.40, "tpr": 0.60},
        }
        res_fail = AIAssuranceCertifier.evaluate_fairness_and_bias(
            self.context, subgroup_metrics=subgroups_fail, disparate_impact_threshold=0.80
        )
        self.assertEqual(res_fail["decision"], ConformityDecision.NON_CONFORMING.value)
        self.assertTrue(res_fail["intersectional_bias_detected"])

    def test_ai_assurance_explainability_stability(self) -> None:
        res_pass = AIAssuranceCertifier.evaluate_explainability_stability(
            self.context,
            fidelity_score=0.95,
            stability_lipschitz_constant=1.2,
            sparsity_ratio=0.85,
        )
        self.assertEqual(res_pass["decision"], ConformityDecision.CONFORMING.value)
        self.assertTrue(res_pass["local_surrogate_valid"])

        res_fail = AIAssuranceCertifier.evaluate_explainability_stability(
            self.context,
            fidelity_score=0.70,
            stability_lipschitz_constant=5.0,
            sparsity_ratio=0.50,
        )
        self.assertEqual(res_fail["decision"], ConformityDecision.NON_CONFORMING.value)
        self.assertFalse(res_fail["local_surrogate_valid"])

    def test_ai_assurance_e0_e5_levels(self) -> None:
        # E0
        e0 = AIAssuranceCertifier.evaluate_e0_e5_assurance(self.context, {})
        self.assertEqual(e0["evaluated_assurance_level"], "E0")

        # E1
        e1 = AIAssuranceCertifier.evaluate_e0_e5_assurance(self.context, {"schema_validated": True})
        self.assertEqual(e1["evaluated_assurance_level"], "E1")

        # E2
        e2 = AIAssuranceCertifier.evaluate_e0_e5_assurance(
            self.context, {"schema_validated": True, "contracts_verified": True}
        )
        self.assertEqual(e2["evaluated_assurance_level"], "E2")

        # E3
        e3 = AIAssuranceCertifier.evaluate_e0_e5_assurance(
            self.context, {"schema_validated": True, "contracts_verified": True, "fuzz_metamorphic_passed": True}
        )
        self.assertEqual(e3["evaluated_assurance_level"], "E3")

        # E4
        e4 = AIAssuranceCertifier.evaluate_e0_e5_assurance(
            self.context,
            {
                "schema_validated": True,
                "contracts_verified": True,
                "fuzz_metamorphic_passed": True,
                "formal_proof_checked": True,
            },
        )
        self.assertEqual(e4["evaluated_assurance_level"], "E4")

        # E5
        e5 = AIAssuranceCertifier.evaluate_e0_e5_assurance(
            self.context,
            {
                "schema_validated": True,
                "contracts_verified": True,
                "fuzz_metamorphic_passed": True,
                "formal_proof_checked": True,
                "independent_tevv_completed": True,
            },
        )
        self.assertEqual(e5["evaluated_assurance_level"], "E5")

    # ── 3. CertificateLifecycleController ──

    def test_certificate_lifecycle_controller(self) -> None:
        # Issue certificate
        cert = CertificateLifecycleController.issue_certificate(
            context=self.context,
            assurance_level="E4",
            product_level="P03",
            scope_description="Safe Autonomous Delivery Controller",
            evaluator_id="AUDITOR_JOE",
            independent_reviewer_id="REVIEWER_JANE",
            sector="RAIL",
        )
        self.assertTrue(cert.certificate_id.startswith("CERT-ELMOS-"))
        self.assertEqual(cert.status, CertificateStatus.ISSUED)

        # Segregation of duties violation
        with self.assertRaises(ValueError):
            CertificateLifecycleController.issue_certificate(
                context=self.context,
                assurance_level="E4",
                product_level="P03",
                scope_description="Invalid Self-Certification",
                evaluator_id="SAME_PERSON",
                independent_reviewer_id="SAME_PERSON",
            )

        # Revocation
        rev = CertificateLifecycleController.revoke_certificate(
            self.context,
            certificate_id=cert.certificate_id,
            reason="Adversarial vulnerability discovered",
            revocation_authority_id="SECURITY_BOARD_01",
        )
        self.assertEqual(rev["status"], CertificateStatus.REVOKED.value)
        self.assertEqual(rev["decision"], ConformityDecision.CONFORMING.value)
        self.assertTrue(rev["revocation_receipt"])

        # Deployment admission
        admit_pass = CertificateLifecycleController.evaluate_deployment_admission(
            self.context, certificate=cert.to_dict(), required_min_assurance="E3"
        )
        self.assertTrue(admit_pass["admitted"])
        self.assertEqual(admit_pass["decision"], ConformityDecision.CONFORMING.value)

        # Deployment admission rejected due to higher requirement (E5 vs E4)
        admit_fail_level = CertificateLifecycleController.evaluate_deployment_admission(
            self.context, certificate=cert.to_dict(), required_min_assurance="E5"
        )
        self.assertFalse(admit_fail_level["admitted"])
        self.assertEqual(admit_fail_level["decision"], ConformityDecision.NON_CONFORMING.value)

        # Deployment admission rejected due to candidate digest mismatch
        tampered_cert = cert.to_dict()
        tampered_cert["subject_candidate_digest"] = "sha256:" + "0" * 64
        admit_fail_digest = CertificateLifecycleController.evaluate_deployment_admission(
            self.context, certificate=tampered_cert, required_min_assurance="E3"
        )
        self.assertFalse(admit_fail_digest["admitted"])

    # ── 4. DataDatabaseCertifier ──

    def test_data_database_certifier(self) -> None:
        # Cutover passing
        cut_pass = DataDatabaseCertifier.certify_cutover_and_rollback(
            self.context, data_checksum_matched=True, data_loss_bytes=0, rollback_tested_seconds=30
        )
        self.assertEqual(cut_pass["decision"], ConformityDecision.CONFORMING.value)
        self.assertTrue(cut_pass["rto_sla_met"])

        # Cutover failing due to data loss
        cut_fail = DataDatabaseCertifier.certify_cutover_and_rollback(
            self.context, data_checksum_matched=False, data_loss_bytes=4096, rollback_tested_seconds=400
        )
        self.assertEqual(cut_fail["decision"], ConformityDecision.NON_CONFORMING.value)
        self.assertFalse(cut_fail["rto_sla_met"])

        # PITR recovery passing
        pitr_pass = DataDatabaseCertifier.certify_backup_pitr_recovery(
            self.context, rpo_achieved_seconds=0, rto_achieved_seconds=60, data_reconciliation_diff_count=0
        )
        self.assertEqual(pitr_pass["decision"], ConformityDecision.CONFORMING.value)
        self.assertTrue(pitr_pass["zero_data_loss_proven"])

        # PITR recovery failing
        pitr_fail = DataDatabaseCertifier.certify_backup_pitr_recovery(
            self.context, rpo_achieved_seconds=600, rto_achieved_seconds=900, data_reconciliation_diff_count=5
        )
        self.assertEqual(pitr_fail["decision"], ConformityDecision.NON_CONFORMING.value)

        # Event replay idempotency passing
        replay_pass = DataDatabaseCertifier.certify_event_replay_idempotency(
            self.context, duplicate_events_injected=5000, side_effects_duplicated=0, state_divergence_detected=False
        )
        self.assertEqual(replay_pass["decision"], ConformityDecision.CONFORMING.value)

        # Event replay failing
        replay_fail = DataDatabaseCertifier.certify_event_replay_idempotency(
            self.context, duplicate_events_injected=5000, side_effects_duplicated=2, state_divergence_detected=True
        )
        self.assertEqual(replay_fail["decision"], ConformityDecision.NON_CONFORMING.value)

    # ── 5. FormalProofCertifier ──

    def test_formal_proof_certifier(self) -> None:
        # Machine proof passing
        proof_pass = FormalProofCertifier.replay_machine_proof(
            self.context,
            proof_kernel="lean4",
            theorem_name="invariants_preserved",
            proof_script_digest="LEAN4_SCRIPT_SHA",
            axioms_used=["classical_em"],
        )
        self.assertTrue(proof_pass["soundness_verified"])
        self.assertEqual(proof_pass["decision"], ConformityDecision.CONFORMING.value)
        self.assertEqual(proof_pass["assurance_level"], "E4")

        # Machine proof with disallowed axiom (sorry)
        proof_fail = FormalProofCertifier.replay_machine_proof(
            self.context,
            proof_kernel="lean4",
            theorem_name="invariants_incomplete",
            proof_script_digest="LEAN4_SCRIPT_SHA_INCOMPLETE",
            axioms_used=["sorry"],
        )
        self.assertFalse(proof_fail["soundness_verified"])
        self.assertEqual(proof_fail["decision"], ConformityDecision.NON_CONFORMING.value)
        self.assertEqual(proof_fail["assurance_level"], "E1")

        # State space coverage passing
        space_pass = FormalProofCertifier.verify_state_space_coverage(
            self.context, model_name="raft_consensus", explored_states=100000, diameter=15
        )
        self.assertEqual(space_pass["decision"], ConformityDecision.CONFORMING.value)

        # State space coverage with deadlock detected
        space_fail = FormalProofCertifier.verify_state_space_coverage(
            self.context, model_name="raft_consensus", explored_states=5000, diameter=8, deadlocks_detected=1
        )
        self.assertEqual(space_fail["decision"], ConformityDecision.NON_CONFORMING.value)

        # TCB minimization
        tcb_small = FormalProofCertifier.evaluate_tcb_minimization(
            self.context, tcb_components=["kernel", "mmu"], kernel_loc_count=2500
        )
        self.assertEqual(tcb_small["decision"], ConformityDecision.CONFORMING.value)
        self.assertTrue(tcb_small["tcb_minimized"])

        tcb_large = FormalProofCertifier.evaluate_tcb_minimization(
            self.context, tcb_components=["kernel", "mmu", "driver"], kernel_loc_count=15000
        )
        self.assertEqual(tcb_large["decision"], ConformityDecision.CONDITIONAL_CONFORMING.value)
        self.assertFalse(tcb_large["tcb_minimized"])

    # ── 6. GovernanceComplianceMonitor ──

    def test_governance_compliance_monitor(self) -> None:
        # Post-market monitoring conforming
        gov_pass = GovernanceComplianceMonitor.monitor_eu_ai_act_post_market(
            self.context, model_risk_category="HIGH_RISK", drift_threshold_exceeded=False
        )
        self.assertEqual(gov_pass["decision"], ConformityDecision.CONFORMING.value)

        # Post-market monitoring non-conforming (unreported incident)
        gov_fail = GovernanceComplianceMonitor.monitor_eu_ai_act_post_market(
            self.context,
            model_risk_category="HIGH_RISK",
            drift_threshold_exceeded=True,
            serious_incident_occurred=True,
            reported_within_statutory_window=False,
        )
        self.assertEqual(gov_fail["decision"], ConformityDecision.NON_CONFORMING.value)

        # Continuous runtime policy
        sec_pass = GovernanceComplianceMonitor.monitor_continuous_runtime_policy(
            self.context, policy_evaluations_total=10000, policy_violations_blocked=15, unauthorized_bypass_detected=False
        )
        self.assertEqual(sec_pass["decision"], ConformityDecision.CONFORMING.value)

        sec_fail = GovernanceComplianceMonitor.monitor_continuous_runtime_policy(
            self.context, policy_evaluations_total=10000, policy_violations_blocked=15, unauthorized_bypass_detected=True
        )
        self.assertEqual(sec_fail["decision"], ConformityDecision.NON_CONFORMING.value)

        # Enterprise dossier
        dossier = GovernanceComplianceMonitor.generate_enterprise_assurance_dossier(
            self.context, included_assurance_levels=["E3", "E4"]
        )
        self.assertEqual(dossier["dossier_status"], "READY_FOR_REGULATOR_AUDIT")
        self.assertEqual(dossier["decision"], ConformityDecision.CONFORMING.value)

    # ── 7. LabMetrologyGovernor ──

    def test_lab_metrology_governor(self) -> None:
        # Uncertainty budget
        budget = LabMetrologyGovernor.compile_uncertainty_budget(
            self.context,
            measurand="clock_drift_ppm",
            nominal_value=0.05,
            components_spec=[
                {"name": "oscillator_jitter", "value": 0.001, "distribution": "NORMAL"},
                {"name": "temp_variation", "value": 0.002, "distribution": "RECTANGULAR"},
            ],
            coverage_factor_k=2.0,
        )
        self.assertEqual(budget["decision"], ConformityDecision.CONFORMING.value)
        self.assertIn("budget", budget)

        # Decision rule evaluation
        rule_eval = LabMetrologyGovernor.evaluate_conformity_decision_rule(
            self.context,
            measured_value=0.05,
            expanded_uncertainty=0.005,
            lower_spec=0.01,
            upper_spec=0.10,
        )
        self.assertEqual(rule_eval["decision"], ConformityDecision.CONFORMING.value)

        # Interlaboratory comparison (En score)
        # diff = |10.0 - 10.02| = 0.02, combined_u = sqrt(0.02^2 + 0.02^2) = 0.02828 -> En = 0.02 / 0.02828 = 0.707 <= 1.0 (satisfactory)
        interlab_pass = LabMetrologyGovernor.evaluate_interlaboratory_comparison(
            self.context,
            lab_value=10.0,
            lab_uncertainty=0.02,
            reference_value=10.02,
            reference_uncertainty=0.02,
        )
        self.assertTrue(interlab_pass["satisfactory"])
        self.assertEqual(interlab_pass["decision"], ConformityDecision.CONFORMING.value)

        # Unsatisfactory interlab comparison (En > 1.0)
        interlab_fail = LabMetrologyGovernor.evaluate_interlaboratory_comparison(
            self.context,
            lab_value=10.0,
            lab_uncertainty=0.01,
            reference_value=10.10,
            reference_uncertainty=0.01,
        )
        self.assertFalse(interlab_fail["satisfactory"])
        self.assertEqual(interlab_fail["decision"], ConformityDecision.NON_CONFORMING.value)

        # Laboratory competence audit
        lab_audit_pass = LabMetrologyGovernor.audit_laboratory_competence(
            self.context, accreditation_number="ISO17025-LAB-42", scopes=["Calibration", "Testing"]
        )
        self.assertTrue(lab_audit_pass["audit_passed"])

        lab_audit_fail = LabMetrologyGovernor.audit_laboratory_competence(
            self.context,
            accreditation_number="ISO17025-LAB-42",
            scopes=["Testing"],
            equipment_calibrated=False,
        )
        self.assertFalse(lab_audit_fail["audit_passed"])

    # ── 8. OperationsSRECertifier ──

    def test_operations_sre_certifier(self) -> None:
        # SLO error budget
        slo_pass = OperationsSRECertifier.govern_slo_error_budget(
            self.context, target_slo_percent=99.9, current_availability=99.98, burn_rate_1h=0.5
        )
        self.assertTrue(slo_pass["release_admitted"])
        self.assertEqual(slo_pass["decision"], ConformityDecision.CONFORMING.value)

        slo_fail = OperationsSRECertifier.govern_slo_error_budget(
            self.context, target_slo_percent=99.9, current_availability=99.80, burn_rate_1h=2.5
        )
        self.assertFalse(slo_fail["release_admitted"])
        self.assertEqual(slo_fail["decision"], ConformityDecision.NON_CONFORMING.value)

        # Multi-region failover
        failover_pass = OperationsSRECertifier.certify_multiregion_failover(
            self.context, failover_duration_seconds=15, active_active_split_brain_prevented=True
        )
        self.assertEqual(failover_pass["decision"], ConformityDecision.CONFORMING.value)

        failover_fail = OperationsSRECertifier.certify_multiregion_failover(
            self.context, failover_duration_seconds=90, active_active_split_brain_prevented=False
        )
        self.assertEqual(failover_fail["decision"], ConformityDecision.NON_CONFORMING.value)

        # Sustainable AI carbon
        carbon_pass = OperationsSRECertifier.certify_sustainable_ai_carbon(
            self.context, joules_per_query=25.0, co2_grams_per_kwh=120.0, efficiency_target_met=True
        )
        self.assertEqual(carbon_pass["decision"], ConformityDecision.CONFORMING.value)

    # ── 9. PolyglotQACertifier ──

    def test_polyglot_qa_certifier(self) -> None:
        # Accessibility WCAG
        a11y_pass = PolyglotQACertifier.certify_accessibility_wcag(
            self.context, violations_critical=0, violations_serious=0, contrast_ratio_min=5.2
        )
        self.assertEqual(a11y_pass["decision"], ConformityDecision.CONFORMING.value)

        a11y_fail = PolyglotQACertifier.certify_accessibility_wcag(
            self.context, violations_critical=2, violations_serious=5, contrast_ratio_min=3.0
        )
        self.assertEqual(a11y_fail["decision"], ConformityDecision.NON_CONFORMING.value)

        # FFI ABI boundary
        ffi_pass = PolyglotQACertifier.certify_ffi_abi_native_boundary(
            self.context, memory_alignment_verified=True, buffer_overflow_probes_blocked=500, type_size_mismatches=0
        )
        self.assertEqual(ffi_pass["decision"], ConformityDecision.CONFORMING.value)

        ffi_fail = PolyglotQACertifier.certify_ffi_abi_native_boundary(
            self.context, memory_alignment_verified=False, type_size_mismatches=3
        )
        self.assertEqual(ffi_fail["decision"], ConformityDecision.NON_CONFORMING.value)

        # Polyglot route
        route_pass = PolyglotQACertifier.certify_polyglot_route(
            self.context, source_language="java", target_language="csharp", ast_equivalence_score=0.998, differential_behavior_passed=True
        )
        self.assertEqual(route_pass["decision"], ConformityDecision.CONFORMING.value)

        route_fail = PolyglotQACertifier.certify_polyglot_route(
            self.context, source_language="c", target_language="rust", ast_equivalence_score=0.85, differential_behavior_passed=False
        )
        self.assertEqual(route_fail["decision"], ConformityDecision.NON_CONFORMING.value)

        # Synthetic test data privacy
        dp_pass = PolyglotQACertifier.certify_synthetic_test_data_privacy(
            self.context, differential_privacy_epsilon=0.5, reidentification_risk_score=0.0005, pii_leakage_detected=False
        )
        self.assertEqual(dp_pass["decision"], ConformityDecision.CONFORMING.value)

        dp_fail = PolyglotQACertifier.certify_synthetic_test_data_privacy(
            self.context, differential_privacy_epsilon=5.0, reidentification_risk_score=0.05, pii_leakage_detected=True
        )
        self.assertEqual(dp_fail["decision"], ConformityDecision.NON_CONFORMING.value)

    # ── 10. SectorProfileCompiler ──

    def test_sector_profile_compiler(self) -> None:
        # Aviation
        av_pass = SectorProfileCompiler.compile_aviation_do178c_profile(
            self.context, dal_level="DAL_A", mcdc_coverage_met=True, structural_coverage_met=True
        )
        self.assertEqual(av_pass["decision"], ConformityDecision.CONFORMING.value)
        self.assertTrue(av_pass["psac_ready"])

        av_fail = SectorProfileCompiler.compile_aviation_do178c_profile(
            self.context, dal_level="DAL_A", mcdc_coverage_met=False
        )
        self.assertEqual(av_fail["decision"], ConformityDecision.NON_CONFORMING.value)

        # Automotive
        auto_pass = SectorProfileCompiler.compile_automotive_iso26262_profile(
            self.context, asil_level="ASIL_D", unreasonable_risk_residual=False
        )
        self.assertEqual(auto_pass["decision"], ConformityDecision.CONFORMING.value)

        auto_fail = SectorProfileCompiler.compile_automotive_iso26262_profile(
            self.context, asil_level="ASIL_D", unreasonable_risk_residual=True
        )
        self.assertEqual(auto_fail["decision"], ConformityDecision.NON_CONFORMING.value)

        # Medical
        med_pass = SectorProfileCompiler.compile_medical_iec62304_profile(
            self.context, software_safety_class="CLASS_C", iso14971_risk_matrix_closed=True, clinical_evaluation_backed=True
        )
        self.assertEqual(med_pass["decision"], ConformityDecision.CONFORMING.value)

        med_fail = SectorProfileCompiler.compile_medical_iec62304_profile(
            self.context, clinical_evaluation_backed=False
        )
        self.assertEqual(med_fail["decision"], ConformityDecision.NON_CONFORMING.value)

        # Financial
        fin_pass = SectorProfileCompiler.compile_financial_sr11_7_profile(
            self.context, conceptual_soundness_proven=True, benchmarking_disparity=0.02, backtesting_violations=0
        )
        self.assertEqual(fin_pass["decision"], ConformityDecision.CONFORMING.value)

        fin_fail = SectorProfileCompiler.compile_financial_sr11_7_profile(
            self.context, conceptual_soundness_proven=False, backtesting_violations=5
        )
        self.assertEqual(fin_fail["decision"], ConformityDecision.NON_CONFORMING.value)

    # ── 11. SecurityPrivacyCertifier ──

    def test_security_privacy_certifier(self) -> None:
        # Confidential computing TEE
        tee_pass = SecurityPrivacyCertifier.verify_confidential_ai_inference(
            self.context,
            tee_platform="AWS_NITRO",
            enclave_measurement_pcr="sha256:" + "7" * 64,
            expected_policy_digest="POLICY_SHA",
            input_data_sealed=True,
        )
        self.assertEqual(tee_pass["decision"], ConformityDecision.CONFORMING.value)

        # WASI sandbox
        wasi_pass = SecurityPrivacyCertifier.verify_wasi_sandbox_capabilities(
            self.context,
            allowed_filesystem_roots=["/var/tmp"],
            allowed_network_hosts=["127.0.0.1"],
            unauthorized_syscalls_attempted=0,
            capability_leakage_detected=False,
        )
        self.assertEqual(wasi_pass["decision"], ConformityDecision.CONFORMING.value)

        wasi_fail = SecurityPrivacyCertifier.verify_wasi_sandbox_capabilities(
            self.context,
            allowed_filesystem_roots=["/var/tmp"],
            allowed_network_hosts=[],
            unauthorized_syscalls_attempted=12,
            capability_leakage_detected=True,
        )
        self.assertEqual(wasi_fail["decision"], ConformityDecision.NON_CONFORMING.value)

        # Cryptographic CAVP
        crypto_pass = SecurityPrivacyCertifier.certify_cryptographic_cavp(
            self.context,
            algorithms=["AES-256-GCM", "ML-KEM-768"],
            known_answer_tests_passed=True,
            post_quantum_ready=True,
        )
        self.assertEqual(crypto_pass["decision"], ConformityDecision.CONFORMING.value)

        # Timestamp token verification
        ts_pass = SecurityPrivacyCertifier.verify_timestamp_token(
            self.context,
            timestamp_token_der_hex="0" * 64,
            evidence_hash="sha256:" + "f" * 64,
            trusted_tsa_cert_fingerprint="TSA_FINGERPRINT",
        )
        self.assertEqual(ts_pass["decision"], ConformityDecision.CONFORMING.value)

    # ── 12. SupplyChainAttestationCertifier ──

    def test_supply_chain_attestation_certifier(self) -> None:
        # Hermetic build
        build_pass = SupplyChainAttestationCertifier.verify_hermetic_build(
            self.context, slsa_level="SLSA_BUILD_LEVEL_3", unpinned_dependencies_count=0, network_isolation_enforced=True
        )
        self.assertEqual(build_pass["decision"], ConformityDecision.CONFORMING.value)

        build_fail = SupplyChainAttestationCertifier.verify_hermetic_build(
            self.context, unpinned_dependencies_count=4, network_isolation_enforced=False
        )
        self.assertEqual(build_fail["decision"], ConformityDecision.NON_CONFORMING.value)

        # License & IP audit
        components_clean = [
            {"name": "lib1", "license": "MIT"},
            {"name": "lib2", "license": "Apache-2.0"},
            {"name": "lib3", "license": "BSD-3-Clause"},
        ]
        lic_pass = SupplyChainAttestationCertifier.audit_license_and_ip(
            self.context, sbom_components=components_clean
        )
        self.assertTrue(lic_pass["ip_clean"])
        self.assertEqual(lic_pass["decision"], ConformityDecision.CONFORMING.value)

        components_dirty = [
            {"name": "lib1", "license": "MIT"},
            {"name": "lib2", "license": "GPL-3.0"},
        ]
        lic_fail = SupplyChainAttestationCertifier.audit_license_and_ip(
            self.context, sbom_components=components_dirty
        )
        self.assertFalse(lic_fail["ip_clean"])
        self.assertEqual(lic_fail["decision"], ConformityDecision.NON_CONFORMING.value)

        # Vulnerability VEX
        cves_clean = [
            {"cve": "CVE-2026-0001", "severity": "LOW"},
            {"cve": "CVE-2026-0002", "severity": "CRITICAL", "vex_justification": "component_not_reachable"},
        ]
        vex_pass = SupplyChainAttestationCertifier.govern_vulnerability_vex(
            self.context, cve_findings=cves_clean, cisa_kev_matches=0
        )
        self.assertEqual(vex_pass["decision"], ConformityDecision.CONFORMING.value)

        cves_dirty = [
            {"cve": "CVE-2026-9999", "severity": "CRITICAL", "vex_justification": ""},
        ]
        vex_fail = SupplyChainAttestationCertifier.govern_vulnerability_vex(
            self.context, cve_findings=cves_dirty, cisa_kev_matches=1
        )
        self.assertEqual(vex_fail["decision"], ConformityDecision.NON_CONFORMING.value)


if __name__ == "__main__":
    unittest.main()
