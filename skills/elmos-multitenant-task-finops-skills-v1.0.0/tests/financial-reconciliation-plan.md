# Financial Reconciliation Test Plan

## Cost reconciliation

For each provider and usage type, reconcile immutable `usage_event` rows against provider invoices/receipts and internal runtime telemetry. Validate unit conversion, price-book version, tier, currency, FX snapshot, correction linkage, task/run/node attribution, and finalization status.

Required equations:

```text
posted_task_cost = sum(POSTED + FINAL + CORRECTION base_cost)
final_task_cost exists only when all required sources are final or explicitly waived
period_total_cost = sum(task cost) + explicitly unallocated/shared cost
```

## Revenue reconciliation

Keep quote, charge, credit, refund, recognition, collection, payment fee, tax, write-off, and correction as separate immutable entry kinds. Verify allocations sum exactly to their source entry and never exceed it except where a signed correction reverses prior allocation.

```text
net_billed = charges - credits - refunds
recognized_revenue = sum(RECOGNITION allocations)
collected_cash = sum(COLLECTION allocations)
gross_profit = recognized_revenue - posted_actual_system_cost
gross_margin = gross_profit / recognized_revenue
```

## Required tests

- duplicate provider receipt and webhook replay;
- delayed provider finalization;
- price-book change during a task;
- FX change after posting;
- negative correction and refund;
- prepaid token consumption;
- subscription daily recognition;
- fixed-project milestone allocation;
- unallocated revenue and shared cost pools;
- task/project/tenant/period rollup rebuild;
- decimal precision and currency boundary tests;
- closed accounting period adjustment policy.

Every report must show `as_of`, source coverage, base/reporting currency, recognition basis, reconciliation status, and any unallocated amount.
