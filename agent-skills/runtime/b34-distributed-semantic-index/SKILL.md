---
name: b34-distributed-semantic-index
description: "Implement a tenant-isolated distributed semantic index for repositories symbols types calls contracts diagnostics recipes and evidence with stable document identities versioning sharding freshness access control compaction and reproducible queries."
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

## Skill 1247: Distributed semantic index and query service

## Use this skill when

- Semantic analysis must scale beyond one process or repository.
- Portfolio queries need symbols, calls, contracts, source maps, and evidence across shards.
- Index freshness, ACLs, compaction, and rebuild behavior require production controls.

## Domain-specific risks and invariants

- Index shards can leak source or metadata across tenants if authorization is not enforced at query time.
- Stale index entries can route impact analysis or repair to deleted symbols.
- Non-deterministic tokenization or unstable IDs can invalidate caches and graph deltas.

## Workflow

1. Define the index schema, stable document IDs, tenant/project scope, repository baseline, analyzer version, and source classification.
2. Choose shard and partition keys that balance locality, scale, and failure isolation.
3. Implement ingestion from PSP/UIR/FCM, graph, diagnostics, recipes, tests, and evidence using idempotent upserts and tombstones.
4. Implement query APIs for symbol lookup, references, callers, contracts, similarity, and source-target trace while enforcing ACL and data-egress policy.
5. Implement freshness watermarks, backpressure, compaction, reindex, and schema migration.
6. Compare incremental indexing against full rebuild on representative portfolios.
7. Run cross-tenant, stale-entry, shard-loss, and replay negative tests.

## Required repository outputs

- Index schema and version manifest
- Shard map, ingestion checkpoints, freshness metrics, and ACL policy
- Query contract tests, reindex plan, and full-vs-incremental evidence

## Verification

- Run deterministic query fixtures on cold and warm indexes.
- Verify cross-tenant and unauthorized repository queries are denied.
- Drop or corrupt a shard in an isolated environment and validate rebuild/replay.

## Stop and escalate when

- Stable identities or tenant scoping cannot be guaranteed.
- Required source content would be replicated to an unapproved region or index.
- Incremental and full rebuild results materially diverge.

## Definition of done

- Index coverage, source-map coverage, and freshness meet policy.
- No cross-tenant result or critical stale entry remains.
- Rebuild and schema upgrade are evidenced.
