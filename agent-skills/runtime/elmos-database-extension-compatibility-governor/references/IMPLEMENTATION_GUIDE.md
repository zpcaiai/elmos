# Implementation Guide — Database Extension Compatibility Governor

## Purpose

Inventory and govern database extensions, plugins, collations, procedural languages and managed-service restrictions during dialect selection and migration.

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

1. fingerprint installed extension versions
2. map extension semantics to target alternatives
3. detect managed-service restrictions
4. generate replacement or external-service adapters
5. bind licensing and security evidence

## Native acceptance corpus

- `ELMOS_DATABASE_EXTENSION_COMPATIBILITY_GOVERNOR-01` — native scenario: fingerprint installed extension versions
- `ELMOS_DATABASE_EXTENSION_COMPATIBILITY_GOVERNOR-02` — native scenario: map extension semantics to target alternatives
- `ELMOS_DATABASE_EXTENSION_COMPATIBILITY_GOVERNOR-03` — native scenario: detect managed-service restrictions
- `ELMOS_DATABASE_EXTENSION_COMPATIBILITY_GOVERNOR-04` — native scenario: generate replacement or external-service adapters
- `ELMOS_DATABASE_EXTENSION_COMPATIBILITY_GOVERNOR-05` — native scenario: bind licensing and security evidence

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
