# Implementation Guide — Cross-Language and Database Differential Runner

## Purpose

Run joint source/target application and source/target database scenarios to detect interaction defects that isolated code or SQL tests miss.

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

1. Orchestrate four-way source/target application/database runs
2. Normalize protocol and database observations
3. Compare transaction and tool side effects end to end
4. Attribute mismatch to code, ORM, SQL or engine
5. Persist replayable counterexamples

## Native acceptance corpus

- `ELMOS_CROSS_LANGUAGE_DATABASE_DIFFERENTIAL_RUNNER-01` — source-app/source-db baseline
- `ELMOS_CROSS_LANGUAGE_DATABASE_DIFFERENTIAL_RUNNER-02` — target-app/target-db candidate
- `ELMOS_CROSS_LANGUAGE_DATABASE_DIFFERENTIAL_RUNNER-03` — crossed compatibility combinations
- `ELMOS_CROSS_LANGUAGE_DATABASE_DIFFERENTIAL_RUNNER-04` — transaction rollback interaction
- `ELMOS_CROSS_LANGUAGE_DATABASE_DIFFERENTIAL_RUNNER-05` — concurrent request/data race
- `ELMOS_CROSS_LANGUAGE_DATABASE_DIFFERENTIAL_RUNNER-06` — CDC and application cutover

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
