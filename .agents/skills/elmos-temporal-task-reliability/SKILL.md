---
name: elmos-temporal-task-reliability
description: Make long-running generation and migration workflows idempotent, cancellable,
  checkpointed, reconcilable, replay-safe, and recoverable.
version: 1.0.0
priority: P0
phase: G2
dependencies:
- elmos-architecture-contract-governance
- elmos-identity-tenant-security
---

# Temporal Workflow, Task Lease, Cancellation, and Recovery

## Objective

Guarantee interrupted work can resume or reconcile without losing results, duplicating side effects, or remaining indefinitely RUNNING.

## Use this skill when

Use this skill when implementing, repairing, reviewing, validating, or productionizing the **Temporal Workflow, Task Lease, Cancellation, and Recovery** capability in an eLMOS repository. Invoke the program orchestrator first for work spanning multiple skills.

## Dependencies

- `elmos-architecture-contract-governance`
- `elmos-identity-tenant-security`

Do not mark this skill complete until required dependency contracts are present and their blocking gates pass. A dependency can be implemented in the same change only when the plan preserves reviewable boundaries.

## Non-negotiable constraints

- Workflow code is deterministic and replay-compatible.
- Assume at-least-once Activity execution; every side effect needs idempotency and fencing.
- Reconcile UNKNOWN_RESULT before retry.
- Large logs and outputs belong in CAS/object storage.

## Required inputs

- Temporal workflows and activities.
- Project/task schema.
- Runner lease APIs.
- External side effects such as PRs, checks, uploads, billing, and notifications.

## Required outputs

- `Versioned workflow/task states.`
- `Idempotent workflow start.`
- `Lease renew/reaper/fencing.`
- Cancellation, pause, resume, checkpoint, reconciliation, and log streaming.
- `Replay/failure-injection tests.`

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

### State machines

- [ ] `ELMOS-WF-001` Define truthful project states including CANCEL_REQUESTED, CANCELLING, RECONCILING, UNKNOWN_RESULT, and MANUAL_RECOVERY.
- [ ] `ELMOS-WF-002` Define task states including lease, run, cancel, completing, expired, unknown, and quarantine.
- [ ] `ELMOS-WF-003` Create an allowed-transition table and reject illegal transitions.
- [ ] `ELMOS-WF-004` Generate unique transition IDs and enforce uniqueness.
- [ ] `ELMOS-WF-005` Write transition, outbox, and audit atomically.
- [ ] `ELMOS-WF-006` Prevent approval before a plan exists.
### Idempotent start

- [ ] `ELMOS-WF-007` Generate deterministic Workflow ID at project creation.
- [ ] `ELMOS-WF-008` Support Idempotency-Key on start and side-effecting commands.
- [ ] `ELMOS-WF-009` Use compare-and-set, transactional outbox, or Temporal Update-with-Start to remove dual-write race.
- [ ] `ELMOS-WF-010` Return existing workflow for duplicate start.
- [ ] `ELMOS-WF-011` Test concurrent starts and failures between each write.
### Activity correctness

- [ ] `ELMOS-WF-012` Replace generic workflow runtime exceptions with explicit application failures or modeled states.
- [ ] `ELMOS-WF-013` Wrap workflows so FAILED or CANCELLED is always persisted.
- [ ] `ELMOS-WF-014` Set per-activity timeouts, heartbeat, and retry policies.
- [ ] `ELMOS-WF-015` Heartbeat parse, build, transform, verification, transfer, and model work.
- [ ] `ELMOS-WF-016` Store checkpoint references in heartbeat details.
- [ ] `ELMOS-WF-017` Use versioned records and stable data conversion.
- [ ] `ELMOS-WF-018` Add Workflow Versioning, Search Attributes, and Continue-As-New.
### Lease and fencing

- [ ] `ELMOS-WF-019` Add attempt, lease_generation, lease_expires_at, fencing_token, receipt_id, and checkpoint to tasks.
- [ ] `ELMOS-WF-020` Implement acknowledgement and periodic renewal.
- [ ] `ELMOS-WF-021` Require attempt/generation on heartbeat, complete, and fail.
- [ ] `ELMOS-WF-022` Reject late results from old or expired leases.
- [ ] `ELMOS-WF-023` Make repeated completion with the same receipt idempotent.
- [ ] `ELMOS-WF-024` Enter reconciliation on conflicting receipts.
- [ ] `ELMOS-WF-025` Reap expired work to UNKNOWN_RESULT.
- [ ] `ELMOS-WF-026` Reconcile workspace, process, artifact, PR, check, and billing before retry.
- [ ] `ELMOS-WF-027` Move irreconcilable work to MANUAL_RECOVERY.
### Cancel, pause, resume

- [ ] `ELMOS-WF-028` Add authorized project/task cancel APIs.
- [ ] `ELMOS-WF-029` Propagate cancel to workflow, activity, runner, and child processes.
- [ ] `ELMOS-WF-030` Persist CANCEL_REQUESTED and CANCELLING truthfully.
- [ ] `ELMOS-WF-031` Save final checkpoint and partial artifact manifest.
- [ ] `ELMOS-WF-032` Expose noninterruptible boundaries.
- [ ] `ELMOS-WF-033` Implement pause/resume and approval signals.
- [ ] `ELMOS-WF-034` Replace database polling with signals or async completion.
- [ ] `ELMOS-WF-035` On resume compare snapshot, toolchain, policy, rule, and target digests.
### Logs and operations

- [ ] `ELMOS-WF-036` Implement chunked logs with monotonic sequence numbers.
- [ ] `ELMOS-WF-037` Support resumable SSE or WebSocket streaming.
- [ ] `ELMOS-WF-038` Store large logs in CAS and only redacted summaries/references in database.
- [ ] `ELMOS-WF-039` Store stage input, output, evidence, status, duration, and cost digests.
- [ ] `ELMOS-WF-040` Prevent customer absolute paths in remote APIs.
- [ ] `ELMOS-WF-041` Scan for stuck workflows and reconcile database, workflow, tasks, and checkpoints.
- [ ] `ELMOS-WF-042` Provide dead-letter/manual recovery view.
- [ ] `ELMOS-WF-043` Retain compatible workflow code for replay.
- [ ] `ELMOS-WF-044` Add deterministic resume from latest valid checkpoint.

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

- [ ] Run duplicate start/completion, late completion, lease expiry, and cancel/complete races.
- [ ] Kill control API, worker, and runner during every major stage.
- [ ] Disconnect the client and verify server work continues and reconnect retrieves progress/results.
- [ ] Replay historical workflows.
- [ ] Verify PR, artifact, notification, and billing effects are never duplicated.

Run repository-native format, lint, typecheck, unit, integration, packaging, and security commands. Also run the package validators when Skill content or schemas change:

```bash
python3 scripts/validate_skill_bundle.py
python3 scripts/validate_json_schemas.py
python3 -m unittest discover -s tests -v
```

## Definition of done

- [ ] No task remains permanently RUNNING after runner loss.
- [ ] Cancellation actually interrupts work and yields truthful state.
- [ ] Completed side effects are not repeated.
- [ ] Reconnecting clients retrieve durable progress, logs, and results.
- [ ] Historical workflows replay or report a compatibility block.

Additionally:

- [ ] No placeholder, TODO-only, mock-only, or documentation-only implementation is counted as production completion.
- [ ] All modified public contracts are versioned and compatibility-tested.
- [ ] All side effects are idempotent or reconciled.
- [ ] Critical actions are authorized, audited, and observable.
- [ ] Evidence identifies exact source, toolchain, rule/model/policy, commands, results, and residual risk.
- [ ] Static bundle validation is described accurately as structural validation only.

## Failure handling and handoff

Classify failures as `ENVIRONMENT`, `DEPENDENCY`, `CODE`, `POLICY`, `SECURITY`, `DATA`, `CAPACITY`, `PROVIDER`, or `UNKNOWN`. Preserve successful checkpoints. Put ambiguous side effects in `UNKNOWN_RESULT`/`MANUAL_RECOVERY`; reconcile before retrying. Update the implementation plan with status, commit, commands, measured wall-clock duration, cost, evidence digest, blockers, and the next dependency-resolved task.
