# API and Event Contracts

The normative machine-readable contracts are in `schemas/`.

## 1. Command APIs

- `POST /v1/task-estimates`
- `POST /v1/task-quotes`
- `POST /v1/task-quotes/{id}/accept`
- `POST /v1/budget-authorizations/{id}/top-ups`
- `POST /v1/task-runs/{id}/pause|resume|cancel`
- `POST /v1/usage-events:ingest`
- `POST /v1/wallets/{id}/credits|reserves|captures|releases`
- `POST /v1/project-contracts`
- `POST /v1/project-contracts/{id}/change-orders`
- `POST /v1/subscriptions`
- `POST /v1/invoices/{id}/finalize`
- `POST /v1/payments/intents`
- `POST /v1/refunds`

Every financial POST requires `Idempotency-Key`, authenticated tenant context and correlation ID.

## 2. Query APIs

- wallet balances and ledger activity
- quote/estimate detail and calculation breakdown
- task cost progress and budget status
- invoice/payment/refund status
- project scope, milestones and change orders
- usage detail by task/run/node/resource
- team cost-center and budget reports
- admin reconciliation and exception queues

Queries must use stable pagination and report `as_of` plus data freshness when aggregates are not real-time.

## 3. Domain events

- `price-book.activated.v1`
- `entitlement.snapshot.changed.v1`
- `wallet.transaction.posted.v1`
- `budget.authorization.created.v1`
- `budget.threshold.reached.v1`
- `task.execution.paused-budget.v1`
- `usage.recorded.v1`
- `usage.rated.v1`
- `task.settled.v1`
- `project.change-order.requested.v1`
- `invoice.finalized.v1`
- `payment.captured.v1`
- `payment.settled.v1`
- `refund.succeeded.v1`
- `reconciliation.exception.created.v1`

## 4. Event envelope

```json
{
  "event_id": "evt_...",
  "event_type": "usage.recorded.v1",
  "schema_version": "1.0",
  "tenant_id": "ten_...",
  "subject_id": "run_...",
  "correlation_id": "corr_...",
  "causation_id": "cmd_or_evt_...",
  "occurred_at": "2026-08-19T10:00:00Z",
  "producer": "metering-service",
  "idempotency_key": "source-scope:key",
  "data": {}
}
```

## 5. Compatibility rules

- Additive fields are optional until all consumers are upgraded.
- Enum expansion requires consumers to tolerate unknown values.
- Breaking semantic changes create a new event/API version.
- Replayed events preserve original `event_id` and add replay metadata outside the business payload.
- PII and secrets are excluded from event payloads unless explicitly classified and encrypted.
