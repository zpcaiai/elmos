---
name: b34-monorepo-partition-work-units
description: "Partition very large monorepos and repository clusters into immutable dependency-aware work units based on build targets bounded contexts ownership criticality testability and resource profiles rather than arbitrary line counts."
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

## Skill 1245: Large monorepo partitioning and work-unit design

## Use this skill when

- A monorepo or tightly coupled repository cluster is too large for one migration task.
- Work must be split without breaking atomic build, schema, release, or business boundaries.
- A scalable campaign needs stable work-unit IDs, dependencies, estimates, and gates.

## Domain-specific risks and invariants

- Arbitrary file or LOC partitioning creates cross-unit churn and invalid partial builds.
- Cycles, generated code, shared schemas, and common release trains can make a proposed split unsafe.
- Overlapping ownership or mutable work-unit definitions make retries and cost attribution unreliable.

## Workflow

1. Parse build targets, modules, bounded contexts, ownership, deployment units, test suites, schemas, and release boundaries.
2. Construct candidate partitions using dependency cuts, criticality, locality, historical change coupling, and resource profiles.
3. Identify strongly connected components and choose merge, adapter, shared-platform, or explicit blocked strategies.
4. Assign stable work-unit IDs, immutable baselines, owners, repositories/modules, dependencies, entry/exit gates, and estimates.
5. Measure cross-unit edge density, overlap, critical path, and expected cache reuse.
6. Validate each unit with isolated discovery/build where possible and compare the partition plan against a whole-workspace baseline.
7. Add negative cases for cyclic, generated, shared-schema, and ownership-conflict partitions.

## Required repository outputs

- `work-units/plan.json` with stable IDs and exact baselines
- Partition rationale, cycle decisions, overlap report, and build/test evidence
- Resource profiles and dependency order for the scheduler

## Verification

- Validate all work-unit dependencies and repository/module references.
- Build representative units independently or document explicit shared prerequisites.
- Verify no source file or owned symbol is silently assigned to conflicting mutable units.

## Stop and escalate when

- A critical strongly connected component cannot be split or migrated as one bounded unit.
- Ownership, release, or data boundaries are unknown.
- Partitioning would require unsupported cross-unit mutable state or unsafe duplicated side effects.

## Definition of done

- All critical scope is covered by valid work units.
- Dependencies and cycles are explicit and schedulable.
- Independent units can retry or recover without corrupting neighboring work.
