---
name: elmos-backup-recovery-replay
description: Protect PostgreSQL, Temporal, CAS, policies, keys, configurations, and
  portfolio state and recover without duplicate external effects.
version: 1.0.0
priority: P1
phase: G8
dependencies:
- elmos-temporal-task-reliability
- elmos-content-addressed-cache
- elmos-evidence-pack-offline-verification
- elmos-observability-finops
---

# Backup, Restore, Disaster Recovery, Reconciliation, and Deterministic Replay

## Objective

Make service, region, database, storage, runner, and workflow failures recoverable within defined RPO/RTO and provable through exercises.

## Use this skill when

Use this skill when implementing, repairing, reviewing, validating, or productionizing the **Backup, Restore, Disaster Recovery, Reconciliation, and Deterministic Replay** capability in an eLMOS repository. Invoke the program orchestrator first for work spanning multiple skills.

## Dependencies

- `elmos-temporal-task-reliability`
- `elmos-content-addressed-cache`
- `elmos-evidence-pack-offline-verification`
- `elmos-observability-finops`

Do not mark this skill complete until required dependency contracts are present and their blocking gates pass. A dependency can be implemented in the same change only when the plan preserves reviewable boundaries.

## Non-negotiable constraints

- A backup is not accepted until restored and validated.
- Recovery reconciles before retrying unknown side effects.
- Historical workflow code/schema/trust required for replay is retained.
- DR tests must not mutate real customer production endpoints.

## Required inputs

- Data inventory, authority map, RPO/RTO, residency, encryption, legal hold, and dependencies.
- PostgreSQL/Temporal/object/config/key backup facilities.
- Idempotency receipts, checkpoints, manifests, and evidence.

## Required outputs

- `Backup/restore automation and runbooks.`
- `Reconciliation/replay tools.`
- `Single-project, tenant, portfolio, and regional recovery procedures.`
- `Signed DR evidence and measured RPO/RTO.`

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

### Recovery design

- [ ] `ELMOS-DR-001` Inventory authoritative state and derived/rebuildable indexes for PostgreSQL, Temporal, CAS/object storage, queues, configuration, policy, feature flags, trust roots, and secrets.
- [ ] `ELMOS-DR-002` Define RPO/RTO, recovery dependency order, owners, residency, encryption, retention, and point-of-no-return conditions.
- [ ] `ELMOS-DR-003` Document graceful degradation when a dependency is unavailable.
- [ ] `ELMOS-DR-004` Separate backup credentials/accounts/regions from runtime credentials.
### PostgreSQL recovery

- [ ] `ELMOS-DR-005` Configure encrypted full backups plus WAL/PITR.
- [ ] `ELMOS-DR-006` Test point-in-time, accidental delete, schema-upgrade, and region recovery.
- [ ] `ELMOS-DR-007` Restore with non-superuser runtime roles and verify RLS/security configuration.
- [ ] `ELMOS-DR-008` Reconcile outbox, audit, references, leases, budgets, and object manifests.
- [ ] `ELMOS-DR-009` Measure actual RPO/RTO and data loss window.
### CAS and object recovery

- [ ] `ELMOS-DR-010` Enable versioning/replication or offline backup according to data class.
- [ ] `ELMOS-DR-011` Preserve manifests and reference metadata needed to rebuild indexes.
- [ ] `ELMOS-DR-012` Run periodic digest/inventory sampling and orphan/missing-object reconciliation.
- [ ] `ELMOS-DR-013` Restore accidental deletes and region loss while respecting legal holds.
- [ ] `ELMOS-DR-014` Prevent lifecycle/GC from deleting unreconciled or protected recovery data.
### Temporal recovery and replay

- [ ] `ELMOS-DR-015` Back up persistence/visibility configuration and namespace/search-attribute settings.
- [ ] `ELMOS-DR-016` Retain replay-compatible workflow/activity code and data converters.
- [ ] `ELMOS-DR-017` Restore histories and run replay verification before resuming.
- [ ] `ELMOS-DR-018` Reconcile workflow projection, task leases, checkpoints, and side-effect receipts with PostgreSQL/CAS.
- [ ] `ELMOS-DR-019` Route non-replayable or ambiguous runs to MANUAL_RECOVERY with evidence.
### External side-effect reconciliation

- [ ] `ELMOS-DR-020` Reconcile repository branches/PRs/checks, webhooks, object uploads, notifications, signing, billing, and exports using idempotency receipts and provider state.
- [ ] `ELMOS-DR-021` Never retry UNKNOWN_RESULT before checking whether the side effect happened.
- [ ] `ELMOS-DR-022` Use fencing to reject stale attempts after recovery.
- [ ] `ELMOS-DR-023` Produce a decision record for retry, accept existing, compensate, forward-fix, or manual intervention.
### Recovery scopes

- [ ] `ELMOS-DR-024` Implement single task/project, runner/site, tenant, portfolio, service, storage, database, and regional recovery.
- [ ] `ELMOS-DR-025` Resume from last compatible sealed checkpoint rather than restarting completed stages.
- [ ] `ELMOS-DR-026` Allow partial portfolio recovery while quarantining ambiguous shards.
- [ ] `ELMOS-DR-027` Rebuild derived symbol/index/dashboard state from immutable sources.
### Exercises and evidence

- [ ] `ELMOS-DR-028` Schedule tabletop, component restore, partial outage, regional failover, corrupted object, expired key, non-replayable workflow, and full portfolio exercises.
- [ ] `ELMOS-DR-029` Use isolated test endpoints and synthetic fixtures.
- [ ] `ELMOS-DR-030` Generate DR evidence with inputs, actions, timings, loss, discrepancies, decisions, and remediation.
- [ ] `ELMOS-DR-031` Block production readiness when restore evidence is stale or unsuccessful.

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

- [ ] Restore PostgreSQL to a point before/after a controlled mutation and verify RLS.
- [ ] Delete/corrupt CAS objects and recover/reconcile them.
- [ ] Restore and replay representative Temporal histories across versions.
- [ ] Simulate PR creation response loss and prevent duplicate PR.
- [ ] Run tenant and portfolio recovery while preserving completed shards.

Run repository-native format, lint, typecheck, unit, integration, packaging, and security commands. Also run the package validators when Skill content or schemas change:

```bash
python3 scripts/validate_skill_bundle.py
python3 scripts/validate_json_schemas.py
python3 -m unittest discover -s tests -v
```

## Definition of done

- [ ] Backups are routinely restored and verified.
- [ ] Recovery meets measured RPO/RTO or reports exact gaps.
- [ ] No duplicate external effect or double billing occurs.
- [ ] DR evidence is current and a production certification input.

Additionally:

- [ ] No placeholder, TODO-only, mock-only, or documentation-only implementation is counted as production completion.
- [ ] All modified public contracts are versioned and compatibility-tested.
- [ ] All side effects are idempotent or reconciled.
- [ ] Critical actions are authorized, audited, and observable.
- [ ] Evidence identifies exact source, toolchain, rule/model/policy, commands, results, and residual risk.
- [ ] Static bundle validation is described accurately as structural validation only.

## Failure handling and handoff

Classify failures as `ENVIRONMENT`, `DEPENDENCY`, `CODE`, `POLICY`, `SECURITY`, `DATA`, `CAPACITY`, `PROVIDER`, or `UNKNOWN`. Preserve successful checkpoints. Put ambiguous side effects in `UNKNOWN_RESULT`/`MANUAL_RECOVERY`; reconcile before retrying. Update the implementation plan with status, commit, commands, measured wall-clock duration, cost, evidence digest, blockers, and the next dependency-resolved task.
