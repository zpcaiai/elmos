from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256

import pytest

import elmos_pricing_billing.commercial_closure as cc
from elmos_pricing_billing.errors import DomainError

NOW = datetime(2026, 8, 26, tzinfo=UTC)


def money(value: str, currency: str = "USD") -> cc.ExactAmount:
    return cc.ExactAmount(currency, Decimal(value))


def pricing_components() -> tuple[cc.RateComponent, ...]:
    return tuple(
        cc.RateComponent(
            kind=kind,
            unit_name=f"{kind.value.lower()}-unit",
            managed_rate_micro=100 + index,
            byok_rate_micro=0 if kind is cc.RateComponentKind.MODEL else 40 + index,
        )
        for index, kind in enumerate(cc.RateComponentKind)
    )


def pricing_rules() -> tuple[cc.TaskBillingRule, ...]:
    return tuple(
        cc.TaskBillingRule(task_kind=f"task-{index}", route=route)
        for index, route in enumerate(cc.BillingRoute)
    )


def project_sku() -> cc.ProjectSkuContract:
    return cc.ProjectSkuContract(
        sku_id="sku",
        input_contract_digest="input",
        output_contract_digest="output",
        maximum_scope_units=10,
        acceptance_policy_digest="acceptance",
        included_revision_rounds=2,
    )


def approved_pricing(*, example_only: bool = False) -> tuple[cc.PricingProductClosureService, cc.PriceProductVersion]:
    service = cc.PricingProductClosureService()
    draft = service.create_version(
        tenant_id="tenant",
        book_id="book",
        version=1,
        currency="USD",
        effective_from=NOW,
        effective_to=NOW + timedelta(days=30),
        created_by="maker",
        rate_components=pricing_components(),
        billing_rules=pricing_rules(),
        project_skus=(project_sku(),),
        example_only=example_only,
        impact_targets=("quotes", "subscriptions", "projects"),
        occurred_at=NOW,
    )
    approved = service.approve(
        tenant_id="tenant",
        book_id="book",
        version=1,
        expected_digest=draft.digest,
        approved_by="checker",
        explicit_example_authorization=example_only,
        occurred_at=NOW,
    )
    return service, approved


def plan_definition(*, version: int = 1, tier: cc.PlanTier = cc.PlanTier.PRO) -> cc.PlanDefinition:
    return cc.PlanDefinition(
        tenant_id="tenant",
        plan_id="plan",
        version=version,
        tier=tier,
        seat_limit=5,
        concurrent_task_limit=1,
        model_tier="balanced",
        retention_days=30,
        storage_bytes=1_000_000,
        features=("run", "export"),
        paid_credit_minor=1_000,
        promotional_credit_minor=200,
        published_at=NOW + timedelta(minutes=version),
    )


def active_plan_service() -> tuple[cc.PlanEntitlementClosureService, cc.SubscriptionEntitlementSnapshot]:
    service = cc.PlanEntitlementClosureService()
    service.publish_plan(plan_definition())
    snapshot = service.activate(
        tenant_id="tenant",
        subscription_id="subscription",
        plan_id="plan",
        plan_version=1,
        trial=False,
        enterprise_override_id=None,
        enterprise_override_version=None,
        idempotency_key="activate",
    )
    return service, snapshot


def test_eb02_001_supports_six_explicit_commercial_routes() -> None:
    service, _ = approved_pricing()
    assert {
        service.resolve_route(tenant_id="tenant", book_id="book", version=1, task_kind=f"task-{index}")
        for index in range(6)
    } == set(cc.BillingRoute)


def test_eb02_002_presents_money_and_credits_with_tokens_as_detail_only() -> None:
    service, _ = approved_pricing()
    presentation = service.present_price(
        tenant_id="tenant",
        book_id="book",
        version=1,
        customer_amount_minor=500,
        execution_credit_units=25,
        raw_token_units=9_000,
    )
    assert (presentation.customer_amount_minor, presentation.execution_credit_units) == (500, 25)
    assert presentation.raw_token_units_cost_detail == 9_000


def test_eb02_003_price_book_binds_currency_window_state_approval_and_version() -> None:
    _, approved = approved_pricing()
    assert (approved.currency, approved.version, approved.state, approved.approved_by) == (
        "USD",
        1,
        cc.CommercialRecordState.APPROVED,
        "checker",
    )
    assert approved.effective_to == NOW + timedelta(days=30)


def test_eb02_004_six_rate_components_are_independently_addressable() -> None:
    service, _ = approved_pricing()
    rates = {
        kind: service.rate_component(
            tenant_id="tenant",
            book_id="book",
            version=1,
            kind=kind,
            funding=cc.ModelFunding.MANAGED,
        )
        for kind in cc.RateComponentKind
    }
    assert len(rates) == 6
    assert len(set(rates.values())) == 6


def test_eb02_005_managed_and_byok_use_distinct_model_rate_composition() -> None:
    service, _ = approved_pricing()
    managed = service.rate_component(
        tenant_id="tenant",
        book_id="book",
        version=1,
        kind=cc.RateComponentKind.MODEL,
        funding=cc.ModelFunding.MANAGED,
    )
    byok = service.rate_component(
        tenant_id="tenant",
        book_id="book",
        version=1,
        kind=cc.RateComponentKind.MODEL,
        funding=cc.ModelFunding.BYOK,
    )
    assert managed > 0 and byok == 0


def test_eb02_006_task_kind_routes_deterministically() -> None:
    service, _ = approved_pricing()
    assert service.resolve_route(
        tenant_id="tenant", book_id="book", version=1, task_kind="task-2"
    ) is cc.BillingRoute.ACTUAL_USAGE
    with pytest.raises(DomainError, match="TASK_BILLING_ROUTE_NOT_FOUND"):
        service.resolve_route(tenant_id="tenant", book_id="book", version=1, task_kind="unknown")


def test_eb02_007_project_sku_enforces_machine_verifiable_contract() -> None:
    project_sku().validate_delivery(input_digest="input", output_digest="output", scope_units=10)
    with pytest.raises(DomainError, match="SKU_SCOPE_LIMIT_EXCEEDED"):
        project_sku().validate_delivery(input_digest="input", output_digest="output", scope_units=11)


def test_eb02_008_price_experiment_is_stable_and_rollback_preserves_price_history() -> None:
    service, version = approved_pricing()
    second = service.create_version(
        tenant_id="tenant",
        book_id="book",
        version=2,
        currency="USD",
        effective_from=NOW + timedelta(days=30),
        effective_to=NOW + timedelta(days=60),
        created_by="maker",
        rate_components=pricing_components(),
        billing_rules=pricing_rules(),
        project_skus=(project_sku(),),
        example_only=False,
        impact_targets=("quotes",),
        occurred_at=NOW,
    )
    second = service.approve(
        tenant_id="tenant",
        book_id="book",
        version=2,
        expected_digest=second.digest,
        approved_by="checker",
        explicit_example_authorization=False,
        occurred_at=NOW,
    )
    service.configure_experiment(
        tenant_id="tenant",
        experiment_id="experiment",
        book_id="book",
        control_version=1,
        variant_version=2,
        allocation_basis_points=5_000,
        actor="operator",
        occurred_at=NOW,
    )
    assert service.assign_experiment(tenant_id="tenant", experiment_id="experiment", subject_key="subject") in {1, 2}
    service.rollback_experiment(tenant_id="tenant", experiment_id="experiment", actor="operator", occurred_at=NOW)
    assert service.assign_experiment(tenant_id="tenant", experiment_id="experiment", subject_key="subject") == 1
    assert service.history(tenant_id="tenant", book_id="book")[0].digest == version.digest
    assert second.version == 2


def test_eb02_009_example_price_requires_explicit_authorization() -> None:
    service = cc.PricingProductClosureService()
    draft = service.create_version(
        tenant_id="tenant",
        book_id="example",
        version=1,
        currency="USD",
        effective_from=NOW,
        effective_to=None,
        created_by="maker",
        rate_components=pricing_components(),
        billing_rules=pricing_rules(),
        project_skus=(project_sku(),),
        example_only=True,
        impact_targets=("quotes",),
        occurred_at=NOW,
    )
    with pytest.raises(DomainError, match="EXAMPLE_PRICE_PRODUCTION_FORBIDDEN"):
        service.approve(
            tenant_id="tenant",
            book_id="example",
            version=1,
            expected_digest=draft.digest,
            approved_by="checker",
            explicit_example_authorization=False,
            occurred_at=NOW,
        )


def test_eb02_010_price_changes_emit_digest_bound_impact_audit() -> None:
    service, approved = approved_pricing()
    events = service.audit_events(tenant_id="tenant")
    assert [event.action for event in events] == ["CREATE_VERSION", "APPROVE_VERSION"]
    assert events[-1].after_digest == approved.digest
    assert events[-1].impact_targets == ("quotes", "subscriptions", "projects")


@pytest.mark.parametrize("tier", tuple(cc.PlanTier))
def test_eb03_001_catalog_supports_all_configured_plan_tiers(tier: cc.PlanTier) -> None:
    service = cc.PlanEntitlementClosureService()
    assert service.publish_plan(plan_definition(tier=tier)).tier is tier


def test_eb03_002_plan_snapshot_contains_all_operational_entitlements() -> None:
    _, snapshot = active_plan_service()
    assert (snapshot.seat_limit, snapshot.concurrent_task_limit, snapshot.model_tier) == (5, 1, "balanced")
    assert (snapshot.retention_days, snapshot.storage_bytes, snapshot.features) == (30, 1_000_000, ("run", "export"))


def test_eb03_003_paid_and_promotional_credits_remain_separate() -> None:
    _, snapshot = active_plan_service()
    assert (snapshot.paid_credit_minor, snapshot.promotional_credit_minor) == (1_000, 200)


def test_eb03_004_subscription_transitions_use_an_explicit_state_machine() -> None:
    service = cc.PlanEntitlementClosureService()
    service.publish_plan(plan_definition())
    trial = service.activate(
        tenant_id="tenant",
        subscription_id="trial",
        plan_id="plan",
        plan_version=1,
        trial=True,
        enterprise_override_id=None,
        enterprise_override_version=None,
        idempotency_key="activate-trial",
    )
    assert trial.lifecycle_state is cc.PlanLifecycleState.TRIAL
    active = service.transition(
        tenant_id="tenant",
        subscription_id="trial",
        transition=cc.PlanTransition.END_TRIAL,
        idempotency_key="end-trial",
    )
    paused = service.transition(
        tenant_id="tenant",
        subscription_id="trial",
        transition=cc.PlanTransition.PAUSE,
        idempotency_key="pause",
    )
    restarted = service.transition(
        tenant_id="tenant",
        subscription_id="trial",
        transition=cc.PlanTransition.RESTART,
        idempotency_key="restart",
    )
    assert (active.lifecycle_state, paused.lifecycle_state, restarted.lifecycle_state) == (
        cc.PlanLifecycleState.ACTIVE,
        cc.PlanLifecycleState.PAUSED,
        cc.PlanLifecycleState.ACTIVE,
    )


def test_eb03_005_enterprise_override_has_priority_and_audit() -> None:
    service = cc.PlanEntitlementClosureService()
    service.publish_plan(plan_definition())
    service.set_enterprise_override(
        cc.EnterprisePlanOverride(
            tenant_id="tenant",
            override_id="override",
            version=1,
            base_plan_id="plan",
            additional_features=("private-runtime",),
            seat_limit=50,
            concurrent_task_limit=8,
            priority=100,
            created_by="contract-admin",
            effective_from=NOW,
        )
    )
    snapshot = service.activate(
        tenant_id="tenant",
        subscription_id="enterprise",
        plan_id="plan",
        plan_version=1,
        trial=False,
        enterprise_override_id="override",
        enterprise_override_version=1,
        idempotency_key="activate-enterprise",
    )
    assert (snapshot.seat_limit, snapshot.concurrent_task_limit) == (50, 8)
    assert "private-runtime" in snapshot.features
    assert service.audit_events(tenant_id="tenant")[0].action == "SET_OVERRIDE"


def test_eb03_006_unified_entitlement_api_fails_closed() -> None:
    service, _ = active_plan_service()
    assert service.entitlement(tenant_id="tenant", subscription_id="subscription", capability="run").allowed
    denied = service.entitlement(tenant_id="tenant", subscription_id="subscription", capability="admin")
    assert not denied.allowed and denied.reason == "FEATURE_NOT_INCLUDED"


def test_eb03_007_entitlement_snapshots_bind_versions_and_replay_history() -> None:
    service, first = active_plan_service()
    second = service.transition(
        tenant_id="tenant",
        subscription_id="subscription",
        transition=cc.PlanTransition.PAUSE,
        idempotency_key="pause",
    )
    history = service.subscription_history(tenant_id="tenant", subscription_id="subscription")
    assert history == (first, second)
    assert history[0].plan_version == 1 and history[0].plan_digest


def test_eb03_008_concurrent_task_limit_is_atomic() -> None:
    service, _ = active_plan_service()

    def acquire(index: int) -> str:
        try:
            service.acquire_task_slot(tenant_id="tenant", subscription_id="subscription", lease_id=f"lease-{index}")
            return "OK"
        except DomainError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = tuple(pool.map(acquire, range(4)))
    assert outcomes.count("OK") == 1
    assert outcomes.count("CONCURRENCY_LIMIT_EXCEEDED") == 3


def test_eb03_009_plan_version_event_invalidates_only_exact_cache_entries() -> None:
    service, _ = active_plan_service()
    service.publish_plan(plan_definition(version=2))
    event = service.version_event(tenant_id="tenant", plan_id="plan", from_version=1, to_version=2)
    assert service.invalidate_from_version_event(event) == ("subscription",)
    assert service.entitlement(tenant_id="tenant", subscription_id="subscription", capability="run").allowed
    assert service.invalidate_from_version_event(event) == ("subscription",)


def test_eb03_010_idempotent_transition_does_not_duplicate_credits_or_history() -> None:
    service, snapshot = active_plan_service()
    first = service.transition(
        tenant_id="tenant",
        subscription_id="subscription",
        transition=cc.PlanTransition.PAUSE,
        idempotency_key="same-transition",
    )
    replay = service.transition(
        tenant_id="tenant",
        subscription_id="subscription",
        transition=cc.PlanTransition.PAUSE,
        idempotency_key="same-transition",
    )
    assert replay is first
    assert (replay.paid_credit_minor, replay.promotional_credit_minor) == (
        snapshot.paid_credit_minor,
        snapshot.promotional_credit_minor,
    )
    assert len(service.subscription_history(tenant_id="tenant", subscription_id="subscription")) == 2


def estimate_request(
    *,
    estimate_id: str = "estimate",
    sample_count: int = 100,
    drift_basis_points: int = 100,
    strategy: cc.ExecutionModelStrategy = cc.ExecutionModelStrategy.BALANCED,
) -> cc.TaskEstimateInput:
    return cc.TaskEstimateInput(
        tenant_id="tenant",
        task_id="task",
        estimate_id=estimate_id,
        estimator_version="estimator-v1",
        input_snapshot_digest="input-snapshot",
        input_snapshot_version=7,
        strategy=strategy,
        resources=tuple(
            cc.ResourceForecast(
                kind=kind,
                quantity=Decimal(index + 1),
                unit_rate=money(str(index + 1)),
                machine_seconds=(index + 1) * 10,
            )
            for index, kind in enumerate(cc.EstimateResourceKind)
        ),
        historical_sample_count=sample_count,
        drift_basis_points=drift_basis_points,
        human_developer_seconds=28_800,
        risk_factors=("repository-complexity",),
        uncertainty_sources=("dependency-availability",),
    )


def calibrated_estimate() -> tuple[cc.TaskCostEstimationClosureService, cc.TaskCostEstimate]:
    service = cc.TaskCostEstimationClosureService()
    return service, service.estimate(estimate_request(), created_at=NOW)


def accepted_budget(
    *,
    funding_kind: cc.QuoteFundingKind = cc.QuoteFundingKind.PREPAID,
) -> tuple[cc.QuoteBudgetGuardClosureService, cc.FrozenCommercialQuote, cc.BudgetExecutionSnapshot]:
    _, estimate = calibrated_estimate()
    service = cc.QuoteBudgetGuardClosureService()
    service.configure_funding(
        tenant_id="tenant",
        kind=funding_kind,
        available_or_credit_limit=money("1000"),
    )
    quote = service.issue_quote(
        tenant_id="tenant",
        quote_id="quote",
        estimate=estimate,
        maximum_budget=money("500"),
        price_book_id="book",
        price_book_version=3,
        price_book_digest="book-digest",
        scope_version=4,
        scope_digest="scope-digest",
        alert_basis_points=(5_000, 8_000, 9_500),
        issued_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    execution = service.accept_and_reserve(
        tenant_id="tenant",
        quote_id="quote",
        expected_scope_version=4,
        expected_scope_digest="scope-digest",
        accepted_by="buyer",
        accepted_at=NOW,
        idempotency_key="accept",
    )
    return service, quote, execution


def test_eb06_001_preflight_estimate_covers_all_seven_resource_classes() -> None:
    _, estimate = calibrated_estimate()
    assert {kind for kind, _ in estimate.resource_costs} == set(cc.EstimateResourceKind)


def test_eb06_002_estimate_outputs_monotonic_p50_p80_p90_range() -> None:
    _, estimate = calibrated_estimate()
    assert estimate.costs.p50.value < estimate.costs.p80.value < estimate.costs.p90.value


def test_eb06_003_estimate_outputs_autonomous_machine_wall_clock_eta() -> None:
    _, estimate = calibrated_estimate()
    assert estimate.autonomous_machine_eta_seconds == 308


def test_eb06_004_human_time_is_a_separate_comparison_field() -> None:
    _, estimate = calibrated_estimate()
    assert estimate.human_developer_seconds_comparison == 28_800
    assert estimate.human_developer_seconds_comparison != estimate.autonomous_machine_eta_seconds


def test_eb06_005_economy_balanced_and_best_quality_are_comparable() -> None:
    service = cc.TaskCostEstimationClosureService()
    economy, balanced, quality = service.compare_strategies(estimate_request(), created_at=NOW)
    assert [item.strategy for item in (economy, balanced, quality)] == list(cc.ExecutionModelStrategy)
    assert economy.costs.p90.value < balanced.costs.p90.value < quality.costs.p90.value


def test_eb06_006_estimate_carries_risk_confidence_and_uncertainty() -> None:
    _, estimate = calibrated_estimate()
    assert estimate.risk_factors == ("repository-complexity",)
    assert estimate.uncertainty_sources == ("dependency-availability",)
    assert 0 < estimate.confidence_basis_points <= 10_000


@pytest.mark.parametrize(
    ("sample_count", "drift"),
    ((1, 0), (100, 2_000)),
)
def test_eb06_007_low_sample_or_drift_uses_conservative_rule(sample_count: int, drift: int) -> None:
    service = cc.TaskCostEstimationClosureService()
    estimate = service.estimate(
        estimate_request(sample_count=sample_count, drift_basis_points=drift),
        created_at=NOW,
    )
    assert estimate.mode is cc.EstimationMode.CONSERVATIVE_RULE
    assert "CONSERVATIVE_RULE_FALLBACK" in estimate.uncertainty_sources


def test_eb06_008_calibration_history_is_tenant_bound_and_anonymized() -> None:
    service, estimate = calibrated_estimate()
    anonymous_key = sha256(b"tenant-local-subject").hexdigest()
    service.record_actual(
        tenant_id="tenant",
        estimate_id=estimate.estimate_id,
        anonymized_history_key=anonymous_key,
        actual_cost=money("250"),
        actual_eta_seconds=400,
        recorded_at=NOW,
    )
    history = service.calibration_history(tenant_id="tenant")
    assert history[0].anonymized_history_key == anonymous_key
    assert service.calibration_history(tenant_id="other") == ()


def test_eb06_009_completion_records_prediction_actual_variance_inputs() -> None:
    service, estimate = calibrated_estimate()
    observation = service.record_actual(
        tenant_id="tenant",
        estimate_id=estimate.estimate_id,
        anonymized_history_key=sha256(b"subject").hexdigest(),
        actual_cost=money("321"),
        actual_eta_seconds=777,
        recorded_at=NOW,
    )
    assert observation.predicted_p90 == estimate.costs.p90
    assert (observation.actual_cost, observation.actual_eta_seconds) == (money("321"), 777)


def test_eb06_010_estimator_version_and_input_snapshot_are_immutable_and_replayable() -> None:
    service = cc.TaskCostEstimationClosureService()
    request = estimate_request()
    first = service.estimate(request, created_at=NOW)
    assert service.estimate(request, created_at=NOW + timedelta(days=1)) is first
    assert (first.estimator_version, first.input_snapshot_digest, first.input_snapshot_version) == (
        "estimator-v1",
        "input-snapshot",
        7,
    )
    with pytest.raises(DomainError, match="ESTIMATE_IDEMPOTENCY_CONFLICT"):
        service.estimate(replace_estimate_id_input(request, snapshot_digest="changed"), created_at=NOW)


def replace_estimate_id_input(request: cc.TaskEstimateInput, *, snapshot_digest: str) -> cc.TaskEstimateInput:
    return cc.TaskEstimateInput(
        tenant_id=request.tenant_id,
        task_id=request.task_id,
        estimate_id=request.estimate_id,
        estimator_version=request.estimator_version,
        input_snapshot_digest=snapshot_digest,
        input_snapshot_version=request.input_snapshot_version,
        strategy=request.strategy,
        resources=request.resources,
        historical_sample_count=request.historical_sample_count,
        drift_basis_points=request.drift_basis_points,
        human_developer_seconds=request.human_developer_seconds,
        risk_factors=request.risk_factors,
        uncertainty_sources=request.uncertainty_sources,
    )


def test_eb07_001_quote_displays_range_budget_eta_human_comparison_and_confidence() -> None:
    _, quote, _ = accepted_budget()
    assert quote.p50.value < quote.p80.value < quote.p90.value <= quote.maximum_budget.value
    assert quote.autonomous_machine_eta_seconds > 0
    assert quote.human_developer_seconds_comparison == 28_800
    assert quote.confidence_basis_points > 0


def test_eb07_002_quote_freezes_price_estimate_strategy_and_scope_versions() -> None:
    _, quote, _ = accepted_budget()
    assert (quote.price_book_id, quote.price_book_version, quote.price_book_digest) == (
        "book",
        3,
        "book-digest",
    )
    assert (quote.estimate_id, quote.estimator_version, quote.model_strategy) == (
        "estimate",
        "estimator-v1",
        cc.ExecutionModelStrategy.BALANCED,
    )
    assert (quote.scope_version, quote.scope_digest, bool(quote.frozen_digest)) == (4, "scope-digest", True)


@pytest.mark.parametrize("funding_kind", tuple(cc.QuoteFundingKind))
def test_eb07_003_acceptance_atomically_reserves_maximum_or_credit(
    funding_kind: cc.QuoteFundingKind,
) -> None:
    service, quote, execution = accepted_budget(funding_kind=funding_kind)
    assert execution.reserved_budget == quote.maximum_budget
    replay = service.accept_and_reserve(
        tenant_id="tenant",
        quote_id="quote",
        expected_scope_version=4,
        expected_scope_digest="scope-digest",
        accepted_by="buyer",
        accepted_at=NOW,
        idempotency_key="accept",
    )
    assert replay is execution


def test_eb07_004_configurable_budget_alerts_emit_once_at_crossing() -> None:
    service, _, _ = accepted_budget()
    first = service.commit_billable(
        tenant_id="tenant",
        quote_id="quote",
        amount=money("250"),
        idempotency_key="spend-1",
        occurred_at=NOW,
    )
    second = service.commit_billable(
        tenant_id="tenant",
        quote_id="quote",
        amount=money("150"),
        idempotency_key="spend-2",
        occurred_at=NOW,
    )
    assert first.emitted_alert_basis_points == (5_000,)
    assert second.emitted_alert_basis_points == (5_000, 8_000)


def test_eb07_005_hard_cap_blocks_new_billable_execution_before_effect() -> None:
    service, _, _ = accepted_budget()
    service.commit_billable(
        tenant_id="tenant",
        quote_id="quote",
        amount=money("499"),
        idempotency_key="spend",
        occurred_at=NOW,
    )
    decision = service.preflight_billable(tenant_id="tenant", quote_id="quote", next_amount=money("2"))
    assert not decision.allowed and decision.reason == "HARD_CAP_WOULD_BE_EXCEEDED"


def test_eb07_006_all_five_budget_remediation_paths_are_explicit() -> None:
    service, _, execution = accepted_budget()
    for action in (
        cc.BudgetRemediation.INCREASE_BUDGET,
        cc.BudgetRemediation.DOWNGRADE_MODEL,
        cc.BudgetRemediation.REDUCE_SCOPE,
        cc.BudgetRemediation.BLOCKERS_ONLY,
        cc.BudgetRemediation.STOP_AND_EXPORT,
    ):
        execution = service.apply_remediation(
            tenant_id="tenant",
            quote_id="quote",
            action=action,
            actor="operator",
            occurred_at=NOW,
            additional_budget=money("50") if action is cc.BudgetRemediation.INCREASE_BUDGET else None,
        )
    assert execution.remediation_history == tuple(cc.BudgetRemediation)
    assert execution.state is cc.BudgetExecutionState.STOPPED


def test_eb07_007_settlement_captures_actual_and_releases_unused_reserve() -> None:
    service, _, _ = accepted_budget()
    service.commit_billable(
        tenant_id="tenant",
        quote_id="quote",
        amount=money("300"),
        idempotency_key="spend",
        occurred_at=NOW,
    )
    settlement = service.settle(
        tenant_id="tenant",
        quote_id="quote",
        actual_billable=money("280"),
        responsibility="completed",
        outcome_evidence_digest="outcome",
        settled_at=NOW,
    )
    assert (settlement.captured, settlement.released) == (money("280"), money("220"))


@pytest.mark.parametrize(
    "terminal_state",
    (cc.BudgetExecutionState.FAILED_SETTLED, cc.BudgetExecutionState.CANCELLED_SETTLED),
)
def test_eb07_008_failure_and_cancel_use_responsibility_outcome_audit(
    terminal_state: cc.BudgetExecutionState,
) -> None:
    service, _, _ = accepted_budget()
    service.commit_billable(
        tenant_id="tenant",
        quote_id="quote",
        amount=money("20"),
        idempotency_key="spend",
        occurred_at=NOW,
    )
    settlement = service.settle(
        tenant_id="tenant",
        quote_id="quote",
        actual_billable=money("10"),
        responsibility="provider-or-customer-rule",
        outcome_evidence_digest="evidence",
        settled_at=NOW,
        terminal_state=terminal_state,
    )
    assert settlement.state is terminal_state
    assert service.audit_events(tenant_id="tenant")[-1].state_digest


@pytest.mark.parametrize(
    ("scope_version", "scope_digest", "as_of"),
    ((5, "scope-digest", NOW), (4, "changed", NOW), (4, "scope-digest", NOW + timedelta(hours=2))),
)
def test_eb07_009_expiry_or_scope_change_requires_requote(
    scope_version: int,
    scope_digest: str,
    as_of: datetime,
) -> None:
    service, _, _ = accepted_budget()
    assert service.require_requote_for_scope_or_expiry(
        tenant_id="tenant",
        quote_id="quote",
        observed_scope_version=scope_version,
        observed_scope_digest=scope_digest,
        as_of=as_of,
    )


def test_eb07_010_recovery_record_restores_consistent_budget_and_funding_state() -> None:
    service, _, _ = accepted_budget()
    service.commit_billable(
        tenant_id="tenant",
        quote_id="quote",
        amount=money("120"),
        idempotency_key="spend",
        occurred_at=NOW,
    )
    record = service.recovery_record(tenant_id="tenant", quote_id="quote")
    restored = cc.QuoteBudgetGuardClosureService()
    execution = restored.restore_recovery_record(record)
    assert execution.committed_billable == money("120")
    assert restored.recovery_record(tenant_id="tenant", quote_id="quote").record_digest == record.record_digest


def baseline(*, scope_version: int = 1, scope_digest: str = "scope") -> cc.FrozenProjectBaseline:
    return cc.FrozenProjectBaseline(
        repository_commit_digest="commit",
        requirements_digest="requirements",
        scope_version=scope_version,
        scope_digest=scope_digest,
        environment_digest="environment",
        acceptance_baseline_digest="acceptance",
    )


def project_contract(
    *,
    contract_id: str = "project",
    version: int = 1,
    kind: cc.ProjectContractKind = cc.ProjectContractKind.FIXED_PRICE,
    project_baseline: cc.FrozenProjectBaseline | None = None,
    quoted_price: str = "200",
    created_at: datetime = NOW,
) -> cc.ProjectCommercialContract:
    return cc.ProjectCommercialContract(
        tenant_id="tenant",
        contract_id=contract_id,
        version=version,
        kind=kind,
        baseline=baseline() if project_baseline is None else project_baseline,
        currency="USD",
        quoted_price=money(quoted_price),
        contractual_cap=money("300") if kind is cc.ProjectContractKind.CAPPED_PRICE else None,
        estimated_p80_cost=money("100"),
        estimated_p90_cost=money("120"),
        target_margin_basis_points=2_500,
        support_allowance=money("10"),
        risk_allowance=money("5"),
        included_revision_rounds=2,
        exclusions=("data migration",),
        third_party_responsibilities=("customer owns provider credentials",),
        created_by="maker",
        created_at=created_at,
    )


def project_service() -> tuple[cc.ProjectPricingContractClosureService, cc.ProjectCommercialContract]:
    service = cc.ProjectPricingContractClosureService()
    contract = project_contract()
    return service, service.create_contract(contract)


def enterprise_fees() -> cc.EnterpriseFeeSchedule:
    return cc.EnterpriseFeeSchedule(
        currency="USD",
        annual_platform_fee=money("12000"),
        minimum_commit=money("1000"),
        overage_unit_rate=money("2"),
        private_deployment_fee=money("5000"),
        support_fee=money("2000"),
        sla_fee=money("1000"),
    )


def enterprise_contract(
    *,
    contract_id: str = "enterprise",
    version: int = 1,
    priority: int = 10,
    effective_from: datetime = NOW,
    effective_to: datetime = NOW + timedelta(days=365),
) -> cc.EnterpriseContractVersion:
    return cc.EnterpriseContractVersion(
        tenant_id="tenant",
        contract_id=contract_id,
        version=version,
        effective_from=effective_from,
        effective_to=effective_to,
        fees=enterprise_fees(),
        committed_usage_units=Decimal("500.000000"),
        postpaid_credit_limit=money("50000"),
        purchase_order_reference="PO-123",
        payment_terms_days=30,
        override_priority=priority,
        measurement_trust_boundary_digest="meter-boundary",
        created_by="maker",
        created_at=effective_from,
    )


def enterprise_service() -> tuple[cc.EnterpriseByokClosureService, cc.EnterpriseContractVersion]:
    service = cc.EnterpriseByokClosureService()
    contract = enterprise_contract()
    return service, service.create_contract(contract)


def byok_binding() -> cc.ByokBinding:
    return cc.ByokBinding(
        tenant_id="tenant",
        binding_id="byok",
        contract_id="enterprise",
        contract_version=1,
        model_provider="provider",
        secret_reference=cc.SecretReference(
            provider="vault",
            uri="secret://tenant/byok/provider-key",
            version="v3",
        ),
        quota_units=Decimal("1000.000000"),
        created_by="security-admin",
        created_at=NOW,
    )


def test_eb08_001_supports_discovery_capped_and_fixed_contracts() -> None:
    service = cc.ProjectPricingContractClosureService()
    created = tuple(
        service.create_contract(project_contract(contract_id=kind.value, kind=kind))
        for kind in cc.ProjectContractKind
    )
    assert {item.kind for item in created} == set(cc.ProjectContractKind)


def test_eb08_002_contract_freezes_repo_requirements_scope_environment_and_acceptance() -> None:
    _, contract = project_service()
    assert contract.baseline == baseline()
    assert contract.baseline.digest


def test_eb08_003_fixed_price_covers_p90_margin_acceptance_support_and_risk() -> None:
    contract = project_contract()
    assert contract.quoted_price == money("200")
    assert contract.quoted_price.value > contract.estimated_p90_cost.value
    with pytest.raises(DomainError, match="FIXED_PRICE_UNDERPRICED"):
        project_contract(quoted_price="160")


def test_eb08_004_contract_declares_revisions_exclusions_and_third_party_boundary() -> None:
    _, contract = project_service()
    assert contract.included_revision_rounds == 2
    assert contract.exclusions == ("data migration",)
    assert contract.third_party_responsibilities == ("customer owns provider credentials",)


def test_eb08_005_scope_change_is_isolated_until_maker_checker_approval() -> None:
    service, contract = project_service()
    order = service.request_change_order(
        tenant_id="tenant",
        contract_id=contract.contract_id,
        contract_version=1,
        change_order_id="co-1",
        proposed_baseline=baseline(scope_version=2, scope_digest="scope-2"),
        incremental_price=money("50"),
        requested_by="requester",
        requested_at=NOW,
    )
    assert order.isolated_until_approved and order.state is cc.ChangeOrderState.PENDING
    approved, updated = service.approve_change_order(
        tenant_id="tenant",
        change_order_id="co-1",
        approved_by="approver",
        approval_evidence_digest="approval",
        approved_at=NOW + timedelta(minutes=1),
    )
    assert not approved.isolated_until_approved
    assert (updated.version, updated.baseline.scope_digest, updated.quoted_price) == (2, "scope-2", money("250"))


def test_eb08_006_milestone_acceptance_binds_automated_test_and_approval_evidence() -> None:
    service, contract = project_service()
    acceptance = service.accept_milestone(
        tenant_id="tenant",
        contract_id=contract.contract_id,
        contract_version=1,
        milestone_id="m1",
        automated_test_evidence_digest="tests",
        approval_evidence_digest="approval",
        approved_by="customer",
        accepted_at=NOW,
    )
    assert (acceptance.automated_test_evidence_digest, acceptance.approval_evidence_digest) == (
        "tests",
        "approval",
    )


def test_eb08_007_capped_project_settlement_never_exceeds_contract_cap() -> None:
    service = cc.ProjectPricingContractClosureService()
    contract = service.create_contract(project_contract(kind=cc.ProjectContractKind.CAPPED_PRICE))
    settled = service.settle_capped_project(
        tenant_id="tenant",
        contract_id=contract.contract_id,
        contract_version=1,
        actual_billable=money("999"),
    )
    assert settled == money("300")


@pytest.mark.parametrize("path", tuple(cc.FixedPriceFailurePath))
def test_eb08_008_fixed_acceptance_failure_has_four_explicit_paths(path: cc.FixedPriceFailurePath) -> None:
    service = cc.ProjectPricingContractClosureService()
    contract = service.create_contract(project_contract(contract_id=path.value))
    resolution = service.resolve_fixed_price_acceptance_failure(
        tenant_id="tenant",
        contract_id=contract.contract_id,
        contract_version=1,
        path=path,
        evidence_digest="failure-evidence",
        decided_by="operator",
        decided_at=NOW,
    )
    assert resolution.path is path


def test_eb08_009_project_records_actual_cost_revenue_and_margin_review() -> None:
    service, contract = project_service()
    review = service.record_financial_review(
        tenant_id="tenant",
        contract_id=contract.contract_id,
        contract_version=1,
        actual_cost=money("130"),
        recognized_revenue=money("200"),
        review_evidence_digest="review",
        recorded_at=NOW,
    )
    assert review.realized_margin == money("70")


def test_eb08_010_standard_sku_has_machine_verifiable_input_and_output_limits() -> None:
    service = cc.ProjectPricingContractClosureService()
    service.validate_standard_sku(
        sku=project_sku(),
        input_digest="input",
        output_digest="output",
        scope_units=10,
    )
    with pytest.raises(DomainError, match="SKU_OUTPUT_CONTRACT_MISMATCH"):
        service.validate_standard_sku(
            sku=project_sku(),
            input_digest="input",
            output_digest="changed",
            scope_units=10,
        )


def test_eb12_001_enterprise_fee_schedule_covers_all_six_commercial_components() -> None:
    _, contract = enterprise_service()
    fees = contract.fees
    assert all(
        amount.currency == "USD"
        for amount in (
            fees.annual_platform_fee,
            fees.minimum_commit,
            fees.overage_unit_rate,
            fees.private_deployment_fee,
            fees.support_fee,
            fees.sla_fee,
        )
    )


def test_eb12_002_minimum_commit_burn_down_true_up_and_renewal_are_versioned() -> None:
    service, contract = enterprise_service()
    burn = service.burn_commitment(
        tenant_id="tenant",
        contract_id=contract.contract_id,
        contract_version=1,
        charge=money("1200"),
        idempotency_key="burn",
        occurred_at=NOW,
    )
    assert (burn.burned_from_commit, burn.overage) == (money("1000"), money("200"))
    true_up = service.calculate_true_up(
        tenant_id="tenant",
        contract_id=contract.contract_id,
        contract_version=1,
        calculated_at=contract.effective_to,
    )
    assert (true_up.unused_commit, true_up.billable_overage) == (money("0"), money("200"))
    renewal = service.renew_contract(
        enterprise_contract(
            version=2,
            effective_from=contract.effective_to,
            effective_to=contract.effective_to + timedelta(days=365),
        )
    )
    assert renewal.version == 2


def test_eb12_003_byok_persists_only_secret_reference_not_plaintext_key() -> None:
    service, _ = enterprise_service()
    binding = service.bind_byok(byok_binding())
    assert binding.secret_reference.uri == "secret://tenant/byok/provider-key"
    authorization = service.authorize_byok_usage(
        tenant_id="tenant",
        binding_id="byok",
        requested_units=Decimal("100.000000"),
        idempotency_key="usage",
        actor="runner",
        occurred_at=NOW,
    )
    assert authorization.cumulative_units == Decimal("100.000000")
    assert [event.action for event in service.audit_events(tenant_id="tenant")] == [
        "BIND_SECRET_REFERENCE",
        "AUTHORIZE_USAGE",
    ]
    with pytest.raises(DomainError, match="BYOK_QUOTA_EXCEEDED"):
        service.authorize_byok_usage(
            tenant_id="tenant",
            binding_id="byok",
            requested_units=Decimal("901.000000"),
            idempotency_key="over-quota",
            actor="runner",
            occurred_at=NOW,
        )
    with pytest.raises(DomainError, match="SECRET_REFERENCE_URI_INVALID|PLAINTEXT_SECRET_FORBIDDEN"):
        cc.SecretReference(provider="vault", uri="sk-plaintext", version="v1")


def test_eb12_004_byok_excludes_customer_model_cost_but_bills_platform_and_infra() -> None:
    service, _ = enterprise_service()
    service.bind_byok(byok_binding())
    breakdown = service.calculate_byok_charge(
        tenant_id="tenant",
        binding_id="byok",
        customer_paid_model_cost=money("99"),
        platform_fee=money("10"),
        infrastructure_fee=money("15"),
    )
    assert breakdown.excluded_customer_model_cost == money("99")
    assert breakdown.billable_total == money("25")


def test_eb12_005_enterprise_contract_binds_credit_po_and_payment_terms() -> None:
    _, contract = enterprise_service()
    assert (contract.postpaid_credit_limit, contract.purchase_order_reference, contract.payment_terms_days) == (
        money("50000"),
        "PO-123",
        30,
    )


def test_eb12_006_cost_center_budget_requires_approval_and_creates_chargeback() -> None:
    service, contract = enterprise_service()
    center = service.register_cost_center(
        tenant_id="tenant",
        cost_center_id="engineering",
        department_id="department",
        contract_id=contract.contract_id,
        contract_version=1,
        budget=money("500"),
        owner="owner",
    )
    chargeback = service.approve_chargeback(
        tenant_id="tenant",
        chargeback_id="chargeback",
        cost_center_id=center.cost_center_id,
        amount=money("100"),
        requested_by="requester",
        approved_by="approver",
        purpose="task execution",
        evidence_digest="approval",
        occurred_at=NOW,
    )
    assert chargeback.amount == money("100")
    with pytest.raises(DomainError, match="MAKER_CHECKER_VIOLATION"):
        service.approve_chargeback(
            tenant_id="tenant",
            chargeback_id="invalid",
            cost_center_id=center.cost_center_id,
            amount=money("1"),
            requested_by="same",
            approved_by="same",
            purpose="invalid",
            evidence_digest="evidence",
            occurred_at=NOW,
        )


def test_eb12_007_contract_overrides_are_versioned_with_deterministic_priority() -> None:
    service, first = enterprise_service()
    higher = service.create_contract(enterprise_contract(contract_id="priority", priority=100))
    assert service.resolve_contract_override(tenant_id="tenant", at=NOW + timedelta(days=1)) == higher
    assert service.history(tenant_id="tenant", contract_id=first.contract_id) == (first,)


def test_eb12_008_private_metering_enforces_trust_boundary_and_offline_chain() -> None:
    service, contract = enterprise_service()
    first = cc.OfflineMeteringBatch(
        tenant_id="tenant",
        contract_id=contract.contract_id,
        contract_version=1,
        sequence=1,
        previous_batch_digest=None,
        usage_digest="usage-1",
        boundary_attestation_digest="meter-boundary",
        captured_from=NOW,
        captured_to=NOW + timedelta(hours=1),
    )
    service.accept_offline_metering_batch(first)
    second = cc.OfflineMeteringBatch(
        tenant_id="tenant",
        contract_id=contract.contract_id,
        contract_version=1,
        sequence=2,
        previous_batch_digest=first.digest,
        usage_digest="usage-2",
        boundary_attestation_digest="meter-boundary",
        captured_from=NOW + timedelta(hours=1),
        captured_to=NOW + timedelta(hours=2),
    )
    assert service.accept_offline_metering_batch(second).previous_batch_digest == first.digest


def test_eb12_009_sla_breach_uses_rule_bounded_service_credit() -> None:
    service, contract = enterprise_service()
    decision = service.calculate_service_credit(
        tenant_id="tenant",
        contract_id=contract.contract_id,
        contract_version=1,
        rule=cc.ServiceCreditRule(
            rule_id="availability",
            metric="availability",
            breach_threshold_basis_points=9_900,
            credit_basis_points=1_000,
            maximum_credit_basis_points=2_000,
        ),
        observed_basis_points=9_800,
        eligible_fee=money("1000"),
        evidence_digest="sla-evidence",
        decided_at=NOW,
    )
    assert decision.credit == money("100")


def test_eb12_010_contract_change_cannot_rewrite_historical_settlement() -> None:
    service, contract = enterprise_service()
    settlement = service.record_historical_settlement(
        tenant_id="tenant",
        settlement_id="settlement",
        contract_id=contract.contract_id,
        contract_version=1,
        amount=money("500"),
        source_digest="source-v1",
        recorded_at=NOW,
    )
    service.renew_contract(
        enterprise_contract(
            version=2,
            effective_from=contract.effective_to,
            effective_to=contract.effective_to + timedelta(days=365),
        )
    )
    assert service.record_historical_settlement(
        tenant_id="tenant",
        settlement_id="settlement",
        contract_id=contract.contract_id,
        contract_version=1,
        amount=money("500"),
        source_digest="source-v1",
        recorded_at=NOW,
    ) == settlement
    with pytest.raises(DomainError, match="HISTORICAL_SETTLEMENT_IMMUTABLE"):
        service.record_historical_settlement(
            tenant_id="tenant",
            settlement_id="settlement",
            contract_id=contract.contract_id,
            contract_version=1,
            amount=money("501"),
            source_digest="source-v2",
            recorded_at=NOW,
        )
