---
name: "router-industrial-09-cost-rate-limit-accounting"
description: "Manage hierarchical budgets, rate limiters, token buckets, and append-only cost ledgers."
metadata:
  source_package: "elmos-router-industrial-skillpack"
  source_package_id: "elmos.router-industrial-skillpack"
  source_version: "1.0.0"
  source_path: "skills/09-cost-rate-limit-accounting/SKILL.md"
  source_sha256: "sha256:e31cb0a5443259fd9e470d5570c4831497a76910b87cc576a0985d052a2a9682"
  normalized_namespace: "router-industrial-v1"
  runtime_module: "engines/router-industrial-engine/src/elmos_router_industrial/skill_runtime.py"
  runtime_dispatcher: "dispatch_skill"
  runtime_skill_key: "router-industrial-09-cost-rate-limit-accounting"
  runtime_handler: "execute_09_cost_rate_limit_accounting"
  runtime_phase: "accounting"
  runtime_evidence: "LOCAL_HANDLER_BOUND_EXECUTED"
  external_evidence: "NOT_RUN"
  certification: "READY_FOR_RAMPING"
---

## Trusted Repository Runtime Wrapper

This installed Skill is a repository-owned dispatch interface for `router-industrial-09-cost-rate-limit-accounting`.
The extracted source mirror in `skills/elmos-router-industrial-skillpack/` provides specification and configuration data.
Execution is strictly mediated by the typed repository engine `engines/router-industrial-engine`.

### Invocation Contract

1. Accept structured requests for exact Skill key `router-industrial-09-cost-rate-limit-accounting`.
2. Dispatch only through `engines/router-industrial-engine/src/elmos_router_industrial/skill_runtime.py` / `dispatch_skill` to `execute_09_cost_rate_limit_accounting`.
3. Enforce 15 hard policy filters, fail-closed residency checks, token bucket rate limiting, hierarchical budgets, and CAS idempotency.
4. Redact API keys, tokens, and credentials from all prompts, traces, and metrics before egress or persistence.
5. All external vendor calls remain bounded, monitored, circuit-broken, and fallback-eligible.

---

### Source Specification Reference

```markdown
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
```
