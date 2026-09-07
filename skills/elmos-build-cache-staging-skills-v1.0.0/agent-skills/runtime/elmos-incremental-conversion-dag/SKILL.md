---
name: elmos-incremental-conversion-dag
description: Model conversion as a fine-grained deterministic DAG that re-executes only impacted parse, analysis, IR, planning, generation, build, test, repair, and certification nodes.
version: 1.0.0
package: elmos-build-cache-staging-recovery
phase: P3-incremental
dependencies: [elmos-project-snapshot-merkle, elmos-cache-key-fingerprinting, elmos-semantic-interface-hashing, elmos-stage-contract-registry]
---

# Incremental Conversion DAG

## Outcome

Model conversion as a fine-grained deterministic DAG that re-executes only impacted parse, analysis, IR, planning, generation, build, test, repair, and certification nodes.

This is an implementation skill. The coding agent must inspect and modify the actual ELMOS repository, run verification, and provide evidence. Architecture prose alone is not completion.

## Use this skill when

- Implementing or changing this capability in ELMOS.
- Executing phase `P3-incremental` of the cache/staging capability DAG.
- Diagnosing correctness, recoverability, cache-hit, storage, or publication problems related to this capability.
- Dependency skills have passed: **elmos-project-snapshot-merkle, elmos-cache-key-fingerprinting, elmos-semantic-interface-hashing, elmos-stage-contract-registry**.

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

- Each node declares immutable inputs, outputs, side effects, resources, cache policy, and checkpoint boundary.
- Invalidation is graph-derived and explainable.
- Independent nodes may run concurrently, but shared logical outputs require explicit arbitration.
- Certification binds to fresh or still-valid evidence for the exact output tree.

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

1. Support repository, module, file, symbol, IR partition, generated file, compile target, and test-shard node granularities.
2. Build edges for imports, public interfaces, runtime behavior, schemas, routes, dataflow, framework adapters, and generated-file ownership.
3. Compute the minimal affected closure and cache lookup plan before scheduling.
4. Schedule by critical path, resource class, cache locality, and deterministic output ordering.
5. Persist plan versus actual execution and expose reasons for every executed, restored, skipped, and invalidated node.

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
