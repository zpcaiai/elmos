# Implementation Guide — RAG and Memory Poisoning Verifier

## Purpose

Detect and contain malicious documents, cross-tenant contamination, memory poisoning, citation laundering, stale facts and deletion failures.

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

1. Indirect prompt injection corpus
2. Tenant/ACL namespace isolation
3. Memory write provenance and trust scoring
4. Temporal conflict and stale-fact handling
5. Deletion/tombstone and citation integrity verification

## Native acceptance corpus

- `ELMOS_RAG_MEMORY_POISONING_VERIFIER-01` — malicious document injection
- `ELMOS_RAG_MEMORY_POISONING_VERIFIER-02` — cross-tenant retrieval
- `ELMOS_RAG_MEMORY_POISONING_VERIFIER-03` — tool-output memory poisoning
- `ELMOS_RAG_MEMORY_POISONING_VERIFIER-04` — stale fact precedence
- `ELMOS_RAG_MEMORY_POISONING_VERIFIER-05` — citation laundering
- `ELMOS_RAG_MEMORY_POISONING_VERIFIER-06` — deletion recall zero

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
