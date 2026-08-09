---
name: b34-recipe-campaign-orchestrator
description: Execute large-scale recipe campaigns across repository cohorts using exact scope dry runs canaries dependency ordering budgets approvals exceptions pull requests rollback and outcome evidence.
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

## Skill 1255: Large-scale recipe campaign management

## Use this skill when

- A certified recipe or platform upgrade must be applied across many repositories.
- Repository cohorts need canary, phased rollout, exception, and rollback.
- Campaign progress, quality, cost, and consumer compatibility require control.

## Domain-specific risks and invariants

- A recipe that succeeds in one repository can fail across versions, frameworks, or custom extensions.
- Mass PR generation can overload reviewers and CI.
- Partial rollout can leave incompatible producers, consumers, or shared libraries.

## Workflow

1. Define campaign key, immutable recipe set, exact inventory snapshot, inclusion/exclusion rules, cohorts, owners, dependencies, budgets, gates, and rollback.
2. Run assessment and dry-run across the scope; classify unsupported patterns and required prerequisites.
3. Select canary repositories representing risk and diversity.
4. Execute canary with build, test, behavior, security, and cost checks.
5. Expand through dependency-aware cohorts with bounded concurrency and reviewer capacity.
6. Track failures, exceptions, waivers, PR status, adoption, and rollback.
7. Run holdout campaign and final representative portfolio checks.

## Required repository outputs

- `campaigns/<campaign>/plan.json` and immutable recipe digest
- Cohort, canary, exception, budget, PR, and rollback records
- Campaign outcome, failure taxonomy, adoption, and evidence

## Verification

- Validate campaign scope against the inventory snapshot.
- Run dry-run and canary before broad rollout.
- Verify rollback on at least one safe campaign cohort.

## Stop and escalate when

- Recipe certification does not cover the selected versions or frameworks.
- Reviewer, CI, runner, or budget capacity cannot support the rollout.
- Critical dependency ordering or rollback is unresolved.

## Definition of done

- Campaign completes within gates and budget.
- Unsupported repositories remain explicit and owned.
- No silent regression or unreviewed mass merge occurs.
