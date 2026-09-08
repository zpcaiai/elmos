# Routing math and policy

Elmos optimizes **expected completed-task cost**, not per-call price.

For candidate model `m` and task `t`:

```
invoke_cost = estimated_input_tokens * input_price
            + estimated_cached_input_tokens * cached_input_price
            + estimated_output_tokens * output_price
            + provider/tool fixed costs

expected_total_cost = invoke_cost
                    + (1 - p_success(m,t)) * expected_escalation_cost(t,m)
                    + integration_risk_cost(m,t)
                    + retry_penalty(m,t)

route_score = p_success(m,t) * predicted_quality(m,t) * cache_affinity(m,t)
            / (expected_total_cost * latency_factor(m,t))
```

Before scoring, hard constraints remove ineligible candidates:

- task risk minimum tier;
- context limit;
- provider quota/concurrency;
- hard budget;
- model disabled/unavailable;
- long-horizon requirement;
- reviewer independence requirements.

### Bootstrap policy

Until Elmos has enough local telemetry:

- routine deterministic work starts with Flash/GLM/Qwen;
- standard backend/frontend work starts with Kimi/Grok/DeepSeek/Sonnet depending on task class;
- architecture, high-risk semantics and final certification use Sol/Opus;
- long autonomous migrations use Fable with Sol/Opus verification.

These are bootstrap priors, not immutable rankings. The only immutable constraint is the ten-model allowlist.

## Smart vs manual model selection

Routing begins with `model_selection`. In `smart` mode, the router behaves normally and selects a model independently for each atomic task. In `manual` mode, the user-selected model is a hard constraint for primary implementation calls, not merely a score preference. `strict` fallback stops for reselection when the model cannot continue; `smart_within_allowlist` permits a classified, auditable fallback to another of the ten models. Mandatory independent verification remains governed by `verification_policy`.
