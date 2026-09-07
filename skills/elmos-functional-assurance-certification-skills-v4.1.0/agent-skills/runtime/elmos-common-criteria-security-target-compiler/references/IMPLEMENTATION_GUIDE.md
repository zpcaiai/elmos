# Implementation Guide — Common Criteria Security Target Compiler

## Purpose

Implement and independently certify common criteria security target compiler, including define target of evaluation, boundary, environment, assets, threats, objectives and security requirements, map Elmos controls and evidence to functional and assurance components and maintain rationale, dependencies and exact evaluated configuration.

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

1. define target of evaluation, boundary, environment, assets, threats, objectives and security requirements
2. map Elmos controls and evidence to functional and assurance components
3. maintain rationale, dependencies and exact evaluated configuration
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_COMMON_CRITERIA_SECURITY_TARGET_COMPILER-01` — native scenario: define target of evaluation, boundary, environment, assets, threats, objectives and security requirements
- `ELMOS_COMMON_CRITERIA_SECURITY_TARGET_COMPILER-02` — native scenario: map Elmos controls and evidence to functional and assurance components
- `ELMOS_COMMON_CRITERIA_SECURITY_TARGET_COMPILER-03` — native scenario: maintain rationale, dependencies and exact evaluated configuration
- `ELMOS_COMMON_CRITERIA_SECURITY_TARGET_COMPILER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_COMMON_CRITERIA_SECURITY_TARGET_COMPILER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
