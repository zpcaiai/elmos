# Performance Equivalence Verification

- **Skill ID:** `10-performance-equivalence-verification`
- **Version:** `1.0.0`
- **Category:** core/verification
- **Implementation status:** specification only until repository evidence proves otherwise

## Objective

Compare source and target at workload level under controlled infrastructure and data conditions, then distinguish SQL-plan, schema-design, application-pool and distributed-architecture regressions.

## Inputs

- Representative dataset/workload
- Source and target infrastructure metadata
- SLOs and concurrency profile
- Critical query/transaction set
- Warm/cold cache policy

## Required outputs

- Latency/throughput/error metrics
- Plan/operator diffs
- Resource utilization
- Regression attribution
- Target tuning recommendations
- E4 gate result

## Implementation modules / repository contract

- perf/workload.py
- perf/runner.py
- perf/metrics.py
- perf/plan_capture.py
- perf/resources.py
- perf/regression.py
- perf/tuning.py

## Interfaces and contracts

- Thresholds default from config/default-gates.yaml but are route configurable
- Any tuning patch must rerun E3 on affected scope

## Workflow

1. Fingerprint infrastructure, versions, configs and dataset.
2. Replay read/write mix at increasing concurrency with warmup.
3. Capture p50/p95/p99, throughput, error rate, CPU/IO/memory/network and connection-pool metrics.
4. Capture source/target plans for critical SQL.
5. Classify regressions: query, index, distribution, skew, lock, GC, network, pool or application.
6. Apply only evidence-backed tuning candidates through repair workflow.
7. Re-run to prove improvement and absence of behavioral regression.

## Mandatory tests

- Hot-key/skew workload
- Join-heavy query
- Sort/spill
- Large batch write
- Mixed OLTP+report
- Connection storm
- Lock contention
- Cold cache
- Failover during load when route requires HA

## Required evidence

- Benchmark manifest
- Raw metric files
- Plan snapshots
- Regression report
- E4 decision

## Fail-closed / escalation rules

- Do not compare dissimilar hardware without explicit normalization caveat.
- One microbenchmark cannot certify production performance.

## Definition of Done

- Actual implementation exists in the product repository; no stub-only completion.
- Required unit/integration fixtures execute in CI and include negative cases.
- Evidence artifacts conform to schemas/evidence.schema.json and reference real logs/results.
- No silent semantic fallback: unsupported or ambiguous cases are explicit.
- Documentation, config schema and route/version compatibility declarations are updated.
- The skill's release gate is reproducible from a clean checkout.
