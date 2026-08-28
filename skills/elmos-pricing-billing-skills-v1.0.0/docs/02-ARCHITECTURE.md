# Reference Architecture

## 1. Architectural style

本包不强制 Elmos 改写技术栈。实现时优先复用现有服务边界、语言、数据库迁移、消息系统和可观测性。推荐按以下**逻辑边界**组织；早期可以模块化单体，规模增长后再拆服务。

```text
Customer/Admin UI
        |
API Gateway / BFF / Tenant Auth
        |
+---------------- Billing Control Plane ----------------+
| Catalog & Entitlements | Quote & Budget | Projects    |
| Subscription & Invoice | Refund/Dispute | Enterprise  |
+--------------------------------------------------------+
        | commands/events
+---------------- Financial Core ------------------------+
| Double-entry Ledger | Wallet Projection | Payment     |
| Reconciliation      | Accounting Export               |
+--------------------------------------------------------+
        | immutable facts
+---------------- Metering & Economics ------------------+
| Usage Ingestion | Rating | Aggregation | Estimation   |
| Vendor Cost     | Margin Analytics | Drift            |
+--------------------------------------------------------+
        |
Task Runtime / Model Gateway / Sandbox / Test / Storage
```

## 2. Trust boundaries

1. **Task runtime** reports raw usage but cannot mutate customer balances.
2. **Metering** normalizes and rates usage but cannot invent payment success.
3. **Quote/budget** authorizes consumption and asks ledger to reserve/capture.
4. **Ledger** is the only balance fact source.
5. **Payment adapter** treats verified provider events/settlement as cash facts.
6. **Analytics** is read-only and never writes financial truth.
7. **Admin UI** invokes audited commands; it never writes tables directly.

## 3. Command and event pattern

Every financial command includes:

```json
{
  "tenant_id": "t_...",
  "actor_id": "u_...|svc_...",
  "idempotency_key": "stable-business-key",
  "correlation_id": "corr_...",
  "causation_id": "event-or-command-id",
  "expected_version": 7,
  "occurred_at": "RFC3339"
}
```

Recommended reliability primitives:

- ACID transaction for aggregate state + outbox record
- Outbox publisher with at-least-once delivery
- Consumer inbox/idempotency table
- Optimistic version or row lock for wallet/authorization concurrency
- Saga with explicit compensation for cross-provider operations
- Dead-letter queue and operator replay with dry-run preview

## 4. Storage

- PostgreSQL or existing ACID relational database for ledger, invoice, contract and control state.
- Object storage for immutable evidence, provider settlement files and large reports.
- Stream/queue for usage and domain events.
- Analytical warehouse/lakehouse for aggregates; never authoritative for balance.
- Secret manager for payment and BYOK secret references.

## 5. Availability strategy

Financial writes choose correctness over availability:

- If ledger or idempotency store is unavailable, pause new paid execution.
- Existing tasks may continue only if a pre-authorized offline budget and durable local metering policy explicitly allows it.
- Usage events are durably buffered and backfilled; capture occurs only after reconciliation.
- Kill switch can disable top-up, new task authorization, capture, refund, or all financial writes independently.

## 6. Multi-tenant isolation

- Every row and event has `tenant_id` unless it is immutable global catalog data.
- Database row-level security or trusted repository filters are mandatory for customer data.
- Cache keys, object paths, queue partitions, metrics labels and search indexes include tenant scope.
- Global support access uses explicit break-glass role, reason, expiry and audit.

## 7. Compatibility and evolution

- Use versioned OpenAPI/JSON Schema/AsyncAPI contracts.
- Consumers accept additive fields; breaking changes require a new version.
- Database changes follow expand → dual-read/write → backfill → verify → contract.
- Price book and vendor rate changes are temporal versions, not mutable constants.

## 8. Suggested module ports

- `CatalogRepository`, `EntitlementEvaluator`
- `LedgerCommandService`, `WalletQueryService`
- `UsageIngestPort`, `VendorRateResolver`, `UsageRater`
- `Estimator`, `QuoteService`, `BudgetGuard`
- `ProjectContractService`, `AcceptanceService`
- `SubscriptionService`, `InvoiceService`
- `PaymentProvider`, `ReconciliationService`
- `RefundPolicy`, `DisputeService`
- `EnterpriseContractResolver`, `ByokBillingPolicy`
- `CostAllocationService`, `MarginReadModel`

## 9. Prohibited shortcuts

- Direct balance updates
- Floating-point money
- Provider-specific payloads leaking into core domain
- Payment success inferred from browser redirect
- Hard-coded plan/price logic across business services
- Unbounded retries of non-idempotent commands
- Finalized invoice mutation
- Deleting usage or ledger history to ‘fix’ reconciliation
