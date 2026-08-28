# Implementation Guide — Schema Registry Compatibility Controller

## Purpose

Govern Avro, Protobuf, JSON Schema and event schema registration, subject naming, compatibility modes, migration and rollback.

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

1. fingerprint registry and subject policies
2. evaluate backward/forward/full compatibility
3. coordinate producer and consumer rollout
4. generate transcoders and upcasters
5. prevent incompatible deletion or mode changes

## Native acceptance corpus

- `ELMOS_SCHEMA_REGISTRY_COMPATIBILITY_CONTROLLER-01` — native scenario: fingerprint registry and subject policies
- `ELMOS_SCHEMA_REGISTRY_COMPATIBILITY_CONTROLLER-02` — native scenario: evaluate backward/forward/full compatibility
- `ELMOS_SCHEMA_REGISTRY_COMPATIBILITY_CONTROLLER-03` — native scenario: coordinate producer and consumer rollout
- `ELMOS_SCHEMA_REGISTRY_COMPATIBILITY_CONTROLLER-04` — native scenario: generate transcoders and upcasters
- `ELMOS_SCHEMA_REGISTRY_COMPATIBILITY_CONTROLLER-05` — native scenario: prevent incompatible deletion or mode changes

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
