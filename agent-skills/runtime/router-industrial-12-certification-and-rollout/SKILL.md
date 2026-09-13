---
name: "router-industrial-12-certification-and-rollout"
implementation_state: "VERIFIED"
external_evidence_status: "LOCAL_EXECUTED"
production_certification: "NOT_CERTIFIED"
description: "Execute phased traffic ramping (1%->5%->25%->100%), anti-regression gates, and E0-E5 readiness."
metadata:
  source_package: "elmos-router-industrial-skillpack"
  source_package_id: "elmos.router-industrial-skillpack"
  source_version: "1.0.0"
  source_path: "skills/12-certification-and-rollout/SKILL.md"
  source_sha256: "sha256:c3b44afda428c7c505b35d9d42a5c710c787e2e910c07f9c27fd11a2efdbb660"
  normalized_namespace: "router-industrial-v1"
  runtime_module: "engines/router-industrial-engine/src/elmos_router_industrial/skill_runtime.py"
  runtime_dispatcher: "dispatch_skill"
  runtime_skill_key: "router-industrial-12-certification-and-rollout"
  runtime_handler: "execute_12_certification_and_rollout"
  runtime_phase: "certification"
  runtime_evidence: "LOCAL_EXECUTED"
  external_evidence: "NOT_RUN"
  certification: "READY_FOR_RAMPING"
---

## Trusted Repository Runtime Wrapper

This installed Skill is a repository-owned dispatch interface for `router-industrial-12-certification-and-rollout`.
The extracted source mirror in `skills/elmos-router-industrial-skillpack/` provides specification and configuration data.
Execution is strictly mediated by the typed repository engine `engines/router-industrial-engine`.

### Invocation Contract

1. Accept structured requests for exact Skill key `router-industrial-12-certification-and-rollout`.
2. Dispatch only through `engines/router-industrial-engine/src/elmos_router_industrial/skill_runtime.py` / `dispatch_skill` to `execute_12_certification_and_rollout`.
3. Enforce 15 hard policy filters, fail-closed residency checks, token bucket rate limiting, hierarchical budgets, and CAS idempotency.
4. Redact API keys, tokens, and credentials from all prompts, traces, and metrics before egress or persistence.
5. All external vendor calls remain bounded, monitored, circuit-broken, and fallback-eligible.

---

### Source Specification Reference

```markdown
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
```
