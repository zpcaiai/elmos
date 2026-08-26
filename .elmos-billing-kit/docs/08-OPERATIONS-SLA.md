# Operations, SLO, and Incident Runbook

## 1. Suggested SLO categories

Set actual numeric targets after measuring the deployed stack.

- Quote generation availability and latency
- Budget authorization availability and latency
- Usage ingestion lag and loss rate
- Settlement completion latency
- Payment webhook processing lag
- Refund completion latency
- Daily reconciliation completion
- Ledger projection freshness
- Admin exception queue age

## 2. Zero-tolerance invariants

Immediately stop affected writes on:

- Unbalanced ledger transaction
- Duplicate customer charge or duplicate refund
- Unauthorized negative balance
- Hard budget-cap breach
- Cross-tenant exposure
- Evidence of secret leakage
- Irrecoverable ledger/invoice data loss

## 3. Kill switches

Independent controls:

- disable new paid task authorization
- disable new top-ups
- disable usage capture while continuing durable metering
- disable refunds except emergency manual path
- freeze one provider or one tenant
- enter global billing read-only mode

Every switch change is audited and time-bounded where possible.

## 4. Reconciliation cadence

- Near-real-time: usage vs task runtime, reserve vs task state
- Hourly: wallet projection vs ledger, payment events vs intents
- Daily: provider settlement vs payment vs invoice vs ledger
- Monthly: vendor bills vs rated internal cost; revenue and COGS close

## 5. Recovery order

1. Stop risk expansion.
2. Preserve logs, events, database snapshot and provider evidence.
3. Identify authoritative facts and affected tenants/time window.
4. Replay in shadow environment.
5. Verify ledger balance, idempotency, cap and reconciliation.
6. Apply compensation or controlled replay.
7. Resume canary traffic.
8. Complete incident report and control improvement.

## 6. Required incident report fields

- Incident ID, severity, start/end and discovery time
- Affected tenants, transactions, tasks and amount range
- Customer impact and notification
- Timeline and contributing factors
- Authoritative evidence and reconciliation result
- Compensation/refund actions
- Root cause and why controls failed
- Corrective actions, tests and owners
