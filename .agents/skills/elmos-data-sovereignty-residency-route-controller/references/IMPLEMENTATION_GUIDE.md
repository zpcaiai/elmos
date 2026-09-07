# Implementation Guide — Data Sovereignty and Residency Route Controller

## Purpose

Route data, models, logs, backups and support access across regions/providers under residency, transfer, encryption and deletion policy.

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

1. classify data and processing location requirements
2. select region/provider/store routes
3. control transfer, replication and support access
4. verify backups, telemetry and caches remain in scope
5. trigger block or migration on policy/provider drift

## Native acceptance corpus

- `ELMOS_DATA_SOVEREIGNTY_RESIDENCY_ROUTE_CONTROLLER-01` — native scenario: classify data and processing location requirements
- `ELMOS_DATA_SOVEREIGNTY_RESIDENCY_ROUTE_CONTROLLER-02` — native scenario: select region/provider/store routes
- `ELMOS_DATA_SOVEREIGNTY_RESIDENCY_ROUTE_CONTROLLER-03` — native scenario: control transfer, replication and support access
- `ELMOS_DATA_SOVEREIGNTY_RESIDENCY_ROUTE_CONTROLLER-04` — native scenario: verify backups, telemetry and caches remain in scope
- `ELMOS_DATA_SOVEREIGNTY_RESIDENCY_ROUTE_CONTROLLER-05` — native scenario: trigger block or migration on policy/provider drift

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
