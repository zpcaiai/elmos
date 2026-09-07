# Implementation Guide — SQL Semantic Gap Analyzer

## Purpose

Identify dialect differences in NULL/empty string, numeric precision, time, Unicode, collation, coercion, locking, transaction DDL, sequence visibility and procedural behavior.

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

1. Diff source and target DB semantic profiles
2. Classify compile-time, runtime, data and operational gaps
3. Generate dual-execution properties
4. Require data remediation for non-representable values
5. Bind gaps to cutover and rollback conditions

## Native acceptance corpus

- `ELMOS_SQL_SEMANTIC_GAP_ANALYZER-01` — Oracle empty string/NULL
- `ELMOS_SQL_SEMANTIC_GAP_ANALYZER-02` — decimal/overflow
- `ELMOS_SQL_SEMANTIC_GAP_ANALYZER-03` — timezone/date arithmetic
- `ELMOS_SQL_SEMANTIC_GAP_ANALYZER-04` — collation/case/trailing spaces
- `ELMOS_SQL_SEMANTIC_GAP_ANALYZER-05` — locking/isolation
- `ELMOS_SQL_SEMANTIC_GAP_ANALYZER-06` — transactional DDL and sequence

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
