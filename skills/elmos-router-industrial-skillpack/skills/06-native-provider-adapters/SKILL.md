# Skill 06 — Native Direct Provider Adapters

## Goal
Preserve vendor-native features without contaminating Elmos domain contracts.

## SPI
Implement a provider-neutral executor interface, conceptually:

- `supports(executionPlan)`
- `validate(executionPlan)`
- `execute(request, plan, context)`
- `stream(request, plan, context)`
- `estimateCost(request, plan)`
- `cancel(executionId)` when provider supports it
- `healthProbe(deployment)`

## First adapters
Implement at least two strategic direct providers first, chosen by actual Elmos usage.

## Adapter requirements
- deadline propagation
- idempotency where provider supports it
- normalized usage
- normalized finish reason
- normalized tool call representation
- structured output validation
- provider request id capture
- rate-limit headers capture
- error translation
- cancellation mapping
- retryability classification
- feature-capability probe/tests

## Native feature escape hatch
Provider-specific options live in a versioned `ProviderExtension` envelope scoped to the adapter. They must not become global domain assumptions.

## Acceptance
- Native adapter passes contract suite shared by all executors.
- Unsupported native feature causes explicit validation failure, never silent downgrade.
