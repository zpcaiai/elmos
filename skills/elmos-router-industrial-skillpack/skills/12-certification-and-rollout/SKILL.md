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
