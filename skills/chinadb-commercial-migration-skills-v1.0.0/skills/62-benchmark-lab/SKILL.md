# Database Migration Benchmark Lab

- **Skill ID:** `62-benchmark-lab`
- **Version:** `1.0.0`
- **Category:** quality/performance
- **Implementation status:** specification only until repository evidence proves otherwise

## Objective

Provide reproducible OLTP, batch and analytical benchmark scenarios for route comparison and tuning without claiming equivalence from synthetic benchmarks alone.

## Inputs

- Ephemeral source/target environments
- Dataset generators
- Route SLO profiles
- Hardware/container metadata

## Required outputs

- Benchmark scenarios
- Dataset snapshots/fingerprints
- Baseline ranges
- Regression dashboards

## Implementation modules / repository contract

- bench/datasets.py
- bench/scenarios.py
- bench/runner.py
- bench/report.py

## Workflow

1. Provide small CI smoke and large scheduled benchmark profiles.
2. Include read-heavy, write-heavy, mixed, batch, join/aggregation, hotspot/skew and failover workloads.
3. Record infrastructure and database config.
4. Integrate with E4 but keep application production workload evidence distinct.

## Mandatory tests

- Scale-up curves
- Hotspot/skew
- Failover under load
- Long transactions
- Batch+OLTP interference

## Required evidence

- Benchmark manifests
- Raw metrics
- Trend reports

## Definition of Done

- Actual implementation exists in the product repository; no stub-only completion.
- Required unit/integration fixtures execute in CI and include negative cases.
- Evidence artifacts conform to schemas/evidence.schema.json and reference real logs/results.
- No silent semantic fallback: unsupported or ambiguous cases are explicit.
- Documentation, config schema and route/version compatibility declarations are updated.
- The skill's release gate is reproducible from a clean checkout.
