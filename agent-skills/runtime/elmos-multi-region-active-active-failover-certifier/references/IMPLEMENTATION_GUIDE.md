# Implementation Guide — Multi-Region Active-Active Failover Certifier

## Purpose

Certify routing, data replication, session/memory ownership, consistency, failover, failback and regional isolation for AI services.

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

1. model region topology and failure domains
2. verify data, cache and session replication
3. exercise active-active conflict handling
4. perform failover/failback under load
5. confirm residency, RTO/RPO and cost envelope

## Native acceptance corpus

- `ELMOS_MULTI_REGION_ACTIVE_ACTIVE_FAILOVER_CERTIFIER-01` — native scenario: model region topology and failure domains
- `ELMOS_MULTI_REGION_ACTIVE_ACTIVE_FAILOVER_CERTIFIER-02` — native scenario: verify data, cache and session replication
- `ELMOS_MULTI_REGION_ACTIVE_ACTIVE_FAILOVER_CERTIFIER-03` — native scenario: exercise active-active conflict handling
- `ELMOS_MULTI_REGION_ACTIVE_ACTIVE_FAILOVER_CERTIFIER-04` — native scenario: perform failover/failback under load
- `ELMOS_MULTI_REGION_ACTIVE_ACTIVE_FAILOVER_CERTIFIER-05` — native scenario: confirm residency, RTO/RPO and cost envelope

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
