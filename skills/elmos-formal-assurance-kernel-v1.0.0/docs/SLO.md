# Service Level Objectives

## Availability and control-plane SLOs

| Indicator | Target |
|---|---:|
| Control API availability | 99.9% monthly |
| Gate evaluation availability | 99.95% monthly |
| Artifact commit durability after 201 | 99.999999999% target, subject to storage provider |
| P95 control-plane overhead excluding verifier | < 2 seconds |
| P95 queued P0 proof start under normal capacity | < 60 seconds |
| Stale TCB/assumption invalidation propagation | < 5 minutes |
| Cross-tenant access escape | 0 |
| Status-inflation acceptance | 0 |

## Proof-performance indicators

Verifier runtime is workload dependent and is not an API latency SLO. Track by business line, property kind, engine, semantic profile and formula-size bucket:

- wall-clock p50/p95/p99;
- timeout/resource-unknown ratio;
- proof/counterexample ratio;
- cache hit ratio;
- reproof amplification after changes;
- estimated versus actual machine ETA error;
- artifact bytes and cost per obligation.

## Error budgets

A gate outage consumes a stricter budget than reporting. When the gate budget is exhausted, production changes requiring formal assurance freeze; the system must not fail open.

## Cardinality and privacy

Do not place tenant IDs, source paths, formulas, SQL or counterexample values in metric labels. Use trace IDs and controlled dimensions. Detailed data remains in tenant-scoped logs/artifacts.
