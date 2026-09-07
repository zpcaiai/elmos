---
name: b34-scale-benchmark-suite
description: "Build and run reproducible million-line thousand-repository and mixed-language scale benchmarks with exact datasets environments cold and warm runs failure injection latency throughput quality cost and cleanup evidence."
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

## Skill 1261: Million-LOC, thousand-repository, and mixed-language scale benchmarks

## Use this skill when

- The platform needs evidence for large monorepos, portfolio scale, or mixed-language workspaces.
- Capacity, SLO, cache, queue, and cost assumptions need repeatable measurement.
- Release certification requires holdout and representative scale results.

## Domain-specific risks and invariants

- Small synthetic fixtures can hide metadata, dependency, permission, and runtime complexity.
- Warm-cache results alone can misrepresent first-run customer experience.
- A benchmark that skips failed repositories or quality gates is invalid.

## Workflow

1. Define exact benchmark classes, dataset provenance, permissions, repository shapes, LOC counting, languages, build systems, dependency density, artifact sizes, and critical journeys.
2. Lock hardware, runner images, regions, service versions, quotas, policies, and cost rates.
3. Run cold and warm discovery, indexing, graph, work-unit, workflow, build/test, artifact, campaign, PR, and control-tower paths.
4. Capture latency percentiles, throughput, queue age, utilization, cache hit rate, errors, quality gates, cost, and cleanup.
5. Inject runner loss, queue backlog, shard failure, artifact interruption, and control-plane restart.
6. Repeat runs and calculate variance.
7. Run independent holdout and at least one representative customer-shaped portfolio.

## Required repository outputs

- Scale profile, dataset manifest, environment digest, and benchmark plan
- Raw benchmark results, traces, cost, failures, cleanup, and statistical summary
- Cold/warm, failure, holdout, and representative portfolio evidence

## Verification

- Re-run the benchmark from the recorded manifest.
- Verify all repositories and quality gates are counted, including failures.
- Check cleanup and provider bills after the run.

## Stop and escalate when

- Dataset license, provenance, or permission is unclear.
- Environment or quota cannot be locked.
- Metrics exclude failed work or silently reduce scope.

## Definition of done

- All three scale classes meet approved thresholds.
- Results are reproducible within variance limits.
- No silent drop, corruption, starvation, or unapproved overrun occurs.
