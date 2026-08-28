# Implementation Guide — Database Performance and Plan Certifier

## Purpose

Certify representative query plans, latency, throughput, resource use, statistics sensitivity and capacity under target database versions and data distributions.

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

1. Capture normalized and native plans
2. Test representative cardinality/data skew
3. Use statistical latency and throughput gates
4. Detect plan instability after version/statistics change
5. Bind certificate to workload and parameter envelope

## Native acceptance corpus

- `ELMOS_DATABASE_PERFORMANCE_PLAN_CERTIFIER-01` — TPC-style representative query set
- `ELMOS_DATABASE_PERFORMANCE_PLAN_CERTIFIER-02` — data skew plan choice
- `ELMOS_DATABASE_PERFORMANCE_PLAN_CERTIFIER-03` — index usage
- `ELMOS_DATABASE_PERFORMANCE_PLAN_CERTIFIER-04` — parameter sniffing/bind peeking
- `ELMOS_DATABASE_PERFORMANCE_PLAN_CERTIFIER-05` — statistics refresh
- `ELMOS_DATABASE_PERFORMANCE_PLAN_CERTIFIER-06` — P95/P99 regression
- `ELMOS_DATABASE_PERFORMANCE_PLAN_CERTIFIER-07` — connection pool saturation

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
