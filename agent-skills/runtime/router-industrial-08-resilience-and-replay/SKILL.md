---
name: "router-industrial-08-resilience-and-replay"
implementation_state: "VERIFIED"
external_evidence_status: "LOCAL_EXECUTED"
production_certification: "NOT_CERTIFIED"
description: "Enforce circuit breakers, jittered retries, CAS idempotency commit, and deterministic replay."
metadata:
  source_package: "elmos-router-industrial-skillpack"
  source_package_id: "elmos.router-industrial-skillpack"
  source_version: "1.0.0"
  source_path: "skills/08-resilience-and-replay/SKILL.md"
  source_sha256: "sha256:5f55f97517689b2a2e6dfd71f2254124c65717cede06102657827535a3367961"
  normalized_namespace: "router-industrial-v1"
  runtime_module: "engines/router-industrial-engine/src/elmos_router_industrial/skill_runtime.py"
  runtime_dispatcher: "dispatch_skill"
  runtime_skill_key: "router-industrial-08-resilience-and-replay"
  runtime_handler: "execute_08_resilience_and_replay"
  runtime_phase: "resilience"
  runtime_evidence: "LOCAL_EXECUTED"
  external_evidence: "NOT_RUN"
  certification: "READY_FOR_RAMPING"
---

## Trusted Repository Runtime Wrapper

This installed Skill is a repository-owned dispatch interface for `router-industrial-08-resilience-and-replay`.
The extracted source mirror in `skills/elmos-router-industrial-skillpack/` provides specification and configuration data.
Execution is strictly mediated by the typed repository engine `engines/router-industrial-engine`.

### Invocation Contract

1. Accept structured requests for exact Skill key `router-industrial-08-resilience-and-replay`.
2. Dispatch only through `engines/router-industrial-engine/src/elmos_router_industrial/skill_runtime.py` / `dispatch_skill` to `execute_08_resilience_and_replay`.
3. Enforce 15 hard policy filters, fail-closed residency checks, token bucket rate limiting, hierarchical budgets, and CAS idempotency.
4. Redact API keys, tokens, and credentials from all prompts, traces, and metrics before egress or persistence.
5. All external vendor calls remain bounded, monitored, circuit-broken, and fallback-eligible.

---

### Source Specification Reference

```markdown
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
```
