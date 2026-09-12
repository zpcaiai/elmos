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
