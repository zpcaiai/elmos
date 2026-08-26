from __future__ import annotations

import importlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pytest

from elmos_pricing_billing.cli import main
from elmos_pricing_billing.engine import PricingBillingEngine
from elmos_pricing_billing.errors import DomainError
from elmos_pricing_billing.ledger import LedgerService
from elmos_pricing_billing.models import ChargeAuthority, MigrationMode, ReadinessState, canonical_digest
from elmos_pricing_billing.money import MAX_I64, Money
from elmos_pricing_billing.operations import (
    AuditOperationsService,
    MarginAnalyticsService,
    MigrationService,
    SecurityComplianceService,
)
from elmos_pricing_billing.registry import (
    DOMAIN_HANDLER_NAMES,
    REQUIREMENT_BINDINGS,
    SKILL_HANDLER_BINDINGS,
    LocalImplementationState,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)

EXPECTED_SKILL_NAMES = (
    "elmos-billing-orchestrator",
    "elmos-pricing-product-model",
    "elmos-plan-catalog-entitlements",
    "elmos-credit-wallet-ledger",
    "elmos-usage-metering",
    "elmos-task-cost-estimation",
    "elmos-quote-budget-guard",
    "elmos-project-pricing-contracts",
    "elmos-subscription-invoicing",
    "elmos-payments-reconciliation",
    "elmos-refunds-disputes",
    "elmos-enterprise-byok",
    "elmos-cost-margin-analytics",
    "elmos-billing-admin-ux",
    "elmos-security-compliance",
    "elmos-billing-observability-ops",
    "elmos-billing-testing-certification",
    "elmos-rollout-migration",
)


def test_engine_demo_is_repeatable_and_ceiling_is_local() -> None:
    engine = PricingBillingEngine()
    first_report, first_observations = engine.run_local_demo()
    second_report, second_observations = engine.run_local_demo()

    assert first_report == second_report
    assert first_observations == second_observations
    assert first_report.readiness is ReadinessState.LOCAL_EXECUTED
    assert engine.external_boundaries_are_unexecuted(first_report)
    assert tuple(engine.handlers) == EXPECTED_SKILL_NAMES
    assert all(state is LocalImplementationState.LOCAL_EXECUTED for _, state in first_report.handler_results)

    first_observations[EXPECTED_SKILL_NAMES[0]] = False
    _, third_observations = engine.run_local_demo()
    assert third_observations[EXPECTED_SKILL_NAMES[0]] is True


def test_qualification_manifest_maps_all_skills_and_requirements(capsys: pytest.CaptureFixture[str]) -> None:
    engine = PricingBillingEngine()
    manifest = engine.local_qualification_manifest()

    assert DOMAIN_HANDLER_NAMES == EXPECTED_SKILL_NAMES
    assert manifest.skill_count == len(SKILL_HANDLER_BINDINGS) == 18
    assert manifest.requirement_count == len(REQUIREMENT_BINDINGS) == 180
    assert manifest.maximum_readiness is LocalImplementationState.LOCAL_EXECUTED
    assert manifest.persistence_scope == "IN_MEMORY_SAME_PROCESS_ONLY"
    assert manifest.persistence_contract_state is LocalImplementationState.NOT_RUN
    assert tuple(entry.skill_name for entry in manifest.skills) == EXPECTED_SKILL_NAMES
    assert {entry.handler_execution_state for entry in manifest.skills} == {LocalImplementationState.LOCAL_EXECUTED}
    assert Counter(entry.domain_implementation_state for entry in manifest.skills) == {
        LocalImplementationState.LOCAL_EXECUTED: 16,
        LocalImplementationState.PARTIAL: 2,
    }

    expected_requirement_ids = tuple(
        f"EB-{skill_number:02d}-{requirement_number:03d}"
        for skill_number in range(1, 19)
        for requirement_number in range(1, 11)
    )
    assert tuple(entry.requirement_id for entry in manifest.requirements) == expected_requirement_ids
    assert Counter(entry.local_state for entry in manifest.requirements) == {
        LocalImplementationState.LOCAL_EXECUTED: 163,
        LocalImplementationState.PARTIAL: 12,
        LocalImplementationState.NOT_RUN: 5,
    }
    assert all("PASS" not in entry.local_state for entry in manifest.requirements)
    assert dict(manifest.external_boundaries)["certification"] == "NOT_CERTIFIED"
    assert all(state in {"NOT_RUN", "NOT_CERTIFIED"} for _, state in manifest.external_boundaries)

    for skill_number, binding in enumerate(SKILL_HANDLER_BINDINGS, start=1):
        assert binding.requirement_ids == tuple(
            f"EB-{skill_number:02d}-{requirement_number:03d}" for requirement_number in range(1, 11)
        )
        module_name, symbol_name = binding.handler_symbol.rsplit(".", 1)
        expected_type = getattr(importlib.import_module(module_name), symbol_name)
        assert expected_type is not None
        assert type(engine.handler(binding.skill_name)) is expected_type
        assert engine.runtime_artifacts[binding.skill_name] == binding.supporting_artifacts
        for node_id in binding.test_node_ids:
            test_path, test_name = node_id.split("::", 1)
            source = (Path(__file__).resolve().parents[1] / test_path).read_text(encoding="utf-8")
            assert f"def {test_name}(" in source

    assert main(["manifest"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["implementation_manifest"]["skill_count"] == 18
    assert payload["implementation_manifest"]["requirement_count"] == 180
    assert payload["implementation_manifest"]["artifact_count"] == 12
    assert payload["implementation_manifest"]["persistence_contract_state"] == "NOT_RUN"
    assert payload["qualification"]["readiness"] == "LOCAL_EXECUTED"
    assert payload["persistence_scope"] == "IN_MEMORY_SAME_PROCESS_ONLY"


def test_registry_uses_concrete_handlers_and_keeps_external_evidence_not_run() -> None:
    engine = PricingBillingEngine()
    manifest = engine.local_qualification_manifest()
    handler_symbols = tuple(binding.handler_symbol for binding in SKILL_HANDLER_BINDINGS)

    assert len(handler_symbols) == len(set(handler_symbols)) == 18
    assert all(".engine.PricingBillingEngine" not in symbol for symbol in handler_symbols)
    assert all("dispatcher" not in symbol.casefold() for symbol in handler_symbols)
    assert manifest.artifact_count == len(manifest.artifacts) == 12

    repository_root = Path(__file__).resolve().parents[3]
    for artifact in manifest.artifacts:
        source = repository_root / artifact.source_path
        assert source.is_file()
        assert artifact.local_test_state is LocalImplementationState.LOCAL_EXECUTED
        assert artifact.external_evidence_state == "NOT_RUN"
        assert artifact.certification_state == "NOT_CERTIFIED"
        for test_path in artifact.test_paths:
            assert (repository_root / test_path).is_file()
        source_text = source.read_text(encoding="utf-8")
        if artifact.language == "JAVA":
            assert f"class {artifact.symbol.rsplit('.', 1)[1]}" in source_text
        else:
            assert artifact.language == "SQL"
            assert "NOT_CERTIFIED" not in source_text or "not certif" in source_text.casefold()

    assert dict(manifest.external_boundaries) == {
        "payment_sandbox": "NOT_RUN",
        "payment_provider": "NOT_RUN",
        "bank_settlement": "NOT_RUN",
        "tax_engine": "NOT_RUN",
        "accounting_system_of_record": "NOT_RUN",
        "disaster_recovery": "NOT_RUN",
        "customer_acceptance": "NOT_RUN",
        "production_execution": "NOT_RUN",
        "independent_verification": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
    }


def test_canonical_digest_accepts_only_deterministic_json_values() -> None:
    assert canonical_digest({"b": [2, 1], "a": {"value": 3}}) == canonical_digest(
        {"a": {"value": 3}, "b": [2, 1]}
    )
    with pytest.raises(DomainError, match="CANONICAL_VALUE_UNSUPPORTED"):
        canonical_digest({"float": 1.0})
    with pytest.raises(DomainError, match="CANONICAL_MAPPING_KEY_INVALID"):
        canonical_digest({1: "not-a-string-key"})


def test_operations_kill_switch_replay_and_audit_are_tenant_scoped() -> None:
    operations = AuditOperationsService()
    first_a = operations.record_audit(
        tenant_id="tenant-a",
        correlation_id="corr-a",
        actor="actor-a",
        action="read",
        outcome="LOCAL_EXECUTED",
        occurred_at=NOW,
        details={"tenant": "a"},
    )
    first_b = operations.record_audit(
        tenant_id="tenant-b",
        correlation_id="corr-b",
        actor="actor-b",
        action="read",
        outcome="LOCAL_EXECUTED",
        occurred_at=NOW,
        details={"tenant": "b"},
    )
    assert first_a.sequence == first_b.sequence == 1

    work = operations.enqueue(
        work_id="work-a",
        tenant_id="tenant-a",
        correlation_id="corr-a",
        operation="reconcile-local",
    )
    operations.claim(work_id=work.work_id, tenant_id="tenant-a")
    operations.fail(work_id=work.work_id, tenant_id="tenant-a", error_code="TRANSIENT")
    replay = operations.replay(failed_work_id=work.work_id, new_work_id="work-a-replay", tenant_id="tenant-a")
    assert replay.replay_of == work.work_id and replay.attempt == 2
    with pytest.raises(DomainError, match="TENANT_ISOLATION_VIOLATION"):
        operations.claim(work_id=replay.work_id, tenant_id="tenant-b")

    with pytest.raises(DomainError, match="CORRELATION_ID_REQUIRED"):
        operations.set_kill_switch(
            tenant_id="tenant-a",
            enabled=True,
            actor="operator",
            correlation_id="",
            occurred_at=NOW,
        )
    assert not operations.is_killed(tenant_id="tenant-a")
    with pytest.raises(DomainError, match="WILDCARD_TENANT_FORBIDDEN"):
        operations.set_kill_switch(
            tenant_id="*",
            enabled=True,
            actor="operator",
            correlation_id="corr-wildcard",
            occurred_at=NOW,
        )
    operations.set_kill_switch(
        tenant_id="tenant-a",
        enabled=True,
        actor="operator",
        correlation_id="corr-kill",
        occurred_at=NOW,
    )
    with pytest.raises(DomainError, match="KILL_SWITCH_ACTIVE"):
        operations.enqueue(
            work_id="blocked",
            tenant_id="tenant-a",
            correlation_id="corr-blocked",
            operation="bill-local",
        )
    assert not operations.is_killed(tenant_id="tenant-b")
    assert all(event.tenant_id == "tenant-a" for event in operations.audit_events(tenant_id="tenant-a"))


def test_security_denies_cross_tenant_and_unknown_role_with_audit() -> None:
    operations = AuditOperationsService()
    security = SecurityComplianceService(operations)
    allowed = security.authorize(
        principal_id="approver",
        principal_tenant_id="tenant-a",
        resource_tenant_id="tenant-a",
        role="APPROVER",
        action="refund:approve",
        correlation_id="corr-allow",
        occurred_at=NOW,
    )
    cross_tenant = security.authorize(
        principal_id="viewer",
        principal_tenant_id="tenant-b",
        resource_tenant_id="tenant-a",
        role="VIEWER",
        action="billing:read",
        correlation_id="corr-cross",
        occurred_at=NOW,
    )
    unknown_role = security.authorize(
        principal_id="unknown",
        principal_tenant_id="tenant-a",
        resource_tenant_id="tenant-a",
        role="ROOT",
        action="billing:read",
        correlation_id="corr-unknown",
        occurred_at=NOW,
    )
    assert allowed.allowed
    assert not cross_tenant.allowed and cross_tenant.reason == "TENANT_MISMATCH"
    assert not unknown_role.allowed and unknown_role.reason == "ACTION_NOT_GRANTED"
    assert len(operations.audit_events(tenant_id="tenant-a")) == 3
    assert security.validate_secret_reference("secret://tenant-a/key") == "secret://tenant-a/key"
    with pytest.raises(DomainError, match="INLINE_SECRET_FORBIDDEN"):
        security.validate_secret_reference("secret://key=value")


def test_margin_is_integer_exact_and_read_only() -> None:
    view = MarginAnalyticsService.calculate(
        currency="USD",
        revenue_minor=10_000,
        provider_cost_minor=6_000,
        runner_cost_minor=3_000,
        support_cost_minor=2_000,
    )
    assert view.margin_minor == -1_000
    assert view.margin_basis_points == -1_000
    with pytest.raises(DomainError, match="INTEGER_OVERFLOW"):
        MarginAnalyticsService.calculate(
            currency="USD",
            revenue_minor=MAX_I64,
            provider_cost_minor=MAX_I64,
            runner_cost_minor=1,
            support_cost_minor=0,
        )


def test_admin_projection_is_tenant_scoped() -> None:
    engine = PricingBillingEngine()
    engine.run_local_demo()
    tenant_snapshot = engine.admin.snapshot(tenant_id="tenant-demo", currency="USD")
    other_snapshot = engine.admin.snapshot(tenant_id="tenant-other", currency="USD")
    assert tenant_snapshot.rated_usage_count == 1
    assert tenant_snapshot.work_item_count == 2
    assert other_snapshot.rated_usage_count == 0
    assert other_snapshot.suspense_count == 0
    assert other_snapshot.work_item_count == 0


def test_migration_remains_local_simulation_and_opening_is_idempotent() -> None:
    ledger = LedgerService()
    migration = MigrationService(ledger)
    first = migration.import_opening_balance(
        tenant_id="tenant",
        money=Money("USD", 1_000),
        source_snapshot_digest="snapshot-v1",
        occurred_at=NOW,
    )
    repeated = migration.import_opening_balance(
        tenant_id="tenant",
        money=Money("USD", 1_000),
        source_snapshot_digest="snapshot-v1",
        occurred_at=NOW,
    )
    assert first == repeated
    assert len(ledger.transactions(tenant_id="tenant")) == 1
    with pytest.raises(DomainError, match="OPENING_BALANCE_CONFLICT"):
        migration.import_opening_balance(
            tenant_id="tenant",
            money=Money("USD", 1_000),
            source_snapshot_digest="snapshot-v2",
            occurred_at=NOW,
        )

    shadow_decision = migration.charge_decision(tenant_id="tenant")
    assert shadow_decision.authority is ChargeAuthority.EXTERNAL_SYSTEM_NOT_INVOKED
    assert shadow_decision.simulation_only
    migration.set_canary(tenant_id="tenant", enabled=True)
    migration.set_mode(mode=MigrationMode.CANARY)
    canary_decision = migration.charge_decision(tenant_id="tenant")
    assert canary_decision.authority is ChargeAuthority.LOCAL_SIMULATION
    assert canary_decision.simulation_only
    with pytest.raises(DomainError, match="PRODUCTION_AUTHORITY_FORBIDDEN"):
        MigrationService(ledger, environment="production")


def test_local_budget_scenario_exercises_reserve_idempotency_capture_and_release(
    capsys: pytest.CaptureFixture[str],
) -> None:
    scenario = PricingBillingEngine.run_local_budget_scenario()
    assert scenario["hard_cap_minor"] == scenario["reserved_at_accept_minor"] == 12_000
    assert scenario["idempotent_repeat_stable"] is True
    assert scenario["committed_spend_minor"] == scenario["captured_minor"] == 11_500
    assert scenario["reserved_minor"] == 0
    assert scenario["external_side_effects"] is False

    assert main(["scenario"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["scenario"]["captured_minor"] == 11_500
    assert payload["scenario"]["authority"] == "LOCAL_REFERENCE_ONLY"
