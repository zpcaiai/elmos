# Implementation Guide — Kubernetes AI Workload Operator Generator

## Purpose

Generate controllers/CRDs for agent, retrieval and model-serving workloads with reconciliation, status, finalizers, upgrades and tenancy.

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

1. define versioned CRDs and status conditions
2. implement idempotent reconciliation and finalizers
3. manage model/data/artifact dependencies
4. enforce tenant, network and resource policy
5. test upgrade, failure and deletion semantics

## Native acceptance corpus

- `ELMOS_KUBERNETES_AI_WORKLOAD_OPERATOR_GENERATOR-01` — native scenario: define versioned CRDs and status conditions
- `ELMOS_KUBERNETES_AI_WORKLOAD_OPERATOR_GENERATOR-02` — native scenario: implement idempotent reconciliation and finalizers
- `ELMOS_KUBERNETES_AI_WORKLOAD_OPERATOR_GENERATOR-03` — native scenario: manage model/data/artifact dependencies
- `ELMOS_KUBERNETES_AI_WORKLOAD_OPERATOR_GENERATOR-04` — native scenario: enforce tenant, network and resource policy
- `ELMOS_KUBERNETES_AI_WORKLOAD_OPERATOR_GENERATOR-05` — native scenario: test upgrade, failure and deletion semantics

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
