# Implementation Guide — Protocol State-Machine Model Checker

## Purpose

Compile workflow, MCP/A2A/ACP and service protocols into executable state models and verify reachability, safety, liveness, cancellation and recovery.

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

1. translate typed protocol states and guards
2. check invalid transitions and unreachable states
3. verify bounded liveness and cancellation
4. model retries, timeouts and crash recovery
5. map counterexamples to executable scenarios

## Native acceptance corpus

- `ELMOS_PROTOCOL_STATE_MACHINE_MODEL_CHECKER-01` — native scenario: translate typed protocol states and guards
- `ELMOS_PROTOCOL_STATE_MACHINE_MODEL_CHECKER-02` — native scenario: check invalid transitions and unreachable states
- `ELMOS_PROTOCOL_STATE_MACHINE_MODEL_CHECKER-03` — native scenario: verify bounded liveness and cancellation
- `ELMOS_PROTOCOL_STATE_MACHINE_MODEL_CHECKER-04` — native scenario: model retries, timeouts and crash recovery
- `ELMOS_PROTOCOL_STATE_MACHINE_MODEL_CHECKER-05` — native scenario: map counterexamples to executable scenarios

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
