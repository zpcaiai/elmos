# Dispatch Recovery Runbook

RESERVING:
- query Billing by stable reservation idempotency key;
- attach existing reservation or retry same key.

RESERVED:
- allocate fresh fence;
- create Attempt/Lease;
- continue dispatch.

DISPATCHING:
- query exact worker registration / ACK state;
- retry same dispatch identity or abort and compensate.

RUNNING expired lease:
- mark attempt LOST;
- preserve checkpoint;
- increment fence for next attempt;
- reconcile reservation/model-call state.
