# Implementation Guide — Production Change-Control and Recertification Gate

## Purpose

Map code, model, prompt, data, policy, infrastructure and vendor changes to risk, approvals, evidence invalidation and incremental/full recertification.

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

1. classify change semantic and operational impact
2. compute affected obligations and certificates
3. require separation-of-duty approvals
4. compile incremental validation DAG
5. block deployment until current evidence closes

## Native acceptance corpus

- `ELMOS_PRODUCTION_CHANGE_CONTROL_RECERTIFICATION_GATE-01` — native scenario: classify change semantic and operational impact
- `ELMOS_PRODUCTION_CHANGE_CONTROL_RECERTIFICATION_GATE-02` — native scenario: compute affected obligations and certificates
- `ELMOS_PRODUCTION_CHANGE_CONTROL_RECERTIFICATION_GATE-03` — native scenario: require separation-of-duty approvals
- `ELMOS_PRODUCTION_CHANGE_CONTROL_RECERTIFICATION_GATE-04` — native scenario: compile incremental validation DAG
- `ELMOS_PRODUCTION_CHANGE_CONTROL_RECERTIFICATION_GATE-05` — native scenario: block deployment until current evidence closes

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
