# Implementation Guide — TargetLanggraphProjectGenerator

## Purpose

Generate typed graph applications with state schemas, subgraphs, checkpointers, stores, interrupts, durable execution, streaming, human gates and liveness validation.

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

1. Generate typed StateGraph and subgraphs
2. Configure checkpointer and long-term Store
3. Compile interrupts and human approvals
4. Wrap side effects with idempotency/reconciliation
5. Verify liveness and parallel state reducers

## Native acceptance corpus

- `ELMOS_TARGET_LANGGRAPH_PROJECT_GENERATOR-01` — checkpoint serialization
- `ELMOS_TARGET_LANGGRAPH_PROJECT_GENERATOR-02` — interrupt/resume
- `ELMOS_TARGET_LANGGRAPH_PROJECT_GENERATOR-03` — subgraph namespace isolation
- `ELMOS_TARGET_LANGGRAPH_PROJECT_GENERATOR-04` — parallel state conflict
- `ELMOS_TARGET_LANGGRAPH_PROJECT_GENERATOR-05` — worker crash recovery
- `ELMOS_TARGET_LANGGRAPH_PROJECT_GENERATOR-06` — loop termination
- `ELMOS_TARGET_LANGGRAPH_PROJECT_GENERATOR-07` — side-effect idempotency
- `ELMOS_TARGET_LANGGRAPH_PROJECT_GENERATOR-08` — thread versus long-term store

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
