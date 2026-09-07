---
name: elmos-usage-metering-cost-ledger
id: ELMOS-MTF-009
version: 1.0.0
description: Meter model, compute, storage, network, runner, and third-party usage in an immutable ledger and calculate estimated, reserved, posted, and actual task cost.
layer: finops
risk: critical
depends_on:
  - elmos-task-io-artifact-archive
---

# elmos-usage-metering-cost-ledger

## Purpose

Calculate the real system cost of each task and historical total cost with reproducible price-book snapshots and idempotent provider reconciliation.

## Use this skill when

- Implementing or reviewing the Elmos multi-tenant long-task control plane.
- Adding per-account concurrency, queueing, task progress, pause/resume, recovery, archival, cost, billing, or analytics.
- Converting a scaffold into repository-specific production implementation with executable evidence.

## Hard invariants

- Usage events are append-only, signed quantities with globally unique provider or internal idempotency keys.
- Each usage event records provider, SKU, unit, quantity, price-book version, unit price, currency, FX snapshot, and calculated base-currency cost.
- Model cost separates uncached input, cached input, output, embedding, image, audio, and other billable units.
- System autonomous runtime and human review cost are reported separately.
- Ongoing totals are explicitly reported as posted through an as_of timestamp.

## Required inputs

- Target repository revision and deployment topology.
- Existing identity, task, workflow, runner, storage, model gateway, billing, and observability contracts.
- Applicable tenant, account, project, retention, pricing, budget, and revenue policies.
- Representative fixtures for task types and failure modes.

## Procedure

- Define canonical usage units for model, CPU, memory, GPU, sandbox, storage, egress, queue, rendering, testing, and third-party APIs.
- Version provider and internal price books with effective time ranges.
- Emit usage events from model gateway, runner, object store, workflow, and external adapters.
- Calculate event cost at ingestion using the effective price and FX snapshot.
- Aggregate per node, run, task, account, tenant, project, model, provider, and day.
- Reconcile provider invoices and adjust through explicit correction events, never in-place edits.

## Stable implementation tasks

| Task ID | Task | Gate |
|---|---|---|
| `ELMOS-MTF-009-T01` | Define canonical usage dimensions and units. | required |
| `ELMOS-MTF-009-T02` | Create versioned provider and internal price books. | required |
| `ELMOS-MTF-009-T03` | Meter uncached input, cached input, output, and specialized model units. | required |
| `ELMOS-MTF-009-T04` | Meter CPU, memory, GPU, sandbox, and runner time. | required |
| `ELMOS-MTF-009-T05` | Meter storage byte-hours and network egress. | required |
| `ELMOS-MTF-009-T06` | Meter third-party API and rendering costs. | required |
| `ELMOS-MTF-009-T07` | Ingest idempotent immutable usage events. | required |
| `ELMOS-MTF-009-T08` | Calculate base-currency cost with FX snapshots. | required |
| `ELMOS-MTF-009-T09` | Track estimated, reserved, posted, and final actual cost. | required |
| `ELMOS-MTF-009-T10` | Enforce per-task and tenant budget gates. | required |
| `ELMOS-MTF-009-T11` | Aggregate historical total cost by business dimensions. | required |
| `ELMOS-MTF-009-T12` | Reconcile provider invoices with explicit correction events. | required |

## Primary outputs

- `usage-event.schema.json`
- `price-book.schema.json`
- `metering-adapters/`
- `task-cost-summary.sql`
- `budget-policy.yaml`
- `provider-reconciliation-report.json`

## Acceptance criteria

- Replaying the same provider usage receipt does not increase cost.
- Changing a future price book does not retroactively alter already posted task cost.
- Every task cost can be decomposed to usage events and price snapshots.
- Historical total cost equals the sum of posted ledger entries for the selected scope and as_of time.

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
