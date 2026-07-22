---
name: b34-cross-repo-dependency-graph
description: "Build and validate a versioned cross-repository dependency call data event release and runtime graph with stable nodes evidence confidence criticality and consumer relationships for portfolio impact and ordering."
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

## Skill 1246: Cross-repository dependency and version graph

## Use this skill when

- Portfolio migration ordering depends on cross-repository build, package, API, event, data, or deployment relationships.
- Hidden consumers, shared databases, runtime calls, or version constraints must be found.
- Impact analysis and multi-repository PR ordering require a trusted graph.

## Domain-specific risks and invariants

- Manifest dependencies alone miss runtime calls, direct database access, scripts, and manual file flows.
- Version ranges and generated clients can create compatibility edges not visible in source imports.
- A stale or low-confidence graph can produce destructive migration ordering.

## Workflow

1. Create stable graph nodes for repositories, modules, packages, services, APIs, events, databases, schemas, jobs, and deployment units.
2. Ingest edges from build manifests, lockfiles, package registries, code analysis, runtime traces, API gateways, brokers, databases, CI/CD, and deployment manifests.
3. Record edge kind, direction, version constraint, criticality, confidence, evidence, and observation time.
4. Resolve package producers and consumers, API clients, event producers/consumers, direct data readers/writers, and release dependencies.
5. Detect cycles, incompatible version constraints, hidden critical consumers, and orphan nodes.
6. Version the graph and support graph-delta queries.
7. Validate selected critical paths against owners and runtime evidence.

## Required repository outputs

- `graph/dependencies.json` and graph version manifest
- Cycle, hidden-consumer, version-conflict, orphan, and low-confidence reports
- Query fixtures for impact, critical path, and consumer lookup

## Verification

- Run graph reference, uniqueness, and edge-evidence validation.
- Compare critical edges against runtime and owner-confirmed samples.
- Verify graph-version replay produces the same node and edge identities.

## Stop and escalate when

- Critical nodes cannot be assigned stable identity.
- Data or runtime evidence cannot be accessed within policy.
- A critical edge remains contradictory with no owner decision.

## Definition of done

- Critical dependency coverage meets policy.
- Unknown critical edges and orphan critical nodes are zero.
- The graph supports deterministic impact and ordering queries.
