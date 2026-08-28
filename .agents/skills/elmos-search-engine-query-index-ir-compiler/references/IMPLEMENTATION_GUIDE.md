# Implementation Guide — Search Engine Query and Index IR Compiler

## Purpose

Compile analyzer, tokenizer, mapping, relevance, aggregation, vector-hybrid, alias and shard semantics across Elasticsearch/OpenSearch-class systems.

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

1. model mappings, analyzers and token filters
2. compile query DSL and scoring semantics
3. represent index aliases and zero-downtime reindex
4. capture shard, replica and refresh behavior
5. verify hybrid lexical/vector retrieval

## Native acceptance corpus

- `ELMOS_SEARCH_ENGINE_QUERY_INDEX_IR_COMPILER-01` — native scenario: model mappings, analyzers and token filters
- `ELMOS_SEARCH_ENGINE_QUERY_INDEX_IR_COMPILER-02` — native scenario: compile query DSL and scoring semantics
- `ELMOS_SEARCH_ENGINE_QUERY_INDEX_IR_COMPILER-03` — native scenario: represent index aliases and zero-downtime reindex
- `ELMOS_SEARCH_ENGINE_QUERY_INDEX_IR_COMPILER-04` — native scenario: capture shard, replica and refresh behavior
- `ELMOS_SEARCH_ENGINE_QUERY_INDEX_IR_COMPILER-05` — native scenario: verify hybrid lexical/vector retrieval

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
