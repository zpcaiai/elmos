# Multi-tenant task and FinOps repository runtime

This directory documents the repository-owned implementation that reconciles
the imported `elmos-multitenant-task-finops-skills@1.0.0` contract with ELMOS's
existing identity, task, artifact, usage, billing, and runner aggregates.

## Status boundary

| Item | Current state | Meaning |
| --- | --- | --- |
| `V73__account_task_control_and_finops_runtime.sql` | repository-owned implementation artifact | It extends existing ELMOS aggregates. Its presence does not prove that a database migration or workload was executed. |
| Packaged `V100`-`V102` SQL | `NOT_APPLIED` | The packaged SQL remains immutable reference material and was not copied or executed. |
| Repository task results | 144 `NOT_RUN`; 144 evidence `NONE` | No source-catalog task has an exact result receipt. |
| Exact dependency Skills | 4 `UNRESOLVED` | Local code with related behavior does not resolve an exact declared dependency. |
| External evidence | `NOT_RUN` | No Temporal, provider, invoice, settlement, independent-verifier, or production evidence is bound. |
| Production certification | `NOT_CERTIFIED` | Local implementation and tests cannot certify the product. |

The authoritative status records are
[`repository-task-results.json`](../multitenant-task-finops-skills/repository-task-results.json),
[`repository-dependency-bindings.json`](../multitenant-task-finops-skills/repository-dependency-bindings.json),
and
[`repository-reconciliation-register.json`](../multitenant-task-finops-skills/repository-reconciliation-register.json).
The source risk findings remain open and direct source adoption remains blocked.

## Repository-owned surfaces

- [`V73__account_task_control_and_finops_runtime.sql`](../../modules/persistence/src/main/resources/db/migration/V73__account_task_control_and_finops_runtime.sql)
  defines account-bound identity checks, FORCE RLS, the exact three-slot
  semaphore, durable task state, checkpoints, receipts, usage and revenue
  records, and account-safe projections.
- [`TaskFinopsPolicy.java`](../../modules/workflow/src/main/java/io/elmos/workflow/TaskFinopsPolicy.java)
  contains pure state, progress, recovery, scheduling, and decimal-money
  invariants without database, provider, clock, or workflow SDK effects.
- [`TaskFinopsPort.java`](../../modules/workflow/src/main/java/io/elmos/workflow/TaskFinopsPort.java)
  is the typed workflow/persistence boundary.
- [`JdbcTaskFinopsStore.java`](../../modules/persistence/src/main/java/io/elmos/persistence/JdbcTaskFinopsStore.java)
  binds the port to the repository-owned SQL functions and projections.
- [`TaskFinopsController.java`](../../apps/control-plane/src/main/java/io/elmos/controlplane/TaskFinopsController.java)
  exposes tenant-bound reads plus idempotent pause and resume controls; it does
  not expose public usage, revenue, correction, allocation, or reconciliation
  mutation endpoints.

See [the implementation contract](IMPLEMENTATION_CONTRACT.md),
[metric catalog](METRIC_CATALOG.md), and
[local qualification boundary](LOCAL_QUALIFICATION.md).
