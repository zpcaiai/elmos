---
name: b34-portfolio-budget-cost-guardrails
description: "Implement hierarchical portfolio campaign repository work-unit runner model storage transfer and human-review budgets with estimates reservations actuals forecasts hard stops approvals and cost-per-verified-workload."
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

## Skill 1259: Portfolio budgets and cost guardrails

## Use this skill when

- Large migrations need predictable spend and per-customer/project attribution.
- Runner, model, storage, transfer, CI, and human review costs must be controlled.
- Campaigns need hard and soft budgets with approved extension.

## Domain-specific risks and invariants

- Unbounded retries or large artifacts can cause runaway cost.
- Shared infrastructure can hide cross-tenant cost and subsidy.
- Optimizing cost without quality or security gates can produce false savings.

## Workflow

1. Define cost taxonomy and hierarchy from portfolio to campaign, repository, work unit, task, model call, artifact, transfer, and human review.
2. Implement estimate, reservation, accrued, actual, forecast, variance, and currency/time rules.
3. Set soft alerts, hard stops, emergency reserves, and approval workflows.
4. Attribute shared costs using explicit drivers and preserve unallocated amounts.
5. Integrate budgets with scheduler admission, workflow retry, model routing, retention, and transfer.
6. Calculate cost per verified migrated workload and rework cost.
7. Run overrun, retry storm, large transfer, model fallback, and budget-extension tests.

## Required repository outputs

- Budget hierarchy, cost taxonomy, allocation rules, and approval policy
- Meter events, ledger, forecast, variance, and unit-economics reports
- Hard-stop, extension, reconciliation, and no-double-count evidence

## Verification

- Reconcile sampled provider bills and internal meters.
- Trigger soft and hard thresholds in an isolated run.
- Verify quality/security gates cannot be bypassed to save cost.

## Stop and escalate when

- Required cost sources or currency treatment are unavailable.
- A hard stop would leave a non-checkpointable destructive action incomplete.
- Cost allocation would expose another tenant or double count spend.

## Definition of done

- Portfolio and campaign spend are visible and bounded.
- Unapproved overruns are zero.
- Cost per verified workload is reproducible.
