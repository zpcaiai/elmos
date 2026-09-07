# Implementation Guide — Capacity, Soak and Efficiency Certifier

## Purpose

Certify sustained throughput, concurrency, queue stability, resource leaks, cache behavior, model/provider limits and unit economics at declared capacity.

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

1. Model representative arrival and service distributions
2. Run load, stress and long-duration soak
3. Detect memory/connection/thread/queue leaks
4. Exercise rate limits and provider fallbacks
5. Compute cost per successful certified unit

## Native acceptance corpus

- `ELMOS_CAPACITY_SOAK_EFFICIENCY_CERTIFIER-01` — steady load
- `ELMOS_CAPACITY_SOAK_EFFICIENCY_CERTIFIER-02` — burst/backpressure
- `ELMOS_CAPACITY_SOAK_EFFICIENCY_CERTIFIER-03` — max account concurrency
- `ELMOS_CAPACITY_SOAK_EFFICIENCY_CERTIFIER-04` — 24-72h soak contract
- `ELMOS_CAPACITY_SOAK_EFFICIENCY_CERTIFIER-05` — cache hit/miss shift
- `ELMOS_CAPACITY_SOAK_EFFICIENCY_CERTIFIER-06` — provider rate limit
- `ELMOS_CAPACITY_SOAK_EFFICIENCY_CERTIFIER-07` — cost per successful run

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
