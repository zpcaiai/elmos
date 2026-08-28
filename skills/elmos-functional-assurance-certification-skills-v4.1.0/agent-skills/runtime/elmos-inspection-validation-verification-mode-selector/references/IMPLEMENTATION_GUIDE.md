# Implementation Guide — Inspection, Validation and Verification Mode Selector

## Purpose

Implement and independently certify inspection, validation and verification mode selector, including distinguish inspection of present state from validation of intended future use and verification of historical claims, select first-, second- or third-party mode with explicit independence class and compile method-specific evidence and sampling obligations.

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

1. distinguish inspection of present state from validation of intended future use and verification of historical claims
2. select first-, second- or third-party mode with explicit independence class
3. compile method-specific evidence and sampling obligations
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_INSPECTION_VALIDATION_VERIFICATION_MODE_SELECTOR-01` — native scenario: distinguish inspection of present state from validation of intended future use and verification of historical claims
- `ELMOS_INSPECTION_VALIDATION_VERIFICATION_MODE_SELECTOR-02` — native scenario: select first-, second- or third-party mode with explicit independence class
- `ELMOS_INSPECTION_VALIDATION_VERIFICATION_MODE_SELECTOR-03` — native scenario: compile method-specific evidence and sampling obligations
- `ELMOS_INSPECTION_VALIDATION_VERIFICATION_MODE_SELECTOR-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_INSPECTION_VALIDATION_VERIFICATION_MODE_SELECTOR-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
