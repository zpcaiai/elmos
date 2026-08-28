# Implementation Guide — Multi-Tenant SaaS Foundation Generator

## Purpose

Generate tenant identity, isolation, provisioning, quotas, data boundaries, audit, lifecycle and operational controls for commercial AI services.

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

1. select pooled, siloed or hybrid tenancy
2. generate tenant provisioning and offboarding
3. enforce data/cache/vector/evidence isolation
4. integrate quota, audit and support boundaries
5. test noisy-neighbor and tenant deletion

## Native acceptance corpus

- `ELMOS_MULTI_TENANT_SAAS_FOUNDATION_GENERATOR-01` — native scenario: select pooled, siloed or hybrid tenancy
- `ELMOS_MULTI_TENANT_SAAS_FOUNDATION_GENERATOR-02` — native scenario: generate tenant provisioning and offboarding
- `ELMOS_MULTI_TENANT_SAAS_FOUNDATION_GENERATOR-03` — native scenario: enforce data/cache/vector/evidence isolation
- `ELMOS_MULTI_TENANT_SAAS_FOUNDATION_GENERATOR-04` — native scenario: integrate quota, audit and support boundaries
- `ELMOS_MULTI_TENANT_SAAS_FOUNDATION_GENERATOR-05` — native scenario: test noisy-neighbor and tenant deletion

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
