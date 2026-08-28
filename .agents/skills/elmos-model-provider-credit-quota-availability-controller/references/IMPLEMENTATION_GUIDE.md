# Implementation Guide — Model Provider Credit, Quota and Availability Controller

## Purpose

Track subscription/credit/quota, real-time usage, rate limits, regional availability and failover capacity across model providers.

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

1. ingest quota, credit and rate-limit state
2. reserve capacity per run and tenant
3. forecast depletion and reset windows
4. coordinate safe provider fallback
5. reconcile provider usage and invoices

## Native acceptance corpus

- `ELMOS_MODEL_PROVIDER_CREDIT_QUOTA_AVAILABILITY_CONTROLLER-01` — native scenario: ingest quota, credit and rate-limit state
- `ELMOS_MODEL_PROVIDER_CREDIT_QUOTA_AVAILABILITY_CONTROLLER-02` — native scenario: reserve capacity per run and tenant
- `ELMOS_MODEL_PROVIDER_CREDIT_QUOTA_AVAILABILITY_CONTROLLER-03` — native scenario: forecast depletion and reset windows
- `ELMOS_MODEL_PROVIDER_CREDIT_QUOTA_AVAILABILITY_CONTROLLER-04` — native scenario: coordinate safe provider fallback
- `ELMOS_MODEL_PROVIDER_CREDIT_QUOTA_AVAILABILITY_CONTROLLER-05` — native scenario: reconcile provider usage and invoices

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
