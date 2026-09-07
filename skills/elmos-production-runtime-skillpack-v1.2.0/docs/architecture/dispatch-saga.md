# Durable Dispatch Saga

The dispatch intent closes the scheduler crash window between Billing reservation and Attempt creation.

## State sequence

```text
T1 Scheduler DB
READY -> RESERVING
create dispatch_intent(RESERVING)
commit

Billing.reserve(stable-key)
commit in Billing

T2 Scheduler DB
persist reservation_id
dispatch_intent -> RESERVED
work_item -> RESERVED
commit

T3 Scheduler DB
allocate fence atomically
create Attempt
create Lease
dispatch_intent -> ATTEMPT_CREATED -> DISPATCHING
work_item -> DISPATCHING
commit

Network dispatch to exact Worker

T4 Scheduler DB
worker ACK
dispatch_intent -> ACKED
work_item -> RUNNING
attempt -> RUNNING
commit
```

## Crash recovery

- RESERVING without reservation: retry same idempotent Billing reserve.
- Billing succeeded but intent still RESERVING: query Billing by idempotency key, attach reservation, continue.
- RESERVED without attempt: create attempt/fence/lease.
- DISPATCHING without ACK: query worker/lease state or re-dispatch same attempt identity.
- ACKED/RUNNING with expired lease: mark attempt LOST and retry with newer fence.
