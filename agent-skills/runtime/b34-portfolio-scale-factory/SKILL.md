---
name: b34-portfolio-scale-factory
description: "Implement and certify an enterprise-scale migration portfolio pack spanning repository discovery dependency graphs work-unit partitioning distributed workflows runner fleets caches transfers campaigns pull requests recovery fairness budgets benchmarks forecasting and disaster replay."
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

## Skill 1243: Enterprise-scale portfolio and migration factory orchestrator

## Use this skill when

- A user asks to scale the migration platform from one repository or slice to hundreds or thousands of repositories.
- An existing implementation lacks portfolio inventory, work-unit partitioning, distributed scheduling, recovery, scale benchmarks, or cost evidence.
- Several Batch 34 domains must be coordinated into one production-shaped portfolio campaign.

## Domain-specific risks and invariants

- An incomplete repository inventory creates hidden dependencies and false completion.
- Unbounded fan-out, retries, concurrency, or artifact transfer can exhaust tenant and platform capacity.
- Scale claims without repeatable datasets, exact environments, holdout portfolios, and recovery evidence are not certification evidence.

## Workflow

1. Inspect Batch 20-33 contracts, SCM organizations, repository inventory, build systems, runner pools, caches, queues, budgets, telemetry, and prior evidence; create a portfolio gap inventory.
2. Confirm accountable portfolio, platform, security, data, SRE, finance, and migration owners plus one exact portfolio scope and three benchmark classes.
3. Scaffold the portfolio pack and implement incremental repository discovery before migration fan-out.
4. Build the typed dependency graph and immutable work-unit plan, then validate coverage, ownership, cycles, and critical edges.
5. Implement distributed semantic indexing, incremental graph updates, durable workflow sharding, runner fleet scheduling, content-addressed caching, and resumable transfer.
6. Implement one recipe campaign and one dependency-aware multi-repository pull-request wave with checkpoint and rollback.
7. Run fairness, budget, million-LOC, thousand-repository, mixed-language, and disaster-replay validations.
8. Run negative, holdout, and representative portfolios; write evidence and execute the conservative Batch 34 gate.

## Required repository outputs

- `portfolio-packs/<pack-key>/pack.json`, `support-matrix.json`, and `inventory/portfolio.json`
- Typed `graph/dependencies.json` and `work-units/plan.json` with stable IDs and source evidence
- Scale, campaign, scheduler, cache, transfer, budget, forecast, benchmark, DR, and control-tower artifacts
- Independent development, negative, holdout, and representative portfolio corpora
- `certification/{evidence.json,certification.json,gate-result.json,gate-report.md}`

## Verification

- Run all Batch 34 schema and graph/work-unit validators.
- Execute the exact benchmark environment with cold and warm runs, failure injection, checkpoint recovery, and cost capture.
- Verify holdout and representative portfolios without tuning partitioning, scheduling, cache, or thresholds from holdout results.
- Re-run the same portfolio from recorded manifests and compare outputs, costs, and side effects.

## Stop and escalate when

- No accountable owners, exact portfolio scope, representative repositories, or safe benchmark environment exists.
- Critical repositories, dependencies, or data boundaries remain unknown.
- The design depends on unbounded fan-out, non-idempotent tasks, shared mutable workspaces, or cross-tenant caches.
- Scale evidence is synthetic-only where representative production-shaped evidence is required.
- Critical fairness, budget, recovery, integrity, or tenant-isolation failures remain.

## Definition of done

- One production-shaped portfolio completes discovery, graphing, partitioning, distributed execution, caching, transfer, campaign PRs, recovery, benchmarks, forecasting, and DR replay with evidence.
- The million-LOC, thousand-repository, and mixed-language profiles meet approved thresholds without silent drops, starvation, corruption, or unapproved budget overrun.
- The conservative gate emits only the strongest status supported by actual evidence.
