# Production runtime operations

This runbook is executable guidance for the repository-owned runtime. Local
tests and chart rendering do not close the target-environment evidence fields;
the external gate must record real execution and independent verification.

## Availability

1. Check `up`, readiness, HTTP 5xx rate, and the exact component rollout.
2. Stop new billable work if billing or scheduler readiness is degraded.
3. Preserve `UNKNOWN` provider and settlement outcomes; do not retry blindly.
4. Use the content-addressed external-gate report and the approved change ID
   for any rollback or incident handoff.

## Recovery

Scheduled-loop failures, stale leases, unpublished outbox rows, and uncertain
model/tool calls are reconciled by the dedicated recovery loops. Inspect the
durable PostgreSQL state first; Redis is only an ephemeral cache/semaphore.
Never delete a dispatch, reservation, ledger entry, or receipt to make a
dashboard green.

## Worker journal

`elmos_production_runtime_worker_journal_healthy` must remain `1`. A zero value
means the worker stops accepting new work and requires durable-volume and
journal integrity investigation. A worker restart is safe only after the
latest checkpoint and completion-outcome journal records are available.

## Performance

The declared SLO thresholds are 100 ms scheduler claim P95, 150 ms billing
reserve/settle P95, and 2 s projection freshness P95. They are initial gates,
not calibrated production baselines. The target load gate must run the
independent holdout workload and retain raw k6 output.

## Migration rollback

Application rollback uses Helm atomic rollback. Database migrations are
expand/contract and forward-fix only: a failed application rollout must not
run destructive reverse SQL. Before a release, the migration job must finish
with the dedicated migration role, the schema history must be captured, and a
forward-compatible corrective migration must be approved for any rollback
scenario.
