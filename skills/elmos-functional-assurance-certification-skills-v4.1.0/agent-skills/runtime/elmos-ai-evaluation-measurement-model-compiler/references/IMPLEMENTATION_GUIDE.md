# Implementation Guide — AI Evaluation Measurement Model Compiler

## Purpose

Implement and independently certify ai evaluation measurement model compiler, including construct mathematical or simulation measurement models linking inputs to AI evaluation results, identify correlated uncertainty components and model inadequacy and validate model residuals, sensitivity and domain of applicability.

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

1. construct mathematical or simulation measurement models linking inputs to AI evaluation results
2. identify correlated uncertainty components and model inadequacy
3. validate model residuals, sensitivity and domain of applicability
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_AI_EVALUATION_MEASUREMENT_MODEL_COMPILER-01` — native scenario: construct mathematical or simulation measurement models linking inputs to AI evaluation results
- `ELMOS_AI_EVALUATION_MEASUREMENT_MODEL_COMPILER-02` — native scenario: identify correlated uncertainty components and model inadequacy
- `ELMOS_AI_EVALUATION_MEASUREMENT_MODEL_COMPILER-03` — native scenario: validate model residuals, sensitivity and domain of applicability
- `ELMOS_AI_EVALUATION_MEASUREMENT_MODEL_COMPILER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_AI_EVALUATION_MEASUREMENT_MODEL_COMPILER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
