---
name: "router-industrial-06-native-provider-adapters"
implementation_state: "VERIFIED"
external_evidence_status: "LOCAL_EXECUTED"
production_certification: "NOT_CERTIFIED"
description: "Execute high-throughput native provider adapters for OpenAI, Anthropic, and self-hosted engines."
metadata:
  source_package: "elmos-router-industrial-skillpack"
  source_package_id: "elmos.router-industrial-skillpack"
  source_version: "1.0.0"
  source_path: "skills/06-native-provider-adapters/SKILL.md"
  source_sha256: "sha256:4ce6c9d52aa7c0e004fc7b75386d59a38c30085a28a285e8355f35f33cca0cb3"
  normalized_namespace: "router-industrial-v1"
  runtime_module: "engines/router-industrial-engine/src/elmos_router_industrial/skill_runtime.py"
  runtime_dispatcher: "dispatch_skill"
  runtime_skill_key: "router-industrial-06-native-provider-adapters"
  runtime_handler: "execute_06_native_provider_adapters"
  runtime_phase: "adapters"
  runtime_evidence: "LOCAL_EXECUTED"
  external_evidence: "NOT_RUN"
  certification: "READY_FOR_RAMPING"
---

## Trusted Repository Runtime Wrapper

This installed Skill is a repository-owned dispatch interface for `router-industrial-06-native-provider-adapters`.
The extracted source mirror in `skills/elmos-router-industrial-skillpack/` provides specification and configuration data.
Execution is strictly mediated by the typed repository engine `engines/router-industrial-engine`.

### Invocation Contract

1. Accept structured requests for exact Skill key `router-industrial-06-native-provider-adapters`.
2. Dispatch only through `engines/router-industrial-engine/src/elmos_router_industrial/skill_runtime.py` / `dispatch_skill` to `execute_06_native_provider_adapters`.
3. Enforce 15 hard policy filters, fail-closed residency checks, token bucket rate limiting, hierarchical budgets, and CAS idempotency.
4. Redact API keys, tokens, and credentials from all prompts, traces, and metrics before egress or persistence.
5. All external vendor calls remain bounded, monitored, circuit-broken, and fallback-eligible.

---

### Source Specification Reference

```markdown
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
```
