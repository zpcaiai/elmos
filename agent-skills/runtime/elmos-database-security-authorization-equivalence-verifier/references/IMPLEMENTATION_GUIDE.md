# Implementation Guide — Database Security and Authorization Equivalence Verifier

## Purpose

Verify roles, grants, row/column security, masking, encryption, auditing and privileged routines remain equivalent or explicitly strengthened across database routes.

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

1. compile roles, grants and ownership into authorization IR
2. compare row and column policy behavior with negative identities
3. verify masking, encryption and audit semantics
4. exercise definer/invoker and privileged routine boundaries
5. certify least-privilege cutover and rollback

## Native acceptance corpus

- `ELMOS_DATABASE_SECURITY_AUTHORIZATION_EQUIVALENCE_VERIFIER-01` — native scenario: compile roles, grants and ownership into authorization IR
- `ELMOS_DATABASE_SECURITY_AUTHORIZATION_EQUIVALENCE_VERIFIER-02` — native scenario: compare row and column policy behavior with negative identities
- `ELMOS_DATABASE_SECURITY_AUTHORIZATION_EQUIVALENCE_VERIFIER-03` — native scenario: verify masking, encryption and audit semantics
- `ELMOS_DATABASE_SECURITY_AUTHORIZATION_EQUIVALENCE_VERIFIER-04` — native scenario: exercise definer/invoker and privileged routine boundaries
- `ELMOS_DATABASE_SECURITY_AUTHORIZATION_EQUIVALENCE_VERIFIER-05` — native scenario: certify least-privilege cutover and rollback

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
