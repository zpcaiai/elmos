---
name: elmos-task-financial-analytics
id: ELMOS-MTF-011
version: 1.0.0
description: Build trustworthy task, usage, cost, revenue, margin, throughput, recovery, and unit-economics aggregates and dashboards.
layer: analytics
risk: high
depends_on:
  - elmos-usage-metering-cost-ledger
  - elmos-revenue-margin-ledger
---

# elmos-task-financial-analytics

## Purpose

Turn archived task history into operational and commercial statistics while preserving ledger traceability and data-quality qualifications.

## Use this skill when

- Implementing or reviewing the Elmos multi-tenant long-task control plane.
- Adding per-account concurrency, queueing, task progress, pause/resume, recovery, archival, cost, billing, or analytics.
- Converting a scaffold into repository-specific production implementation with executable evidence.

## Hard invariants

- Transactional ledgers remain the source of truth; analytics tables are rebuildable projections.
- Every total includes scope, currency basis, recognition basis, and as_of timestamp.
- Running-period totals are qualified when data is incomplete or still posting.
- Metrics can drill from platform to tenant, account, project, task, run, node, usage, and ledger entries.
- Metric definitions are versioned and tested against reconciliation queries.

## Required inputs

- Target repository revision and deployment topology.
- Existing identity, task, workflow, runner, storage, model gateway, billing, and observability contracts.
- Applicable tenant, account, project, retention, pricing, budget, and revenue policies.
- Representative fixtures for task types and failure modes.

## Procedure

- Build incremental daily and hourly aggregates from task, event, usage, cost, and revenue ledgers.
- Expose throughput, queue time, execution time, success, retry, recovery, cancellation, token, infrastructure cost, revenue, profit, and margin.
- Add dimensions for task type, model, provider, tenant, account, project, workload, cache status, and time.
- Create anomaly rules for cost spikes, negative margin, stalled tasks, missing revenue, and unreconciled usage.
- Provide downloadable task history and finance exports with tenant isolation.
- Rebuild aggregates from source ledgers and compare checksums.

## Stable implementation tasks

| Task ID | Task | Gate |
|---|---|---|
| `ELMOS-MTF-011-T01` | Define metric names, formulas, dimensions, and grain. | required |
| `ELMOS-MTF-011-T02` | Create hourly and daily task aggregates. | required |
| `ELMOS-MTF-011-T03` | Create cost, revenue, profit, and margin aggregates. | required |
| `ELMOS-MTF-011-T04` | Create task throughput and concurrency metrics. | required |
| `ELMOS-MTF-011-T05` | Create progress, retry, recovery, and cancellation metrics. | required |
| `ELMOS-MTF-011-T06` | Create model and cache efficiency metrics. | required |
| `ELMOS-MTF-011-T07` | Add filters by tenant, account, project, task type, model, and period. | required |
| `ELMOS-MTF-011-T08` | Add drill-through to source events and ledger entries. | required |
| `ELMOS-MTF-011-T09` | Detect missing, duplicated, stale, and unreconciled financial data. | required |
| `ELMOS-MTF-011-T10` | Create tenant-isolated CSV/JSON exports. | required |
| `ELMOS-MTF-011-T11` | Rebuild and checksum aggregate projections. | required |
| `ELMOS-MTF-011-T12` | Publish operational and executive dashboard specifications. | required |

## Primary outputs

- `metric-catalog.yaml`
- `analytics-rollups.sql`
- `dashboard-spec.md`
- `financial-export-schema.json`
- `data-quality-checks.sql`
- `aggregate-rebuild-report.json`

## Acceptance criteria

- Platform totals equal the sum of tenant totals for the same scope, basis, currency, and as_of time.
- Task-level drill-through explains every cost and revenue component.
- Deleting analytics projections and rebuilding them produces equivalent totals.
- Dashboards clearly distinguish estimates from posted actuals and recognized revenue from cash collection.

## Required tests

- Unit tests for state transitions, formulas, policy decisions, and idempotency.
- PostgreSQL integration tests with a non-superuser role and real RLS.
- Temporal integration and workflow replay tests when workflow behavior is in scope.
- Multi-replica concurrency tests for race-sensitive behavior.
- Failure-injection and recovery tests for long-running or side-effecting behavior.
- Contract tests for APIs, events, schemas, and object manifests.
- Financial reconciliation tests whenever usage, cost, revenue, or margin is in scope.

## Evidence contract

For every completed task, record:

- repository commit SHA and migration version;
- environment, tenant/account fixtures, and configuration digest;
- executed command and machine wall-clock duration;
- test result, trace IDs, task/run IDs, and relevant event sequences;
- database/object-store evidence references;
- assumptions, residual risks, waivers, owner, and expiry.

## Production-claim boundary

This Skill is an implementation specification. Do **not** claim the Elmos target repository has implemented or passed this capability until repository-specific migrations, code, tests, load runs, recovery campaigns, tenant-isolation checks, provider reconciliation, and release gates have produced executable evidence.
