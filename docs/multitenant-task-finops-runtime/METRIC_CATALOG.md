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
| `rollout_state_version` | account/environment/feature | Optimistic version of an ordered local feature-flag decision. It does not prove provider or environment rollout. |
| `lifecycle_state_version` | account/lifecycle job | Monotonic export/deletion state version; `BLOCKED`, `UNKNOWN_RESULT`, and `RECONCILING` are non-success. |
| `exported_row_count`, `exported_byte_count` | account/lifecycle job | Exact cumulative local export counts bound to the page-checkpoint chain and terminal manifest. They are not provider-delivery evidence. |

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
| `provider_reported_minor` | account/provider/currency/period | Exact scale-6 amount reported by the provider; absent or `UNKNOWN` provider outcome cannot be inferred as zero. |
| `ledger_recorded_minor` | account/provider/currency/period | Exact scale-6 local ledger amount for the same currency and half-open period. |
| `settlement_difference_minor` | account/provider/currency/period | Provider amount minus ledger amount. Only exact zero with independent evidence may be `MATCHED`; otherwise it is `UNRECONCILED` or `UNKNOWN`. |
| `model_cache_observation_count` | model/provider/currency | Count of immutable model observations in the bounded local projection. Duplicate observation IDs fail closed. |
| `model_cache_hit_count` | model/provider/currency | Count of observations with a positive cache-read token count. A claimed hit without cache-read tokens is invalid. |
| `model_cache_hit_ratio` | model/provider/currency | Exact cache hits divided by observation count at scale 9; it is not a provider cache guarantee. |
| `model_input_tokens`, `model_output_tokens` | model/provider | Exact non-negative token totals, never mixed across model/provider dimensions. |
| `cache_read_tokens`, `cache_write_tokens` | model/provider | Exact cache token counters retained with the observation scope. They do not prove provider cache billing. |
| `model_cost_per_output_token_minor` | model/provider/currency | Exact local cost divided by output tokens; `NULL` when no output tokens exist. Provider invoice reconciliation remains separate. |

`mtf_task_financial_summary` is a rebuildable, account-scoped projection. Its
`CURRENT`, `PARTIAL`, or `UNRECONCILED` qualification and event watermark must
travel with every value. A local SQL row is not provider invoice, payment,
bank, accounting, tax, independent-review, or production-certification
evidence. The exact `elmos-observability-finops` dependency remains
`UNRESOLVED`.

## Rebuild, aggregate, and export metadata

| Field | Grain | Definition and boundary |
| --- | --- | --- |
| `generation_version` | account/projection generation | Monotonic head generation, exactly one above the caller's expected generation. |
| `input_continuity` | account/projection generation | `COMPLETE` is required to publish a head. `UNKNOWN` never publishes as current. |
| `run_count`, `bucket_count` | rebuild | Exact JSONB payload element counts persisted with the rebuild. |
| `run_payload_digest`, `bucket_payload_digest` | rebuild | SHA-256 digests of PostgreSQL-normalized JSONB payloads; they are not external signatures. |
| `journal_checksum` | rebuild window | Digest of the ordered journal inputs used for local run reconstruction. |
| `hourly_checksum`, `daily_checksum` | rebuild window/grain | Digests of deterministic local aggregate buckets for the exact window and grain. |
| `external_evidence_state` | projection generation | Remains `NOT_RUN` until separately authorized external evidence exists. |
| `provider_outcome` | projection generation | Remains `UNKNOWN`; local rows cannot manufacture provider success. |
| `production_certification` | projection generation | Remains `NOT_CERTIFIED`. |
| `externally_qualified` | current projection row | Always false in the current V77.2 views. |
| export `row_count`, `content_digest` | account/generation/format | Exact local CSV/JSON data-row count and byte digest. They do not prove object-provider delivery. |

`mtf_current_task_run_projections` and
`mtf_current_task_aggregate_buckets` expose the exact current
organization/account/rebuild/generation tuple plus the non-success evidence
states. All external execution and production qualification remain `NOT_RUN`
and `NOT_CERTIFIED`.
