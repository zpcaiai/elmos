# Implementation Guide — AIDurableRuntimeIntegrator

## Purpose

Integrate generated projects with durable workflow, checkpoints, replay, pause/resume/cancel, leases, fencing, outbox and side-effect reconciliation.

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

1. Negotiate exact target profile
2. Emit complete native project and extension artifacts
3. Run native import/build/start/load tests
4. Generate deployment, operations and evidence hooks
5. Preserve unsupported features in a ledger

## Native acceptance corpus

- `ELMOS_AI_DURABLE_RUNTIME_INTEGRATOR-01` — worker crash
- `ELMOS_AI_DURABLE_RUNTIME_INTEGRATOR-02` — duplicate delivery
- `ELMOS_AI_DURABLE_RUNTIME_INTEGRATOR-03` — pause resume cancel
- `ELMOS_AI_DURABLE_RUNTIME_INTEGRATOR-04` — AiDurableRuntimeIntegrator representative end-to-end fixture
- `ELMOS_AI_DURABLE_RUNTIME_INTEGRATOR-05` — crash recovery preserves single-writer semantics
- `ELMOS_AI_DURABLE_RUNTIME_INTEGRATOR-06` — upstream or contract drift invalidates stale evidence
- `ELMOS_AI_DURABLE_RUNTIME_INTEGRATOR-07` — undeclared authority is denied
- `ELMOS_AI_DURABLE_RUNTIME_INTEGRATOR-08` — resource and wall-clock budget is measured
- `ELMOS_AI_DURABLE_RUNTIME_INTEGRATOR-09` — minimal native project
- `ELMOS_AI_DURABLE_RUNTIME_INTEGRATOR-10` — representative production fixture

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
