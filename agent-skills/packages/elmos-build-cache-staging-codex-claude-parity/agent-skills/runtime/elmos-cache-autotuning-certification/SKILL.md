---
name: elmos-cache-autotuning-certification
description: Benchmark, tune, canary, and certify adaptive cache policies against representative ELMOS traces with multi-objective and worst-cohort gates.
version: 1.2.0
package: elmos-build-cache-staging-codex-claude-parity
phase: P6-optimization
dependencies: [elmos-learning-augmented-cache-control, elmos-dag-aware-cache-prefetch, elmos-cache-chaos-certification]
---

# Cache Autotuning and Production Certification

## Outcome

Turn cache-policy research into a repeatable production selection process that proves value on ELMOS workloads and blocks regressions in correctness, latency, fairness, or operational safety.

This is an implementation skill. The coding agent must inspect and modify the actual ELMOS repository, run verification, and provide evidence. Architecture prose or a simulator-only result is not completion.

## Use this skill when

- Implementing or changing SOTA/adaptive cache optimization in ELMOS.
- Executing phase `P6-optimization` of the cache/staging capability DAG.
- Diagnosing cache hit, avoided-work, storage, latency, policy-drift, prefetch, fairness, or cache-pollution problems.
- Dependency skills have passed: **elmos-learning-augmented-cache-control, elmos-dag-aware-cache-prefetch, elmos-cache-chaos-certification**.

## Required inputs

- Current ELMOS repository, architecture, and deployment profile.
- `manifest.json`, all dependency skills, and their fresh evidence.
- `docs/source-packages/elmos-sota-cache-optimization-spec.md`.
- Trace, policy, benchmark-report schemas and the SOTA acceptance matrix in this package.
- Representative privacy-reviewed ELMOS traces or an explicit statement that only synthetic pre-validation is possible.

## Produced artifacts

- Production implementation code, policy interfaces, and configuration.
- Trace schemas, benchmark fixtures, automated tests, and failure-injection coverage.
- Metrics, dashboards, policy decision records, and reproducible benchmark reports.
- Feature flags, safe fallback configuration, operator documentation, and rollout evidence.
- Machine-readable evidence linked to the implementation commit and trace fingerprint.

## Non-negotiable invariants

- A policy cannot be certified from synthetic traces alone.
- Baselines include LRU, SIEVE, S3-FIFO, and the currently deployed policy at equal capacity.
- The final test corpus is untouched by tuning and includes worst-case scans, bursts, large artifacts, multi-tenant contention, and drift transitions.
- Certification binds to exact policy code, model, configuration, trace-corpus fingerprint, hardware profile, and cache capacity.
- Any correctness, cross-tenant, corruption, recovery, or publication failure is an automatic rejection regardless of hit rate.

## Execution workflow

1. Inspect the existing ELMOS repository, current cache tiers, conversion DAG, artifact formats, orchestration, storage limits, and telemetry.
2. Load every dependency skill and verify its evidence is fresh and compatible with the current implementation commit.
3. Map the capability to concrete interfaces, migrations, policy modules, feature flags, tests, dashboards, rollout gates, and rollback paths.
4. Implement the smallest production-shaped vertical slice without putting learned or heuristic decisions on the correctness path.
5. Add deterministic replay, unit, integration, concurrency, drift, failure, and security tests as applicable.
6. Run the repository suite plus the SOTA cache acceptance cases and compare against fixed LRU, SIEVE, and S3-FIFO baselines.
7. Record exact commands, trace fingerprints, policy/model versions, metrics, output digests, regressions, and unresolved limitations.
8. Enable production write decisions only after shadow evaluation, canary gates, and automatic fallback have passed.

## Implementation tasks

1. Build a benchmark matrix across cache tiers, capacities, languages, framework conversions, repository sizes, edit classes, model providers, and network regimes.
2. Search bounded parameters using trace replay, then validate on time-separated holdouts and report Pareto frontiers for hit, bytes, avoided compute, tokens, critical path, overhead, and fairness.
3. Require a configurable minimum weighted-value improvement over the deployed baseline, no material worst-cohort regression, and no p95 decision/lookup SLO regression before canary.
4. Run shadow, read-only recommendation, canary tenant, progressive percentage, and full rollout phases with automatic rollback triggers.
5. Exercise cache restart, policy-state recovery, remote outage, trace loss, model unavailability, corrupted state, quota pressure, and adversarial scans.
6. Emit a signed `CachePolicyCertificate` and expire it when policy/model/config, workload regime, capacity, toolchain, or objective profile changes materially.

## Acceptance criteria

- Implementation exists in the ELMOS repository and follows its architectural conventions rather than creating a disconnected benchmark prototype.
- Cache correctness remains based on exact ActionKeys, immutable CAS objects, validation levels, tenancy, and provenance; policy selection only affects admission, placement, prefetch, retention, or eviction.
- Deterministic replay, unit, integration, concurrency, drift, and relevant failure-path tests pass.
- Every policy choice and learned-model decision is observable, versioned, explainable, and reversible.
- Fresh evidence records the source commit, exact commands, trace corpus fingerprint, platform, policy/model versions, results, confidence intervals where applicable, and known limitations.

Capability-specific acceptance also includes every invariant and task above, plus the relevant rows in `tests/acceptance/sota-cache-acceptance-matrix.md`.

## Evidence required

- Implementation commit or working-tree diff summary.
- Test commands and complete pass/fail counts.
- Trace corpus manifest, train/validation/test split, and privacy review.
- Per-policy object hit ratio, byte hit ratio, avoided-compute ratio, token-cost savings, critical-path savings, p95 decision overhead, and storage/network impact.
- Shadow/canary comparison, drift results, fallback exercise, and at least one controlled failure/recovery trace.
- Explicit blocker report instead of a false completion claim when a gate cannot be met.

## Anti-patterns

- Claiming one eviction policy is universally state of the art without workload replay.
- Optimizing raw hit count while increasing bytes transferred, model tokens, wall-clock time, or recomputation cost.
- Allowing a model, heuristic, vector similarity result, or prefetch prediction to bypass exact-key validation or provenance checks.
- Training and evaluating on the same trace window, leaking future events, or silently changing benchmark capacity.
- Switching policies on every request, causing oscillation, cache resets, or unbounded hot-path overhead.
- Caching secrets, raw prompts, source contents, or tenant-identifying payloads in trace features.
- Enabling an experimental policy without a fixed-policy fallback and rollback trigger.

## Done condition

The skill is done only when production code, policy/configuration state, automated tests, trace replay, shadow/canary evidence, telemetry, rollback controls, and fresh machine-readable evidence all exist and `./validate.sh` passes. A paper citation, architecture proposal, isolated simulator win, or successful compilation alone is not completion.
