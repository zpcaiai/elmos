# Implementation Guide — GraphRAG Pipeline Certifier

## Purpose

Certify graph construction, community/entity retrieval, path grounding, citations, updates, deletion and performance for GraphRAG implementations.

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

1. validate extraction and graph build quality
2. measure graph retrieval recall and path precision
3. verify claims to node/edge/source provenance
4. test incremental update and deletion
5. benchmark graph/vector/hybrid cost and latency

## Native acceptance corpus

- `ELMOS_GRAPHRAG_PIPELINE_CERTIFIER-01` — native scenario: validate extraction and graph build quality
- `ELMOS_GRAPHRAG_PIPELINE_CERTIFIER-02` — native scenario: measure graph retrieval recall and path precision
- `ELMOS_GRAPHRAG_PIPELINE_CERTIFIER-03` — native scenario: verify claims to node/edge/source provenance
- `ELMOS_GRAPHRAG_PIPELINE_CERTIFIER-04` — native scenario: test incremental update and deletion
- `ELMOS_GRAPHRAG_PIPELINE_CERTIFIER-05` — native scenario: benchmark graph/vector/hybrid cost and latency

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
