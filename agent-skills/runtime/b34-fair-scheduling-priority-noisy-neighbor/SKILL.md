---
name: b34-fair-scheduling-priority-noisy-neighbor
description: "Implement weighted fair scheduling priority classes aging quotas deadlines bounded preemption per-tenant concurrency and noisy-neighbor controls across workflow queues runner fleets models storage and transfer."
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

## Skill 1258: Fair scheduling, priority, and noisy-neighbor control

## Use this skill when

- Multiple customers, projects, and campaigns compete for shared capacity.
- Urgent hotfixes and production blockers need priority without starving normal work.
- One tenant or workload can exhaust runners, queues, models, storage, or bandwidth.

## Domain-specific risks and invariants

- Strict priority can starve lower classes indefinitely.
- Unbounded preemption can waste work or corrupt non-preemptible phases.
- Fairness at one queue can be defeated by downstream bottlenecks.

## Workflow

1. Define tenant/project weights, priority classes, quotas, concurrency, deadlines, aging, burst, and reserved capacity.
2. Classify tasks as preemptible, checkpointable, non-preemptible, or dedicated.
3. Implement weighted fair queueing across workflow, runner, model, transfer, and storage admission.
4. Apply backpressure and admission control before overload.
5. Expose scheduling reasons, queue age, service share, throttling, and deadline risk.
6. Run steady, burst, urgent, low-priority, dedicated, and malicious/noisy-neighbor scenarios.
7. Tune from development data, then verify on independent holdout portfolios.

## Required repository outputs

- Fairness and priority policy
- Admission, quota, preemption, and backpressure configuration
- Service-share, starvation, deadline, and noisy-neighbor evidence

## Verification

- Verify every active class receives minimum service within policy.
- Generate a tenant burst and confirm other tenants remain within SLO.
- Preempt checkpointable work and validate safe resume.

## Stop and escalate when

- Policy would starve a class or violate a contractual dedicated capacity.
- Preemption is requested for a non-checkpointable activity.
- Downstream limits cannot enforce the same tenant and priority boundaries.

## Definition of done

- Fairness SLOs pass.
- Urgent work meets policy without indefinite starvation.
- No tenant can exceed approved shared-resource impact.
