# Current External References

Retrieved/verified: 2026-09-09.

## LiteLLM
- Getting Started / Proxy / Router / budgeting / virtual keys:
  https://docs.litellm.ai/

The current documentation describes a unified interface over 100+ providers, retry/fallback routing, proxy authentication/authorization, spend tracking/budgets, rate limiting and observability callbacks.

## OpenRouter
- Provider matrix:
  https://openrouter.ai/providers
- Data collection:
  https://openrouter.ai/docs/guides/privacy/data-collection
- Model fallbacks:
  https://openrouter.ai/docs/guides/routing/model-fallbacks
- Guardrails:
  https://openrouter.ai/blog/announcements/guardrails/

OpenRouter documents model fallback behavior, provider-specific retention/training characteristics, opt-in prompt retention, metadata collection, and workspace guardrails including budget/ZDR/provider restrictions.

## Engineering rule
External products are implementation dependencies, not architectural authorities. Pin tested versions and validate configuration against the exact deployed release before production rollout.
