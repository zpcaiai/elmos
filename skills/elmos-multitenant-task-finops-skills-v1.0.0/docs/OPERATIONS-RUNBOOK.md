# Operations Runbook

## Slot appears stuck

1. Inspect task state, workflow status, slot lease generation, node attempt lease, latest checkpoint, and side-effect receipts.
2. Do not manually clear a slot while an external effect may still be running.
3. Mark `UNKNOWN_RESULT`, run reconciliation, and release only with the current generation after a safe decision.
4. Record operator identity, reason, evidence, and resulting queue promotion.

## Workflow exists but database does not show it

Use deterministic workflow IDs and the outbox/Temporal search attributes to reconcile. Never start a second workflow until the original ID is confirmed absent or terminal.

## Progress is stale but task is running

Check outbox age, event-bus health, projector offset, and SSE gateway. Critical execution state remains in PostgreSQL/Temporal; rebuilding the progress projection must not restart the task.

## Cost is incomplete

Show posted data and `as_of` with reconciliation status. Check provider receipts, price-book mapping, FX snapshot, delayed finalization, and correction linkage. Do not label partial cost as final.

## Revenue differs from payment cash

Reconcile billed, recognized, and collected ledgers separately. A payment can precede or follow recognition; payment fees, taxes, credits, and refunds must not be silently netted into one number.
