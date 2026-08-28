# Implementation Guide — Cost Allocation, Chargeback and Showback Controller

## Purpose

Allocate model, compute, storage, network, database and support costs to tenant, project, route and feature with explainable reconciliation.

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

1. ingest provider and internal usage ledgers
2. attribute shared and cached costs
3. reconcile estimates with invoices
4. generate showback/chargeback and anomaly alerts
5. preserve pricing version and margin evidence

## Native acceptance corpus

- `ELMOS_COST_ALLOCATION_CHARGEBACK_SHOWBACK_CONTROLLER-01` — native scenario: ingest provider and internal usage ledgers
- `ELMOS_COST_ALLOCATION_CHARGEBACK_SHOWBACK_CONTROLLER-02` — native scenario: attribute shared and cached costs
- `ELMOS_COST_ALLOCATION_CHARGEBACK_SHOWBACK_CONTROLLER-03` — native scenario: reconcile estimates with invoices
- `ELMOS_COST_ALLOCATION_CHARGEBACK_SHOWBACK_CONTROLLER-04` — native scenario: generate showback/chargeback and anomaly alerts
- `ELMOS_COST_ALLOCATION_CHARGEBACK_SHOWBACK_CONTROLLER-05` — native scenario: preserve pricing version and margin evidence

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
