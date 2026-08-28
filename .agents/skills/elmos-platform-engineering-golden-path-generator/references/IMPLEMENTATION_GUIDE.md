# Implementation Guide — Platform Engineering Golden Path Generator

## Purpose

Generate self-service application and AI workload golden paths with templates, policies, scorecards, paved-road services and escape hatches.

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

1. compile archetype to approved platform services
2. generate repo, CI, observability and security defaults
3. register ownership and service catalog metadata
4. measure adoption and exception cost
5. version and deprecate golden paths safely

## Native acceptance corpus

- `ELMOS_PLATFORM_ENGINEERING_GOLDEN_PATH_GENERATOR-01` — native scenario: compile archetype to approved platform services
- `ELMOS_PLATFORM_ENGINEERING_GOLDEN_PATH_GENERATOR-02` — native scenario: generate repo, CI, observability and security defaults
- `ELMOS_PLATFORM_ENGINEERING_GOLDEN_PATH_GENERATOR-03` — native scenario: register ownership and service catalog metadata
- `ELMOS_PLATFORM_ENGINEERING_GOLDEN_PATH_GENERATOR-04` — native scenario: measure adoption and exception cost
- `ELMOS_PLATFORM_ENGINEERING_GOLDEN_PATH_GENERATOR-05` — native scenario: version and deprecate golden paths safely

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
