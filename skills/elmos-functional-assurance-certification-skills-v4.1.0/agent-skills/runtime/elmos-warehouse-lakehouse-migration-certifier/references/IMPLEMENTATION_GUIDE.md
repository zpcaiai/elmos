# Implementation Guide — Warehouse and Lakehouse Migration Certifier

## Purpose

Certify semantic, performance, governance and cost migration among warehouses and open table formats using dual execution and workload replay.

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

1. translate analytical SQL and UDFs
2. replay representative BI/ETL workloads
3. verify data and aggregate equivalence
4. validate table-feature and engine compatibility
5. certify cost, concurrency and rollback

## Native acceptance corpus

- `ELMOS_WAREHOUSE_LAKEHOUSE_MIGRATION_CERTIFIER-01` — native scenario: translate analytical SQL and UDFs
- `ELMOS_WAREHOUSE_LAKEHOUSE_MIGRATION_CERTIFIER-02` — native scenario: replay representative BI/ETL workloads
- `ELMOS_WAREHOUSE_LAKEHOUSE_MIGRATION_CERTIFIER-03` — native scenario: verify data and aggregate equivalence
- `ELMOS_WAREHOUSE_LAKEHOUSE_MIGRATION_CERTIFIER-04` — native scenario: validate table-feature and engine compatibility
- `ELMOS_WAREHOUSE_LAKEHOUSE_MIGRATION_CERTIFIER-05` — native scenario: certify cost, concurrency and rollback

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
