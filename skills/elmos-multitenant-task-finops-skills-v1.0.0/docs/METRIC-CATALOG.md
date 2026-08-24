# Metric Catalog

## Concurrency and queue

- `account_active_root_tasks`: occupied account slots, maximum 3.
- `account_waiting_tasks`: durable queued tasks for an account.
- `tenant_active_tasks`: slot-consuming tasks in a tenant.
- `tenant_concurrency_units_used`: sum of admitted workload resource units.
- `queue_age_p50/p95/p99`: time from durable submission to admission.
- `slot_claim_conflict_rate`: retries caused by account-slot contention.
- `queue_promotion_latency`: safe slot release to next admission.

## Execution and recovery

- task success/failure/cancel/pause rates;
- node retry and recovery rates;
- stale lease count and reconciliation age;
- checkpoint creation/verification latency;
- progress freshness and projector lag;
- autonomous system runtime split into queue, execution, model, validation, transfer, and recovery.

## Cost and business

- estimated/reserved/posted/final cost per task;
- model, compute, GPU, storage, egress, third-party, retry, recovery, and shared cost;
- billed, recognized, collected, refund, credit, fee, and tax totals;
- gross profit and gross margin by task, project, account, tenant, task type, model, and period;
- cost-estimate error and provider reconciliation coverage;
- unallocated revenue/shared-cost pools.

Every metric declares owner, grain, filters, event-time/processing-time basis, currency, `as_of`, freshness SLO, and source lineage.
