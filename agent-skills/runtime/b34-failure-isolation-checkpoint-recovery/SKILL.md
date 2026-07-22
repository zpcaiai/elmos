---
name: b34-failure-isolation-checkpoint-recovery
description: "Implement shard-level failure isolation durable checkpoints bounded retries quarantine dead-letter handling local rollback and partial portfolio recovery without restarting successful work."
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

## Skill 1257: Failure isolation, checkpoint, and local recovery

## Use this skill when

- Large campaigns experience runner loss, provider errors, repository failures, or corrupted artifacts.
- Successful shards must remain committed while failed shards recover.
- Retries and manual repair need precise checkpoints.

## Domain-specific risks and invariants

- Global restart wastes work and can duplicate side effects.
- Retry storms can amplify a provider or repository outage.
- A corrupt checkpoint can silently skip work or reuse invalid outputs.

## Workflow

1. Define failure domains by tenant, portfolio, repository, work unit, workflow phase, artifact, and external provider.
2. Define checkpoint contents, commit tokens, artifact digests, recovery ownership, and retention.
3. Classify retryable, non-retryable, environmental, policy, data, and code failures.
4. Implement bounded retry with backoff, jitter, circuit breakers, quarantine, and dead-letter queues.
5. Recover from the last verified checkpoint and validate prior committed outputs.
6. Implement local rollback or compensation for partial external effects.
7. Inject failures at discovery, indexing, build, test, artifact, PR, and reporting phases.

## Required repository outputs

- Failure taxonomy, checkpoint schema, retry and quarantine policies
- Recovery manifests and partial-progress reports
- Failure-injection, replay, rollback, and duplicate-effect evidence

## Verification

- Kill workers and corrupt selected non-production checkpoints.
- Verify successful shards are not repeated.
- Verify unbounded retries and duplicate external effects are impossible.

## Stop and escalate when

- A phase has non-idempotent effects without compensation.
- Checkpoint integrity cannot be verified.
- Recovery would cross tenant, baseline, or policy boundaries.

## Definition of done

- Failed shards recover independently.
- Successful work remains valid.
- No lost progress, duplicate effect, or infinite retry remains.
