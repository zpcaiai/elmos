# Implementation Guide — Retrieval Index Build and Compaction Governor

## Purpose

Govern full/incremental index builds, segment merge, compaction, replicas, consistency, resource budgets and rollback across retrieval stores.

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

1. plan versioned full and incremental builds
2. coordinate replicas and online cutover
3. verify compaction does not lose ACL/deletes
4. bound CPU, memory, IO and duration
5. retain rollback index until certification

## Native acceptance corpus

- `ELMOS_RETRIEVAL_INDEX_BUILD_COMPACTION_GOVERNOR-01` — native scenario: plan versioned full and incremental builds
- `ELMOS_RETRIEVAL_INDEX_BUILD_COMPACTION_GOVERNOR-02` — native scenario: coordinate replicas and online cutover
- `ELMOS_RETRIEVAL_INDEX_BUILD_COMPACTION_GOVERNOR-03` — native scenario: verify compaction does not lose ACL/deletes
- `ELMOS_RETRIEVAL_INDEX_BUILD_COMPACTION_GOVERNOR-04` — native scenario: bound CPU, memory, IO and duration
- `ELMOS_RETRIEVAL_INDEX_BUILD_COMPACTION_GOVERNOR-05` — native scenario: retain rollback index until certification

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
