# Implementation Guide — Saga Workflow and Compensation Compiler

## Purpose

Compile long-running distributed business transactions into durable saga state machines with explicit compensation, irreversible steps and human gates.

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

1. derive saga steps and state ownership
2. classify compensable and irreversible effects
3. generate timeout, retry and approval transitions
4. persist idempotency and reconciliation state
5. verify cancellation and partial-failure behavior

## Native acceptance corpus

- `ELMOS_SAGA_WORKFLOW_COMPENSATION_COMPILER-01` — native scenario: derive saga steps and state ownership
- `ELMOS_SAGA_WORKFLOW_COMPENSATION_COMPILER-02` — native scenario: classify compensable and irreversible effects
- `ELMOS_SAGA_WORKFLOW_COMPENSATION_COMPILER-03` — native scenario: generate timeout, retry and approval transitions
- `ELMOS_SAGA_WORKFLOW_COMPENSATION_COMPILER-04` — native scenario: persist idempotency and reconciliation state
- `ELMOS_SAGA_WORKFLOW_COMPENSATION_COMPILER-05` — native scenario: verify cancellation and partial-failure behavior

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
