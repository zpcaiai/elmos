from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from elmos_pricing_billing.errors import DomainError
from elmos_pricing_billing.operations_closure import (
    BackendRuleDecision,
    BillingAdminExperienceService,
    BillingDrilldown,
    BillingObservabilityOperationsService,
    BillingSecurityComplianceService,
    BudgetAction,
    CertificationState,
    CostCenterBudget,
    ExternalExecutionState,
    HighRiskActionState,
    OperationsMode,
    ProjectCommercialView,
    SecretReference,
    SloDefinition,
)

NOW = datetime(2026, 8, 26, tzinfo=UTC)


def test_eb14_quote_run_wallet_drilldown_and_project_views_are_exact() -> None:
    service = BillingAdminExperienceService()
    quote = service.quote_card(
        tenant_id="tenant-a",
        quote_id="quote-1",
        currency="usd",
        low=Decimal("10.00"),
        expected=Decimal("12.50"),
        high=Decimal("15.00"),
        hard_cap=Decimal("20.00"),
        machine_eta_seconds=90,
        human_reference_seconds=3600,
        mode="BALANCED",
        test_plan=("unit", "contract"),
        acceptance_criteria=("ledger-balanced",),
        pricing_version="book-7",
    )
    run = service.run_budget(
        tenant_id="tenant-a",
        run_id="run-1",
        currency="USD",
        used=Decimal("4"),
        reserved=Decimal("5"),
        projected_remaining=Decimal("6"),
        hard_cap=Decimal("20"),
        threshold_percents=(50, 80, 100),
    )
    wallet = service.wallet(
        tenant_id="tenant-a",
        currency="USD",
        paid=Decimal("100"),
        promotional=Decimal("20"),
        reserved=Decimal("10"),
        consumed=Decimal("40"),
        refunded=Decimal("5"),
        expired=Decimal("5"),
    )
    row = BillingDrilldown("tenant-a", "inv", "task", "run", "node", "gpu", Decimal("1.25"), "USD")
    project = ProjectCommercialView("tenant-a", "project", "scope-digest", ("M1",), ("M1",), ("CO-1",))

    assert quote.currency == "USD"
    assert set(run.allowed_actions) == set(BudgetAction)
    assert wallet.paid != wallet.promotional
    assert service.drilldown((row,), tenant_id="tenant-a") == (row,)
    assert service.project_view(project, tenant_id="tenant-a") == project


def test_eb14_cost_center_high_risk_backend_authority_and_resume() -> None:
    service = BillingAdminExperienceService()
    budget = service.define_cost_center(
        CostCenterBudget("tenant-a", "cc-1", "engineering", "usd", Decimal("1000"), ("approver",))
    )
    requested = service.request_high_risk(
        action_id="action-1",
        tenant_id="tenant-a",
        action="refund:override",
        preview={"amount": "10.00", "currency": "USD"},
        requested_by="maker",
    )
    with pytest.raises(DomainError, match="requester cannot approve"):
        service.approve_high_risk(action_id=requested.action_id, tenant_id="tenant-a", approved_by="maker")
    approved = service.approve_high_risk(action_id=requested.action_id, tenant_id="tenant-a", approved_by="checker")
    decision = service.backend_rule(
        tenant_id="tenant-a",
        rule_id="refund-limit",
        rule_version="3",
        facts={"amount": "10.00"},
        allowed=True,
        reason="within approved limit",
    )
    executed = service.execute_high_risk(
        action_id=requested.action_id,
        tenant_id="tenant-a",
        preview={"amount": "10.00", "currency": "USD"},
        backend_decision=decision,
    )
    token = service.save_resume_token(tenant_id="tenant-a", journey_id="billing-journey", state={"step": 3})
    money = service.accessible_money(amount=Decimal("12.30"), currency="eur", locale="fr-FR")

    assert budget.currency == "USD"
    assert approved.state is HighRiskActionState.APPROVED
    assert executed.state is HighRiskActionState.EXECUTED
    assert executed.audit_digest
    assert service.resume(tenant_id="tenant-a", journey_id="billing-journey", token=token)
    assert money["aria_label"] == "12.30 EUR"


def test_eb15_tenant_sod_secret_encryption_and_audit_chain_fail_closed() -> None:
    service = BillingSecurityComplianceService()
    allowed = service.authorize(
        principal_id="principal",
        principal_tenant_id="tenant-a",
        resource_tenant_id="tenant-a",
        role="APPROVER",
        action="refund:approve",
        policy_version="policy-2",
    )
    denied = service.authorize(
        principal_id="principal",
        principal_tenant_id="tenant-a",
        resource_tenant_id="tenant-b",
        role="APPROVER",
        action="refund:approve",
        policy_version="policy-2",
    )
    service.require_dual_approval(requested_by="maker", approved_by="checker", action="refund:approve")
    binding = service.encryption_binding(
        in_transit_policy="mTLS1.3",
        at_rest_key=SecretReference("secret://tenant-a/kms/at-rest"),
        backup_key=service.secret_reference("secret://tenant-a/kms/backup"),
    )
    service.append_audit(
        tenant_id="tenant-a",
        actor="principal",
        action="authorization:decision",
        occurred_at=NOW,
        payload={"allowed": True},
    )
    service.append_audit(
        tenant_id="tenant-a",
        actor="principal",
        action="ledger:write",
        occurred_at=NOW,
        payload={"entry": "entry-1"},
    )

    assert allowed.allowed
    assert not denied.allowed and denied.reason == "TENANT_MISMATCH"
    assert binding["external_execution"] is ExternalExecutionState.NOT_RUN
    assert service.verify_audit(tenant_id="tenant-a")
    with pytest.raises(DomainError, match="raw secrets are forbidden"):
        SecretReference("plaintext-secret")


def test_eb15_fraud_redaction_privacy_surfaces_and_red_team_remain_bounded() -> None:
    service = BillingSecurityComplianceService()
    assessment = service.assess_fraud(
        tenant_id="tenant-a",
        assessment_id="fraud-1",
        topup_count=6,
        refund_ratio=Decimal("0.6"),
        concurrent_sessions=12,
        account_takeover_signal=True,
        bot_score=Decimal("0.9"),
        rules_version="rules-1",
    )
    redacted = service.redact({"authorization": "Bearer raw", "safe": "value", "prompt": "private"})
    privacy = service.request_privacy_action(
        request_id="privacy-1",
        tenant_id="tenant-a",
        subject_id="subject-1",
        kind="DELETE",
        legal_hold_reason="invoice retention",
    )
    policy_digest = service.validate_surface_policy(
        {surface: "policy-1" for surface in BillingSecurityComplianceService.REQUIRED_SURFACES}
    )
    gate = service.red_team_release_gate(
        {
            "authorization": ExternalExecutionState.LOCAL_EXECUTED,
            "replay": ExternalExecutionState.NOT_RUN,
            "race": ExternalExecutionState.NOT_RUN,
            "injection": ExternalExecutionState.NOT_RUN,
            "secret-leak": ExternalExecutionState.NOT_RUN,
        }
    )

    assert assessment.blocked and len(assessment.signals) == 5
    assert redacted == {"authorization": "[REDACTED]", "safe": "value", "prompt": "[REDACTED]"}
    assert privacy.state == "BLOCKED_LEGAL_HOLD"
    assert len(policy_digest) == 64
    assert gate["ready"] is False
    assert gate["certification"] is CertificationState.NOT_CERTIFIED


def test_eb16_trace_signals_slos_kill_switch_queue_and_recovery() -> None:
    service = BillingObservabilityOperationsService()
    for stage in ("quote", "authorization", "usage", "invoice", "payment", "refund", "reconciliation"):
        service.record_trace(
            tenant_id="tenant-a",
            correlation_id="corr-1",
            stage=stage,
            subject_id=f"{stage}-1",
            occurred_at=NOW,
            facts={"stage": stage},
        )
    for operation in BillingObservabilityOperationsService.SLO_OPERATIONS:
        service.configure_slo(SloDefinition(operation, 9_900, 300, "slo-1"))
    service.observe_signal(
        tenant_id="tenant-a",
        kind="LEDGER_IMBALANCE",
        subject_id="ledger-1",
        severity="CRITICAL",
        facts={"delta": "1.00"},
    )
    item = service.enqueue(
        work_id="work-1",
        tenant_id="tenant-a",
        kind="STUCK_SAGA",
        subject_id="saga-1",
        correlation_id="corr-1",
    )
    assigned = service.assign(work_id=item.work_id, tenant_id="tenant-a", assigned_to="operator")
    replay = service.replay(work_id=assigned.work_id, tenant_id="tenant-a", new_work_id="work-2")
    verification = service.verify_recovery(
        tenant_id="tenant-a",
        before={"ledger": "a"},
        after={"ledger": "a"},
        ledger_balanced=True,
        idempotency_preserved=True,
        reconciliation_matched=True,
    )

    assert len(service.trace(tenant_id="tenant-a", correlation_id="corr-1")) == 7
    assert service.slo_complete()
    assert service.mode(tenant_id="tenant-a") is OperationsMode.KILLED
    with pytest.raises(DomainError, match="financial writes are disabled"):
        service.assert_mutable(tenant_id="tenant-a")
    assert replay.replay_of == "work-1"
    assert service.recovery_ready(verification)


def test_eb16_backup_dr_and_incident_contracts_do_not_claim_execution() -> None:
    service = BillingObservabilityOperationsService()
    contract = service.backup_dr_contract(
        asset_kinds=("ledger", "contract", "invoice", "audit"),
        rpo_seconds=300,
        rto_seconds=1800,
    )
    incident = service.incident_report(
        incident_id="incident-1",
        timeline=("detected", "contained", "reconciled"),
        financial_impact={"currency": "USD", "amount": "0.00"},
        root_cause="local synthetic invariant signal",
        prevention_actions=("add negative test",),
    )

    assert contract["backup_execution"] is ExternalExecutionState.NOT_RUN
    assert contract["restore_drill"] is ExternalExecutionState.NOT_RUN
    assert contract["certification"] is CertificationState.NOT_CERTIFIED
    assert len(str(incident["digest"])) == 64


def test_backend_rule_decision_cannot_cross_tenant() -> None:
    service = BillingAdminExperienceService()
    requested = service.request_high_risk(
        action_id="action-x",
        tenant_id="tenant-a",
        action="budget:add",
        preview={"amount": "1"},
        requested_by="maker",
    )
    service.approve_high_risk(action_id=requested.action_id, tenant_id="tenant-a", approved_by="checker")
    decision = BackendRuleDecision("tenant-b", "rule", "1", "digest", True, "allowed")
    with pytest.raises(DomainError, match="decision tenant mismatch"):
        service.execute_high_risk(
            action_id=requested.action_id,
            tenant_id="tenant-a",
            preview={"amount": "1"},
            backend_decision=decision,
        )
