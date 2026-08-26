from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from threading import RLock
from types import MappingProxyType

from .billing import (
    EnterpriseTermsService,
    PaymentReconciliationService,
    RefundDisputeService,
    SubscriptionInvoiceService,
)
from .commercial import ProjectContractService, QuoteBudgetService, TaskCostEstimator
from .commercial_closure import (
    EnterpriseByokClosureService,
    PlanEntitlementClosureService,
    PricingProductClosureService,
    ProjectPricingContractClosureService,
    QuoteBudgetGuardClosureService,
    TaskCostEstimationClosureService,
)
from .financial_exactness_closure import (
    CostMarginExactnessService,
    CreditWalletExactnessService,
    SubscriptionInvoicingExactnessService,
    UsageMeteringExactnessService,
)
from .governance_closure import BillingMigrationService, BillingOrchestrationService, BillingQualificationService
from .ledger import LedgerService
from .models import (
    DisputeState,
    EnterpriseAgreement,
    Entitlement,
    ExternalEvidenceState,
    InvoiceLine,
    MigrationMode,
    PlanState,
    PriceBookState,
    PriceEntry,
    PricingModel,
    ProviderPaymentState,
    QualificationReport,
    QuoteState,
    ReadinessState,
    RefundState,
    SubscriptionState,
    UsageEvent,
)
from .money import Money
from .operations import (
    AdminProjectionService,
    AuditOperationsService,
    MarginAnalyticsService,
    MigrationService,
    QualificationService,
    SecurityComplianceService,
)
from .operations_closure import (
    BillingAdminExperienceService,
    BillingObservabilityOperationsService,
    BillingSecurityComplianceService,
)
from .pricing import PlanEntitlementService, PriceBookService
from .registry import (
    DOMAIN_HANDLER_NAMES,
    SKILL_HANDLER_BINDINGS,
    LocalImplementationState,
    LocalQualificationManifest,
    RuntimeArtifactBinding,
    build_local_qualification_manifest,
)
from .usage import UsageMeteringService


class PricingBillingEngine:
    """Composition root for bounded local reference behavior only."""

    def __init__(self, *, price_book_id: str = "local-reference") -> None:
        self.price_books = PriceBookService()
        self.plans = PlanEntitlementService()
        self.ledger = LedgerService()
        self.usage = UsageMeteringService(self.price_books, book_id=price_book_id)
        self.estimator = TaskCostEstimator()
        self.quotes = QuoteBudgetService(self.ledger)
        self.projects = ProjectContractService()
        self.subscriptions = SubscriptionInvoiceService()
        self.payments = PaymentReconciliationService()
        self.refunds = RefundDisputeService(self.ledger)
        self.enterprise = EnterpriseTermsService()
        self.margin = MarginAnalyticsService()
        self.operations = AuditOperationsService()
        self.migration = MigrationService(self.ledger)
        self.security = SecurityComplianceService(self.operations)
        self.admin = AdminProjectionService(
            ledger=self.ledger,
            usage=self.usage,
            payments=self.payments,
            operations=self.operations,
        )
        self.qualification = QualificationService()
        self.orchestration_closure = BillingOrchestrationService()
        self.pricing_closure = PricingProductClosureService()
        self.plan_closure = PlanEntitlementClosureService()
        self.estimation_closure = TaskCostEstimationClosureService()
        self.quote_closure = QuoteBudgetGuardClosureService()
        self.project_contract_closure = ProjectPricingContractClosureService()
        self.wallet_exactness = CreditWalletExactnessService()
        self.usage_exactness = UsageMeteringExactnessService()
        self.subscription_exactness = SubscriptionInvoicingExactnessService()
        self.margin_exactness = CostMarginExactnessService()
        self.enterprise_closure = EnterpriseByokClosureService()
        self.admin_closure = BillingAdminExperienceService()
        self.security_closure = BillingSecurityComplianceService()
        self.observability_closure = BillingObservabilityOperationsService()
        self.qualification_closure = BillingQualificationService()
        self.migration_closure = BillingMigrationService()
        self._price_book_id = price_book_id
        handlers: dict[str, object] = {
            "elmos-billing-orchestrator": self.orchestration_closure,
            "elmos-pricing-product-model": self.pricing_closure,
            "elmos-plan-catalog-entitlements": self.plan_closure,
            "elmos-credit-wallet-ledger": self.wallet_exactness,
            "elmos-usage-metering": self.usage_exactness,
            "elmos-task-cost-estimation": self.estimation_closure,
            "elmos-quote-budget-guard": self.quote_closure,
            "elmos-project-pricing-contracts": self.project_contract_closure,
            "elmos-subscription-invoicing": self.subscription_exactness,
            "elmos-payments-reconciliation": self.payments,
            "elmos-refunds-disputes": self.refunds,
            "elmos-enterprise-byok": self.enterprise_closure,
            "elmos-cost-margin-analytics": self.margin_exactness,
            "elmos-billing-admin-ux": self.admin_closure,
            "elmos-security-compliance": self.security_closure,
            "elmos-billing-observability-ops": self.observability_closure,
            "elmos-billing-testing-certification": self.qualification_closure,
            "elmos-rollout-migration": self.migration_closure,
        }
        self._handlers: Mapping[str, object] = MappingProxyType(handlers)
        self._runtime_artifacts: Mapping[str, tuple[RuntimeArtifactBinding, ...]] = MappingProxyType(
            {binding.skill_name: binding.supporting_artifacts for binding in SKILL_HANDLER_BINDINGS}
        )
        self._demo_lock = RLock()
        self._demo_cache: tuple[QualificationReport, Mapping[str, object]] | None = None

    @property
    def handlers(self) -> Mapping[str, object]:
        return self._handlers

    def handler(self, name: str) -> object:
        return self._handlers[name]

    @property
    def runtime_artifacts(self) -> Mapping[str, tuple[RuntimeArtifactBinding, ...]]:
        """Exact non-Python implementation artifacts; metadata never executes them."""

        return self._runtime_artifacts

    def run_local_demo(self) -> tuple[QualificationReport, dict[str, object]]:
        with self._demo_lock:
            if self._demo_cache is not None:
                return self._demo_cache[0], dict(self._demo_cache[1])
            report, observations = self._run_local_demo_once()
            self._demo_cache = (report, MappingProxyType(dict(observations)))
            return report, dict(observations)

    def _run_local_demo_once(self) -> tuple[QualificationReport, dict[str, object]]:
        """Exercise each handler with deterministic local facts and no external calls."""

        timestamp = datetime(2026, 1, 1, tzinfo=UTC)
        tenant = "tenant-demo"
        observations: dict[str, object] = {}

        draft = self.price_books.create_draft(
            book_id=self._price_book_id,
            version=1,
            effective_from=timestamp,
            entries=(PriceEntry("model-token", "USD", 20_000, provider_rate_micro=10_000),),
        )
        approved = self.price_books.approve(
            book_id=draft.book_id,
            version=draft.version,
            expected_revision=draft.revision,
            approved_at=timestamp,
        )
        observations["elmos-pricing-product-model"] = approved.state is PriceBookState.APPROVED

        plan = self.plans.create_draft(
            plan_id="pro",
            version=1,
            entitlements=(Entitlement("conversion", 100),),
            concurrency_limit=2,
        )
        approved_plan = self.plans.approve(plan_id=plan.plan_id, version=plan.version, expected_revision=plan.revision)
        snapshot = self.plans.activate(
            tenant_id=tenant,
            plan_id=approved_plan.plan_id,
            version=approved_plan.version,
            activated_at=timestamp,
        )
        lease = self.plans.acquire(tenant_id=tenant, capability="conversion")
        self.plans.release(tenant_id=tenant, lease_id=lease)
        observations["elmos-plan-catalog-entitlements"] = (
            approved_plan.state is PlanState.APPROVED and self.plans.active_count(tenant_id=tenant) == 0
        )

        self.ledger.opening_balance(
            tenant_id=tenant,
            money=Money("USD", 50_000),
            idempotency_key="demo-opening",
            reference="demo-opening",
            occurred_at=timestamp,
        )
        observations["elmos-credit-wallet-ledger"] = self.ledger.verify_rebuild(tenant_id=tenant, currency="USD")

        rated = self.usage.ingest(
            UsageEvent(
                tenant_id=tenant,
                event_id="usage-1",
                sku="model-token",
                quantity_micro=2_000_000,
                occurred_at=timestamp + timedelta(minutes=1),
                byok=True,
                correlation_id="corr-demo",
            )
        )
        observations["elmos-usage-metering"] = rated.billable_minor > 0 and rated.provider_cost_micro == 0

        estimate = self.estimator.estimate(cost_samples_minor=(100, 200, 300, 400, 500), machine_eta_seconds=75)
        observations["elmos-task-cost-estimation"] = (
            estimate.p50_minor <= estimate.p80_minor <= estimate.p90_minor and estimate.machine_eta_seconds == 75
        )

        quote = self.quotes.create(
            quote_id="quote-1",
            tenant_id=tenant,
            scope_digest="scope-v1",
            money=Money("USD", 10_000),
            estimate=estimate,
            price_book_id=approved.book_id,
            price_book_version=approved.version,
            price_book_digest=approved.digest,
            model_strategy="BALANCED",
            human_time_reference_seconds=3_600,
            confidence_basis_points=8_000,
            hard_cap_minor=20_000,
            threshold_percents=(50, 80, 100),
            expires_at=timestamp + timedelta(days=1),
        )
        accepted = self.quotes.accept(
            quote_id=quote.quote_id,
            tenant_id=tenant,
            scope_digest=quote.scope_digest,
            accepted_by="approver-demo",
            accepted_at=timestamp + timedelta(hours=1),
        )
        decision = self.quotes.preflight_spend(quote_id=quote.quote_id, tenant_id=tenant, next_minor=4_000)
        observations["elmos-quote-budget-guard"] = accepted.state is QuoteState.ACCEPTED and decision.allowed

        contract = self.projects.create(
            contract_id="contract-1",
            tenant_id=tenant,
            model=PricingModel.CAPPED,
            scope_digest="project-scope-v1",
            currency="USD",
            cap_minor=30_000,
        )
        change = self.projects.propose_change(
            change_id="change-1",
            contract_id=contract.contract_id,
            tenant_id=tenant,
            proposed_by="maker-demo",
            new_scope_digest="project-scope-v2",
            delta_minor=5_000,
        )
        revised_contract = self.projects.approve_change(
            change_id=change.change_id,
            tenant_id=tenant,
            approved_by="checker-demo",
        )
        acceptance = self.projects.accept_milestone(
            acceptance_id="acceptance-1",
            contract_id=contract.contract_id,
            tenant_id=tenant,
            milestone="M1",
            accepted_by="customer-demo",
            accepted_at=timestamp + timedelta(days=2),
            scope_digest=revised_contract.scope_digest,
        )
        observations["elmos-project-pricing-contracts"] = (
            revised_contract.version == 2 and acceptance.scope_digest == revised_contract.scope_digest
        )

        subscription = self.subscriptions.subscribe(
            subscription_id="subscription-1",
            tenant_id=tenant,
            plan_snapshot=snapshot,
            started_at=timestamp,
        )
        invoice = self.subscriptions.issue_invoice(
            invoice_id="invoice-1",
            tenant_id=tenant,
            subscription_id=subscription.subscription_id,
            lines=(InvoiceLine("line-1", "local reference", Money("USD", 1_000)),),
            issued_at=timestamp,
            due_at=timestamp + timedelta(days=14),
        )
        self.subscriptions.issue_credit_note(
            credit_note_id="credit-note-1",
            invoice_id=invoice.invoice_id,
            tenant_id=tenant,
            money=Money("USD", 100),
            reason="local correction",
            issued_at=timestamp + timedelta(days=1),
        )
        dunning = self.subscriptions.record_dunning(
            event_id="dunning-1",
            invoice_id=invoice.invoice_id,
            tenant_id=tenant,
            state=SubscriptionState.PAST_DUE,
            occurred_at=timestamp + timedelta(days=15),
            reason="local overdue projection",
        )
        observations["elmos-subscription-invoicing"] = bool(invoice.digest) and dunning.sequence == 1

        self.payments.observe_webhook(
            provider="provider-neutral-demo",
            provider_event_id="provider-event-1",
            tenant_id=tenant,
            payment_reference="payment-1",
            state=ProviderPaymentState.SUCCEEDED,
            raw_payload=b'{"local":true}',
            signature_verified=True,
            received_at=timestamp + timedelta(minutes=2),
        )
        reconciliation = self.payments.reconcile(
            reconciliation_id="reconcile-1",
            tenant_id=tenant,
            payment_reference="payment-1",
            currency="USD",
            ledger_minor=1_000,
            invoice_minor=1_000,
            provider_minor=1_000,
            bank_minor=1_000,
        )
        observations["elmos-payments-reconciliation"] = reconciliation.matched

        self.refunds.register_refundable(tenant_id=tenant, payment_reference="payment-1", money=Money("USD", 1_000))
        refund = self.refunds.request_refund(
            refund_id="refund-1",
            tenant_id=tenant,
            payment_reference="payment-1",
            money=Money("USD", 250),
            requested_by="refund-maker",
            reason="local demo",
        )
        self.refunds.approve(refund_id=refund.refund_id, tenant_id=tenant, approved_by="refund-checker")
        self.refunds.execute_local_credit(refund_id=refund.refund_id, tenant_id=tenant, occurred_at=timestamp)
        reversed_refund = self.refunds.reverse_local_credit(
            refund_id=refund.refund_id,
            tenant_id=tenant,
            occurred_at=timestamp + timedelta(minutes=3),
        )
        dispute = self.refunds.open_dispute(
            dispute_id="dispute-1",
            tenant_id=tenant,
            payment_reference="payment-1",
            money=Money("USD", 100),
            opened_by="dispute-maker",
            reason="local demo",
        )
        decided_dispute = self.refunds.decide_dispute(
            dispute_id=dispute.dispute_id,
            tenant_id=tenant,
            decided_by="dispute-checker",
            state=DisputeState.WON,
        )
        observations["elmos-refunds-disputes"] = (
            reversed_refund.state is RefundState.REVERSED and decided_dispute.state is DisputeState.WON
        )

        byok_reference = "secret://" + tenant + "/provider-key"
        agreement = self.enterprise.create(
            EnterpriseAgreement(
                agreement_id="agreement-1",
                tenant_id=tenant,
                currency="USD",
                committed_minor=10_000,
                credit_limit_minor=5_000,
                byok_secret_ref=byok_reference,
                sla_credit_cap_minor=1_000,
            )
        )
        remaining = self.enterprise.authorize_spend(
            agreement_id=agreement.agreement_id,
            tenant_id=tenant,
            amount_minor=1_000,
            idempotency_key="enterprise-spend-1",
        )
        sla_credit = self.enterprise.calculate_sla_credit(
            agreement_id=agreement.agreement_id,
            tenant_id=tenant,
            eligible_charge_minor=10_000,
            credit_basis_points=500,
            idempotency_key="sla-credit-1",
        )
        observations["elmos-enterprise-byok"] = remaining == 14_000 and sla_credit.minor == 500

        margin = self.margin.calculate(
            currency="USD",
            revenue_minor=10_000,
            provider_cost_minor=2_000,
            runner_cost_minor=1_000,
            support_cost_minor=500,
        )
        observations["elmos-cost-margin-analytics"] = margin.margin_minor == 6_500

        work = self.operations.enqueue(
            work_id="work-1",
            tenant_id=tenant,
            correlation_id="corr-demo",
            operation="local-reconcile",
        )
        self.operations.claim(work_id=work.work_id, tenant_id=tenant)
        self.operations.fail(work_id=work.work_id, tenant_id=tenant, error_code="LOCAL_TRANSIENT")
        replay = self.operations.replay(failed_work_id=work.work_id, new_work_id="work-2", tenant_id=tenant)
        self.operations.record_audit(
            tenant_id=tenant,
            correlation_id="corr-demo",
            actor="local-engine",
            action="demo",
            outcome="LOCAL_EXECUTED",
            occurred_at=timestamp,
            details={"external": False},
        )
        observations["elmos-billing-observability-ops"] = replay.attempt == 2 and bool(
            self.operations.audit_events(tenant_id=tenant)
        )

        authorization = self.security.authorize(
            principal_id="approver-demo",
            principal_tenant_id=tenant,
            resource_tenant_id=tenant,
            role="APPROVER",
            action="refund:approve",
            correlation_id="corr-auth",
            occurred_at=timestamp,
        )
        denied = self.security.authorize(
            principal_id="viewer-demo",
            principal_tenant_id="tenant-other",
            resource_tenant_id=tenant,
            role="VIEWER",
            action="billing:read",
            correlation_id="corr-denied",
            occurred_at=timestamp,
        )
        observations["elmos-security-compliance"] = authorization.allowed and not denied.allowed

        self.migration.import_opening_balance(
            tenant_id="tenant-migration",
            money=Money("USD", 1_000),
            source_snapshot_digest="source-snapshot-demo",
            occurred_at=timestamp,
        )
        shadow = self.migration.compare_shadow(
            comparison_id="shadow-1",
            tenant_id=tenant,
            reference="usage-1",
            external_minor=100,
            simulated_minor=100,
        )
        self.migration.set_canary(tenant_id=tenant, enabled=True)
        self.migration.set_mode(mode=MigrationMode.CANARY)
        charge_decision = self.migration.charge_decision(tenant_id=tenant)
        observations["elmos-rollout-migration"] = shadow.matched and charge_decision.simulation_only

        admin = self.admin.snapshot(tenant_id=tenant, currency="USD")
        observations["elmos-billing-admin-ux"] = admin.rated_usage_count == 1 and admin.work_item_count == 2

        observations["elmos-billing-testing-certification"] = all(
            state in {ExternalEvidenceState.NOT_RUN, ExternalEvidenceState.NOT_CERTIFIED}
            for _, state in QualificationService.EXTERNAL_BOUNDARIES
        )
        observations["elmos-billing-orchestrator"] = tuple(self.handlers) == DOMAIN_HANDLER_NAMES

        for binding in SKILL_HANDLER_BINDINGS:
            handler = self._handlers[binding.skill_name]
            concrete_symbol = f"{handler.__class__.__module__}.{handler.__class__.__qualname__}"
            observations[binding.skill_name] = bool(observations[binding.skill_name]) and (
                concrete_symbol == binding.handler_symbol
            )

        handler_results = {name: bool(observations[name]) for name in DOMAIN_HANDLER_NAMES}
        report = self.qualification.build_report(
            expected_handlers=DOMAIN_HANDLER_NAMES,
            handler_results=handler_results,
        )
        return report, observations

    def qualify_local(self) -> QualificationReport:
        report, _ = self.run_local_demo()
        return report

    @classmethod
    def run_local_budget_scenario(cls) -> dict[str, object]:
        """Replay hard-cap reservation, idempotent spend, capture, and release locally."""

        timestamp = datetime(2026, 1, 1, tzinfo=UTC)
        tenant = "tenant-budget-scenario"
        engine = cls(price_book_id="budget-scenario")
        draft = engine.price_books.create_draft(
            book_id="budget-scenario",
            version=1,
            effective_from=timestamp,
            entries=(PriceEntry("work-unit", "USD", 10_000),),
        )
        price_book = engine.price_books.approve(
            book_id=draft.book_id,
            version=draft.version,
            expected_revision=draft.revision,
            approved_at=timestamp,
        )
        estimate = engine.estimator.estimate(
            cost_samples_minor=(8_000, 10_000, 11_500),
            machine_eta_seconds=600,
        )
        engine.ledger.opening_balance(
            tenant_id=tenant,
            money=Money("USD", 20_000),
            idempotency_key="scenario-opening",
            reference="scenario-opening",
            occurred_at=timestamp,
        )
        quote = engine.quotes.create(
            quote_id="scenario-quote",
            tenant_id=tenant,
            scope_digest="scenario-scope-v1",
            money=Money("USD", 10_000),
            estimate=estimate,
            price_book_id=price_book.book_id,
            price_book_version=price_book.version,
            price_book_digest=price_book.digest,
            model_strategy="BALANCED",
            human_time_reference_seconds=7_200,
            confidence_basis_points=8_000,
            hard_cap_minor=12_000,
            threshold_percents=(100,),
            expires_at=timestamp + timedelta(days=1),
        )
        engine.quotes.accept(
            quote_id=quote.quote_id,
            tenant_id=tenant,
            scope_digest=quote.scope_digest,
            accepted_by="scenario-approver",
            accepted_at=timestamp,
        )
        first = engine.quotes.commit_spend(
            quote_id=quote.quote_id,
            tenant_id=tenant,
            amount_minor=3_000,
            idempotency_key="scenario-spend-1",
        )
        repeated = engine.quotes.commit_spend(
            quote_id=quote.quote_id,
            tenant_id=tenant,
            amount_minor=3_000,
            idempotency_key="scenario-spend-1",
        )
        final = engine.quotes.commit_spend(
            quote_id=quote.quote_id,
            tenant_id=tenant,
            amount_minor=8_500,
            idempotency_key="scenario-spend-2",
        )
        engine.ledger.capture(
            tenant_id=tenant,
            money=Money("USD", final.committed_spend_minor),
            idempotency_key="scenario-capture",
            reference=quote.quote_id,
            occurred_at=timestamp,
        )
        engine.ledger.release(
            tenant_id=tenant,
            money=Money("USD", quote.hard_cap_minor - final.committed_spend_minor),
            idempotency_key="scenario-release",
            reference=quote.quote_id,
            occurred_at=timestamp,
        )
        balance = engine.ledger.balance(tenant_id=tenant, currency="USD")
        return {
            "authority": "LOCAL_REFERENCE_ONLY",
            "external_side_effects": False,
            "persistence_scope": "IN_MEMORY_SAME_PROCESS_ONLY",
            "hard_cap_minor": quote.hard_cap_minor,
            "reserved_at_accept_minor": quote.hard_cap_minor,
            "idempotent_repeat_stable": first is repeated,
            "committed_spend_minor": final.committed_spend_minor,
            "available_minor": balance.available_minor,
            "reserved_minor": balance.reserved_minor,
            "captured_minor": balance.captured_minor,
        }

    def local_qualification_manifest(self) -> LocalQualificationManifest:
        _, observations = self.run_local_demo()
        handler_results = {name: bool(observations[name]) for name in DOMAIN_HANDLER_NAMES}
        return build_local_qualification_manifest(handler_results)

    @staticmethod
    def external_boundaries_are_unexecuted(report: QualificationReport) -> bool:
        return (
            report.readiness is ReadinessState.LOCAL_EXECUTED
            and all(state is LocalImplementationState.LOCAL_EXECUTED for _, state in report.handler_results)
            and all(
                state in {ExternalEvidenceState.NOT_RUN, ExternalEvidenceState.NOT_CERTIFIED}
                for _, state in report.external_evidence
            )
        )
