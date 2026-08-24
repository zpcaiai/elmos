# Multi-tenant task and FinOps metric catalog

This catalog defines the repository projection fields. It does not establish
that collectors, dashboards, provider bills, or production workloads have run.
Every consumer must preserve organization, account, task, currency, event
watermark, `as_of`, reconciliation status, and qualification where present.

## Operational metrics

| Metric | Grain | Definition and boundary |
| --- | --- | --- |
| `root_task_limit` | account | Constant `3`. It is the platform hard maximum, not a plan entitlement. |
| `active_root_tasks` | account | Count of slots in `ACTIVE` or `RECONCILING`; therefore unknown outcomes continue to consume capacity. |
| `waiting_root_tasks` | account | Count of account jobs in `QUEUED` plus `WAITING_FOR_SLOT`. |
| `available_root_slots` | account | Count of `FREE` slot rows. It must remain between 0 and 3. |
| `queue_position` | task | One plus higher-priority ready jobs, with enqueue time and job ID tie-breakers. It is a current projection, not a promised start time. |
| `event_sequence` | task event | Monotonic per-task sequence used to detect gaps and replay after a cursor. |
| `progress_percent` | task/event | Monotonic 0-99 while non-success; exactly 100 only for `SUCCEEDED`. |
| `elapsed_millis` | task | Monotonic elapsed execution value; pause and retry semantics must be read with events. |
| `eta_p50_millis`, `eta_p90_millis` | task | Non-negative remaining-time estimates with P90 at least P50. They are estimates, not SLOs. |
| `reconciliation_status` | account/task | `UNKNOWN` for reconciling capacity or task outcomes; terminal task state alone does not reconcile finance. |

The account metrics come from `mtf_account_concurrency_status`; task event and
progress fields come from `mtf_task_events` and `mtf_task_progress`.

## Financial metrics

| Metric | Grain | Exact definition and boundary |
| --- | --- | --- |
| `exact_quantity` | usage event | Provider quantity at scale 9 with an explicit usage unit. Quantities with different units are never summed as one measure. |
| `base_cost_minor` | usage event/currency | Source quantity times effective unit price and FX, recomputed at the write boundary and stored at scale 6. |
| `estimated_cost_minor` | task/currency | Sum of usage entries whose cost state is `ESTIMATED`. |
| `reserved_cost_minor` | task/currency | Sum of usage entries whose cost state is `RESERVED`. |
| `posted_cost_minor` | task/currency | Sum of usage entries whose cost state is `POSTED`. |
| `final_cost_minor` | task/currency | Sum of usage entries whose cost state is `FINAL`; it must not be inferred from an estimate. |
| `recognized_revenue_minor` | task/currency | Sum of revenue-recognition entries or entries in `RECOGNIZED` state. It is not cash. |
| `collected_cash_minor` | task/currency | Sum of cash-receipt entries or entries in `COLLECTED` state. It is not recognized revenue. |
| `refunds_minor` | task/currency | Signed refund ledger amount; presentation must retain its sign. |
| `gross_profit_minor` | task/currency | Current SQL projection: recognized revenue minus `coalesce(final cost, posted cost, 0)`, at scale 6. |
| `gross_margin_ratio` | task/currency | Gross profit divided by recognized revenue; `NULL` when recognized revenue is zero. |
| `unreconciled_usage_count` | task/currency | Usage entries whose reconciliation status is not `RECONCILED`. |
| `unreconciled_revenue_count` | task/currency | Revenue entries not reconciled or not fully allocated by absolute amount. |
| allocation variance | revenue entry/currency | Source amount minus the sum of allocations. A non-zero scale-6 variance is unreconciled, never rounded away in presentation. |

`mtf_task_financial_summary` is a rebuildable, account-scoped projection. Its
`CURRENT`, `PARTIAL`, or `UNRECONCILED` qualification and event watermark must
travel with every value. A local SQL row is not provider invoice, payment,
bank, accounting, tax, independent-review, or production-certification
evidence. The exact `elmos-observability-finops` dependency remains
`UNRESOLVED`.
