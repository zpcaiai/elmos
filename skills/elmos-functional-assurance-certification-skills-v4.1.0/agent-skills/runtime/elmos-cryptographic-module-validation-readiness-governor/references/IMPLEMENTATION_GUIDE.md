# Implementation Guide — Cryptographic Module Validation Readiness Governor

## Purpose

Implement and independently certify cryptographic module validation readiness governor, including define cryptographic module boundary, approved services, roles, states, self-tests and operational environments, collect design, entropy, key management and algorithm evidence and separate readiness package from actual accredited module validation.

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

1. define cryptographic module boundary, approved services, roles, states, self-tests and operational environments
2. collect design, entropy, key management and algorithm evidence
3. separate readiness package from actual accredited module validation
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_CRYPTOGRAPHIC_MODULE_VALIDATION_READINESS_GOVERNOR-01` — native scenario: define cryptographic module boundary, approved services, roles, states, self-tests and operational environments
- `ELMOS_CRYPTOGRAPHIC_MODULE_VALIDATION_READINESS_GOVERNOR-02` — native scenario: collect design, entropy, key management and algorithm evidence
- `ELMOS_CRYPTOGRAPHIC_MODULE_VALIDATION_READINESS_GOVERNOR-03` — native scenario: separate readiness package from actual accredited module validation
- `ELMOS_CRYPTOGRAPHIC_MODULE_VALIDATION_READINESS_GOVERNOR-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_CRYPTOGRAPHIC_MODULE_VALIDATION_READINESS_GOVERNOR-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
