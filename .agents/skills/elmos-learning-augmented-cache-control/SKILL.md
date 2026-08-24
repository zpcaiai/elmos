---
name: elmos-learning-augmented-cache-control
description: Add S4-FIFO-style asynchronous parameter learning and optional low-overhead learned eviction experiments without putting ML on cache correctness paths.
version: 1.2.0
package: elmos-build-cache-staging-codex-claude-parity
phase: P6-optimization
dependencies: [elmos-adaptive-cache-policy-orchestrator, elmos-cache-security-provenance, elmos-cache-trace-replay-simulator]
---

# Learning-Augmented Cache Control Plane

## Outcome

Introduce a safe learning-augmented control plane that tunes simple high-throughput policies using trace-derived features while preserving interpretable decisions, bounded overhead, and immediate fallback.

This is an implementation skill. The coding agent must inspect and modify the actual ELMOS repository, run verification, and provide evidence. Architecture prose or a simulator-only result is not completion.

## Use this skill when

- Implementing or changing SOTA/adaptive cache optimization in ELMOS.
- Executing phase `P6-optimization` of the cache/staging capability DAG.
- Diagnosing cache hit, avoided-work, storage, latency, policy-drift, prefetch, fairness, or cache-pollution problems.
- Dependency skills have passed: **elmos-adaptive-cache-policy-orchestrator, elmos-cache-security-provenance, elmos-cache-trace-replay-simulator**.

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

- The data plane remains a simple deterministic cache policy; model inference only changes bounded policy parameters or selects a policy epoch.
- Models, training data, feature definitions, normalization, objectives, and thresholds are versioned and signed.
- Raw source, prompt, generated code, secret, and tenant identity content is excluded from features.
- OOD detection, drift alarms, confidence floors, shadow mode, canary rollout, and fixed-policy fallback are mandatory.
- Online self-modification of model code or unreviewed auto-training deployment is forbidden.

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

1. Implement S4-FIFO-style learning-augmented parameter tuning: collect cache-level features asynchronously, predict bounded S3-FIFO parameters, and apply them only at safe epochs.
2. Add optional 3L-Cache-style low-overhead learned candidate evaluation in simulator/shadow mode, with bidirectional sampling and controlled retraining cadence.
3. Keep feature extraction and inference off the hot path; enforce p95 decision and memory budgets.
4. Add model registry, data lineage, reproducible training, holdout evaluation, calibration, drift/OOD detection, rollback, and deletion procedures.
5. Generate human-readable rationales from structured feature/parameter contributions; do not use a generative model to make the actual cache decision.
6. Red-team poisoning, tenant-skew attacks, adversarial scans, model rollback, stale-feature behavior, and telemetry loss.

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
