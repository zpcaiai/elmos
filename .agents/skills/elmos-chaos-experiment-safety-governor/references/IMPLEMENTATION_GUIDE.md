# Implementation Guide — Chaos Experiment Safety Governor

## Purpose

Plan and authorize bounded failure injection with blast-radius, abort, observability, side-effect and restoration controls.

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

1. compile experiment hypothesis and steady state
2. calculate scope and dependency blast radius
3. enforce kill switch and time bounds
4. verify monitoring before injection
5. restore state and reconcile effects

## Native acceptance corpus

- `ELMOS_CHAOS_EXPERIMENT_SAFETY_GOVERNOR-01` — native scenario: compile experiment hypothesis and steady state
- `ELMOS_CHAOS_EXPERIMENT_SAFETY_GOVERNOR-02` — native scenario: calculate scope and dependency blast radius
- `ELMOS_CHAOS_EXPERIMENT_SAFETY_GOVERNOR-03` — native scenario: enforce kill switch and time bounds
- `ELMOS_CHAOS_EXPERIMENT_SAFETY_GOVERNOR-04` — native scenario: verify monitoring before injection
- `ELMOS_CHAOS_EXPERIMENT_SAFETY_GOVERNOR-05` — native scenario: restore state and reconcile effects

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
