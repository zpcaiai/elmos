# Implementation Guide — AI Retention and Erasure Verifier

## Purpose

Enforce and verify retention, legal hold, export and deletion across prompts, traces, datasets, vector indexes, memories, caches, artifacts and backups.

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

1. Data-class-specific retention rules
2. Legal hold precedence
3. Distributed deletion orchestration
4. Provider deletion verification
5. Backup expiry and residual-copy proof

## Native acceptance corpus

- `ELMOS_AI_RETENTION_ERASURE_VERIFIER-01` — normal expiry
- `ELMOS_AI_RETENTION_ERASURE_VERIFIER-02` — user erasure request
- `ELMOS_AI_RETENTION_ERASURE_VERIFIER-03` — legal hold block
- `ELMOS_AI_RETENTION_ERASURE_VERIFIER-04` — provider deletion
- `ELMOS_AI_RETENTION_ERASURE_VERIFIER-05` — cache/vector/memory purge
- `ELMOS_AI_RETENTION_ERASURE_VERIFIER-06` — backup expiry

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
