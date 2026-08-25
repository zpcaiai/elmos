# Temporal Workflow, Task Lease, Cancellation, and Recovery

- Skill: `elmos-temporal-task-reliability`
- Priority: `P0`
- Phase: `G2`
- Dependencies: `elmos-architecture-contract-governance`, `elmos-identity-tenant-security`

## Objective

Guarantee interrupted work can resume or reconcile without losing results, duplicating side effects, or remaining indefinitely RUNNING.

## Task groups

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

## Validation

- [ ] Run duplicate start/completion, late completion, lease expiry, and cancel/complete races.
- [ ] Kill control API, worker, and runner during every major stage.
- [ ] Disconnect the client and verify server work continues and reconnect retrieves progress/results.
- [ ] Replay historical workflows.
- [ ] Verify PR, artifact, notification, and billing effects are never duplicated.

## Exit gate

- [ ] No task remains permanently RUNNING after runner loss.
- [ ] Cancellation actually interrupts work and yields truthful state.
- [ ] Completed side effects are not repeated.
- [ ] Reconnecting clients retrieve durable progress, logs, and results.
- [ ] Historical workflows replay or report a compatibility block.
