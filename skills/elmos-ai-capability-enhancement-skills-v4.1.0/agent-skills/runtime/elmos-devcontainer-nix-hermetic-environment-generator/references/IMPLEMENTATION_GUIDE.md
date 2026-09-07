# Implementation Guide — Devcontainer and Nix Hermetic Environment Generator

## Purpose

Generate reproducible local and CI development environments with pinned toolchains, services, policies and offline verification.

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

1. emit devcontainer/Nix environment definitions
2. pin compilers, package managers and system libraries
3. provision local service dependencies
4. support offline cache and integrity checks
5. verify parity with CI and production profiles

## Native acceptance corpus

- `ELMOS_DEVCONTAINER_NIX_HERMETIC_ENVIRONMENT_GENERATOR-01` — native scenario: emit devcontainer/Nix environment definitions
- `ELMOS_DEVCONTAINER_NIX_HERMETIC_ENVIRONMENT_GENERATOR-02` — native scenario: pin compilers, package managers and system libraries
- `ELMOS_DEVCONTAINER_NIX_HERMETIC_ENVIRONMENT_GENERATOR-03` — native scenario: provision local service dependencies
- `ELMOS_DEVCONTAINER_NIX_HERMETIC_ENVIRONMENT_GENERATOR-04` — native scenario: support offline cache and integrity checks
- `ELMOS_DEVCONTAINER_NIX_HERMETIC_ENVIRONMENT_GENERATOR-05` — native scenario: verify parity with CI and production profiles

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
