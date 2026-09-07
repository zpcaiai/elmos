# Implementation Guide — AI Cache Semantic Consistency Verifier

## Purpose

Verify prompt, model, tool, retrieval, build and transformation caches against semantic keys, tenant isolation, freshness and evidence invalidation.

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

1. Semantic cache key construction
2. Tenant/policy/model/tool/version partitioning
3. Freshness and negative-cache TTL
4. Drift/evidence invalidation propagation
5. Poisoning and collision detection

## Native acceptance corpus

- `ELMOS_AI_CACHE_SEMANTIC_CONSISTENCY_VERIFIER-01` — valid hit
- `ELMOS_AI_CACHE_SEMANTIC_CONSISTENCY_VERIFIER-02` — semantic miss
- `ELMOS_AI_CACHE_SEMANTIC_CONSISTENCY_VERIFIER-03` — cross-tenant isolation
- `ELMOS_AI_CACHE_SEMANTIC_CONSISTENCY_VERIFIER-04` — model drift invalidation
- `ELMOS_AI_CACHE_SEMANTIC_CONSISTENCY_VERIFIER-05` — tool policy change invalidation
- `ELMOS_AI_CACHE_SEMANTIC_CONSISTENCY_VERIFIER-06` — poisoned entry quarantine

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
