# Elmos Router Industrial Skill Package

**Target:** Elmos Proof-Driven Agentic Harness / Repository Semantic Compiler  
**Architecture:** Elmos Router + LiteLLM + Direct Provider APIs + OpenRouter + optional self-hosted inference  
**Status:** Implementation-ready blueprint for Codex / Claude Code / engineering teams  
**Version:** 1.0

## 1. Outcome

Build a production-grade model intelligence and routing subsystem in which:

- **Elmos owns all semantic routing decisions.**
- **LiteLLM is a replaceable gateway/normalization layer, never the source of routing truth.**
- **Direct provider adapters preserve native capabilities and avoid lowest-common-denominator loss.**
- **OpenRouter is a provider option for long-tail models, rapid model onboarding, benchmark/eval, and disaster recovery.**
- **Self-hosted OpenAI-compatible inference (vLLM/SGLang/etc.) can be added without changing domain orchestration.**
- **Security policy, tenant isolation, budget, audit, execution authority, retries, failover, and commit semantics remain inside Elmos.**

## 2. Non-negotiable architecture rules

1. The caller never selects a raw provider endpoint directly.
2. Every inference step receives a durable `ModelExecutionPlan`.
3. Hard policy constraints are evaluated **before** score-based optimization.
4. Fallbacks must preserve required capabilities and data-handling constraints.
5. A gateway may normalize transport, but may not silently alter Elmos routing policy.
6. Tool-result commit is exactly-once at the Elmos Harness boundary.
7. Lossless replay preserves the original `VerifiedSecurityContext`, `CapabilityLease`, model plan, and policy version.
8. Prompt/response body logging is disabled by default.
9. Provider credentials are never returned to tenants, agents, tools, logs, traces, or persisted task payloads.
10. Model/provider configuration is versioned and auditable.
11. Model aliases are stable; physical deployments may change behind them.
12. All provider failures are mapped into a stable Elmos error taxonomy.
13. Every request emits usage/cost/latency/route-decision telemetry.
14. Routing correctness is covered by deterministic contract tests; model quality is covered by evals, not unit tests.
15. No dependency on LiteLLM/OpenRouter is allowed in Elmos domain interfaces.

## 3. Recommended runtime topology

```text
Elmos Agentic Harness
        |
        v
+-----------------------------+
| Model Intelligence Kernel   |
|-----------------------------|
| Policy Engine               |
| Capability Resolver         |
| Route Planner               |
| Cost/Latency Optimizer      |
| Fallback Planner            |
| Model Health                |
| Model/Provider Registry     |
+--------------+--------------+
               |
               v
        RouteDecision
               |
      +--------+---------+----------------+
      |                  |                |
      v                  v                v
Native Direct Lane   Unified Gateway   Self-host Lane
      |                  |                |
OpenAI/Anthropic/     LiteLLM Proxy    vLLM/SGLang/
Google/etc.             |              OpenAI-compatible
                        |
         +--------------+--------------+
         |                             |
      Direct-backed                 OpenRouter
      deployments                   provider
```

## 4. Why dual-lane

Use **Unified Gateway Lane** for ordinary chat/completions/responses/embeddings where normalization is safe and useful.

Use **Native Direct Lane** when a task requires:
- provider-native reasoning controls,
- provider-native prompt caching semantics,
- batch APIs,
- native file/input containers,
- provider-specific tool execution,
- features not losslessly represented by the gateway,
- early access/new API functionality,
- provider-specific compliance or data residency controls.

The route planner chooses the lane; callers do not.

## 5. Skill execution order

Run skills in this order:

1. `00-master-orchestrator`
2. `01-domain-contracts`
3. `02-model-provider-registry`
4. `03-policy-and-security`
5. `04-routing-engine`
6. `05-litellm-gateway`
7. `06-native-provider-adapters`
8. `07-openrouter-adapter`
9. `08-resilience-and-replay`
10. `09-cost-rate-limit-accounting`
11. `10-observability-and-evals`
12. `11-deployment-and-operations`
13. `12-certification-and-rollout`

Do not parallelize skills 01–04 unless the domain interfaces are frozen first. Implementation of provider adapters may run in parallel after contracts are accepted.

## 6. Definition of Done

The package is complete when:
- the Elmos domain layer compiles without importing LiteLLM/OpenRouter SDK types;
- at least 2 native providers + LiteLLM + OpenRouter are functional;
- deterministic routing tests pass;
- policy denials cannot be bypassed with fallback;
- retry/fallback/circuit-breaker behavior is verified with fault injection;
- tenant budgets and provider rate limits are enforced;
- every inference call is traceable by task/step/route IDs;
- exact-once result commit survives worker crash and replay;
- a 24h soak test meets the chosen SLO envelope;
- canary rollout and rollback are automated;
- model benchmark data can alter weighted routing without redeploying application code.

## 7. Suggested implementation stack

The contracts are language-neutral. For Elmos, a pragmatic split is:

- **Control/domain service:** Java 21+/Spring Boot or Kotlin, aligned with existing Elmos backend.
- **LiteLLM Proxy:** independent Python service/container.
- **State:** PostgreSQL.
- **Hot policy/health/cache:** Redis optional, never sole source of truth.
- **Telemetry:** OpenTelemetry.
- **Secrets:** Vault/KMS/cloud secret manager.
- **Async durability:** existing Elmos durable workflow/event substrate; do not introduce a second workflow engine only for routing.
- **Config:** database-backed versioned config with Git-exportable YAML snapshots.

## 8. Artifacts in this package

- `SKILL.md`: master execution instructions
- `skills/*/SKILL.md`: focused implementation skills
- `contracts/model-execution-plan.schema.json`
- `contracts/route-decision.schema.json`
- `contracts/error-taxonomy.md`
- `configs/model-registry.example.yaml`
- `configs/policy.example.yaml`
- `configs/litellm.example.yaml`
- `adr/ADR-001-routing-boundaries.md`
- `IMPLEMENTATION_CHECKLIST.md`
- `REFERENCES.md`
