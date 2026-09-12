# Skill 02 — Model & Provider Registry

## Goal
Make model capability, cost, compliance, health and deployments data-driven.

## Entities

### ModelDescriptor
- alias
- provider-independent family
- capability vector
- modalities
- context/output bounds
- reasoning profiles
- tool support
- structured output support
- streaming support
- benchmark scores
- lifecycle status: experimental/canary/stable/deprecated/disabled

### ProviderDescriptor
- provider id
- provider type
- supported regions
- retention/training policy metadata
- residency guarantees
- credential reference
- contractual/SLA metadata
- enabled flag

### ProviderDeployment
- deployment id
- model alias
- actual provider model name
- endpoint/region
- lane support
- rate limit profile
- pricing profile
- health state
- priority
- feature overrides

## Registry rules
- Stable aliases never embed price or provider.
- Registry data is versioned.
- Runtime config changes are audited.
- Deprecated models remain resolvable for replay.
- Health is separate from static registry truth.

## Acceptance
- A new model can be introduced by registry/config plus adapter capability, without changing orchestration code.
- A model can have multiple deployments.
- A deployment can be disabled without deleting history.
