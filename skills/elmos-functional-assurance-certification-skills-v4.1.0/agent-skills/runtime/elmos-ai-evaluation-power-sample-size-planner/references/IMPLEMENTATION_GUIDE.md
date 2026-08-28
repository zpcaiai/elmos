# Implementation Guide — AI Evaluation Power and Sample-Size Planner

## Purpose

Implement and independently certify ai evaluation power and sample-size planner, including plan sample size for minimum relevant effect, variance, confidence and subgroup coverage, account for clustered, repeated and adaptive measurements and report underpowered claims as bounded or indeterminate.

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

1. plan sample size for minimum relevant effect, variance, confidence and subgroup coverage
2. account for clustered, repeated and adaptive measurements
3. report underpowered claims as bounded or indeterminate
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_AI_EVALUATION_POWER_SAMPLE_SIZE_PLANNER-01` — native scenario: plan sample size for minimum relevant effect, variance, confidence and subgroup coverage
- `ELMOS_AI_EVALUATION_POWER_SAMPLE_SIZE_PLANNER-02` — native scenario: account for clustered, repeated and adaptive measurements
- `ELMOS_AI_EVALUATION_POWER_SAMPLE_SIZE_PLANNER-03` — native scenario: report underpowered claims as bounded or indeterminate
- `ELMOS_AI_EVALUATION_POWER_SAMPLE_SIZE_PLANNER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_AI_EVALUATION_POWER_SAMPLE_SIZE_PLANNER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
