from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class LocalImplementationState(StrEnum):
    """Conservative state for the bounded local reference implementation."""

    LOCAL_EXECUTED = "LOCAL_EXECUTED"
    PARTIAL = "PARTIAL"
    NOT_RUN = "NOT_RUN"


@dataclass(frozen=True, slots=True)
class RuntimeArtifactBinding:
    language: str
    symbol: str
    source_path: str
    test_paths: tuple[str, ...]
    local_test_state: LocalImplementationState
    external_evidence_state: str = "NOT_RUN"
    certification_state: str = "NOT_CERTIFIED"


@dataclass(frozen=True, slots=True)
class SkillHandlerBinding:
    skill_name: str
    handler_symbol: str
    test_node_ids: tuple[str, ...]
    domain_state: LocalImplementationState
    requirement_ids: tuple[str, ...]
    supporting_artifacts: tuple[RuntimeArtifactBinding, ...]


@dataclass(frozen=True, slots=True)
class RequirementBinding:
    requirement_id: str
    skill_name: str
    handler_symbol: str
    test_node_ids: tuple[str, ...]
    local_state: LocalImplementationState


@dataclass(frozen=True, slots=True)
class SkillQualificationEntry:
    skill_name: str
    handler_symbol: str
    test_node_ids: tuple[str, ...]
    handler_execution_state: LocalImplementationState
    domain_implementation_state: LocalImplementationState
    requirement_ids: tuple[str, ...]
    supporting_artifacts: tuple[RuntimeArtifactBinding, ...]


@dataclass(frozen=True, slots=True)
class LocalQualificationManifest:
    schema_version: str
    authority: str
    maximum_readiness: LocalImplementationState
    persistence_scope: str
    persistence_contract_state: LocalImplementationState
    skill_count: int
    artifact_count: int
    requirement_count: int
    skills: tuple[SkillQualificationEntry, ...]
    artifacts: tuple[RuntimeArtifactBinding, ...]
    requirements: tuple[RequirementBinding, ...]
    external_boundaries: tuple[tuple[str, str], ...]


_FINANCIAL_JAVA = (
    "modules/commercial-operations/src/main/java/"
    "io/elmos/commercial/PricingBillingFinancialRuntime.java"
)
_FINANCIAL_JAVA_TEST = (
    "modules/commercial-operations/src/test/java/"
    "io/elmos/commercial/PricingBillingFinancialRuntimeTest.java"
)
_PAYMENT_JAVA = (
    "modules/commercial-operations/src/main/java/"
    "io/elmos/commercial/PaymentRefundReconciliationRuntime.java"
)
_PAYMENT_JAVA_TEST = (
    "modules/commercial-operations/src/test/java/"
    "io/elmos/commercial/PaymentRefundReconciliationRuntimeTest.java"
)
_FINANCIAL_MIGRATION = "modules/persistence/src/main/resources/db/migration/V65__pricing_billing_financial_core.sql"
_FINANCIAL_MIGRATION_TEST = (
    "modules/persistence/src/test/java/"
    "io/elmos/persistence/PricingBillingFinancialCoreMigrationContractTest.java"
)


def _java_financial(symbol: str) -> RuntimeArtifactBinding:
    return RuntimeArtifactBinding(
        language="JAVA",
        symbol=f"io.elmos.commercial.PricingBillingFinancialRuntime.{symbol}",
        source_path=_FINANCIAL_JAVA,
        test_paths=(_FINANCIAL_JAVA_TEST,),
        local_test_state=LocalImplementationState.LOCAL_EXECUTED,
    )


def _java_payment(symbol: str) -> RuntimeArtifactBinding:
    return RuntimeArtifactBinding(
        language="JAVA",
        symbol=f"io.elmos.commercial.PaymentRefundReconciliationRuntime.{symbol}",
        source_path=_PAYMENT_JAVA,
        test_paths=(_PAYMENT_JAVA_TEST,),
        local_test_state=LocalImplementationState.LOCAL_EXECUTED,
    )


_POSTGRES_FINANCIAL = RuntimeArtifactBinding(
    language="SQL",
    symbol="db.migration.V65__pricing_billing_financial_core",
    source_path=_FINANCIAL_MIGRATION,
    test_paths=(_FINANCIAL_MIGRATION_TEST,),
    local_test_state=LocalImplementationState.LOCAL_EXECUTED,
)


_SKILL_SPECS: tuple[
    tuple[
        str,
        str,
        tuple[str, ...],
        LocalImplementationState,
        tuple[RuntimeArtifactBinding, ...],
    ],
    ...,
] = (
    (
        "elmos-billing-orchestrator",
        "elmos_pricing_billing.governance_closure.BillingOrchestrationService",
        (
            "tests/test_governance_closure.py::"
            "test_eb01_baseline_dependency_dag_checkpoint_and_handoff_are_replayable",
        ),
        LocalImplementationState.LOCAL_EXECUTED,
        (),
    ),
    (
        "elmos-pricing-product-model",
        "elmos_pricing_billing.commercial_closure.PricingProductClosureService",
        ("tests/test_commercial_closure.py::test_eb02_001_supports_six_explicit_commercial_routes",),
        LocalImplementationState.LOCAL_EXECUTED,
        (),
    ),
    (
        "elmos-plan-catalog-entitlements",
        "elmos_pricing_billing.commercial_closure.PlanEntitlementClosureService",
        ("tests/test_commercial_closure.py::test_eb03_006_unified_entitlement_api_fails_closed",),
        LocalImplementationState.LOCAL_EXECUTED,
        (),
    ),
    (
        "elmos-credit-wallet-ledger",
        "elmos_pricing_billing.financial_exactness_closure.CreditWalletExactnessService",
        (
            "tests/test_financial_exactness_closure.py::"
            "test_eb04_append_only_wallet_conserves_paid_promotional_reserved_refunded_and_expired",
            "tests/test_financial_exactness_closure.py::"
            "test_eb04_manual_adjustment_requires_independent_approval_and_evidence",
            "tests/test_financial_exactness_closure.py::"
            "test_eb04_idempotency_tenant_isolation_negative_balance_and_external_unknown_fail_closed",
            "tests/test_financial_exactness_closure.py::"
            "test_eb04_bounded_concurrent_reservation_never_corrupts_or_overdraws_projection",
        ),
        LocalImplementationState.LOCAL_EXECUTED,
        (_java_financial("WalletLedger"), _POSTGRES_FINANCIAL),
    ),
    (
        "elmos-usage-metering",
        "elmos_pricing_billing.financial_exactness_closure.UsageMeteringExactnessService",
        (
            "tests/test_financial_exactness_closure.py::"
            "test_eb05_typed_resources_attribution_precision_rate_version_and_treatments",
            "tests/test_financial_exactness_closure.py::"
            "test_eb05_dedupe_correction_late_window_and_detail_lineage_are_deterministic",
            "tests/test_financial_exactness_closure.py::"
            "test_eb05_bounded_backpressure_retry_dead_letter_replay_and_reconciliation_fail_closed",
        ),
        LocalImplementationState.LOCAL_EXECUTED,
        (_java_financial("UsageMeter"), _POSTGRES_FINANCIAL),
    ),
    (
        "elmos-task-cost-estimation",
        "elmos_pricing_billing.commercial_closure.TaskCostEstimationClosureService",
        ("tests/test_commercial_closure.py::test_eb06_001_preflight_estimate_covers_all_seven_resource_classes",),
        LocalImplementationState.LOCAL_EXECUTED,
        (),
    ),
    (
        "elmos-quote-budget-guard",
        "elmos_pricing_billing.commercial_closure.QuoteBudgetGuardClosureService",
        ("tests/test_commercial_closure.py::test_eb07_005_hard_cap_blocks_new_billable_execution_before_effect",),
        LocalImplementationState.LOCAL_EXECUTED,
        (),
    ),
    (
        "elmos-project-pricing-contracts",
        "elmos_pricing_billing.commercial_closure.ProjectPricingContractClosureService",
        ("tests/test_commercial_closure.py::test_eb08_005_scope_change_is_isolated_until_maker_checker_approval",),
        LocalImplementationState.LOCAL_EXECUTED,
        (),
    ),
    (
        "elmos-subscription-invoicing",
        "elmos_pricing_billing.financial_exactness_closure.SubscriptionInvoicingExactnessService",
        (
            "tests/test_financial_exactness_closure.py::"
            "test_eb09_subscription_lifecycle_idempotency_and_calendar_boundaries",
            "tests/test_financial_exactness_closure.py::"
            "test_eb09_typed_invoice_snapshot_draft_final_and_correction_lineage",
            "tests/test_financial_exactness_closure.py::"
            "test_eb09_renewal_credit_terms_dunning_and_accounting_events_are_distinct",
        ),
        LocalImplementationState.LOCAL_EXECUTED,
        (_java_financial("InvoiceBook"), _POSTGRES_FINANCIAL),
    ),
    (
        "elmos-payments-reconciliation",
        "elmos_pricing_billing.billing.PaymentReconciliationService",
        ("tests/test_billing_and_payments.py::test_verified_webhook_dedup_unknown_state_and_four_way_suspense",),
        LocalImplementationState.PARTIAL,
        (
            _java_payment("WebhookGateway"),
            _java_payment("PaymentAggregate"),
            _java_payment("ReconciliationEngine"),
        ),
    ),
    (
        "elmos-refunds-disputes",
        "elmos_pricing_billing.billing.RefundDisputeService",
        ("tests/test_billing_and_payments.py::test_refund_limits_maker_checker_reversal_and_dispute",),
        LocalImplementationState.PARTIAL,
        (
            _java_payment("RefundPolicy"),
            _java_payment("RefundSaga"),
            _java_payment("RefundBook"),
            _java_payment("DisputeBook"),
        ),
    ),
    (
        "elmos-enterprise-byok",
        "elmos_pricing_billing.commercial_closure.EnterpriseByokClosureService",
        ("tests/test_commercial_closure.py::test_eb12_003_byok_persists_only_secret_reference_not_plaintext_key",),
        LocalImplementationState.LOCAL_EXECUTED,
        (),
    ),
    (
        "elmos-cost-margin-analytics",
        "elmos_pricing_billing.financial_exactness_closure.CostMarginExactnessService",
        (
            "tests/test_financial_exactness_closure.py::"
            "test_eb13_fact_sources_states_dimensions_versioned_allocation_and_estimate_variance",
            "tests/test_financial_exactness_closure.py::"
            "test_eb13_as_of_close_coverage_cost_drivers_alerts_and_price_approval",
        ),
        LocalImplementationState.LOCAL_EXECUTED,
        (_java_financial("MarginAnalyzer"), _POSTGRES_FINANCIAL),
    ),
    (
        "elmos-billing-admin-ux",
        "elmos_pricing_billing.operations_closure.BillingAdminExperienceService",
        ("tests/test_operations_closure.py::test_eb14_quote_run_wallet_drilldown_and_project_views_are_exact",),
        LocalImplementationState.LOCAL_EXECUTED,
        (),
    ),
    (
        "elmos-security-compliance",
        "elmos_pricing_billing.operations_closure.BillingSecurityComplianceService",
        ("tests/test_operations_closure.py::test_eb15_tenant_sod_secret_encryption_and_audit_chain_fail_closed",),
        LocalImplementationState.LOCAL_EXECUTED,
        (),
    ),
    (
        "elmos-billing-observability-ops",
        "elmos_pricing_billing.operations_closure.BillingObservabilityOperationsService",
        ("tests/test_operations_closure.py::test_eb16_trace_signals_slos_kill_switch_queue_and_recovery",),
        LocalImplementationState.LOCAL_EXECUTED,
        (),
    ),
    (
        "elmos-billing-testing-certification",
        "elmos_pricing_billing.governance_closure.BillingQualificationService",
        ("tests/test_governance_closure.py::test_eb17_binding_separates_executor_verifier_and_gate_never_certifies",),
        LocalImplementationState.LOCAL_EXECUTED,
        (),
    ),
    (
        "elmos-rollout-migration",
        "elmos_pricing_billing.governance_closure.BillingMigrationService",
        ("tests/test_governance_closure.py::test_eb18_cutover_customer_plan_and_legacy_retention_stay_human_gated",),
        LocalImplementationState.LOCAL_EXECUTED,
        (),
    ),
)


_CLOSURE_LOCAL_SKILLS = frozenset({1, 2, 3, 4, 5, 6, 7, 8, 9, 12, 13, 14, 15, 16, 17, 18})

_LOCAL_EXECUTED_REQUIREMENTS = frozenset(
    {
        "EB-11-006",
        "EB-11-007",
        "EB-11-009",
    }
) | frozenset(
    f"EB-{skill_number:02d}-{requirement_number:03d}"
    for skill_number in _CLOSURE_LOCAL_SKILLS
    for requirement_number in range(1, 11)
)

_NOT_RUN_REQUIREMENTS = frozenset(
    {
        "EB-10-001",
        "EB-10-002",
        "EB-10-006",
        "EB-10-007",
        "EB-10-008",
    }
)


def _requirement_state(requirement_id: str) -> LocalImplementationState:
    if requirement_id in _LOCAL_EXECUTED_REQUIREMENTS:
        return LocalImplementationState.LOCAL_EXECUTED
    if requirement_id in _NOT_RUN_REQUIREMENTS:
        return LocalImplementationState.NOT_RUN
    return LocalImplementationState.PARTIAL


SKILL_HANDLER_BINDINGS: tuple[SkillHandlerBinding, ...] = tuple(
    SkillHandlerBinding(
        skill_name=name,
        handler_symbol=symbol,
        test_node_ids=tests,
        domain_state=domain_state,
        requirement_ids=tuple(f"EB-{index:02d}-{number:03d}" for number in range(1, 11)),
        supporting_artifacts=artifacts,
    )
    for index, (name, symbol, tests, domain_state, artifacts) in enumerate(_SKILL_SPECS, start=1)
)

DOMAIN_HANDLER_NAMES: tuple[str, ...] = tuple(binding.skill_name for binding in SKILL_HANDLER_BINDINGS)

REQUIREMENT_BINDINGS: tuple[RequirementBinding, ...] = tuple(
    RequirementBinding(
        requirement_id=requirement_id,
        skill_name=binding.skill_name,
        handler_symbol=binding.handler_symbol,
        test_node_ids=binding.test_node_ids,
        local_state=_requirement_state(requirement_id),
    )
    for binding in SKILL_HANDLER_BINDINGS
    for requirement_id in binding.requirement_ids
)


EXTERNAL_BOUNDARIES: tuple[tuple[str, str], ...] = (
    ("payment_sandbox", "NOT_RUN"),
    ("payment_provider", "NOT_RUN"),
    ("bank_settlement", "NOT_RUN"),
    ("tax_engine", "NOT_RUN"),
    ("accounting_system_of_record", "NOT_RUN"),
    ("disaster_recovery", "NOT_RUN"),
    ("customer_acceptance", "NOT_RUN"),
    ("production_execution", "NOT_RUN"),
    ("independent_verification", "NOT_RUN"),
    ("certification", "NOT_CERTIFIED"),
)


def build_local_qualification_manifest(handler_results: Mapping[str, bool]) -> LocalQualificationManifest:
    if tuple(handler_results) != DOMAIN_HANDLER_NAMES:
        raise ValueError("handler results must preserve all 18 exact manifest-owned Skill names in order")
    skills = tuple(
        SkillQualificationEntry(
            skill_name=binding.skill_name,
            handler_symbol=binding.handler_symbol,
            test_node_ids=binding.test_node_ids,
            handler_execution_state=(
                LocalImplementationState.LOCAL_EXECUTED
                if handler_results[binding.skill_name]
                else LocalImplementationState.PARTIAL
            ),
            domain_implementation_state=binding.domain_state,
            requirement_ids=binding.requirement_ids,
            supporting_artifacts=binding.supporting_artifacts,
        )
        for binding in SKILL_HANDLER_BINDINGS
    )
    artifacts_by_identity: dict[tuple[str, str, str], RuntimeArtifactBinding] = {}
    for binding in SKILL_HANDLER_BINDINGS:
        for artifact in binding.supporting_artifacts:
            artifacts_by_identity[(artifact.language, artifact.symbol, artifact.source_path)] = artifact
    artifacts = tuple(artifacts_by_identity.values())
    return LocalQualificationManifest(
        schema_version="1.0",
        authority="LOCAL_REFERENCE_ONLY",
        maximum_readiness=LocalImplementationState.LOCAL_EXECUTED,
        persistence_scope="IN_MEMORY_SAME_PROCESS_ONLY",
        persistence_contract_state=LocalImplementationState.NOT_RUN,
        skill_count=len(skills),
        artifact_count=len(artifacts),
        requirement_count=len(REQUIREMENT_BINDINGS),
        skills=skills,
        artifacts=artifacts,
        requirements=REQUIREMENT_BINDINGS,
        external_boundaries=EXTERNAL_BOUNDARIES,
    )
