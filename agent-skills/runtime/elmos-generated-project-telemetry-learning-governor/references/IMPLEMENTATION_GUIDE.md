# Implementation Guide — Generated Project Telemetry Learning Governor

## Purpose

Use privacy-governed production telemetry to improve templates, routes and tests while preserving tenant boundaries, consent and independent validation.

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

1. define allowed learning signals and purpose
2. aggregate and de-identify across approved scope
3. detect failure and performance patterns
4. propose template/test improvements
5. require holdout and canary before promotion

## Native acceptance corpus

- `ELMOS_GENERATED_PROJECT_TELEMETRY_LEARNING_GOVERNOR-01` — native scenario: define allowed learning signals and purpose
- `ELMOS_GENERATED_PROJECT_TELEMETRY_LEARNING_GOVERNOR-02` — native scenario: aggregate and de-identify across approved scope
- `ELMOS_GENERATED_PROJECT_TELEMETRY_LEARNING_GOVERNOR-03` — native scenario: detect failure and performance patterns
- `ELMOS_GENERATED_PROJECT_TELEMETRY_LEARNING_GOVERNOR-04` — native scenario: propose template/test improvements
- `ELMOS_GENERATED_PROJECT_TELEMETRY_LEARNING_GOVERNOR-05` — native scenario: require holdout and canary before promotion

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
