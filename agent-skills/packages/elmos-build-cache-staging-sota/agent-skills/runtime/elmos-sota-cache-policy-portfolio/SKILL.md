---
name: elmos-sota-cache-policy-portfolio
description: Implement a deployable portfolio of SIEVE, S3-FIFO, W-TinyLFU, size-aware and cost-aware policies with modern adaptive candidates and safe fallbacks.
version: 1.1.0
package: elmos-build-cache-staging-sota
phase: P6-optimization
dependencies: [elmos-cache-trace-replay-simulator, elmos-content-addressable-storage, elmos-action-cache]
---

# SOTA Cache Policy Portfolio

## Outcome

Provide a common, production-grade policy interface and a strong policy portfolio instead of hard-coding LRU or assuming one algorithm dominates every ELMOS workload.

This is an implementation skill. The coding agent must inspect and modify the actual ELMOS repository, run verification, and provide evidence. Architecture prose or a simulator-only result is not completion.

## Use this skill when

- Implementing or changing SOTA/adaptive cache optimization in ELMOS.
- Executing phase `P6-optimization` of the cache/staging capability DAG.
- Diagnosing cache hit, avoided-work, storage, latency, policy-drift, prefetch, fairness, or cache-pollution problems.
- Dependency skills have passed: **elmos-cache-trace-replay-simulator, elmos-content-addressable-storage, elmos-action-cache**.

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

- Exact cache-key validity, object integrity, trust level, and tenant authorization are checked before any policy decision.
- Every tier has a bounded-overhead fixed-policy fallback.
- Policy implementations expose memory, CPU, lock-contention, admission, eviction, and churn counters.
- Active-run roots, checkpoints, published trees, pins, legal holds, and certification evidence are never evicted by a replacement policy.
- Experimental Merlin-, S4-FIFO-, 3L-Cache-, or SCION-inspired modes remain feature-flagged until independently reproduced on ELMOS traces.

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

1. Define a stable `CachePolicy` SPI for access, admission, victim selection, resize, snapshot/restore, protected roots, and decision explanations.
2. Implement and test SIEVE for high-concurrency scan-resistant caches; S3-FIFO for one-hit-heavy object workloads; W-TinyLFU for recency/frequency admission; size-aware TinyLFU for heterogeneous artifacts; and GDSF for frequency × recompute-value ÷ size decisions.
3. Add tier presets: W-TinyLFU for hot metadata, SIEVE/S3-FIFO for local CAS, size/value-aware policies for remote CAS, and no-evict protected staging/checkpoint sets.
4. Add conformance tests using identical traces, capacity, warm-up, object-size semantics, and admission accounting.
5. Add snapshot-compatible policy state so service restart does not destroy frequency/admission history unless explicitly configured.
6. Provide clean interfaces for learning-augmented parameter tuning without placing inference on the read-hit critical path.

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
