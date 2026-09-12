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
