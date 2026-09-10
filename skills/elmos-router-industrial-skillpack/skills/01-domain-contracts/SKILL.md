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
