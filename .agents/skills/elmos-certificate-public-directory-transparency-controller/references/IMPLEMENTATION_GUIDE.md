# Implementation Guide — Certificate Public Directory and Transparency Controller

## Purpose

Implement and independently certify certificate public directory and transparency controller, including publish searchable certificate metadata, scope, status, limitations and verification instructions, protect confidential evidence while enabling public reliance and append issuance, update, suspension and revocation to transparency log.

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

1. publish searchable certificate metadata, scope, status, limitations and verification instructions
2. protect confidential evidence while enabling public reliance
3. append issuance, update, suspension and revocation to transparency log
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_CERTIFICATE_PUBLIC_DIRECTORY_TRANSPARENCY_CONTROLLER-01` — native scenario: publish searchable certificate metadata, scope, status, limitations and verification instructions
- `ELMOS_CERTIFICATE_PUBLIC_DIRECTORY_TRANSPARENCY_CONTROLLER-02` — native scenario: protect confidential evidence while enabling public reliance
- `ELMOS_CERTIFICATE_PUBLIC_DIRECTORY_TRANSPARENCY_CONTROLLER-03` — native scenario: append issuance, update, suspension and revocation to transparency log
- `ELMOS_CERTIFICATE_PUBLIC_DIRECTORY_TRANSPARENCY_CONTROLLER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_CERTIFICATE_PUBLIC_DIRECTORY_TRANSPARENCY_CONTROLLER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
