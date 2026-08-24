---
name: elmos-codex-claude-cache-parity-rollout
description: Integrate and release the complete ELMOS cache parity architecture across prompt, context, deterministic actions, artifacts, environments, routing, diagnostics, benchmarking, and continuous SLO control.
version: 1.2.0
package: elmos-build-cache-staging-codex-claude-parity
phase: P13-parity-rollout
dependencies: [elmos-cache-rollout-end-to-end, elmos-cache-hit-slo-autotuning, elmos-multi-layer-cache-coordinator, elmos-codex-claude-parity-benchmark]
---

# Codex/Claude-Class Cache Parity End-to-End Rollout

## Outcome

Deliver a production-shaped ELMOS cache subsystem that reaches the package parity targets on defined warm coding/conversion workloads, exposes honest measured results, and safely degrades when a cache layer is unavailable. This is an implementation skill. The coding agent must modify the actual ELMOS repository, run reproducible verification, and attach evidence; prose, simulated counters, or a disconnected prototype are not completion.

## Use this skill when

- Executing the final v1.2.0 cache parity program after all dependency Skills have fresh evidence.
- Preparing production rollout, migration from v1.1.0, or a release claim about Codex/Claude-class caching.
- Coordinating schema, API, worker, provider, storage, dashboard, SLO, security, and operator changes.

## Required inputs

- Current ELMOS repository/deployments, all 42 package Skills, dependency evidence, v1.1.0 migration state, provider profiles, parity corpus, capacity/cost budget, rollout cohorts, and incident/rollback procedures.
- Data retention, tenancy, security, compliance, availability, and release policies.
- Baseline production metrics and explicitly approved claim language.

## Produced artifacts

- Integrated production code and migrations for every parity layer, plus backward-compatible v1.1.0 migration and rollback.
- Feature-flag hierarchy, shadow/read-only/canary/progressive rollout plan, runbooks, dashboards, alerts, and on-call diagnostics.
- Fresh parity certificate and zero-false-hit/security/chaos evidence for the release candidate.
- Measured production scorecard by cohort and honest capability statement that lists scenarios not expected to hit highly.
- Final evidence index linking code, config, schemas, tests, reports, and rollback exercises.

## Non-negotiable invariants

- The release cannot promise universal 95-100% cache hits; it may claim only measured results for defined eligible workloads and published denominators.
- Correct misses are always preferred to false hits; accepted false hits, cross-tenant reuse, corrupt execution, and under-validated publication must remain zero.
- All durable task state lives in run journal/checkpoints/CAS/staging, never only in provider prompt cache, local memory, or one worker.
- Every layer can be independently disabled and the system continues on a correct slower path.
- Migration is backward compatible or explicitly staged with dual-read/write and verified rollback.
- Release gates bind to exact code/config/provider/corpus/platform fingerprints and expire after material change.

## Execution workflow

1. Inventory current v1.1.0 deployment and map each new v1.2.0 schema/API/worker/provider/UI change with compatibility and rollback.
2. Land observation-only provider adapters, prefix manifests, ledger, environment/affinity inventory, miss diagnostics, and unified accounting.
3. Enable canonical prompt layout and context ledger by cohort; then environment snapshots, affinity routing, coordinator, and compaction under feature flags.
4. Run full parity, security, chaos, migration, load, and rollback suites on a release candidate.
5. Roll out shadow, internal/dogfood, canary tenants, 5%, 25%, 50%, and 100% only when SLO/error-budget gates pass.
6. Publish measured scorecard and monitor drift, provider changes, miss reasons, capacity, cost, fairness, and false-hit sentinels.

## Implementation tasks

1. Create a migration ledger for schemas, cache namespaces, prompt compatibility groups, environment snapshots, routing, dashboards, and operator APIs.
2. Implement dual-read/safe-write or versioned namespace transitions so v1.1.0 entries remain valid only where identities and validation semantics match.
3. Wire all feature flags and kill switches by provider, model, tenant, project, request class, layer, and policy.
4. Integrate parity benchmark into CI/nightly/release workflows and block promotion on mandatory gate failure.
5. Create production dashboards for eligible token reuse, exact/weighted Action reuse, environment hit, restart reuse, wall-clock/token/cost savings, unexpected misses, wrong-shard, false-hit sentinels, and worst cohorts.
6. Exercise rollback from every rollout phase, provider no-cache mode, cache-store outage, worker failure, corrupted object, secret rotation, model/tool change, and context compaction failure.
7. Document operator actions for top miss reasons and a capacity/cost plan for local/remote CAS, environment snapshots, provider cache writes, and telemetry.
8. Generate a release evidence index and measured claim text that distinguishes target, certified benchmark result, and posted production observation.

## Acceptance criteria

- All 42 Skills are present, dependency-valid, implemented or explicitly tracked, and the package validator/test suite passes.
- Release candidate passes every parity mandatory gate: >=90% stable-turn eligible token reuse after turn 3; <=2% unexpected full-prefix misses; >=99% exact rerun weighted Action reuse; >=90% small-edit reuse; <=5% unnecessary invalidation; >=95% environment hit; >=80% warm-start p95 reduction; >=99.9% restart artifact reuse; >=70% stable-follow-up wall-clock saved; >=80% model input cost saved; zero false hits.
- Migration and rollback preserve runs, checkpoints, staged files, artifacts, permissions, and validated publication state.
- Optional cache-layer outages degrade correctly without data loss, duplicate side effects, or unsafe publication.
- Worst-cohort, fairness, capacity, latency, and provider-cost guardrails pass, not merely global averages.
- Production claims cite the measured report and state the cold-start/model-switch/tool-change/major-upgrade boundaries.

## Evidence required

- Implementation/migration commits, schema/API diffs, feature-flag inventory, deployment manifests, and evidence freshness map.
- Full CI, parity, load, security, tenant-isolation, chaos, migration, rollback, and clean-rebuild equivalence results.
- Signed parity certificate, raw observation digest, dashboards, canary/control outcomes, and final production scorecard.
- Runbooks, incident simulations, capacity/cost forecast, and approved claim wording.

## Anti-patterns

- Declaring success because the Skills package exists while the ELMOS repository lacks implementation and measured evidence.
- Enabling all layers at once without observation, shadow, canary, or independent kill switches.
- Using aggregate raw hit rate as the release gate.
- Hiding cold starts, model/tool changes, TTL expiry, or unsupported providers from users.
- Retaining old cache namespaces after semantic compatibility has changed.
- Publishing “same as Codex/Claude” without a defined workload and report.

## Done condition

The v1.2.0 program is complete only after production integration, migration, all parity/security/chaos gates, zero-false-hit proof, staged rollout, rollback exercises, dashboards/runbooks, and a measured—not merely targeted—scorecard are attached to the exact release candidate.
