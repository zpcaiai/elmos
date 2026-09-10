---
name: "router-industrial-01-domain-contracts"
description: "Enforce provider-neutral typed domain contracts, execution plans, and schema validation."
metadata:
  source_package: "elmos-router-industrial-skillpack"
  source_package_id: "elmos.router-industrial-skillpack"
  source_version: "1.0.0"
  source_path: "skills/01-domain-contracts/SKILL.md"
  source_sha256: "sha256:6f11fe43158886b46528c6f2ceff30c098ff19cfc2f1da42a35cf07172fb175e"
  normalized_namespace: "router-industrial-v1"
  runtime_module: "engines/router-industrial-engine/src/elmos_router_industrial/skill_runtime.py"
  runtime_dispatcher: "dispatch_skill"
  runtime_skill_key: "router-industrial-01-domain-contracts"
  runtime_handler: "execute_01_domain_contracts"
  runtime_phase: "contracts"
  runtime_evidence: "LOCAL_HANDLER_BOUND_EXECUTED"
  external_evidence: "NOT_RUN"
  certification: "READY_FOR_RAMPING"
---

## Trusted Repository Runtime Wrapper

This installed Skill is a repository-owned dispatch interface for `router-industrial-01-domain-contracts`.
The extracted source mirror in `skills/elmos-router-industrial-skillpack/` provides specification and configuration data.
Execution is strictly mediated by the typed repository engine `engines/router-industrial-engine`.

### Invocation Contract

1. Accept structured requests for exact Skill key `router-industrial-01-domain-contracts`.
2. Dispatch only through `engines/router-industrial-engine/src/elmos_router_industrial/skill_runtime.py` / `dispatch_skill` to `execute_01_domain_contracts`.
3. Enforce 15 hard policy filters, fail-closed residency checks, token bucket rate limiting, hierarchical budgets, and CAS idempotency.
4. Redact API keys, tokens, and credentials from all prompts, traces, and metrics before egress or persistence.
5. All external vendor calls remain bounded, monitored, circuit-broken, and fallback-eligible.

---

### Source Specification Reference

```markdown
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
```
