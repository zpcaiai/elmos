# Implementation Guide — Security Evaluation Methodology Work-Unit Compiler

## Purpose

Implement and independently certify security evaluation methodology work-unit compiler, including compile evaluator actions, inputs, verdict criteria and evidence for each assurance work unit, ensure evaluation depth and rigor are reproducible across evaluators and record sampling, dependencies, deviations and reviewer approval.

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

1. compile evaluator actions, inputs, verdict criteria and evidence for each assurance work unit
2. ensure evaluation depth and rigor are reproducible across evaluators
3. record sampling, dependencies, deviations and reviewer approval
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_SECURITY_EVALUATION_METHODOLOGY_WORK_UNIT_COMPILER-01` — native scenario: compile evaluator actions, inputs, verdict criteria and evidence for each assurance work unit
- `ELMOS_SECURITY_EVALUATION_METHODOLOGY_WORK_UNIT_COMPILER-02` — native scenario: ensure evaluation depth and rigor are reproducible across evaluators
- `ELMOS_SECURITY_EVALUATION_METHODOLOGY_WORK_UNIT_COMPILER-03` — native scenario: record sampling, dependencies, deviations and reviewer approval
- `ELMOS_SECURITY_EVALUATION_METHODOLOGY_WORK_UNIT_COMPILER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_SECURITY_EVALUATION_METHODOLOGY_WORK_UNIT_COMPILER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
