# Implementation Guide — Golden Route: Managed Agent Runtime

## Purpose

Certify portability from framework-native projects to a selected managed agent cloud with identity, observability, rollback and tested exit strategy.

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

1. Source framework import and AI-SIR recovery
2. Managed target negotiation
3. Identity/network/deployment generation
4. Native load/scale/observability tests
5. Export, rollback and exit drill

## Native acceptance corpus

- `ELMOS_AI_GOLDEN_ROUTE_MANAGED_RUNTIME-01` — native deploy
- `ELMOS_AI_GOLDEN_ROUTE_MANAGED_RUNTIME-02` — workload identity
- `ELMOS_AI_GOLDEN_ROUTE_MANAGED_RUNTIME-03` — private network
- `ELMOS_AI_GOLDEN_ROUTE_MANAGED_RUNTIME-04` — scale/recovery
- `ELMOS_AI_GOLDEN_ROUTE_MANAGED_RUNTIME-05` — data export
- `ELMOS_AI_GOLDEN_ROUTE_MANAGED_RUNTIME-06` — rollback
- `ELMOS_AI_GOLDEN_ROUTE_MANAGED_RUNTIME-07` — exit to alternate runtime

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
