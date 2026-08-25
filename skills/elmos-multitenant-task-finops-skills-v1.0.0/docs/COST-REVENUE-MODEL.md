# Cost, Revenue, and Profitability Model

## 1. Objectives

For every task and historical scope, Elmos must answer:

- What did the autonomous system consume?
- What did that consumption cost?
- What amount was quoted, billed, recognized, and collected?
- How much revenue is attributable to the task?
- What are gross profit and gross margin?
- Which model, provider, node, retry, recovery, storage, or infrastructure component drove the result?
- Are totals final or merely posted through an `as_of` timestamp?

## 2. Measurement layers

### Estimate

Created before execution from input size, task type, repository characteristics, historical analogs, model plan, cache prediction, and expected validation/retry.

### Reservation

Budget amount or credits reserved to prevent overspend. Reservation is not cost or revenue.

### Posted actual

Immutable usage entries ingested through `as_of`. Running tasks use this qualified measure.

### Final actual

Posted usage is complete, provider receipts are reconciled or within accepted lag, shared allocation is applied, and the task is closed financially.

## 3. Usage taxonomy

| Category | Usage types |
|---|---|
| Model | input token, cached input token, output token, embedding token, image, audio second, transcription, provider request |
| Compute | vCPU-second, GB-second, GPU-second, accelerator unit |
| Runner | sandbox-second, runner-minute, workspace GB-hour |
| Storage | object byte-hour, database allocated byte-hour, snapshot byte-hour |
| Network | ingress if billable, egress byte, cross-region byte |
| Workflow | optional Temporal/shared control allocation |
| Build/Test | build minute, test minute, browser minute, device minute |
| Render | PDF/PPT/image/video render unit |
| External | Git provider, security scan, package registry, payment provider, notification |
| Correction | explicit signed cost correction after reconciliation |

Every unit has a canonical name and conversion rule.

## 4. Price book

A price-book item is effective-dated and includes:

```text
provider
sku
usage_type
unit
region
tier/range
unit_price
currency
effective_from
effective_to
source/reference
version
rounding_policy
minimum_charge
```

At ingestion, the usage event stores the selected item/version, unit price, currency, FX snapshot, base-currency cost, and calculation version. Historical events never recalculate because a later provider price changes.

## 5. Model cost

Example:

```text
model_cost =
  uncached_input_tokens / 1e6 × uncached_input_price
+ cached_input_tokens   / 1e6 × cached_input_price
+ output_tokens         / 1e6 × output_price
+ embedding_units              × embedding_price
+ image_units                  × image_price
+ audio_seconds                × audio_price
+ provider_specific_units      × provider_specific_price
```

Record original provider usage and normalized usage. Do not infer all cost from application-side token estimates when provider usage receipts are available.

## 6. Compute and storage cost

```text
compute_cost =
  vCPU_seconds × price_per_vCPU_second
+ GB_seconds   × price_per_GB_second
+ GPU_seconds  × price_per_GPU_second

storage_cost =
  object_byte_hours   × object_byte_hour_price
+ snapshot_byte_hours × snapshot_byte_hour_price
+ egress_bytes        × egress_byte_price
```

Shared infrastructure may be allocated by measured usage, reserved capacity, active time, or a documented hybrid policy. Store allocation policy and version.

## 7. Retry, recovery, and cache

Retries and recovery consume real cost and remain visible by attempt.

Dashboard dimensions:

- first-pass cost;
- retry cost;
- recovery/reconciliation cost;
- cache-hit saved cost;
- cache-miss cost;
- user-triggered rerun cost;
- system defect-related cost.

Do not silently delete cost from failed or cancelled tasks.

## 8. Budgets

Budget scopes:

- task;
- account;
- tenant;
- project;
- provider/model;
- billing period.

Budget states:

```text
AVAILABLE
WARNING
RESERVED
SOFT_EXCEEDED
HARD_EXCEEDED
OVERRIDE_APPROVED
CLOSED
```

A hard exceed pauses or fails according to task policy. Overrides require actor, reason, amount, expiry, and audit.

## 9. Revenue model

Supported modes:

### Prepaid credits/token balance

- customer purchases credits;
- purchase/collection is recorded separately;
- task consumption allocates recognized revenue according to policy;
- unused balance remains liability/deferred revenue where applicable to the business accounting policy.

### Pay as you go

- usage produces charge entries;
- invoice/payment produces collection entries;
- revenue recognition follows the configured policy.

### Subscription plus overage

- subscription base is allocated by a versioned policy;
- included usage is distinguishable from overage;
- overage produces direct task/account charges.

### Fixed project

- quoted/contract amount belongs to project;
- revenue is recognized by milestone/acceptance policy;
- task allocation may be milestone or usage weighted.

### Dedicated tenant/private/offline license

- setup, license, support, and usage revenue remain distinct;
- shared platform cost allocation may differ from SaaS.

## 10. Revenue entry taxonomy

| Kind | Meaning |
|---|---|
| `QUOTE` | Commercial offer; not revenue |
| `CHARGE` | Amount billed/charged |
| `CREDIT` | Customer credit reducing billed amount |
| `REFUND` | Returned value |
| `RECOGNITION` | Revenue recognized for profitability/reporting basis |
| `COLLECTION` | Cash/payment settled |
| `PAYMENT_FEE` | Processor fee, treated separately from system cost |
| `TAX` | Tax component, excluded or included according to metric definition |
| `ADJUSTMENT` | Approved signed correction |

Entries are immutable. A correction references the prior entry.

## 11. Allocation

A revenue entry may be:

- directly attached to one task;
- attached to a project and allocated to tasks;
- attached to a subscription period and allocated across tenant usage;
- unallocated until enough evidence exists.

Allocation fields:

```text
source_revenue_entry_id
tenant_id
project_id
task_id
task_run_id (optional)
allocation_method
allocation_policy_version
weight
allocated_amount
currency
occurred_at
approved_by (if manual)
```

Invariant:

```text
sum(task/project allocations)
<= allocatable source amount within currency precision
```

A fully allocated entry should equal the source allocatable amount.

## 12. Core metrics

### Cost

```text
estimated_cost
reserved_cost
posted_actual_system_cost
final_actual_system_cost
human_review_cost (separate)
```

### Revenue

```text
quoted_value
net_billed_revenue
recognized_revenue
collected_cash
refunds
credits
payment_fees
taxes
```

### Profitability

```text
gross_profit
= recognized_revenue - posted_or_final_actual_system_cost

gross_margin
= gross_profit / recognized_revenue
```

When recognized revenue is zero, margin is null, not infinity.

Other unit economics:

```text
cost_per_successful_task
revenue_per_task
profit_per_task
cost_per_1M_output_tokens
cost_per_repository_KLOC
retry_cost_rate
cache_savings_rate
provider/model margin
tenant/project contribution
```

## 13. Currency and FX

- Store original amount/currency.
- Store base currency and FX rate snapshot used for the projection.
- Never add amounts across currencies without an explicit conversion basis.
- Define rounding per currency and provider.
- Corrections from provider invoice rounding are explicit ledger entries.
- Dashboard exposes reporting currency and FX basis.

## 14. `as_of` semantics

For running tasks or incomplete provider settlement:

```text
Posted system cost through 2026-08-19T16:00:00+08:00
```

Do not label it simply "final cost".

Every financial response includes:

- scope;
- period;
- basis;
- reporting currency;
- `as_of`;
- reconciliation status;
- included/excluded accounts/providers;
- estimate versus posted/final status.

## 15. Reconciliation

### Usage/provider

Compare:

- internal request ID;
- provider receipt/usage ID;
- units by type;
- price tier;
- currency;
- provider invoice line;
- internal cost.

Differences become explicit correction events or unresolved exceptions.

### Revenue/payment

Compare:

- order/charge;
- invoice;
- payment intent/settlement;
- refund;
- fee;
- collection;
- recognition;
- allocation.

### Projection

Compare:

```text
task cost summary = sum usage ledger
task recognized revenue = sum allocations of recognition entries
platform total = sum tenant totals
tenant total = sum task/project/unallocated components
```

## 16. Data quality statuses

```text
COMPLETE
POSTING
PARTIAL_PROVIDER_DATA
UNRECONCILED
DUPLICATE_SUSPECTED
MISSING_PRICE
MISSING_FX
UNALLOCATED_REVENUE
ALLOCATION_MISMATCH
MANUAL_REVIEW
FINAL
```

Financial dashboards must surface these statuses.

## 17. Access control

- Task submitters may view task operational cost according to product policy.
- Tenant owners/finance roles may view tenant cost/revenue/margin.
- Platform finance/admin sees cross-tenant totals through explicit audited roles.
- Raw prompts, source files, provider receipts, and payment identifiers follow stricter field-level/redaction policy.
- Manual price, cost, revenue, refund, or allocation changes require reason and audit.
