---
name: b34-portfolio-dr-replay
description: Implement portfolio-level disaster recovery and deterministic replay for inventory graphs indexes workflow state queues leases caches artifacts manifests campaigns pull requests budgets and audit without duplicate external effects.
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

## Skill 1263: Portfolio disaster recovery and task replay

## Use this skill when

- A region, database, queue, index, artifact store, or workflow control plane can fail during a large campaign.
- Portfolio state must recover within RPO/RTO and resume without redoing successful work.
- Disaster tests must include external effects such as PRs and artifact publication.

## Domain-specific risks and invariants

- Restoring metadata without artifacts or indexes can create inconsistent state.
- Replaying workflows can duplicate PRs, messages, charges, or destructive actions.
- Caches and derived indexes must not become authoritative during recovery.

## Workflow

1. Define authoritative stores, derived stores, backup, replication, encryption, RPO, RTO, recovery order, and ownership.
2. Capture inventory snapshots, graph/index checkpoints, workflow histories, task leases, artifact manifests, budget ledgers, campaign/PR commit tokens, and audit.
3. Implement restore, rehydrate derived state, reconcile queues/leases, and deterministic replay.
4. Use idempotency and external-effect commit tokens to prevent duplicates.
5. Exercise region loss, database restore, queue loss, index rebuild, artifact-store interruption, and partial campaign recovery.
6. Verify data integrity, tenant isolation, cost ledger, control tower, and customer-visible state after recovery.
7. Document manual decision points and runbooks.

## Required repository outputs

- DR and replay plan with authoritative/derived-store map
- Backup, restore, rehydration, replay, reconciliation, and runbook artifacts
- RPO/RTO, duplicate-effect, tenant-isolation, and customer-state evidence

## Verification

- Run a full isolated DR exercise from backups and manifests.
- Compare recovered portfolio state with pre-failure checkpoints.
- Verify no duplicate PR, artifact, charge, or external mutation.

## Stop and escalate when

- Authoritative state or encryption keys cannot be restored.
- Replay of a non-idempotent external action lacks a commit token.
- RPO/RTO cannot be met for critical portfolios.

## Definition of done

- Portfolio recovers within target RPO/RTO.
- Successful work remains committed and failed work resumes safely.
- No duplicate external effects or cross-tenant leakage occurs.
