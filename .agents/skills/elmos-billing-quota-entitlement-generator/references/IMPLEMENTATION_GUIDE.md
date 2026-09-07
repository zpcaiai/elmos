# Implementation Guide — Billing, Quota and Entitlement Generator

## Purpose

Generate prepaid/usage/project billing, entitlement, quota, reservation, settlement and dispute evidence from machine usage ledgers.

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

1. compile product plans and entitlements
2. reserve and enforce concurrent/task/token budgets
3. meter immutable usage and provider costs
4. settle, refund and reconcile transactions
5. expose customer usage and dispute evidence

## Native acceptance corpus

- `ELMOS_BILLING_QUOTA_ENTITLEMENT_GENERATOR-01` — native scenario: compile product plans and entitlements
- `ELMOS_BILLING_QUOTA_ENTITLEMENT_GENERATOR-02` — native scenario: reserve and enforce concurrent/task/token budgets
- `ELMOS_BILLING_QUOTA_ENTITLEMENT_GENERATOR-03` — native scenario: meter immutable usage and provider costs
- `ELMOS_BILLING_QUOTA_ENTITLEMENT_GENERATOR-04` — native scenario: settle, refund and reconcile transactions
- `ELMOS_BILLING_QUOTA_ENTITLEMENT_GENERATOR-05` — native scenario: expose customer usage and dispute evidence

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
