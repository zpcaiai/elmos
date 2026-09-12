---

# FILE: `README.md`

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


---

# FILE: `SKILL.md`

# Skill: Build Elmos Industrial Model Intelligence & Routing Plane

## Mission

Implement a production-grade model routing subsystem for Elmos using:

- Elmos-owned semantic/policy routing,
- LiteLLM as a replaceable unified gateway,
- direct native provider adapters,
- OpenRouter as a long-tail / DR / evaluation provider,
- optional self-hosted inference.

This skill is an **orchestrator**. Execute the child skills in order and refuse shortcuts that violate the architecture invariants.

## Inputs

Expected repository context:
- Elmos backend source,
- current task/execution-plan abstractions,
- tenant/account/billing model,
- current observability primitives,
- secret-management approach,
- deployment manifests,
- existing provider/model integrations.

If exact names differ, adapt to repository conventions; do not create a parallel architecture unnecessarily.

## Required outputs

1. `Model Intelligence Kernel`
2. Stable domain contracts:
   - `ModelExecutionPlan`
   - `RouteRequest`
   - `RouteDecision`
   - `ModelDescriptor`
   - `ProviderDescriptor`
   - `ProviderDeployment`
   - `RoutingPolicy`
   - `VerifiedSecurityContext`
   - `CapabilityLease`
   - stable provider error taxonomy
3. Provider execution SPI with no LiteLLM/OpenRouter type leakage.
4. LiteLLM gateway adapter.
5. Native provider adapters.
6. OpenRouter adapter.
7. Routing policy engine with hard filters then weighted ranking.
8. Fallback planner, circuit breaker, retry budget, deadline propagation.
9. Tenant/provider/model concurrency and rate limiting.
10. Cost ledger and reconciliation.
11. OpenTelemetry instrumentation.
12. Deterministic routing tests + integration tests + chaos/fault tests + benchmark/eval harness.
13. HA deployment and rollback plan.

## Global invariants

### Boundary invariants
- Domain code must not depend on vendor SDK DTOs.
- Provider adapters translate at the edge.
- Provider model names are not persisted as business-facing model identifiers; persist stable Elmos aliases plus resolved deployment snapshot.
- Gateway and provider selection are explicit fields in `RouteDecision`.

### Security invariants
- Every inference step has a verified tenant/security context.
- Provider credentials are resolved at execution time from secret references.
- No raw secret in plan/event/log/trace.
- Policy is fail-closed when classification/compliance information is missing.
- Fallback cannot weaken data retention, residency, tenant, tool, or permission constraints.
- Replay cannot downgrade authority.

### Reliability invariants
- A request has one end-to-end deadline.
- Retries consume a retry budget.
- Non-idempotent tool side effects are never duplicated by inference retries.
- Stream failover after emitted tokens requires an explicit restart/continuation policy; never concatenate two providers blindly.
- Result commit is idempotent and exactly-once from the Harness perspective.

### Cost invariants
- Request admission checks budget before provider execution.
- Estimated cost is used preflight; provider-reported usage is authoritative when available.
- Cost ledger is append-only/auditable.
- Duplicate retries/fallbacks are attributed to the originating step.

## Required execution sequence

1. Inspect repository and map existing abstractions.
2. Run child skill 01 and freeze contracts.
3. Add registries and versioned configuration.
4. Implement policy/security hard filters.
5. Implement deterministic route ranking and fallback graph.
6. Implement LiteLLM and native lanes.
7. Add OpenRouter as a provider, not as a routing authority.
8. Add durability/replay/commit protections.
9. Add budget/rate limits.
10. Add telemetry.
11. Add evals and fault testing.
12. Deploy behind feature flags and shadow routing.
13. Canary 1% → 5% → 25% → 50% → 100% only when gates pass.

## Do not do

- Do not route solely by `if model == ...`.
- Do not let LiteLLM choose a materially different model unless the resolved plan explicitly permits it.
- Do not treat 429/5xx as equivalent to policy denial.
- Do not use random fallback lists.
- Do not store prompts in logs by default.
- Do not hide provider cost from Elmos accounting.
- Do not retry tool calls because the model call was retried.
- Do not make health/cost data a hard dependency if a safe conservative route is available.
- Do not make OpenRouter the only route to strategic providers.
- Do not couple business code to a specific model generation.

## Final report format

Return:
1. architecture changes,
2. files/modules changed,
3. migrations,
4. API/contracts,
5. tests and evidence,
6. SLO results,
7. unresolved risks,
8. rollback instructions,
9. next optimization opportunities.


---

# FILE: `skills/00-master-orchestrator/SKILL.md`

# Skill 00 — Master Orchestrator

## Goal
Coordinate all routing-plane work as a controlled migration, not a big-bang rewrite.

## Tasks
1. Inventory existing model/provider calls, including hidden direct HTTP calls.
2. Identify task/step identifiers, durable events, billing, auth, permission context, and trace context.
3. Produce a dependency map:
   `caller -> routing -> adapter -> provider -> result commit`.
4. Create feature flags:
   - `router_v2_enabled`
   - `shadow_route_enabled`
   - `native_lane_enabled`
   - `openrouter_fallback_enabled`
5. Define coexistence:
   legacy path remains callable until certification gates pass.
6. Freeze package/module boundaries before implementation.

## Acceptance
- All known model calls are inventoried.
- No new provider call bypasses the new SPI.
- Rollback to legacy route requires configuration only.


---

# FILE: `skills/01-domain-contracts/SKILL.md`

# Skill 01 — Domain Contracts

## Goal
Create provider-neutral, durable contracts that remain stable across model/provider churn.

## Required types

### RouteRequest
Must include:
- tenantId
- taskId
- stepId
- attemptId
- taskClass
- requiredCapabilities[]
- preferredCapabilities[]
- dataClassification
- securityContextRef
- capabilityLeaseRef
- maxInputTokens / expectedOutputTokens
- deadline
- budgetEnvelope
- latencyClass
- qualityClass
- region/residency constraints
- tool/structured-output requirements
- model preferences/denials
- idempotency key
- policy version pin or resolution rule

### ModelExecutionPlan
Durable snapshot resolved before execution. Include:
- stable model alias
- selected deployment id
- execution lane (`NATIVE_DIRECT`, `LITELLM`, `OPENROUTER`, `SELF_HOSTED`)
- provider
- model revision if known
- reasoning profile
- context/output limits
- tools / structured output contract
- retry class
- fallback graph reference
- budget
- deadline
- policy version
- security-context hash
- capability-lease hash

### RouteDecision
Include:
- decisionId
- candidates considered
- hard-filter denial reasons
- selected deployment
- score breakdown
- fallback chain
- config/model-registry/policy versions
- decision timestamp
- health snapshot version
- cost-estimate snapshot

## Versioning
- Contracts are explicit-version DTOs/events.
- Persist `schemaVersion`.
- Add-only changes first; incompatible changes require a migration adapter.
- Durable task replay must deserialize historical versions.

## Acceptance
- Serialization compatibility tests exist.
- No vendor SDK type appears in domain contracts.
- Historical fixture for N-1 contract replays successfully.


---

# FILE: `skills/02-model-provider-registry/SKILL.md`

# Skill 02 — Model & Provider Registry

## Goal
Make model capability, cost, compliance, health and deployments data-driven.

## Entities

### ModelDescriptor
- alias
- provider-independent family
- capability vector
- modalities
- context/output bounds
- reasoning profiles
- tool support
- structured output support
- streaming support
- benchmark scores
- lifecycle status: experimental/canary/stable/deprecated/disabled

### ProviderDescriptor
- provider id
- provider type
- supported regions
- retention/training policy metadata
- residency guarantees
- credential reference
- contractual/SLA metadata
- enabled flag

### ProviderDeployment
- deployment id
- model alias
- actual provider model name
- endpoint/region
- lane support
- rate limit profile
- pricing profile
- health state
- priority
- feature overrides

## Registry rules
- Stable aliases never embed price or provider.
- Registry data is versioned.
- Runtime config changes are audited.
- Deprecated models remain resolvable for replay.
- Health is separate from static registry truth.

## Acceptance
- A new model can be introduced by registry/config plus adapter capability, without changing orchestration code.
- A model can have multiple deployments.
- A deployment can be disabled without deleting history.


---

# FILE: `skills/03-policy-and-security/SKILL.md`

# Skill 03 — Policy, Data Governance & Security

## Goal
Fail closed on security/compliance before cost/quality optimization.

## Data classifications
At minimum:
- PUBLIC
- INTERNAL
- CONFIDENTIAL
- SOURCE_CODE
- SECRET_BEARING
- PII

Classification may be composite.

## Hard filters
Evaluate before ranking:
1. tenant allow/deny
2. model allow/deny
3. provider allow/deny
4. region/residency
5. retention/ZDR requirement
6. training/use-of-data requirement
7. capability requirement
8. context length
9. tool support
10. structured output support
11. secret-bearing restrictions
12. budget hard ceiling
13. provider legal/compliance restrictions
14. capability lease
15. execution authority

## Security context
Integrate with Elmos `VerifiedSecurityContext` and invocation-scoped `CapabilityLease`:
- route request stores references/hashes, not raw privileged material;
- executor re-validates lease before invocation;
- replay may not mint broader authority;
- fallback inherits all constraints.

## Prompt/logging
- raw prompt/response logging OFF by default;
- redact secret/PII fields before optional debug capture;
- debug capture must be tenant-policy gated, encrypted, TTL-bound, auditable;
- traces contain hashes/size/token metadata by default.

## OpenRouter-specific requirement
Treat provider retention/training metadata as policy inputs. Do not assume all OpenRouter providers have identical retention behavior.

## Acceptance
- A denied provider cannot re-enter via fallback.
- Missing classification on protected task causes denial or conservative route.
- Security policy has deterministic unit tests.
- Secrets are absent from structured logs and traces.


---

# FILE: `skills/04-routing-engine/SKILL.md`

# Skill 04 — Routing Engine

## Goal
Deterministically choose the best eligible deployment for each Elmos step.

## Algorithm

### Phase A — hard eligibility
Filter with Skill 03 policies.

### Phase B — normalized scoring
For each eligible candidate compute a score from:
- capability fit
- task-specific benchmark quality
- reliability/health
- expected latency
- estimated cost
- cache affinity
- region affinity
- provider diversity
- historical task-class success

Recommended structure:

`score = Σ(weight_i * normalized_feature_i) - penalties`

Never encode policy denial as a low score.

### Phase C — tie-break
Stable deterministic tie-break:
1. higher policy priority
2. lower projected cost
3. higher health
4. stable deployment id lexical order

### Phase D — fallback graph
Generate ordered fallbacks with constraints:
- same required capabilities;
- no compliance weakening;
- no budget bypass;
- provider diversity preferred;
- avoid repeatedly selecting same outage domain;
- preserve native lane if required.

## Task classes
Start with Elmos-specific classes:
- REPO_ANALYSIS
- ARCHITECTURE_REASONING
- CODE_GENERATION
- LARGE_REFACTOR
- MIGRATION_PLANNING
- MIGRATION_EXECUTION
- TEST_GENERATION
- DEBUGGING
- SQL_TRANSLATION
- FORMAL_VERIFICATION
- DOCUMENTATION
- CHEAP_CLASSIFICATION
- EMBEDDING
- RERANKING

## Shadow mode
For every production request, optionally compute route-v2 decision without executing it. Compare:
- selected model/provider,
- estimated cost,
- expected quality tier,
- policy differences,
- latency projection.

## Acceptance
- Given same config/health snapshot/request, decision is deterministic.
- Route decision contains score explanation.
- Policy-ineligible candidate can never win.
- Property tests cover candidate permutations.


---

# FILE: `skills/05-litellm-gateway/SKILL.md`

# Skill 05 — LiteLLM Gateway Integration

## Goal
Use LiteLLM as a replaceable infrastructure gateway, not as the source of Elmos semantic routing truth.

## Deployment
Run LiteLLM Proxy independently from the Elmos API process.

Recommended production topology:
- >=2 proxy replicas
- health/readiness probes
- PodDisruptionBudget
- resource limits
- TLS/mTLS or trusted service mesh
- secrets through secret manager
- persistent backing DB only for features that require it
- no master key embedded in application source

## Elmos responsibilities
Elmos sends a fully resolved deployment/model alias and request policy.

## LiteLLM responsibilities
Allowed:
- protocol normalization,
- auth proxying,
- provider-compatible retries where explicitly allowed,
- provider deployment load balancing inside an Elmos-approved deployment group,
- rate limiting as defense-in-depth,
- usage/cost telemetry,
- observability hooks.

Not allowed:
- selecting a different semantic model class without Elmos permission;
- weakening retention/security policy;
- replacing Elmos budget ledger;
- changing tool permissions.

## Failover ownership
Prefer:
- Elmos owns cross-model fallback.
- LiteLLM may own same-model/same-policy deployment failover.
This avoids hidden semantic changes.

## Configuration
Use stable Elmos model aliases and explicit deployment groups.

## Acceptance
- Gateway can be bypassed by native lane for a selected deployment.
- LiteLLM outage does not take down native-direct routes.
- Elmos can reconstruct exact physical deployment used.


---

# FILE: `skills/06-native-provider-adapters/SKILL.md`

# Skill 06 — Native Direct Provider Adapters

## Goal
Preserve vendor-native features without contaminating Elmos domain contracts.

## SPI
Implement a provider-neutral executor interface, conceptually:

- `supports(executionPlan)`
- `validate(executionPlan)`
- `execute(request, plan, context)`
- `stream(request, plan, context)`
- `estimateCost(request, plan)`
- `cancel(executionId)` when provider supports it
- `healthProbe(deployment)`

## First adapters
Implement at least two strategic direct providers first, chosen by actual Elmos usage.

## Adapter requirements
- deadline propagation
- idempotency where provider supports it
- normalized usage
- normalized finish reason
- normalized tool call representation
- structured output validation
- provider request id capture
- rate-limit headers capture
- error translation
- cancellation mapping
- retryability classification
- feature-capability probe/tests

## Native feature escape hatch
Provider-specific options live in a versioned `ProviderExtension` envelope scoped to the adapter. They must not become global domain assumptions.

## Acceptance
- Native adapter passes contract suite shared by all executors.
- Unsupported native feature causes explicit validation failure, never silent downgrade.


---

# FILE: `skills/07-openrouter-adapter/SKILL.md`

# Skill 07 — OpenRouter Provider Adapter

## Goal
Use OpenRouter for long-tail, rapid onboarding, benchmark/eval and disaster recovery while preserving Elmos policy authority.

## Allowed use cases
- models without first-party adapter,
- temporary model trials,
- evaluation matrix,
- DR when strategic direct provider route fails,
- provider diversity.

## Policy requirements
- resolve OpenRouter provider/retention rules before execution;
- apply ZDR/provider restrictions where required;
- pin allowed providers when compliance demands it;
- do not allow OpenRouter model fallback to introduce a model not present in the Elmos fallback graph.

## Fallback rule
Default:
- Elmos controls **cross-model** fallback.
- OpenRouter may control **provider-level** routing within an Elmos-approved model/provider policy.
If OpenRouter model-fallback feature is used, the exact ordered model list must be generated by Elmos and persisted in `ModelExecutionPlan`.

## Accounting
- record OpenRouter request id,
- actual resolved model/provider when surfaced,
- usage,
- latency,
- platform/gateway costs when available,
- retry/fallback count.

## Acceptance
- OpenRouter can be disabled globally without changing caller code.
- A compliance-restricted request cannot route to a noncompliant OpenRouter provider.
- DR test shows direct-provider outage can fail over only when plan permits.


---

# FILE: `skills/08-resilience-and-replay/SKILL.md`

# Skill 08 — Resilience, Replay & Commit Semantics

## Goal
Survive rate limits, outages, worker crashes and partial streams without duplicated side effects.

## Error taxonomy
Normalize at least:
- AUTH
- PERMISSION
- POLICY_DENIED
- RATE_LIMIT
- QUOTA_EXHAUSTED
- TIMEOUT
- CANCELLED
- PROVIDER_4XX
- PROVIDER_5XX
- CONTENT_REFUSAL
- CONTEXT_OVERFLOW
- INVALID_STRUCTURED_OUTPUT
- TOOL_PROTOCOL_ERROR
- NETWORK
- CIRCUIT_OPEN
- BUDGET_DENIED
- UNSUPPORTED_CAPABILITY

## Retry policy
Retry only retryable failures.
Use:
- exponential backoff + jitter,
- bounded retry count,
- retry budget per request,
- end-to-end deadline,
- provider Retry-After where safe.

Never retry:
- policy denial,
- invalid auth until configuration changes,
- deterministic validation errors,
- side-effectful tool execution as a consequence of inference retry.

## Circuit breakers
Scope by:
`provider + deployment + region + error-class`.

States:
CLOSED -> OPEN -> HALF_OPEN.

## Streaming
If tokens have been emitted:
- record stream epoch,
- if failure occurs, either fail the step or restart under a new epoch,
- never append a new provider continuation as if it were one uninterrupted response unless protocol explicitly supports safe continuation.

## Exactly-once result commit
Use:
- durable `attemptId`,
- idempotency key,
- compare-and-set/unique constraint for terminal commit,
- result hash,
- tool-result commit boundary,
- duplicate event rejection.

## Replay
Persist enough to reproduce:
- plan version,
- policy version,
- registry version,
- security-context hash,
- capability-lease hash,
- resolved deployment,
- request hash,
- provider request id,
- attempt lineage.

## Acceptance
- kill worker after provider success but before commit; replay commits once.
- inject 429 and 5xx; retry/fallback is bounded.
- partial stream cannot create duplicated final text.


---

# FILE: `skills/09-cost-rate-limit-accounting/SKILL.md`

# Skill 09 — Cost, Budget, Rate Limit & Concurrency Accounting

## Goal
Make model spend a first-class Elmos control-plane concern.

## Budget hierarchy
Support:
- platform
- tenant
- workspace/project
- user/service-account
- task
- step

## Preflight
Estimate:
`input_tokens * price_in + expected_output_tokens * price_out + fixed/tool/cache modifiers`.

Reject when hard budget would be exceeded unless an authorized override exists.

## Postflight
Reconcile:
1. provider-reported usage
2. gateway usage
3. Elmos tokenizer estimate as fallback

Record confidence/source.

## Rate limiting
Enforce at:
- tenant
- provider
- deployment
- model alias
- task class

Use token bucket/leaky bucket + concurrency semaphores.

## Backpressure
When capacity is exhausted:
- reject low-priority work,
- queue durable background work,
- downgrade only if policy explicitly permits,
- never silently exceed task deadline.

## Accounting event
Append:
- task/step/attempt
- tenant
- model alias
- deployment/provider
- input/output/cache/reasoning tokens where available
- estimated cost
- actual reconciled cost
- retry/fallback waste
- currency
- pricing snapshot/version

## Acceptance
- budget race under concurrency cannot overspend beyond configured tolerance.
- retry cost is visible.
- cost attribution survives fallback.


---

# FILE: `skills/10-observability-and-evals/SKILL.md`

# Skill 10 — Observability, Health & Evals

## Goal
Know why a route was chosen, how it behaved, how much it cost, and whether it improved Elmos outcomes.

## OpenTelemetry spans
Recommended:
- `elmos.route.evaluate`
- `elmos.route.select`
- `elmos.gateway.invoke`
- `elmos.provider.invoke`
- `elmos.provider.stream`
- `elmos.result.validate`
- `elmos.result.commit`

Attributes:
- tenant pseudonymous id
- taskClass
- modelAlias
- provider/deployment
- lane
- routeDecisionId
- policyVersion
- registryVersion
- attempt
- fallbackIndex
- status/errorClass
- token counts
- cost
- latency
- cache hit
- prompt hash, not prompt body

## Metrics
At minimum:
- request rate
- success/error by class
- p50/p95/p99 latency
- TTFT
- tokens/sec where available
- fallback rate
- retry rate
- circuit-open count
- budget denials
- cost per tenant/task/model
- route distribution
- structured-output validation failure
- tool-call protocol failure
- provider health

## Health model
Do not use a single boolean.
Track windowed:
- availability
- rate-limit pressure
- timeout rate
- p95 latency
- success rate
- refusal/error classes.

## Evals
Create Elmos task-class benchmark suites:
- compilation success
- test pass
- semantic equivalence
- mutation score
- patch acceptance
- architecture rubric
- hallucination/unsupported edit rate
- wall-clock
- token/cost

Do not update routing weights directly from a single online sample. Promote benchmark versions through review.

## Acceptance
- every production request is traceable end-to-end.
- no prompt bodies appear in default telemetry.
- route-quality regression can be detected by benchmark gate.


---

# FILE: `skills/11-deployment-and-operations/SKILL.md`

# Skill 11 — Deployment & Operations

## Goal
Deploy the routing plane as an HA, independently scalable production subsystem.

## Services
Recommended logical components:
- Elmos Router API/library
- Model Registry/Policy service or module
- LiteLLM Proxy cluster
- provider adapter workers if isolation is desired
- telemetry collector
- PostgreSQL
- optional Redis

Keep initial deployment simpler if possible; preserve logical boundaries even if some modules share a process.

## HA
- >=2 instances for stateless router/gateway
- multi-AZ where platform supports it
- readiness based on local health, not every provider being up
- graceful drain for streaming requests
- bounded shutdown
- connection pool protection
- DB migrations backward-compatible

## Configuration rollout
- draft -> validate -> canary -> active
- immutable version ids
- instant rollback to prior active version
- reject invalid model capability/policy combinations before activation

## Secret rotation
- credentials referenced by secret id
- adapter resolves latest valid secret at call time or short TTL cache
- dual-key rotation where providers permit
- rotation does not require app redeploy

## SLO starting targets
Treat these as initial engineering targets to validate in staging, not universal guarantees:
- route decision p95 < 25 ms excluding external calls
- router availability >= 99.95%
- no single gateway dependency for native-capable strategic routes
- 100% inference attempts have trace id and cost attribution
- 0 plaintext provider secrets in logs/events

## Acceptance
- rolling deploy preserves active streams or drains them safely.
- gateway outage leaves eligible native lane functional.
- config rollback tested.


---

# FILE: `skills/12-certification-and-rollout/SKILL.md`

# Skill 12 — Certification, Chaos & Rollout

## Goal
Prove the router is safe before it becomes authoritative.

## Test layers

### T0 static/contracts
- schema compatibility
- forbidden dependency checks
- secret scanning
- config validation

### T1 unit
- policy filters
- score normalization
- deterministic tie-break
- fallback generation
- error classification
- budget arithmetic

### T2 adapter contract
Run identical suite against every adapter.

### T3 integration
- real/stub LiteLLM
- real/stub OpenRouter
- at least two direct providers
- streaming
- structured output
- tool calls
- cancellation

### T4 fault/chaos
Inject:
- 429
- 401/403
- 500/502/503
- timeout
- broken stream
- malformed tool call
- malformed structured JSON
- DNS/network failure
- LiteLLM outage
- OpenRouter outage
- DB transient failure
- duplicate event
- worker crash around commit boundary

### T5 eval
Run real Elmos migration/generation tasks.

### T6 soak/load
- sustained concurrency
- burst traffic
- tenant noisy-neighbor
- provider rate-limit saturation
- cost ledger reconciliation

## Rollout
1. shadow only
2. 1% canary
3. 5%
4. 25%
5. 50%
6. 100%

Advance only when:
- policy mismatches = 0 critical
- no security regression
- error budget healthy
- quality not below baseline gate
- cost within approved envelope
- rollback tested

## Rollback
Feature flag returns traffic to legacy route while preserving new telemetry for diagnosis.

## Final evidence pack
Generate:
- architecture diagram
- route decision examples
- policy test report
- provider adapter matrix
- load/soak report
- chaos report
- eval report
- cost comparison
- security checklist
- rollback evidence


---

# FILE: `contracts/error-taxonomy.md`

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


---

# FILE: `configs/model-registry.example.yaml`

version: "2026-09-09.1"

models:
  - alias: strategic-coding-high
    family: coding-reasoning
    lifecycle: stable
    capabilities:
      coding: 0.98
      architecture: 0.95
      refactoring: 0.98
      tool_calling: true
      structured_output: true
      streaming: true
      long_context: true
    task_benchmarks:
      LARGE_REFACTOR: 0.96
      MIGRATION_EXECUTION: 0.95

  - alias: cheap-classifier
    family: classifier
    lifecycle: stable
    capabilities:
      classification: 0.95
      structured_output: true
      streaming: false

providers:
  - id: openai-direct
    type: NATIVE
    credential_ref: secret://providers/openai/prod
    enabled: true

  - id: anthropic-direct
    type: NATIVE
    credential_ref: secret://providers/anthropic/prod
    enabled: true

  - id: litellm-prod
    type: LITELLM
    credential_ref: secret://gateways/litellm/prod
    enabled: true

  - id: openrouter
    type: OPENROUTER
    credential_ref: secret://providers/openrouter/prod
    enabled: true

deployments:
  - id: strategic-coding-high-openai-native
    model_alias: strategic-coding-high
    provider_id: openai-direct
    lane: NATIVE_DIRECT
    actual_model: "<provider-model-id>"
    regions: ["us"]
    retention: provider_contract
    training: false
    rate_limit_profile: openai-prod
    pricing_profile: strategic-openai-2026-09
    enabled: true

  - id: strategic-coding-high-openrouter
    model_alias: strategic-coding-high
    provider_id: openrouter
    lane: OPENROUTER
    actual_model: "<openrouter-model-id>"
    allowed_openrouter_providers: ["<approved-provider>"]
    require_zdr: true
    rate_limit_profile: openrouter-prod
    pricing_profile: strategic-openrouter-2026-09
    enabled: true


---

# FILE: `configs/policy.example.yaml`

version: "2026-09-09.1"

defaults:
  fail_closed: true
  raw_prompt_logging: false
  raw_response_logging: false
  cross_model_fallback_owner: ELMOS
  same_model_deployment_failover_owner: GATEWAY_ALLOWED

classifications:
  PUBLIC:
    allow_openrouter: true
  INTERNAL:
    allow_openrouter: true
  CONFIDENTIAL:
    require_no_training: true
    require_retention_class: ZERO_OR_CONTRACTED
  SOURCE_CODE:
    require_no_training: true
    raw_logging: false
  SECRET_BEARING:
    allow_openrouter: false
    require_native_or_self_hosted: true
    raw_logging: false
  PII:
    require_region_policy: true
    raw_logging: false

task_classes:
  LARGE_REFACTOR:
    quality_weight: 0.45
    reliability_weight: 0.20
    cost_weight: 0.10
    latency_weight: 0.10
    benchmark_weight: 0.15
  CHEAP_CLASSIFICATION:
    quality_weight: 0.20
    reliability_weight: 0.20
    cost_weight: 0.40
    latency_weight: 0.20

fallback:
  max_attempts: 3
  max_cross_model_fallbacks: 2
  preserve_required_capabilities: true
  preserve_security_constraints: true
  prefer_failure_domain_diversity: true


---

# FILE: `configs/litellm.example.yaml`

# Illustrative LiteLLM config.
# Validate against the exact LiteLLM version pinned by Elmos before deployment.

model_list:
  - model_name: elmos-unified-coding
    litellm_params:
      model: openai/<deployment-or-model>
      api_key: os.environ/OPENAI_API_KEY

  - model_name: elmos-openrouter-longtail
    litellm_params:
      model: openrouter/<provider>/<model>
      api_key: os.environ/OPENROUTER_API_KEY

general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
  database_url: os.environ/LITELLM_DATABASE_URL

# Elmos owns semantic cross-model routing.
# Configure LiteLLM retries/fallbacks only within deployment groups explicitly allowed by Elmos.


---

# FILE: `adr/ADR-001-routing-boundaries.md`

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


---

# FILE: `IMPLEMENTATION_CHECKLIST.md`

# Implementation Checklist

## P0 — Contracts & Safety
- [ ] inventory all current provider calls
- [ ] introduce provider-neutral SPI
- [ ] add `ModelExecutionPlan`
- [ ] add `RouteDecision`
- [ ] add model/provider/deployment registry
- [ ] add deterministic hard policy filters
- [ ] integrate `VerifiedSecurityContext`
- [ ] integrate invocation-scoped `CapabilityLease`
- [ ] exact-once result commit
- [ ] lossless replay fixtures
- [ ] error taxonomy

## P1 — Execution Lanes
- [ ] LiteLLM proxy deployment
- [ ] LiteLLM adapter
- [ ] native provider adapter #1
- [ ] native provider adapter #2
- [ ] OpenRouter adapter
- [ ] self-host compatible adapter
- [ ] structured output validation
- [ ] streaming normalization
- [ ] cancellation/deadline propagation

## P1 — Reliability
- [ ] retry budget
- [ ] jittered backoff
- [ ] per-deployment circuit breaker
- [ ] fallback graph
- [ ] partial-stream epoch handling
- [ ] idempotency keys
- [ ] durable attempt lineage

## P1 — Cost & Capacity
- [ ] budget hierarchy
- [ ] preflight estimate
- [ ] postflight reconciliation
- [ ] provider/model/tenant rate limits
- [ ] concurrency limits
- [ ] durable backpressure

## P2 — Observability & Intelligence
- [ ] OpenTelemetry spans
- [ ] request/cost/health metrics
- [ ] route explanation
- [ ] benchmark registry
- [ ] task-class eval suites
- [ ] shadow router
- [ ] model health windows
- [ ] config/policy version rollout

## P2 — Certification
- [ ] adapter contract tests
- [ ] policy property tests
- [ ] chaos injection
- [ ] 24h soak
- [ ] noisy-neighbor load test
- [ ] security log/trace scan
- [ ] budget race test
- [ ] worker-crash commit test
- [ ] canary rollback drill

## Release gate
- [ ] 0 critical policy bypasses
- [ ] 0 plaintext secrets in logs/events
- [ ] route determinism passes
- [ ] quality >= approved baseline
- [ ] cost within envelope
- [ ] rollback proven


---

# FILE: `REFERENCES.md`

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
