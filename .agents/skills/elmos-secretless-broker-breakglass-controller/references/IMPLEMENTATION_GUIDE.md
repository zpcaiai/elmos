# Implementation Guide — Secretless Broker and Break-Glass Controller

## Purpose

Issue short-lived scoped credentials, eliminate static secrets, and govern audited emergency access with dual control and automatic expiry.

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

1. broker workload-bound credentials
2. enforce purpose, path and parameter scope
3. rotate and revoke automatically
4. implement dual-control break-glass
5. reconcile and review every emergency action

## Native acceptance corpus

- `ELMOS_SECRETLESS_BROKER_BREAKGLASS_CONTROLLER-01` — native scenario: broker workload-bound credentials
- `ELMOS_SECRETLESS_BROKER_BREAKGLASS_CONTROLLER-02` — native scenario: enforce purpose, path and parameter scope
- `ELMOS_SECRETLESS_BROKER_BREAKGLASS_CONTROLLER-03` — native scenario: rotate and revoke automatically
- `ELMOS_SECRETLESS_BROKER_BREAKGLASS_CONTROLLER-04` — native scenario: implement dual-control break-glass
- `ELMOS_SECRETLESS_BROKER_BREAKGLASS_CONTROLLER-05` — native scenario: reconcile and review every emergency action

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
