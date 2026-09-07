# Domain Model

## 1. Main aggregates

| Aggregate | Responsibility | Key invariants |
|---|---|---|
| PriceBook | Versioned customer prices | immutable after activation; temporal validity |
| VendorRateBook | Versioned internal provider costs | event-time rating; no historical rewrite |
| Plan/Entitlement | Features, quotas, seats, included credits | decision traceable to version |
| BillingAccount | Tenant billing identity and terms | one active billing profile per scope |
| Wallet | Paid/promo/reserved projections | derived from ledger; non-negative unless credit |
| LedgerTransaction | Balanced financial movement | append-only; debit equals credit |
| UsageEvent | Raw normalized resource use | immutable, idempotent, attributable |
| TaskEstimate | Resource/cost/runtime prediction | reproducible snapshot |
| TaskQuote | Customer offer and hard cap | binds scope, price, estimate, expiry |
| BudgetAuthorization | Reserve/credit permission | cannot exceed accepted authority |
| ProjectContract | Capped/fixed scope and milestones | scope baseline and change orders |
| Subscription | Plan lifecycle and billing anchor | deterministic transition and grant |
| Invoice | Immutable finalized receivable | corrections via new documents |
| Payment | Provider-neutral money movement | verified external fact and idempotency |
| Refund/Dispute | Reversal and claim workflow | cumulative refund ceiling |
| EnterpriseContract | Overrides, commit, SLA, BYOK | versioned precedence and date range |

## 2. Identifiers

Use globally unique, opaque IDs with stable prefixes for supportability:

- `ten_`, `ba_`, `wal_`, `ltx_`, `le_`
- `use_`, `est_`, `quo_`, `auth_`, `run_`
- `prj_`, `mil_`, `co_`
- `sub_`, `inv_`, `pay_`, `ref_`, `dsp_`
- `pb_`, `vrb_`, `plan_`, `contract_`

Never encode mutable business data in IDs.

## 3. Amount types

```text
MoneyAmount      = { currency: ISO-4217, minor_units: int64 }
CreditAmount     = { credit_unit: string, micro_credits: int64 }
UsageQuantity    = { unit: enum, quantity: decimal-string, scale: int }
RatedCost        = { amount, rate_version_id, formula_version }
```

Use checked arithmetic and overflow guards. JSON carries large integers as strings where client precision is uncertain.

## 4. Ledger account examples

- Asset: provider clearing, bank clearing, refund receivable
- Liability: customer paid credit liability, promotional credit liability, reserved credit liability
- Revenue: platform subscription, managed model usage, sandbox, project revenue, support
- Contra revenue: discounts, service credits, refunds
- Expense/COGS: model vendor, compute, storage, payment fees
- Suspense: unmatched cash, unmatched provider event, migration difference

Exact accounting treatment requires jurisdiction-specific review; the technical model must preserve enough facts to support the approved policy.

## 5. Temporal versioning

Every price, rate, entitlement, refund policy, tax input and enterprise override has:

- stable logical ID
- immutable version ID
- `valid_from`, `valid_to`
- status: draft/approved/active/retired
- approval metadata
- content hash

Transaction records save the resolved version ID and calculation breakdown.

## 6. Data ownership

- Ledger owns balance truth.
- Metering owns usage truth.
- Invoice owns receivable document truth.
- Payment owns provider movement truth.
- Contract owns commercial scope truth.
- Analytics owns derived insight only.

Cross-domain copies are projections and must retain source IDs and versions.
