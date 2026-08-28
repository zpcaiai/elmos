# Implementation Guide — Generated API and Event Schema Evolution Controller

## Purpose

Govern versioning and compatibility for generated REST, GraphQL, gRPC, event and tool contracts across regeneration, migration and rolling deployment.

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

1. classify breaking and non-breaking changes
2. generate compatibility adapters and deprecation windows
3. verify mixed-version rolling deployments
4. bind consumer impact to repository graph
5. coordinate rollback and schema registry state

## Native acceptance corpus

- `ELMOS_GENERATED_API_EVENT_SCHEMA_EVOLUTION_CONTROLLER-01` — native scenario: classify breaking and non-breaking changes
- `ELMOS_GENERATED_API_EVENT_SCHEMA_EVOLUTION_CONTROLLER-02` — native scenario: generate compatibility adapters and deprecation windows
- `ELMOS_GENERATED_API_EVENT_SCHEMA_EVOLUTION_CONTROLLER-03` — native scenario: verify mixed-version rolling deployments
- `ELMOS_GENERATED_API_EVENT_SCHEMA_EVOLUTION_CONTROLLER-04` — native scenario: bind consumer impact to repository graph
- `ELMOS_GENERATED_API_EVENT_SCHEMA_EVOLUTION_CONTROLLER-05` — native scenario: coordinate rollback and schema registry state

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
