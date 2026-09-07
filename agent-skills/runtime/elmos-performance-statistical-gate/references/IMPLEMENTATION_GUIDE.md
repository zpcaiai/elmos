# Implementation Guide — Performance Statistical Gate

## Purpose

Evaluate latency, throughput, resource, quality and cost regressions with representative workloads, confidence intervals, power analysis and sequential decisions.

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

1. Define workload and measurement protocol before execution
2. Separate warmup, steady state and saturation
3. Use confidence intervals and practical effect thresholds
4. Control repeated/sequential testing error
5. Report quality-cost-latency tradeoffs

## Native acceptance corpus

- `ELMOS_PERFORMANCE_STATISTICAL_GATE-01` — P95/P99 latency
- `ELMOS_PERFORMANCE_STATISTICAL_GATE-02` — throughput saturation
- `ELMOS_PERFORMANCE_STATISTICAL_GATE-03` — resource efficiency
- `ELMOS_PERFORMANCE_STATISTICAL_GATE-04` — quality versus cost
- `ELMOS_PERFORMANCE_STATISTICAL_GATE-05` — paired baseline/candidate
- `ELMOS_PERFORMANCE_STATISTICAL_GATE-06` — soak trend
- `ELMOS_PERFORMANCE_STATISTICAL_GATE-07` — low-power experiment blocks

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
