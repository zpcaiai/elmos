# ELMOS CNY self-serve pricing catalog baseline

Date: 2026-07-28

Catalog version: `2026-07-28.1`

Status: `DRAFT`

## Bounded scope

This baseline introduces a customer-visible CNY catalog for exactly three
self-serve plans: a 14-day free trial, a monthly Pro plan and an annual Pro
plan. It reuses the existing Product, Price Book, Subscription and Entitlement
boundaries in `V10__commercial_operations_and_asset_reuse.sql`; it does not
create a parallel invoice, payment, tax, revenue or journal system.

The authoritative engineering quantities are integer token counts, integer
platform credits and CNY amounts with two decimal places. The web representation
uses integer fen. The Java commercial boundary uses `BigDecimal` with an exact
scale of two for money and scale zero for allowances.

## Catalog decision

| Plan | Price | Allowance window | Model tokens | Platform credits |
|---|---:|---|---:|---:|
| Free trial | CNY 0.00 / 14 days | trial term | 2,000,000 | 60 |
| Pro monthly | CNY 129.00 / month | monthly | 20,000,000 | 600 |
| Pro annual | CNY 1,290.00 / year | monthly refill | 25,000,000 / month | 750 / month |

The annual contractual display ceilings are 300,000,000 tokens and 9,000
credits. Monthly and annual paid allowances refill monthly and do not roll over.
The default overage policy is `HARD_STOP_NO_AUTOMATIC_CHARGE`.

## Unresolved authorities and assumptions

- Seller Legal Entity: `NOT_CONFIGURED`.
- Tax jurisdiction, tax-inclusive/exclusive presentation and invoice rules:
  `NOT_CONFIGURED`.
- Payment provider, merchant account, refund flow and reconciliation:
  `NOT_CONFIGURED`.
- Customer authentication, one-trial-per-customer enforcement and checkout
  authorization: `NOT_CONFIGURED`.
- Model mix and runner cost observations required to validate gross margin:
  `NOT_RUN`.
- Published terms, privacy language, support SLA and customer acceptance:
  `NOT_RUN`.

Because these authorities are unresolved, the catalog stays `DRAFT`; it may be
displayed and inspected but cannot fulfill an order. No customer charge,
invoice, accounting entry or revenue claim is produced by this implementation.

## Competitor reference boundary

The structure is informed by the public Cursor and Windsurf/Devin pattern of a
free entry plan and a USD 20 individual Pro plan. ELMOS amounts and allowances
are independent product decisions, not copied usage entitlements and not a
claim of feature equivalence.
