# Progress, Checkpoints, and Recovery

## 1. Design goal

Progress must be detailed enough for users, operations, analytics, and ETA calibration, but recording it must not become the bottleneck of long-running work. Recovery-critical state is durable before acknowledgement; high-frequency telemetry is asynchronous and batched.

## 2. Event journal

Canonical event types:

### Task lifecycle

```text
TaskCreated
TaskQueued
TaskAdmitted
TaskStarting
TaskStarted
TaskPauseRequested
TaskPaused
TaskResumeRequested
TaskCancelRequested
TaskCancelled
TaskRetryScheduled
TaskUnknownResult
TaskReconciling
TaskManualRecoveryRequired
TaskSucceeded
TaskFailed
```

### Node lifecycle

```text
NodePlanned
NodeReady
NodeScheduled
NodeLeased
NodeStarted
NodeHeartbeat
NodeProgressed
NodeCheckpointing
NodeCheckpointed
NodeRetryScheduled
NodeUnknownResult
NodeReconciling
NodeSucceeded
NodeFailed
NodeCancelled
NodeSkipped
```

### Data and finance

```text
InputArchived
ArtifactProduced
LogSegmentStored
SideEffectIntentRecorded
SideEffectReceiptRecorded
UsageRecorded
CostProjectionUpdated
RevenueAllocated
FinancialProjectionUpdated
```

### Control and infrastructure

```text
SlotClaimed
SlotRenewed
SlotReleased
QuotaBlocked
BudgetBlocked
WorkflowStartRequested
WorkflowStarted
OutboxDelivered
RecoveryDecisionRecorded
```

## 3. Event contract

Required fields:

```json
{
  "schema_version": "1.0",
  "event_id": "uuid",
  "transition_id": "globally unique idempotency key",
  "tenant_id": "uuid",
  "account_id": "uuid",
  "task_id": "uuid",
  "task_run_id": "uuid",
  "sequence_no": 42,
  "event_type": "NodeCheckpointed",
  "node_key": "verify",
  "node_attempt_id": "uuid",
  "checkpoint_id": "uuid",
  "occurred_at": "timestamp",
  "actor_type": "WORKFLOW",
  "actor_id": "string",
  "trace_id": "string",
  "request_id": "string",
  "payload": {}
}
```

Consumers process at least once and deduplicate by `event_id` or `transition_id`.

## 4. Sequence allocation

A durable append function:

1. locks `task_run`;
2. checks `transition_id`;
3. increments `next_event_sequence`;
4. inserts the event;
5. returns the allocated sequence.

The UI may receive events out of order from the bus but restores order by sequence. Missing sequence ranges trigger replay from the API.

## 5. Progress model

### Node progress

Each node reports:

- state;
- `completed_units`;
- `total_units` where measurable;
- fractional progress;
- elapsed runtime;
- heartbeat time;
- attempt;
- retry/recovery status.

### Root progress

```text
overall_progress
= sum(node_weight × node_progress)
  / sum(current_planned_node_weights)
```

Rules:

- monotonic within a run;
- capped at 99% until all required nodes and finalization succeed;
- dynamically discovered nodes add weight using a declared policy;
- skipped nodes contribute according to policy and reason;
- failed/cancelled tasks retain last progress plus terminal state.

### Weight sources

1. measured historical P50 wall-clock for comparable tasks;
2. static fallback by node type;
3. input-size/resource estimate;
4. calibrated correction during execution.

Store weight-model version and assumptions so ETA errors can be analyzed.

## 6. ETA

Report:

```text
Autonomous system runtime ETA
= remaining queue
+ remaining execution
+ model/provider wait
+ validation
+ transfer/render/export
+ expected retry/recovery allowance
```

Provide P50 and P90. Human approval waiting time and human-equivalent engineering effort are separate fields.

During execution, update ETA from:

- completed node actuals;
- current node throughput;
- queue and worker saturation;
- provider rate limits;
- retry count;
- cache hit/miss;
- artifact transfer rate;
- historical comparable tasks.

## 7. Asynchronous ingestion

High-frequency worker telemetry flows through a bounded client buffer:

- coalesce progress deltas by node;
- batch heartbeats;
- rotate log segments by size/time;
- flush on interval, node terminal state, checkpoint, pause, cancel, and shutdown;
- spill to local durable buffer if the event endpoint is temporarily unavailable;
- drop only explicitly non-critical samples and increment a loss metric.

Critical events bypass the lossy/coalescing path.

## 8. Checkpoints

### Required checkpoint contents

- task/run/node/attempt identifiers;
- input manifest and repository snapshot digest;
- workflow/schema/policy versions;
- current durable state digest;
- completed node outputs;
- completed side-effect receipts;
- cache keys and dependency digests;
- model/provider/tool versions;
- sandbox/runtime image digest;
- next executable node;
- compatibility rules;
- object URI/hash for large state;
- created time and trace.

### Atomicity

Checkpoint commit should atomically persist:

- checkpoint metadata;
- node/task state transition;
- progress event;
- side-effect/output references;
- outbox event.

The object content must be uploaded and hash-verified before the database row marks it available.

## 9. Side-effect receipts

Examples:

- Git branch/commit/PR creation;
- object upload;
- provider generation request;
- payment/refund;
- webhook delivery;
- email/notification;
- external database migration;
- deployment;
- artifact signing.

Receipt fields:

- operation type;
- idempotency key;
- intent hash;
- provider/external object ID;
- request and response digests;
- completion/failure status;
- compensation reference;
- attempt and lease generation;
- timestamp.

Recovery checks receipts before repeating an operation.

## 10. Runner lease protocol

Endpoints/commands:

```text
lease
ack
renew
progress
logs
checkpoint
complete
fail
cancel
reconcile
```

Every command includes:

```text
task_run_id
node_key
attempt_no
lease_generation
runner_id
receipt_id/idempotency_key
```

A stale generation receives conflict and may not mutate current state.

## 11. Recovery decision matrix

| Observation | Decision |
|---|---|
| No side-effect intent, checkpoint available | Resume/retry |
| Intent exists, no receipt, provider proves no operation | Retry |
| Receipt proves success, local callback lost | Mark completed and continue |
| Provider operation in progress | Wait/reconcile |
| Provider result exists but content/hash differs | Manual recovery/security review |
| Workspace contains uncommitted partial changes | Restore/fork according to checkpoint policy |
| Checkpoint input/revision/tool compatible | Resume |
| Checkpoint incompatible but restartable | Fork new run from earlier safe input |
| Irreducible ambiguity | `MANUAL_RECOVERY` |

## 12. Snapshot rebuild

A recovery test deletes `task_progress_snapshot` and rebuilds it by replaying task events in sequence. The rebuilt snapshot must match:

- task/run/node states;
- current node;
- progress;
- retry/recovery counts;
- last checkpoint;
- artifact counts;
- posted cost/revenue watermarks.

## 13. Client reconnect

SSE flow:

1. client stores last received `sequence_no`;
2. reconnects with `Last-Event-ID` or `after_sequence`;
3. API reads durable events greater than that sequence;
4. after catch-up, live stream continues;
5. if retained history is archived, API returns snapshot plus archive reference/watermark.

Client disconnect never controls task execution.

## 14. Recovery objectives

Targets to validate:

- critical task event loss: zero;
- progress propagation P95 ≤ 2 seconds;
- checkpoint RPO: latest declared safe point;
- stale runner detection: configured lease timeout plus reaper interval;
- supported recovery decision P95 within two minutes after detection, excluding external provider ambiguity;
- duplicate externally visible side effects: zero in certified scenarios;
- snapshot rebuild parity: exact for state/counts and within defined numeric precision for ETA/financial projections.
