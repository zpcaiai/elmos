# Billing and Accounting

## Layers

Separate:

1. raw provider usage;
2. provider price version;
3. actual infrastructure/provider cost;
4. customer commercial pricing version;
5. discounts/contracts;
6. customer credit charge;
7. ledger movement;
8. accounting journal;
9. margin analytics.

Historical usage must never be repriced using current prices.

## Reconciliation

Avoid joining raw ledger and raw reservation tables in one aggregate, because one-to-many joins multiply amounts.

Aggregate each source independently, then join the aggregates by wallet/accounting window.

## Double entry

Every posted journal must balance per currency:

`SUM(debit) = SUM(credit)`

Corrections are new compensating journals, never edits to historical financial records.
