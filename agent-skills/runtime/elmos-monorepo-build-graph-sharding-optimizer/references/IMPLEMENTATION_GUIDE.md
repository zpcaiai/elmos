# Implementation Guide — Monorepo Build-Graph Sharding Optimizer

## Purpose

Partition million-file polyglot repositories into dependency-safe analysis, generation, build and verification shards with cache-aware critical-path scheduling.

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

1. construct cross-language build and ownership graph
2. derive deterministic shard boundaries
3. schedule critical path under tenant quotas
4. reuse content-addressed artifacts safely
5. merge shard evidence without coverage gaps

## Native acceptance corpus

- `ELMOS_MONOREPO_BUILD_GRAPH_SHARDING_OPTIMIZER-01` — native scenario: construct cross-language build and ownership graph
- `ELMOS_MONOREPO_BUILD_GRAPH_SHARDING_OPTIMIZER-02` — native scenario: derive deterministic shard boundaries
- `ELMOS_MONOREPO_BUILD_GRAPH_SHARDING_OPTIMIZER-03` — native scenario: schedule critical path under tenant quotas
- `ELMOS_MONOREPO_BUILD_GRAPH_SHARDING_OPTIMIZER-04` — native scenario: reuse content-addressed artifacts safely
- `ELMOS_MONOREPO_BUILD_GRAPH_SHARDING_OPTIMIZER-05` — native scenario: merge shard evidence without coverage gaps

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
