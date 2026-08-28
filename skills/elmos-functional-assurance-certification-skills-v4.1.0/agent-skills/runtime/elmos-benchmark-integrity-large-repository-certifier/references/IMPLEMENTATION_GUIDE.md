# Implementation Guide — Benchmark Integrity and Large Repository Certifier

## Purpose

Certify repository-scale productivity and correctness on hidden, contamination-checked, representative repositories including >500k and >1M LOC cases.

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

1. Freeze hidden benchmark repositories and licenses
2. Check training/eval contamination and memorization signals
3. Measure correctness, completion, time and cost
4. Require repeated independent runs and failure disclosure
5. Separate route-specific from broad marketing claims

## Native acceptance corpus

- `ELMOS_BENCHMARK_INTEGRITY_LARGE_REPOSITORY_CERTIFIER-01` — 500k LOC repository
- `ELMOS_BENCHMARK_INTEGRITY_LARGE_REPOSITORY_CERTIFIER-02` — 1M LOC repository
- `ELMOS_BENCHMARK_INTEGRITY_LARGE_REPOSITORY_CERTIFIER-03` — multi-module/multi-language repo
- `ELMOS_BENCHMARK_INTEGRITY_LARGE_REPOSITORY_CERTIFIER-04` — generated/vendor code handling
- `ELMOS_BENCHMARK_INTEGRITY_LARGE_REPOSITORY_CERTIFIER-05` — hidden acceptance
- `ELMOS_BENCHMARK_INTEGRITY_LARGE_REPOSITORY_CERTIFIER-06` — three repeated runs
- `ELMOS_BENCHMARK_INTEGRITY_LARGE_REPOSITORY_CERTIFIER-07` — cost/ETA accuracy

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
