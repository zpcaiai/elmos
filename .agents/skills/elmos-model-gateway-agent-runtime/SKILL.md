---
name: elmos-model-gateway-agent-runtime
description: Provide governed multi-provider model access, semantic context assembly,
  hard budgets, tool controls, local inference, prefix caching, and auditable repair
  loops.
version: 1.0.0
priority: P1
phase: G6
dependencies:
- elmos-identity-tenant-security
- elmos-content-addressed-cache
- elmos-incremental-semantic-index
- elmos-semantic-ir-compiler-platform
- elmos-secure-sandbox-runtime
---

# Model Gateway, Context Builder, Budgeted Agent Runtime, and Inference Cache

## Objective

Use models only where deterministic compilers/rules cannot finish the task, with enforceable cost, data, tool, and quality boundaries.

## Use this skill when

Use this skill when implementing, repairing, reviewing, validating, or productionizing the **Model Gateway, Context Builder, Budgeted Agent Runtime, and Inference Cache** capability in an eLMOS repository. Invoke the program orchestrator first for work spanning multiple skills.

## Dependencies

- `elmos-identity-tenant-security`
- `elmos-content-addressed-cache`
- `elmos-incremental-semantic-index`
- `elmos-semantic-ir-compiler-platform`
- `elmos-secure-sandbox-runtime`

Do not mark this skill complete until required dependency contracts are present and their blocking gates pass. A dependency can be implemented in the same change only when the plan preserves reviewable boundaries.

## Non-negotiable constraints

- Rules/compiler transformations precede LLM calls.
- Private source may only reach providers allowed by tenant/data policy.
- Budgets, iterations, tools, egress, and time are hard enforcement points.
- Model output never bypasses build, test, security, or approval gates.

## Required inputs

- Classified task and semantic gaps.
- Symbol/dependency graph and selected source context.
- Model catalog/provider credentials and policy.
- Prompt/skill/rule versions, budgets, and tool allowlists.

## Required outputs

- `Versioned gateway contracts and provider adapters.`
- `Model catalog/router and policy decisions.`
- `Prompt registry/context manifests.`
- `Budget ledger, tool-call audit, exact/prefix caches.`
- `Repair-loop evidence and stopping decisions.`

## Repository discovery

Before editing:

1. Locate `AGENTS.md`, `CLAUDE.md`, repository-local Skills, architecture decision records, manifests, schemas, migrations, and build commands.
2. Identify actual control-plane, workflow, runner, engine, web, database, object-store, policy, telemetry, and test modules; do not assume the reference layout exists.
3. Search for existing contracts and implementations before creating duplicates.
4. Record current behavior, known gaps, security boundaries, external side effects, and the exact validation commands that are available.
5. Create or update a durable implementation plan from `templates/IMPLEMENTATION-PLAN.yaml`.

## Execution workflow

1. Select the smallest dependency-resolved vertical slice.
2. Freeze input snapshots, schema/toolchain/policy versions, and rollback boundaries.
3. Implement contract/schema changes before consumers, using backward-compatible transitions.
4. Implement production behavior, authorization, idempotency, telemetry, audit, failure handling, tests, documentation, and runbooks together.
5. Execute focused tests, integration tests, race/failure tests, security tests, and clean-environment reproduction as applicable.
6. Save large outputs by digest; record commands, results, durations, cost, evidence, and residual risk.
7. Report autonomous **system wall-clock runtime** separately from human-equivalent engineering/review effort.
8. Never claim production completion from generated files or static validation alone.

## Implementation checklist

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

## Required artifacts

At minimum, produce or update:

- Versioned contracts and schemas.
- Database migrations and compatibility/rollback notes where state changes.
- Production implementation with explicit authorization, idempotency, retries, cancellation, and failure classification as applicable.
- Unit, integration, end-to-end, race/failure, and security tests appropriate to risk.
- OpenTelemetry instrumentation, operational metrics, alerts, and runbooks for production components.
- Audit/evidence records with immutable input and output digests.
- Updated architecture and operational documentation.
- Task report based on `templates/TASK-REPORT.md`.

## Validation

- [ ] Deny a disallowed provider for private source.
- [ ] Race concurrent calls against a shared budget and prove no overspend.
- [ ] Change prompt/model/policy/permission and require cache miss.
- [ ] Attempt tool/path/network privilege escalation and reject it.
- [ ] Run repeated non-improving repair loops and verify bounded stop/evidence.

Run repository-native format, lint, typecheck, unit, integration, packaging, and security commands. Also run the package validators when Skill content or schemas change:

```bash
python3 scripts/validate_skill_bundle.py
python3 scripts/validate_json_schemas.py
python3 -m unittest discover -s tests -v
```

## Definition of done

- [ ] Every model/tool operation has identity, policy, budget, context, usage, and outcome provenance.
- [ ] No call can exceed hard scope or data policy through fallback.
- [ ] Caching is exact and permission-safe for executable outputs.
- [ ] Agent changes pass deterministic verification before promotion.

Additionally:

- [ ] No placeholder, TODO-only, mock-only, or documentation-only implementation is counted as production completion.
- [ ] All modified public contracts are versioned and compatibility-tested.
- [ ] All side effects are idempotent or reconciled.
- [ ] Critical actions are authorized, audited, and observable.
- [ ] Evidence identifies exact source, toolchain, rule/model/policy, commands, results, and residual risk.
- [ ] Static bundle validation is described accurately as structural validation only.

## Failure handling and handoff

Classify failures as `ENVIRONMENT`, `DEPENDENCY`, `CODE`, `POLICY`, `SECURITY`, `DATA`, `CAPACITY`, `PROVIDER`, or `UNKNOWN`. Preserve successful checkpoints. Put ambiguous side effects in `UNKNOWN_RESULT`/`MANUAL_RECOVERY`; reconcile before retrying. Update the implementation plan with status, commit, commands, measured wall-clock duration, cost, evidence digest, blockers, and the next dependency-resolved task.
