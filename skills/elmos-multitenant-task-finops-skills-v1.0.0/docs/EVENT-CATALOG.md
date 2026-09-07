# Event Catalog

## 1. Envelope

All domain events use a versioned envelope:

```json
{
  "specversion": "1.0",
  "type": "elmos.task.NodeCheckpointed.v1",
  "source": "elmos://workflow",
  "id": "uuid",
  "time": "RFC3339 timestamp",
  "subject": "tenant/{tenant}/task/{task}/run/{run}",
  "datacontenttype": "application/json",
  "tenant_id": "uuid",
  "account_id": "uuid",
  "project_id": "uuid or null",
  "task_id": "uuid",
  "task_run_id": "uuid",
  "sequence_no": 42,
  "transition_id": "string",
  "trace_id": "string",
  "request_id": "string",
  "data": {}
}
```

Delivery is at-least-once. Consumers deduplicate by event ID/transition ID, persist the decision in `inbox_event_dedup`, and restore per-run order with sequence number.

## 2. Channels

| Channel | Events | Consumers |
|---|---|---|
| `elmos.task.lifecycle.v1` | task state transitions | UI, scheduler, notifications, analytics |
| `elmos.task.node.v1` | node/attempt transitions | progress, analytics, recovery |
| `elmos.task.progress.v1` | heartbeat/progress snapshots | SSE, operations |
| `elmos.task.checkpoint.v1` | checkpoint/recovery | workflow, recovery service, evidence |
| `elmos.task.artifact.v1` | input/output/log manifests | UI, integrity, retention |
| `elmos.task.admission.v1` | slot/quota/scheduling | scheduler, UI, analytics |
| `elmos.finops.usage.v1` | usage/cost events | cost projector, budget, analytics |
| `elmos.billing.revenue.v1` | revenue/allocation | finance projector, analytics |
| `elmos.audit.v1` | privileged audit | security/SIEM |
| `elmos.task.notification.v1` | user notification intents | notification adapter |

## 3. Lifecycle events

| Event | Critical | Core data |
|---|---:|---|
| `TaskCreated` | Yes | request hash, task type, workload, input manifest |
| `TaskQueued` | Yes | reasons, queue entered time |
| `TaskAdmitted` | Yes | slot, generation, resource reservation |
| `TaskStarted` | Yes | workflow ID, run number |
| `TaskPauseRequested` | Yes | actor, reason |
| `TaskPaused` | Yes | checkpoint, slot release |
| `TaskResumeRequested` | Yes | actor, checkpoint |
| `TaskCancelRequested` | Yes | actor, reason |
| `TaskCancelled` | Yes | final checkpoint/partial artifacts |
| `TaskRetryScheduled` | Yes | error class, backoff |
| `TaskUnknownResult` | Yes | expired lease/ambiguity |
| `TaskReconciling` | Yes | reconciliation plan |
| `TaskManualRecoveryRequired` | Yes | ambiguity and options |
| `TaskSucceeded` | Yes | output manifest, final checkpoint |
| `TaskFailed` | Yes | error class, last checkpoint |

## 4. Node/progress events

`NodeHeartbeat` and `NodeProgressed` are batchable. All node terminal and checkpoint events are critical.

For high-frequency events, `data` includes:

```text
node_key
attempt_no
lease_generation
completed_units
total_units
progress
message_code
log_watermark
observed_at
```

Do not put full source, prompt, secret, or verbose log content in the event bus.

## 5. Admission events

```text
SlotClaimed
SlotRenewed
SlotReleased
AdmissionBlocked
TaskPromoted
TenantQuotaChanged
BudgetGateChanged
SchedulerDecisionRecorded
```

`SchedulerDecisionRecorded` stores explainable policy inputs and selected result without sensitive raw data.

## 6. Checkpoint/recovery events

```text
CheckpointCommitted
LeaseExpired
ReconciliationStarted
SideEffectVerified
RecoveryResumed
RecoveryForked
ManualRecoveryApproved
ManualRecoveryRejected
```

## 7. Artifact events

```text
InputArchived
ArtifactProduced
ArtifactVerified
ArtifactIntegrityFailed
LogSegmentStored
RetentionChanged
LegalHoldApplied
TenantExportCreated
ArtifactDeleted
```

Object content is referenced by immutable manifest.

## 8. Usage/cost events

```text
UsageRecorded
UsageCorrected
CostProjected
BudgetWarning
BudgetExceeded
BudgetOverrideApproved
ProviderReconciliationCompleted
```

`UsageRecorded` carries normalized usage and snapshotted price information. It must not be recomputed by a downstream consumer using today's price.

## 9. Revenue events

```text
RevenueEntryRecorded
RevenueAllocated
RevenueAllocationCorrected
RefundRecorded
CollectionRecorded
RevenueRecognized
SettlementReconciled
FinancialProjectionUpdated
```

## 10. Schema evolution

- Additive compatible fields remain in the same major event version.
- Breaking semantic or required-field changes create a new event type/version.
- Producers dual-publish only for a time-bounded migration.
- Consumers declare supported versions.
- Events retain original schema version for replay.
- Workflow payload evolution follows Temporal replay/versioning rules independently.

## 11. Outbox states

```text
PENDING
CLAIMED
DELIVERED
RETRY_WAIT
DEAD_LETTER
```

Outbox records include attempt count, available time, claimed-by/lease, last error, and payload hash. A dead-letter event triggers an alert and operator/replay workflow; it does not roll back already committed business truth.
