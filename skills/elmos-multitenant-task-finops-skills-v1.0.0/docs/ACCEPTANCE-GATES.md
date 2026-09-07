# Acceptance and Production Gates

## Gate G1 — Identity and tenant isolation

- [ ] Tenant/account identity comes from verified authentication and membership.
- [ ] Client tenant header cannot authorize access.
- [ ] All tenant business tables have forced RLS.
- [ ] Runtime roles are non-superuser, non-owner, and lack BYPASSRLS.
- [ ] Cross-tenant API, SQL, object, event, export, and finance tests pass.
- [ ] Audit contains actor, tenant, account, request, trace, task/run, reason, and outcome.

## Gate G2 — Account concurrency

- [ ] Exactly three durable account slot rows exist or are lazily guaranteed.
- [ ] Slot claim is atomic and transactionally bound to admission.
- [ ] Slot renewal/release is fenced by lease generation.
- [ ] One account across tenants never exceeds three active root tasks.
- [ ] Fourth task becomes durable `WAITING_FOR_SLOT`.
- [ ] 100-request multi-replica race admits no more than three.
- [ ] Duplicate create/control requests are idempotent.

## Gate G3 — Scheduling and capacity

- [ ] Workload classes and resource units exist.
- [ ] Tenant and platform quotas are enforced.
- [ ] Temporal task queues and worker concurrency are bounded.
- [ ] Weighted fairness/no-starvation benchmark passes.
- [ ] Queue age, position, reason, and ETA are visible.
- [ ] Saturation degrades by queue/backpressure rather than overload.

## Gate G4 — Workflow correctness

- [ ] Deterministic workflow ID and start intent are durable.
- [ ] No DB/Temporal orphan or duplicate-start race in tests.
- [ ] Typed payloads, versioning, Search Attributes, and Continue-As-New exist.
- [ ] All failure/terminal paths persist state.
- [ ] Pause/cancel propagates to activities/runner.
- [ ] Temporal replay tests pass.

## Gate G5 — Progress and journal

- [ ] Event sequence and transition idempotency are enforced.
- [ ] Critical transitions persist before acknowledgement.
- [ ] High-frequency telemetry is batched and bounded.
- [ ] Progress is monotonic and capped before success.
- [ ] SSE reconnect/replay works.
- [ ] Snapshot rebuild matches source journal.
- [ ] Progress overhead meets measured target.

## Gate G6 — Recovery

- [ ] Every long stage declares checkpoint boundaries.
- [ ] Checkpoints contain required compatibility/lineage fields.
- [ ] Side effects use intents and receipts.
- [ ] Runner lease protocol supports renew/cancel/checkpoint/idempotent complete/fail.
- [ ] Lease expiry enters unknown/reconciliation.
- [ ] Stale generation cannot mutate current attempt.
- [ ] Fault injection produces no duplicate certified side effects.
- [ ] Manual recovery is explicit and audited.

## Gate G7 — Archive and retention

- [ ] Every input/output has an immutable manifest and SHA-256.
- [ ] Large payloads/logs reside in object storage.
- [ ] Execution environment/model/tool/policy/cache lineage is archived.
- [ ] Output versions are append-only.
- [ ] Integrity verification runs before recovery/delivery.
- [ ] Secret retention controls pass.
- [ ] Export, legal hold, and deletion are tenant-isolated and audited.

## Gate G8 — Usage and cost

- [ ] Usage taxonomy and price books are versioned.
- [ ] Model, compute, storage, network, runner, and third-party usage is metered.
- [ ] Provider/internal idempotency prevents duplicate cost.
- [ ] Unit price, currency, FX, and calculation version are snapshotted.
- [ ] Estimated/reserved/posted/final cost are distinct.
- [ ] Budgets and overrides are enforced/audited.
- [ ] Provider invoice reconciliation is executed.
- [ ] Historical totals drill to raw ledger entries.

## Gate G9 — Revenue and margin

- [ ] Charge, credit, refund, recognition, collection, fee, tax, and adjustment are distinct.
- [ ] Revenue entries are append-only.
- [ ] Billing modes have explicit recognition/allocation policy.
- [ ] Task/project allocations sum within precision.
- [ ] Recognized revenue and collected cash are separate.
- [ ] Gross profit/margin use explicit cost/revenue basis.
- [ ] Payment settlement/refund reconciliation is executed.
- [ ] Manual adjustments require approval/evidence.

## Gate G10 — Analytics and data quality

- [ ] Operational and financial metric definitions are versioned.
- [ ] Every total includes scope, currency/basis, and `as_of`.
- [ ] Running totals are marked posting/incomplete.
- [ ] Platform/tenant/task totals reconcile.
- [ ] Projections can be deleted and rebuilt.
- [ ] Drill-through reaches events/usage/revenue.
- [ ] Duplicate, missing, stale, unpriced, unreconciled, and unallocated data is visible.

## Gate G11 — Performance, resilience, and DR

- [ ] Load and soak tests use representative tenants/task mix.
- [ ] Noisy-neighbor and retry-storm tests pass.
- [ ] Database/Temporal/object-store/event-bus/provider failures are injected.
- [ ] Backup, PITR, restore, and replay drills pass.
- [ ] SLO/capacity limits and autonomous machine wall-clock are reported.
- [ ] Alert/runbook coverage exists.
- [ ] Rollback and roll-forward are exercised.

## Gate G12 — Production claim

A release may claim production readiness only when:

- [ ] all hard gates have target-repository executed evidence;
- [ ] evidence identifies commit, migration, environment, configuration, commands, test IDs, traces, task/run IDs, and timestamps;
- [ ] known limitations and waivers are explicit;
- [ ] waivers have owner, expiry, compensating control, and rollback trigger;
- [ ] no placeholder/mock provider is represented as a production integration;
- [ ] certification evidence is signed or otherwise tamper-evident.
