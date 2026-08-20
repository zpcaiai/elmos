---
name: elmos-cache-observability-performance
description: Instrument cache lookup, staging, promotion, recovery, GC, and publication; then tune hit rate and restore economics without weakening correctness.
version: 1.1.0
package: elmos-build-cache-staging-sota
phase: P6-assurance
dependencies: [elmos-action-cache, elmos-project-generation-file-staging, elmos-run-journal-state-machine, elmos-remote-shared-cache, elmos-incremental-conversion-dag]
---

# Cache Observability and Performance

## Outcome

Instrument cache lookup, staging, promotion, recovery, GC, and publication; then tune hit rate and restore economics without weakening correctness.

This is an implementation skill. The coding agent must inspect and modify the actual ELMOS repository, run verification, and provide evidence. Architecture prose alone is not completion.

## Use this skill when

- Implementing or changing this capability in ELMOS.
- Executing phase `P6-assurance` of the cache/staging capability DAG.
- Diagnosing correctness, recoverability, cache-hit, storage, or publication problems related to this capability.
- Dependency skills have passed: **elmos-action-cache, elmos-project-generation-file-staging, elmos-run-journal-state-machine, elmos-remote-shared-cache, elmos-incremental-conversion-dag**.

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

- Telemetry does not log source code, secrets, tokens, or raw prompts by default.
- Every run, node, ActionKey, artifact, staged file, checkpoint, and lease is correlatable.
- Hit rate is reported by stage and avoided work, not as one global vanity metric.
- Semantic similarity reuse remains candidate-only until fresh validation.

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

1. Emit OpenTelemetry spans for lookup, materialize, execute, write, seal, promote, checkpoint, resume, upload, publish, and GC.
2. Measure local/remote/partial hits, bytes deduplicated, CPU/time/compiler/model-token savings, restore latency, miss reasons, stale leases, corruption, and nondeterminism.
3. Build benchmarks for identical rerun, formatting-only, private-body, public-interface, schema, rule-pack, toolchain, lockfile, prompt/model, and remote-outage changes.
4. Tune DAG granularity, local LRU, compression, chunk size, prefetch, concurrency, locality scheduling, and recompute-versus-restore bypass.
5. Add SLOs and regression gates for p95 lookup, workspace allocation, seal/promotion, checkpoint/resume, no-change reuse, and small-change reuse.

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
