---
name: b34-shared-library-bom-platform-dependency
description: Analyze and govern shared libraries BOMs parent builds platform dependencies generated clients version alignment forks and consumer rollout across a repository portfolio.
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

## Skill 1249: Shared library, BOM, and platform dependency analysis

## Use this skill when

- A shared library, parent POM, Gradle platform, NuGet props, Python package, npm workspace, or generated client affects many repositories.
- A portfolio campaign must coordinate version alignment and consumer migration.
- Forked internal libraries and unmanaged copies must be consolidated or governed.

## Domain-specific risks and invariants

- A central upgrade can break hundreds of consumers.
- Version ranges and transitive overrides can hide the actual runtime dependency.
- Forked copies may contain customer-specific or security-sensitive changes.

## Workflow

1. Discover shared package producers, BOMs/platforms, parent builds, generated clients, forks, mirrors, and vendored copies.
2. Resolve actual versions from lockfiles, dependency resolution, runtime manifests, and artifact registries.
3. Build consumer sets and classify compatibility, release cadence, owner, criticality, and migration readiness.
4. Detect divergent forks, conflicting constraints, unsupported versions, and dependency diamonds.
5. Design staged platform/BOM upgrades, compatibility windows, adapters, and rollback.
6. Execute a canary consumer cohort, then dependency-aware rollout with contract and behavior tests.
7. Record adoption, failures, exceptions, and retirement of old versions.

## Required repository outputs

- Shared dependency inventory and consumer graph
- Version-alignment and fork-divergence reports
- Staged rollout plan and compatibility evidence

## Verification

- Resolve dependencies in representative consumers using exact lockfiles and registries.
- Run canary and holdout consumer builds/tests.
- Verify old versions are not retired while active critical consumers remain.

## Stop and escalate when

- Package provenance or ownership is unknown.
- A critical consumer cannot be tested or identified.
- A proposed upgrade requires unapproved breaking behavior or security regression.

## Definition of done

- Critical consumers are known and version-aligned or explicitly excepted.
- Canary and holdout consumers pass.
- Old platform versions have a safe retirement plan.
