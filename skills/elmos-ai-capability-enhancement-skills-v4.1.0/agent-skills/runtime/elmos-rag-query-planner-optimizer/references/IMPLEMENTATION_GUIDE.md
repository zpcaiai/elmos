# Implementation Guide — RAG Query Planner and Optimizer

## Purpose

Compile evidence-aware retrieval plans across rewrite, decomposition, hybrid search, filters, rerank, graph traversal, context packing and abstention budgets.

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

1. Typed query intent and decomposition
2. Dense/sparse/graph strategy selection
3. Filter and ACL pushdown
4. Rerank/context packing budget
5. Fallback and evidence-insufficient abstention

## Native acceptance corpus

- `ELMOS_RAG_QUERY_PLANNER_OPTIMIZER-01` — simple retrieval
- `ELMOS_RAG_QUERY_PLANNER_OPTIMIZER-02` — multi-hop decomposition
- `ELMOS_RAG_QUERY_PLANNER_OPTIMIZER-03` — hybrid fusion
- `ELMOS_RAG_QUERY_PLANNER_OPTIMIZER-04` — filter pushdown
- `ELMOS_RAG_QUERY_PLANNER_OPTIMIZER-05` — budget constraint
- `ELMOS_RAG_QUERY_PLANNER_OPTIMIZER-06` — unsupported evidence abstention

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
