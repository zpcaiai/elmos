---
name: b34-incremental-graph-impact
description: Implement incremental dependency and semantic graph updates with tombstones invalidation stable graph versions impact propagation full-rebuild equivalence and conservative affected-work selection.
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

## Skill 1248: Incremental graph computation and impact updates

## Use this skill when

- Repository changes should update portfolio graphs without full recomputation.
- Affected work units, tests, campaigns, consumers, and PR ordering must be recalculated.
- Graph updates must survive duplicate, out-of-order, or replayed events.

## Domain-specific risks and invariants

- Missing tombstones leave deleted symbols and edges active.
- Under-propagated impact can skip critical tests or consumers.
- Out-of-order events can regress graph versions or resurrect stale nodes.

## Workflow

1. Define graph-change events, ordering, idempotency keys, version rules, and replay semantics.
2. Compute node/edge additions, changes, deletions, and confidence updates from source deltas and runtime evidence.
3. Apply tombstones and invalidate dependent index, cache, work-unit, test, and campaign results.
4. Propagate impact conservatively through build, runtime, data, security, and public-contract edges.
5. Persist graph checkpoints and watermarks.
6. Compare incremental results with scheduled full rebuilds on development and holdout portfolios.
7. Inject duplicate, out-of-order, deletion, cycle, and partial-failure events.

## Required repository outputs

- Graph delta and checkpoint artifacts
- Affected work-unit/test/consumer/campaign results
- Incremental-vs-full equivalence evidence and drift report

## Verification

- Replay the same event stream twice and verify identical graph versions.
- Compare impacted sets with a full rebuild and owner-reviewed critical samples.
- Verify deleted nodes cannot reappear without a newer valid source event.

## Stop and escalate when

- Event ordering or repository baselines are ambiguous.
- Impact propagation excludes a critical edge without approved rationale.
- Incremental/full divergence remains on P0 cases.

## Definition of done

- Incremental updates are idempotent and replayable.
- P0 impacted sets match the certified full computation.
- Graph checkpoints recover after interruption.
