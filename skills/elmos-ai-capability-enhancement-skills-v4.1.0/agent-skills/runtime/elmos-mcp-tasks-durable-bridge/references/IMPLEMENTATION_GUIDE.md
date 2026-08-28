# Implementation Guide — MCP Tasks Durable Bridge

## Purpose

Bridge MCP Tasks to Elmos durable runs with monotonic state, checkpointing, pause/resume/cancel, lease fencing, mid-flight input and side-effect reconciliation.

## Required vertical slice

A conforming first implementation must execute one real, exact-version vertical slice through:

1. API command and idempotency validation;
2. PostgreSQL run/event/outbox persistence with tenant policy;
3. K7 authority, sandbox, lease and fencing acquisition;
4. the Skill-specific native operation;
5. at least one positive and one negative native fixture;
6. independent proof/evidence production;
7. K8 blocked-or-certified decision;
8. pause/resume and worker-loss recovery;
9. machine wall-clock and cost reporting;
10. safe uninstall/rollback or compensating action.

## Skill-specific work packages

1. Task handle to Run/Step binding
2. Monotonic transition validator
3. Idempotent polling and updates
4. Checkpoint/recovery after client or worker loss
5. Cancellation and side-effect settlement

## Native acceptance corpus

- `ELMOS_MCP_TASKS_DURABLE_BRIDGE-01` — task create/poll/complete
- `ELMOS_MCP_TASKS_DURABLE_BRIDGE-02` — duplicate update idempotency
- `ELMOS_MCP_TASKS_DURABLE_BRIDGE-03` — worker crash recovery
- `ELMOS_MCP_TASKS_DURABLE_BRIDGE-04` — client disconnect resume
- `ELMOS_MCP_TASKS_DURABLE_BRIDGE-05` — stale fencing rejection
- `ELMOS_MCP_TASKS_DURABLE_BRIDGE-06` — cancel with unsettled side effect

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
