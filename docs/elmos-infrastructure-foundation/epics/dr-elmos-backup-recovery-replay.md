# Backup, Restore, Disaster Recovery, Reconciliation, and Deterministic Replay

- Skill: `elmos-backup-recovery-replay`
- Priority: `P1`
- Phase: `G8`
- Dependencies: `elmos-temporal-task-reliability`, `elmos-content-addressed-cache`, `elmos-evidence-pack-offline-verification`, `elmos-observability-finops`

## Objective

Make service, region, database, storage, runner, and workflow failures recoverable within defined RPO/RTO and provable through exercises.

## Task groups

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

## Validation

- [ ] Restore PostgreSQL to a point before/after a controlled mutation and verify RLS.
- [ ] Delete/corrupt CAS objects and recover/reconcile them.
- [ ] Restore and replay representative Temporal histories across versions.
- [ ] Simulate PR creation response loss and prevent duplicate PR.
- [ ] Run tenant and portfolio recovery while preserving completed shards.

## Exit gate

- [ ] Backups are routinely restored and verified.
- [ ] Recovery meets measured RPO/RTO or reports exact gaps.
- [ ] No duplicate external effect or double billing occurs.
- [ ] DR evidence is current and a production certification input.
