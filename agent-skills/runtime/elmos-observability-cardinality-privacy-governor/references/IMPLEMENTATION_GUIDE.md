# Implementation Guide — Observability Cardinality and Privacy Governor

## Purpose

Govern trace/metric/log schemas, sampling, cardinality, redaction, retention and tenant access for AI and polyglot systems.

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

1. compile versioned telemetry profile
2. classify high-cardinality and sensitive attributes
3. configure head/tail sampling and exemplars
4. enforce tenant access and retention
5. measure telemetry cost and blind spots

## Native acceptance corpus

- `ELMOS_OBSERVABILITY_CARDINALITY_PRIVACY_GOVERNOR-01` — native scenario: compile versioned telemetry profile
- `ELMOS_OBSERVABILITY_CARDINALITY_PRIVACY_GOVERNOR-02` — native scenario: classify high-cardinality and sensitive attributes
- `ELMOS_OBSERVABILITY_CARDINALITY_PRIVACY_GOVERNOR-03` — native scenario: configure head/tail sampling and exemplars
- `ELMOS_OBSERVABILITY_CARDINALITY_PRIVACY_GOVERNOR-04` — native scenario: enforce tenant access and retention
- `ELMOS_OBSERVABILITY_CARDINALITY_PRIVACY_GOVERNOR-05` — native scenario: measure telemetry cost and blind spots

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
