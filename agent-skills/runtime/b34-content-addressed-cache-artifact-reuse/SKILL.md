---
name: b34-content-addressed-cache-artifact-reuse
description: "Implement tenant-aware content-addressed caches and immutable artifact reuse keyed by complete inputs toolchains policies environments and permissions with poisoning defense eviction garbage collection and correctness proofs."
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

## Skill 1253: Content-addressed cache and incremental artifact reuse

## Use this skill when

- Portfolio performance depends on reusing parse, index, build, test, package, and transformation outputs.
- Caches must remain correct across repositories, toolchains, profiles, regions, and tenants.
- Storage cost and garbage collection need explicit governance.

## Domain-specific risks and invariants

- Incomplete cache keys can return stale or semantically incompatible outputs.
- Cross-tenant cache sharing can leak proprietary code or metadata.
- Untrusted artifacts can poison future builds.

## Workflow

1. Define artifact types, canonical input manifests, digests, environment/toolchain/profile/policy keys, tenant scope, trust level, and provenance.
2. Implement immutable blobs, metadata indexes, write-once publication, signature/digest verification, and negative-cache policy.
3. Define safe reuse classes: same run, same tenant, signed public, or prohibited.
4. Implement cache lookup, partial reuse, invalidation, TTL, quota, eviction, reachability-based garbage collection, and replication.
5. Detect poisoning, collision, tampered metadata, stale policy, and unsupported toolchain reuse.
6. Compare cached and uncached outputs on development and holdout portfolios.
7. Measure hit rate, latency, storage, egress, and cost without weakening correctness.

## Required repository outputs

- Cache key specification and trust policy
- CAS metadata, provenance, eviction/GC plans, and replication manifest
- Cold/warm equivalence and poisoning negative-test evidence

## Verification

- Verify digest/signature on read and write.
- Run the same workloads cold and warm and compare outputs exactly or canonically.
- Attempt cross-tenant, stale-toolchain, and tampered-artifact reuse.

## Stop and escalate when

- A cache key omits an input that can affect output.
- Artifact trust or tenant ownership is ambiguous.
- Cached and uncached P0 results diverge.

## Definition of done

- Cache reuse is correct, isolated, and measurable.
- Poisoning and unauthorized reuse are blocked.
- Eviction and GC do not remove reachable evidence.
