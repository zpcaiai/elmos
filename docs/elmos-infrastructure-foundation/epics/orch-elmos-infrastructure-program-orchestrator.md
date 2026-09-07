# eLMOS Infrastructure Program Orchestrator

- Skill: `elmos-infrastructure-program-orchestrator`
- Priority: `P0`
- Phase: `G0-G9`
- Dependencies: None

## Objective

Turn the infrastructure roadmap into a durable, dependency-aware execution program that Codex or Claude Code can resume across long sessions.

## Task groups

### Discovery and baseline

- [ ] `ELMOS-ORCH-001` Inventory applications, workers, runners, engines, platform modules, contracts, schemas, migrations, CI, deployment files, and skills.
- [ ] `ELMOS-ORCH-002` Identify authoritative stores for project, workflow, task, artifact, audit, billing, policy, and evidence.
- [ ] `ELMOS-ORCH-003` Detect placeholders, in-memory production state, trusted headers, default secrets, unprotected endpoints, and unexecuted integrations.
- [ ] `ELMOS-ORCH-004` Run the repository test suite and capture exact command, commit, environment, result, duration, and failures.
- [ ] `ELMOS-ORCH-005` Create a gap map from code to the selected acceptance gate.

### Planning and dependency control

- [ ] `ELMOS-ORCH-006` Load the skill manifest and task catalog before selecting work.
- [ ] `ELMOS-ORCH-007` Resolve all dependencies and approved exceptions.
- [ ] `ELMOS-ORCH-008` Select the smallest vertical slice that produces a demonstrable end-to-end result.
- [ ] `ELMOS-ORCH-009` Split work into reversible commits, migrations, checkpoints, and rollback boundaries.
- [ ] `ELMOS-ORCH-010` Attach validation commands and expected evidence to every task.
- [ ] `ELMOS-ORCH-011` Estimate system wall-clock runtime from measured history and label uncertainty.
- [ ] `ELMOS-ORCH-012` Estimate human-equivalent effort separately.
- [ ] `ELMOS-ORCH-013` Reserve compute, model, storage, network, and review budgets.

### Execution and handoff

- [ ] `ELMOS-ORCH-014` Create or update the durable implementation-plan YAML before editing.
- [ ] `ELMOS-ORCH-015` Implement production code, schema, tests, telemetry, audit, documentation, and runbook changes together.
- [ ] `ELMOS-ORCH-016` Classify failures as environment, dependency, code, policy, security, data, capacity, provider, or unknown.
- [ ] `ELMOS-ORCH-017` Place irreconcilable results in BLOCKED or MANUAL_RECOVERY rather than hiding partial failure.
- [ ] `ELMOS-ORCH-018` Checkpoint after each successful validation boundary and store large outputs by digest.
- [ ] `ELMOS-ORCH-019` Update status, commit, commands, measured duration, cost, evidence digest, and residual risk.
- [ ] `ELMOS-ORCH-020` Report the next dependency-resolved task and why it is next.
- [ ] `ELMOS-ORCH-021` Emit CERTIFIED, LIMITED, EXPERIMENTAL, or BLOCKED release status.

## Validation

- [ ] Validate that every selected task has all dependencies DONE or an approved exception.
- [ ] Run package validators and repository-native tests.
- [ ] Verify every progress claim references a test, trace, report, digest, or signed evidence.
- [ ] Interrupt after a checkpoint and prove the plan resumes without repeating confirmed side effects.

## Exit gate

- [ ] A new agent can resume without hidden conversation context.
- [ ] No P0 gate is bypassed.
- [ ] Every DONE task has executable evidence and rollback or forward-fix.
- [ ] System ETA and human-equivalent effort are separate fields.
