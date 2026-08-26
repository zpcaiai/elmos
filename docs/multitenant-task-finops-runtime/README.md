# Multi-tenant task and FinOps repository runtime

This directory documents the repository-owned implementation that reconciles
the imported `elmos-multitenant-task-finops-skills@1.0.0` contract with ELMOS's
existing identity, task, artifact, usage, billing, and runner aggregates.

## Status boundary

| Item | Current state | Meaning |
| --- | --- | --- |
| `V77`, `V77.1`, and `V77.2` migrations | repository-owned implementation artifacts | They extend existing ELMOS aggregates. Their presence does not prove that a database migration or workload was executed. |
| Current V77 qualification | `NOT_RUN` | The historical 56/56 local V73 receipt predates the current code and does not qualify V77, V77.1, V77.2, or their new Java/test bindings. |
| Packaged `V100`-`V102` SQL | `NOT_APPLIED` | The packaged SQL remains immutable reference material and was not copied or executed. |
| Repository implementation mapping | 63 `IMPLEMENTED`; 69 `PARTIAL`; 12 `NOT_STARTED` | These are content-bound implementation states, not execution results. |
| Repository task results | 144 `NOT_RUN`; 144 evidence `NONE` | No source-catalog task has an exact result receipt. |
| Exact dependency Skills | 4 `UNRESOLVED` | Local code with related behavior does not resolve an exact declared dependency. |
| External evidence | `NOT_RUN` | No Temporal, object/payment provider, invoice, settlement, independent-verifier, or production evidence is bound. |
| Production certification | `NOT_CERTIFIED` | Local implementation and tests cannot certify the product. |

The authoritative status records are
[`repository-task-results.json`](../multitenant-task-finops-skills/repository-task-results.json),
[`repository-dependency-bindings.json`](../multitenant-task-finops-skills/repository-dependency-bindings.json),
and
[`repository-reconciliation-register.json`](../multitenant-task-finops-skills/repository-reconciliation-register.json).
The source risk findings remain open and direct source adoption remains blocked.

## Repository-owned surfaces

- [`V77__account_task_control_and_finops_runtime.sql`](../../modules/persistence/src/main/resources/db/migration/V77__account_task_control_and_finops_runtime.sql)
  defines transaction-bound identity checks, FORCE RLS, the exact three-slot
  semaphore, durable task state, checkpoints, receipts, usage and revenue
  records, and account-safe projections.
- [`V77_1__task_finops_recovery_lifecycle_and_settlement.sql`](../../modules/persistence/src/main/resources/db/migration/V77_1__task_finops_recovery_lifecycle_and_settlement.sql)
  adds ordered feature rollout, incompatible-checkpoint fork records, tenant
  export/deletion lifecycle state, and fail-closed settlement reconciliation.
- [`V77_2__task_finops_analytics_rebuild_and_exports.sql`](../../modules/persistence/src/main/resources/db/migration/V77_2__task_finops_analytics_rebuild_and_exports.sql)
  adds continuity-gated, generation-bound analytics rebuild publication and
  tenant-isolated current projections.
- [`TaskFinopsPolicy.java`](../../modules/workflow/src/main/java/io/elmos/workflow/TaskFinopsPolicy.java)
  and the recovery, lifecycle, rollout, settlement, and analytics policy
  classes contain pure deterministic decisions without provider effects.
- [`TaskFinopsPort.java`](../../modules/workflow/src/main/java/io/elmos/workflow/TaskFinopsPort.java)
  and [`TaskFinopsOperationsPort.java`](../../modules/workflow/src/main/java/io/elmos/workflow/TaskFinopsOperationsPort.java)
  are the typed workflow/persistence boundaries.
- [`JdbcTaskFinopsStore.java`](../../modules/persistence/src/main/java/io/elmos/persistence/JdbcTaskFinopsStore.java)
  and [`JdbcTaskFinopsOperationsStore.java`](../../modules/persistence/src/main/java/io/elmos/persistence/JdbcTaskFinopsOperationsStore.java)
  bind those ports to repository-owned SQL functions and projections.
- [`TaskFinopsController.java`](../../apps/control-plane/src/main/java/io/elmos/controlplane/TaskFinopsController.java)
  and [`TaskFinopsOperationsController.java`](../../apps/control-plane/src/main/java/io/elmos/controlplane/TaskFinopsOperationsController.java)
  expose authenticated, account-bound control surfaces. They do not perform
  Temporal, object-store deletion, payment-provider settlement, deployment, or
  certification effects.

See [the implementation contract](IMPLEMENTATION_CONTRACT.md),
[metric catalog](METRIC_CATALOG.md), and
[local qualification boundary](LOCAL_QUALIFICATION.md).
