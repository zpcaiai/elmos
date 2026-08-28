# Implementation Guide — Common Criteria Evaluation Assurance Level Planner

## Purpose

Implement and independently certify common criteria evaluation assurance level planner, including choose assurance package based on threat, recognition and procurement needs, compile development, guidance, lifecycle, testing and vulnerability evidence plan and distinguish EAL or composed package from overall product safety certification.

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

1. choose assurance package based on threat, recognition and procurement needs
2. compile development, guidance, lifecycle, testing and vulnerability evidence plan
3. distinguish EAL or composed package from overall product safety certification
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_COMMON_CRITERIA_EVALUATION_ASSURANCE_LEVEL_PLANNER-01` — native scenario: choose assurance package based on threat, recognition and procurement needs
- `ELMOS_COMMON_CRITERIA_EVALUATION_ASSURANCE_LEVEL_PLANNER-02` — native scenario: compile development, guidance, lifecycle, testing and vulnerability evidence plan
- `ELMOS_COMMON_CRITERIA_EVALUATION_ASSURANCE_LEVEL_PLANNER-03` — native scenario: distinguish EAL or composed package from overall product safety certification
- `ELMOS_COMMON_CRITERIA_EVALUATION_ASSURANCE_LEVEL_PLANNER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_COMMON_CRITERIA_EVALUATION_ASSURANCE_LEVEL_PLANNER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
