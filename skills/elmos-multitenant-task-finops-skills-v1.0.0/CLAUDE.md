# CLAUDE.md — Elmos Multi-Tenant Task Control & FinOps

Use the Skills under `.agents/skills/` as executable implementation specifications.

## Primary command

```text
$elmos-multitenant-task-finops-orchestrator
```

## Execution order

Follow `skill-manifest.json`; do not skip identity/RLS, admission slots, Temporal lifecycle, recovery, or financial ledgers to reach UI work sooner.

## Non-negotiable behavior

- One authenticated account has at most three simultaneously active root tasks across all tenants.
- Extra submissions become durable `WAITING_FOR_SLOT` records.
- Use atomic PostgreSQL slot rows with lease generation; never count-then-start.
- Preserve immutable events, checkpoints, side-effect receipts, usage events, and revenue entries.
- Reconcile `UNKNOWN_RESULT` before retrying ambiguous side effects.
- Keep internal cost, customer charge, recognized revenue, and collected cash distinct.
- Enforce tenant isolation in the API, database, event subscriptions, and object storage.

Before claiming completion, run the target repository's tests plus this package's `./verify.sh`, and produce an evidence-bound execution report.
