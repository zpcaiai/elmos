---
name: elmos-multitenant-task-finops-orchestrator
id: ELMOS-MTF-001
version: 1.0.0
description: Orchestrate the end-to-end implementation of multi-tenant task admission, progress/recovery, archival, metering, revenue, and profitability for eLMOS.
layer: orchestration
risk: critical
depends_on:
  - elmos-architecture-contract-governance
  - elmos-identity-tenant-security
  - elmos-temporal-task-reliability
  - elmos-observability-finops
---

# elmos-multitenant-task-finops-orchestrator

## Purpose

Turn the product requirement into a repository-specific, testable implementation plan without duplicating existing eLMOS infrastructure capabilities.

## Use this skill when

- Implementing or reviewing the Elmos multi-tenant long-task control plane.
- Adding per-account concurrency, queueing, task progress, pause/resume, recovery, archival, cost, billing, or analytics.
- Converting a scaffold into repository-specific production implementation with executable evidence.

## Hard invariants

- The account-wide active root-task limit is three across every tenant membership and client session.
- A fourth submitted root task is durable but remains WAITING_FOR_SLOT until a slot is released; internal DAG nodes do not consume account root-task slots.
- PostgreSQL is the authoritative source for task state, slots, checkpoints, usage, revenue, and audit records.
- Temporal owns durable orchestration; business state and financial truth remain queryable in PostgreSQL.
- No production-complete claim is allowed without repository migrations, integration tests, load tests, recovery evidence, and financial reconciliation evidence.

## Required inputs

- Target repository revision and deployment topology.
- Existing identity, task, workflow, runner, storage, model gateway, billing, and observability contracts.
- Applicable tenant, account, project, retention, pricing, budget, and revenue policies.
- Representative fixtures for task types and failure modes.

## Procedure

- Inventory current task, workflow, runner, identity, billing, object-storage, and observability code.
- Map existing entities and migrations to the canonical contracts in this package; record reuse, conflict, and missing items.
- Freeze task state, event, checkpoint, usage, revenue, API, and RLS contracts before implementation.
- Build a minimal vertical slice: create task → queue/admit → run one node → checkpoint → emit progress → meter cost → produce output → allocate revenue.
- Add cancellation, pause/resume, retries, lease expiry, reconciliation, and duplicate-delivery paths.
- Execute the certification skill and bind every acceptance criterion to executable evidence.

## Stable implementation tasks

| Task ID | Task | Gate |
|---|---|---|
| `ELMOS-MTF-001-T01` | Scan the target repository and locate identity, task, workflow, runner, event, storage, billing, and analytics boundaries. | required |
| `ELMOS-MTF-001-T02` | Create a requirement-to-component gap matrix and mark existing, reusable, conflicting, and missing implementation. | required |
| `ELMOS-MTF-001-T03` | Freeze domain names, state machine, identifiers, idempotency keys, event names, and financial terms. | required |
| `ELMOS-MTF-001-T04` | Select the authoritative storage owner for every persistent data type and prohibit dual truth. | required |
| `ELMOS-MTF-001-T05` | Plan backward-compatible schema migrations and rollback/roll-forward procedures. | required |
| `ELMOS-MTF-001-T06` | Define the first production-shaped vertical slice and its fixtures. | required |
| `ELMOS-MTF-001-T07` | Sequence dependent skills and assign evidence owners. | required |
| `ELMOS-MTF-001-T08` | Define environment-specific feature flags and safe rollout order. | required |
| `ELMOS-MTF-001-T09` | Integrate runtime ETA reporting with queue, execution, model, validation, transfer, and recovery time. | required |
| `ELMOS-MTF-001-T10` | Track implementation status in a stable task matrix. | required |
| `ELMOS-MTF-001-T11` | Run all package and repository validation gates. | required |
| `ELMOS-MTF-001-T12` | Generate the final execution report with known limitations and waivers. | required |

## Primary outputs

- `implementation-plan.md`
- `gap-analysis.json`
- `contract-freeze.json`
- `migration-plan.md`
- `execution-report.md`
- `evidence-bundle.json`

## Acceptance criteria

- Every requirement has an implementation owner, API or event contract, database owner, test, and evidence reference.
- The first vertical slice can be replayed from a fixed revision with identical durable state and financial totals.
- Existing eLMOS skills are extended rather than silently replaced.
- No unresolved P0 conflict remains between workflow history and PostgreSQL task truth.

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
