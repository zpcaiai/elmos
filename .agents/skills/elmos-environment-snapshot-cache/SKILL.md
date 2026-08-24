---
name: elmos-environment-snapshot-cache
description: Cache reproducible sandbox, toolchain, dependency, index, and setup state with precise invalidation so warm ELMOS tasks avoid repeated environment construction.
version: 1.2.0
package: elmos-build-cache-staging-codex-claude-parity
phase: P10-environment-affinity
dependencies: [elmos-sandbox-overlay-workspaces, elmos-native-build-cache-adapters, elmos-cache-security-provenance, elmos-cache-retention-gc]
---

# Environment Snapshot Cache

## Outcome

Provide Codex-class warm environment startup while preserving secret isolation, dependency correctness, and deterministic invalidation. This is an implementation skill. The coding agent must inspect and modify the actual ELMOS repository, run reproducible verification, and attach evidence. A design document, mocked counter, or isolated demo is not completion.

## Use this skill when

- Project tasks repeatedly install dependencies, provision SDKs, rebuild indexes, or initialize sandboxes.
- Warm-start latency is a major part of conversion/generation critical path.
- Implementing cache-locality routing or provider-independent task resume.

## Required inputs

- Base image, setup/maintenance scripts, lockfiles, package-manager state, compiler/SDK/tool digests, environment allowlist, secret references, workspace mount plan, and tenant policy.
- Native build-cache adapters, CAS, staging, security, and retention contracts.
- Environment snapshot schema and restore benchmark fixtures.

## Produced artifacts

- Canonical `EnvironmentSnapshotKey`, immutable snapshot manifest, chunked CAS layers, and restore verifier.
- Snapshot builder for base, toolchain, dependencies, generated indexes, and project warm state with explicit trust levels.
- Warm pool and restore-vs-rebuild decision engine.
- Secret-safe invalidation, vulnerability/age revocation, quotas, garbage collection, and audit events.
- Cold/warm startup benchmark and failure-recovery tests.

## Non-negotiable invariants

- Snapshot keys include every result-affecting base image, setup/maintenance script, lockfile, toolchain, SDK/compiler, platform, and approved environment input.
- Secret values are never serialized into reusable layers; secret identity/version changes invalidate affected snapshots according to policy.
- Restored files and layers are digest-verified before execution, and untrusted project snapshots never become globally trusted images.
- Writable task state remains isolated above immutable layers; no cross-tenant writable overlay reuse.
- Known vulnerable, revoked, corrupt, or policy-incompatible snapshots are quarantined even when they would improve hit rate.
- Restore is bypassed when verified rebuild is cheaper under current bandwidth/load conditions.

## Execution workflow

1. Profile cold setup into base-image pull, package resolution/download/install, compilation, indexing, setup scripts, and task-specific state.
2. Define canonical layer boundaries and precise invalidation dimensions.
3. Implement snapshot build, seal, CAS promotion, restore, verification, lease, and cleanup.
4. Integrate native package/build caches without embedding machine-specific absolute paths or secrets.
5. Add warm-pool admission and affinity signals, then benchmark restore versus rebuild across repository sizes and network regimes.
6. Canary by tenant/project trust class and exercise revocation, corruption, secret rotation, and dependency update.

## Implementation tasks

1. Create layered manifests for base runtime, language toolchains, dependency stores, compiled indexes, repository checkout, and optional task warm state.
2. Normalize setup and maintenance scripts, lockfiles, platform/architecture, package-manager configuration, compiler flags, and selected environment variables into the key.
3. Implement snapshot creation using copy-on-write/reflink/OCI-style layers where supported and portable tar/CAS fallback otherwise.
4. Add secret mount-after-restore, secret-reference fingerprinting, redaction scanning, and snapshot rejection on leaked secret patterns.
5. Implement vulnerability/policy revocation lists and mandatory revalidation after configured age or toolchain advisory.
6. Expose warm-pool state and cache-locality metadata to the affinity router.
7. Measure restore I/O, decompression, verification, setup avoided, write amplification, and net wall-clock/cost savings.
8. Add concurrency tests for multiple workers restoring the same snapshot and crash tests during build/promotion/restore.

## Acceptance criteria

- With unchanged environment inputs, environment snapshot hit rate is at least 95% on the parity corpus.
- Warm-start p95 is at least 80% lower than cold-start p95 for eligible scenarios, measured end to end and net of verification.
- Changing any declared lockfile, script, base image, compiler/SDK, platform, approved environment value, or secret version causes the expected invalidation.
- Secret scanners and tenant-isolation tests report zero reusable-layer leaks.
- Corrupted or revoked snapshots are never executed and automatically fall back to a clean rebuild.
- Restored builds/tests are behaviorally equivalent to clean-environment controls.

## Evidence required

- Snapshot key/spec, layer manifests, build/restore source, security scans, and invalidation matrix.
- Cold-versus-warm benchmark by project/language/platform, including p50/p95 and net bytes/cost.
- Secret rotation, corruption, revocation, concurrent restore, and clean-rebuild equivalence traces.
- Warm-pool/retention configuration and rollback exercise.

## Anti-patterns

- Caching an entire mutable home directory or task workspace without layer boundaries.
- Using only a lockfile hash while ignoring base image, setup script, compiler, platform, or environment.
- Baking secret values into snapshots or logs.
- Restoring unverified snapshots because local disk is trusted.
- Counting snapshot lookup as a hit when restore is bypassed or fails.

## Done condition

Completion requires precise environment keys, immutable layered snapshots, secure build/restore, warm pool, invalidation/revocation, equivalence and chaos tests, and measured 95% eligible hit plus 80% p95 warm-start improvement gates.
