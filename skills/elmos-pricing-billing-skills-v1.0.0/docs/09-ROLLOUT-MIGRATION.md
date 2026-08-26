# Rollout and Migration Plan

## Phase 0 — Instrument only

Add correlation IDs and usage capture without billing. Verify event completeness against task runtime.

## Phase 1 — Shadow rating

Calculate hypothetical charges using the new price book. Compare with manual/legacy expectations. No customer balance changes.

## Phase 2 — Wallet and ledger pilot

Create opening balances for internal/employee tenants, enable reserve/capture and run daily reconciliation.

## Phase 3 — Paid canary

Enable a small low-risk customer cohort with explicit terms and support coverage. Automated rollback on duplicate charge, negative balance, cap breach, or unexplained shadow difference.

## Phase 4 — Subscription and projects

Enable recurring plans, included credits, capped projects and fixed SKUs in controlled order.

## Phase 5 — Enterprise/BYOK

Activate postpaid, committed spend, private deployment and SLA only after contract and finance operations are ready.

## Phase 6 — Full migration and retirement

Migrate remaining tenants in waves. Keep legacy read-only for audit and rollback until stability and retention criteria are met.

## Opening balance protocol

1. Export source balances with source IDs and snapshot timestamp.
2. Clean duplicates and classify negative/unknown balances.
3. Approve the total by currency/credit class.
4. Post balanced opening transactions with source hashes.
5. Recompute wallet projections.
6. Reconcile source total, ledger total and projection total.
7. Freeze the migration batch manifest and evidence.

## Rollback principle

Rollback stops new traffic and restores routing/configuration. It does not delete financial facts. Incorrect effects are reversed through compensating entries and customer-visible documents.
