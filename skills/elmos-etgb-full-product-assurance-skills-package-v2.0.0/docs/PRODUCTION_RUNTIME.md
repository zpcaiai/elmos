# ETGB Production Runtime

## Control plane

A production ETGB run is identified by immutable `candidate_digest` and `plan_digest`, then executed as stable shards. The authoritative state is persisted in PostgreSQL/Temporal; executors hold only leases. State changes use compare-and-set on revision and fencing token.

```text
PLANNED → PREPARING → BASELINING
→ TRANSFORMING | GENERATING → BUILDING
→ VALIDATING → SCORING → PUBLISHING → COMPLETED
```

Exceptional states are `PAUSING`, `PAUSED`, `RESUMING`, `CANCELLING`, `COMPENSATING`, `CANCELLED`, `FAILED`, and `BLOCKED`.

## Transaction boundaries

The following pairs must be atomic or connected by an outbox/idempotent consumer:

- run transition + transition audit;
- phase result + checkpoint;
- usage total + usage event;
- evidence metadata + publication event;
- release decision + release event.

A process crash between database commit and message publication is recovered from the outbox.

## Workers

Transformation/generation and validation use separate Environments and authority. A worker heartbeat renews a bounded lease. Takeover increments fencing; stale workers lose mutation, publication and billing rights.

## Adapter SDK

`etgb/harness.py` is a local executable reference. Production adapters implement the contract in `integrations/harness/adapter-contract.yaml`. They must return artifact paths, side-effect receipts and usage, and must expose compensation/cleanup.

## Pause, resume and cancellation

Pause completes the current atomic side effect, checkpoints and releases the lease. Resume validates all digests and requires a higher fencing token. Cancellation reconciles charges, compensates promised side effects, preserves evidence and records unresolved effects.

## Production readiness

A control-plane integration is not ready until the 100-scenario cross-cutting suite has been executed with real infrastructure, including crash/reboot, duplicate events, outbox failure, budget exhaustion, hidden-test access denial, RLS, stale fencing and evidence tampering.
