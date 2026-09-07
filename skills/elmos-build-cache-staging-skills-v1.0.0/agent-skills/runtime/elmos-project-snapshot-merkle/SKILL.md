---
name: elmos-project-snapshot-merkle
description: Create deterministic repository snapshots and Merkle trees so small changes invalidate only affected modules, files, symbols, and downstream actions.
version: 1.0.0
package: elmos-build-cache-staging-recovery
phase: P1-local-cache
dependencies: [elmos-cache-system-architecture]
---

# Project Snapshot and Merkle Tree

## Outcome

Create deterministic repository snapshots and Merkle trees so small changes invalidate only affected modules, files, symbols, and downstream actions.

This is an implementation skill. The coding agent must inspect and modify the actual ELMOS repository, run verification, and provide evidence. Architecture prose alone is not completion.

## Use this skill when

- Implementing or changing this capability in ELMOS.
- Executing phase `P1-local-cache` of the cache/staging capability DAG.
- Diagnosing correctness, recoverability, cache-hit, storage, or publication problems related to this capability.
- Dependency skills have passed: **elmos-cache-system-architecture**.

## Required inputs

- Current ELMOS repository and architecture.
- `manifest.json` and all dependency skills.
- `docs/source-packages/elmos-build-cache-staging-spec.md`.
- Relevant schemas, SQL, OpenAPI, templates, and acceptance tests under this package.
- Exact source/target language profile and deployment profile when the implementation is adapter-specific.

## Produced artifacts

- Production implementation code and interfaces.
- Database migrations or storage adapters where required.
- Automated tests, fixtures, and failure-injection coverage.
- Configuration, operator/developer documentation, and rollout flags.
- Machine-readable evidence linked to the implementation commit.

## Non-negotiable invariants

- Raw-byte, normalized-syntax, and semantic digests are recorded separately where applicable.
- Absolute paths, host names, file access times, and unrelated UI state never affect snapshot identity.
- Symlink, executable-bit, case-sensitivity, line-ending, submodule, and ignore policies are explicit and versioned.
- Snapshot traversal never follows an unapproved link outside the repository.

## Execution workflow

1. Inspect the existing repository. Identify current conversion stages, storage, task orchestration, workspaces, build adapters, manifests, and release flow.
2. Load dependency skills and verify their evidence is fresh and compatible.
3. Map this skill to concrete files, interfaces, migrations, tests, metrics, feature flags, and rollback.
4. Implement the smallest end-to-end vertical slice, including failure handling and idempotency.
5. Add unit, integration, deterministic replay, security, and fault-injection tests as applicable.
6. Run the repository test suite plus the package acceptance cases that cover this capability.
7. Record exact commands, output digests, metrics, trace references, and unresolved limitations.
8. Update the Stage Contract Registry and capability status only after required gates pass.

## Implementation tasks

1. Classify source, generated, dependency, vendor, binary, secret, and ignored files.
2. Compute a fast pre-hash and canonical SHA-256 digest, then build sorted directory and module Merkle nodes.
3. Record lockfile, dependency, submodule, platform metadata, and normalization-policy roots independently.
4. Compare snapshots to emit changed files, renames, changed public interfaces, and candidate impacted modules.
5. Create cross-platform golden fixtures for macOS, Linux, and Windows path semantics.

## Acceptance criteria

- Implementation exists in the ELMOS repository and follows the existing architectural conventions rather than creating a disconnected prototype.
- Unit, integration, deterministic replay, and relevant failure-path tests pass.
- All produced artifacts, state transitions, digests, and validation levels are machine-readable and auditable.
- The capability is observable with structured logs, metrics, and traces without leaking source or secrets.
- Fresh evidence records the source commit, exact commands, platform, toolchain profile, results, and known limitations.

Capability-specific acceptance also includes every invariant and task above, plus the relevant rows in `tests/acceptance/cache-staging-acceptance-matrix.md`.

## Evidence required

- Implementation commit or working-tree diff summary.
- Test commands and complete pass/fail counts.
- At least one successful execution trace and one controlled failure/recovery trace.
- Relevant manifests, ActionKeys, artifact/tree digests, staged-file states, checkpoint references, or certification references.
- Performance and resource measurements when this skill affects latency, storage, model tokens, or compilation.
- Explicit blocker report instead of a false completion claim when a gate cannot be met.

## Anti-patterns

- Treating file existence, cache presence, or a happy-path demo as proof of completion.
- Writing generated content directly into the source tree or live final output.
- Adding unversioned schemas, mutable aliases, undeclared environment dependencies, or hidden temporary storage.
- Using Redis or an in-memory queue as the only recoverable truth.
- Bypassing validation, provenance, tenancy, or evidence requirements to improve apparent hit rate.
- Silently overwriting user content, conflicting cache entries, or staged outputs.

## Done condition

The skill is done only when production code, migrations/adapters, automated tests, failure-path verification, telemetry, documentation, rollout controls, and fresh machine-readable evidence all exist and `./validate.sh` passes. A proposal, partial code generation, or successful compilation alone is not completion.
