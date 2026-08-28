# Implementation Guide — Railway Software Safety Case Profile

## Purpose

Implement and independently certify railway software safety case profile, including compile RAMS lifecycle, software safety integrity and independent safety assessment evidence, trace hazards, safety requirements, verification and configuration baselines and verify fail-safe behavior, degraded modes and operational rules.

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

1. compile RAMS lifecycle, software safety integrity and independent safety assessment evidence
2. trace hazards, safety requirements, verification and configuration baselines
3. verify fail-safe behavior, degraded modes and operational rules
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_RAILWAY_SOFTWARE_SAFETY_CASE_PROFILE-01` — native scenario: compile RAMS lifecycle, software safety integrity and independent safety assessment evidence
- `ELMOS_RAILWAY_SOFTWARE_SAFETY_CASE_PROFILE-02` — native scenario: trace hazards, safety requirements, verification and configuration baselines
- `ELMOS_RAILWAY_SOFTWARE_SAFETY_CASE_PROFILE-03` — native scenario: verify fail-safe behavior, degraded modes and operational rules
- `ELMOS_RAILWAY_SOFTWARE_SAFETY_CASE_PROFILE-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_RAILWAY_SOFTWARE_SAFETY_CASE_PROFILE-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
