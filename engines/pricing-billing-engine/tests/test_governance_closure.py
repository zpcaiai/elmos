from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from elmos_pricing_billing.errors import DomainError
from elmos_pricing_billing.governance_closure import (
    BatchNode,
    BillingMigrationService,
    BillingOrchestrationService,
    BillingQualificationService,
    ImplementationState,
    MigrationAuthority,
    RequirementTrace,
    RequirementTraceabilityService,
    VerificationBinding,
)
from elmos_pricing_billing.operations_closure import CertificationState, ExternalExecutionState

NOW = datetime(2026, 8, 26, tzinfo=UTC)


def test_eb01_five_state_traceability_is_machine_derived() -> None:
    service = RequirementTraceabilityService(("EB-01-001", "EB-01-002", "EB-01-003"))
    service.record(
        RequirementTrace(
            requirement_id="EB-01-001",
            source_file="source.py",
            symbol="Service.method",
            test_node_id="tests/test_source.py::test_method",
            test_state=ExternalExecutionState.NOT_RUN,
            runtime_evidence_digest=None,
            commit=None,
            behavior_implemented=True,
            acceptance_complete=True,
        )
    )
    service.record(
        RequirementTrace(
            requirement_id="EB-01-002",
            source_file="source.py",
            symbol="Service.interface",
            test_node_id=None,
            test_state=ExternalExecutionState.NOT_RUN,
            runtime_evidence_digest=None,
            commit=None,
            behavior_implemented=False,
            acceptance_complete=False,
            stub_only=True,
        )
    )

    assert service.status("EB-01-001") is ImplementationState.NOT_VERIFIED
    assert service.status("EB-01-002") is ImplementationState.STUB
    assert service.status("EB-01-003") is ImplementationState.MISSING
    report = service.machine_report()
    assert report["requirement_count"] == 3
    assert len(str(report["digest"])) == 64


def test_eb01_baseline_dependency_dag_checkpoint_and_handoff_are_replayable() -> None:
    service = BillingOrchestrationService()
    baseline = service.capture_baseline(
        baseline_id="baseline-1",
        repository_commit="a" * 40,
        capabilities=("billing", "task", "payment", "model", "tenant", "invoice"),
        captured_at=NOW,
    )
    order = service.dependency_order(
        (
            BatchNode("B", ("A",), True, "parallel-2"),
            BatchNode("A", (), True, "parallel-1"),
            BatchNode("C", ("A",), True, "parallel-2"),
        )
    )
    checkpoint = service.save_checkpoint(
        checkpoint_id="checkpoint-1",
        tenant_id="tenant-a",
        batch_id="B",
        inputs={"scope": "scope-1"},
        code_baseline=baseline.repository_commit,
        completed_nodes=("A",),
        output={"artifact": "artifact-1"},
        cost_snapshot=Decimal("12.30"),
        billing_receipt_id="receipt-1",
        created_at=NOW,
    )
    replayed = service.save_checkpoint(
        checkpoint_id="checkpoint-1",
        tenant_id="tenant-a",
        batch_id="B",
        inputs={"scope": "scope-1"},
        code_baseline=baseline.repository_commit,
        completed_nodes=("A",),
        output={"artifact": "artifact-1"},
        cost_snapshot=Decimal("12.30"),
        billing_receipt_id="receipt-1",
        created_at=NOW,
    )
    handoff = service.handoff(
        handoff_id="handoff-1",
        checkpoint_id=checkpoint.checkpoint_id,
        from_agent="codex",
        to_agent="claude-code",
        tenant_id="tenant-a",
    )

    assert order == ("A", "B", "C")
    assert replayed == checkpoint
    assert handoff.billing_receipt_id == checkpoint.billing_receipt_id
    with pytest.raises(DomainError, match="checkpoint belongs to another tenant"):
        service.handoff(
            handoff_id="handoff-cross-tenant",
            checkpoint_id=checkpoint.checkpoint_id,
            from_agent="codex",
            to_agent="claude-code",
            tenant_id="tenant-b",
        )


def test_eb01_contract_change_release_gate_and_completion_trace_fail_closed() -> None:
    service = BillingOrchestrationService()
    change = service.authorize_contract_change(
        contract_id="contract-1",
        fixed_price=True,
        old_scope={"files": 10},
        new_scope={"files": 20},
        adr_id="ADR-42",
        impact_analysis={"cost_delta": "10.00"},
        reason="customer expanded scope",
    )
    blocked = service.release_gate(
        {
            "security": True,
            "ledger-balance": True,
            "reconciliation": False,
            "performance": True,
            "recovery": True,
            "rollback": True,
        }
    )
    trace = service.completion_trace(
        requirement_id="EB-01-008",
        files=("source.py",),
        symbols=("Service.method",),
        tests=("tests/test_source.py::test_method",),
        runtime_evidence=(),
        commit=None,
    )

    assert change is not None and change.adr_id == "ADR-42"
    assert not blocked.allowed and blocked.failed_domains == ("reconciliation",)
    assert blocked.maximum_decision is CertificationState.NOT_CERTIFIED
    assert trace["commit"] is None


def test_eb17_suites_require_exact_cases_and_external_payment_evidence() -> None:
    service = BillingQualificationService()
    assert service.property_suite({name: True for name in service.PROPERTY_INVARIANTS})
    assert service.contract_suite({name: True for name in service.CONTRACT_SURFACES})
    assert service.concurrency_suite({name: True for name in service.CONCURRENCY_CASES})
    assert service.security_suite({name: True for name in service.SECURITY_CASES})
    assert (
        service.payment_sandbox_evidence(sandbox_receipt=None, settlement_sample_digest=None)
        is ExternalExecutionState.NOT_RUN
    )
    assert service.shadow_billing(
        old_total=Decimal("100.00"),
        new_total=Decimal("100.01"),
        tolerance=Decimal("0.02"),
        explanation="rounding version changed",
    )


def test_eb17_binding_separates_executor_verifier_and_gate_never_certifies() -> None:
    binding = VerificationBinding(
        requirement_id="EB-01-001",
        test_node_ids=("tests/test.py::test_case",),
        evidence_digests=("a" * 64,),
        executor="executor",
        verifier="verifier",
        authorization_id="authorization-1",
    )
    BillingQualificationService.require_complete_binding(binding)
    report = BillingQualificationService.certify(
        environment_id="local-macos",
        commit="b" * 40,
        bindings=(binding,),
        p0_failures=(),
        critical_invariant_failures=(),
        external_levels={"payment-sandbox": ExternalExecutionState.NOT_RUN},
    )
    assert not report.eligible
    assert report.decision is CertificationState.NOT_CERTIFIED
    assert report.external_execution is ExternalExecutionState.NOT_RUN
    with pytest.raises(DomainError, match="executor and verifier must differ"):
        BillingQualificationService.require_complete_binding(
            VerificationBinding(
                requirement_id="EB-01-002",
                test_node_ids=("tests/test.py::test_case",),
                evidence_digests=("c" * 64,),
                executor="same",
                verifier="same",
                authorization_id="authorization-1",
            )
        )


def test_eb18_quality_opening_record_shadow_authority_wave_and_rollback() -> None:
    service = BillingMigrationService()
    anomalies = service.assess_data_quality(
        tenant_id="tenant-a",
        source_id="legacy-wallet-1",
        facts={"balance": "unknown"},
        anomaly_kinds=("MISSING_CURRENCY", "DUPLICATE_ACCOUNT"),
    )
    debit, credit = service.opening_balance_entries(
        tenant_id="tenant-a",
        currency="USD",
        amount=Decimal("100"),
        reference="legacy-wallet-1",
    )
    record = service.register_record(
        migration_id="migration-1",
        tenant_id="tenant-a",
        source_id="legacy-wallet-1",
        source_payload={"balance": "100", "currency": "USD"},
        source_version="legacy-v3",
        approved_by="migration-checker",
        target={"entry_ids": ["debit", "credit"]},
    )
    shadow = service.shadow_rate(
        tenant_id="tenant-a",
        source_id="legacy-invoice-1",
        legacy_amount=Decimal("10.00"),
        new_amount=Decimal("10.01"),
        tolerance=Decimal("0.02"),
        explanation="price book precision changed",
    )
    assert service.set_authority(tenant_id="tenant-a", authority=MigrationAuthority.LEGACY) is MigrationAuthority.LEGACY
    assert service.set_authority(tenant_id="tenant-a", authority=MigrationAuthority.SHADOW) is MigrationAuthority.SHADOW
    assert service.set_authority(tenant_id="tenant-a", authority=MigrationAuthority.NEW) is MigrationAuthority.NEW
    wave = service.create_wave(wave_id="wave-1", tenant_ids=("tenant-a",), risk_tier="LOW")
    rolled_back = service.apply_rollback_signals(wave_id=wave.wave_id, signals=("SHADOW_DRIFT",))

    assert len(anomalies) == 2
    assert debit["amount"] + credit["amount"] == Decimal("0")
    assert record.source_hash and record.approved_by == "migration-checker"
    assert shadow.within_tolerance
    assert rolled_back.state == "ROLLED_BACK"


def test_eb18_cutover_customer_plan_and_legacy_retention_stay_human_gated() -> None:
    service = BillingMigrationService()
    blocked = service.cutover_reconciliation(
        ledger_digest="a" * 64,
        invoice_digest=None,
        payment_digest="b" * 64,
        final_incremental_digest="c" * 64,
    )
    complete = service.cutover_reconciliation(
        ledger_digest="a" * 64,
        invoice_digest="d" * 64,
        payment_digest="b" * 64,
        final_incremental_digest="c" * 64,
    )
    support = service.customer_support_plan(
        notification_template="migration notice",
        support_runbook="support/runbook-v1",
        dispute_fast_track="queue/priority-billing",
    )
    legacy = service.retain_legacy(
        tenant_id="tenant-a",
        read_only=True,
        audit_available=True,
        rollback_available=True,
    )

    assert blocked["decision"] == "BLOCKED"
    assert complete["decision"] == "READY_FOR_HUMAN_DECISION"
    assert complete["external_execution"] is ExternalExecutionState.NOT_RUN
    assert complete["certification"] is CertificationState.NOT_CERTIFIED
    assert len(str(support["digest"])) == 64
    assert legacy["decommission_allowed"] is False
