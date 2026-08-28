# Implementation Guide — AI Test Laboratory Competence Governor

## Purpose

Implement and independently certify ai test laboratory competence governor, including establish laboratory management system, impartiality, personnel, facilities and method controls, authorize staff and automated evaluators by exact method and scope and monitor validity of results, equipment, software and environmental conditions.

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

1. establish laboratory management system, impartiality, personnel, facilities and method controls
2. authorize staff and automated evaluators by exact method and scope
3. monitor validity of results, equipment, software and environmental conditions
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_AI_TEST_LABORATORY_COMPETENCE_GOVERNOR-01` — native scenario: establish laboratory management system, impartiality, personnel, facilities and method controls
- `ELMOS_AI_TEST_LABORATORY_COMPETENCE_GOVERNOR-02` — native scenario: authorize staff and automated evaluators by exact method and scope
- `ELMOS_AI_TEST_LABORATORY_COMPETENCE_GOVERNOR-03` — native scenario: monitor validity of results, equipment, software and environmental conditions
- `ELMOS_AI_TEST_LABORATORY_COMPETENCE_GOVERNOR-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_AI_TEST_LABORATORY_COMPETENCE_GOVERNOR-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
