# Reproducible Toolchains, Dependency Environments, and Warm Pools

- Skill: `elmos-reproducible-toolchain`
- Priority: `P0`
- Phase: `G3`
- Dependencies: `elmos-content-addressed-cache`, `elmos-identity-tenant-security`

## Objective

Make baseline builds and generated projects repeatable across runners and time, while separating environment failures from source-code failures.

## Task groups

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

## Validation

- [ ] Build every production toolchain twice and compare image/provenance.
- [ ] Run representative fixtures on two clean runners.
- [ ] Seed a credential and prove it is absent from image history, SBOM, logs, and artifacts.
- [ ] Change a toolchain component and invalidate old action results.
- [ ] Test unsupported versions and repository outages with correct classification.

## Exit gate

- [ ] Every execution records complete immutable toolchain identity.
- [ ] Representative builds are reproducible or explicitly classified.
- [ ] No secrets are baked into images/caches.
- [ ] Toolchain changes invalidate affected caches and can roll back by digest.
