# Implementation Guide — Cross-Store Polyglot Persistence Route Planner

## Purpose

Select relational, document, key-value, graph, search, vector and lakehouse targets per bounded context using workload, semantics, reversibility and operational evidence.

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

1. classify aggregate and query workloads
2. score store capabilities and exit risk
3. design ownership and consistency boundaries
4. plan coexistence and strangler routes
5. emit no-fit and external-policy decisions

## Native acceptance corpus

- `ELMOS_CROSS_STORE_POLYGLOT_PERSISTENCE_ROUTE_PLANNER-01` — native scenario: classify aggregate and query workloads
- `ELMOS_CROSS_STORE_POLYGLOT_PERSISTENCE_ROUTE_PLANNER-02` — native scenario: score store capabilities and exit risk
- `ELMOS_CROSS_STORE_POLYGLOT_PERSISTENCE_ROUTE_PLANNER-03` — native scenario: design ownership and consistency boundaries
- `ELMOS_CROSS_STORE_POLYGLOT_PERSISTENCE_ROUTE_PLANNER-04` — native scenario: plan coexistence and strangler routes
- `ELMOS_CROSS_STORE_POLYGLOT_PERSISTENCE_ROUTE_PLANNER-05` — native scenario: emit no-fit and external-policy decisions

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
