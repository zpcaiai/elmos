---
name: elmos-reproducible-toolchain
description: Build immutable multi-language toolchain manifests/images, reproducible
  dependencies, signed provenance, caches, and warm runner pools.
version: 1.0.0
priority: P0
phase: G3
dependencies:
- elmos-content-addressed-cache
- elmos-identity-tenant-security
---

# Reproducible Toolchains, Dependency Environments, and Warm Pools

## Objective

Make baseline builds and generated projects repeatable across runners and time, while separating environment failures from source-code failures.

## Use this skill when

Use this skill when implementing, repairing, reviewing, validating, or productionizing the **Reproducible Toolchains, Dependency Environments, and Warm Pools** capability in an eLMOS repository. Invoke the program orchestrator first for work spanning multiple skills.

## Dependencies

- `elmos-content-addressed-cache`
- `elmos-identity-tenant-security`

Do not mark this skill complete until required dependency contracts are present and their blocking gates pass. A dependency can be implemented in the same change only when the plan preserves reviewable boundaries.

## Non-negotiable constraints

- Every production toolchain is identified by immutable image and component digests.
- Credentials are runtime-injected and never baked into images or caches.
- Targets are selected from compatibility evidence, not globally hard-coded.
- Nix may support certification but is not mandatory for every adapter.

## Required inputs

- Language/runtime compatibility profiles.
- Container build infrastructure.
- Private repositories and secret broker.
- Runner OS, architecture, and GPU inventory.

## Required outputs

- `Toolchain schema/registry.`
- `Layered signed images.`
- `Dependency snapshots and caches.`
- `Reproducibility reports.`
- `Warm-pool configuration.`

## Repository discovery

Before editing:

1. Locate `AGENTS.md`, `CLAUDE.md`, repository-local Skills, architecture decision records, manifests, schemas, migrations, and build commands.
2. Identify actual control-plane, workflow, runner, engine, web, database, object-store, policy, telemetry, and test modules; do not assume the reference layout exists.
3. Search for existing contracts and implementations before creating duplicates.
4. Record current behavior, known gaps, security boundaries, external side effects, and the exact validation commands that are available.
5. Create or update a durable implementation plan from `templates/IMPLEMENTATION-PLAN.yaml`.

## Execution workflow

1. Select the smallest dependency-resolved vertical slice.
2. Freeze input snapshots, schema/toolchain/policy versions, and rollback boundaries.
3. Implement contract/schema changes before consumers, using backward-compatible transitions.
4. Implement production behavior, authorization, idempotency, telemetry, audit, failure handling, tests, documentation, and runbooks together.
5. Execute focused tests, integration tests, race/failure tests, security tests, and clean-environment reproduction as applicable.
6. Save large outputs by digest; record commands, results, durations, cost, evidence, and residual risk.
7. Report autonomous **system wall-clock runtime** separately from human-equivalent engineering/review effort.
8. Never claim production completion from generated files or static validation alone.

## Implementation checklist

### Toolchain manifest

- [ ] `ELMOS-TOOL-001` Record ID, version, image digest, OS, architecture, runtime, compiler, build tools, libraries, adapter, policy, dependency-cache scope, locale, timezone, network, random seed, CPU, GPU, and determinism.
- [ ] `ELMOS-TOOL-002` Include full toolchain digest in every Action Key and Evidence Pack.
- [ ] `ELMOS-TOOL-003` Maintain compatibility matrix rather than one target.
- [ ] `ELMOS-TOOL-004` Version/deprecate without mutating history.
- [ ] `ELMOS-TOOL-005` Reject execution when runner lacks required capability.
### Layered images

- [ ] `ELMOS-TOOL-006` Layer base OS, language runtime, compiler/build tools, framework pack, eLMOS adapter, and project dependencies.
- [ ] `ELMOS-TOOL-007` Use BuildKit-equivalent cache mounts for Maven, Gradle, npm/pnpm/yarn, NuGet, pip/uv, Cargo, Go modules, and others.
- [ ] `ELMOS-TOOL-008` Run non-root and minimize packages/capabilities.
- [ ] `ELMOS-TOOL-009` Use .dockerignore and immutable base digests.
- [ ] `ELMOS-TOOL-010` Generate SBOM, vulnerability/license report, provenance, and signature.
- [ ] `ELMOS-TOOL-011` Prevent secrets, source, and private URLs in image layers.
### Language/platform matrix

- [ ] `ELMOS-TOOL-012` Provide governed Java 8, 11, 17, and 21 environments.
- [ ] `ELMOS-TOOL-013` Provide Kotlin, .NET/MSBuild, Python legacy/modern/GPU, Node/TypeScript, Go, Rust, C/C++/LLVM, PHP, Dart/Flutter, Windows, macOS/Swift, and notebook environments as supported paths require.
- [ ] `ELMOS-TOOL-014` Record supported project ranges and incompatibilities.
- [ ] `ELMOS-TOOL-015` For GPU record model, compute capability, driver, runtime libraries, device count, precision, and determinism.
- [ ] `ELMOS-TOOL-016` Keep unsupported legacy runtimes isolated and offline by default.
### Dependency reproduction

- [ ] `ELMOS-TOOL-017` Verify Maven/Gradle wrappers and checksums.
- [ ] `ELMOS-TOOL-018` Verify npm/pnpm/yarn, Cargo, Python, NuGet, Go, Dart, and other lock files.
- [ ] `ELMOS-TOOL-019` Without lock files capture repository, version, checksum, license, and resolution graph.
- [ ] `ELMOS-TOOL-020` Broker private credentials per task.
- [ ] `ELMOS-TOOL-021` Isolate tenant-private caches and separate verified public cache.
- [ ] `ELMOS-TOOL-022` Support offline dependency bundles.
- [ ] `ELMOS-TOOL-023` Detect dependency confusion, unpinned/mutable artifacts, and repository fallback.
### Reproducibility and classification

- [ ] `ELMOS-TOOL-024` Run the same snapshot/toolchain on two clean runners and compare declared outputs.
- [ ] `ELMOS-TOOL-025` Normalize or document timestamps, archive ordering, random IDs, paths, and nondeterminism.
- [ ] `ELMOS-TOOL-026` Classify failures as environment, source, private repository, network, policy, capacity, or unknown.
- [ ] `ELMOS-TOOL-027` Detect build scripts modifying source.
- [ ] `ELMOS-TOOL-028` Emit reproducibility report and mark nonreproducible output LIMITED/BLOCKED.
### Warm pools

- [ ] `ELMOS-TOOL-029` Maintain toolchain-specific warm pools based on demand.
- [ ] `ELMOS-TOOL-030` Scale from queue age, cache locality, startup cost, and forecast.
- [ ] `ELMOS-TOOL-031` Drain/rotate safely on image, policy, or certificate changes.
- [ ] `ELMOS-TOOL-032` Measure cold start, warm start, dependency resolution, and cache hit.

## Required artifacts

At minimum, produce or update:

- Versioned contracts and schemas.
- Database migrations and compatibility/rollback notes where state changes.
- Production implementation with explicit authorization, idempotency, retries, cancellation, and failure classification as applicable.
- Unit, integration, end-to-end, race/failure, and security tests appropriate to risk.
- OpenTelemetry instrumentation, operational metrics, alerts, and runbooks for production components.
- Audit/evidence records with immutable input and output digests.
- Updated architecture and operational documentation.
- Task report based on `templates/TASK-REPORT.md`.

## Validation

- [ ] Build every production toolchain twice and compare image/provenance.
- [ ] Run representative fixtures on two clean runners.
- [ ] Seed a credential and prove it is absent from image history, SBOM, logs, and artifacts.
- [ ] Change a toolchain component and invalidate old action results.
- [ ] Test unsupported versions and repository outages with correct classification.

Run repository-native format, lint, typecheck, unit, integration, packaging, and security commands. Also run the package validators when Skill content or schemas change:

```bash
python3 scripts/validate_skill_bundle.py
python3 scripts/validate_json_schemas.py
python3 -m unittest discover -s tests -v
```

## Definition of done

- [ ] Every execution records complete immutable toolchain identity.
- [ ] Representative builds are reproducible or explicitly classified.
- [ ] No secrets are baked into images/caches.
- [ ] Toolchain changes invalidate affected caches and can roll back by digest.

Additionally:

- [ ] No placeholder, TODO-only, mock-only, or documentation-only implementation is counted as production completion.
- [ ] All modified public contracts are versioned and compatibility-tested.
- [ ] All side effects are idempotent or reconciled.
- [ ] Critical actions are authorized, audited, and observable.
- [ ] Evidence identifies exact source, toolchain, rule/model/policy, commands, results, and residual risk.
- [ ] Static bundle validation is described accurately as structural validation only.

## Failure handling and handoff

Classify failures as `ENVIRONMENT`, `DEPENDENCY`, `CODE`, `POLICY`, `SECURITY`, `DATA`, `CAPACITY`, `PROVIDER`, or `UNKNOWN`. Preserve successful checkpoints. Put ambiguous side effects in `UNKNOWN_RESULT`/`MANUAL_RECOVERY`; reconcile before retrying. Update the implementation plan with status, commit, commands, measured wall-clock duration, cost, evidence digest, blockers, and the next dependency-resolved task.
