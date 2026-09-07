---
name: b34-portfolio-scale-certification-gate
description: Run the conservative Batch 34 portfolio-scale certification gate and emit certified limited experimental or blocked status from inventory graph work units index workflows fleet cache transfer campaigns pull requests recovery fairness budgets benchmarks forecasts disaster replay holdout and evidence.
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

## Skill 1264: Batch 34 portfolio-scale certification gate

## Use this skill when

- A Batch 34 portfolio pack is being assessed for limited or certified release.
- A team needs to validate scale claims or prevent a status-only certification.
- A release review requires evidence across all portfolio-scale domains.

## Domain-specific risks and invariants

- A pack can appear complete while inventory, graph, benchmark, fairness, recovery, or representative evidence is missing.
- Metrics can be fabricated or computed on silently reduced scope.
- Scale certification without holdout and DR evidence creates unacceptable operational risk.

## Workflow

1. Run pack, inventory, dependency-graph, and work-unit validators.
2. Verify exact portfolio scope, owners, baselines, regions, languages, build systems, and inventory coverage.
3. Verify typed graph, semantic index, incremental equivalence, durable workflows, runner placement, cache correctness, transfer integrity, campaign and multi-PR evidence.
4. Verify checkpoint recovery, fairness, budget, control-tower freshness, benchmark, forecast, and DR replay.
5. Verify independent holdout and representative portfolio corpora and all evidence references.
6. Apply conservative thresholds and zero-tolerance fields.
7. Write gate result and report; never upgrade status beyond evidence.

## Required repository outputs

- Updated `certification/gate-result.json` and `gate-report.md`
- A complete failure list or evidence-backed pass
- No direct code or configuration changes except gate output

## Verification

- Run `python3 scripts/batch34/run_portfolio_gate.py portfolio-packs/<pack-key>`.
- Inspect every evidence reference and benchmark manifest.
- Confirm certified status cannot pass with empty corpora or zero-valued fake metrics.

## Stop and escalate when

- Any required artifact, owner, exact scope, holdout, representative portfolio, or evidence reference is missing.
- Any zero-tolerance integrity, tenant, fairness, cost, or recovery failure is nonzero.
- Scale benchmark scope or environment is not reproducible.

## Definition of done

- Gate output matches actual evidence.
- Certified packs meet all thresholds and zero-tolerance conditions.
- Insufficient packs remain limited, experimental, research, or blocked.
