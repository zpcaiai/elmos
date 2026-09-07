# Implementation Roadmap

## Phase 0 — Contract freeze and gap review

Deliver:

- repository inventory;
- domain/API/event/schema/state/identifier freeze;
- existing/new table mapping;
- data migration and rollback plan;
- feature-flag and rollout plan;
- representative fixtures.

Exit:

- no competing source of truth;
- all P0 conflicts have owner and migration;
- account-wide scope of the three-task rule is encoded.

## Phase 1 — Identity, RLS, and immutable task request

Implement:

- OIDC/JWT and membership resolution;
- transaction-local tenant/account context;
- non-superuser runtime roles;
- forced RLS;
- immutable task and input manifest;
- scoped `Idempotency-Key`;
- audit skeleton.

Vertical-slice gate:

- one tenant/account can create and read its task;
- another tenant/account cannot access it through API, raw SQL, or object reference.

## Phase 2 — Three-slot admission and durable queue

Implement:

- account slot rows 1..3;
- atomic claim/renew/release;
- task state transitions;
- `WAITING_FOR_SLOT`;
- concurrency status API;
- scheduler promotion;
- stale slot reconciler.

Gate:

- 100 concurrent starts admit at most three;
- fourth task is durable and later promoted;
- account across multiple tenants remains at most three.

## Phase 3 — Tenant/resource scheduler and workflow start

Implement:

- tenant quotas/resource units;
- workload classes/task queues;
- bounded worker pools;
- weighted fair scheduling;
- deterministic workflow IDs;
- transactional outbox starter or Update-with-Start;
- typed payloads/Search Attributes.

Gate:

- no duplicate/orphan workflow start;
- heavy tasks respect resource units;
- tenant backlog does not starve peers.

## Phase 4 — Progress, control, and current UI

Implement:

- task/node/attempt event journal;
- sequence allocation and idempotency;
- progress snapshots and weights;
- ETA P50/P90;
- SSE replay;
- pause/cancel signals;
- log segmentation.

Gate:

- reconnect replays missed events;
- progress is monotonic;
- cancel reaches running activities;
- progress overhead is bounded.

## Phase 5 — Checkpoint, lease, and recovery

Implement:

- atomic checkpoints;
- side-effect intent/receipt;
- runner lease generation/renewal;
- reaper;
- unknown-result reconciliation;
- compatible resume/fork;
- manual recovery UI/runbook.

Gate:

- crash injection at each boundary causes no duplicate side effect;
- stale completion is rejected;
- checkpoint compatibility is enforced.

## Phase 6 — Input/output archive and retention

Implement:

- object manifests;
- content-addressed encrypted storage;
- immutable artifact versions;
- execution environment lineage;
- integrity verification;
- retention/legal hold/export/delete.

Gate:

- every result traces to exact inputs/versions;
- object mutation/missing content is detected;
- tenant object isolation passes.

## Phase 7 — Usage metering and cost

Implement:

- usage taxonomy;
- price book and FX snapshots;
- model/compute/storage/network/third-party adapters;
- task budgets;
- cost summaries;
- provider reconciliation.

Gate:

- duplicate receipts do not double cost;
- task cost drills to immutable usage;
- historical totals reconcile.

## Phase 8 — Revenue, allocation, and margin

Implement:

- billing mode contracts;
- revenue entries;
- direct/project/subscription allocation;
- refunds/fees/taxes;
- recognized versus collected measures;
- task/platform margin.

Gate:

- allocation sums correctly;
- refunds and settlements reconcile;
- cost/revenue currencies and bases are explicit.

## Phase 9 — Analytics and dashboards

Implement:

- hourly/daily projections;
- operational dashboard;
- task history and exports;
- financial dashboard;
- anomaly/data-quality statuses;
- rebuild job.

Gate:

- projections rebuild from ledgers;
- platform/tenant/task totals reconcile;
- running totals show `as_of` and posting status.

## Phase 10 — Production certification and rollout

Execute:

- contract/schema tests;
- multi-replica load;
- noisy-neighbor/fairness;
- workflow replay;
- RLS/security;
- chaos/recovery;
- provider/payment reconciliation;
- backup/PITR/restore;
- canary tenant rollout;
- rollback/roll-forward drill;
- signed evidence pack.

Release strategy:

```text
schema only
→ shadow events
→ shadow admission decisions
→ selected internal tenants
→ selected customer tenants
→ percentage rollout
→ general availability
```

Hard gates cannot be waived indefinitely. Every waiver has owner, reason, expiry, compensating control, and rollback trigger.

## Suggested implementation ownership

| Area | Primary |
|---|---|
| Identity/RLS/admission/API | Java/Spring control plane |
| Workflow lifecycle | Temporal Java worker |
| Private execution/lease/sandbox | Go runner |
| Web task/finance UI | Next.js/TypeScript |
| Object storage | Artifact module/adapters |
| Usage/cost | Model gateway, runner, storage adapters + Java FinOps module |
| Revenue/payment | Billing module/adapters |
| Analytics | Projection workers/SQL |
| Observability | OpenTelemetry across all components |
| Certification | Repository CI + deployed test environment |

## Migration from existing progress/task tables

1. Freeze old/new mapping.
2. Add new identifiers and projection tables.
3. Backfill historical task/run rows.
4. Begin dual-write of critical events.
5. Compare state and progress checksums.
6. Enable new reads for internal users.
7. Enable new admission.
8. Stop old writes after rollback window.
9. Archive old tables only after evidence and retention review.
