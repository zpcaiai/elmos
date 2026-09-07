# Performance and scale certification

## Scale claims

Large-repository commercial certification requires three repositories above 500k LOC and at least one above 1M LOC. Record modules, dependency edges, build time, tests, database objects and artifact size; LOC alone is insufficient.

## Tests

Cold/warm cache, max account concurrency, fair multi-tenant load, shard resume, load, stress, long soak, dependency degradation, large database/schema/routine datasets and cancellation under pressure.

## Metrics

Separate queue and execution. Track p50/p95/p99 per phase, throughput, peak RSS, CPU, disk/network, cache, retry, tokens, credits and machine wall-clock. Correctness, security and evidence gates remain prerequisites.

Use `etgb/performance.py` and the `performance-scale-certification` Skill.
