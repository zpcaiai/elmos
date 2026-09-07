# Production Readiness Matrix

| Area | Required |
|---|---|
| Durable state | PostgreSQL authoritative |
| Blob state | content-addressed object storage |
| Scheduler | fair, bounded frontier, durable Saga |
| Fencing | atomic per-work-item |
| Worker | addressable, heartbeat, checkpoint |
| Billing | reserve/settle/release/topup |
| Metering | streaming cumulative usage events |
| Idempotency | dedicated request records |
| Provider call replay | receipt/reconciliation |
| Ledger | append-only |
| Accounting | balanced journals |
| Reconciliation | zero unexplained delta |
| Events | transactional outbox |
| UI | rebuildable projections |
| RLS | request scoped + controlled background path |
| Recovery | all non-terminal states reconciled |
| Deployment | Stateful workers / exact addressing |
| QA | concurrency, chaos, PITR, tenant isolation |
