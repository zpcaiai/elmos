# Billing State Machines

## 1. Task quote and execution

```text
DRAFT_ESTIMATE
  -> QUOTED
  -> ACCEPTED
  -> AUTHORIZED
  -> RUNNING
  -> PAUSED_BUDGET -> AUTHORIZED/RUNNING | CANCELED
  -> COMPLETED | FAILED | CANCELED
  -> SETTLING
  -> SETTLED | SETTLEMENT_REVIEW
```

Guards:

- `QUOTED → ACCEPTED`: quote not expired; scope/hash unchanged.
- `ACCEPTED → AUTHORIZED`: reserve succeeds or enterprise credit available.
- `RUNNING → PAUSED_BUDGET`: predicted next billable node exceeds hard cap.
- `SETTLING → SETTLED`: usage window closed, capture balanced, unused reserve released.

## 2. Budget authorization

```text
REQUESTED -> ACTIVE -> PARTIALLY_CAPTURED -> CAPTURED
                    -> RELEASED
                    -> EXPIRED
                    -> REVIEW
```

A released/expired amount cannot later be captured without a new authorization.

## 3. Project contract

```text
DISCOVERY -> PROPOSED -> ACCEPTED -> ACTIVE
ACTIVE -> MILESTONE_REVIEW -> ACTIVE | COMPLETED
ACTIVE -> CHANGE_REQUESTED -> CHANGE_APPROVED -> ACTIVE
ACTIVE -> PAUSED | TERMINATED
COMPLETED -> SETTLED
```

Scope drift creates `CHANGE_REQUESTED`; it does not silently mutate the active baseline.

## 4. Subscription

```text
DRAFT -> TRIALING -> ACTIVE -> PAST_DUE -> SUSPENDED -> CANCELED
                    ACTIVE -> PAUSED -> ACTIVE
                    ACTIVE -> CANCELED_AT_PERIOD_END -> CANCELED
```

Entitlement availability during grace/past_due is policy-driven and versioned.

## 5. Invoice

```text
DRAFT -> OPEN/FINALIZED -> PARTIALLY_PAID -> PAID
                       -> VOID
                       -> UNCOLLECTIBLE
OPEN/PAID -> CREDIT_NOTE_ISSUED (separate document)
```

Finalized invoices are immutable.

## 6. Payment

```text
CREATED -> REQUIRES_ACTION -> AUTHORIZED -> CAPTURED -> SETTLED
CREATED/AUTHORIZED -> CANCELED
CAPTURED/SETTLED -> PARTIALLY_REFUNDED -> REFUNDED
CAPTURED/SETTLED -> DISPUTED -> WON | LOST
```

Provider events can arrive out of order; transition logic must be monotonic and event-time aware.

## 7. Refund

```text
REQUESTED -> ELIGIBILITY_REVIEW -> APPROVED -> PROCESSING
PROCESSING -> SUCCEEDED | PARTIAL | FAILED_RETRYABLE | FAILED_FINAL
REQUESTED/REVIEW -> REJECTED
```

Wallet reversal and provider refund are correlated but independently recoverable.

## 8. Price book

```text
DRAFT -> IN_REVIEW -> APPROVED -> SCHEDULED -> ACTIVE -> RETIRED
```

Only one version may be active for a given scope/currency/time interval unless an explicit experiment allocation resolves ambiguity.
