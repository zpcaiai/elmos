---
name: elmos-scale-benchmark-certification
description: Benchmark cold/warm/incremental execution across repository and portfolio
  sizes, inject failures and attacks, calibrate forecasts, and certify real pilot
  readiness.
version: 1.0.0
priority: P1
phase: G9
dependencies:
- elmos-observability-finops
- elmos-progressive-delivery
- elmos-backup-recovery-replay
- elmos-policy-supply-chain-signing
---

# Scale Benchmarks, Fault Injection, Security Tests, and Pilot Certification

## Objective

Prove that eLMOS correctness, performance, security, recovery, cost, and evidence claims hold under representative scale and failure.

## Use this skill when

Use this skill when implementing, repairing, reviewing, validating, or productionizing the **Scale Benchmarks, Fault Injection, Security Tests, and Pilot Certification** capability in an eLMOS repository. Invoke the program orchestrator first for work spanning multiple skills.

## Dependencies

- `elmos-observability-finops`
- `elmos-progressive-delivery`
- `elmos-backup-recovery-replay`
- `elmos-policy-supply-chain-signing`

Do not mark this skill complete until required dependency contracts are present and their blocking gates pass. A dependency can be implemented in the same change only when the plan preserves reviewable boundaries.

## Non-negotiable constraints

- Benchmarks use fixed datasets, snapshots, toolchains, policies, environments, and declared warm/cold state.
- Static package validation is not production certification.
- Fault/security tests run in isolated environments.
- Pilot success includes explainable failures and repeatability, not only happy paths.

## Required inputs

- Fixture and real-pilot repositories.
- Target scale profiles, workloads, faults, attacks, metrics, gates, and budgets.
- Cold/warm cache and capacity configurations.

## Required outputs

- `Reproducible benchmark suite/results.`
- `Fault/security/recovery evidence.`
- `Cache/runtime/cost forecast calibration.`
- `CERTIFIED, LIMITED, EXPERIMENTAL, or BLOCKED pilot status.`

## Repository discovery

Before editing:

1. Locate `AGENTS.md`, `CLAUDE.md`, repository-local Skills, architecture decision records, manifests, schemas, migrations, and build commands.
2. Identify actual control-plane, workflow, runner, engine, web, database, object-store, policy, telemetry, and test modules; do not assume the reference layout exists.
3. Search for existing contracts and implementations before creating duplicates.
4. Record current behavior, known gaps, security boundaries, external side effects, and the exact validation commands that are available.
5. Create or update a durable implementation plan from `templates/IMPLEMENTATION-PLAN.yaml`.

## Execution workflow

1. Select the smallest dependency-resolved vertical slice.
2. Freeze input snapshots, schema/toolchain/policy versions, and rollback boundaries.
3. Implement contract/schema changes before consumers, using backward-compatible transitions.
4. Implement production behavior, authorization, idempotency, telemetry, audit, failure handling, tests, documentation, and runbooks together.
5. Execute focused tests, integration tests, race/failure tests, security tests, and clean-environment reproduction as applicable.
6. Save large outputs by digest; record commands, results, durations, cost, evidence, and residual risk.
7. Report autonomous **system wall-clock runtime** separately from human-equivalent engineering/review effort.
8. Never claim production completion from generated files or static validation alone.

## Implementation checklist

### Fixture estate

- [ ] `ELMOS-BENCH-001` Create fixed small/medium/large/XL Java, Maven/Gradle multi-module, Spring legacy, database/message/cache, Python web/data/ML, .NET, TypeScript UI, native, and mixed-language monorepo fixtures.
- [ ] `ELMOS-BENCH-002` Include known semantic, dependency, build, flaky, security, performance, and recovery cases.
- [ ] `ELMOS-BENCH-003` Pin commits, dependencies, datasets, seeds, toolchains, and expected results.
- [ ] `ELMOS-BENCH-004` Exclude restricted customer source and license all fixtures.
### Cold, warm, and incremental runs

- [ ] `ELMOS-BENCH-005` Run empty-cache cold, full warm, single-file, single-symbol, module, dependency, toolchain, rule, prompt/model, policy, and permission-change scenarios.
- [ ] `ELMOS-BENCH-006` Measure every cache layer, invalidation reason, bytes transferred, stages recomputed, duration, cost, and quality.
- [ ] `ELMOS-BENCH-007` Sample-recompute warm hits and compare outputs to detect poisoning/staleness.
- [ ] `ELMOS-BENCH-008` Verify changed inputs invalidate exactly the required work.
### Scale profiles

- [ ] `ELMOS-BENCH-009` Define S under 50K LOC, M 50K-500K, L 500K-2M, XL above 2M, and portfolios of 100/1000 repositories with mixed languages.
- [ ] `ELMOS-BENCH-010` Measure inventory/index size, workflow history, queue, runner utilization, CAS, transfer, DB, model, validation, evidence, and cleanup.
- [ ] `ELMOS-BENCH-011` Exercise multi-repo dependencies, merge ordering, partial failure, quotas, fairness, and noisy neighbors.
- [ ] `ELMOS-BENCH-012` Report throughput, latency distributions, resource curves, bottlenecks, and saturation.
### Fault injection

- [ ] `ELMOS-BENCH-013` Restart control API/Temporal workers/runners, interrupt network, expire leases/certificates, degrade database/object storage/model providers, corrupt chunks/cache, duplicate webhooks/start/cancel/complete, exhaust quota/disk, and fail shards.
- [ ] `ELMOS-BENCH-014` Verify deterministic state, fencing, reconciliation, bounded retries, partial recovery, and no duplicate side effects.
- [ ] `ELMOS-BENCH-015` Generate reusable regression cases for every discovered failure.
### Security campaign

- [ ] `ELMOS-BENCH-016` Test cross-tenant database/CAS/cache/workspace/evidence access, stolen/revoked runner identity, sandbox escape/path traversal/metadata/egress, secret leakage, cache poisoning, malicious dependencies, prompt injection/tool escalation, unsigned artifacts, policy bypass, and export abuse.
- [ ] `ELMOS-BENCH-017` Use independent red-team assertions and preserve safe evidence.
- [ ] `ELMOS-BENCH-018` Block release on unresolved critical findings.
### Forecast and quality calibration

- [ ] `ELMOS-BENCH-019` Backtest machine wall-clock ETA P50/P80/P95, queue/capacity forecasts, cost forecasts, and automation confidence across cold/warm/change/scale/failure cohorts.
- [ ] `ELMOS-BENCH-020` Calibrate models continuously and report coverage/interval accuracy and segment bias.
- [ ] `ELMOS-BENCH-021` Keep human-equivalent effort comparison separate from autonomous runtime.
- [ ] `ELMOS-BENCH-022` Track compile, test retention, behavior, regression, repair, PR acceptance, evidence, source-egress, and cost-per-verified-workload.
### Pilot certification

- [ ] `ELMOS-BENCH-023` Select at least three structurally different real Java repositories with authorization and fixed commits.
- [ ] `ELMOS-BENCH-024` Complete source-local snapshot, baseline, health check, deterministic OpenRewrite path, compile/tests, classified long-tail repair, PR/checks, signed offline evidence, and repeat run.
- [ ] `ELMOS-BENCH-025` Record all failures, manual tasks, deviations, review time, source-egress bytes, runtime, and cost.
- [ ] `ELMOS-BENCH-026` Issue CERTIFIED/LIMITED/EXPERIMENTAL/BLOCKED based on exact gates.
- [ ] `ELMOS-BENCH-027` Do not claim commercial production readiness until the repeatable pilot and restore/security gates pass.

## Required artifacts

At minimum, produce or update:

- Versioned contracts and schemas.
- Database migrations and compatibility/rollback notes where state changes.
- Production implementation with explicit authorization, idempotency, retries, cancellation, and failure classification as applicable.
- Unit, integration, end-to-end, race/failure, and security tests appropriate to risk.
- OpenTelemetry instrumentation, operational metrics, alerts, and runbooks for production components.
- Audit/evidence records with immutable input and output digests.
- Updated architecture and operational documentation.
- Task report based on `templates/TASK-REPORT.md`.

## Validation

- [ ] Re-run benchmark from a clean environment and compare manifests.
- [ ] Validate cold/warm/incremental correctness and exact invalidation.
- [ ] Run all listed failure races and duplicate-effect assertions.
- [ ] Execute red-team campaign under isolated accounts.
- [ ] Repeat three real pilots and verify signed packs offline.

Run repository-native format, lint, typecheck, unit, integration, packaging, and security commands. Also run the package validators when Skill content or schemas change:

```bash
python3 scripts/validate_skill_bundle.py
python3 scripts/validate_json_schemas.py
python3 -m unittest discover -s tests -v
```

## Definition of done

- [ ] Performance and cost claims are reproducible and segmented.
- [ ] Critical failure/security scenarios have passing regression tests.
- [ ] Runtime/cost estimates are calibrated against actuals.
- [ ] Commercial readiness status is conservative, evidence-backed, and repeatable.

Additionally:

- [ ] No placeholder, TODO-only, mock-only, or documentation-only implementation is counted as production completion.
- [ ] All modified public contracts are versioned and compatibility-tested.
- [ ] All side effects are idempotent or reconciled.
- [ ] Critical actions are authorized, audited, and observable.
- [ ] Evidence identifies exact source, toolchain, rule/model/policy, commands, results, and residual risk.
- [ ] Static bundle validation is described accurately as structural validation only.

## Failure handling and handoff

Classify failures as `ENVIRONMENT`, `DEPENDENCY`, `CODE`, `POLICY`, `SECURITY`, `DATA`, `CAPACITY`, `PROVIDER`, or `UNKNOWN`. Preserve successful checkpoints. Put ambiguous side effects in `UNKNOWN_RESULT`/`MANUAL_RECOVERY`; reconcile before retrying. Update the implementation plan with status, commit, commands, measured wall-clock duration, cost, evidence digest, blockers, and the next dependency-resolved task.
