---
name: b34-multilanguage-workspace-build-graph
description: "Model and execute multi-language workspaces and mixed build graphs across Maven Gradle MSBuild Python npm pnpm yarn Bazel and generated code with exact toolchains dependency order and reproducible outputs."
---

## Operating mode

Work directly in the repository. Inspect existing Batch 20-33 contracts, repository inventories, graph/index services, workflow histories, runner fleets, caches, artifact stores, SCM integrations, CI/CD, budgets, telemetry, incidents, and evidence before editing. Implement the smallest production-shaped portfolio or scale slice that satisfies this skill; do not stop at architecture notes when executable discovery, typed contracts, distributed processing, recovery, benchmarks, and evidence can be added.

Read these shared contracts first:

- `../../../docs/batch34/IMPLEMENTATION_CONTRACT.md`
- `../../../docs/batch34/QUALITY_GATES.md`
- `../../../docs/batch34/REPOSITORY_LAYOUT.md`
- `../../../docs/batch34/PORTFOLIO_MODEL.md`
- `../../../docs/batch34/SHARDING_AND_IDEMPOTENCY.md`
- `../../../docs/batch34/SCHEDULING_FAIRNESS.md`
- `../../../docs/batch34/CACHE_AND_TRANSFER_POLICY.md`
- `../../../docs/batch34/BENCHMARK_SPEC.md`
- `../../../docs/batch34/DR_AND_REPLAY_POLICY.md`
- `../../../docs/batch34/SECURITY_AND_DATA_BOUNDARIES.md`

Use the supplied helpers where applicable:

- `python3 scripts/batch34/scaffold_portfolio_pack.py ...`
- `python3 scripts/batch34/validate_portfolio_pack.py ...`
- `python3 scripts/batch34/validate_dependency_graph.py ...`
- `python3 scripts/batch34/validate_work_units.py ...`
- `python3 scripts/batch34/run_portfolio_gate.py ...`

## Global constraints

- Treat every portfolio pack as an exact tenant, SCM scope, region, inventory snapshot, toolchain, scheduler, and benchmark tuple. A materially different portfolio or execution policy requires a new version or pack.
- Discover repositories and runtime consumers from multiple evidence sources. Do not treat a single SCM listing or CMDB export as complete.
- Use typed Portfolio Inventory, Dependency Graph, Work Unit Plan, Scale Profile, Campaign Plan, and DR Replay contracts. Do not implement scale behavior as ad hoc scripts or unbounded shell fan-out.
- All distributed activities must be idempotent or compensated, checkpointed, bounded, tenant isolated, and replayable. Persist commit tokens for external effects.
- Use stable IDs and immutable baselines for repositories, graph nodes, work units, artifacts, campaigns, and benchmark datasets.
- Enforce hard placement, data-region, attestation, source-egress, and tenant constraints before cache affinity, cost, or speed preferences.
- Content-addressed reuse requires complete input manifests, digest/signature verification, provenance, and explicit tenant/trust policy. Never reuse ambiguous or untrusted artifacts.
- Keep development, negative, holdout, and representative portfolio corpora physically separate. Do not tune thresholds, partitioning, scheduling, or cache policy from holdout results.
- Fix systemic defects in discovery, graphing, partitioning, indexing, workflows, schedulers, recipes, or manifests rather than patching hundreds of repositories independently.
- No scale claim may silently exclude failed, inaccessible, unsupported, or over-budget repositories. Unknown scope remains visible in all metrics.
- Protect customer branch rules, source code, artifacts, budgets, and data boundaries. Never force merge, broaden permissions, or relax security to improve throughput.
- Run narrow tests first, then scale, failure, holdout, representative portfolio, and conservative Batch 34 gate checks before release claims.

## Skill 1250: Multi-language workspace and mixed build systems

## Use this skill when

- A monorepo contains Java, C#, Python, JavaScript/TypeScript, generated code, native helpers, or multiple build tools.
- Cross-language generation and packaging order must be preserved.
- One migration campaign must run a composite build and test graph.

## Domain-specific risks and invariants

- Independent build tools may disagree on source roots, outputs, lockfiles, or lifecycle.
- Generated code order and toolchain drift can create non-reproducible builds.
- Generic shell execution without typed steps can hide side effects and credentials.

## Workflow

1. Discover exact toolchains, wrappers, build roots, workspaces, source sets, generators, package managers, registries, caches, and CI entrypoints.
2. Emit a typed composite build graph with inputs, outputs, dependencies, side effects, secrets, resource profiles, and idempotency.
3. Lock tool and plugin versions and capture environment/container digests.
4. Implement isolated build adapters for each certified toolchain.
5. Coordinate generated code, package publication, cross-language contracts, and test ordering.
6. Run cold and warm composite builds and compare outputs.
7. Add negative cases for missing generators, stale lockfiles, cyclic build dependencies, and mixed runtime versions.

## Required repository outputs

- Workspace manifest and typed build DAG
- Toolchain lock and environment manifests
- Cold/warm build evidence, generated-source provenance, and failure classification

## Verification

- Run exact source and target composite builds.
- Verify content digests and dependency order.
- Rebuild in a fresh runner and compare outputs.

## Stop and escalate when

- A required tool or script has unknown side effects.
- Toolchain or private registry versions cannot be locked.
- Cross-language cycles cannot be represented or isolated safely.

## Definition of done

- Composite build is reproducible.
- All generated outputs have provenance.
- Cross-language test and package order is correct.
