# Implementation Guide — Federated Retrieval and Data-Source Router

## Purpose

Route queries across private, remote, SQL, search, graph and vector sources under capability, authorization, freshness, latency and cost constraints.

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

1. compile source capability and authorization profiles
2. decompose and route multi-source queries
3. merge evidence with calibrated scores
4. enforce residency and minimum disclosure
5. fallback, timeout and partial-result semantics

## Native acceptance corpus

- `ELMOS_FEDERATED_RETRIEVAL_DATA_SOURCE_ROUTER-01` — native scenario: compile source capability and authorization profiles
- `ELMOS_FEDERATED_RETRIEVAL_DATA_SOURCE_ROUTER-02` — native scenario: decompose and route multi-source queries
- `ELMOS_FEDERATED_RETRIEVAL_DATA_SOURCE_ROUTER-03` — native scenario: merge evidence with calibrated scores
- `ELMOS_FEDERATED_RETRIEVAL_DATA_SOURCE_ROUTER-04` — native scenario: enforce residency and minimum disclosure
- `ELMOS_FEDERATED_RETRIEVAL_DATA_SOURCE_ROUTER-05` — native scenario: fallback, timeout and partial-result semantics

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
