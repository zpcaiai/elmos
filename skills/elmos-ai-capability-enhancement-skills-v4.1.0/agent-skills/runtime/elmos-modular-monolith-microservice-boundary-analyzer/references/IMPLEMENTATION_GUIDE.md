# Implementation Guide — Modular Monolith and Microservice Boundary Analyzer

## Purpose

Evaluate coupling, change cadence, data ownership, latency, transaction and team boundaries before extracting or merging services.

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

1. build static/runtime coupling graph
2. measure co-change and operational dependency
3. map transaction and data ownership
4. simulate extraction/merge impact
5. produce reversible strangler plan

## Native acceptance corpus

- `ELMOS_MODULAR_MONOLITH_MICROSERVICE_BOUNDARY_ANALYZER-01` — native scenario: build static/runtime coupling graph
- `ELMOS_MODULAR_MONOLITH_MICROSERVICE_BOUNDARY_ANALYZER-02` — native scenario: measure co-change and operational dependency
- `ELMOS_MODULAR_MONOLITH_MICROSERVICE_BOUNDARY_ANALYZER-03` — native scenario: map transaction and data ownership
- `ELMOS_MODULAR_MONOLITH_MICROSERVICE_BOUNDARY_ANALYZER-04` — native scenario: simulate extraction/merge impact
- `ELMOS_MODULAR_MONOLITH_MICROSERVICE_BOUNDARY_ANALYZER-05` — native scenario: produce reversible strangler plan

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
