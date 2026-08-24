---
name: elmos-task-lifecycle-temporal
id: ELMOS-MTF-005
version: 1.0.0
description: Implement the durable task/run/node state machine on Temporal with idempotent startup, cancellation, pause/resume, retry, versioning, and PostgreSQL state projection.
layer: workflow
risk: critical
depends_on:
  - elmos-workload-aware-scheduler
---

# elmos-task-lifecycle-temporal

## Purpose

Make every long-running eLMOS task controllable and recoverable without orphan workflows, duplicate side effects, or unqueryable failure states.

## Use this skill when

- Implementing or reviewing the Elmos multi-tenant long-task control plane.
- Adding per-account concurrency, queueing, task progress, pause/resume, recovery, archival, cost, billing, or analytics.
- Converting a scaffold into repository-specific production implementation with executable evidence.

## Hard invariants

- A task request is immutable; retries and resumes create or continue task runs while preserving history.
- Workflow IDs are deterministic and bound to task_id and run number before Temporal startup.
- Workflow startup uses an outbox starter or Update-with-Start to eliminate database/Temporal dual-write races.
- Every terminal workflow path records SUCCEEDED, FAILED, or CANCELLED in PostgreSQL.
- Pause and cancel signals propagate to activities and private runner tasks.

## Required inputs

- Target repository revision and deployment topology.
- Existing identity, task, workflow, runner, storage, model gateway, billing, and observability contracts.
- Applicable tenant, account, project, retention, pricing, budget, and revenue policies.
- Representative fixtures for task types and failure modes.

## Procedure

- Implement the canonical task state machine and validate legal transitions.
- Generate deterministic workflow IDs and persist them before or atomically with start intent.
- Use typed, versioned payload records and Temporal Search Attributes.
- Use explicit application failures, retry policies, heartbeats, cancellation scopes, and Continue-As-New.
- Project workflow transitions into task_run and append-only task_event records with unique transition IDs.
- Handle UNKNOWN_RESULT through reconciliation rather than blind retry.

## Stable implementation tasks

| Task ID | Task | Gate |
|---|---|---|
| `ELMOS-MTF-005-T01` | Define task, run, node, and attempt states and legal transitions. | required |
| `ELMOS-MTF-005-T02` | Create deterministic workflow IDs and run numbers. | required |
| `ELMOS-MTF-005-T03` | Implement idempotent workflow startup through outbox or Update-with-Start. | required |
| `ELMOS-MTF-005-T04` | Use typed versioned workflow payloads. | required |
| `ELMOS-MTF-005-T05` | Persist every critical transition with a unique transition_id. | required |
| `ELMOS-MTF-005-T06` | Implement explicit application failure mapping. | required |
| `ELMOS-MTF-005-T07` | Propagate pause and cancel to all activities and runner tasks. | required |
| `ELMOS-MTF-005-T08` | Implement retry policies by error class. | required |
| `ELMOS-MTF-005-T09` | Add Search Attributes and operational queries. | required |
| `ELMOS-MTF-005-T10` | Use Continue-As-New for long histories. | required |
| `ELMOS-MTF-005-T11` | Project terminal state in a global try/catch/finally path. | required |
| `ELMOS-MTF-005-T12` | Run Temporal replay and duplicate-start tests. | required |

## Primary outputs

- `task-state-machine.yaml`
- `workflow-contracts/`
- `temporal-search-attributes.md`
- `retry-policy.yaml`
- `cancellation-contract.md`
- `workflow-replay-report.json`

## Acceptance criteria

- Concurrent starts do not create duplicate workflows or orphan workflow histories.
- A workflow failure always becomes a durable FAILED or recovery state in PostgreSQL.
- Cancel interrupts supported running work and does not merely change the UI.
- Historical workflow code remains replay-compatible after versioned changes.

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
