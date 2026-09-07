# Implementation Guide — AI Secret and Credential Lifecycle Controller

## Purpose

Broker short-lived model, tool, database and cloud credentials with least privilege, rotation, revocation, leak detection and incident integration.

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

1. Secret broker integration
2. Request-scoped credential issuance
3. Rotation and revocation lifecycle
4. Output/log/trace leak prevention
5. Incident-driven mass revocation

## Native acceptance corpus

- `ELMOS_AI_SECRET_CREDENTIAL_LIFECYCLE_CONTROLLER-01` — short-lived issuance
- `ELMOS_AI_SECRET_CREDENTIAL_LIFECYCLE_CONTROLLER-02` — scope restriction
- `ELMOS_AI_SECRET_CREDENTIAL_LIFECYCLE_CONTROLLER-03` — rotation
- `ELMOS_AI_SECRET_CREDENTIAL_LIFECYCLE_CONTROLLER-04` — revocation
- `ELMOS_AI_SECRET_CREDENTIAL_LIFECYCLE_CONTROLLER-05` — log redaction
- `ELMOS_AI_SECRET_CREDENTIAL_LIFECYCLE_CONTROLLER-06` — incident mass revoke

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
