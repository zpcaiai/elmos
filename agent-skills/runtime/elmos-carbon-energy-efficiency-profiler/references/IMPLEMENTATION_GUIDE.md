# Implementation Guide — Carbon and Energy Efficiency Profiler

## Purpose

Measure and optimize energy, accelerator utilization, region/time scheduling and carbon estimates without compromising correctness, privacy or SLA.

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

1. collect workload and hardware energy proxies
2. compare model/runtime efficiency per verified task
3. schedule flexible work under policy
4. report assumptions and regional carbon factors
5. gate optimization against quality and residency

## Native acceptance corpus

- `ELMOS_CARBON_ENERGY_EFFICIENCY_PROFILER-01` — native scenario: collect workload and hardware energy proxies
- `ELMOS_CARBON_ENERGY_EFFICIENCY_PROFILER-02` — native scenario: compare model/runtime efficiency per verified task
- `ELMOS_CARBON_ENERGY_EFFICIENCY_PROFILER-03` — native scenario: schedule flexible work under policy
- `ELMOS_CARBON_ENERGY_EFFICIENCY_PROFILER-04` — native scenario: report assumptions and regional carbon factors
- `ELMOS_CARBON_ENERGY_EFFICIENCY_PROFILER-05` — native scenario: gate optimization against quality and residency

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
