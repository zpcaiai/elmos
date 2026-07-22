---
name: suite-data-migration-history-archive-and-reconciliation
description: Plan and validate enterprise suite configuration, reference, master, balance, open transaction, history, attachment, audit, and archive migration. Use for migration waves, control totals, reject handling, financial and inventory reconciliation, CRM reconciliation, historical tiering, and authority transfer.
---

# Suite Data Migration

## Execute

1. Enforce the DAG: configuration, reference, master, opening balance, open transaction, required history, attachment, and derived index.
2. Scope each wave by company, country, business unit, module, object, date, status, and tenant.
3. Select migrate, transform, merge, split, archive, reference-only, recompute, or retire per object.
4. Record source count, accepted, rejected, target count, amount, hash, Crosswalk, error, owner, and evidence frontier.
5. Reconcile trial balance, ledgers, AR, AP, assets, tax, currency, inventory quantity and value, lots, reservations, sales, procurement, and CRM independently.
6. Choose active target, read-only archive, analytical lakehouse, legacy read-only, or regulatory archive for history.

## Hard gates

Block transactions before master data, unresolved rejects, balance differences, valuation differences, missing authority, inaccessible archive, or unapproved history scope. Equal row count is never sufficient financial evidence.
