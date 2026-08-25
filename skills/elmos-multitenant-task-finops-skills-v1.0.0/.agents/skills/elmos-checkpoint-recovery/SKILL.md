---
name: elmos-checkpoint-recovery
id: ELMOS-MTF-007
version: 1.0.0
description: Create atomic checkpoints, side-effect receipts, runner leases, compatibility validation, and reconciliation paths for safe pause, resume, retry, and crash recovery.
layer: reliability
risk: critical
depends_on:
  - elmos-task-lifecycle-temporal
  - elmos-task-progress-journal
---

# elmos-checkpoint-recovery

## Purpose

Resume interrupted tasks from the latest safe point without repeating externally visible side effects or corrupting evidence.

## Use this skill when

- Implementing or reviewing the Elmos multi-tenant long-task control plane.
- Adding per-account concurrency, queueing, task progress, pause/resume, recovery, archival, cost, billing, or analytics.
- Converting a scaffold into repository-specific production implementation with executable evidence.

## Hard invariants

- Every durable stage boundary records checkpoint_id, input manifest digest, repository revision, state digest, completed side effects, cache keys, model/tool versions, and next node.
- External side effects require idempotency keys and immutable completion receipts.
- Lease renewal, completion, failure, and release carry attempt number and lease generation.
- An expired running lease enters UNKNOWN_RESULT and RECONCILING before retry.
- An incompatible checkpoint forks a new run and never overwrites old evidence.

## Required inputs

- Target repository revision and deployment topology.
- Existing identity, task, workflow, runner, storage, model gateway, billing, and observability contracts.
- Applicable tenant, account, project, retention, pricing, budget, and revenue policies.
- Representative fixtures for task types and failure modes.

## Procedure

- Define safe checkpoint boundaries for every workflow and long-running node.
- Write checkpoint plus node transition and outbox event atomically.
- Persist side-effect intent and receipt for Git, payment, provider, storage, and external API operations.
- Renew runner leases and emit heartbeats with attempt and generation.
- Reconcile expired leases against receipts, artifacts, provider IDs, and workspace state.
- Validate checkpoint compatibility before resume and choose continue, restart-node, fork-run, or manual recovery.

## Stable implementation tasks

| Task ID | Task | Gate |
|---|---|---|
| `ELMOS-MTF-007-T01` | Identify safe checkpoint boundaries for every task type. | required |
| `ELMOS-MTF-007-T02` | Persist atomic checkpoint manifests. | required |
| `ELMOS-MTF-007-T03` | Record completed side effects and immutable receipts. | required |
| `ELMOS-MTF-007-T04` | Implement runner lease generation and renewal. | required |
| `ELMOS-MTF-007-T05` | Implement generation-safe complete and fail operations. | required |
| `ELMOS-MTF-007-T06` | Detect expired leases and set UNKNOWN_RESULT. | required |
| `ELMOS-MTF-007-T07` | Reconcile provider, workspace, artifact, and receipt state. | required |
| `ELMOS-MTF-007-T08` | Validate input, revision, tool, model, and schema compatibility. | required |
| `ELMOS-MTF-007-T09` | Resume from a compatible checkpoint. | required |
| `ELMOS-MTF-007-T10` | Fork a new run for incompatible recovery. | required |
| `ELMOS-MTF-007-T11` | Expose manual recovery with audited decisions. | required |
| `ELMOS-MTF-007-T12` | Inject crashes at every checkpoint and side-effect boundary. | required |

## Primary outputs

- `checkpoint-schema.json`
- `side-effect-receipt-schema.json`
- `runner-lease-protocol.md`
- `reconciliation-rules.yaml`
- `recovery-runbook.md`
- `fault-injection-report.json`

## Acceptance criteria

- A worker crash after an external side effect does not repeat that side effect on recovery.
- A stale worker cannot complete or release a newer attempt.
- Resume selects the most recent compatible checkpoint and records the recovery reason.
- Unsupported ambiguity is surfaced as MANUAL_RECOVERY rather than silently retried.

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
