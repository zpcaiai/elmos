# Implementation Guide — Certification Scheme Surveillance Planner

## Purpose

Implement and independently certify certification scheme surveillance planner, including design periodic, event-driven, remote and on-site surveillance mix, select surveillance samples from change, incident, usage and risk signals and reassess continuing conformity without repeating irrelevant work.

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

1. design periodic, event-driven, remote and on-site surveillance mix
2. select surveillance samples from change, incident, usage and risk signals
3. reassess continuing conformity without repeating irrelevant work
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_CERTIFICATION_SCHEME_SURVEILLANCE_PLANNER-01` — native scenario: design periodic, event-driven, remote and on-site surveillance mix
- `ELMOS_CERTIFICATION_SCHEME_SURVEILLANCE_PLANNER-02` — native scenario: select surveillance samples from change, incident, usage and risk signals
- `ELMOS_CERTIFICATION_SCHEME_SURVEILLANCE_PLANNER-03` — native scenario: reassess continuing conformity without repeating irrelevant work
- `ELMOS_CERTIFICATION_SCHEME_SURVEILLANCE_PLANNER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_CERTIFICATION_SCHEME_SURVEILLANCE_PLANNER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
