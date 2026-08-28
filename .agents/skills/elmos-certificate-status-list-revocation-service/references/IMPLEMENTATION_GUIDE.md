# Implementation Guide — Certificate Status List and Revocation Service

## Purpose

Implement and independently certify certificate status list and revocation service, including publish privacy-preserving active, suspended, withdrawn, expired and superseded status, support offline cache, freshness, stapling and emergency revocation and bind reason, effective time, affected scope and replacement certificate.

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

1. publish privacy-preserving active, suspended, withdrawn, expired and superseded status
2. support offline cache, freshness, stapling and emergency revocation
3. bind reason, effective time, affected scope and replacement certificate
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_CERTIFICATE_STATUS_LIST_REVOCATION_SERVICE-01` — native scenario: publish privacy-preserving active, suspended, withdrawn, expired and superseded status
- `ELMOS_CERTIFICATE_STATUS_LIST_REVOCATION_SERVICE-02` — native scenario: support offline cache, freshness, stapling and emergency revocation
- `ELMOS_CERTIFICATE_STATUS_LIST_REVOCATION_SERVICE-03` — native scenario: bind reason, effective time, affected scope and replacement certificate
- `ELMOS_CERTIFICATE_STATUS_LIST_REVOCATION_SERVICE-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_CERTIFICATE_STATUS_LIST_REVOCATION_SERVICE-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
