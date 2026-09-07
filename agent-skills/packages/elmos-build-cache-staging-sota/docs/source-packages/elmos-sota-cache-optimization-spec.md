# ELMOS SOTA Cache Optimization Specification

Version: 1.1.0  
Status: implementation contract  
Scope: conversion, project generation, intermediate artifacts, Action Cache, CAS, staging, checkpoints, compilation, testing, repair, and certification.

## 1. Why ELMOS needs a policy portfolio

ELMOS cache objects are not homogeneous web objects. A 20 KB symbol table, a 5 MB Semantic IR partition, a 600 MB native build output, and a model-generated patch can have radically different storage size, transfer time, recomputation cost, validation value, reuse probability, and critical-path impact. Therefore a single global LRU, LFU, or even a single recent research policy is not an acceptable architecture.

The cache subsystem SHALL separate:

1. **Correctness plane** — exact ActionKey, immutable CAS digest, schema version, validation level, provenance, tenant authorization, and trust namespace.
2. **Data plane** — bounded-overhead lookup, admission, promotion, materialization, and eviction.
3. **Control plane** — trace analysis, policy selection, parameter tuning, drift detection, capacity allocation, shadow evaluation, and certification.

A control-plane mistake may reduce performance; it must never make an invalid artifact reusable.

## 2. Optimization objectives

ELMOS SHALL report at least the following metrics per tier, stage, tenant cohort, language pair, project-size cohort, and policy epoch:

- Object Hit Ratio (OHR)
- Byte Hit Ratio (BHR)
- Action Hit Ratio (AHR)
- Avoided Compute Ratio (ACR)
- Avoided Model Token Ratio (AMTR)
- Critical Path Saved Ratio (CPSR)
- Net Wall-Clock Saved
- Net Monetary Cost Saved
- Restore-to-Recompute Ratio
- Prefetch Precision and Coverage
- Eviction Churn and Write Amplification
- p50/p95/p99 lookup and policy-decision overhead
- Fair-share and quota violations
- False-reuse count, which MUST remain zero

The default multi-objective value function is:

```text
ExpectedCacheValue =
    P(reuse within horizon)
  × (recompute_wall_ms
     + model_token_cost
     + compiler_cpu_cost
     + critical_path_penalty
     + retained_validation_value)
  - storage_cost
  - expected_restore_cost
  - network_cost
  - cache_pollution_cost
  - trust_risk_penalty
```

Weights are versioned by objective profile. Development, CI, conversion-as-a-service, and certification retention may use different profiles.

## 3. Tiered default policies

### L0 — in-process metadata and tiny manifests

Default: W-TinyLFU.  
Fallback: SIEVE.  
Reason: compact frequency-based admission prevents one-hit metadata scans from displacing repeatedly used entries while maintaining low latency.

### L1 — local CAS and Action Cache materializations

Default candidate set: S3-FIFO and SIEVE.  
Adaptive candidates: Merlin-style pattern characterization and S4-FIFO-style bounded parameter tuning.  
Reason: local caches experience monorepo scans, one-hit build artifacts, bursts, and high concurrency.

### L2 — remote shared CAS

Default candidate set: size-aware TinyLFU and GDSF, with S3-FIFO/SIEVE as strong baselines.  
Objective: byte hit, avoided recomputation, network egress, and multi-tenant fairness rather than object count alone.

### Active run, staging, checkpoint, and publication roots

Policy: protected-set semantics plus DAG next-use ranking.  
No generic eviction algorithm may delete reachable active state.

### Semantic candidate reuse

Policy: candidate-only retrieval. Similarity may rank historical plans, mappings, repairs, and tests, but exact regeneration, compilation, tests, behavior comparison, and provenance gates are still required before direct reuse.

## 4. Strong fixed-policy portfolio

ELMOS SHALL implement the following behind one `CachePolicy` SPI:

- **SIEVE** — visited-bit FIFO-like eviction with low hit-path mutation and strong scan resistance.
- **S3-FIFO** — small FIFO admission filter, main FIFO, and ghost history to quickly demote one-hit objects.
- **W-TinyLFU** — recency window plus approximate frequency admission using a Doorkeeper and Count-Min-style sketch.
- **Size-aware TinyLFU** — compares frequency/value density when objects have heterogeneous size.
- **GDSF** — combines frequency, retrieval/recompute value, size, and cache-age inflation.
- **LRU** — retained only as a baseline and emergency compatibility fallback, not the assumed optimal default.

Every implementation SHALL support bounded metadata, capacity resize, snapshot/restore or intentional reset, protected roots, deterministic replay, and per-decision reason codes.

## 5. Adaptive policy orchestration

A compact off-path workload fingerprint SHALL include:

- one-hit ratio;
- reuse-distance p50/p90/p99;
- object-size p50/p90/p99 and coefficient of variation;
- correlation between size, frequency, and recomputation value;
- stage mix and validation-level mix;
- cacheable ratio;
- sequential scan and burst indicators;
- remote latency/bandwidth regime;
- tenant concentration and fairness pressure;
- known-future ratio from the planned DAG.

The initial selector SHALL be deterministic and rule-based. A learned selector may later choose among the fixed-policy experts. Policy changes occur only at safe epochs with minimum dwell time and hysteresis. Low confidence, OOD, drift, missing telemetry, or control-plane failure falls back to a pinned strong baseline.

## 6. Learning-augmented control

The preferred production pattern is learning-augmented heuristics:

- keep data-plane operations simple;
- asynchronously collect cache-level features;
- infer a small bounded parameter vector or select a policy epoch;
- apply only after validation and at a safe boundary;
- retain full fallback and rollback.

An S4-FIFO-style controller may tune S3-FIFO parameters. Merlin-style characterization may be evaluated for heterogeneous workloads. 3L-Cache-style learned victim selection is experimental until its overhead, reproducibility, and worst-cohort behavior pass ELMOS gates.

A generative language model MAY explain a structured policy choice but MUST NOT make the authoritative eviction or correctness decision.

## 7. DAG-aware future reuse

Unlike a generic object cache, ELMOS usually knows the upcoming conversion DAG. The scheduler SHALL build a next-use index and use it to:

- protect artifacts needed soon;
- prefetch remote artifacts before their consuming node becomes runnable;
- place nodes on workers already holding immutable inputs;
- cancel prefetch after branch resolution;
- bypass restore when deterministic recomputation is cheaper;
- rank victims by next-use distance, cost density, and protection state.

Known DAG future information must be distinguished from historical prediction in metrics and evidence.

## 8. Trace and replay methodology

Trace events contain hashes and numerical metadata only. No raw source, prompt, generated output, secret, or direct tenant identity may be recorded.

Required corpus partitions:

- warm-up;
- tuning/train;
- validation;
- final untouched time-separated test;
- drift transition;
- adversarial scans and bursts;
- multi-tenant contention;
- remote outage and latency shift.

Every comparison uses equal cache capacity, identical request sequence, identical object-size interpretation, identical protected roots, and explicit warm-up semantics.

## 9. Rollout gates

1. Simulator-only validation.
2. Production request mirroring to shadow policies.
3. Read-only policy recommendations.
4. Canary tenant/project cohorts.
5. Progressive shared-cache write decisions.
6. Full rollout with automatic rollback.

A configurable certification profile SHALL require a positive weighted-value improvement over the deployed baseline, no material worst-cohort regression, no p95 lookup/decision SLO regression, no fairness regression, and zero correctness/security failures.

## 10. Failure and fallback

Fallback triggers include:

- model unavailable or signature invalid;
- feature schema mismatch;
- OOD or drift threshold exceeded;
- policy decision p95 above budget;
- hit/value regression beyond guardrail;
- cache churn or write amplification beyond guardrail;
- remote outage or bandwidth collapse;
- trace capture loss;
- policy-state corruption;
- tenant fairness violation.

Fallback is immediate and does not require rebuilding ActionKeys or CAS data. Policy-state migration is explicit and auditable.

## 11. Required production evidence

A cache-policy certificate binds:

- ELMOS commit;
- policy implementation digest;
- model and feature schema digest;
- complete configuration digest;
- trace-corpus digest and split;
- hardware/network profile;
- capacity and protected-root rules;
- objective weights;
- baseline and candidate reports;
- shadow/canary results;
- rollback exercise;
- expiration conditions.
