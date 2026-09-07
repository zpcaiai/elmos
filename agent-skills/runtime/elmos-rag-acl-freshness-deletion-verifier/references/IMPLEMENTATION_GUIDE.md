# Implementation Guide — RAG ACL, Freshness and Deletion Verifier

## Purpose

Prove that retrieval observes point-in-time authorization, freshness limits, retention and verified deletion across all indexes, caches and memories.

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

1. Document/segment ACL propagation
2. Point-in-time authorization check
3. Freshness watermark and stale-answer policy
4. Deletion across dense/sparse/graph/cache/memory
5. Residual copy and backup accounting

## Native acceptance corpus

- `ELMOS_RAG_ACL_FRESHNESS_DELETION_VERIFIER-01` — authorized retrieval
- `ELMOS_RAG_ACL_FRESHNESS_DELETION_VERIFIER-02` — revoked access immediate denial
- `ELMOS_RAG_ACL_FRESHNESS_DELETION_VERIFIER-03` — freshness watermark
- `ELMOS_RAG_ACL_FRESHNESS_DELETION_VERIFIER-04` — delete from every index
- `ELMOS_RAG_ACL_FRESHNESS_DELETION_VERIFIER-05` — cache purge
- `ELMOS_RAG_ACL_FRESHNESS_DELETION_VERIFIER-06` — backup retention boundary

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
