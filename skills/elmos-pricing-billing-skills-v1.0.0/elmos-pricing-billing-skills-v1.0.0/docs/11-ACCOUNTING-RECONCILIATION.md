# Accounting and Reconciliation Engineering Guide

## 1. Technical accounting goals

The system must preserve enough immutable facts for approved accountants to determine cash, customer credit liability, receivables, revenue, refunds, discounts, vendor COGS, payment fees and deferred/recognized project revenue.

## 2. Example balanced transactions

### Paid top-up

```text
Dr Provider/Bank Clearing Asset
Cr Customer Paid Credit Liability
```

### Reserve credits

```text
Dr Customer Available Credit Liability
Cr Customer Reserved Credit Liability
```

### Capture usage

```text
Dr Customer Reserved Credit Liability
Cr Usage Revenue
```

### Release unused reserve

```text
Dr Customer Reserved Credit Liability
Cr Customer Available Credit Liability
```

### Refund

Use policy-approved reversal/contra-revenue entries linked to the original transaction; exact accounts depend on settlement state and accounting policy.

## 3. Reconciliation keys

- provider account + provider event/charge/settlement ID
- invoice ID and line IDs
- ledger transaction ID
- wallet ID and task/project/subscription ID
- bank settlement date/batch
- currency and gross/fee/net amounts

## 4. Exception categories

- provider succeeded, internal missing
- internal captured, provider failed
- amount/currency/fee mismatch
- duplicate provider event
- invoice paid but ledger open
- wallet credited without cash/approved grant
- late usage after settlement
- migration opening difference

Each exception has owner, severity, amount exposure, aging, evidence and resolution transaction.

## 5. Close controls

- All batches imported and hashed
- Suspense balance reviewed
- Ledger balanced by currency and credit class
- Wallet projection equals ledger
- Provider settlement equals payment facts within approved timing differences
- Invoice subledger equals receivable accounts
- Usage revenue traceable to rated events and authorizations
- Refunds/chargebacks reconciled
- Period locked; late events follow adjustment policy

This guide is an engineering model, not a substitute for the organization's approved accounting policy.
