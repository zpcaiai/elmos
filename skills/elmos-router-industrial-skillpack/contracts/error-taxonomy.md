# Elmos Provider Error Taxonomy

Every adapter MUST map provider/gateway errors into this stable taxonomy.

| Class | Retryable by default | Fallback eligible | Notes |
|---|---:|---:|---|
| AUTH | No | No | configuration issue |
| PERMISSION | No | No | provider permission |
| POLICY_DENIED | No | No | fail closed |
| RATE_LIMIT | Yes | Yes | honor retry-after/deadline |
| QUOTA_EXHAUSTED | Usually no same deployment | Yes | fallback if budget/policy allows |
| TIMEOUT | Yes | Yes | bounded by end-to-end deadline |
| CANCELLED | No | No | caller cancellation |
| PROVIDER_4XX | Usually no | Maybe | classify finer when possible |
| PROVIDER_5XX | Yes | Yes | circuit breaker input |
| CONTENT_REFUSAL | No | Policy-specific | not an infrastructure error |
| CONTEXT_OVERFLOW | No | Maybe | only if fallback supports required context |
| INVALID_STRUCTURED_OUTPUT | Limited | Maybe | validation/retry policy |
| TOOL_PROTOCOL_ERROR | Limited | Maybe | never duplicate tool side effects |
| NETWORK | Yes | Yes | breaker input |
| CIRCUIT_OPEN | No current route | Yes | choose another failure domain |
| BUDGET_DENIED | No | Maybe cheaper route only if explicitly allowed |
| UNSUPPORTED_CAPABILITY | No | Yes | route-planning/config error |

## Mapping rules
- Preserve original provider status/code/request-id in diagnostic metadata.
- Do not expose provider secret-bearing payloads.
- `retryable` and `fallbackEligible` are resolved from taxonomy + plan + deadline + budget, not provider exception text alone.
