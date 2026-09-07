# Feature Flags, Shadow Validation, Canary Rollout, and Safe Compatibility

- Skill: `elmos-progressive-delivery`
- Priority: `P2`
- Phase: `G8`
- Dependencies: `elmos-verification-fabric`, `elmos-observability-finops`, `elmos-policy-supply-chain-signing`

## Objective

Prevent platform changes from silently degrading migration quality, correctness, security, cost, or recovery.

## Task groups

### Feature flag foundation

- [ ] `ELMOS-REL-001` Provide provider-neutral OpenFeature-compatible evaluation.
- [ ] `ELMOS-REL-002` Target by tenant, repository, project, language path, adapter, risk, region, runner, and internal cohort.
- [ ] `ELMOS-REL-003` Record flag name/version/variant/reason/context digest in trace/evidence.
- [ ] `ELMOS-REL-004` Require authorization/audit for changes and approval for high-risk flags.
- [ ] `ELMOS-REL-005` Provide emergency kill switch independent of candidate service health.

### Shadow execution

- [ ] `ELMOS-REL-006` Run current and candidate engines/rules/prompts/models/toolchains from identical immutable inputs.
- [ ] `ELMOS-REL-007` Keep candidate outputs isolated and prevent external side effects.
- [ ] `ELMOS-REL-008` Compare patches, IR, compile/tests, contracts, behavior, performance, security, token/compute cost, runtime, and reviewer acceptance.
- [ ] `ELMOS-REL-009` Ensure candidate failure cannot fail the primary run.
- [ ] `ELMOS-REL-010` Store deterministic shadow evidence and sampling context.

### Canary controller

- [ ] `ELMOS-REL-011` Support staged cohorts such as internal, 1%, 5%, 20%, 50%, and 100%.
- [ ] `ELMOS-REL-012` Define minimum sample and thresholds for success, regression, unknown evidence, latency, cost, incidents, and certification.
- [ ] `ELMOS-REL-013` Pause automatically on insufficient data and rollback on severe regression.
- [ ] `ELMOS-REL-014` Prevent Simpson's-paradox-style aggregation by checking relevant repository/language/risk segments.
- [ ] `ELMOS-REL-015` Require explicit approval for final high-risk rollout.

### Compatibility releases

- [ ] `ELMOS-REL-016` Use expand/contract database migrations and compatibility windows.
- [ ] `ELMOS-REL-017` Preserve Protobuf field numbers and API versioning.
- [ ] `ELMOS-REL-018` Use Temporal workflow/activity versioning and retain replay-compatible code.
- [ ] `ELMOS-REL-019` Provide IR/schema migration and dual-read/write where required.
- [ ] `ELMOS-REL-020` Keep historical toolchain image, rule, prompt, model route, and policy digests available for rollback/replay.

### Rollback and learning

- [ ] `ELMOS-REL-021` Roll back routes/configuration first when safe, then workloads/toolchains/rules as required.
- [ ] `ELMOS-REL-022` Preserve generated artifacts/evidence for diagnosis without promoting them.
- [ ] `ELMOS-REL-023` Create regression cases from canary failures and require them before re-rollout.
- [ ] `ELMOS-REL-024` Audit rollout, pause, override, rollback, and kill-switch operations.

## Validation

- [ ] Shadow a deliberately broken rule and prove no customer mutation.
- [ ] Trigger quality, behavior, security, performance, and cost rollback thresholds.
- [ ] Run old Temporal histories against upgraded workers.
- [ ] Exercise database expand/contract with mixed versions.
- [ ] Use kill switch while the candidate control path is unhealthy.

## Exit gate

- [ ] New behavior is first measured in shadow and limited cohorts.
- [ ] Severe regressions automatically stop or roll back.
- [ ] Schema/workflow upgrades preserve replay and mixed-version compatibility.
- [ ] Every rollout conclusion has evidence and reproducible cohort definitions.
