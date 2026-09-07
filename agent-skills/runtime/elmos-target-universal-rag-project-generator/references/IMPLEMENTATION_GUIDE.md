# Implementation Guide — TargetUniversalRagProjectGenerator

## Purpose

Generate production RAG repositories spanning ingestion, parsing, ACL-aware indexing, hybrid retrieval, reranking, grounded answering, administration, evaluation and operations.

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

1. Generate ingestion, parsing, embedding and indexing services
2. Generate dense/sparse/graph retrieval and reranking
3. Generate ACL, CDC, tombstone and reindex controls
4. Generate grounded answer and citation services
5. Generate retrieval and answer evaluation suites

## Native acceptance corpus

- `ELMOS_TARGET_UNIVERSAL_RAG_PROJECT_GENERATOR-01` — snapshot plus CDC
- `ELMOS_TARGET_UNIVERSAL_RAG_PROJECT_GENERATOR-02` — hybrid retrieval
- `ELMOS_TARGET_UNIVERSAL_RAG_PROJECT_GENERATOR-03` — ACL filter
- `ELMOS_TARGET_UNIVERSAL_RAG_PROJECT_GENERATOR-04` — rerank and context packing
- `ELMOS_TARGET_UNIVERSAL_RAG_PROJECT_GENERATOR-05` — citation precision
- `ELMOS_TARGET_UNIVERSAL_RAG_PROJECT_GENERATOR-06` — unsupported evidence abstention
- `ELMOS_TARGET_UNIVERSAL_RAG_PROJECT_GENERATOR-07` — delete propagation
- `ELMOS_TARGET_UNIVERSAL_RAG_PROJECT_GENERATOR-08` — restore/reindex
- `ELMOS_TARGET_UNIVERSAL_RAG_PROJECT_GENERATOR-09` — load and latency

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
