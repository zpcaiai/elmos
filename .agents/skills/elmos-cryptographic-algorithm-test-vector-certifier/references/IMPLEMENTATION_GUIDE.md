# Implementation Guide — Cryptographic Algorithm Test-Vector Certifier

## Purpose

Implement and independently certify cryptographic algorithm test-vector certifier, including execute known-answer, Monte Carlo, negative and edge test vectors against exact implementation, bind algorithm, parameter set, implementation and platform digests and export ACVP-compatible evidence where authorized.

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

1. execute known-answer, Monte Carlo, negative and edge test vectors against exact implementation
2. bind algorithm, parameter set, implementation and platform digests
3. export ACVP-compatible evidence where authorized
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_CRYPTOGRAPHIC_ALGORITHM_TEST_VECTOR_CERTIFIER-01` — native scenario: execute known-answer, Monte Carlo, negative and edge test vectors against exact implementation
- `ELMOS_CRYPTOGRAPHIC_ALGORITHM_TEST_VECTOR_CERTIFIER-02` — native scenario: bind algorithm, parameter set, implementation and platform digests
- `ELMOS_CRYPTOGRAPHIC_ALGORITHM_TEST_VECTOR_CERTIFIER-03` — native scenario: export ACVP-compatible evidence where authorized
- `ELMOS_CRYPTOGRAPHIC_ALGORITHM_TEST_VECTOR_CERTIFIER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_CRYPTOGRAPHIC_ALGORITHM_TEST_VECTOR_CERTIFIER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
