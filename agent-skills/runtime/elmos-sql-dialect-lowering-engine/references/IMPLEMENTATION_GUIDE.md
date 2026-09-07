# Implementation Guide — SQL Dialect Lowering Engine

## Purpose

Lower DB-SIR into target DDL, DML and routines through deterministic rules, vendor profiles and bounded synthesis with reversible lineage.

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

1. Apply typed dialect rules before text rewriting
2. Preserve object and query lineage
3. Generate compatibility functions only with explicit ownership
4. Bound generative routine translation
5. Refuse critical unsupported features

## Native acceptance corpus

- `ELMOS_SQL_DIALECT_LOWERING_ENGINE-01` — DDL lowering
- `ELMOS_SQL_DIALECT_LOWERING_ENGINE-02` — query lowering
- `ELMOS_SQL_DIALECT_LOWERING_ENGINE-03` — routine lowering
- `ELMOS_SQL_DIALECT_LOWERING_ENGINE-04` — trigger lowering
- `ELMOS_SQL_DIALECT_LOWERING_ENGINE-05` — compatibility shim
- `ELMOS_SQL_DIALECT_LOWERING_ENGINE-06` — round-trip formatting/source map

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
