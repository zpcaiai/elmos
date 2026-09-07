# Implementation Guide — Vector Store Migration and Benchmark Controller

## Purpose

Migrate embeddings and metadata among vector stores while preserving ACLs, recall, latency, freshness, deletion and cost envelopes.

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

1. validate embedding identity and dimensionality
2. rebuild or transfer indexes deterministically
3. run recall/latency/cost benchmark corpora
4. verify ACL and namespace preservation
5. shadow queries and gate cutover/rollback

## Native acceptance corpus

- `ELMOS_VECTOR_STORE_MIGRATION_BENCHMARK_CONTROLLER-01` — native scenario: validate embedding identity and dimensionality
- `ELMOS_VECTOR_STORE_MIGRATION_BENCHMARK_CONTROLLER-02` — native scenario: rebuild or transfer indexes deterministically
- `ELMOS_VECTOR_STORE_MIGRATION_BENCHMARK_CONTROLLER-03` — native scenario: run recall/latency/cost benchmark corpora
- `ELMOS_VECTOR_STORE_MIGRATION_BENCHMARK_CONTROLLER-04` — native scenario: verify ACL and namespace preservation
- `ELMOS_VECTOR_STORE_MIGRATION_BENCHMARK_CONTROLLER-05` — native scenario: shadow queries and gate cutover/rollback

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
