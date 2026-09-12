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
