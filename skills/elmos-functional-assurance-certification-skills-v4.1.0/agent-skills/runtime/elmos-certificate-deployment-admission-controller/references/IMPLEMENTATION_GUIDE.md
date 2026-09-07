# Implementation Guide — Certificate-Bound Deployment Admission Controller

## Purpose

Admit deployment only when artifact, environment, policy, evidence freshness and independent certificate exactly match the requested production envelope.

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

1. verify certificate signature, expiry and revocation
2. bind artifact digest, policy bundle and environment profile
3. check E0-E5 and P05 scope for the requested deployment
4. deny stale or partial evidence
5. emit immutable admission and denial receipts

## Native acceptance corpus

- `ELMOS_CERTIFICATE_DEPLOYMENT_ADMISSION_CONTROLLER-01` — native scenario: verify certificate signature, expiry and revocation
- `ELMOS_CERTIFICATE_DEPLOYMENT_ADMISSION_CONTROLLER-02` — native scenario: bind artifact digest, policy bundle and environment profile
- `ELMOS_CERTIFICATE_DEPLOYMENT_ADMISSION_CONTROLLER-03` — native scenario: check E0-E5 and P05 scope for the requested deployment
- `ELMOS_CERTIFICATE_DEPLOYMENT_ADMISSION_CONTROLLER-04` — native scenario: deny stale or partial evidence
- `ELMOS_CERTIFICATE_DEPLOYMENT_ADMISSION_CONTROLLER-05` — native scenario: emit immutable admission and denial receipts

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
