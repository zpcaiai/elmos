# Implementation Guide — Multiple-Comparison and Sequential Test Controller

## Purpose

Implement and independently certify multiple-comparison and sequential test controller, including control family-wise error or false discovery across many metrics and subgroups, support alpha spending, sequential monitoring and predeclared stopping and distinguish exploratory findings from confirmatory certification evidence.

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

1. control family-wise error or false discovery across many metrics and subgroups
2. support alpha spending, sequential monitoring and predeclared stopping
3. distinguish exploratory findings from confirmatory certification evidence
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_AI_MULTIPLE_COMPARISON_SEQUENTIAL_TEST_CONTROLLER-01` — native scenario: control family-wise error or false discovery across many metrics and subgroups
- `ELMOS_AI_MULTIPLE_COMPARISON_SEQUENTIAL_TEST_CONTROLLER-02` — native scenario: support alpha spending, sequential monitoring and predeclared stopping
- `ELMOS_AI_MULTIPLE_COMPARISON_SEQUENTIAL_TEST_CONTROLLER-03` — native scenario: distinguish exploratory findings from confirmatory certification evidence
- `ELMOS_AI_MULTIPLE_COMPARISON_SEQUENTIAL_TEST_CONTROLLER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_AI_MULTIPLE_COMPARISON_SEQUENTIAL_TEST_CONTROLLER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
