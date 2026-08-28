# Implementation Guide — Vector Database and Index IR Compiler

## Purpose

Compile embedding schema, metric, normalization, filter, index algorithm, consistency, namespace, deletion and recall/latency envelopes across vector stores.

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

1. model vector dimensions, metric and normalization
2. capture HNSW/IVF/PQ and vendor index parameters
3. represent metadata filters and tenant namespaces
4. compile update/delete/compaction semantics
5. bind recall, latency and cost obligations

## Native acceptance corpus

- `ELMOS_VECTOR_DATABASE_INDEX_IR_COMPILER-01` — native scenario: model vector dimensions, metric and normalization
- `ELMOS_VECTOR_DATABASE_INDEX_IR_COMPILER-02` — native scenario: capture HNSW/IVF/PQ and vendor index parameters
- `ELMOS_VECTOR_DATABASE_INDEX_IR_COMPILER-03` — native scenario: represent metadata filters and tenant namespaces
- `ELMOS_VECTOR_DATABASE_INDEX_IR_COMPILER-04` — native scenario: compile update/delete/compaction semantics
- `ELMOS_VECTOR_DATABASE_INDEX_IR_COMPILER-05` — native scenario: bind recall, latency and cost obligations

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
