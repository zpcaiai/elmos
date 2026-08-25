---
name: elmos-dag-aware-cache-prefetch
description: Exploit the known ELMOS conversion DAG to predict next use, protect imminent artifacts, prefetch selectively, and place work near cached state.
version: 1.2.0
package: elmos-build-cache-staging-codex-claude-parity
phase: P6-optimization
dependencies: [elmos-sota-cache-policy-portfolio, elmos-incremental-conversion-dag, elmos-remote-shared-cache, elmos-project-generation-file-staging]
---

# DAG-Aware Future-Reuse Prefetch and Placement

## Outcome

Use information already available in the planned conversion DAG to reduce avoidable misses, network waits, and critical-path stalls more reliably than generic history-only prediction.

This is an implementation skill. The coding agent must inspect and modify the actual ELMOS repository, run verification, and provide evidence. Architecture prose or a simulator-only result is not completion.

## Use this skill when

- Implementing or changing SOTA/adaptive cache optimization in ELMOS.
- Executing phase `P6-optimization` of the cache/staging capability DAG.
- Diagnosing cache hit, avoided-work, storage, latency, policy-drift, prefetch, fairness, or cache-pollution problems.
- Dependency skills have passed: **elmos-sota-cache-policy-portfolio, elmos-incremental-conversion-dag, elmos-remote-shared-cache, elmos-project-generation-file-staging**.

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

- Only declared DAG dependencies or versioned historical probabilities may drive prefetch; hidden file discovery is forbidden.
- Prefetch never changes ActionKey correctness, stage ordering, side effects, or publication semantics.
- An object is prefetched only when expected restore benefit exceeds transfer, decompression, and cache-pollution cost.
- Bandwidth, concurrency, memory, disk, and tenant budgets are enforced before issuing prefetches.
- Wrong predictions are measurable and trigger throttling or disablement.

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

1. Build a next-use index from the scheduled DAG, including branch probability, critical-path position, artifact size, restore latency, recompute cost, and validation level.
2. Protect artifacts used within a configurable future horizon and rank other victims by next-use distance, cost density, and current pressure.
3. Prefetch remote CAS objects in earliest-beneficial-use order with deduplication, cancellation, backpressure, and transfer coalescing.
4. Add cache-locality-aware worker scheduling that prefers workers already holding required immutable inputs without violating fairness or critical-path priority.
5. Implement restore-versus-recompute bypass when network/download/decompression cost exceeds deterministic recomputation.
6. Measure prefetch precision, coverage, late-prefetch rate, wasted bytes, critical-path savings, and pollution-induced misses.

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
