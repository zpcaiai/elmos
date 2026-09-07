"""Public API for the ELMOS pricing and billing engine.

Provides deterministic local reference behavior for pricing, metering, billing,
reconciliation, quotation, and financial governance Skills.  All money values use
exact decimal arithmetic.  Tenant, legal-entity, and segregation-of-duties
boundaries fail closed.  Unknown provider or bank results block retry, close, and
publication until reconciled.

This engine is self-attested engineering evidence only.  Static Skill validation
is not accounting, tax, payment, bank, or management-reporting certification.
"""

from .domain import (
    BillingCycle,
    BillingPeriod,
    ChargeItem,
    ContractError,
    CreditNote,
    Currency,
    EntitlementGrant,
    Invoice,
    InvoiceLineItem,
    InvoiceStatus,
    LedgerEntry,
    LedgerEntryType,
    MeteringEvent,
    Money,
    PricingPlan,
    PricingTier,
    QuotaLimit,
    RateCard,
    ReconciliationResult,
    ReconciliationStatus,
    SubscriptionStatus,
    TenantScope,
    UsageRecord,
)
from .contracts import (
    RequestContract,
    ResultContract,
    canonical_json,
    digest_json,
    require_text,
    validate_money,
)
from .service import PricingBillingService
from .handlers import SKILL_REGISTRY, dispatch_skill

__all__ = [
    "BillingCycle",
    "BillingPeriod",
    "ChargeItem",
    "ContractError",
    "CreditNote",
    "Currency",
    "EntitlementGrant",
    "Invoice",
    "InvoiceLineItem",
    "InvoiceStatus",
    "LedgerEntry",
    "LedgerEntryType",
    "MeteringEvent",
    "Money",
    "PricingBillingService",
    "PricingPlan",
    "PricingTier",
    "QuotaLimit",
    "RateCard",
    "ReconciliationResult",
    "ReconciliationStatus",
    "RequestContract",
    "ResultContract",
    "SKILL_REGISTRY",
    "SubscriptionStatus",
    "TenantScope",
    "UsageRecord",
    "canonical_json",
    "digest_json",
    "dispatch_skill",
    "require_text",
    "validate_money",
]
