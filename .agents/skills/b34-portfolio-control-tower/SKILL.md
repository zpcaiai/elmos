---
name: b34-portfolio-control-tower
description: Implement a portfolio control tower with evidence-backed read models for inventory progress quality dependencies risk capacity cost forecasts campaigns pull requests incidents recovery and customer outcomes.
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

## Skill 1260: Portfolio migration control tower

## Use this skill when

- Executives, migration leaders, engineers, and customers need a common portfolio view.
- Data must drill from portfolio status to work unit, task, artifact, PR, test, and evidence.
- Read-model freshness and data quality need explicit governance.

## Domain-specific risks and invariants

- Vanity metrics such as generated LOC or task count can hide quality and business risk.
- Averages can hide critical failed repositories or tenants.
- Stale or manually overridden dashboards can mislead go/no-go decisions.

## Workflow

1. Define personas, decisions, metric definitions, source systems, freshness, confidentiality, and drill-down paths.
2. Build read models for inventory coverage, work-unit state, graph blockers, build/test/behavior gates, campaigns, PRs, capacity, queue age, cost, forecast, incidents, DR, and retirement.
3. Expose data quality, stale data, unknown scope, and evidence links.
4. Implement tenant/project access control and portfolio aggregation without leaking customer data.
5. Add alerts and decision workflows for critical blockers, budget, SLO, starvation, and recovery.
6. Validate dashboard values against source records and sampled raw evidence.
7. Run stale-data, missing-data, and cross-tenant negative tests.

## Required repository outputs

- Metric catalog and control-tower read-model schemas
- Portfolio, campaign, repository, work-unit, cost, risk, and forecast views
- Freshness, reconciliation, access-control, and evidence drill-down tests

## Verification

- Reconcile dashboard metrics against authoritative records.
- Verify critical red states cannot be hidden by aggregation.
- Attempt unauthorized portfolio drill-down and verify denial.

## Stop and escalate when

- Metric definitions or authoritative sources are unresolved.
- Critical data is stale beyond decision SLO.
- Aggregation would expose tenant-confidential data.

## Definition of done

- Control tower supports real decisions with current evidence.
- Unknown and stale scope is explicit.
- Users can drill to source evidence without cross-tenant leakage.
