# Implementation Guide — Test Method Validation and Verification Controller

## Purpose

Implement and independently certify test method validation and verification controller, including validate laboratory-developed methods for intended use and performance characteristics, verify standard methods in the local environment before use and control method changes, deviations, software versions and revalidation.

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

1. validate laboratory-developed methods for intended use and performance characteristics
2. verify standard methods in the local environment before use
3. control method changes, deviations, software versions and revalidation
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_TEST_METHOD_VALIDATION_VERIFICATION_CONTROLLER-01` — native scenario: validate laboratory-developed methods for intended use and performance characteristics
- `ELMOS_TEST_METHOD_VALIDATION_VERIFICATION_CONTROLLER-02` — native scenario: verify standard methods in the local environment before use
- `ELMOS_TEST_METHOD_VALIDATION_VERIFICATION_CONTROLLER-03` — native scenario: control method changes, deviations, software versions and revalidation
- `ELMOS_TEST_METHOD_VALIDATION_VERIFICATION_CONTROLLER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_TEST_METHOD_VALIDATION_VERIFICATION_CONTROLLER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
