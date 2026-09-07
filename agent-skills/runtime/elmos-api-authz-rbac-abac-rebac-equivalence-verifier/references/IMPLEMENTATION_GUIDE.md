# Implementation Guide — API Authorization RBAC/ABAC/ReBAC Equivalence Verifier

## Purpose

Verify authorization semantics across source/target frameworks and policy engines, including field, row, relationship and contextual decisions.

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

1. compile authorization decision graph
2. generate positive and negative identity/context matrix
3. compare source and target decisions and explanations
4. verify cache and policy-update invalidation
5. test row/field/tool and relationship authorization

## Native acceptance corpus

- `ELMOS_API_AUTHZ_RBAC_ABAC_REBAC_EQUIVALENCE_VERIFIER-01` — native scenario: compile authorization decision graph
- `ELMOS_API_AUTHZ_RBAC_ABAC_REBAC_EQUIVALENCE_VERIFIER-02` — native scenario: generate positive and negative identity/context matrix
- `ELMOS_API_AUTHZ_RBAC_ABAC_REBAC_EQUIVALENCE_VERIFIER-03` — native scenario: compare source and target decisions and explanations
- `ELMOS_API_AUTHZ_RBAC_ABAC_REBAC_EQUIVALENCE_VERIFIER-04` — native scenario: verify cache and policy-update invalidation
- `ELMOS_API_AUTHZ_RBAC_ABAC_REBAC_EQUIVALENCE_VERIFIER-05` — native scenario: test row/field/tool and relationship authorization

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
