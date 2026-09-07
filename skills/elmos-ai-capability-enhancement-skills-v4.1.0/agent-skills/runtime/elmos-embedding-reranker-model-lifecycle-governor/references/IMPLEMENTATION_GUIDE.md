# Implementation Guide — Embedding and Reranker Model Lifecycle Governor

## Purpose

Govern embedding/reranker selection, versioning, dimensionality, index compatibility, re-embedding, evaluation and rollback.

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

1. register exact embedding and reranker profiles
2. validate dimension, metric and tokenizer compatibility
3. plan incremental re-embedding and dual indexes
4. benchmark retrieval and grounding impact
5. coordinate rollback and cache invalidation

## Native acceptance corpus

- `ELMOS_EMBEDDING_RERANKER_MODEL_LIFECYCLE_GOVERNOR-01` — native scenario: register exact embedding and reranker profiles
- `ELMOS_EMBEDDING_RERANKER_MODEL_LIFECYCLE_GOVERNOR-02` — native scenario: validate dimension, metric and tokenizer compatibility
- `ELMOS_EMBEDDING_RERANKER_MODEL_LIFECYCLE_GOVERNOR-03` — native scenario: plan incremental re-embedding and dual indexes
- `ELMOS_EMBEDDING_RERANKER_MODEL_LIFECYCLE_GOVERNOR-04` — native scenario: benchmark retrieval and grounding impact
- `ELMOS_EMBEDDING_RERANKER_MODEL_LIFECYCLE_GOVERNOR-05` — native scenario: coordinate rollback and cache invalidation

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
