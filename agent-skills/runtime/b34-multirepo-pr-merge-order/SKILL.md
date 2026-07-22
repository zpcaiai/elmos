---
name: b34-multirepo-pr-merge-order
description: "Generate coordinate and verify dependency-aware multi-repository pull requests with atomic change sets compatibility windows status checks approvals merge ordering partial-failure handling rollback and audit."
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

## Skill 1256: Multi-repository pull requests and merge ordering

## Use this skill when

- One migration change spans libraries, APIs, schemas, clients, services, and deployments in multiple repositories.
- PRs must merge in a safe order while preserving compatibility.
- Partial merges and rejected PRs need recovery.

## Domain-specific risks and invariants

- Independent PRs can temporarily break consumers or producers.
- Status checks tied to stale commits can produce false approvals.
- Mass force-push or auto-merge can bypass customer governance.

## Workflow

1. Create a change-set ID and map affected repositories, contracts, compatibility windows, owners, and dependency DAG.
2. Generate atomic commits and PRs with source baselines, recipe/model provenance, manifests, evidence, and rollback instructions.
3. Define merge phases such as expand, compatible producers/consumers, switch, and contract.
4. Bind status checks and approvals to exact commit SHAs.
5. Enforce Code Owners, branch protection, reviewer capacity, and no self-approval.
6. Handle rejected, delayed, superseded, and partially merged PRs with forward recovery or rollback.
7. Observe runtime compatibility before closing the change set.

## Required repository outputs

- Multi-repository change-set and PR DAG
- Per-PR evidence, status checks, approvals, merge conditions, and rollback
- Partial-merge simulation and recovery evidence

## Verification

- Validate topological order and compatibility windows.
- Change a commit after approval and verify checks invalidate.
- Simulate a mid-sequence failure and verify recovery.

## Stop and escalate when

- A critical repository or owner cannot participate.
- No compatibility window exists for the proposed order.
- Branch protection or approval requirements would need to be bypassed.

## Definition of done

- All PRs are traceable to one change set.
- Merge order preserves compatibility.
- Partial failure is recoverable without hidden manual state.
