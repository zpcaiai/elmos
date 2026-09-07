# Implementation Guide — AI Tenant Memory Isolation Verifier

## Purpose

Prove isolation of session, user, organization, episodic, semantic and procedural memory across storage, cache, retrieval and trace boundaries.

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

1. Memory scope and namespace model
2. RLS/ACL/cache partition verification
3. Cross-agent sharing consent
4. Export/delete and lifecycle isolation
5. Adversarial tenant crossover campaign

## Native acceptance corpus

- `ELMOS_AI_TENANT_MEMORY_ISOLATION_VERIFIER-01` — session isolation
- `ELMOS_AI_TENANT_MEMORY_ISOLATION_VERIFIER-02` — user/organization isolation
- `ELMOS_AI_TENANT_MEMORY_ISOLATION_VERIFIER-03` — shared memory consent
- `ELMOS_AI_TENANT_MEMORY_ISOLATION_VERIFIER-04` — cache isolation
- `ELMOS_AI_TENANT_MEMORY_ISOLATION_VERIFIER-05` — export/delete
- `ELMOS_AI_TENANT_MEMORY_ISOLATION_VERIFIER-06` — cross-tenant adversarial query

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
