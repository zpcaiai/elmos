# Implementation Guide — Certificate Portability and Transfer Controller

## Purpose

Implement and independently certify certificate portability and transfer controller, including package evidence, audit trail, status and scope for transfer without issuer lock-in, verify receiving body competence and acceptance of prior work and preserve original issuer responsibility and transfer decision lineage.

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

1. package evidence, audit trail, status and scope for transfer without issuer lock-in
2. verify receiving body competence and acceptance of prior work
3. preserve original issuer responsibility and transfer decision lineage
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_CERTIFICATE_PORTABILITY_TRANSFER_CONTROLLER-01` — native scenario: package evidence, audit trail, status and scope for transfer without issuer lock-in
- `ELMOS_CERTIFICATE_PORTABILITY_TRANSFER_CONTROLLER-02` — native scenario: verify receiving body competence and acceptance of prior work
- `ELMOS_CERTIFICATE_PORTABILITY_TRANSFER_CONTROLLER-03` — native scenario: preserve original issuer responsibility and transfer decision lineage
- `ELMOS_CERTIFICATE_PORTABILITY_TRANSFER_CONTROLLER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_CERTIFICATE_PORTABILITY_TRANSFER_CONTROLLER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
