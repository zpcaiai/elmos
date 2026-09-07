# Product Requirements — Multi-Tenant Task Control & FinOps

## 1. Objective

Build an Elmos subsystem that safely executes long-running, multi-node tasks for many tenants while:

1. enforcing a hard account-wide limit of three simultaneously active root tasks;
2. preserving progress and execution history asynchronously without losing recovery-critical state;
3. recovering from client disconnects, service restarts, worker loss, retries, and ambiguous side effects;
4. archiving each task's inputs, outputs, execution context, node history, and evidence;
5. calculating task-level and historical cost, revenue, profit, and margin;
6. providing tenant-isolated operational and commercial analytics.

## 2. Terms

| Term | Definition |
|---|---|
| Tenant | A customer organization or isolated Elmos workspace. |
| Account | An authenticated human or service principal. One account may belong to multiple tenants. |
| Root task | A user-visible task submission such as project generation, conversion, modernization, analysis, or test campaign. |
| Node | A DAG/workflow step inside a root task. Nodes do not consume account root-task slots. |
| Task run | One executable workflow history for a task. Retry/fork creates a new run; resume may continue a compatible run. |
| Active slot | One of the three account-wide root-task execution permits. |
| Usage event | Immutable metering record for model, compute, storage, network, runner, or third-party consumption. |
| Revenue entry | Immutable signed event for charge, credit, refund, recognition, collection, fee, tax, or adjustment. |
| Posted | Persisted and included in the ledger through an `as_of` timestamp. |
| Recognized revenue | Revenue included for profitability under the selected recognition policy. |
| Collected cash | Payment actually settled or received; distinct from recognized revenue. |

## 3. Functional requirements

### Identity and tenant isolation

- `FR-ID-001`: Validate OIDC/JWT and resolve account and tenant membership server-side.
- `FR-ID-002`: Never trust a client-provided tenant header as authorization evidence.
- `FR-ID-003`: Apply PostgreSQL `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` to every tenant business table.
- `FR-ID-004`: Use non-superuser, non-owner runtime roles without `BYPASSRLS`.
- `FR-ID-005`: Audit actor, tenant, account, task, run, request, trace, action, reason, and outcome for privileged operations.

### Submission and concurrency

- `FR-CC-001`: Accept a client-supplied `Idempotency-Key` for task submission.
- `FR-CC-002`: Persist the immutable task request before scheduling.
- `FR-CC-003`: Enforce a hard maximum of three slot-consuming root tasks per account across all tenant memberships.
- `FR-CC-004`: Store a fourth or later valid task as `WAITING_FOR_SLOT`.
- `FR-CC-005`: Atomically claim and release account slots in PostgreSQL.
- `FR-CC-006`: Apply tenant active-task, queued-task, resource-unit, budget, and provider quotas in addition to the account limit.
- `FR-CC-007`: Expose `active_slots`, `maximum_slots=3`, `queued_count`, queue position, and admission reason.
- `FR-CC-008`: Prevent stale workers or duplicate requests from releasing a newer slot lease.

### Workflow lifecycle

- `FR-WF-001`: Represent task, run, node, attempt, lease, and recovery states explicitly.
- `FR-WF-002`: Bind a deterministic Temporal workflow ID to the task run before or atomically with start.
- `FR-WF-003`: Support pause, resume, cancel, retry, and fork-from-checkpoint.
- `FR-WF-004`: Propagate cancellation to running activities and private-runner work.
- `FR-WF-005`: Persist all terminal states in PostgreSQL.
- `FR-WF-006`: Classify errors as retryable, non-retryable, budget, policy, environment, user input, provider, or unknown-result.
- `FR-WF-007`: Use workflow versioning and Continue-As-New for long histories.

### Progress and node journal

- `FR-PR-001`: Append task and node events with monotonic per-run sequence numbers.
- `FR-PR-002`: Make each transition/event idempotent.
- `FR-PR-003`: Maintain a compact current progress snapshot.
- `FR-PR-004`: Calculate monotonic weighted progress and machine ETA P50/P90.
- `FR-PR-005`: Stream progress through SSE or WebSocket with replay from `after_sequence`.
- `FR-PR-006`: Batch high-frequency heartbeats, logs, and non-critical progress deltas.
- `FR-PR-007`: Rebuild progress snapshots from the append-only event journal.

### Checkpoint and recovery

- `FR-RC-001`: Commit a checkpoint at every safe stage boundary.
- `FR-RC-002`: Include input manifest digest, revision, state digest, completed side effects, cache keys, model/tool versions, policy version, and next node.
- `FR-RC-003`: Record side-effect intents and immutable receipts.
- `FR-RC-004`: Require attempt number and lease generation for renew, complete, fail, cancel, and release.
- `FR-RC-005`: Mark expired running work `UNKNOWN_RESULT`, then reconcile before retry.
- `FR-RC-006`: Resume only from a compatible checkpoint.
- `FR-RC-007`: Fork a new run when compatibility fails; preserve old evidence.
- `FR-RC-008`: Provide audited manual recovery for irreducible ambiguity.

### Input, output, and execution archive

- `FR-IO-001`: Archive the user request, parameters, multimodal file manifests, repository snapshot, and project constraints.
- `FR-IO-002`: Store large binary/text payloads and logs in S3-compatible object storage.
- `FR-IO-003`: Store object URI, SHA-256, size, media type, encryption key reference, retention class, and version in PostgreSQL.
- `FR-IO-004`: Archive generated results, code, reports, diagrams, tests, logs, and evidence as immutable artifact versions.
- `FR-IO-005`: Archive execution environment, tool/model versions, prompt/policy version, dependency locks, and cache lineage.
- `FR-IO-006`: Support retention, legal hold, tenant export, and deletion.
- `FR-IO-007`: Never archive reusable secrets or long-lived repository credentials.

### Usage and cost

- `FR-CO-001`: Meter model input, cached input, output, embedding, image, audio, and provider-specific units separately.
- `FR-CO-002`: Meter CPU, memory, GPU, runner/sandbox, storage byte-hours, egress, rendering, tests, and third-party APIs.
- `FR-CO-003`: Use an append-only usage ledger with an idempotency key.
- `FR-CO-004`: Snapshot provider, SKU, unit price, currency, FX rate, and price-book version on each usage event.
- `FR-CO-005`: Track estimated, reserved, posted, and final actual cost.
- `FR-CO-006`: Enforce task and tenant cost budgets and record overrides.
- `FR-CO-007`: Calculate historical total cost by tenant, account, project, task, model, provider, workload, and time.
- `FR-CO-008`: Reconcile provider invoices through explicit correction events.

### Revenue and margin

- `FR-RV-001`: Support prepaid credits, pay-as-you-go, subscription included/overage, fixed project, dedicated tenant, private deployment, and offline license billing.
- `FR-RV-002`: Distinguish quote, charge, credit, refund, recognition, collection, tax, payment fee, and adjustment.
- `FR-RV-003`: Store append-only signed revenue entries.
- `FR-RV-004`: Allocate direct and shared revenue to tasks through a versioned policy.
- `FR-RV-005`: Calculate billed revenue, recognized revenue, collected cash, net revenue, gross profit, and gross margin.
- `FR-RV-006`: Calculate historical total revenue and profitability by business dimensions.
- `FR-RV-007`: Reconcile payment-provider settlements and refunds.
- `FR-RV-008`: Keep system cost, human review cost, and human-equivalent effort separate.

### Analytics and operations

- `FR-AN-001`: Provide task throughput, queue, active concurrency, duration, success, retry, recovery, pause, and cancellation metrics.
- `FR-AN-002`: Provide token, compute, storage, provider, cost, revenue, profit, and margin metrics.
- `FR-AN-003`: Drill from platform/tenant/account/project to task/run/node/event/ledger.
- `FR-AN-004`: Show scope, basis, currency, and `as_of` on every financial total.
- `FR-AN-005`: Detect duplicate, missing, stale, unreconciled, or negative-margin data.
- `FR-AN-006`: Provide tenant-isolated exports.
- `FR-AN-007`: Rebuild all analytical projections from transactional ledgers.

## 4. State and slot semantics

Slot-consuming states:

```text
ADMITTED
STARTING
RUNNING
PAUSE_REQUESTED
PAUSING
CANCEL_REQUESTED
CANCELLING
RECONCILING (only while an active execution lease is retained)
```

Non-slot-consuming states:

```text
CREATED
WAITING_FOR_SLOT
PAUSED
RETRY_WAIT
UNKNOWN_RESULT after active lease expiry
MANUAL_RECOVERY
SUCCEEDED
FAILED
CANCELLED
```

A product may show non-terminal paused/recovery tasks as "open", but the hard requirement applies to simultaneous execution slots.

## 5. User experience

### Task list

For every task show:

- name, type, tenant/project, submission time;
- state and current node;
- overall progress and node progress;
- elapsed autonomous runtime;
- queue time and machine ETA P50/P90;
- retry/recovery count;
- estimated, posted, and final cost;
- attributable recognized revenue and margin where the viewer is authorized;
- result, artifact, log, and recovery links.

### Account concurrency widget

```text
Active tasks: 2 / 3
Waiting for slot: 4
Tenant capacity: throttled / available
Next estimated start: ...
```

### Financial dashboard

- posted system cost through `as_of`;
- recognized revenue and collected cash separately;
- gross profit and margin;
- cost and revenue by task type, model, provider, tenant, project, and period;
- estimated-versus-actual variance;
- negative-margin and budget alerts.

## 6. Non-functional requirements

- `NFR-001`: No account oversubscription under multi-replica concurrent requests.
- `NFR-002`: Zero cross-tenant data leakage in tested paths.
- `NFR-003`: Critical event and ledger acknowledgement only after durable persistence.
- `NFR-004`: Progress UI lag target P95 ≤ 2 seconds under normal load.
- `NFR-005`: Task creation API target P95 ≤ 500 ms excluding upload transfer and external identity latency.
- `NFR-006`: Progress-event write overhead target ≤ 5% of task wall-clock for representative workloads.
- `NFR-007`: Recovery point is the latest committed safe checkpoint.
- `NFR-008`: Recovery does not repeat a completed external side effect.
- `NFR-009`: Cost/revenue replay is idempotent.
- `NFR-010`: Analytics projections are deletable and rebuildable.
- `NFR-011`: All schemas, events, APIs, and state changes are versioned.
- `NFR-012`: Large payloads do not live in hot transactional rows.
- `NFR-013`: Backups, restore, and point-in-time recovery cover task and financial ledgers.
- `NFR-014`: Retention, export, and deletion are tenant-auditable.
- `NFR-015`: Autonomous system runtime is reported separately from human effort and human waiting time.

## 7. Out of scope for this package

- A specific payment-provider implementation.
- A specific Kafka/NATS/Redpanda deployment; the event-bus interface is replaceable.
- A specific analytics database. PostgreSQL rollups are the default; a warehouse/ClickHouse projection may be added when volume justifies it.
- Actual Elmos repository code changes or deployed test evidence.
- General ledger, tax filing, or statutory accounting certification.

## 8. Completion definition

The subsystem is complete only when repository-specific evidence proves:

1. hard account limit under contention;
2. tenant isolation with real RLS and non-superuser roles;
3. durable progress, checkpoint, and recovery;
4. cancellation and pause propagation;
5. input/output integrity and retention;
6. idempotent usage and revenue ledgers;
7. reconciled totals and drill-through;
8. measured performance, load, chaos, backup/restore, and production gates.
