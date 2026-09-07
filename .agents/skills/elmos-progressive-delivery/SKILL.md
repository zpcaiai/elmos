---
name: elmos-progressive-delivery
description: Release new adapters, rules, prompts, models, toolchains, schemas, and
  platform components through governed flags, shadow comparison, canary gates, and
  rollback.
version: 1.0.0
priority: P2
phase: G8
dependencies:
- elmos-verification-fabric
- elmos-observability-finops
- elmos-policy-supply-chain-signing
---

# Feature Flags, Shadow Validation, Canary Rollout, and Safe Compatibility

## Objective

Prevent platform changes from silently degrading migration quality, correctness, security, cost, or recovery.

## Use this skill when

Use this skill when implementing, repairing, reviewing, validating, or productionizing the **Feature Flags, Shadow Validation, Canary Rollout, and Safe Compatibility** capability in an eLMOS repository. Invoke the program orchestrator first for work spanning multiple skills.

## Dependencies

- `elmos-verification-fabric`
- `elmos-observability-finops`
- `elmos-policy-supply-chain-signing`

Do not mark this skill complete until required dependency contracts are present and their blocking gates pass. A dependency can be implemented in the same change only when the plan preserves reviewable boundaries.

## Non-negotiable constraints

- Shadow outputs do not mutate customer repositories or production state.
- Rollout gates use validated quality and safety signals, not only service uptime.
- Schema/workflow changes remain replay- and rollback-compatible.
- Kill switches and rollback preserve evidence.

## Required inputs

- Candidate/current component versions.
- Feature cohorts, policies, metrics, thresholds, and minimum sample.
- Compatibility and rollback plans.

## Required outputs

- `OpenFeature-compatible decisions.`
- `Shadow comparison evidence.`
- `Canary progression/rollback controller.`
- Schema, workflow, toolchain, rule, prompt, and model compatibility releases.

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

- [ ] Shadow a deliberately broken rule and prove no customer mutation.
- [ ] Trigger quality, behavior, security, performance, and cost rollback thresholds.
- [ ] Run old Temporal histories against upgraded workers.
- [ ] Exercise database expand/contract with mixed versions.
- [ ] Use kill switch while the candidate control path is unhealthy.

Run repository-native format, lint, typecheck, unit, integration, packaging, and security commands. Also run the package validators when Skill content or schemas change:

```bash
python3 scripts/validate_skill_bundle.py
python3 scripts/validate_json_schemas.py
python3 -m unittest discover -s tests -v
```

## Definition of done

- [ ] New behavior is first measured in shadow and limited cohorts.
- [ ] Severe regressions automatically stop or roll back.
- [ ] Schema/workflow upgrades preserve replay and mixed-version compatibility.
- [ ] Every rollout conclusion has evidence and reproducible cohort definitions.

Additionally:

- [ ] No placeholder, TODO-only, mock-only, or documentation-only implementation is counted as production completion.
- [ ] All modified public contracts are versioned and compatibility-tested.
- [ ] All side effects are idempotent or reconciled.
- [ ] Critical actions are authorized, audited, and observable.
- [ ] Evidence identifies exact source, toolchain, rule/model/policy, commands, results, and residual risk.
- [ ] Static bundle validation is described accurately as structural validation only.

## Failure handling and handoff

Classify failures as `ENVIRONMENT`, `DEPENDENCY`, `CODE`, `POLICY`, `SECURITY`, `DATA`, `CAPACITY`, `PROVIDER`, or `UNKNOWN`. Preserve successful checkpoints. Put ambiguous side effects in `UNKNOWN_RESULT`/`MANUAL_RECOVERY`; reconcile before retrying. Update the implementation plan with status, commit, commands, measured wall-clock duration, cost, evidence digest, blockers, and the next dependency-resolved task.
