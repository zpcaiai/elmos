# Batch 99 — Durable Runtime Kernel Pack

## Purpose

Provides the durable orchestration kernel needed for long-running, resumable and failure-safe execution.

System objective: execute compiled Skills through durable state machines, DAG planning, scheduling, leases, retries, cancellation, compensation, replay, budgets, observability and conservative runtime certification.

## Inventory

- Skills: **16**
- Stable local IDs: **B99-S01–B99-S16**
- Global IDs: intentionally unassigned to avoid collision with the user's existing Batch 81–96 package.

| ID | Skill | Title | Purpose |
|---|---|---|---|
| B99-S01 | `b99-durable-run-state-model` | Durable Run State Model | Define the authoritative run, task, step and effect state machines with legal transitions and terminal semantics. |
| B99-S02 | `b99-plan-to-dag-compiler` | Plan to DAG Compiler | Compile selected executable Skill contracts into a deterministic dependency-aware execution DAG. |
| B99-S03 | `b99-durable-scheduler-queue` | Durable Scheduler and Queue | Schedule runnable DAG nodes with persistence, priorities, fairness, backpressure and tenant isolation. |
| B99-S04 | `b99-task-lease-heartbeat` | Task Lease and Heartbeat | Implement exclusive task claims, heartbeat renewal, expiry and safe reclaim without duplicate effects. |
| B99-S05 | `b99-retry-backoff-policy` | Retry and Backoff Policy | Apply bounded, classified and budget-aware retries without converting deterministic failures into loops. |
| B99-S06 | `b99-idempotency-effect-journal` | Idempotency and Effect Journal | Record external effects and enforce idempotency keys, deduplication and reconciliation. |
| B99-S07 | `b99-cancellation-propagation` | Cancellation Propagation | Propagate user, policy, budget and incident cancellation through workflows, runners and external effects. |
| B99-S08 | `b99-pause-resume-checkpoint` | Pause Resume and Checkpoint | Persist resumable checkpoints and approval pauses without replaying completed side effects. |
| B99-S09 | `b99-saga-compensation-engine` | Saga Compensation Engine | Coordinate compensations for partial cross-system failure while preserving audit and residual-risk truth. |
| B99-S10 | `b99-workflow-versioning-replay` | Workflow Versioning and Replay | Support deterministic workflow code evolution, replay and migration for in-flight runs. |
| B99-S11 | `b99-external-effect-outbox-inbox` | External Effect Outbox and Inbox | Provide durable outbox/inbox patterns for messages, webhooks and provider calls with deduplication. |
| B99-S12 | `b99-execution-budget-quota` | Execution Budget and Quota | Enforce time, token, compute, storage, network and external-operation budgets at run and tenant scope. |
| B99-S13 | `b99-concurrency-fairness-controller` | Concurrency and Fairness Controller | Control global, tenant, repository and resource-key concurrency with anti-starvation behavior. |
| B99-S14 | `b99-failure-classification-diagnostics` | Failure Classification and Diagnostics | Classify model, contract, dependency, build, test, runtime, policy, infrastructure and user failures before repair. |
| B99-S15 | `b99-runtime-observability-tracing` | Runtime Observability and Tracing | Instrument runs, DAG nodes, runner tasks, tool calls, effects and evidence with correlated telemetry. |
| B99-S16 | `b99-durable-runtime-certification-gate` | Durable Runtime Certification Gate | Certify runtime behavior only after recovery, retry, cancellation, replay, budget, fairness and failure-injection evidence passes. |

## Batch completion gate

The Batch is not complete merely because these Markdown files validate. Completion requires implementation in the target ELMOS repository, real integration tests, failure-path evidence, exact scope binding and the final Batch certification Skill result.
