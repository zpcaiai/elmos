# Implementation Guide — Admin and Operator Portal Generator

## Purpose

Generate tenant administration, run control, approvals, evidence, cost, incident and certification views with least privilege and auditability.

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

1. generate role-scoped navigation and APIs
2. surface run, proof, cost and certificate state
3. implement approval, kill switch and recovery actions
4. support audit export and tenant support boundaries
5. test accessibility, security and stale-state handling

## Native acceptance corpus

- `ELMOS_ADMIN_OPERATOR_PORTAL_GENERATOR-01` — native scenario: generate role-scoped navigation and APIs
- `ELMOS_ADMIN_OPERATOR_PORTAL_GENERATOR-02` — native scenario: surface run, proof, cost and certificate state
- `ELMOS_ADMIN_OPERATOR_PORTAL_GENERATOR-03` — native scenario: implement approval, kill switch and recovery actions
- `ELMOS_ADMIN_OPERATOR_PORTAL_GENERATOR-04` — native scenario: support audit export and tenant support boundaries
- `ELMOS_ADMIN_OPERATOR_PORTAL_GENERATOR-05` — native scenario: test accessibility, security and stale-state handling

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
