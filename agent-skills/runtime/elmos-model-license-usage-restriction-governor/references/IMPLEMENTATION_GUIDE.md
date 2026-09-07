# Implementation Guide — Model License and Usage Restriction Governor

## Purpose

Parse and enforce model, dataset, weight, API and output usage restrictions across generation, deployment, redistribution and customer delivery.

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

1. inventory model and data licenses
2. compile commercial, redistribution and field-of-use constraints
3. propagate obligations into deployment profiles
4. block incompatible combination and export
5. produce customer-facing usage evidence

## Native acceptance corpus

- `ELMOS_MODEL_LICENSE_USAGE_RESTRICTION_GOVERNOR-01` — native scenario: inventory model and data licenses
- `ELMOS_MODEL_LICENSE_USAGE_RESTRICTION_GOVERNOR-02` — native scenario: compile commercial, redistribution and field-of-use constraints
- `ELMOS_MODEL_LICENSE_USAGE_RESTRICTION_GOVERNOR-03` — native scenario: propagate obligations into deployment profiles
- `ELMOS_MODEL_LICENSE_USAGE_RESTRICTION_GOVERNOR-04` — native scenario: block incompatible combination and export
- `ELMOS_MODEL_LICENSE_USAGE_RESTRICTION_GOVERNOR-05` — native scenario: produce customer-facing usage evidence

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
