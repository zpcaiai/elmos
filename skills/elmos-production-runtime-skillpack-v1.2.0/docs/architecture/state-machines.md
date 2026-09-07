# Runtime State Machines

## WorkItem

```text
PENDING
  -> READY
  -> RESERVING
      -> WAITING_FOR_CREDIT
      -> RESERVED
  -> DISPATCHING
  -> RUNNING
      -> SUCCEEDED
      -> RETRY_WAIT -> READY
      -> FAILED
      -> CANCELLED
```

Terminal states are immutable.

## DispatchIntent

```text
CREATED
 -> RESERVING
 -> RESERVED
 -> ATTEMPT_CREATED
 -> DISPATCHING
 -> ACKED
 -> COMPLETED

Any non-terminal state may move to ABORTED through a compensating recovery path.
```

## Attempt

`CREATED -> RUNNING -> SUCCEEDED | FAILED | TIMED_OUT | LOST | CANCELLED`

## Credit reservation

`ACTIVE -> SETTLED | RELEASED | EXPIRED`

## Idempotency record

`IN_PROGRESS -> SUCCEEDED | FAILED`

An IN_PROGRESS record older than its operation-specific recovery window must be reconciled, never blindly duplicated.
