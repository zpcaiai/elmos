# Implementation Guide — Generated Code Secure-Defaults Verifier

## Purpose

Verify authentication, authorization, validation, cryptography, logging, headers, network and dependency defaults in every generated repository.

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

1. compile framework-specific secure-default profile
2. scan generated configuration and code paths
3. run exploit-oriented negative tests
4. verify production/development profile separation
5. block insecure template or adapter versions

## Native acceptance corpus

- `ELMOS_GENERATED_CODE_SECURE_DEFAULTS_VERIFIER-01` — native scenario: compile framework-specific secure-default profile
- `ELMOS_GENERATED_CODE_SECURE_DEFAULTS_VERIFIER-02` — native scenario: scan generated configuration and code paths
- `ELMOS_GENERATED_CODE_SECURE_DEFAULTS_VERIFIER-03` — native scenario: run exploit-oriented negative tests
- `ELMOS_GENERATED_CODE_SECURE_DEFAULTS_VERIFIER-04` — native scenario: verify production/development profile separation
- `ELMOS_GENERATED_CODE_SECURE_DEFAULTS_VERIFIER-05` — native scenario: block insecure template or adapter versions

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
