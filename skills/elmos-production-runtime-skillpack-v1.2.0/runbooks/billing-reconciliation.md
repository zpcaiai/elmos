# Billing Reconciliation Runbook

1. Select accounting window and wallet set.
2. Snapshot opening balances.
3. Aggregate ledger independently.
4. Aggregate active reservations independently.
5. Aggregate top-ups independently.
6. Aggregate final usage independently.
7. Compare computed close with wallet projection.
8. Inspect usage without settlement and settlement without usage.
9. Inspect expired ACTIVE reservations.
10. Correct only with compensating ADJUSTMENT/REFUND/RELEASE entries.
11. Re-run until unexplained delta = 0.
