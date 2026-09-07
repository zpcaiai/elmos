# Implementation Guide — API-First Contract Generation Controller

## Purpose

Generate OpenAPI, AsyncAPI, GraphQL and gRPC contracts, mock/simulator assets, server/client stubs and compatibility gates before implementation.

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

1. compile observable behavior into interface contracts
2. generate examples, errors and security schemes
3. produce server/client stubs with ownership regions
4. register compatibility and review gates
5. keep implementation and contract synchronized

## Native acceptance corpus

- `ELMOS_API_FIRST_CONTRACT_GENERATION_CONTROLLER-01` — native scenario: compile observable behavior into interface contracts
- `ELMOS_API_FIRST_CONTRACT_GENERATION_CONTROLLER-02` — native scenario: generate examples, errors and security schemes
- `ELMOS_API_FIRST_CONTRACT_GENERATION_CONTROLLER-03` — native scenario: produce server/client stubs with ownership regions
- `ELMOS_API_FIRST_CONTRACT_GENERATION_CONTROLLER-04` — native scenario: register compatibility and review gates
- `ELMOS_API_FIRST_CONTRACT_GENERATION_CONTROLLER-05` — native scenario: keep implementation and contract synchronized

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
