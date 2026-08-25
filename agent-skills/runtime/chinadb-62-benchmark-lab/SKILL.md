---
name: chinadb-62-benchmark-lab
description: "Use when ELMOS must follow the ChinaDB commercial database-migration specification for Database Migration Benchmark Lab. Keep exact directed route and version semantics, require real evidence, and fail closed on unsupported behavior."
metadata:
  source_package: "chinadb-commercial-migration-skills"
  source_version: "1.0.0"
  source_directory: "62-benchmark-lab"
  source_path: "skills/62-benchmark-lab/SKILL.md"
  source_sha256: "sha256:082cf6c63053050f2f27c4618afa345075323fdb58b38a82dd11b938d7dccd00"
  normalized_namespace: "chinadb-commercial-migration-v1"
  implementation_state: "SPEC_ONLY"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
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

## Repository Integration Boundary

- Provenance is pinned to `chinadb-commercial-migration-skills` version `1.0.0`, source Skill `62-benchmark-lab`, and the SHA-256 digest in frontmatter.
- Installation normalizes an invocable specification only; it does not implement a converter, adapter, data mover, verifier, repairer, cutover, or certification workflow.
- Repository state is `SPEC_ONLY`; implementation is `false`, evidence is empty / `NOT_RUN`, and production certification is `NOT_CERTIFIED`.
- Every database route remains directional and exact to engine version, edition, provider, mode, driver, charset, collation, time zone, extension, and workload scope.
- SQL and procedural transformations require typed semantic IR and real source/target execution; parser-only, regex-only, generated, synthetic, or self-verified output is not runtime proof.
- Unsupported, lossy, ambiguous, partial, unknown, or unreconciled semantics fail closed and must remain explicit.
- Customer or production data writes require a separately authorized workflow; use disposable, cloned, masked, or synthetic data by default.
- Only the applicable conservative Batch 31 gate may raise database migration readiness, and independent external evidence is still required for certification.
