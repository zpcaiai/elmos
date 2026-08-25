---
name: elmos-infrastructure-program-orchestrator
description: Orchestrate the complete eLMOS infrastructure hardening program, resolve
  dependencies, select the next executable slice, and emit evidence-backed progress.
version: 1.0.0
priority: P0
phase: G0-G9
dependencies: []
---

# eLMOS Infrastructure Program Orchestrator

## Objective

Turn the infrastructure roadmap into a durable, dependency-aware execution program that Codex or Claude Code can resume across long sessions.

## Use this skill when

Use this skill when implementing, repairing, reviewing, validating, or productionizing the **eLMOS Infrastructure Program Orchestrator** capability in an eLMOS repository. Invoke the program orchestrator first for work spanning multiple skills.

## Dependencies

- None

Do not mark this skill complete until required dependency contracts are present and their blocking gates pass. A dependency can be implemented in the same change only when the plan preserves reviewable boundaries.

## Non-negotiable constraints

- Do not mark an EPIC complete from prose or file presence alone; require executable evidence.
- Do not start downstream work while an unmet P0 dependency remains.
- Report system autonomous wall-clock ETA separately from human-equivalent engineering effort.
- Prefer one production-shaped vertical slice over broad scaffolding.
- Preserve repository conventions unless an ADR authorizes change.

## Required inputs

- Repository root, branch, and commit.
- Existing architecture, migrations, contracts, CI, tests, deployments, skills, and prior evidence.
- Target deployment modes and source-residency policy.
- Runner, model, storage, network, and review budgets.

## Required outputs

- `Dependency-resolved implementation plan.`
- `Machine-readable execution plan and task ledger.`
- System ETA, human comparison, cost forecast, risk register, and blockers.
- `Checkpoint and Evidence Pack references.`

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

- [ ] Validate that every selected task has all dependencies DONE or an approved exception.
- [ ] Run package validators and repository-native tests.
- [ ] Verify every progress claim references a test, trace, report, digest, or signed evidence.
- [ ] Interrupt after a checkpoint and prove the plan resumes without repeating confirmed side effects.

Run repository-native format, lint, typecheck, unit, integration, packaging, and security commands. Also run the package validators when Skill content or schemas change:

```bash
python3 scripts/validate_skill_bundle.py
python3 scripts/validate_json_schemas.py
python3 -m unittest discover -s tests -v
```

## Definition of done

- [ ] A new agent can resume without hidden conversation context.
- [ ] No P0 gate is bypassed.
- [ ] Every DONE task has executable evidence and rollback or forward-fix.
- [ ] System ETA and human-equivalent effort are separate fields.

Additionally:

- [ ] No placeholder, TODO-only, mock-only, or documentation-only implementation is counted as production completion.
- [ ] All modified public contracts are versioned and compatibility-tested.
- [ ] All side effects are idempotent or reconciled.
- [ ] Critical actions are authorized, audited, and observable.
- [ ] Evidence identifies exact source, toolchain, rule/model/policy, commands, results, and residual risk.
- [ ] Static bundle validation is described accurately as structural validation only.

## Failure handling and handoff

Classify failures as `ENVIRONMENT`, `DEPENDENCY`, `CODE`, `POLICY`, `SECURITY`, `DATA`, `CAPACITY`, `PROVIDER`, or `UNKNOWN`. Preserve successful checkpoints. Put ambiguous side effects in `UNKNOWN_RESULT`/`MANUAL_RECOVERY`; reconcile before retrying. Update the implementation plan with status, commit, commands, measured wall-clock duration, cost, evidence digest, blockers, and the next dependency-resolved task.
