# ELMOS token and platform-credit meter baseline

Date: 2026-07-28

Meter version: `v1`

Status: `DRAFT`

## Meter definitions

`model-token-v1` aggregates the model provider's accepted input-token and
output-token quantities using `SUM`. A missing, late, timed-out or unreconciled
provider result is `UNKNOWN`; it is never silently recorded as zero.

`platform-credit-v1` aggregates accepted immutable ELMOS operation-usage events
using `SUM`:

| Operation | Rate |
|---|---:|
| Repository discovery and analysis | 5 credits / execution |
| Migration or translation plan | 15 credits / execution |
| Verified generation or migration | 40 credits / execution |
| Isolated Runner | 1 credit / started minute |
| Evidence-pack verification | 10 credits / execution |

A composite job consumes the sum of its accepted operation events and, when it
uses a model, the accepted provider token quantity. Rejected preflight requests
consume neither meter. Runner usage is based on accepted started minutes rather
than a fixed job label.

## Window and correction rules

- Free-trial allowance uses one 14-day term window.
- Paid allowances use monthly windows anchored to the subscription anniversary,
  including an annual subscription.
- Unused quantities do not roll over.
- Corrections append a versioned compensating usage event; accepted source
  events are not mutated or deleted.
- A duplicate idempotency key must return the original usage-event decision.
- An exhausted token or credit allowance denies additional metered work. There
  is no automatic overage charge in version `v1`.

## Unresolved implementation evidence

- Authenticated tenant and legal-entity binding for customer usage:
  `NOT_CONFIGURED`.
- Provider-native token receipt ingestion and reconciliation: `NOT_RUN`.
- Durable usage-event ledger and outbox integration: `NOT_RUN`.
- Production anomaly thresholds, late-arrival window and independent
  reconciliation: `NOT_RUN`.
- Authorized external execution and representative customer workload:
  `NOT_RUN`.

The current code and API expose deterministic definitions and limits only. They
do not claim certified usage aggregates, billable charges, invoices or
production metering.
