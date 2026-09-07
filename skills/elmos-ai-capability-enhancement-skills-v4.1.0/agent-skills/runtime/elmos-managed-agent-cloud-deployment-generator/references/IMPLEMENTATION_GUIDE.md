# Implementation Guide — Managed Agent Cloud Deployment Generator

## Purpose

Generate portable deployments to AWS, Google, Microsoft and Databricks managed agent runtimes with identity, network, observability, evidence and exit plans.

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

1. Managed runtime capability negotiation
2. IaC and workload identity generation
3. Private networking and data residency
4. Native health/trace/cost integration
5. Export, rollback and vendor-exit validation

## Native acceptance corpus

- `ELMOS_MANAGED_AGENT_CLOUD_DEPLOYMENT_GENERATOR-01` — AWS target plan
- `ELMOS_MANAGED_AGENT_CLOUD_DEPLOYMENT_GENERATOR-02` — Google target plan
- `ELMOS_MANAGED_AGENT_CLOUD_DEPLOYMENT_GENERATOR-03` — Microsoft target plan
- `ELMOS_MANAGED_AGENT_CLOUD_DEPLOYMENT_GENERATOR-04` — Databricks target plan
- `ELMOS_MANAGED_AGENT_CLOUD_DEPLOYMENT_GENERATOR-05` — identity/network denial
- `ELMOS_MANAGED_AGENT_CLOUD_DEPLOYMENT_GENERATOR-06` — export and rollback

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
