---
name: query-workload-rewrite-plan-and-performance-validator
description: Rewrite representative SQL workloads and independently compare results, plans, latency, throughput, locks, concurrency, and parameter sensitivity across source and target databases. Use for database migration query compatibility, performance regression, and cutover readiness validation.
---

# Query Workload Validation

## Select representative work

- Prioritize OLTP reads/writes, reports, analytical scans, batch updates, ETL, maintenance, and admin SQL by frequency, total time, P95, CPU, IO, locks, business criticality, errors, and cutover impact.
- Use captured workload and approved synthetic supplements; do not treat one query as system coverage.

## Compare semantics

- Execute source and target SQL against equivalent isolated data.
- Compare columns, types, nulls, values, counts, duplicates, decimals, dates, characters, and errors.
- Do not treat order as contractual without ORDER BY; raise IMPLICIT_ORDER_DEPENDENCY when consumers rely on accidental ordering.
- Validate pagination, merge/upsert, hierarchy, pivot, temporal, JSON, casts, collation, locks, and isolation explicitly.

## Compare performance

- Compare actual latency, throughput, CPU, IO, rows, memory, spills, locks, and concurrency; never compare vendor optimizer cost numbers directly.
- Test bind peeking, parameter sniffing, generic/literal plans, skew, histograms, prepared statements, hot keys, long transactions, pools, deadlocks, and failover.
- Evaluate result correctness and performance as independent gates.
- Fail cutover when approved P95, throughput, lock, resource, or stability thresholds regress.
