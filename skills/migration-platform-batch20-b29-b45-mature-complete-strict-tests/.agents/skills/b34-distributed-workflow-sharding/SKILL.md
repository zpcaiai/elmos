---
name: b34-distributed-workflow-sharding
description: Implement durable distributed migration workflows with bounded fan-out partition keys idempotent activities checkpointed fan-in backpressure compensation and deterministic replay.
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

## Skill 1251: Distributed workflow and task sharding

## Use this skill when

- Portfolio work must be split across many workers or regions.
- Long-running discovery, analysis, build, repair, test, campaign, and PR tasks need durable state.
- Retries and partial failures must not duplicate business side effects.

## Domain-specific risks and invariants

- Unbounded fan-out can collapse queues, databases, runners, or provider APIs.
- Non-idempotent retries can create duplicate PRs, messages, artifacts, or mutations.
- Workflow code changes can make in-flight histories unreplayable.

## Workflow

1. Define workflow states, shard keys, activity contracts, idempotency keys, retry classes, timeouts, checkpoints, compensation, and versioning.
2. Partition by tenant, portfolio, repository, work unit, phase, and resource profile without violating ordering constraints.
3. Implement bounded fan-out/fan-in and backpressure.
4. Persist activity outputs as immutable artifacts and commit tokens.
5. Implement duplicate message handling, lease loss, worker crash, partial fan-in, cancellation, and compensation.
6. Version workflow definitions and support deterministic replay of in-flight runs.
7. Run scale, failure, and replay tests across independent shards.

## Required repository outputs

- Versioned workflow definitions and activity schemas
- Shard plan, checkpoint state, retry/compensation policies, and replay manifests
- Failure-injection and deterministic-replay evidence

## Verification

- Kill workers during every critical phase and verify recovery.
- Replay histories against supported workflow versions.
- Verify repeated activities do not duplicate external effects.

## Stop and escalate when

- An activity cannot be made idempotent or compensated.
- Workflow version changes break deterministic replay.
- Fan-out or queue pressure cannot be bounded.

## Definition of done

- Distributed workflows recover without lost progress or duplicate effects.
- In-flight version compatibility is evidenced.
- Backpressure and cancellation work at scale.
