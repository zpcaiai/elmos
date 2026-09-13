# Elmos Router Industrial Engine

Production-grade Model Intelligence and Routing Engine for Elmos, implementing the full architecture specified in `elmos-router-industrial-skillpack`.

## Core Architectural Invariants
1. **Semantic Routing Authority**: Elmos owns all semantic routing decisions, model selection, policy filters, budget governance, and exactly-once result commit.
2. **Replaceable Gateway**: LiteLLM serves strictly as an infrastructure normalization and auth gateway; it never alters semantic model class or bypasses Elmos policy.
3. **Native Direct Adapters**: Direct native adapters for OpenAI, Anthropic, etc. preserve vendor-native capabilities (reasoning effort, extended thinking, prompt caching, native tool calls, strict JSON schema).
4. **OpenRouter as a Governed Lane**: OpenRouter is treated as a provider lane for long-tail models, fast onboarding, benchmarks, and disaster recovery, strictly governed by ZDR and data residency rules.
5. **Fail-Closed Security & Policy**: 15 hard policy filters evaluate tenant, model, provider, region, retention, training consent, context, tool support, and secret-bearing constraints before scoring.
6. **4-Phase Deterministic Routing**: Phase A (hard eligibility) -> Phase B (multi-factor normalized scoring) -> Phase C (deterministic tie-break) -> Phase D (constrained fallback graph).
7. **Resilience & Idempotency**: Scoped circuit breakers (`provider + deployment + region + error_class`), exponential backoff with full jitter, per-request retry budget, stream epoch isolation, and Compare-And-Set (CAS) exactly-once result commit.
8. **Spend & Capacity Governance**: Hierarchical budget enforcement (Platform -> Tenant -> Project -> User -> Task -> Step), preflight cost estimation, postflight usage reconciliation, multi-tier rate limiting, and append-only cost ledger.
9. **Zero Vendor SDK Leakage**: The domain contracts and SPI layers contain zero third-party vendor SDK dependencies.
