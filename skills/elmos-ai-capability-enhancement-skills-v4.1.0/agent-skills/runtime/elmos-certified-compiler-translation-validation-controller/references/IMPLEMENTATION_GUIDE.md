# Implementation Guide — Certified Compiler and Translation Validation Controller

## Purpose

Implement and independently certify certified compiler and translation validation controller, including prefer certified compiler or independently validate every concrete translation, compare source and target semantics at IR, binary and runtime boundaries and preserve proof lineage through optimization and code generation.

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

1. prefer certified compiler or independently validate every concrete translation
2. compare source and target semantics at IR, binary and runtime boundaries
3. preserve proof lineage through optimization and code generation
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_CERTIFIED_COMPILER_TRANSLATION_VALIDATION_CONTROLLER-01` — native scenario: prefer certified compiler or independently validate every concrete translation
- `ELMOS_CERTIFIED_COMPILER_TRANSLATION_VALIDATION_CONTROLLER-02` — native scenario: compare source and target semantics at IR, binary and runtime boundaries
- `ELMOS_CERTIFIED_COMPILER_TRANSLATION_VALIDATION_CONTROLLER-03` — native scenario: preserve proof lineage through optimization and code generation
- `ELMOS_CERTIFIED_COMPILER_TRANSLATION_VALIDATION_CONTROLLER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_CERTIFIED_COMPILER_TRANSLATION_VALIDATION_CONTROLLER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
