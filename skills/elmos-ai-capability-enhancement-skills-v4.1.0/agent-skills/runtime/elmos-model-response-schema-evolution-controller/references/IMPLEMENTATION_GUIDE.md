# Implementation Guide — Model Response Schema Evolution Controller

## Purpose

Manage backward/forward compatibility of model response and tool argument schemas across model, provider and framework upgrades.

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

1. Schema version graph
2. Producer/consumer compatibility analysis
3. Transitional adapters and dual parsing
4. Canary and rollback plan
5. Old-schema retirement evidence

## Native acceptance corpus

- `ELMOS_MODEL_RESPONSE_SCHEMA_EVOLUTION_CONTROLLER-01` — backward compatible change
- `ELMOS_MODEL_RESPONSE_SCHEMA_EVOLUTION_CONTROLLER-02` — breaking field change
- `ELMOS_MODEL_RESPONSE_SCHEMA_EVOLUTION_CONTROLLER-03` — dual parser
- `ELMOS_MODEL_RESPONSE_SCHEMA_EVOLUTION_CONTROLLER-04` — tool argument migration
- `ELMOS_MODEL_RESPONSE_SCHEMA_EVOLUTION_CONTROLLER-05` — rollback
- `ELMOS_MODEL_RESPONSE_SCHEMA_EVOLUTION_CONTROLLER-06` — retirement gate

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
