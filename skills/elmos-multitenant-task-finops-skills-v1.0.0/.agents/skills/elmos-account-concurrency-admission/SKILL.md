---
name: elmos-account-concurrency-admission
id: ELMOS-MTF-003
version: 1.0.0
description: Implement race-free, account-wide admission control with a hard maximum of three active root tasks and durable queuing for excess submissions.
layer: runtime-control
risk: critical
depends_on:
  - elmos-tenant-identity-rls
---

# elmos-account-concurrency-admission

## Purpose

Prevent distributed API nodes, retries, tabs, and devices from starting more than three active tasks for the same authenticated account.

## Use this skill when

- Implementing or reviewing the Elmos multi-tenant long-task control plane.
- Adding per-account concurrency, queueing, task progress, pause/resume, recovery, archival, cost, billing, or analytics.
- Converting a scaffold into repository-specific production implementation with executable evidence.

## Hard invariants

- The hard account-wide maximum is exactly three active root tasks; no plan or admin override may raise it.
- The effective admission limit may be lower because of tenant quota, budget, maintenance, or platform capacity.
- Submission and execution admission are separate: a fourth task is stored as WAITING_FOR_SLOT and does not execute.
- PostgreSQL slot rows and transactional locking are authoritative; Redis may accelerate reads but may not decide admission alone.
- Task creation is idempotent by tenant_id, account_id, and Idempotency-Key.

## Required inputs

- Target repository revision and deployment topology.
- Existing identity, task, workflow, runner, storage, model gateway, billing, and observability contracts.
- Applicable tenant, account, project, retention, pricing, budget, and revenue policies.
- Representative fixtures for task types and failure modes.

## Procedure

- Seed or lazily create slot numbers 1, 2, and 3 for each account.
- Claim one free slot in the same database transaction that changes a task from WAITING_FOR_SLOT to ADMITTED.
- Use SELECT FOR UPDATE SKIP LOCKED or an equivalent atomic function; never count then insert.
- Renew slot leases from the workflow control plane and release them only with a matching lease generation.
- When a task reaches a non-slot-consuming state, emit SlotReleased and schedule the next eligible queued task.
- Expose active_slots, maximum_slots=3, queued_count, and queue position to the UI.

## Stable implementation tasks

| Task ID | Task | Gate |
|---|---|---|
| `ELMOS-MTF-003-T01` | Define slot-consuming and non-slot-consuming task states. | required |
| `ELMOS-MTF-003-T02` | Implement three durable account slot rows. | required |
| `ELMOS-MTF-003-T03` | Implement atomic slot claim with row locking and lease generation. | required |
| `ELMOS-MTF-003-T04` | Implement generation-safe slot renewal and release. | required |
| `ELMOS-MTF-003-T05` | Implement idempotent task submission. | required |
| `ELMOS-MTF-003-T06` | Queue fourth and later tasks without executing them. | required |
| `ELMOS-MTF-003-T07` | Promote queued tasks after terminal, paused, or safely reconciled slot release. | required |
| `ELMOS-MTF-003-T08` | Enforce tenant active-task, queued-task, and resource-unit quotas. | required |
| `ELMOS-MTF-003-T09` | Expose concurrency status and queue position APIs. | required |
| `ELMOS-MTF-003-T10` | Publish admission and slot lifecycle events. | required |
| `ELMOS-MTF-003-T11` | Add stale-slot reaping and reconciliation. | required |
| `ELMOS-MTF-003-T12` | Run high-contention race tests across multiple API replicas. | required |

## Primary outputs

- `account-slot-schema.sql`
- `admission-service/`
- `admission-policy.yaml`
- `concurrency-api.yaml`
- `slot-race-test-report.json`
- `queue-fairness-report.json`

## Acceptance criteria

- With 100 simultaneous valid start requests for one account, at most three tasks enter slot-consuming states.
- Two different accounts can each run up to three tasks without sharing slots.
- One account operating in multiple tenants still has at most three active root tasks in total.
- Duplicate create requests return the original task and never consume an additional slot.

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
