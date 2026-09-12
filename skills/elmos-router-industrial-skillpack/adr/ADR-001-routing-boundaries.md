# ADR-001: Elmos Owns Semantic Routing; Gateways Are Replaceable

## Status
Accepted.

## Context
Elmos requires task-aware model selection, security-sensitive source-code handling, durable replay, cost governance, and provider-independent evolution. Gateway products can normalize protocols and offer infrastructure routing, but cannot own Elmos task semantics or execution authority.

## Decision
1. Elmos `Model Intelligence Kernel` owns:
   - task classification,
   - hard policy,
   - capability matching,
   - model selection,
   - cross-model fallback,
   - budget policy,
   - durable execution plan,
   - security context,
   - result commit.

2. LiteLLM owns replaceable gateway concerns:
   - API normalization,
   - gateway auth/rate-limit defense-in-depth,
   - approved same-model deployment balancing/failover,
   - telemetry.

3. Direct provider adapters exist for native capabilities and independence.

4. OpenRouter is represented as a provider/route option and may not bypass Elmos policy.

## Consequences
### Positive
- no strategic vendor lock-in,
- native feature fidelity,
- safer replay,
- explicit cost/security semantics,
- independent gateway replacement.

### Negative
- more Elmos engineering,
- model registry must be maintained,
- adapter contract testing required,
- routing policy governance becomes a first-class responsibility.

## Rejected
- All traffic permanently through OpenRouter.
- LiteLLM as the only routing brain.
- Callers choosing raw provider/model endpoints.
