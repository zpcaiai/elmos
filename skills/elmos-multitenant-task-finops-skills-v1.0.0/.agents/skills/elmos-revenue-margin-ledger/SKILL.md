---
name: elmos-revenue-margin-ledger
id: ELMOS-MTF-010
version: 1.0.0
description: Record charges, credits, refunds, recognition, collection, and task/project allocations for prepaid, pay-as-you-go, subscription, fixed-project, and private-license revenue.
layer: billing
risk: critical
depends_on:
  - elmos-usage-metering-cost-ledger
---

# elmos-revenue-margin-ledger

## Purpose

Measure each task's attributable revenue, historical total revenue, gross profit, and gross margin without conflating billing, recognition, and cash collection.

## Use this skill when

- Implementing or reviewing the Elmos multi-tenant long-task control plane.
- Adding per-account concurrency, queueing, task progress, pause/resume, recovery, archival, cost, billing, or analytics.
- Converting a scaffold into repository-specific production implementation with executable evidence.

## Hard invariants

- Revenue entries are append-only signed ledger events; corrections are new entries.
- Quoted, billed, recognized, and collected amounts are distinct measures.
- The default profitability measure uses recognized revenue minus posted actual system cost.
- Fixed project and subscription revenue is allocated to tasks through a versioned, auditable allocation policy.
- Refunds, credits, taxes, payment fees, and currency conversion are represented explicitly.

## Required inputs

- Target repository revision and deployment topology.
- Existing identity, task, workflow, runner, storage, model gateway, billing, and observability contracts.
- Applicable tenant, account, project, retention, pricing, budget, and revenue policies.
- Representative fixtures for task types and failure modes.

## Procedure

- Create billing account, order, invoice/charge reference, revenue entry, and allocation contracts.
- Support prepaid credit consumption, pay-as-you-go usage, subscription inclusion/overage, fixed project fees, and private/offline license revenue.
- Map revenue entries to tenant, account, project, task, and run where attributable.
- Allocate shared revenue by direct, milestone, or usage-weighted policy and version the policy.
- Calculate recognized revenue, collected cash, net billed revenue, gross profit, and gross margin.
- Reconcile payment-provider settlements and record fees and refunds separately.

## Stable implementation tasks

| Task ID | Task | Gate |
|---|---|---|
| `ELMOS-MTF-010-T01` | Define supported billing modes and revenue states. | required |
| `ELMOS-MTF-010-T02` | Create append-only revenue ledger entries. | required |
| `ELMOS-MTF-010-T03` | Record charges, credits, refunds, recognition, and collection separately. | required |
| `ELMOS-MTF-010-T04` | Map direct task and project revenue. | required |
| `ELMOS-MTF-010-T05` | Allocate fixed-project revenue by milestone or usage. | required |
| `ELMOS-MTF-010-T06` | Allocate subscription revenue with a versioned policy. | required |
| `ELMOS-MTF-010-T07` | Record taxes, payment fees, and FX separately. | required |
| `ELMOS-MTF-010-T08` | Calculate recognized and collected totals. | required |
| `ELMOS-MTF-010-T09` | Calculate per-task gross profit and gross margin. | required |
| `ELMOS-MTF-010-T10` | Calculate tenant, account, project, and platform totals. | required |
| `ELMOS-MTF-010-T11` | Reconcile payment-provider settlements. | required |
| `ELMOS-MTF-010-T12` | Audit manual revenue and allocation adjustments. | required |

## Primary outputs

- `revenue-entry.schema.json`
- `revenue-allocation.schema.json`
- `billing-mode-catalog.yaml`
- `revenue-recognition-policy.md`
- `task-margin-summary.sql`
- `settlement-reconciliation-report.json`

## Acceptance criteria

- A refund reduces the correct billed, collected, and recognized measures through explicit entries.
- Per-task allocated revenue sums to the source revenue amount within currency precision.
- Historical total revenue is reproducible for a selected recognition basis and as_of time.
- Gross margin never silently mixes currencies or human-equivalent effort with system cost.

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
