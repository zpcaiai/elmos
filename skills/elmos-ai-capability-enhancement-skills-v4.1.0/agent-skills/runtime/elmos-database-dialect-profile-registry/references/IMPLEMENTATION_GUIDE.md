# Implementation Guide — Database Dialect Profile Registry

## Purpose

Govern exact database engine, version, compatibility mode, charset, collation, driver, extension and operational semantic profiles.

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

1. Fingerprint real engines and compatibility modes
2. Model DDL/DML/routine/transaction capabilities
3. Track charset, collation, extensions and driver
4. Classify support and certified envelopes
5. Invalidate evidence on parameter or engine drift

## Native acceptance corpus

- `ELMOS_DATABASE_DIALECT_PROFILE_REGISTRY-01` — PostgreSQL profile
- `ELMOS_DATABASE_DIALECT_PROFILE_REGISTRY-02` — Oracle profile
- `ELMOS_DATABASE_DIALECT_PROFILE_REGISTRY-03` — SQL Server profile
- `ELMOS_DATABASE_DIALECT_PROFILE_REGISTRY-04` — MySQL/MariaDB profile
- `ELMOS_DATABASE_DIALECT_PROFILE_REGISTRY-05` — DB2 profile
- `ELMOS_DATABASE_DIALECT_PROFILE_REGISTRY-06` — warehouse profile
- `ELMOS_DATABASE_DIALECT_PROFILE_REGISTRY-07` — compatibility mode mismatch

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
