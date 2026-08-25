# Scale Benchmarks, Fault Injection, Security Tests, and Pilot Certification

- Skill: `elmos-scale-benchmark-certification`
- Priority: `P1`
- Phase: `G9`
- Dependencies: `elmos-observability-finops`, `elmos-progressive-delivery`, `elmos-backup-recovery-replay`, `elmos-policy-supply-chain-signing`

## Objective

Prove that eLMOS correctness, performance, security, recovery, cost, and evidence claims hold under representative scale and failure.

## Task groups

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

## Validation

- [ ] Re-run benchmark from a clean environment and compare manifests.
- [ ] Validate cold/warm/incremental correctness and exact invalidation.
- [ ] Run all listed failure races and duplicate-effect assertions.
- [ ] Execute red-team campaign under isolated accounts.
- [ ] Repeat three real pilots and verify signed packs offline.

## Exit gate

- [ ] Performance and cost claims are reproducible and segmented.
- [ ] Critical failure/security scenarios have passing regression tests.
- [ ] Runtime/cost estimates are calibrated against actuals.
- [ ] Commercial readiness status is conservative, evidence-backed, and repeatable.
