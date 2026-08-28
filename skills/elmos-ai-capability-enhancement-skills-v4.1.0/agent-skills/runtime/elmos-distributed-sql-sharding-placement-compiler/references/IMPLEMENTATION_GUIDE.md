# Implementation Guide — Distributed SQL Sharding and Placement Compiler

## Purpose

Compile sharding, locality, replica, consistency, rebalance, global index and distributed transaction semantics for distributed SQL targets.

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

1. derive shard and locality keys from workload evidence
2. model replica placement and failure domains
3. compile global index and cross-shard transaction rules
4. plan online rebalance and hotspot mitigation
5. verify consistency under partition and failover

## Native acceptance corpus

- `ELMOS_DISTRIBUTED_SQL_SHARDING_PLACEMENT_COMPILER-01` — native scenario: derive shard and locality keys from workload evidence
- `ELMOS_DISTRIBUTED_SQL_SHARDING_PLACEMENT_COMPILER-02` — native scenario: model replica placement and failure domains
- `ELMOS_DISTRIBUTED_SQL_SHARDING_PLACEMENT_COMPILER-03` — native scenario: compile global index and cross-shard transaction rules
- `ELMOS_DISTRIBUTED_SQL_SHARDING_PLACEMENT_COMPILER-04` — native scenario: plan online rebalance and hotspot mitigation
- `ELMOS_DISTRIBUTED_SQL_SHARDING_PLACEMENT_COMPILER-05` — native scenario: verify consistency under partition and failover

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
