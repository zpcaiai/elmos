---
name: elmos-task-progress-journal
id: ELMOS-MTF-006
version: 1.0.0
description: Record append-only task and node progress events, maintain compact progress snapshots, and stream near-real-time updates without slowing task execution.
layer: observability
risk: high
depends_on:
  - elmos-task-lifecycle-temporal
---

# elmos-task-progress-journal

## Purpose

Provide trustworthy progress, node history, ETA calibration, statistics, and recovery evidence for every task.

## Use this skill when

- Implementing or reviewing the Elmos multi-tenant long-task control plane.
- Adding per-account concurrency, queueing, task progress, pause/resume, recovery, archival, cost, billing, or analytics.
- Converting a scaffold into repository-specific production implementation with executable evidence.

## Hard invariants

- Critical transitions, node completion, checkpoint references, and financial usage acknowledgements are durably persisted before acknowledgement.
- High-frequency heartbeats, log chunks, and progress deltas are asynchronously batched and may be eventually consistent.
- Every task-run event has a monotonic sequence number and an idempotent transition or event key.
- Progress never decreases for the same run and never reaches 100 percent before a terminal success state.
- Large logs are stored in object storage; PostgreSQL stores segment references, hashes, time ranges, and summaries.

## Required inputs

- Target repository revision and deployment topology.
- Existing identity, task, workflow, runner, storage, model gateway, billing, and observability contracts.
- Applicable tenant, account, project, retention, pricing, budget, and revenue policies.
- Representative fixtures for task types and failure modes.

## Procedure

- Append NodeScheduled, NodeStarted, NodeHeartbeat, NodeCompleted, NodeFailed, CheckpointCommitted, ArtifactProduced, UsageRecorded, and task-control events.
- Aggregate events into task_progress_snapshot with weighted node progress.
- Estimate node weights from historical wall-clock distributions and retain the assumptions.
- Publish progress through transactional outbox and SSE; allow replay from after_sequence.
- Batch heartbeats and logs with bounded buffers and flush on node completion or shutdown.
- Rebuild snapshots from the event journal to prove recoverability.

## Stable implementation tasks

| Task ID | Task | Gate |
|---|---|---|
| `ELMOS-MTF-006-T01` | Define the append-only task event catalog. | required |
| `ELMOS-MTF-006-T02` | Allocate monotonic per-run event sequences. | required |
| `ELMOS-MTF-006-T03` | Enforce event and transition idempotency. | required |
| `ELMOS-MTF-006-T04` | Persist current node and progress snapshots. | required |
| `ELMOS-MTF-006-T05` | Compute weighted monotonic progress. | required |
| `ELMOS-MTF-006-T06` | Store elapsed time and machine ETA P50/P90. | required |
| `ELMOS-MTF-006-T07` | Batch asynchronous heartbeat and progress writes. | required |
| `ELMOS-MTF-006-T08` | Segment large logs into object storage. | required |
| `ELMOS-MTF-006-T09` | Publish outbox events to the configured event bus. | required |
| `ELMOS-MTF-006-T10` | Expose SSE replay with after_sequence. | required |
| `ELMOS-MTF-006-T11` | Rebuild snapshots from the journal. | required |
| `ELMOS-MTF-006-T12` | Test duplicate, delayed, and out-of-order event delivery. | required |

## Primary outputs

- `task-event-schema.json`
- `progress-aggregator/`
- `sse-stream-contract.yaml`
- `node-weight-model.json`
- `log-segment-policy.md`
- `progress-rebuild-report.json`

## Acceptance criteria

- The UI can reconnect and replay all missed progress from a sequence number.
- Critical state and checkpoint events survive worker or API crashes.
- Progress recording adds bounded overhead under load and does not use one-second database polling.
- A progress snapshot can be deleted and deterministically rebuilt from events.

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
