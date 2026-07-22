---
name: b34-repository-portfolio-discovery
description: "Discover and maintain an evidence-backed enterprise repository portfolio across SCM organizations CMDB CI package registries runtime telemetry ownership permissions size language build criticality region and lifecycle without silently omitting inaccessible or shadow assets."
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

## Skill 1244: Enterprise repository portfolio discovery

## Use this skill when

- An organization needs a complete repository inventory before portfolio migration.
- SCM listings disagree with CMDB, CI, package registries, runtime telemetry, or billing.
- Shadow repositories, forks, mirrors, archived code, inaccessible assets, or missing owners must be classified.

## Domain-specific risks and invariants

- SCM APIs alone do not reveal runtime use, package consumers, direct database readers, or shadow automation.
- Cloning every repository without budgets or permission boundaries can create security and cost incidents.
- Inaccessible repositories must remain explicit unknowns rather than disappearing from coverage metrics.

## Workflow

1. Enumerate exact SCM organizations, groups, projects, repositories, default branches, baseline commits, permissions, archived status, forks, mirrors, and LFS/submodules.
2. Correlate CMDB, CI/CD, package registry, deployment, DNS, runtime, ownership, security classification, region, and cost evidence.
3. Fingerprint languages, build systems, generated sources, approximate LOC, repository size, activity, criticality, and lifecycle without executing untrusted code.
4. Deduplicate forks and mirrors while preserving legal, region, and deployment identities.
5. Assign owner or create an ownership obligation; record inaccessible, deleted, archived, and shadow assets.
6. Persist an immutable inventory snapshot and incremental change feed.
7. Validate critical coverage against independent enterprise sources and add holdout discovery cases.

## Required repository outputs

- Portfolio inventory snapshot with stable repository IDs and evidence references
- Unreachable, ownerless, shadow, duplicate, fork, mirror, and archived asset reports
- Incremental repository change feed and inventory coverage metrics

## Verification

- Compare inventory counts and critical assets with SCM, CMDB, CI/CD, package registry, and runtime sources.
- Re-run incremental discovery and prove stable IDs and no duplicate repository creation.
- Verify access boundaries and ensure no source content is exported contrary to policy.

## Stop and escalate when

- Repository enumeration requires credentials or scope not approved by the customer.
- Critical inventory sources materially disagree and no owner can resolve them.
- Discovery would execute repository code or clone restricted source without an approved runner.

## Definition of done

- Critical repository coverage and owner coverage meet policy.
- Every unknown or inaccessible repository is explicit and owned.
- Inventory snapshots and deltas are reproducible and tenant isolated.
