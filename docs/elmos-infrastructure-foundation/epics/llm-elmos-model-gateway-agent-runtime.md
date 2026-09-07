# Model Gateway, Context Builder, Budgeted Agent Runtime, and Inference Cache

- Skill: `elmos-model-gateway-agent-runtime`
- Priority: `P1`
- Phase: `G6`
- Dependencies: `elmos-identity-tenant-security`, `elmos-content-addressed-cache`, `elmos-incremental-semantic-index`, `elmos-semantic-ir-compiler-platform`, `elmos-secure-sandbox-runtime`

## Objective

Use models only where deterministic compilers/rules cannot finish the task, with enforceable cost, data, tool, and quality boundaries.

## Task groups

### Catalog and provider abstraction

- [ ] `ELMOS-LLM-001` Define model provider, model revision, deployment, context, modality, tool, structured-output, residency, privacy, price, rate-limit, and lifecycle records.
- [ ] `ELMOS-LLM-002` Define normalized request, streaming event, response, usage, cost, finish reason, safety/refusal, and provider-error contracts.
- [ ] `ELMOS-LLM-003` Implement timeout, bounded retry, backoff, circuit breaker, concurrency/rate limits, and capability negotiation.
- [ ] `ELMOS-LLM-004` Preserve historical model identity/provenance after retirement.
- [ ] `ELMOS-LLM-005` Use secret references and short-lived provider credentials.

### Routing and policy

- [ ] `ELMOS-LLM-006` Classify tasks and prefer deterministic rule, local small model, medium code model, frontier model, then multi-model review.
- [ ] `ELMOS-LLM-007` Score candidates by capability, quality evidence, latency, cost, residency, confidentiality, health, and quota.
- [ ] `ELMOS-LLM-008` Enforce provider/model allowlists per tenant/repository/data class.
- [ ] `ELMOS-LLM-009` Provide primary/fallback routing without silently weakening policy.
- [ ] `ELMOS-LLM-010` Record route candidates, selected model, policy decision, degradation, and reason in trace/evidence.

### Hard budgets

- [ ] `ELMOS-LLM-011` Create tenant, portfolio, project, workflow, stage, agent-run, and call budgets.
- [ ] `ELMOS-LLM-012` Reserve estimated tokens/cost before each call and reconcile actual usage after completion.
- [ ] `ELMOS-LLM-013` Enforce maximum prompt/completion/total tokens, cost, calls, iterations, wall-clock, concurrency, and repair patches.
- [ ] `ELMOS-LLM-014` Stop repeated equivalent errors and non-improving loops.
- [ ] `ELMOS-LLM-015` Require time-limited approval for overrides and audit reserved/actual/forecast values.
- [ ] `ELMOS-LLM-016` Prevent races from overspending shared budgets.

### Prompt and skill registry

- [ ] `ELMOS-LLM-017` Store immutable versioned system prompts, task prompts, structured-output schemas, examples, and linked Skill/Rule packages.
- [ ] `ELMOS-LLM-018` Digest every prompt/context template and include it in action/provenance keys.
- [ ] `ELMOS-LLM-019` Require evaluation and review before promotion.
- [ ] `ELMOS-LLM-020` Support shadow, canary, rollback, deprecation, and tenant override within policy.
- [ ] `ELMOS-LLM-021` Block embedded secrets and uncontrolled dynamic instructions.

### Semantic context builder

- [ ] `ELMOS-LLM-022` Start from target symbols/gaps and select callers, callees, types, contracts, tests, configuration, database/message schemas, rules, and prior validated decisions.
- [ ] `ELMOS-LLM-023` Score and explain every selected context block.
- [ ] `ELMOS-LLM-024` Use exact snapshot/digest references and prevent stale-context mixing.
- [ ] `ELMOS-LLM-025` Apply token budgets through semantic compression/summarization without dropping binding contracts.
- [ ] `ELMOS-LLM-026` Keep tenant/project memory isolated and validate reusable knowledge before promotion.
- [ ] `ELMOS-LLM-027` Emit a context manifest suitable for replay and cache identity.

### Caching and local inference

- [ ] `ELMOS-LLM-028` Support local vLLM/SGLang or equivalent endpoints with health and capacity registration.
- [ ] `ELMOS-LLM-029` Arrange stable policy/skill/project context to maximize prefix cache safely.
- [ ] `ELMOS-LLM-030` Use exact response caching only when model revision, prompt, context, parameters, schema, policy, and permissions match.
- [ ] `ELMOS-LLM-031` Do not use fuzzy semantic cache for executable code transformations by default.
- [ ] `ELMOS-LLM-032` Partition or encrypt cache by tenant/data class and recheck authorization on lookup.
- [ ] `ELMOS-LLM-033` Measure prefix, exact, provider, and miss reason metrics.

### Tool-controlled agent loop

- [ ] `ELMOS-LLM-034` Bind each agent run to explicit file, shell, compiler, test, retrieval, network, and repository tool allowlists.
- [ ] `ELMOS-LLM-035` Validate tool parameters against schemas and policy before execution.
- [ ] `ELMOS-LLM-036` Run shell/build/test tools in the required sandbox and workspace.
- [ ] `ELMOS-LLM-037` Use idempotency keys/fencing for side-effecting tools.
- [ ] `ELMOS-LLM-038` Require approval for high-risk writes, dependency/security changes, export, or PR operations.
- [ ] `ELMOS-LLM-039` Record every tool request/result digest, decision, duration, and failure.
- [ ] `ELMOS-LLM-040` Prevent agents from changing their own policy, budget, identity, sandbox, or allowlist.

### Repair quality loop

- [ ] `ELMOS-LLM-041` Feed only classified failures and relevant semantic context to repair agents.
- [ ] `ELMOS-LLM-042` Create one isolated patch per iteration and run selected validation.
- [ ] `ELMOS-LLM-043` Track objective improvement, repeated signatures, regression count, and remaining gaps.
- [ ] `ELMOS-LLM-044` Escalate to full tests at risk thresholds and before promotion.
- [ ] `ELMOS-LLM-045` Stop and emit a human task when bounds or confidence fail.

## Validation

- [ ] Deny a disallowed provider for private source.
- [ ] Race concurrent calls against a shared budget and prove no overspend.
- [ ] Change prompt/model/policy/permission and require cache miss.
- [ ] Attempt tool/path/network privilege escalation and reject it.
- [ ] Run repeated non-improving repair loops and verify bounded stop/evidence.

## Exit gate

- [ ] Every model/tool operation has identity, policy, budget, context, usage, and outcome provenance.
- [ ] No call can exceed hard scope or data policy through fallback.
- [ ] Caching is exact and permission-safe for executable outputs.
- [ ] Agent changes pass deterministic verification before promotion.
