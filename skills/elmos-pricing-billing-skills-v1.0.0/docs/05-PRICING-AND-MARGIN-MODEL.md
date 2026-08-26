# Pricing, Estimation, and Margin Model

## 1. Internal task cost

```text
actual_internal_cost =
    managed_model_input
  + managed_model_output
  + cache_write
  + cache_read
  + embeddings_and_rerank
  + sandbox_cpu
  + sandbox_gpu
  + browser_automation
  + test_execution
  + storage
  + network_egress
  + third_party_tools
  + allocated_platform_variable_cost
```

BYOK removes only customer-owned model-provider cost from Elmos pass-through unless the contract says otherwise.

## 2. Customer usage price

```text
customer_price =
    rated_billable_usage
  + platform_or_orchestration_fee
  + risk_or_quality_mode_modifier
  - discounts
  - service_credits
  + applicable_tax
```

All terms are versioned and the calculation stores a human-readable breakdown.

## 3. Capped project quote

```text
recommended_cap =
  P90(expected_variable_cost)
  + acceptance_cost
  + support_cost
  + scope_risk_reserve
  + target_contribution
```

Customer settlement is `min(actual customer-rated amount, accepted cap)` unless an approved change order creates additional authority.

## 4. Fixed-price quote

```text
fixed_price =
  P80_or_P90_historical_total_cost / (1 - target_margin)
  + non-variable delivery obligations
```

Only enable for segments whose cost variance and acceptance failure rate stay below approved thresholds.

## 5. Estimator outputs

Required fields:

- `estimated_cost_p50`, `p80`, `p90`
- `recommended_hard_cap`
- `machine_runtime_p50/p90_seconds`
- `human_effort_reference_hours_or_days`
- `confidence`, `risk_factors`, `similar_sample_count`
- expected usage by resource category
- estimator/model/rule version

## 6. Quality modes

| Mode | Routing intent | Typical behavior |
|---|---|---|
| Economy | minimum expected cost | cost-efficient model, limited cross-review, essential tests |
| Balanced | default value | economical executors + stronger reviewer, standard test suite |
| Best Quality | maximum assurance | stronger models, multi-agent review, broader verification |

Quality mode affects routing and risk reserve; it does not waive the hard budget cap.

## 7. Margin metrics

- Gross margin = recognized revenue − direct COGS
- Contribution margin = revenue − direct COGS − allocated variable platform cost
- Cost per successful task
- Refund-adjusted revenue per task
- Quote error = actual / quoted midpoint and actual / cap
- Cache savings, routing savings, retry waste, test cost, auto-repair cost

## 8. Price governance

1. Finance validates vendor rates and accounting mapping.
2. Product validates customer value and segment behavior.
3. Engineering validates implementability and meter coverage.
4. Security/legal/tax review applies where needed.
5. Approver activates a future-dated immutable price-book version.
6. Canary tenants verify; automated rollback stops new authorizations if guardrails fail.
