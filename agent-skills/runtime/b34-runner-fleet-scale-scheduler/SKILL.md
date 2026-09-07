---
name: b34-runner-fleet-scale-scheduler
description: "Implement a large tenant-isolated runner fleet scheduler using attestation capabilities region data policy resource profiles cache affinity leases autoscaling drain and recovery."
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

## Skill 1252: Runner fleet large-scale scheduling

## Use this skill when

- Thousands of repository or work-unit jobs need safe placement across private and platform runners.
- Jobs require exact language, build, region, network, model, cache, or attestation capabilities.
- Fleet capacity and upgrades must not lose work or cross tenant boundaries.

## Domain-specific risks and invariants

- Capability mismatch can produce false failures or data-policy violations.
- Oversubscription can cause thrashing and nondeterministic build failures.
- Cache affinity can conflict with fairness, region, or security requirements.

## Workflow

1. Inventory runner pools, identities, attestation, capabilities, regions, network profiles, source-egress policies, resource limits, versions, and costs.
2. Define job requirements and hard placement constraints before preferences.
3. Implement queue-to-runner matching, leases, heartbeats, reservation, cache affinity, anti-affinity, and bounded overcommit.
4. Implement autoscaling, warm pools, drain, rolling upgrade, quarantine, revocation, and failure recovery.
5. Enforce tenant and project isolation and region/data policy.
6. Capture scheduling reasons, wait time, utilization, failure, and cost.
7. Run burst, steady-state, private-runner loss, upgrade, and noisy-neighbor tests.

## Required repository outputs

- Fleet and capability manifests
- Scheduler policy, lease records, placement explanations, and capacity metrics
- Autoscale, drain, upgrade, failure, and tenant-isolation evidence

## Verification

- Schedule mixed capability workloads and verify all hard constraints.
- Remove runners during active jobs and validate lease recovery.
- Attempt cross-tenant and wrong-region placement and verify denial.

## Stop and escalate when

- Required attestation, region, network, or toolchain capacity is unavailable.
- Scheduler would relax hard security or data constraints.
- Oversubscription or queue growth cannot be bounded.

## Definition of done

- Placement is correct and explainable.
- Fleet scales and upgrades safely.
- No cross-tenant or policy-invalid job runs.
