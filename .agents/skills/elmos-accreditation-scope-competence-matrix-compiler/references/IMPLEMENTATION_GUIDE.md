# Implementation Guide — Accreditation Scope and Competence Matrix Compiler

## Purpose

Implement and independently certify accreditation scope and competence matrix compiler, including compile exact technical fields, methods, products, versions and assurance levels into accreditation scope, map personnel competence, facilities, tools and witness evidence to each scope cell and block certificate issuance outside demonstrated competence.

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

1. compile exact technical fields, methods, products, versions and assurance levels into accreditation scope
2. map personnel competence, facilities, tools and witness evidence to each scope cell
3. block certificate issuance outside demonstrated competence
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_ACCREDITATION_SCOPE_COMPETENCE_MATRIX_COMPILER-01` — native scenario: compile exact technical fields, methods, products, versions and assurance levels into accreditation scope
- `ELMOS_ACCREDITATION_SCOPE_COMPETENCE_MATRIX_COMPILER-02` — native scenario: map personnel competence, facilities, tools and witness evidence to each scope cell
- `ELMOS_ACCREDITATION_SCOPE_COMPETENCE_MATRIX_COMPILER-03` — native scenario: block certificate issuance outside demonstrated competence
- `ELMOS_ACCREDITATION_SCOPE_COMPETENCE_MATRIX_COMPILER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_ACCREDITATION_SCOPE_COMPETENCE_MATRIX_COMPILER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
