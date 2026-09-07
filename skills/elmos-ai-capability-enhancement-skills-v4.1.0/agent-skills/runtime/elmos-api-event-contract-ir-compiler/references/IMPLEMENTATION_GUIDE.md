# Implementation Guide — API and Event Contract IR Compiler

## Purpose

Compile REST, GraphQL, gRPC, Webhook and event-driven interfaces into a unified contract IR including identity, ordering, effects, errors and compatibility.

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

1. normalize request/response and streaming shapes
2. model error and retry semantics
3. represent authentication and authorization requirements
4. capture side effects and idempotency
5. derive producer/consumer compatibility obligations

## Native acceptance corpus

- `ELMOS_API_EVENT_CONTRACT_IR_COMPILER-01` — native scenario: normalize request/response and streaming shapes
- `ELMOS_API_EVENT_CONTRACT_IR_COMPILER-02` — native scenario: model error and retry semantics
- `ELMOS_API_EVENT_CONTRACT_IR_COMPILER-03` — native scenario: represent authentication and authorization requirements
- `ELMOS_API_EVENT_CONTRACT_IR_COMPILER-04` — native scenario: capture side effects and idempotency
- `ELMOS_API_EVENT_CONTRACT_IR_COMPILER-05` — native scenario: derive producer/consumer compatibility obligations

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
