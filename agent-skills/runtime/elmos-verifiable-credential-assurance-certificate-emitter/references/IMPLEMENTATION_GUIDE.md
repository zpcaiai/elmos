# Implementation Guide — Verifiable Credential Assurance Certificate Emitter

## Purpose

Implement and independently certify verifiable credential assurance certificate emitter, including emit standards-compatible verifiable certificate credentials with selective disclosure where appropriate, bind holder, subject, issuer, evidence and status mechanisms and verify presentation nonce, audience, purpose and anti-replay.

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

1. emit standards-compatible verifiable certificate credentials with selective disclosure where appropriate
2. bind holder, subject, issuer, evidence and status mechanisms
3. verify presentation nonce, audience, purpose and anti-replay
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_VERIFIABLE_CREDENTIAL_ASSURANCE_CERTIFICATE_EMITTER-01` — native scenario: emit standards-compatible verifiable certificate credentials with selective disclosure where appropriate
- `ELMOS_VERIFIABLE_CREDENTIAL_ASSURANCE_CERTIFICATE_EMITTER-02` — native scenario: bind holder, subject, issuer, evidence and status mechanisms
- `ELMOS_VERIFIABLE_CREDENTIAL_ASSURANCE_CERTIFICATE_EMITTER-03` — native scenario: verify presentation nonce, audience, purpose and anti-replay
- `ELMOS_VERIFIABLE_CREDENTIAL_ASSURANCE_CERTIFICATE_EMITTER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_VERIFIABLE_CREDENTIAL_ASSURANCE_CERTIFICATE_EMITTER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
