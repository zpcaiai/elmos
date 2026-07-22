---
name: b34-portfolio-capacity-duration-forecast
description: "Forecast portfolio migration capacity duration cost and completion risk from actual work-unit features queueing resource profiles historical throughput dependencies and uncertainty with continuous calibration."
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

## Skill 1262: Portfolio capacity and duration forecasting

## Use this skill when

- Portfolio leaders need credible dates, staffing, runner capacity, and budget forecasts.
- Different languages, frameworks, repository shapes, risk, and dependency critical paths affect duration.
- Forecasts must update as actual work arrives.

## Domain-specific risks and invariants

- Single-point estimates create false certainty.
- Using LOC alone ignores dependencies, build time, test complexity, review, and customer delay.
- Training on incomplete or leakage-prone data can bias customer commitments.

## Workflow

1. Define forecast targets, features, cohorts, actuals, censored work, external dependencies, and confidence intervals.
2. Use inventory, work units, graph critical path, historical stage durations, failure rates, cache, runner capacity, human review, and customer wait time.
3. Build baseline deterministic and statistical/queueing models before advanced predictors.
4. Produce P50/P80/P95 duration, capacity, cost, bottleneck, and scenario outputs.
5. Backtest on completed portfolios and calibrate prediction intervals.
6. Track forecast revisions and explain major drivers.
7. Use holdout portfolios and prevent customer-private data leakage.

## Required repository outputs

- Forecast feature and model manifest
- Portfolio and wave forecasts with confidence intervals and bottlenecks
- Backtest, calibration, drift, and scenario evidence

## Verification

- Compare forecasts with completed work and report error by cohort.
- Verify interval coverage, not only average error.
- Run sensitivity for runner loss, review capacity, failure rate, and scope growth.

## Stop and escalate when

- Historical actuals or feature definitions are unreliable.
- Forecast would expose one customer to another or overfit holdout data.
- Management requests an unsupported precise date without uncertainty.

## Definition of done

- Forecasts are calibrated and explainable.
- Capacity and budget scenarios are actionable.
- Accuracy and interval coverage meet the approved profile.
