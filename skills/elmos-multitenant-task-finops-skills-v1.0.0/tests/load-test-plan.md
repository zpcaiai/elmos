# Load and Concurrency Test Plan

## Objectives

Prove the three-task invariant under contention and establish sustainable throughput for submission, progress ingestion, scheduling, recovery, and financial posting.

## Workload profiles

1. **Single-account hotspot:** 100–10,000 simultaneous create/start requests for one account across 2–8 API replicas.
2. **Many-account SaaS:** 10,000 accounts, Poisson arrivals, each account limited to three root tasks.
3. **Cross-tenant account:** one account belongs to 20 tenants and submits from every tenant.
4. **Mixed workload:** small CPU, model-heavy, high-memory conversion, GPU validation, and private-runner tasks.
5. **Progress storm:** up to 50 node heartbeats per second per active task, coalesced before durable projection.
6. **Financial ingestion:** bursty provider receipts, duplicate callbacks, corrections, and delayed finalization.
7. **Queue churn:** frequent pause/resume/cancel plus slot expiry and promotion.

## Invariants checked continuously

```sql
-- Must always return zero rows.
SELECT account_id, count(*)
FROM elmos.account_task_slot
WHERE task_id IS NOT NULL
GROUP BY account_id
HAVING count(*) > 3;
```

Also verify one occupied task maps to one slot, lease generations never move backwards, terminal/paused tasks do not retain a slot beyond the release SLO, and ledger idempotency constraints never permit duplicate cost/revenue.

## Performance targets

These are default certification targets and must be calibrated to the chosen deployment size:

| Metric | Target |
|---|---:|
| Task submission API P95, excluding upload | ≤ 250 ms |
| Task submission API P99 | ≤ 750 ms |
| Slot claim transaction P95 | ≤ 50 ms |
| Queue promotion after safe slot release P95 | ≤ 2 s |
| Durable critical event append P95 | ≤ 100 ms |
| UI progress freshness P95 | ≤ 2 s |
| Progress ingestion sustained rate | ≥ 20,000 events/s per reference cluster |
| Usage/revenue ledger sustained rate | ≥ 5,000 entries/s per reference cluster |
| Projection catch-up after 30-minute outage | ≤ 15 min |
| Scheduler duplicate-start rate | 0 |
| Account oversubscription count | 0 |
| Lost required events/checkpoints/ledger entries | 0 |

## Test method

- Run warm-up, steady-state, spike, and soak phases.
- Separate client, API, database, Temporal, event bus, worker, object-store, and provider-emulator latency.
- Record database lock wait, pool saturation, WAL, vacuum, index size, queue age, outbox age, Temporal task queue lag, worker utilization, object-store throughput, and event projector lag.
- Test both uniform traffic and adversarial hot accounts.
- Repeat after one API replica, one worker group, and one database read replica are removed.

## Required capacity conclusions

The report must identify per-deployment sustainable active root tasks, internal node concurrency, submissions per second, progress events per second, ledger postings per second, storage growth per task, and scaling bottlenecks. It must not infer production capacity from unit tests.
