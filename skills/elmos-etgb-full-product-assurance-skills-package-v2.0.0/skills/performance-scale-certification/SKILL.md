---
name: performance-scale-certification
description: Certify functional and operational scalability across large repositories, data volumes, concurrency, soak, stress, resource, token, credit and latency budgets.
---

# Performance and Scale Certification

## Repository tiers

- L1 fixture: isolated semantics;
- L2 small repository: at least 10k LOC or multiple modules;
- L3 medium: at least 100k LOC, 15 modules or 10-minute baseline build;
- L4 large: at least 500k LOC, 50 modules or 30-minute build;
- L4 mega: at least 1M LOC, 100 modules or 60-minute build.

A commercial large-repository claim requires at least three repositories above 500k LOC, including one above 1M LOC, with repeated clean evidence.

## Campaigns

- cold and warm-cache runs;
- single and maximum account concurrency;
- fair multi-tenant load;
- large file/module/dependency graphs;
- large database schema, routine count and row volumes;
- long-running soak for memory, thread, file-descriptor and workspace leaks;
- stress to budget/resource limits and graceful backpressure;
- cancellation/resume of large shards;
- provider rate-limit and degraded dependency modes.

## Metrics

Track queue time separately from execution. Measure phase p50/p95/p99, throughput, peak RSS, CPU, disk/network, cache hit, retries, tokens, credits and total machine wall-clock. Correctness and security are prerequisites; faster wrong output is a failure.

## Comparison

Use absolute service objectives and candidate-vs-baseline non-regression ratios. Do not require identical database plans or language runtime profiles; require equivalent behavior within explicit operational budgets. Repeat runs and publish confidence/variance.

## Scalability invariants

- work and memory grow within declared complexity envelopes;
- shard count does not change semantics;
- resume does not duplicate work or side effects;
- increasing concurrency respects three-task account cap and tenant fairness;
- cache keys include every semantic and policy digest;
- performance optimizations do not weaken tests or Oracles.

## Implementation

Use `etgb/performance.py`, machine ETA/cost history and scale-specific L3/L4 corpora. Store raw profiler/benchmark artifacts in the evidence ledger.
