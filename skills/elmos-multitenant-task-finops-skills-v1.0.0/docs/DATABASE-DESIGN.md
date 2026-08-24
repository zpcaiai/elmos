# Database Design

## 1. Principles

1. PostgreSQL is the authoritative source for task state, admission slots, checkpoints, artifact metadata, usage, revenue, and audit.
2. The database stores structured metadata and references; large payloads and log content reside in object storage.
3. A task request is immutable. Mutable current state is separated from append-only history.
4. Usage and revenue are append-only ledgers. Corrections are new signed entries.
5. Every tenant business table is protected by forced RLS.
6. Global account concurrency is modeled with three explicit slot rows, not a count query.
7. High-volume event and ledger tables use time-oriented indexes, retention/archival, and optional partitioning after measured need.
8. Analytics projections are rebuildable and never replace transactional ledgers.

## 2. Core entity groups

### Identity and policy

| Table | Purpose |
|---|---|
| `tenant_runtime_quota` | Tenant active, queued, resource-unit, provider, and budget limits |
| `account_task_slot` | Exactly three global root-task execution slots per account |
| `audit_event` | Immutable security, control, finance, and retention audit |

The identity provider/account/membership tables may already exist. This package references their UUIDs rather than defining a competing identity truth.

### Task lifecycle

| Table | Purpose |
|---|---|
| `task` | Immutable request identity and current task projection |
| `task_run` | One workflow run/history with workflow ID and aggregate timing |
| `task_node` | Planned/current node state |
| `task_node_attempt` | Attempts, worker/runner lease, errors, timing |
| `task_event` | Append-only sequenced task/run/node journal |
| `task_progress_snapshot` | Rebuildable current progress/ETA |
| `task_checkpoint` | Durable recovery point |
| `task_side_effect_receipt` | Idempotent external side-effect evidence |
| `outbox_event` | Transactional publication intent |
| `inbox_event_dedup` | Consumer-side event ID deduplication for at-least-once delivery |

### I/O and artifacts

| Table | Purpose |
|---|---|
| `task_input` | Input parameters and object references |
| `task_artifact` | Versioned output/artifact metadata |
| `task_log_segment` | Object-store log segment references |

### Usage, revenue, and analytics

| Table | Purpose |
|---|---|
| `price_book_item` | Effective-dated provider/internal prices |
| `usage_event` | Immutable billable resource usage |
| `task_cost_summary` | Rebuildable/maintained cost projection |
| `revenue_entry` | Immutable signed charge/credit/refund/recognition/collection entry |
| `revenue_allocation` | Allocation of source revenue entry to task/project |
| `task_financial_summary` | Task-level financial projection |
| `tenant_financial_daily` | Rebuildable daily operational/commercial aggregate |

## 3. Task versus task run

`task` represents the user's immutable intent. `task_run` represents execution.

Examples:

- A retry after a non-recoverable run creates `run_no=2`.
- A compatible pause/resume may continue the same run.
- A checkpoint incompatible with current revision/tool/model policy creates a forked run and references `parent_run_id` and `fork_checkpoint_id`.
- Historical outputs and finance remain attached to the producing run.

## 4. Account slot design

### Why explicit slots

A distributed count-then-start implementation is unsafe:

```text
API replica A counts 2 active tasks
API replica B counts 2 active tasks
both start
result = 4 active tasks
```

Instead, each account owns rows:

```text
(account_id, slot_no=1)
(account_id, slot_no=2)
(account_id, slot_no=3)
```

A transaction atomically locks and leases one row. No fourth row exists.

### Slot fields

- `account_id`
- `slot_no` in `1..3`
- `task_id`
- `tenant_id` of occupied task
- `lease_generation`
- `claimed_at`
- `lease_expires_at`
- `updated_at`

The active workflow renews the slot lease. A completion/release request must supply the current generation. This fences stale workers and duplicate callbacks.

### Global versus tenant scope

The slot primary key is account-wide, so an account running two tasks in tenant A can run only one additional task in tenant B. Tenant quotas are evaluated separately and may further reduce admission.

## 5. State projection and journal

`task.state` and `task_run.state` provide efficient current queries. `task_event` provides history.

Every critical transition contains:

- `event_id`;
- `transition_id` unique for idempotency;
- `task_id`, `task_run_id`, optional node/attempt;
- monotonic `sequence_no`;
- old/new state where applicable;
- actor/source;
- payload;
- `occurred_at`;
- `trace_id`, `request_id`.

The event append function locks `task_run`, allocates the next sequence, and inserts the event. Duplicate `transition_id` returns the original sequence without creating another event. Broker consumers insert `(consumer_name, event_id)` into `inbox_event_dedup` before applying side effects; a primary-key conflict means the event was already processed.

## 6. Checkpoint data

A checkpoint stores:

```json
{
  "checkpoint_id": "...",
  "task_run_id": "...",
  "node_key": "verify",
  "input_manifest_sha256": "...",
  "repository_revision": "...",
  "state_sha256": "...",
  "completed_side_effect_receipts": ["..."],
  "cache_keys": ["..."],
  "tool_versions": {},
  "model_versions": {},
  "policy_version": "...",
  "schema_version": "1",
  "next_node_key": "package",
  "compatibility": {}
}
```

Large checkpoint state is an encrypted object; the row stores URI, hash, size, media type, and key reference.

## 7. Usage ledger

### Canonical fields

- tenant/account/project/task/run/node dimensions;
- event source and idempotency/provider receipt key;
- provider and SKU;
- usage type and unit;
- signed quantity;
- price-book item/version;
- unit price and currency;
- FX rate and base currency;
- calculated cost;
- estimate/final/correction flag;
- occurred/ingested timestamps;
- trace and provider request IDs.

### Cost formula examples

Model:

```text
(input_tokens / 1,000,000 × input_price)
+ (cached_input_tokens / 1,000,000 × cached_input_price)
+ (output_tokens / 1,000,000 × output_price)
```

Compute:

```text
vCPU_seconds × vCPU_second_price
+ GB_seconds × GB_second_price
+ GPU_seconds × GPU_second_price
```

Storage:

```text
byte_hours × byte_hour_price
+ egress_bytes × egress_byte_price
```

Amounts use high-precision numeric fields and explicit currency precision/rounding policy.

## 8. Revenue ledger

`revenue_entry.kind` includes:

- `QUOTE`
- `CHARGE`
- `CREDIT`
- `REFUND`
- `RECOGNITION`
- `COLLECTION`
- `PAYMENT_FEE`
- `TAX`
- `ADJUSTMENT`

Amounts are signed. A refund is not an update to the original charge. Entries may reference a billing order, invoice, payment-provider object, or source revenue entry.

`revenue_allocation` maps a source entry to one or more tasks/projects using:

- `DIRECT`
- `MILESTONE`
- `USAGE_WEIGHTED`
- `MANUAL_APPROVED`

The allocation policy and version are stored. Allocated amounts must sum to the source allocatable amount within currency precision.

## 9. Financial projections

`task_financial_summary` contains:

- estimated cost;
- reserved cost;
- posted actual cost;
- final actual cost;
- net billed revenue;
- recognized revenue;
- collected cash;
- payment fees;
- taxes;
- gross profit;
- gross margin;
- currency/basis;
- `as_of`;
- reconciliation status.

It is a projection. Source ledger entries remain the evidence.

## 10. Indexing

Minimum indexes:

```text
task(account_id, state, created_at)
task(tenant_id, state, created_at)
task(tenant_id, project_id, created_at)
task_run(task_id, run_no)
task_run(workflow_id)
task_node(task_run_id, state, node_key)
task_node_attempt(task_run_id, node_key, attempt_no)
task_event(task_run_id, sequence_no)
task_event(task_id, occurred_at)
task_checkpoint(task_run_id, created_at desc)
outbox_event(status, available_at, created_at)
usage_event(tenant_id, occurred_at)
usage_event(task_id, occurred_at)
usage_event(provider, provider_receipt_id)
revenue_entry(tenant_id, occurred_at)
revenue_allocation(task_id, occurred_at)
audit_event(tenant_id, occurred_at)
```

Use partial indexes for active states and undelivered outbox rows.

## 11. Volume and retention

- Keep current task/run/node/summary rows in primary hot storage.
- Retain task events and usage/revenue ledgers according to contractual and financial policy.
- Move verbose log content immediately to object storage.
- Archive old event payloads to object storage or partitioned cold tables while retaining hashes and summary indexes.
- Use monthly partitions when measured event volume or maintenance windows justify them; do not prematurely partition every table.
- Replicate ledgers to an analytical store only when query load threatens transactional SLOs.

## 12. RLS and roles

Suggested roles:

| Role | Purpose |
|---|---|
| `elmos_migration_owner` | Owns schema; never used by runtime |
| `elmos_control_app` | Tenant/account-scoped API operations |
| `elmos_workflow_app` | Task/run scoped workflow activities |
| `elmos_outbox_publisher` | Claims and marks outbox events |
| `elmos_analytics_app` | Reads tenant-authorized projections/ledgers |
| `elmos_finance_admin` | Explicit finance operations with audit |
| `elmos_break_glass` | Time-limited emergency access, separately monitored |

No runtime role is superuser, table owner, or `BYPASSRLS`.

## 13. Migration strategy

1. Add new enum/domain contracts and tables without changing current behavior.
2. Backfill tenant/account/run identifiers and three slot rows.
3. Dual-write current task progress into the new journal behind a feature flag.
4. Verify projection parity.
5. Enable new admission in shadow mode and compare decisions.
6. Enable hard admission for selected tenants.
7. Enable usage/cost ledger and reconcile against provider records.
8. Enable revenue allocations and dashboards.
9. Remove old duplicate state/cost truths after migration evidence and rollback window.
